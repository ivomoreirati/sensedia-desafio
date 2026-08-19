import json
import os


def handler(event, context):
    """Placeholder — confirma que a infra sobe e responde de ponta a ponta.

    O CRUD real de /products entra em um commit posterior (ver
    docs/decisions/ADR-001-stack-e-arquitetura.md).
    """
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(
            {
                "message": "ok",
                "env": os.environ.get("ENV", "unknown"),
                "table": os.environ.get("TABLE_NAME", "unknown"),
            }
        ),
    }
