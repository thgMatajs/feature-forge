# Project Anatomy — "se procura X, vai em Y"

Mapa orientativo. Em dúvida sobre onde algo vive, comece aqui.

## Engine (~21.9K LOC Python)

| Procura | Vai em |
|---|---|
| Handler de comando (`forge <cmd>`) | `engine/<cmd>.py` (13 handlers em v1.1) |
| Foundation: dispatcher, CLI parser, UI helpers, persona | `engine/{cli,utils,ui,persona}.py` |
| State: cards, memory, graph, inventory | `engine/{cards,memory,graph,inventory}/` |
| Integrations: MCP, vision | `engine/{mcp,vision}/` |
| Schema migrations (graph SQLite) | `engine/graph/migrations/` |
| Reuse intelligence pipeline | `engine/graph/reuse/` (parsers + detection + apply) |

## Layer 1 — Capability cards

| Procura | Vai em |
|---|---|
| Card canônico (20 em v1.1) | `cards/<name>.yaml` |
| Card schema | `docs/schemas/card.md` |
| Preset | `presets/kmp-mobile.yaml` (+ outros) |

## Layer 2 — Templates (18 em v1.1)

| Procura | Vai em |
|---|---|
| Feature artifacts | `templates/feature-*.template.md` |
| Spec artifacts (YAML) | `templates/*-spec.template.yaml` |
| Subtype-specific intake | `templates/feature-intake-{bugfix,refactor}.template.md` |

## Validators (14 + 2 helpers em v1.1)

| Procura | Vai em |
|---|---|
| Validator canônico | `validators/<name>.py` |
| Helpers compartilhados | `validators/_common.py` |
| Validator tests | `tests/validators/test_<name>.py` |

## Docs

| Procura | Vai em |
|---|---|
| Visão geral | `docs/design/00-vision.md` |
| Decisões | `docs/design/01-decisions.md` |
| Phases roadmap | `docs/design/02-phases.md` + `docs/design/ROADMAP.md` |
| Influences (skills absorbidas) | `INFLUENCES.md` + `docs/design/03-influences.md` |
| Pending gaps | `docs/design/04-pending.md` |
| Filesystem layout | `docs/design/05-filesystem-layout.md` |
| Command surface | `docs/design/06-command-surface.md` |
| Disciplinas universais | `docs/design/07-discipline.md` |
| Estado/handoff | `docs/design/08-session-handoff.md` |
| Schemas YAML/JSON | `docs/schemas/*.md` |
| UX roteiros (forge plan/implement/verify/etc.) | `docs/ux/*.md` |
| Lifecycle (memory + graph) | `docs/lifecycle/memory-and-graph.md` |

## Agents (prompts pra sub-agents)

| Procura | Vai em |
|---|---|
| Planning conductor + 9 sub-agents | `agents/*.md` |

## Hooks — dois diretórios distintos

| Procura | Vai em |
|---|---|
| Git hooks + Claude Code hooks instalados em PROJETOS CONSUMIDORES via `forge init` | `hooks/` (raiz) |
| Claude Code hooks deste repo (manutenção interna) | `.claude/hooks/` |

## Tests

| Procura | Vai em |
|---|---|
| Unit tests | `tests/<module>/test_*.py` |
| Integration (marker `integration`) | `tests/integration/test_*.py` |
| E2E (marker `e2e`) | `tests/e2e/test_*.py` |
| Fixtures comuns | `tests/conftest.py` |
| Test data | `tests/fixtures/` |

## Bin

| Procura | Vai em |
|---|---|
| Dispatcher Bash canônico | `bin/forge` |

## Smoke tests rápidos

```bash
./bin/forge --version              # CLI vivo
pytest -k smoke                    # smoke suite
pytest tests/validators/ -x        # validators OK
python -m engine.cli --help        # CLI entry alternativa (pyproject scripts)
```

## Onde NÃO mexer sem revisitar

Lista em [scope.md](scope.md). Decisões load-bearing em
[decisions.md](decisions.md).
