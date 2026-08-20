"""Lambda handler — CRUD de /products.

Invocado via Function URL (sem API Gateway — ver ADR-001), então o
roteamento por método/path é feito aqui dentro, não numa camada de borda
declarativa.

Nota: a emulação de Function URL do LocalStack 3.0 (community) não repassa
o `statusCode` da resposta da Lambda para o HTTP real — o cliente sempre
recebe 200, mesmo quando este handler retorna 404/400/204. Confirmado que
o handler está correto invocando a função diretamente via
`aws lambda invoke` (bypassa a Function URL). É uma limitação do
emulador, não do código; documentado em ADR-001. Em AWS real o
comportamento é o padrão (statusCode repassado normalmente).
"""

import base64
import json
import logging
import math
import os
import re
import uuid
from decimal import Decimal

import boto3

TABLE_NAME = os.environ.get("TABLE_NAME")

_dynamodb = boto3.resource("dynamodb")
_ROUTE = re.compile(r"/products(?:/([^/]+))?")

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _log(event_type: str, **fields):
    """Log estruturado em JSON — uma linha por evento, fácil de indexar em
    CloudWatch Logs Insights (ou no que quer que leia os logs no LocalStack).
    Nunca loga corpo de requisição/resposta: evita vazar dados de produto ou
    qualquer coisa sensível no futuro, mesmo não havendo segredo hoje.
    """
    logger.info(json.dumps({"event": event_type, **fields}))


def _table():
    return _dynamodb.Table(TABLE_NAME)


def _json_default(value):
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"tipo não serializável: {type(value)}")


def _response(status_code, body=None):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=_json_default) if body is not None else "",
    }


def _error(status_code, message):
    return _response(status_code, {"error": message})


def _parse_body(event):
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _is_valid_price(price):
    """Exclui bool (subclasse de int) e Infinity/NaN (JSON do Python aceita
    ambos por padrão, mas DynamoDB rejeita — sem isso, viravam 500 em vez de
    400, achado em revisão de qualidade)."""
    return isinstance(price, (int, float)) and not isinstance(price, bool) and math.isfinite(price) and price >= 0


def _validate_product(data):
    if not isinstance(data, dict):
        return "corpo da requisição deve ser um objeto JSON"
    name = data.get("name")
    price = data.get("price")
    if not isinstance(name, str) or not name.strip():
        return "'name' é obrigatório e deve ser uma string não vazia"
    if not _is_valid_price(price):
        return "'price' é obrigatório e deve ser um número finito >= 0"
    return None


def _to_item(product_id, data):
    return {
        "id": product_id,
        "name": data["name"],
        "price": Decimal(str(data["price"])),
    }


def _validate_partial_product(data):
    """Para PATCH: qualquer subconjunto de {name, price} é aceito, desde que
    pelo menos um campo venha e cada campo presente seja válido. Diferente de
    PUT, que exige o objeto inteiro (substituição total)."""
    if not isinstance(data, dict):
        return "corpo da requisição deve ser um objeto JSON"
    if "name" not in data and "price" not in data:
        return "informe pelo menos um campo para atualizar: 'name' ou 'price'"
    if "name" in data and (not isinstance(data["name"], str) or not data["name"].strip()):
        return "'name', se informado, deve ser uma string não vazia"
    if "price" in data and not _is_valid_price(data["price"]):
        return "'price', se informado, deve ser um número finito >= 0"
    return None


def handler(event, context):
    # .get(k) or {} em vez de .get(k, {}): o default só vale quando a chave
    # está ausente, não quando está presente com valor None (evento de teste
    # construído à mão pode ter "requestContext": null) — achado em revisão
    # de qualidade, causava AttributeError não tratado antes do try/except.
    request_context = event.get("requestContext") or {}
    method = (request_context.get("http") or {}).get("method", "")
    path = (event.get("rawPath") or "").rstrip("/") or "/"
    _log("request_received", method=method, path=path)

    response = _route(method, path, event)

    _log("request_completed", method=method, path=path, status=response["statusCode"])
    return response


def _route(method, path, event):
    if method == "GET" and path == "/health":
        return _response(200, {"status": "ok"})

    match = _ROUTE.fullmatch(path)
    if not match:
        return _error(404, f"rota não encontrada: {path}")
    product_id = match.group(1)

    try:
        if product_id is None:
            if method == "GET":
                return _list_products()
            if method == "POST":
                return _create_product(event)
            return _error(405, f"método {method} não suportado em /products")

        if method == "GET":
            return _get_product(product_id)
        if method == "PUT":
            return _update_product(product_id, event)
        if method == "PATCH":
            return _patch_product(product_id, event)
        if method == "DELETE":
            return _delete_product(product_id)
        return _error(405, f"método {method} não suportado em /products/{{id}}")
    except Exception:
        # Stack trace completo vai só pro log interno (CloudWatch/LocalStack) —
        # o cliente nunca vê mais do que a mensagem genérica abaixo.
        logger.exception("erro inesperado processando requisição")
        return _error(500, "erro interno ao processar a requisição")


def _list_products():
    items = _table().scan().get("Items", [])
    return _response(200, items)


def _create_product(event):
    data = _parse_body(event)
    error = _validate_product(data)
    if error:
        return _error(400, error)

    item = _to_item(str(uuid.uuid4()), data)
    _table().put_item(Item=item)
    return _response(201, item)


def _get_product(product_id):
    item = _table().get_item(Key={"id": product_id}).get("Item")
    if item is None:
        return _error(404, "produto não encontrado")
    return _response(200, item)


def _update_product(product_id, event):
    existing = _table().get_item(Key={"id": product_id}).get("Item")
    if existing is None:
        return _error(404, "produto não encontrado")

    data = _parse_body(event)
    error = _validate_product(data)
    if error:
        return _error(400, error)

    item = _to_item(product_id, data)
    _table().put_item(Item=item)
    return _response(200, item)


def _patch_product(product_id, event):
    """Atualização parcial: só sobrescreve os campos enviados.

    Existe ao lado de PUT (substituição total) — decisão registrada em
    METODOLOGIA.md ponto 3: PUT sozinho obrigava reenviar o objeto inteiro
    até pra mudar um campo, o que não fazia sentido para o escopo deste
    CRUD nem facilitava testar a API manualmente.
    """
    existing = _table().get_item(Key={"id": product_id}).get("Item")
    if existing is None:
        return _error(404, "produto não encontrado")

    data = _parse_body(event)
    error = _validate_partial_product(data)
    if error:
        return _error(400, error)

    merged = {
        "name": data.get("name", existing["name"]),
        "price": data.get("price", existing["price"]),
    }
    item = _to_item(product_id, merged)
    _table().put_item(Item=item)
    return _response(200, item)


def _delete_product(product_id):
    existing = _table().get_item(Key={"id": product_id}).get("Item")
    if existing is None:
        return _error(404, "produto não encontrado")
    _table().delete_item(Key={"id": product_id})
    return _response(204)
