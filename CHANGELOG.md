# Changelog

Todas as mudanças notáveis no feature-forge.

Formato baseado em [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versionamento: [SemVer](https://semver.org/lang/pt-BR/spec/v2.0.0.html).

## [1.0.0] — 2026-05-29

### Adicionado

#### Fase 1 — Schemas + filesystem (espinha dorsal)

- 9 schemas canônicos (`docs/schemas/{workflow-config, card, memory, graph, inventories, proposed-evolutions, rejected-evolutions, workflow-config-history, capability-labels}.md`)
- 27 decisões locked em `docs/design/01-decisions.md`
- 7 disciplinas universais em `docs/design/07-discipline.md`
- Filesystem layout canônico em `docs/design/05-filesystem-layout.md`

#### Fase 2 — Agents + UX roteiros (cérebros)

- 10 agent prompts: planning-conductor + 9 sub-agents (feature-intake, feature-prd, screen-analysis, contract-planner, tech-spec, task-contract-writer, readiness-reviewer, retrospective, memory-distiller)
- 7 roteiros UX cinemáticos (init, plan, implement, verify, doctor, reconfigure, evolve)
- ~7.000 LOC de markdown

#### Fase 3 — Templates + cards + preset (conteúdo)

- 16 templates canônicos (feature-intake, feature-prd, screen-analysis, bdd, ui-state-spec, navigation-spec, data-contract-spec, analytics-spec, test-strategy, tech-spec, task-breakdown, task-contract, implementation-readiness-review, plan-feature-handoff, evals)
- 12 cards canônicos iniciais (kotlin-language, kmp-shared, compose-screens, swiftui-screens, koin-annotations, skie-bridge, nav3, swiftui-navigation, firebase-auth, firebase-firestore (monolítico), firebase-storage, crashlytics)
- Preset `kmp-mobile-firebase` (depois substituído pelo `kmp-mobile` na 3.5)

#### Fase 3.5 — Refactor backend-agnostic + REST coverage

- Catálogo canônico de capability labels (40 labels v1: 16 singular + 3 latente + 14 auxiliar + 5 reservada)
- `firebase-firestore` monolítico ARQUIVADO; split em `firestore-persistence` + `firestore-realtime` + `firestore-security-rules`
- 6 cards REST novos: `ktor-client`, `rest-api-contract`, `kotlinx-serialization-json`, `room-database`, `datastore-prefs`, `auth-jwt-bearer`
- Preset `kmp-mobile-firebase` ARQUIVADO; substituído por `kmp-mobile` base + 4 backend-candidates (firebase-stack / rest-stack / hybrid / local-only)
- 3 templates refatorados pra agnóstico (`data-contract-spec`, `tech-spec`, `test-strategy`)
- 29 FOLLOWUPs herdados fechados em rodada paralela de 4 sub-agents

#### Fase 4 — Python engine + Bash dispatcher (músculos)

- `bin/forge` Bash dispatcher
- Foundation: `engine/cli.py` + `engine/utils/` + `engine/ui/` + `engine/persona/`
- State: `engine/cards/` + `engine/memory/` + `engine/graph/` + `engine/inventory/`
- Integration: `engine/mcp/` + `engine/vision/`
- 13 commands handlers: init, plan, implement, verify, status, doctor, reconfigure, evolve, undo, graph_cli, memory_cli, raw, ingest
- 57 arquivos Python · ~12.880 LOC

#### Fase 5 — Hooks + validators + tests (pele e validação)

- 9 hooks (5 Claude Code + 3 git wrappers + 1 GitHub Actions workflow)
- 13 validators Python (+2 helpers) com 3-caminhos discipline + JSON tail-on-stdout contract
- Suite pytest: 266 tests (unit + integration + 13 commands smoke + validators)
- Hooks instalação automática no `forge init`

### Mudado

- **Cleanup pós-review crítico** (47 fixes em 6 sub-agents paralelos):
  - Schema drift triplo (memory.l2 key alignment + backend block real + MEM-L1-VL warn)
  - Decision 27 (Ctrl+C pause) honrada de verdade em init.py
  - Phase lock auto-release em plan + implement
  - `apply_proposal_to_l2` raise NotImplementedError nos fall-through (não mais silent drop)
  - `_handle_pre_commit` deriva slug da branch/L1 (gates voltam a bloquear)
  - CI workflow instala forge de verdade
  - Performance: `blast_radius` 250 queries → 1 (~50× speedup), `_persist_*` executemany (3-5×), walk cache compartilhado
  - JUnit5 false positive fix
  - Path traversal block em `normalize_screenshot_path`
  - BOM UTF-8 tolerância em card.yaml
  - Setext + ATX heading mix em merger
  - 13 smoke tests novos pros commands handlers

### Removido

- Preset `kmp-mobile-firebase` (movido pra `presets/.archived/kmp-mobile-firebase-pre-3.5/`)
- Card `firebase-firestore` monolítico (movido pra `cards/.archived/firebase-firestore-monolithic/`)
- Capability labels `realtime-data`, `auth-server` (renomeadas/splitadas)

### Conhecidos limites v1

Ver `docs/design/08-session-handoff.md § Conhecidos limites v1`:

- `forge implement` é stub manual (Apply Mode automatizado em Phase 6)
- `forge init` Cena 7 (Jira/ticketing) não prompted
- 9 kinds de `apply_proposal_to_l2` raise NotImplementedError
- LLM hookup real é Phase 6
- Tree-sitter / AST: regex parsers v1 por design

[1.0.0]: https://github.com/thgMatajs/feature-forge/releases/tag/v1.0.0
