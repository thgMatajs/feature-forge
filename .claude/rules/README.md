# `.claude/rules/` — índice

Regras operacionais pra sessões Claude Code mantendo feature-forge. Cada
rule diz **como cumprir** um dos mandamentos de `CLAUDE.md`. Voz: mentor
calmo.

> **Enxugue Fase 0 (mem dogfood, 2026-06-25):** o detalhe das rules migrou
> pro acervo `mem` (recuperável via `.claude/bin/mem find "<tema>"`). Cada
> arquivo aqui virou ponteiro + invariante de enforcement always-on. O
> Tier-0 (Mandamento 0 + 6 mandamentos + fluxo único) vive em `CLAUDE.md` e
> não depende do mem.

## Map (tema → consulta mem)

| Rule | Consulta pra o detalhe |
|---|---|
| orchestrator-persona | `mem find "identidade orquestrador-mantenedor voz operacional"` · `mem find "5 casos legítimos de defer"` |
| subagent-workflow | `mem find "qual subagent_type gsd-executor reviewer fixer"` · `mem find "despacho subagente context-pack"` |
| decisions | `mem find "8 decisões load-bearing"` · `mem find "como revisitar decisão locked sem silent drift"` |
| disciplines | `mem find "exatamente 3 caminhos em todo gate template"` · `mem find "6 disciplinas universais"` |
| testing | `mem find "TDD pytest gates verde antes de pronto"` · `mem find "comandos de teste markers fixtures"` |
| scope | `mem find "edite só o que a tarefa pede whitelist"` · `mem find "anti-padrões scope creep"` |
| reuse | `mem find "reuso forge graph antes de criar helper"` · `mem find "infra compartilhada validators compor"` |
| superpowers | `mem find "10 skills superpowers triggers"` · `mem find "skills não ativadas hierarquia prioridade"` |
| doc-sync | `mem find "matriz código docs sincronizar ao tocar engine"` · `mem find "checklist pré-commit doc-sync"` |
| plan-auditor | `mem find "12 checks auditoria de plano"` · `mem find "override inline verdict BLOCK"` |
| project-anatomy | `mem find "onde cada coisa vive mapa de navegação"` · `mem find "smoke tests rápidos forge --version"` |
| SMOKE-CHECKLIST | `mem find "5 verificações de smoke pós-bootstrap"` |

Use `.claude/bin/mem get <id>` pra o corpo acionável de cada nota.

## Auditoria contínua (manual, ~mensal)

```bash
git log --oneline -30 | head                                          # Mandamento 0 segura?
git log --since='30 days' --pretty=format:'%h %s' -- docs/design/08-session-handoff.md  # doc-sync rola?
git log --all -p -- docs/design/01-decisions.md | grep -c 'Revisita'  # ceremony em locked?
wc -l .claude/state/load-bearing-edits.jsonl 2>/dev/null || echo "(no audit log yet)"
```

Comando futuro `forge audit-rules` está anotado como gap em `docs/design/04-pending.md`.
