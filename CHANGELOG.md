# Changelog

Todas as mudanças notáveis no feature-forge.

Formato baseado em [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versionamento: [SemVer](https://semver.org/lang/pt-BR/spec/v2.0.0.html).

## [Unreleased]

### Added (Claude Code rules system)

- `CLAUDE.md` root + `.claude/rules/*.md` (12 operational rules) — Mandamento 0 (orchestrator-mantenedor com delegação total via Agent tool) + 6 mandamentos (decisões locked, verde antes de pronto, reuso, escopo, voz mentor calmo, doc-sync) + workflow por verbo + map dos 10 superpowers skills ativos.
- `.claude/hooks/*.sh` (4 hooks): `session-start-orientation.sh` (injeta Mandamento 0 + estado), `pre-tool-use-load-bearing.sh` (warn + audit em load-bearing edits), `post-edit-doc-drift.sh` (lembrete doc-sync once-per-file-per-session), `pre-commit-feature-forge.sh` (HARD BLOCK em `01-decisions.md` sem ceremony "Revisita decisão" + SOFT WARN em código vivo sem doc-sync).
- `.claude/settings.json` registrando os 3 hooks Claude Code (SessionStart, PreToolUse, PostToolUse).
- `.claude/bootstrap.sh` (idempotent one-time setup — symlinks `.git/hooks/`).
- `tests/integration/test_claude_rules_system.py` — 36 testes (marker `integration`).
- `docs/superpowers/specs/2026-06-01-claude-md-design.md` (brainstorm) + `docs/superpowers/plans/2026-06-01-claude-md-rules-system.md` (plan executável).

### Changed

- polish(claude-rules): corrige smoke checklist execution — hooks PreToolUse/PostToolUse confirmados em subagent context via doc oficial + side-effect persistente; veredito anterior estava furado por capturar só stderr. Veredito final: 4/5 (Check #3 corrigido pra PASS via audit log; Check #2 permanece FAIL por entrega inconsistente do PostToolUse). Gap de observabilidade anotado em `docs/design/04-pending.md`.

## [1.1.0] — 2026-06-01

### Adicionado

#### Stress-test 2026-05-29 — 4 Gaps shipped

- **Gap 1 — Bugfix subtype** (hotfix urgency fast-path): `subtype="bugfix"` no
  `_VALID_SUBTYPES`, keyword + ticket-pattern detection (`IN-/PD-/BUG-`),
  Wave B conditional sub-question (`A·C·D·E` logic-only OR `A·B·C·D·E`
  UI-observable), template `feature-intake-bugfix.template.md`.
- **Gap 2 — Non-product feature track** (refactor only; spike + chore stubbed):
  `subtype=refactor|spike|chore`, filesystem layout `non-product/{slug}/`,
  template `feature-intake-refactor.template.md`, validator
  `check_no_behavior_change` gateando Wave E.
- **Gap 8 — `blocked-on-external` state** (orthogonal to subtype): state
  enum value, manual unblock via `forge reconfigure → external-deps`,
  preservado em retomadas.
- **Gap 18 — Reuse intelligence** (expansão completa): detecção init-time +
  incremental + 6 categorias (within-module, cross-module, redundant-platform,
  near-duplicate, kmp-migration, ts-helper) + integração com `forge plan`
  refactor subtype.

#### Reuse intelligence (Gap 18 expandido)

- **6 detection categories** em `engine/graph/duplicates.py`:
  - `duplicate-within-module` (Kotlin extension repetida em 1 módulo, conf 0.95)
  - `duplicate-cross-module` (sibling modules → smallest-common-ancestor via
    Gradle dependency closure, conf 0.85)
  - `redundant-platform-specific` (Android Kotlin idêntico a shared commonMain, conf 0.90)
  - `near-duplicate` (mesma assinatura, body_hash diferente — drift signal, conf 0.40)
  - `kmp-migration-candidate` (Swift ↔ Kotlin shared com Jaccard ≥0.4, conf 0.50–0.75)
  - `duplicate-ts-helper` (TypeScript top-level duplicado, conf 0.95)
- **Schema v2 — colunas + tabelas**:
  - `files.source_set` (commonMain / androidMain / iosMain / …)
  - `symbols.{receiver_type, body_hash, body_tokens, modifiers}`
  - `module_deps` (Gradle dependency graph parsed de cada `build.gradle(.kts)`)
  - `reuse_findings` + `reuse_finding_locations` (materialized detection output)
- **Parser overhaul** (Kotlin / Swift / TypeScript):
  - visibility agora persistida (era hardcoded "public")
  - signature normalizada (param names dropped, generics simplified)
  - body extraction brace-aware em `engine/graph/_body_text.py`
  - body_hash (SHA-1[:16]) + body_tokens (JSON) para Jaccard cross-language
  - Swift two-pass captura receiver de `extension Type { func ... }`
- **Module inference** (settings.gradle + build.gradle parsing):
  - `engine/graph/gradle_modules.py`: longest-prefix match para multi-módulo
    (KMP `:shared:feature:auth` ou Android `:androidApp:feature:bonsai`)
  - `engine/graph/gradle_deps.py`: transitive closure + smallest-common-ancestor
- **Apply flow** (`engine/graph/reuse_apply.py`):
  - 6 novos kinds em `_VALID_KINDS` do distiller
  - `apply_proposal_to_l2` dispatcha para `apply_reuse_intelligence_proposal`
  - Renderiza `templates/feature-intake-refactor.template.md` com payload
  - Escreve L1 `status.json` com `subtype="refactor"` → `forge plan {slug}`
    detecta automaticamente e pula Wave A discovery (Gap 2 integration)
- **Engine wiring**:
  - `engine/init.py` Step 11.5: `queue_proposals_from_table` após graph build
  - `engine/init.py` Step 11.6: escreve `.claude/hooks/post-edit-detect-duplications.sh`
  - `engine/reconfigure.py`: re-queue após rebuild
  - `engine/doctor.py`: `_check_reuse_findings` agregado por categoria
  - `engine/graph_cli.py`: opções 12–17 + `r` (combined) + `forge graph detect-incremental <file>` non-interactive
  - `engine/graph/incremental.py`: `detect_after_update` para hook entrypoint
- **Q11 backward-compat**: filtro `f.module = 'shared'` → `LIKE 'shared:%'`
  para multi-módulo shared.
- **Tests**: 20 unit tests em `tests/unit/test_reuse_intelligence.py`,
  cobrindo body extraction, gradle parsing, parser fields, detection completo,
  apply + status.json. **367 tests passam, 0 regressões**.
- **Schema docs**: `docs/schemas/graph.md` + `docs/schemas/proposed-evolutions.md`
  ganham seção "Reuse Intelligence (schema v2)".

### Mudado

- `_VALID_KINDS` do `engine/memory/distiller.py` ganha 6 entries reuse-related.
- `engine/graph/queries.py` Q11 (`find_reusable_helpers`) suporta multi-módulo
  shared via `LIKE 'shared:%'`.

### Conhecidos limites v1.1

- `kmp-migration-candidate` confidence é shallow (token Jaccard, não AST).
  False positives possíveis — apply NUNCA auto-runs; usuário revisa.
- Hook script `.claude/hooks/post-edit-detect-duplications.sh` é escrito
  no init, mas wiring em `.claude/settings.local.json` é manual (opt-in).
- Gradle dependency parsing cobre `implementation(project(...))` e
  variantes comuns. DSL Kotlin avançado ou `includeBuild` pode falhar.

[1.1.0]: https://github.com/thgMatajs/feature-forge/releases/tag/v1.1.0

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
