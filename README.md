# Desafio Técnico Sensedia — Platform Services

CLI de provisionamento (`up`/`destroy`) que sobe uma infraestrutura serverless
(Lambda + DynamoDB) sustentando uma API HTTP com CRUD de `/products`, rodando
inteiramente contra o [LocalStack](https://www.localstack.cloud/) — sem conta de
nuvem real, sem custo.

O produto avaliado aqui é a **CLI**, não a API. Decisões de arquitetura e os
trade-offs assumidos estão documentados em [`docs/decisions/ADR-001-stack-e-arquitetura.md`](docs/decisions/ADR-001-stack-e-arquitetura.md).
O processo de desenvolvimento assistido por IA está em [`METODOLOGIA.md`](METODOLOGIA.md).

## Pré-requisitos

- **Docker Desktop** rodando (o LocalStack e a execução da Lambda dependem dele —
  o executor de Lambda do LocalStack sobe o runtime da função em um container
  próprio, montando o socket do Docker do host)
- **Python 3.11+**
- **[Terraform](https://developer.hashicorp.com/terraform/install)** (`brew tap hashicorp/tap && brew install hashicorp/tap/terraform` no macOS —
  a fórmula saiu do Homebrew core, precisa do tap oficial da HashiCorp)

Nada além disso. Nenhuma conta de nuvem, nenhuma credencial real.

## Setup

```bash
git clone <url-deste-repositório>
cd sensedia-desafio

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # credenciais dummy do LocalStack — já vêm preenchidas

docker compose up -d   # sobe o LocalStack em localhost:4566
```

Aguarde o LocalStack ficar pronto (alguns segundos):

```bash
curl -s http://localhost:4566/_localstack/health
```

## Uso da CLI

```bash
python -m cli.main up --env dev        # provisiona / reconcilia o ambiente
python -m cli.main up --env dev        # rodar de novo: "já estava atualizado", exit 0

python -m cli.main destroy --env dev   # pede confirmação antes de destruir
python -m cli.main destroy --env dev --yes   # sem confirmação, para automação/CI

python -m cli.main status --env dev    # inspeciona sem efeito colateral (não cria/muda/destrói nada)
```

`--env` aceita `dev` ou `stg` — cada um em um workspace Terraform separado (state
isolado), validado criando dados em `dev` e confirmando que não aparecem em `stg`,
e que destruir um não afeta o outro.

Convenções da CLI:
- **stdout** é o resultado para o operador; **stderr** é diagnóstico/erro.
- **Exit code 0** = sucesso, incluindo "nada a fazer" (ambiente já atualizado ou já
  destruído). **Exit code ≠ 0** = falha real, sempre.
- Nenhum stacktrace Python chega até o operador — erros do Terraform são
  traduzidos para uma mensagem legível.

## Testando a API

Depois do `up`, pegue a URL pública da Lambda:

```bash
FUNCTION_URL=$(AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1 \
  terraform -chdir=infra output -raw function_url)
```

```bash
# Health check (não toca no banco — só confirma que a Lambda está viva)
curl -s "$FUNCTION_URL/health"

# Criar
curl -s -X POST "$FUNCTION_URL/products" \
  -H "Content-Type: application/json" \
  -d '{"name":"Teclado mecânico","price":350.50}'
# {"id": "...", "name": "Teclado mecânico", "price": 350.5}

# Listar
curl -s "$FUNCTION_URL/products"

# Buscar um
curl -s "$FUNCTION_URL/products/<id>"

# Atualizar
curl -s -X PUT "$FUNCTION_URL/products/<id>" \
  -H "Content-Type: application/json" \
  -d '{"name":"Teclado mecânico RGB","price":399.90}'

# Remover
curl -s -X DELETE "$FUNCTION_URL/products/<id>"
```

> **Nota sobre status HTTP no LocalStack**: a emulação de Function URL do
> LocalStack 3.0 (community) não repassa o `statusCode` do handler para a resposta
> HTTP real — todo `curl` acima retorna `200`, mesmo em erro (`404`/`400`). O
> handler está correto (confirmado invocando a Lambda diretamente via
> `aws lambda invoke`, que retorna o `statusCode` certo); é uma limitação do
> emulador, documentada em detalhe no ADR-001. Em AWS real o comportamento é o
> padrão — o cliente recebe o status HTTP correto.

## Rodando os testes

```bash
python -m pytest cli/tests/ -v
```

Testes da CLI não dependem de Docker/LocalStack/rede (mockam o `terraform_runner`)
— rodam em frações de segundo. Não há testes automatizados para o handler da
Lambda; o CRUD foi validado manualmente via `curl` contra o LocalStack (ver
histórico de commits).

## Arquitetura

```
operador → CLI (Python/Typer) → subprocess → Terraform → LocalStack
                                                              │
                                                    Lambda Function URL
                                                              │
                                                       Lambda (Python)
                                                              │
                                                      DynamoDB (via IAM Role)
```

Sem API Gateway (Function URL é suficiente para um único recurso HTTP) e sem
credencial de banco (acesso via IAM Role — não existe usuário/senha para
vazar). Decisões completas, alternativas descartadas e trade-offs assumidos:
[ADR-001](docs/decisions/ADR-001-stack-e-arquitetura.md).

### Autenticação

A API **não tem autenticação** (`authorization_type = "NONE"` na Function URL).
Decisão deliberada, não omissão: o desafio permite explicitamente autenticação
trivial ou inexistente, e qualquer mecanismo de auth (API key, JWT, IAM auth na
própria Function URL) adicionaria superfície de configuração e de erro sem
testar nada que este desafio avalia — a CLI e o ciclo de vida da
infraestrutura, não a segurança de borda da API. Em um cenário real de
produção, o próximo passo seria IAM auth na Function URL (`authorization_type
= "AWS_IAM"`) ou um autenticador Lambda na frente, dependendo de quem consome
a API.

## Estrutura do repositório

```
cli/                  # Typer app — comandos up/destroy, sem lógica de infra
  main.py
  terraform_runner.py # wrapper fino sobre `terraform` via subprocess
  tests/               # testes que não dependem de cloud
infra/                # só Terraform
  main.tf
  envs/                # dev.tfvars, stg.tfvars
app/
  handler.py           # Lambda: CRUD de /products
docs/decisions/         # ADRs
.github/workflows/ci.yml # testes da CLI + terraform fmt/validate, sem provisionar
.claude/commands/adr.md  # comando customizado: registra decisões como ADR
CLAUDE.md               # configuração/contexto ensinado ao agente de IA
METODOLOGIA.md           # processo de desenvolvimento assistido por IA
```

## Requisitos do desafio — checklist

| # | Requisito | Como é atendido |
|---|---|---|
| R1 | `up` idempotente | Terraform state calcula diff; segunda chamada reporta "já estava atualizado", exit 0. Validado manualmente 2x seguidas. |
| R2 | `destroy` sem órfãos, seguro rodar 2x | Terraform destroy usa o state para saber tudo que existe; segunda chamada reporta "já estava destruído", exit 0. Validado manualmente 2x seguidas. |
| R3 | Credencial de nuvem nunca no repo | `.gitignore` cobre `.env`/`.tfstate`; credenciais (mesmo dummy do LocalStack) só via variável de ambiente, nunca hardcoded no `.tf`. |
| R4 | API não expõe credencial de banco | Acesso Lambda→DynamoDB via IAM Role — não existe credencial de banco na arquitetura. |
| R5 | README reproduzível do zero | Este arquivo. |
| R6 | Decisões de arquitetura registradas | [ADR-001](docs/decisions/ADR-001-stack-e-arquitetura.md). |
| R7 | METODOLOGIA.md com 2+ abordagens | [METODOLOGIA.md](METODOLOGIA.md). |
| R8 | Artefatos de processo e config de agentes versionados | [CLAUDE.md](CLAUDE.md), [`.claude/commands/adr.md`](.claude/commands/adr.md), histórico de commits, este README. |

Diferenciais entregues: segundo ambiente (`--env stg`, isolado por workspace do
Terraform — validado com dados reais), comando `status` de inspeção sem efeito
colateral, `destroy` com confirmação + `--yes`, testes automatizados sem
dependência de nuvem, CI validando testes + `terraform fmt`/`validate` sem
provisionar, comando customizado do Claude Code (`/adr`) para registrar novas
decisões de arquitetura, `/health` + log estruturado em JSON (sem corpo de
requisição/resposta), histórico de commits espelhando decisão → implementação
→ ajuste.

Diferencial conscientemente **não** perseguido: estado do Terraform em backend
remoto (S3 + lock DynamoDB). Justificativa em ADR-001, Decisão 4.
