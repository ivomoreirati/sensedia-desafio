variable "env" {
  description = "Nome do ambiente (usado para isolar recursos: dev, stg)"
  type        = string

  validation {
    condition     = contains(["dev", "stg"], var.env)
    error_message = "env deve ser \"dev\" ou \"stg\"."
  }
}

variable "region" {
  description = "Região AWS (arbitrária no LocalStack, mas exigida pelo provider)"
  type        = string
  default     = "us-east-1"
}

variable "localstack_endpoint" {
  description = "Endpoint do LocalStack para todos os serviços AWS usados"
  type        = string
  default     = "http://localhost:4566"
}

variable "project" {
  description = "Prefixo usado no nome de todos os recursos, para evitar colisão com outros projetos no mesmo LocalStack"
  type        = string
  default     = "sensedia-desafio"
}
