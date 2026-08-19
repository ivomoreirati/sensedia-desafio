locals {
  name_prefix = "${var.project}-${var.env}"
}

# --- Banco: DynamoDB ---------------------------------------------------

resource "aws_dynamodb_table" "products" {
  name         = "${local.name_prefix}-products"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }
}

# --- Identidade: IAM Role da Lambda (sem credencial de banco) ----------

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_exec" {
  name               = "${local.name_prefix}-lambda-exec"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

data "aws_iam_policy_document" "lambda_permissions" {
  statement {
    sid       = "DynamoDBCrud"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:Scan"]
    resources = [aws_dynamodb_table.products.arn]
  }

  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "lambda_permissions" {
  name   = "${local.name_prefix}-lambda-permissions"
  role   = aws_iam_role.lambda_exec.id
  policy = data.aws_iam_policy_document.lambda_permissions.json
}

# --- Compute: Lambda -----------------------------------------------------
# Handler é um placeholder "hello world" nesta etapa — o CRUD completo de
# /products entra em um commit posterior (ver ADR-001 / plano de commits).

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/../app/handler.py"
  output_path = "${path.module}/build/handler.zip"
}

resource "aws_lambda_function" "api" {
  function_name    = "${local.name_prefix}-api"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "handler.handler"
  runtime          = "python3.12"
  timeout          = 10
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      TABLE_NAME = aws_dynamodb_table.products.name
      ENV        = var.env
    }
  }
}

resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api.function_name
  authorization_type = "NONE" # ver README/ADR: autenticação fora de escopo, decisão explícita

  lifecycle {
    # O LocalStack não devolve `invoke_mode` na leitura do recurso, então o
    # Terraform detecta drift falso e tenta corrigir a cada apply. Nada muda
    # de fato (comportamento real da AWS/LocalStack é idêntico); ignoramos
    # esse atributo para que `up` rodado 2x reporte "no changes" de verdade.
    ignore_changes = [invoke_mode]
  }
}
