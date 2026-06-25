# Subagent Workflow

Como despachar bem. Mandamento 0 diz QUE despacha; este doc apontava COMO.
Enxugado pro ponteiro — o detalhe (qual subagent_type por trabalho, dispatch
paralelo, context-pack obrigatório, anti-padrões, loop review-fix, loop
pós-plano, trust-but-verify, e o handling de exit 2 do forge) vive no `mem`.

## Invariante always-on

- Todo dispatch leva context-pack: TAREFA + ARQUIVOS PERMITIDOS + ARQUIVOS
  PARA LER + CRITÉRIO DE SUCESSO TESTÁVEL + ANTI-PADRÕES + VOZ + COMMIT.
- Dispatch paralelo só quando tarefas são independentes (sem shared state,
  sem ordem, sem editar o mesmo arquivo).
- Subagente que recebe exit 2 do forge reporta o pending; NÃO fecha o loop
  sozinho (responsabilidade do orquestrador/host).

## Detalhe (recupere por tema)

```bash
.claude/bin/mem find "qual subagent_type gsd-executor reviewer fixer debugger"
.claude/bin/mem find "dispatch paralelo tarefas independentes sem shared state"
.claude/bin/mem find "sempre anexe context-pack anti-padrões de dispatch"
.claude/bin/mem find "loop review-fix REVIEW.md plan-auditor trust-but-verify"
.claude/bin/mem find "exit 2 do forge é contrato pending response intent protocol"
```

Use `.claude/bin/mem get <id>` pra o corpo acionável.
