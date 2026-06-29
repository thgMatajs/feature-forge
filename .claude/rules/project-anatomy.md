# Project Anatomy — "se procura X, vai em Y"

Mapa orientativo. Enxugado pro ponteiro — o mapa completo (engine, cards,
templates, validators, docs, agents, hooks, tests, bin) e os smoke tests
rápidos vivem no `mem`.

## Invariante always-on (atalho)

- Handler de comando: `engine/<cmd>.py` · Validators: `validators/<name>.py`
  (+ test em `tests/validators/`) · Cards/templates/presets: `cards/`,
  `templates/`, `presets/` · Docs de design: `docs/design/NN-*.md` · Hooks
  do repo: `.claude/hooks/` (diferente de `hooks/` que `forge init` instala
  em consumidores) · Fronteira mem: `engine/integrations/mem.py`.

## Detalhe (recupere por tema)

```bash
.claude/bin/mem find "onde cada coisa vive mapa de navegação do repo engine cards"
.claude/bin/mem find "smoke tests rápidos forge --version pytest validators onde não mexer"
```

Onde NÃO mexer sem revisitar: `.claude/rules/scope.md` + `.claude/rules/decisions.md`.
