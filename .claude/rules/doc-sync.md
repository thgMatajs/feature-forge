# Doc-sync — matriz código→docs

Mandamento #6. Ao tocar código vivo, atualize docs no MESMO commit. Enxugado
pro ponteiro — a matriz completa código→docs, o checklist pré-commit, o
como-editar handoff/CHANGELOG e os bloqueios opt-in vivem no `mem`.

## Invariante always-on

Mexeu em `engine/`, `validators/`, `hooks/`, `templates/`, `cards/`,
`presets/`, `docs/schemas/`, `docs/guides/`, `docs/diagrams/` → atualize no
MESMO commit: `CHANGELOG.md` (Unreleased) + `docs/design/08-session-
handoff.md` (Última atualização + Conhecidos limites se aplicável) +
`README.md` (se stats mudaram) + guides/diagrams (se comportamento
documentado mudou). O pre-commit emite SOFT WARNING quando código vivo é
staged sem CHANGELOG/handoff/README.

## Detalhe (recupere por tema)

```bash
.claude/bin/mem find "matriz código docs sincronizar ao tocar engine validators"
.claude/bin/mem find "checklist pré-commit doc-sync CHANGELOG handoff README"
.claude/bin/mem find "bloqueios opt-in pre-commit test-count regression validator cascade"
```

Use `.claude/bin/mem get <id>` pra o corpo acionável.
