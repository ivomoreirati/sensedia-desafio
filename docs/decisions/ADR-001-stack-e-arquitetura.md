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

**Decisão**: API Gateway/Function URL → Lambda → DynamoDB, acesso via IAM Role.

**Trade-off assumido**: nenhuma credencial de banco existe nesta arquitetura — não é
"escondida com cuidado", ela simplesmente não existe, porque o acesso é via IAM. Isso
resolve R4 por construção. Em troca, abro mão de demonstrar modelagem relacional e de
uma arquitetura mais próxima do que muitas empresas rodam em produção com banco SQL.

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
compartilhável": como o ambiente inteiro é local e efêmero, perseguir backend remoto
(S3 + lock DynamoDB) resolveria um problema que não existe neste contexto. Documento
aqui como pensaria isso em um cenário AWS real, mas não implemento.
