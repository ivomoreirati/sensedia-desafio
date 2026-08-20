# ADR-001 — Stack e arquitetura inicial

**Status**: aceito
**Data**: 2026-08-19

## Contexto

Desafio técnico de 3 dias úteis: construir um CLI de provisionamento de ambiente
(`up`/`destroy`) que sustenta uma API HTTP com CRUD persistindo em banco. A avaliação
pesa, em ordem: (1) a CLI como produto, (2) idempotência do ciclo de vida, (3)
metodologia de uso de IA, (4) decisões de arquitetura, (5) qualidade de código, (6) API
e persistência. Linguagem, provider de nuvem e ferramenta de IaC são livres.

## Decisão 1 — Linguagem da CLI: Python + Typer

Nunca construí uma CLI antes. Em 3 dias, o risco maior é gastar tempo aprendendo o
ecossistema de CLI em si, não resolvendo o problema.

**Alternativas descartadas**:
- **Go + Cobra**: alinhado ao stack do time (usa Go no dia a dia), mas eu nunca usei Go.
  O próprio enunciado diz que a linguagem não é critério de corte — arriscar a entrega
  por alinhamento cultural não compensa.
- **Java + Picocli**: é minha linguagem mais forte, mas tem mais boilerplate e ciclo de
  build/empacotamento mais lento de iterar em 3 dias.

**Trade-off assumido**: abro mão de alinhamento com o stack do time (Go) em troca de
velocidade e confiabilidade de entrega. Typer gera `--help`, parsing e validação a
partir de type hints, o que reduz drasticamente código de infraestrutura da própria CLI.

## Decisão 2 — Provisionamento: Terraform via subprocess

**Alternativas descartadas**:
- **SDK direto (boto3)**: imperativo — cada chamada de API não sabe se o recurso já
  existe. Cumprir idempotência (R1) e destroy sem órfãos (R2) exigiria implementar
  reconciliação de estado manualmente, um risco alto de bug em 3 dias.
- **Pulumi**: mesmas garantias declarativas de idempotência via state, e unificaria tudo
  em Python. Descartado por ter ecossistema menor e menos peso como padrão de mercado
  para defender numa entrevista de Platform Services.

**Decisão**: Terraform (não OpenTofu — mesma sintaxe, mas documentação/exemplos mais
consistentes) orquestrado via `subprocess` pela CLI. O state do Terraform é o registro
de "o que já existe"; `apply`/`destroy` calculam diff contra esse state, o que resolve
R1 e R2 por construção em vez de por código escrito à mão.

**Trade-off assumido**: dependência externa (binário `terraform` precisa estar
disponível) e uma camada de abstração a mais — erros que chegam até a CLI são erros do
Terraform, que precisam ser traduzidos para algo legível ao operador.

## Decisão 3 — Arquitetura: Lambda + DynamoDB via IAM Role (serverless)

**Alternativas descartadas**:
- **ECS Fargate + RDS Postgres**: arquitetura mais "enterprise tradicional", banco
  relacional real. Descartada porque exige VPC/ALB/Security Groups/Secrets Manager —
  mais superfície de infra e de perguntas na defesa, provisiona mais devagar (atrapalha
  iterar `up`/`destroy` repetidamente em 3 dias), e exige gerenciar credencial de banco
  de verdade.
- **EC2 (VM)**: mais manual (gestão de SO, systemd), foge do que se espera de automação
  moderna de plataforma. Sem vantagem clara para este escopo.

**Decisão**: Lambda → DynamoDB, acesso via IAM Role.

**Trade-off assumido**: nenhuma credencial de banco existe nesta arquitetura — não é
"escondida com cuidado", ela simplesmente não existe, porque o acesso é via IAM. Isso
resolve R4 por construção. Em troca, abro mão de demonstrar modelagem relacional e de
uma arquitetura mais próxima do que muitas empresas rodam em produção com banco SQL.

## Decisão 3b — Exposição HTTP: Lambda Function URL (não API Gateway)

**Alternativas descartadas**:
- **API Gateway (HTTP API)**: mais peças de Terraform (API, integração, rota,
  deploy/stage — 3+ recursos a mais só pra expor a mesma Lambda), e recursos
  (throttling, domínio customizado, autenticação de borda, múltiplos backends)
  que este escopo não usa — um recurso HTTP CRUD só.

**Decisão**: `aws_lambda_function_url`, sem API Gateway. Roteamento por
método/path fica dentro do próprio handler (ver `app/handler.py`), já que a
Function URL não tem conceito de rota declarativa.

**Trade-off assumido**: abro mão de recursos prontos de borda (throttling,
domínio customizado, API keys) que um API Gateway daria de graça, em troca de
menos infraestrutura pra provisionar/destruir/manter e menos superfície pra
errar em 3 dias. Também descobri na prática que isso tem um custo de emulação:
a Function URL no LocalStack 3.0 (community) não repassa `statusCode` do
handler pro HTTP real (ver limitação abaixo) — um trade-off que só apareceu
testando, não era previsível na decisão.

## Decisão 4 — Alvo de nuvem: LocalStack

**Alternativas descartadas**: AWS real (free tier) — validaria uma URL pública de
verdade, mas depende de conta pessoal e de gestão de credencial real.

**Decisão**: LocalStack. O desafio aceita emulador local sem prejuízo de avaliação.
Elimina qualquer risco de custo e qualquer necessidade de gerenciar credencial real de
nuvem (R3 fica trivialmente satisfeito, mas o mecanismo de injeção de credencial por
variável de ambiente é mantido como se fosse real).

**Trade-off assumido**: não entrego uma URL pública real — entrego `docker compose up` +
`curl` de exemplo rodando localmente, conforme a alternativa explicitamente aceita pelo
enunciado. Também descarto o diferencial de "estado persistido em lugar durável e
compartilhável": como o ambiente inteiro é local e efêmero (uma pessoa, uma máquina),
perseguir backend remoto resolveria um problema que não existe neste contexto.

**Como eu pensaria o backend remoto se o contexto exigisse** (mais de uma pessoa/máquina
operando o mesmo ambiente):

```hcl
terraform {
  backend "s3" {
    bucket         = "sensedia-desafio-tfstate"
    key            = "infra/terraform.tfstate"  # workspace_key_prefix separa dev/stg automaticamente
    region         = "us-east-1"
    dynamodb_table = "sensedia-desafio-tfstate-lock"  # lock de escrita concorrente
    encrypt        = true
  }
}
```

O ponto que exige desenho, não só configuração: isso cria um problema de
"ovo e galinha" — o backend S3+DynamoDB precisa existir *antes* do `terraform
init` conseguir usá-lo, então não pode ser criado pelo mesmo `.tf` que ele
armazena o state de. A solução usual é um bootstrap separado (um `.tf` menor,
aplicado uma vez, fora do fluxo normal de `up`/`destroy`, ou até criado
manualmente/via script na primeira vez que alguém configura o projeto). A CLI
também mudaria: `up`/`destroy` passariam a assumir que esse backend já existe,
em vez de gerenciar seu próprio ciclo de vida.

Como o LocalStack já emula S3 e DynamoDB, dava para validar esse desenho sem
custo de AWS real — não fiz isso porque não resolve nenhum requisito
obrigatório nem diferencial que valha mais que o tempo que tiraria de CLI e
CRUD, que pesam mais na avaliação.

**Limitações de emulação encontradas na prática** (vale a pena registrar porque afeta
o que se observa testando a API, não a correção do código):

- `localstack/localstack:latest` passou a exigir `LOCALSTACK_AUTH_TOKEN` mesmo no
  edition community — fixamos a imagem em `3.0` no `docker-compose.yml`.
- A Function URL da Lambda no LocalStack 3.0 (community) não repassa o `statusCode`
  retornado pelo handler para o HTTP real: toda resposta chega ao cliente como `200`,
  mesmo quando o handler retorna `404`/`400`/`204`. Confirmado com `aws lambda invoke`
  direto (sem passar pela Function URL) que o handler devolve o `statusCode` correto —
  é limitação do emulador, não bug de aplicação. Em AWS real o comportamento é padrão.
