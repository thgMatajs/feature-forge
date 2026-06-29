# Plan Auditor — prompt template

Prompt determinístico que `gsd-code-reviewer` recebe ao auditar planos
pós-`superpowers:writing-plans`. Enxugado pro ponteiro — o prompt completo,
os 12 checks (C1/C2, H1-H4, M1-M3, L1-L3), a severity calibration de
detection findings, o override mechanism, a verdict logic, o output format e
o protocolo de re-audit vivem no `mem`.

## Invariante always-on

- O auditor é dispatched OBRIGATORIAMENTE antes do "Execution Handoff" do
  writing-plans. Critical findings não-acknowledged bloqueiam o handoff.
- Detection findings (friendly errors, gate bypass, mandamento enforcement,
  state assertions) recebem severity **mínimo HIGH** — o reviewer não
  improvisa "é cosmético".
- Output em `.planning/plan-reviews/<plan-slug>-review-r<N>.md`. Cap de 3
  rodadas; rodada 4 → verdict `ESCALATE`.

## Detalhe (recupere por tema)

```bash
.claude/bin/mem find "12 checks auditoria de plano"
.claude/bin/mem find "calibrar severity detection findings"
.claude/bin/mem find "os 12 checks C1 C2 H1 H4 M1 M3 L1 L3 trigger detecção"
.claude/bin/mem find "override inline verdict BLOCK PASS_WITH_WARNINGS output PLAN-REVIEW"
.claude/bin/mem find "re-audit rodadas anti-padrões reviewer ESCALATE"
```

Use `.claude/bin/mem get <id>` pra o corpo acionável do prompt e dos checks.
