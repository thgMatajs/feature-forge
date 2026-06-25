# Testing — disciplina

Mandamento #2: verde antes de "pronto". Enxugado pro ponteiro — os comandos
canônicos, markers, fixtures, counts por lane, a regra TDD (bugfix/feature/
refactor), os validators ativos e seus testes vivem no `mem`.

## Invariante always-on

- `.venv/bin/pytest` é o canonical (tem json5 + deps; o system pytest gera
  falsos negativos).
- Lane rápida: `.venv/bin/pytest -m "not integration and not e2e"`.
- Gates de "pronto": pytest full verde + `forge verify` sem hard fail +
  doc-sync + reviewer assinou off (sem high/critical). Count não pode
  regredir sem justificativa no commit body.
- TDD é mandamento: bugfix começa com regression test FALHANDO; feature
  começa com happy-path FALHANDO; refactor NÃO adiciona teste e roda
  `check_no_behavior_change`.

## Counts (snapshot — re-confirme com o handoff)

Fonte canônica de counts: `docs/design/08-session-handoff.md`. Re-confirme:
`.venv/bin/pytest -m 'not integration and not e2e' -q | tail -1`.

## Detalhe (recupere por tema)

```bash
.claude/bin/mem find "comandos de teste markers fixtures counts por lane .venv pytest"
.claude/bin/mem find "TDD pytest gates verde antes de pronto"
.claude/bin/mem find "validators ativos cyclomatic complexity secrets gate testes"
```

Use `.claude/bin/mem get <id>` pra o corpo acionável.
