# `.claude/rules/` — index

Operational rules for Claude Code sessions maintaining feature-forge. Each
rule says **how to comply** with one of the mandamentos in `CLAUDE.md`.

Voz: mentor calmo. Não duplica `docs/design/*` — adiciona camada operacional.

## Map

| Rule | One-liner | Quando ler |
|---|---|---|
| [orchestrator-persona.md](orchestrator-persona.md) | Identidade do mantenedor, whitelist de ferramentas, workflow loops | sempre, no início de cada sessão |
| [subagent-workflow.md](subagent-workflow.md) | Qual subagent_type pra quê, context-pack, trust-but-verify | antes de qualquer Agent dispatch |
| [decisions.md](decisions.md) | 8 decisões load-bearing + protocolo "Revisita decisão N" | antes de editar `docs/design/01-decisions.md` |
| [disciplines.md](disciplines.md) | 6 disciplinas universais + template 3-caminhos | em qualquer gate ou violação |
| [testing.md](testing.md) | pytest, markers, validators, gates | antes de "pronto" |
| [scope.md](scope.md) | Arquivos load-bearing, anti-padrões de scope creep | antes de edits que cruzam módulos |
| [reuse.md](reuse.md) | `forge graph` antes de criar helper novo | antes de Write em código novo |
| [superpowers.md](superpowers.md) | 10 skills com triggers e bloqueios | quando dúvida de skill ativar |
| [doc-sync.md](doc-sync.md) | Matriz código→docs, checklist pré-commit | em todo commit que toca código "vivo" |
| [plan-auditor.md](plan-auditor.md) | Prompt + 12 checks pra auditoria pós writing-plans | antes/depois de dispatch do auditor |
| [project-anatomy.md](project-anatomy.md) | Mapa "se procura X, vai em Y" + smoke tests | navegação inicial |
| [SMOKE-CHECKLIST.md](SMOKE-CHECKLIST.md) | 5 verificações manuais pós-bootstrap | one-time após instalar |

## Auditoria contínua (manual, ~mensal)

Comandos pra você (humano) revisar como o sistema está segurando:

```bash
# Mandamento 0 segura?
git log --oneline -30 | head

# Doc-sync rola?
git log --since='30 days' --pretty=format:'%h %s' -- docs/design/08-session-handoff.md

# Locked decisions caem em ceremony?
git log --all -p -- docs/design/01-decisions.md | grep -c 'Revisita'

# Audit log de load-bearing edits
wc -l .claude/state/load-bearing-edits.jsonl 2>/dev/null || echo "(no audit log yet)"
```

Comando futuro `forge audit-rules` está anotado como gap em `docs/design/04-pending.md`.
