# Scope discipline

Mandamento #4: edite só o que a tarefa pede. Em dúvida, **pergunte ao
usuário** (não decida). Enxugado pro ponteiro — os anti-padrões de scope
creep ("vou aproveitar", refactor não-solicitado, rename "while I'm here")
e a detecção mecânica vivem no `mem`.

## Invariante always-on

- Subagente recebe lista explícita de "ARQUIVOS PERMITIDOS PARA EDIT" no
  context-pack. Sair da lista = violação de scope → revert + re-dispatch.
- Exceção legítima: doc-sync na mesma mudança (Mandamento #6).

## Whitelist load-bearing (avisada pelo hook PreToolUse)

A whitelist autoritativa vive no hook
`.claude/hooks/pre-tool-use-load-bearing.sh` (função `is_load_bearing`).
Cópia pra referência: `docs/design/00-vision.md`, `01-decisions.md`,
`05-filesystem-layout.md`, `06-command-surface.md`, `07-discipline.md`,
`docs/schemas/**`, `presets/**`, `cards/**`, `CLAUDE.md`, `.claude/rules/**`.
O hook avisa (audit em `.claude/state/load-bearing-edits.jsonl`), não bloqueia.

## Detalhe (recupere por tema)

```bash
.claude/bin/mem find "edite só o que a tarefa pede arquivos load-bearing whitelist"
.claude/bin/mem find "anti-padrões scope creep aproveitar refactor rename"
```
