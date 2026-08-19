---
description: Registra uma nova decisão de arquitetura como ADR em docs/decisions/, no formato usado neste projeto.
argument-hint: <descrição curta da decisão a registrar>
---

Registre uma nova decisão de arquitetura como ADR em `docs/decisions/`, sobre:
$ARGUMENTS

Antes de escrever, releia `docs/decisions/ADR-001-stack-e-arquitetura.md` para
seguir exatamente o mesmo formato e nível de detalhe (não invente uma estrutura
nova). Cada ADR usa este esqueleto por decisão:

```
## Decisão N — <título curto>

**Alternativas descartadas**: <opção> — <por que foi descartada, em uma frase>.
(repetir para cada alternativa considerada)

**Decisão**: <o que foi escolhido>.

**Trade-off assumido**: <o que se abre mão em troca, honestamente — não só o
lado positivo>.
```

Passos:

1. Olhe o histórico recente de commits e a conversa atual para entender qual
   decisão real está sendo registrada — não invente contexto, use o que
   realmente foi discutido/decidido.
2. Se já existe um ADR aberto (`docs/decisions/ADR-001-*.md` ou similar) que
   ainda faz sentido estender com mais uma decisão relacionada, adicione uma
   seção nele em vez de criar um arquivo novo — é assim que ADR-001 já
   consolida quatro decisões relacionadas de stack. Só crie
   `ADR-00N-<slug>.md` novo se for uma decisão de um tema claramente
   diferente.
3. Preencha **Alternativas descartadas** e **Trade-off assumido** de verdade —
   se alguma dessas informações não estiver clara na conversa, pergunte antes
   de inventar.
4. Não commite automaticamente — deixe o arquivo pronto para revisão e diga
   qual arquivo foi criado/editado. Quem decide quando commitar é o operador
   deste projeto, conforme CLAUDE.md.
