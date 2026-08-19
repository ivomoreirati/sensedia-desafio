# Credenciais (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY) vêm de variável de
# ambiente, nunca hardcoded aqui — mesmo sendo valores dummy do LocalStack
# (ver .env.example e CLAUDE.md).
provider "aws" {
  region                      = var.region
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    dynamodb       = var.localstack_endpoint
    lambda         = var.localstack_endpoint
    iam            = var.localstack_endpoint
    sts            = var.localstack_endpoint
    cloudwatchlogs = var.localstack_endpoint
  }
}
