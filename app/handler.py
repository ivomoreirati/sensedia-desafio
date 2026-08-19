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
import os
import re
import uuid
from decimal import Decimal

import boto3

TABLE_NAME = os.environ.get("TABLE_NAME")

_dynamodb = boto3.resource("dynamodb")
_ROUTE = re.compile(r"/products(?:/([^/]+))?")


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


def _validate_product(data):
    if not isinstance(data, dict):
        return "corpo da requisição deve ser um objeto JSON"
    name = data.get("name")
    price = data.get("price")
    if not isinstance(name, str) or not name.strip():
        return "'name' é obrigatório e deve ser uma string não vazia"
    if not isinstance(price, (int, float)) or isinstance(price, bool) or price < 0:
        return "'price' é obrigatório e deve ser um número >= 0"
    return None


def _to_item(product_id, data):
    return {
        "id": product_id,
        "name": data["name"],
        "price": Decimal(str(data["price"])),
    }


def handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "")
    path = (event.get("rawPath") or "").rstrip("/") or "/"

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
        if method == "DELETE":
            return _delete_product(product_id)
        return _error(405, f"método {method} não suportado em /products/{{id}}")
    except Exception:
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


def _delete_product(product_id):
    existing = _table().get_item(Key={"id": product_id}).get("Item")
    if existing is None:
        return _error(404, "produto não encontrado")
    _table().delete_item(Key={"id": product_id})
    return _response(204)
