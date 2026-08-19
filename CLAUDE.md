# CLAUDE.md

Contexto para qualquer agente (Claude ou outro) trabalhando neste repositório.

## O que é este projeto

Desafio técnico Sensedia — Platform Services. Um CLI de provisionamento (`up`/`destroy`)
que sobe uma infraestrutura de nuvem sustentando uma API HTTP com CRUD (`/products`)
persistindo em banco. O produto avaliado é a CLI, não a API — trate erros e mensagens
de CLI com o mesmo cuidado que trataria uma feature de produto.

O usuário-alvo da CLI é um operador de infraestrutura que nunca viu o código. Toda
mensagem de erro, help text e exit code deve ser pensado para essa pessoa, não para
quem está desenvolvendo.

## Decisões de stack (não desviar sem registrar um novo ADR em docs/decisions/)

- **CLI**: Python 3 + Typer. Dependências via `venv` + `pip` (`requirements.txt`), sem
  Poetry/uv.
- **Provisionamento**: Terraform (não OpenTofu, não Pulumi, não SDK direto), invocado
  via `subprocess` a partir da CLI.
- **Alvo de nuvem**: LocalStack (sem conta AWS real). Provider AWS do Terraform aponta
  `endpoints {}` para `http://localhost:4566`. Credenciais são sempre dummy
  (`test`/`test`), injetadas por variável de ambiente — nunca hardcoded, mesmo sendo
  fake, para manter o mesmo mecanismo que valeria com AWS real.
- **Arquitetura**: Lambda + DynamoDB, acesso via IAM Role (sem credencial de banco —
  decisão que resolve R4 por construção).
- **Layout do repo**: `cli/` (Typer app, sem lógica de infra), `infra/` (só Terraform),
  `app/` (handler da Lambda, CRUD), `docs/decisions/` (ADRs).

## Convenções

- `up --env <env>` e `destroy --env <env>` precisam ser idempotentes: rodar duas vezes
  não quebra nem duplica. "Nada a fazer" é sucesso (`exit 0`), não erro.
- stdout = resultado para o operador. stderr = diagnóstico/erro. Exit code é a API real
  da CLI — nunca retornar 0 em caso de falha.
- Terraform state fica local e fora do controle de versão (diferencial de state remoto
  foi conscientemente descartado — ver ADR-001).
- Commits em Conventional Commits (`feat`, `fix`, `docs`, `test`, `chore`), um bloco de
  decisão+implementação por commit, refletindo o processo real de desenvolvimento — não
  reescrever/squashar histórico para parecer mais bonito.
- Antes de adicionar recurso, dependência ou escopo não decidido em nenhum ADR, sinalizar
  em vez de assumir.
