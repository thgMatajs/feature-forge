# Pending design artifacts

What still needs to be drafted, in dependency order. Use this as the
checklist for next sessions.

## Phase 1 — Espinha dorsal (schemas + estrutura)

- [x] workflow-config.yaml schema → `docs/schemas/workflow-config.md`
- [x] Card schema → `docs/schemas/card.md`
- [x] Inventory schemas → `docs/schemas/inventories.md`
- [x] Memory schemas → `docs/schemas/memory.md`
- [x] Graph DB schema → `docs/schemas/graph.md`
- [x] Esqueleto de pastas + arquivos vazios → `docs/design/05-filesystem-layout.md`

### Auxiliary schemas (added during gap-fix)

- [x] proposed-evolutions.yaml schema → `docs/schemas/proposed-evolutions.md`
- [x] rejected-evolutions.yaml schema → `docs/schemas/rejected-evolutions.md`
- [x] workflow-config-history.jsonl schema → `docs/schemas/workflow-config-history.md`

**🎉 Fase 1 — 100% concluída**

## Phase 2 — Cérebros (agents)

- [x] forge init roteiro → `docs/ux/forge-init-roteiro.md`
- [x] planning-conductor prompt → `agents/planning-conductor.md`
- [x] forge plan roteiro end-to-end → `docs/ux/forge-plan-roteiro.md`
- [x] forge implement roteiro end-to-end → `docs/ux/forge-implement-roteiro.md`
- [x] forge verify roteiro → `docs/ux/forge-verify-roteiro.md`
- [x] forge doctor roteiro → `docs/ux/forge-doctor-roteiro.md`
- [x] forge reconfigure roteiro → `docs/ux/forge-reconfigure-roteiro.md`
- [x] forge evolve roteiro → `docs/ux/forge-evolve-roteiro.md`
- [x] Universal disciplines doc → `docs/design/07-discipline.md`
  - TODO v2 polish: cross-link cada §X.Referenced-from no documento alvo (roteiro/schema) para fechar o loop bidirecional.
- [x] Sub-agent prompts (Phase 2 complete):
  - [x] feature-intake-agent → `agents/feature-intake-agent.md` (334 lines)
  - [x] feature-prd-agent → `agents/feature-prd-agent.md` (296 lines)
  - [x] screen-analysis-agent → `agents/screen-analysis-agent.md` (431 lines)
  - [x] contract-planner-agent → `agents/contract-planner-agent.md` (620 lines)
  - [x] tech-spec-agent → `agents/tech-spec-agent.md` (456 lines)
  - [x] task-contract-writer → `agents/task-contract-writer.md` (450 lines)
  - [x] readiness-reviewer → `agents/readiness-reviewer.md` (318 lines)
  - [x] retrospective-agent → `agents/retrospective-agent.md` (490 lines)
  - [x] memory-distiller → `agents/memory-distiller.md` (331 lines)

**🎉 Fase 2 — 100% concluída** (7 roteiros UX + 10 agent prompts, ~7.000 linhas)

## Phase 3 — Conteúdo (templates + cards)

- [x] Templates × 16 → `templates/`
  - [x] feature-intake.template.md
  - [x] feature-prd.template.md
  - [x] screen-analysis.template.md
  - [x] bdd.template.md
  - [x] bdd.template.json
  - [x] ui-state-spec.template.yaml
  - [x] navigation-spec.template.yaml
  - [x] data-contract-spec.template.yaml
  - [x] analytics-spec.template.yaml
  - [x] test-strategy.template.yaml
  - [x] tech-spec.template.md
  - [x] task-breakdown.template.yaml
  - [x] task-contract.template.yaml
  - [x] implementation-readiness-review.template.md
  - [x] plan-feature-handoff.template.json
  - [x] evals.template.json
- [x] Cards canônicos × 12 → `cards/{name}/` (canonical home — siblings of presets/)
  - [x] kotlin-language
  - [x] kmp-shared
  - [x] compose-screens
  - [x] swiftui-screens
  - [x] koin-annotations
  - [x] skie-bridge
  - [x] nav3
  - [x] swiftui-navigation
  - [x] firebase-auth                       (capabilities atualizadas em Fase 3.5)
  - [x] firebase-firestore                  ARQUIVADO em Fase 3.5 → split em 3 cards
  - [x] firebase-storage                    (capabilities OK)
  - [x] crashlytics                         (capabilities OK)
- [x] Preset manifest → `presets/kmp-mobile-firebase/preset.yaml`  ARQUIVADO em Fase 3.5

## Phase 3.5 — Refactor backend-agnostic + REST coverage (entregue 2026-05-29)

Motivação: Fase 3 inicial calcificou Firebase como o backend canônico. Projetos reais usam REST com Retrofit/Ktor mais frequentemente — refactor pra v1 sair sem viés Firebase-first.

- [x] **Catálogo canônico de capability labels** → `docs/schemas/capability-labels.md` (35 labels v1, 9 famílias, 4 tipos: Singular / Latente / Auxiliar / Reservada)
- [x] **Arquivado** `cards/firebase-firestore/` → `cards/.archived/firebase-firestore-monolithic/`
- [x] **3 cards Firestore splittados:**
  - [x] `firestore-persistence` — provê `persistence-server`, `api-contract-firebase-sdk`
  - [x] `firestore-realtime` — provê `realtime-stream`, requires `persistence-server`
  - [x] `firestore-security-rules` — provê `firestore-rules-guarded`, requires `persistence-server`
- [x] **Patches em cards Firebase existentes:**
  - [x] `firebase-auth/card.yaml` — provides: `auth-provider`, `auth-token-bearer`, `auth-firebase-managed` (split do antigo `auth-server`)
  - [x] `firebase-storage/card.yaml` — confirmado: `file-storage`, `firebase-storage`
  - [x] `crashlytics/card.yaml` — confirmado: `crash-reporting`, `crashlytics`
- [x] **6 cards REST novos:**
  - [x] `kotlinx-serialization-json` — provê `serialization-json` (piloto)
  - [x] `ktor-client` — provê `http-client`
  - [x] `rest-api-contract` — provê `api-contract-rest`
  - [x] `room-database` — provê `persistence-local` (Room 2.7+ KMP-stable)
  - [x] `datastore-prefs` — provê `local-prefs-storage`
  - [x] `auth-jwt-bearer` — provê `auth-provider`, `auth-token-bearer` (alternativa REST a firebase-auth)
- [x] **Templates refatorados (3) pra agnóstico:**
  - [x] `data-contract-spec.template.yaml` — top-level `persistence_strategy` + sub-blocos `firestore_collections` / `rest_endpoints` / `local_tables` / `local_prefs` / `realtime_streams` populados via card merge-keys
  - [x] `tech-spec.template.md` — §7 Data layer split em §7.1-§7.7 por capability (server persistence / network http / REST contract / local persistence / realtime / security rules / auth)
  - [x] `test-strategy.template.yaml` — `backend_e2e.provider` agnóstico (`firestore-emulator | mock-server-rest | contract-tests | none`)
- [x] **Agent prompts patchados:**
  - [x] `contract-planner-agent.md` — extension-points formalizados no frontmatter; Data Contract com 2 variantes (Firestore + REST); Auth Contract com 2 variantes mutuamente exclusivas (firebase-auth XOR auth-jwt-bearer)
  - [x] `tech-spec-agent.md` — extension-points novos (`section:Network layer`, `section:Local Persistence`, `section:Auth layer`); Examples com stack Firestore E stack REST
  - [x] `task-contract-writer.md` — referências a `firebase-firestore` (deletado) atualizadas para `firestore-persistence`
- [x] **Preset refactor:**
  - [x] `presets/kmp-mobile-firebase/` arquivado em `presets/.archived/kmp-mobile-firebase-pre-3.5/`
  - [x] `presets/kmp-mobile/preset.yaml` + README criado — só 8 cards de stack; backend via `backend-candidates` (firebase-stack / rest-stack / hybrid / local-only)
- [x] **Patch `docs/design/05-filesystem-layout.md`** — lista de cards (20 ativos + 1 arquivado) e presets (kmp-mobile base + kmp-mobile-firebase arquivado) atualizadas em Step 4 da Fase 3.5
- [x] **PENDENTE** — Patch `docs/schemas/card.md` exemplo Firestore (agora 3 cards splittados em vez de monolítico)  — Cleanup 3.5: Example C reescrito para `firestore-persistence` (manifest completo com `provides: [persistence-server, api-contract-firebase-sdk]`, `conflicts-with: [persistence-server]`, signals sem firestore.rules); Example A corrigido (extension-point `section:Language Conventions` inexistente → `section:Shared (KMP) layer`); cross-ref para `docs/schemas/capability-labels.md` adicionada no topo do schema-version block.
- [x] **PENDENTE** — Patch `docs/ux/forge-init-roteiro.md` (backend selection UX com backend-candidates)  — Cleanup 3.5: Cena 6.5 inserida entre Cena 6 e Cena 7, apresentando os 4 backend-candidates (`firebase-stack`, `rest-stack`, `hybrid-firebase-auth-rest-data`, `local-only`) com signals casados, escolha + opção "personalizar cards manualmente". Cena 6 atualizada para anunciar a 6.5 e remover `firebase-*` do núcleo do preset.

### Fase 3.5 — FOLLOWUPs (não-bloqueantes p/ Fase 4)

- [x] **Normalizar snake_case nos fragments dos cards** — templates dos cards (`firestore-collections.yaml`, `rest-endpoints-data-contract.yaml`, etc) usavam kebab-case nas chaves top-level. Cleanup 3.5: 9 fragments normalizados para snake_case (`firestore_collections:`, `rest_endpoints:`, `room_tables:`, `storage_paths:`, `firestore_rules_tests:`, `crash_reporting:`, `firebase_auth_events:`, `allowed_files_koin_modules:`, `compose_file_patterns:`, `swiftui_file_patterns:` + sub-keys). Card names em comentários (`firestore-realtime`, `firestore-security-rules`) e capability labels (`auth-token-bearer`, `persistence-server`) permanecem kebab por convenção.
- [x] **Labels reservadas v1.1+** — sem provider v1, **por design**: `analytics-pipeline`, `graphql-client`, `websocket-realtime`, `sse-realtime`, `auth-oauth2-rest`. Documentadas no catálogo `capability-labels.md` como "Reservada — sem provider v1". Cards correspondentes virão em v1.1+ conforme demanda real (roadmap, não meia-bomba).
- [x] **Labels out-of-scope v1** — documentadas em `capability-labels.md` como "rejeitadas / out-of-scope". Decisão final: cards correspondentes virão em v1.1+ conforme demanda.
- [x] **Schema do `card.md`** — exemplo de detecção/contribuição ainda referenciava `firebase-firestore` monolítico. Cleanup 3.5: substituído por `firestore-persistence`. (mesmo escopo do PENDENTE 115 acima)
- [x] **`validate_data_contract.py`** — Fase 5b entregou (194 LOC). Reconhece `persistence_strategy`, `operations`, sub-blocos por capability (`firestore_collections`, `rest_endpoints`, `local_tables`, `local_prefs`, `realtime_streams`) + cross-check strategy×card.
- [x] **`validate_capability_labels.py`** — Fase 5b entregou (149 LOC). Parse de `capability-labels.md` + força conformidade em todos os `cards/*/card.yaml`. Reservadas → warn; out-of-catalog → fail.
- [x] **Card `crashlytics`** — confirmar que injeta nome canônico `Firebase{Feature}AnalyticsException` no rule:error-event-binding. Cleanup 3.5: `contract-planner-additions.md` reforça o naming canônico (era `exception-class:` em texto sem referência viva); link para `FirebaseAuthAnalyticsException.kt` em MeoBonsai adicionado como exemplo. `tech-spec-additions.md` já carrega a forma canônica.
- [x] **`evals.template.json` path** — mora em filesystem-layout como `evals/evals.json` (subpasta); template atual é single file. Cleanup 3.5: nota `_template_location` adicionada ao JSON deixando explícito que o template canônico vive em `templates/evals.template.json` e que o engine materializa em `{feature}/evals/evals.json`.
- [x] **Forge init UX** — `engine/init.py` implementa Cena 6.5 backend-candidates (firebase-stack / rest-stack / hybrid / local-only / personalizar). Roteiro `forge-init-roteiro.md` (Fase 4 implementa Python).
- [x] **`extension-points` no `screen-analysis-agent`** — frontmatter não declarava extension-points (card `compose-screens` reportou contribuição como documento preparatório fora de `agent-prompts`). Cleanup 3.5: 4 extension-points adicionados (`after:Component Detection`, `section:UI State Inference`, `section:Visual Ambiguities`, `after:i18n key candidates`).
- [x] **`nav3/card.yaml conflicts-with`** — label `navigation2-android` está fora do catálogo v1. Verificado em cleanup 3.5: `conflicts-with: []` já estava com FOLLOWUP comment apontando reativação em v1.1+. Spot-check cobre `swiftui-screens`, `compose-screens`, demais cards — nenhuma label fora do catálogo nos conflicts-with ativos.

## Phase 4 — Músculos (código) ✅ 57 arquivos, ~12.880 LOC

- [x] Bash dispatcher → `bin/forge`
- [x] Python engine entry → `engine/__init__.py` + `engine/cli.py` (argparse-less dispatcher)
- [x] `engine/init.py` — auto-detect + questionnaire + backend-candidates + inventory + graph build + workflow-config writer
- [x] `engine/plan.py` — planning-conductor Waves A-E + auto-resume + phase_lock
- [x] `engine/implement.py` — task executor topo-sort + plan mode + apply handoff
- [x] `engine/verify.py` — validator cascade fail-fast + `run_scope` API
- [x] `engine/doctor.py` — 11 health checks (full) / 3 (quick) + bak overdue
- [x] `engine/reconfigure.py` — single mutation entrypoint + 10 submenus
- [x] `engine/status.py` — read-only board 6 sections (não listado original)
- [x] `engine/raw.py` — escape hatch (verify-card, edit-config, rebuild-templates real, forge-debug, migrator stub)
- [x] `engine/graph/builder.py` + `incremental.py` + `queries.py` (Q1-Q10) + 3 parsers (Kotlin/Swift/TS)
- [x] `engine/memory/{l1,l2,l3,distiller}.py`
- [x] `engine/cards/{loader,resolver,merger,snapshotter}.py`
- [x] `engine/inventory/{design_system,i18n,conventions}.py`
- [x] `engine/mcp/{registry,types,jira,linear,github_issues,context7}.py`
- [x] `engine/vision/screenshot.py`
- [x] `engine/ingest.py` — single ingest entry pra hook events
- [x] `engine/evolve.py` — review proposed evolutions single-by-single
- [x] `engine/undo.py` — 7 targets menu
- [x] `engine/graph_cli.py` — Q1-Q10 read-only CLI
- [x] `engine/memory_cli.py` — inspect/search/forget/distill/export
- [x] `engine/utils/{paths,yaml_io,sha256,sqlite_io}.py`
- [x] `engine/ui/{renderer,progress,tree,question}.py`
- [x] `engine/persona/mentor_calmo.py`
- [x] `pyproject.toml`
- [x] **Cleanup final** — 29 FOLLOWUPs fechados (forge-version-lock, .gitignore init, history HIST-001..012, doctor last-run, verify L1+log+API, ingest pre-commit real, raw rebuild-templates real, undo commit-sha schema, memory_cli distill real, capability-labels parser, CARD-011/012 cross-check + 3 card bugs fix, categorias, firebase-auth confidence, setext headings, Windows filelock, rejected fingerprints schema, verify-log validation, L2 buckets aux, gitignore parser, 6 tabelas populate, concurrency lock, to_file_id resolution, JUnit5, tailwind parser, level fallback, AndroidManifest, features counter, Ticket dataclass)

## Phase 5 — Pele e validação ✅ 59+13 arquivos, ~6600 LOC

- [x] **Hooks** (9 arquivos, ~277 LOC em `hooks/`):
  - [x] `hooks/post-edit-codebase-graph.sh`
  - [x] `hooks/post-write-feature-artifact.sh`
  - [x] `hooks/pre-commit-feature-forge.sh`
  - [x] `hooks/post-subagent-validate.sh`
  - [x] `hooks/session-start-drift-check.sh`
  - [x] `hooks/git-pre-commit` + `git-post-commit` + `git-pre-push`
  - [x] `hooks/ci-pr-ingest.yml` (GitHub Actions workflow template)
- [x] **Validators Python** (15 arquivos, 2622 LOC em `validators/`):
  - [x] `validate_feature_package.py` (242 LOC) — completeness vs strictness-matrix
  - [x] `validate_readiness.py` (171 LOC) — parseia readiness_verdict
  - [x] `validate_task_contract.py` (247 LOC) — schema + gates + deps
  - [x] `validate_data_contract.py` (194 LOC) — persistence_strategy + strategy×card cross-check
  - [x] `validate_screen_analysis.py` (207 LOC) — StateUI + Meo* refs vs inventory
  - [x] `validate_backend_e2e.py` (207 LOC) — provider + scenarios coverage
  - [x] `check_no_invented_behavior.py` (184 LOC) — grep logEvent/testTag vs contracts
  - [x] `check_files_in_allowed_files.py` (193 LOC) — git diff vs allowed_files
  - [x] `validate_capability_labels.py` (149 LOC) — labels ∈ catalog
  - [x] `validate_workflow_config.py` (175 LOC) — schema + cards sha256
  - [x] `validate_card_yaml.py` (111 LOC) — wrapper CARD-001..018
  - [x] `validate_inventory.py` (161 LOC) — DS/i18n/conventions schemas
  - [x] `validate_memory.py` (197 LOC) — L1/L2/archived schemas
  - [x] Helpers: `__init__.py` + `_common.py` (3-paths + JSON output canônico)
- [x] **E2E test scenarios** (5 cenários em `tests/e2e/`):
  - [x] greenfield init (`test_e2e_greenfield_init.py`)
  - [x] brownfield init in MeoBonsai (`test_e2e_brownfield_init.py`)
  - [x] full plan (`test_e2e_full_plan.py`)
  - [x] implement-task gates (`test_e2e_implement_gates.py`)
  - [x] resume after pause (`test_e2e_resume_after_pause.py`)
- [x] **Tests extra** (30+ arquivos, ~3460 LOC em `tests/`):
  - [x] 20 unit tests (engine/utils, ui, persona, cards, memory, graph, inventory, mcp)
  - [x] 5 integration tests (init greenfield/brownfield, cards resolver MeoBonsai, graph build, inventory extract)
  - [x] 13 validator tests (smoke + happy + fail paths, +596 LOC)
  - [x] conftest.py com fixtures comuns (tmp_project_root, tmp_forge_project, meobonsai_root, tmp_forge_project_with_feature)
- [x] **Cleanup Fase 5** — 3 itens fechados:
  - [x] Hooks instalação automática durante `forge init` Step 13 (+92 LOC em init.py — `_install_hooks` + `_install_git_hooks` com symlinks relativos pra `.git/hooks/`)
  - [x] 3 handlers ausentes em `engine/ingest.py`: `post-subagent-validate`, `pre-push`, `ci-pr-ingest` (+150 LOC, 8 rotas totais)
  - [x] Tests dos 13 validators (13 arquivos novos em `tests/unit/test_validators_*.py`)

**Smoke gates finais:** 258 tests passing, 12 skipped (e2e por default — `RUN_E2E=1` ativa). Zero regressões.

### Out-of-scope Fase 5 (decisões arquiteturais, não FOLLOWUPs)

- `engine.doctor` não expõe `_run_quick_check` como API pública — `ingest._handle_pre_push` tem fallback gracioso; expor API quando v1.1 demandar
- Windows symlink fallback em `_install_git_hooks` — silent try/except OK; ADR formal quando Windows entrar
- `read_yaml_or_default` raise em YAML malformado — decisão validator-side; trocar requires patch coordenado nos 13 validators

## Reading order for new contributors

**For a fresh session retomando o projeto, use o handoff:**

→ `docs/design/08-session-handoff.md` (TL;DR + ordem mandatória + auto-mode prompt)

**Para revisão profunda, ordem completa:**

1. `docs/design/08-session-handoff.md` (start here!)
2. `README.md`
3. `docs/design/01-decisions.md` (27 decisões locked)
4. `docs/design/06-command-surface.md` (12 comandos, zero flags)
5. `docs/design/07-discipline.md` (7 disciplines universais)
6. `docs/design/00-vision.md`
7. `docs/design/02-phases.md`
8. `docs/design/03-influences.md`
9. `docs/design/05-filesystem-layout.md`
10. `docs/ux/forge-init-roteiro.md` (start UX docs here)
11. `docs/schemas/workflow-config.md` (start schemas here)
12. `agents/planning-conductor.md` (start agents here)
13. `docs/lifecycle/memory-and-graph.md`
14. This file (04-pending.md) to see what's left
