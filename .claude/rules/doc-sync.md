# Doc-sync — matriz código→docs

Mandamento #6. Ao tocar código vivo, atualize docs no MESMO commit. Enxugado
pro ponteiro — a matriz completa código→docs, o checklist pré-commit, o
como-editar handoff/CHANGELOG e os bloqueios opt-in vivem no `mem`.

## Invariante always-on

Mexeu em `engine/`, `validators/`, `hooks/`, `templates/`, `cards/`,
`presets/`, `docs/schemas/`, `docs/guides/`, `docs/diagrams/` → atualize no
MESMO commit: `CHANGELOG.md` (Unreleased) + `README.md` (se stats mudaram)
+ guides/diagrams (se comportamento documentado mudou). O pre-commit emite
SOFT WARNING quando código vivo é staged sem CHANGELOG/README.

- **Sincronia mem↔backlog:** fechar um item em `docs/design/04-pending.md` →
  arquivar/supersede a nota `reference` correspondente do mem NO MESMO commit
  (o mem surfa só os temas ABERTOS ATIVOS; o doc enumera tudo). Mandamento #7.

O **estado de sessão** saiu do gate per-commit: rode `.claude/bin/mem
session` no fim de sessão (handoff curado, committed). O
`docs/design/08-session-handoff.md` congelou — snapshot histórico +
fallback de bootstrap do SessionStart, não mais editado a cada sessão.

## Detalhe (recupere por tema)

```bash
.claude/bin/mem find "matriz código docs sincronizar ao tocar engine validators"
.claude/bin/mem find "checklist pré-commit doc-sync CHANGELOG handoff README"
.claude/bin/mem find "bloqueios opt-in pre-commit test-count regression validator cascade"
```

Use `.claude/bin/mem get <id>` pra o corpo acionável.
