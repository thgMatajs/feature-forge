# Superpowers — 10 skills ativadas

Skills do superpowers que o orchestrator usa. **Não há runtime import** —
skills são recurso humano + Claude Code (Decisão 22). Enxugado pro ponteiro —
a tabela dos 10 triggers precisos, as skills deliberadamente não ativadas, a
hierarquia de prioridade e a extensão local plan-auditor vivem no `mem`.

## Invariante always-on

- Hierarquia de prioridade: **user instructions > superpowers skills >
  default system prompt**. Se CLAUDE.md conflita com superpowers, o projeto
  vence; se o user manda "edita direto", o user vence.
- Decisão 22: skills NUNCA são import runtime. `engine/` não importa nada de
  `superpowers/`/`gsd-*/`. Push-back imediato se alguém sugerir.

## Detalhe (recupere por tema)

```bash
.claude/bin/mem find "10 skills superpowers triggers precisos brainstorming writing-plans"
.claude/bin/mem find "skills não ativadas hierarquia prioridade Decision 22"
```

A extensão local plan-auditor: ver `.claude/rules/plan-auditor.md`.
