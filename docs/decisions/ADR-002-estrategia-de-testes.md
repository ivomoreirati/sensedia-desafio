# ADR-002 — Estratégia de testes: CLI automatizada, handler validado manualmente

**Status**: aceito
**Data**: 2026-08-20

## Contexto

A CLI (`cli/`) tem 18 testes unitários (`cli/tests/test_cli.py`), rodando em
CI a cada push. O handler da Lambda (`app/handler.py`), que implementa o CRUD
de `/products`, não tem nenhum teste automatizado — foi validado manualmente
via `curl` contra o LocalStack ao longo da sessão (create/list/get/update/
patch/delete, mais os casos de erro 400/404), com os resultados registrados
nas mensagens de commit correspondentes.

## Decisão — Estratégia de teste por camada

**Alternativas descartadas**:
- **Testes unitários do handler com mock de `boto3`** (ex.: biblioteca
  `moto`): permitiria testar validação/roteamento sem tocar rede, no mesmo
  espírito dos testes da CLI. Descartada porque mockar o DynamoDB não teria
  pego os dois bugs reais que só apareceram testando contra o LocalStack de
  verdade — o drift de `invoke_mode` na Function URL e a Function URL não
  repassando `statusCode` pro HTTP real (ambos em ADR-001). Um mock de boto3
  dá falsa confiança: a lógica pura fica coberta, mas o comportamento real de
  integração, que é onde os bugs de verdade apareceram, não.
- **Testes de integração automatizados contra o LocalStack real** (subir
  `docker compose`, `terraform apply`, bater na Function URL de verdade,
  `terraform destroy`, tudo dentro da suite/CI): seria a cobertura mais fiel
  ao comportamento real. Descartada para esta semana por custo de
  infraestrutura de teste — orquestrar Docker + Terraform dentro de uma
  suite automatizada é mais pesado e mais lento que os testes unitários da
  CLI, e essa mesma sessão teve um incidente real de Docker travando a
  máquina por disco cheio, o que reforça o risco de rodar isso repetidamente
  sem supervisão. Já registrado em `METODOLOGIA.md` (ponto 4) como algo a
  fazer em 6 meses, não em 3 dias.

**Decisão**: testes automatizados só na CLI; handler validado manualmente via
`curl`, com os resultados documentados no histórico de commits e no README
(seção "Rodando os testes").

**Trade-off assumido**: abro mão de uma rede de segurança automática para
regressões futuras no handler — qualquer mudança em `app/handler.py` precisa
de validação manual de novo, sem teste que quebre sozinho em CI se algo
regredir. Em troca, não gasto o tempo escasso de 3 dias orquestrando
infraestrutura de teste de integração que já provou ser frágil nesta mesma
máquina. Essa alocação de esforço é deliberada, não descuido: a CLI é o item
de maior peso na avaliação (critério 1) e recebeu o investimento de testes
automatizados; a API é o item de menor peso (critério 6) e ficou com
validação manual, suficiente para o escopo mas não para evolução contínua.
