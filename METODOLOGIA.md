# METODOLOGIA.md

## 1. Abordagens consideradas

Considerei duas abordagens pra este projeto de 3 dias.

**A — Deliberação guiada por teoria e trade-offs antes de cada bloco (escolhida).**
Antes de escrever qualquer código, cada decisão (linguagem, ferramenta de IaC,
arquitetura de nuvem, exposição HTTP, modelo de dados) passou por uma etapa de
teoria explícita + trade-offs comparados lado a lado + escolha justificada,
registrada em [ADR-001](docs/decisions/ADR-001-stack-e-arquitetura.md). Só
depois disso o código correspondente era escrito.

**B — Ping-pong iterativo (descartada).** Pedir código função por função, sem
uma fase de deliberação prévia, ajustando conforme os problemas aparecem na
prática.

**Por que A**: o escopo do desafio é pequeno e fechado pelo próprio enunciado
(dois comandos, CRUD de um recurso, requisitos numerados R1-R8). Pra esse tipo
de escopo, o custo principal de A é tempo de conversa antes de existir a
primeira linha de infraestrutura; o ganho é que incompatibilidades de decisão
(ex.: Function URL vs. API Gateway, LocalStack vs. AWS real) apareceram *antes*
de eu escrever Terraform em cima delas, não depois de já ter investido tempo
numa direção errada. Para um projeto sem escopo fixo — uma feature nova em
produto vivo, por exemplo — a abordagem B, iterando rápido e descobrindo o
escopo no processo, provavelmente teria sido mais rápida.

## 2. Onde a IA acelerou e onde atrapalhou ou errou

**Acelerou:**
- Boilerplate do Terraform (provider, `data "aws_iam_policy_document"`,
  recursos) saiu correto de primeira — nenhum erro de sintaxe em nenhum
  `apply` rodado.
- Os 10 testes unitários da CLI (estrutura de mocking com
  `typer.testing.CliRunner`) foram escritos e passaram já na primeira rodada.
- Diagnóstico de causa raiz em dois incidentes reais durante a sessão: disco
  cheio derrubando o Docker (cruzando `df -h` com o erro de I/O reportado) e o
  loop de drift de `invoke_mode` na Function URL (comparando `apply` repetido
  com invocação direta da Lambda via `aws lambda invoke`).
- Documentação (ADR, README) ficou completa e organizada em muito menos tempo
  do que escrever do zero.

**Atrapalhou ou errou:**
- Deu uma instrução errada sobre `.terraform.lock.hcl`: disse inicialmente que
  "costuma-se ignorar" no `.gitignore`, quando a prática correta é versionar
  esse arquivo (trava as versões exatas dos providers, o que é o que garante
  reprodução idêntica em outra máquina). Autocorrigido antes de aplicar, mas
  foi um erro real de instrução, não só imprecisão de linguagem.
- Assumiu implicitamente que "Terraform = idempotência garantida" sem
  qualificar que isso depende do provider/emulador refletir o estado real com
  fidelidade. Só ficou claro que a suposição era incompleta ao rodar `apply`
  duas vezes de verdade contra o LocalStack e ver "1 to change" em vez de "No
  changes" — o LocalStack não devolve `invoke_mode` na leitura do recurso, e
  nada nisso seria detectado sem testar de fato, não só ler o código.
- Escolheu `localstack/localstack:latest` no `docker-compose.yml` sem saber
  que uma mudança recente de licenciamento do LocalStack passou a exigir
  token de autenticação mesmo no edition community — só descoberto ao rodar,
  não antecipado antes.
- Escreveu o comando `up`/`destroy` inicial sem selecionar workspace do
  Terraform, o que significava que `dev` e `stg` compartilhariam o mesmo
  state local — aplicar `stg` depois de `dev` destruiria os recursos de
  `dev`. Só apareceu ao testar de propósito o diferencial de segundo
  ambiente; não foi antecipado no desenho original da CLI. Corrigido com
  `terraform workspace select/new` por ambiente.

## 3. Caso concreto de discordância

Pedi pro agente listar decisões de implementação que ele tinha tomado sozinho
dentro do que eu já tinha aprovado em nível mais alto, justamente pra ter algo
concreto pra concordar ou discordar — até esse ponto, toda decisão relevante
já tinha sido validada *antes* de virar código, então não tinha sobrado atrito
real pra registrar aqui.

**Discordei de que `PUT /products/{id}` exigisse o objeto inteiro** (`name` e
`price` sempre, mesmo pra mudar só um campo). Pra mim isso deixava a API mais
chata de testar manualmente do que precisava ser pra esse escopo — eu queria
poder mandar só o campo que estava mudando. Pedi pra usar um método que
aceitasse atualização parcial. O agente manteve o `PUT` como estava
(substituição total, semântica REST correta) e adicionou `PATCH
/products/{id}` do lado, que só exige pelo menos um campo (`name` ou `price`)
e mantém o resto do que já existia — os dois convivem agora.

**Também questionei uma escolha mais técnica**: o código original tratava
*qualquer* erro ao selecionar um workspace do Terraform como "workspace não
existe, então cria um novo" — perguntei se isso era realmente a forma certa de
capturar a exceção específica, ou se estava mascarando outros erros reais
(state corrompido, permissão). O agente concordou que sim, era uma
generalização perigosa, e trocou por `terraform workspace select -or-create`
— uma flag nativa do próprio Terraform pra esse exato caso, que elimina o
`try/except` genérico por completo em vez de só deixá-lo mais específico.

Os dois casos: nenhuma das duas mudanças era estritamente necessária pro
escopo do desafio, mas as duas deixaram o código mais correto — vale mais
questionar decisão de implementação já pronta do que só aprovar decisão de
arquitetura antes de existir código.

## 4. O que mudaria em 6 meses

- Testes de integração automatizados contra o LocalStack rodando em CI a cada
  commit, não só validação manual — teria pego o bug do `invoke_mode`
  automaticamente, não numa sessão de teste manual.
- Backend remoto de state (S3 + lock DynamoDB), descartado aqui por escopo
  (ambiente 100% local e de uma pessoa só), mas necessário assim que mais de
  uma pessoa precisasse operar o mesmo ambiente.
- Pipeline de CI validando `terraform fmt -check`, `terraform validate` e
  `pytest` a cada PR — não implementado nesta semana por prioridade de tempo.
- Revisão de segurança mais formal: aqui a segurança foi tratada por decisão
  arquitetural (IAM Role em vez de credencial de banco), mas não houve uma
  etapa dedicada de threat modeling — em 6 meses isso viraria uma revisão
  explícita.
- Subagentes especializados por camada (um revisando só `.tf`, outro só o
  handler da Lambda) em vez de uma única sessão de agente cobrindo o projeto
  inteiro de ponta a ponta.
