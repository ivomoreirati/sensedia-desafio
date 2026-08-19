output "function_url" {
  description = "URL HTTP pública da API (Lambda Function URL)"
  value       = aws_lambda_function_url.api.function_url
}

output "table_name" {
  description = "Nome da tabela DynamoDB usada pela API"
  value       = aws_dynamodb_table.products.name
}
