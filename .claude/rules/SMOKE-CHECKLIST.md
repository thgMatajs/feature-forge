# Smoke Checklist (one-time, post-bootstrap)

5 verificações manuais pra confirmar que o rules system está vivo. Execute
**uma vez** após `bash .claude/bootstrap.sh`. Enxugado pro ponteiro — os
passos detalhados de cada check e o registro da última execução vivem no
`mem`.

## Os 5 checks (títulos always-on)

1. **SessionStart hook** injeta orientação no início da sessão.
2. **PostToolUse drift hook** dispara ao editar arquivo "vivo" (`engine/*`).
3. **PreToolUse load-bearing hook** dispara ao editar doc load-bearing +
   grava em `.claude/state/load-bearing-edits.jsonl`.
4. **Pre-commit hard-block** bloqueia `01-decisions.md` staged sem "Revisita
   decisão" no CHANGELOG; passa com a cerimônia.
5. **Mandamento 0** — o orquestrador dispatcha em vez de editar direto.

## Detalhe + última execução (recupere por tema)

```bash
.claude/bin/mem find "5 verificações de smoke pós-bootstrap hooks"
.claude/bin/mem find "última execução smoke 4/5 side-effect persistente vs stderr subagente"
```

Lição operacional registrada: pra hooks em subagent context, **side-effect
persistente em `.claude/state/*` é canal de audit mais confiável que stderr
capture**.
