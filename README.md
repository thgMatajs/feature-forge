# feature-forge

A standalone CLI skill that orchestrates end-to-end planning + implementation of mobile features across Android, iOS, KMP, and Web. Backend-agnostic (Firebase, REST, GraphQL, local-only).

> **State:** v1 entregue (2026-05-29). ~370 arquivos, ~28K LOC. Pronto pra commit inicial + dogfooding.

## What it is

Skill CLI-first com 12 comandos canônicos (zero flags — toda parametrização via menu interativo) que dirige o ciclo completo de feature mobile:

1. **`forge init`** — bootstrap em qualquer projeto KMP/mobile (greenfield ou brownfield)
2. **`forge plan {feature-slug}`** — 5 waves (intake/PRD → screen+contracts → tech-spec → tasks → readiness) com 16 templates
3. **`forge implement {feature-slug}`** — execução task-by-task com gates de scope + atomic commits
4. **`forge verify`** — cascade de 13 validators com 3-caminhos discipline
5. **`forge doctor`** — health check em 11 categorias
6. **`forge reconfigure`** — single entrypoint pra TODA mutação post-init (cards, paths, conventions, etc)
7. Outros: `status`, `evolve`, `undo`, `graph`, `memory`, `raw`

## Identity

| | |
|---|---|
| Name | feature-forge |
| Command alias | `forge` |
| Persona | mentor calmo |
| Vocabulary | "forge" só como verbo; resto neutro |
| Scope OUT | arch macro · decisão de produto · code review final · time tracking |

## Stack alvo

Backend-agnostic — qualquer combinação:

- **Firebase stack**: firebase-auth + firestore-persistence + firestore-realtime + firestore-security-rules + firebase-storage + crashlytics
- **REST stack**: ktor-client + rest-api-contract + kotlinx-serialization-json + room-database + datastore-prefs + auth-jwt-bearer
- **Híbrido**: Firebase Auth + REST API + Room local cache
- **Local-only**: Room + DataStore (offline-first)
- **UI**: Compose (Android) + SwiftUI (iOS) + React (Web via @JsExport)
- **KMP shared**: Kotlin Multiplatform + SKIE bridge
- **Navigation**: Nav3 (Android) + NavigationStack (iOS)
- **DI**: Koin Annotations (KMP/Android) + factory functions (iOS/Web)

## Arquitetura

6 layers (ver `docs/design/00-vision.md` pra detalhe):

1. **Cards** — unidades atômicas de composição (20 cards canônicos v1)
2. **Templates** — esqueletos dos 16 artefatos por feature
3. **Memory** — L1 per-feature (WIP) + L2 project (committed) + L3 read-only (auto-memory)
4. **Graph** — SQLite com 10 queries canônicas (similar features, blast-radius, orphans, etc)
5. **Inventory** — DS components + i18n + conventions extraídos do projeto
6. **Engine Python** — Bash dispatcher + 13 commands + foundation + state + integrations

## Stats

| Categoria | Conteúdo |
|---|---|
| Schemas | 9 schemas + capability-labels catalog |
| Agent prompts | 10 (planning-conductor + 9 sub-agents) |
| UX roteiros | 7 (init, plan, implement, verify, doctor, reconfigure, evolve) |
| Templates canônicos | 16 (intake → PRD → screen → bdd → contracts → tech-spec → tasks → readiness → handoff → evals) |
| Cards canônicos | 20 (8 stack + 6 Firebase + 6 REST) |
| Preset | kmp-mobile (8 stack cards + 4 backend-candidates) |
| Validators Python | 13 (+ 2 helpers) |
| Hooks | 9 (5 Claude Code + 3 git + 1 GitHub Actions) |
| Tests | 266 passing (unit + integration + 13 commands smoke + validators) |
| LOC total | ~28.000 |
| Decisões locked | 27 + 7 direcionais (Fase 3.5) |

## Instalação

```bash
# Clone canonical
git clone <repo> ~/Documents/feature-forge
export FORGE_HOME=~/Documents/feature-forge
export PATH="$FORGE_HOME/bin:$PATH"

# Verifica
forge --version  # → forge 1.0.0

# Init num projeto novo
cd ~/code/my-project
forge init  # → interactive, sem flags
```

Requer Python 3.11+ + PyYAML (única dep externa).

## Where it lives

```
~/Documents/feature-forge/              canonical source (this repo)
  bin/forge                             Bash dispatcher
  engine/                               Python engine (~12.880 LOC)
  docs/                                 design + schemas + UX roteiros
  agents/                               agent prompts (10 prompts)
  templates/                            16 canonical templates
  cards/                                20 canonical cards
  presets/kmp-mobile/                   canonical preset v1
  validators/                           13 validators + helpers
  hooks/                                9 hooks (Claude Code + git + CI)
  tests/                                266 passing tests

[per project install via `forge init`]
{project}/.claude/skills/feature-forge/   snapshot copy
```

## Command surface (12 + 1 hidden)

12 comandos user-facing — zero flags — toda parametrização via prompts interativos (Decision 9 + 10 locked).

```
forge init           bootstrap workflow num projeto (greenfield/brownfield)
forge plan           plan feature (waves A-E)
forge implement      execute task-by-task
forge verify         validator cascade
forge status         read-only board
forge doctor         health check
forge reconfigure    single mutation entrypoint
forge graph          query graph (Q1-Q10)
forge memory         inspect L1/L2/L3
forge evolve         review propostas (single-by-single)
forge undo           reverter última ação
forge raw            escape hatch (verify-card, edit-config, debug)
```

`forge ingest` (hidden) — invocado por hooks, nunca tipado pelo usuário.

## Documentação

Start here:

- **`docs/design/08-session-handoff.md`** — TL;DR completo + estado por fase + limites v1
- `docs/design/00-vision.md` — arquitetura (6 layers, capability cards)
- `docs/design/01-decisions.md` — 27 decisões locked
- `docs/design/06-command-surface.md` — 12 comandos canônicos
- `docs/design/07-discipline.md` — 7 disciplinas universais
- `docs/schemas/capability-labels.md` — catálogo canônico de capabilities
- `docs/ux/forge-init-roteiro.md` — UX cinemática do init
- `agents/planning-conductor.md` — super-agent prompt
- `presets/kmp-mobile/README.md` — preset base v1
- `CHANGELOG.md` — release notes detalhadas

## Conhecidos limites v1

Documentados em `docs/design/08-session-handoff.md § Conhecidos limites v1`:

- **`forge implement` é stub manual** — Apply Mode automatizado é Phase 6
- **`forge init` Cena 7 (Jira/ticketing)** não prompted — use `forge reconfigure` pós-init
- **9 kinds de `apply_proposal_to_l2`** em fall-through (raise NotImplementedError documentado)
- **LLM/sub-agent hookup real** — `plan.py`/`implement.py` narram fluxo + renderizam templates; integração Anthropic API é Phase 6
- **Tree-sitter / AST real** — regex parsers v1 por design

## Origin

Extraído de `MeoBonsai/.agents/skills/feature-implementation-workflow/` em maio 2026 e generalizado pra portabilidade cross-project. Ver `INFLUENCES.md` pra atribuições.

## License

MIT (ver `LICENSE`).
