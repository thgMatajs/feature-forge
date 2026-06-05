# Superpowers — 10 skills ativadas

Skills do superpowers que o orchestrator usa neste projeto. **Não há
runtime import** — skills são recurso humano + Claude Code (Decision 22).

## Tabela completa

| Skill | Trigger preciso | Bloqueia? |
|---|---|---|
| `superpowers:brainstorming` | qualquer creative work — "vamos planejar/adicionar/criar/refatorar X" | sim — hard gate antes de tocar código |
| `superpowers:writing-plans` | task ≥3 passos OU cruza ≥3 arquivos OU envolve subagent dispatch | sim para implementação não-trivial |
| `superpowers:subagent-driven-development` | toda implementação não-trivial | **sim — mandamento 0** |
| `superpowers:dispatching-parallel-agents` | 2+ tarefas independentes sem shared state | sim quando aplicável |
| `superpowers:test-driven-development` | implementar feature ou bugfix (instrução vai no pacote do subagent) | sim — context-pack pro subagent inclui obrigatoriamente |
| `superpowers:systematic-debugging` | bug, test failure, comportamento inesperado | sim — orchestrator guia raciocínio |
| `superpowers:requesting-code-review` | pós toda implementação não-trivial | **sim — mandamento 0** |
| `superpowers:receiving-code-review` | quando reviewer subagent retorna REVIEW.md | sim |
| `superpowers:executing-plans` | quando há plan escrito a seguir (modo inline alternativo ao subagent-driven) | recomendado |
| `superpowers:verification-before-completion` | antes de claim "pronto/implementado/feito" | sim — hard gate antes de commit final |
| `plan-auditor` (rule local) | pós writing-plans terminal-state, antes do execution-handoff | **sim — critical findings bloqueiam** |

## Skills NÃO ativadas (deliberadamente)

- `superpowers:using-git-worktrees` — projeto não usa worktrees em v1.1.
  Influences.md já documenta como "absorvido patterns only" sem dep. Se
  pattern emergir (multi-feature paralelo), entra via `forge evolve`.
- `superpowers:finishing-a-development-branch` — single-maintainer, branch
  cleanup é simples.
- `superpowers:writing-skills` — projeto inteiro É uma skill; criar
  sub-skills não está no radar.
- `superpowers:using-superpowers` — meta-skill, auto-invocada por session-
  start.

Quando padrão emergir e justificar, entrar via:
1. `forge evolve` propõe addition
2. Brainstorm de revisita
3. Update neste rule + CLAUDE.md superpowers map

## Extensão local: plan-auditor

`plan-auditor` não é skill do superpowers — é rule deste projeto
(`.claude/rules/plan-auditor.md`). Estende o terminal-state do
`superpowers:writing-plans`: antes do "Execution Handoff" do SKILL.md,
o orquestrador OBRIGATORIAMENTE dispatcha `gsd-code-reviewer` com o
prompt do auditor. Critical findings bloqueiam o handoff até fix-dispatch
resolver.

Detalhe completo: `.claude/rules/plan-auditor.md`.

## Hierarquia de prioridade (per superpowers contract)

```
1. User explicit instructions (CLAUDE.md, AGENTS.md, direct requests) ← TOPO
2. Superpowers skills
3. Default system prompt                                                ← BASE
```

Se CLAUDE.md (este projeto) entra em conflito com superpowers, **o
projeto vence**. Se user manda "edita direto" mesmo violando Mandamento 0,
**o user vence**.

## Decision 22 reforço

Skills são padrão de comportamento + ferramenta humana + ferramenta do
Claude Code. NUNCA são import runtime. `engine/` não importa nada de
`superpowers/`, `gsd-*/`, ou qualquer outra skill. Esta é decisão
load-bearing — quebra portability.

Se algum subagent sugerir "vamos usar superpowers como lib" → push-back
imediato, viola Decision 22.
