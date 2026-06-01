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

## Stress-test 2026-05-29 — gaps a tratar

Stress test conversacional executado 2026-05-29 confrontou o pipeline contra 6
cenários cobrindo 5 famílias de estresse (cerimônia desproporcional, escopo
que rompe a unidade "feature", mutação durante execução, shape fora do happy
path, humano/time/compliance). Resultado: 1/6 bem coberto, 3/6 gaps remediáveis
sem quebrar decisões locked, 1/6 gap fundamental (precisa novo estado de
feature), 1/6 out-of-scope honesto v1.

A intenção dessa seção é virar fila de evolution candidates pra v1.1+, **não**
re-abrir decisões locked. Mentor calmo é firme nas bordas — as 27 decisões
permanecem como estão. Estes gaps são para **estender o forge dentro das
decisões**, não revisitar.

### Gap 1 — Cenário A1: Hotfix urgente sem fast-path ✅ resolvido 2026-05-30 (bugfix subtype completo)

**Severidade:** média. Bugfix realmente urgente (P0, 30min) força cerimônia
desproporcional (~6-10 min de waves + plan-mode + apply + review). Dev tende a
bypassar o forge — tensão entre disciplina e pressão de produção.

**Origem:** `forge-plan-roteiro.md` waves A-E rodam todas independente de
shape; `agents/planning-conductor.md` Phase 2 walk em 27 nós sem short-circuit;
shape canônico "bugfix" inexistente; auto-retrospective gera proposed-evolutions
mesmo pra fix trivial.

**Solução aplicada — `bugfix` subtype shipped completo:**

A solução constrói diretamente sobre o subtype mechanism do Gap 2 (refactor
ship 2026-05-30) e a state-orthogonal `blocked-on-external` do Gap 8 — sem
regredir nenhum dos dois. `bugfix` é o 5º valor do `subtype` enum (após
product / refactor / spike / chore), com semântica distinta de refactor:

- Refactor = comportamento inalterado por design; Wave B sempre skipada;
  `check_no_behavior_change` gate.
- Bugfix = restaurar comportamento correto; Wave B **conditional** (1 sub-
  question em Cena 2.5); sem `check_no_behavior_change` (mudança é
  inerente — de quebrado pra correto).

- [x] **Subtype `bugfix` no enum canônico** — `engine/memory/l1.py
      _VALID_SUBTYPES`, `docs/schemas/memory.md §subtype semantics by
      value`, MEM-L1-008 atualizada pra aceitar o 5º valor.
- [x] **Filesystem layout** — mesmo `non-product/{slug}/` subtree usado por
      refactor. Decisão: bugfix também é "não é nova product behavior", é
      "restaurar product behavior correto", então cabe no mesmo guarda-chuva.
- [x] **Cena 2.5 estendida** em `docs/ux/forge-plan-roteiro.md`:
      - Keyword detection: `bugfix`, `hotfix`, `P0`, `P1`, `crítico`, `bug `,
        `fix `, `falha`, `quebrado`, `não funciona`, `regression`, `crash`
      - **Ticket-pattern detection** (`IN-NNNNN`, `PD-NNNN`, `BUG-NNNN`
        prefixes only — `BACKEND-`/`BONSAI-` ambíguos não promovem)
      - 3 novos casos UX: happy path + P0/hotfix urgency + vague description
      - Sub-question da Wave B: "esse bug envolve mudança de UI ou de
        comportamento observável?" — única decisão extra do bugfix
- [x] **Engine wiring** em `engine/plan.py`:
      - `_SUBTYPE_KEYWORDS["bugfix"]` com 20 keywords
      - `_TICKET_PATTERN` regex + `_BUGFIX_TICKET_PREFIXES` whitelist
      - `detect_subtype_from_input` agora cobre keyword + ticket pattern
        (precedence: refactor > bugfix > spike > chore > ticket pattern)
      - `_WAVE_ORDER_BUGFIX_LOGIC_ONLY` (A·C·D·E) +
        `_WAVE_ORDER_BUGFIX_UI_OBSERVABLE` (A·B·C·D·E)
      - `_wave_order_for_subtype(subtype, wave_b_required=...)` runtime
        branching (única wave-dispatch que depende de sub-question)
      - `_elicit_bugfix_wave_b_required()` + `_persist_hypothesis_wave_b_required()`
        + `_read_hypothesis_wave_b_required()` helpers
      - `WAVE_A_BUGFIX_TEMPLATES` constant pointing at the new intake
      - `run()` chama Wave B sub-question pra bugfix antes do dispatch
      - Artifact-count message do closing reflete Wave B status
- [x] **Template novo** `templates/feature-intake-bugfix.template.md` —
      intake stripped com §Problem statement, §Reproduction steps (MANDATORY),
      §Expected vs actual behavior, §Root-cause hypothesis (with confidence),
      §Fix scope, §Regression risk (low/medium/high), §Validation strategy,
      §Links. Drop intencional: "user value", "scope OUT", "why now".
- [x] **`agents/planning-conductor.md`** patched:
      - Phase 1 step 4: bugfix keyword cues + urgency acknowledgment +
        Wave B sub-question
      - Phase 1 hypothesis.yaml bugfix variant (bug-ticket, repro-known,
        wave_b_required, root-cause-confidence, regression-risk, fix-shape)
      - Phase 2 "Ticket pattern detection" subsection (high-confidence
        bumps) + table de prefixes
      - Phase 4 wave-dispatch matrix com bugfix row + Bugfix branch
        section (Wave B conditional behavior)
      - Phase 6 auto-retrospective trigger com **5-whys prompt template**
        (Gap 1 mandatory — bugfix retro tem highest learning value)
      - Closing format ganha **bugfix variant** (Wave B ran/skipped flag,
        regression risk, retrospective notice)
- [x] **`agents/tech-spec-agent.md`** patched:
      - Context pack subtype field aceita "bugfix" + novo `wave_b_required`
        field documentado
      - Document structure: **subtype-conditional rendering** section
        ganha bugfix mode (sempre §§ 1·2·3-7·13·14; §11 conditional;
        §§ 8·9·10·12 skip)
      - Phase 2 ganha "Bugfix variant" (antes/depois of behavior path)
      - Phase 3 ganha bugfix two-modes (UI/observable vs logic-only)
      - **Example 4 — Bugfix subtype IN-37234** com context pack
        completo + tech-spec rendering + output JSON
- [x] **`docs/design/07-discipline.md` §8** estendida pra cobrir bugfix:
      - Tabela de subtypes ganha bugfix row
      - Nova subseção "Bugfix — comportamento detalhado (Gap 1, 2026-05-30)"
        com: quando aplica, distinção formal vs refactor (tabela 5-eixos),
        Wave A/B/C/D/E semantics, **Phase 6 5-whys template**
      - Filesystem layout atualizada
      - Keyword table ampliada com bugfix + ticket pattern regex
      - Cheat-sheet operacional preservada (sem nova entrada — bugfix
        cabe em §8)
- [x] **`tests/unit/test_plan_subtype.py`** estendido (não substituído):
      - 6 novos casos de bugfix keyword detection
      - 6 novos casos de ticket pattern detection (whitelist + non-whitelist)
      - 3 novos casos de priority (refactor vs bugfix, bugfix vs spike,
        product when only ticket)
      - 3 novos wave-order tests (logic-only / UI-observable / None default)
      - 2 novos L1State round-trip tests (bugfix + all-5 canonical)
      - 1 novo set_subtype bugfix persistence test
      - 3 novos intake template selection tests (constant pointing, distinct,
        file exists on disk)
      - 3 novos hypothesis.yaml wave_b_required round-trip tests
      - **+28 tests · 0 regressions · 365 passed, 1 skipped (baseline 337+1)**

**Princípio preservado:** zero flag (Decision 10), 12 comandos (Decision 9),
3-caminhos universal (discipline §1), pause-vs-abort (discipline §7),
never-invent (00-vision §What feature-forge is NOT), deterministic context
(sub-agents recebem subtype + wave_b_required via context pack).

**Gap 2 e Gap 8 NÃO foram regredidos:**

- Subtype enum estendido de 4 → 5 valores (refactor/spike/chore preservados)
- Wave order de refactor preservado (A·C·D·E)
- `check_no_behavior_change` continua rodando APENAS quando subtype=refactor
  (não roda em bugfix — bugfix muda comportamento por definição)
- `blocked-on-external` state preservado (ortogonal a subtype — bugfix
  pode ficar blocked esperando backend, exatamente como refactor pode)

**O que ficou como TODO residual (v1.1+):**

- [ ] **Smart 5-whys prompting** — atualmente o retrospective-agent recebe
      um template estático. v1.1+: agent lê root-cause unknown vs confirmed
      e adapta o prompt (mais drill-down quando confidence inicial era < 0.5).
- [ ] **Auto-detection de regression test missing** — quando bugfix
      implement.py finaliza sem adicionar test, validator novo emite warning
      ("bugfix sem regression test é bugfix cego"). Não bloqueia em v1.0;
      virou cheat de retro pra ser proposed-evolution.
- [ ] **Cross-feature bug pattern detection** — quando 2+ features tiveram
      bugfix com root cause similar (ex.: "trim falta em validador") em
      janela curta, retrospective emite proposta de promover guard pra
      shared/core/util/.
- [ ] **`forge graph` Q12 — bugs-similar-root-cause** — query nova pra
      reuso de fix patterns. v1.1+ quando houver dados suficientes pra
      similarity metric significativa.
- [ ] **Severity gating** — quando severity=P0/P1 em hypothesis, Wave E
      relaxa ainda mais (aceita partial root-cause confidence). v1.1+ —
      por ora P0 e P3 seguem o mesmo gate.
- [ ] **Anti-pattern: A2 small feature** — explicit non-goal aqui. Small
      product features ficam como product subtype. Plan tamanho é
      proporcional ao tamanho da feature; não há mecanismo especial.

**Validation pendente para piloto smoke test:**

- [ ] Smoke test bugfix UI/observable: planejar fix de UI real
      (ex.: BonsaiForm que aceita whitespace como nome vazio), confirmar
      `subtype=bugfix` + `wave_b_required=true`, verificar que Wave B
      roda + tech-spec foca §1·§2·§3-7·§13·§14.
- [ ] Smoke test bugfix logic-only: planejar fix de lógica pura
      (ex.: validador de email com regex incorreto), confirmar
      `subtype=bugfix` + `wave_b_required=false`, verificar que Wave B
      pula + intake-bugfix renderiza + tech-spec é stripped (similar a
      refactor mas com regression-risk).
- [ ] Smoke test ticket pattern detection: input `IN-37234 está
      crashing app no Android 14`, verificar que conductor sobe pra
      bugfix confidence alta na Cena 2.5.
- [ ] Smoke test urgency acknowledgment: input com "P0 em produção",
      verificar que conductor cumprimenta urgency + segue disciplina
      (não pula Wave B quando bug é UI).
- [ ] Smoke test 5-whys retrospective: completar implement de bugfix,
      verificar que retrospective-agent emite proposed-evolutions com
      walked-through analysis (não vazio, não "be more careful").
- [ ] Smoke test conductor vague drill-down: input "tem um bug, algo
      não funciona", verificar que conductor recusa rotear bugfix +
      apresenta 3-caminhos.

**Arquivos modified (Gap 1):**

- `docs/schemas/memory.md` — `bugfix` em subtype enum + semantics row + MEM-L1-008
- `docs/design/07-discipline.md` — §8 ganha bugfix subsection + tabela
  expandida + keyword table + cross-link refs
- `docs/ux/forge-plan-roteiro.md` — Cena 2.5 ganha 3 cenários bugfix
  (happy + P0 urgency + vague) + nota operacional sobre Wave B sub-question
- `agents/planning-conductor.md` — Phase 1 (bugfix keyword cues + Wave B
  sub-question + urgency ack) + Phase 1 hypothesis bugfix variant +
  Phase 2 (ticket pattern detection table) + Phase 4 (matrix row +
  Bugfix branch section) + Phase 6 (5-whys retro template) + Closing
  format (bugfix variant)
- `agents/tech-spec-agent.md` — context pack (subtype + wave_b_required) +
  subtype-conditional rendering (bugfix mode) + Phase 2 bugfix variant +
  Phase 3 bugfix two-modes + Example 4
- `engine/memory/l1.py` — `_VALID_SUBTYPES` ganha bugfix
- `engine/plan.py` — `_SUBTYPE_KEYWORDS["bugfix"]` + `_TICKET_PATTERN` +
  `_BUGFIX_TICKET_PREFIXES` + `_WAVE_ORDER_BUGFIX_*` + `_wave_order_for_subtype`
  com kwarg + `detect_subtype_from_input` com ticket pattern bump +
  `WAVE_A_BUGFIX_TEMPLATES` + `_elicit_bugfix_wave_b_required` +
  `_persist_hypothesis_wave_b_required` + `_read_hypothesis_wave_b_required` +
  `_confirm_subtype_inference` ganha bugfix pretty-name + `_run_waves_for_subtype`
  com kwarg + `run()` orquestra Wave B sub-question + artifact message
- `templates/feature-intake-bugfix.template.md` — NEW, 230 LOC
- `tests/unit/test_plan_subtype.py` — +28 tests (327 LOC adicionadas)

### Gap 2 — Cenários A3/A4: Non-product feature track (spike + refactor + chore) ✅ resolvido 2026-05-30 (refactor only; spike + chore stubbed)

**Severidade:** alta. Forge atualmente modela só features de produto. Cenários
"non-product feature" não cabem honestamente:

- **Spike (A3):** comportamento ainda desconhecido. Não tem PRD definitivo,
  não atinge `readiness=ready`. Forçar Wave B faria conductor "inventar".
- **Refactor (A4):** comportamento explicitamente inalterado por design.
  Sem PRD natural, sem screen-analysis (zero mudança visual), sem analytics.
  Forçar contract-planner-agent gera 5 specs vazias ou artificiais.
- **Chore:** atualização de dep, bump de versão, cleanup. Mesma classe.

Todas violam o princípio "eu não invento" (00-vision §What feature-forge
is NOT) quando passam pelo pipeline default.

**Origem:** estados de feature em 07-discipline §7 (`not-started → planning →
planned → implementing → verified → done`) não comportam non-product; waves
B-C-D obrigatórias geram artefatos sem matéria-prima; L1→archived polui
similarity-graph com tentativas descartadas (no caso de spike) ou refactors
internos (no caso de A4).

**Solução aplicada — `refactor` completo, `spike + chore` stub via 3-caminhos:**

- [x] **Novo guarda-chuva `non-product-feature track`** com subtipos
      `spike | refactor | chore`. `refactor` ship por completo nesta v1.0;
      `spike + chore` ficam como stub via 3-caminhos discipline §1 (caminhos
      legítimos: treat as product / wait v1.1+ / abort) — sem improviso.
- [x] **Filesystem-layout extension:**
      `docs/feature-implementation-workflow/non-product/{slug}/` paralelo a
      `features/{slug}/`. Tabela em `docs/design/05-filesystem-layout.md §3`
      mostra quais artefatos existem por subtipo. Não entra na
      similarity-graph automática (conductor §Phase 1 skipa Q1 quando
      subtype=refactor).
- [x] **Cena 2.5 do plan-roteiro** (nova seção inserida entre Cena 2 e
      Cena 3) detecta keywords ("spike", "POC", "viabilidade", "exploração",
      "refactor", "mover", "renomear", "extrair", "sem mudança visual",
      "bump", "atualizar dependência", "cleanup", "chore") e roteia para
      o subtipo apropriado interativamente. Zero flag — Decision 10
      preservada.
- [x] **Validator novo `check_no_behavior_change.py`** quando subtipo=refactor:
      rejeita se diff toca testes funcionais (indicador de mudança
      comportamental disfarçada). 3-caminhos canônico (fix/revert/split).
      Inactive quando subtype != refactor (no-op pass).
- [x] **Template novo `templates/feature-intake-refactor.template.md`** —
      variante stripped sem PRD: §Problem, §Root cause, §Files affected,
      §Architecture before→after, §No-behavior-change attestation
      (checklist explícito), §Validation strategy.
- [x] **`status.json` schema upgrade aditivo** — campo `subtype` em
      `docs/schemas/memory.md §status.json`. Default `"product"` quando
      ausente (forward compat para status.json escritos por engines
      pre-Gap-2). Validation rule MEM-L1-008 estendida.
- [x] **`L1State.subtype` em `engine/memory/l1.py`** + helpers
      `current_subtype()` / `set_subtype()`. Round-trip + invalid-value
      rejection cobertos por testes.
- [x] **`engine/plan.py` branch wave dispatch** — `_wave_order_for_subtype`
      retorna (A,B,C,D,E) para product e (A,C,D,E) para refactor;
      `_resolve_features_root` reroteia para `non-product/{slug}/` quando
      subtype != "product"; `_handle_stub_subtype` surface 3-caminhos
      para spike/chore.
- [x] **`agents/planning-conductor.md` Phase 1 + Phase 4** patched:
      Cena 2 source-inquiry agora documenta subtype detection (Phase 1
      step 4); Phase 4 declara wave matrix por subtype + bloco 3-caminhos
      para spike/chore; closing format ganha refactor variant.
- [x] **`agents/tech-spec-agent.md` context pack + Document structure**
      ganha campo `subtype`, lista artefatos ABSENT por subtype, e
      seção "Subtype-conditional rendering" declarando quais §§ vivem
      em refactor (§§ 1, 2, 3-7 modified-only, 14).

**Princípio preservado:** zero flag (Decision 10), 12 comandos
(Decision 9), 3-caminhos universal (discipline §1), pause-vs-abort
(discipline §7), never-invent (00-vision §What feature-forge is NOT).

**O que ficou como TODO residual (v1.1+):**

- [ ] **Spike subtype completo** — workspace livre + findings opcionais
      + UX de "promote spike to feature" quando user decide ir adiante.
      Stub atual surfaces 3-caminhos. Issue: workspace livre quebra a
      premissa de `readiness=ready` que vários comandos confiam — precisa
      novo estado `exploring` ortogonal antes de shippar.
- [ ] **Chore subtype completo** — intake-minimal + task-contract apenas.
      Stub atual surfaces 3-caminhos. Issue: chore frequentemente cruza
      múltiplas features (bump de dep toca N módulos) — fica acoplado a
      Gap 3 (migração grande).
- [ ] **`subtype-aware retrospective-agent`** — quando refactor termina,
      retrospective deve emit propostas de promoção de helpers
      identificados durante o move (não promoção de patterns de produto).
      Pendente de design.
- [ ] **`forge graph` query Q12 — refactors-similar-shape** — quando user
      planeja refactor novo, mostrar refactors anteriores similares
      (mover X→Y, rename A→B). Stub: usar Q1 existente filtrado por
      `non-product/`.
- [ ] **`status.json.subtype` migration tool** — para projetos que já
      têm features no L1 com status.json pre-Gap-2 e queiram explicitamente
      backfill `subtype: product`. v1.0 trata ausência como product
      automaticamente; tool seria opt-in.
- [ ] **Edge case documented**: feature começa como product, depois user
      percebe que é refactor mid-planning. Caminho atual: `forge undo`
      + replanejar. v1.1+: `forge reconfigure` → menu "trocar subtype"
      com validação que Wave B artifacts estão deletados.

**Validation pendente para piloto smoke test:**

- [ ] Smoke test refactor real no MeoBonsai: planejar mover `MeoButton`
      de `organisms/` → `atoms/`, verificar que Wave B skipa, intake-
      refactor renderiza, tech-spec stripped, allowed_files preciso na
      Wave D, check_no_behavior_change passa em diff limpo.
- [ ] Smoke test happy: planejar feature de produto normal (`lembrete-rega`)
      e verificar que `subtype: product` persiste e Wave B roda normal.
- [ ] Smoke test stub: tentar planejar com keyword "spike" e verificar
      que 3-caminhos block renderiza, option A (treat as product) flipa
      subtype e continua Wave B.
- [ ] Verificar que `forge status` board lê subtype corretamente quando
      feature já planejada (dependência cross-arquivo `engine/status.py`
      — não tocado em Gap 2; pode precisar ajuste cosmético em v1.1).
- [ ] Verificar que `forge implement` em refactor lê task-contract
      `validations: [check_no_behavior_change]` e roda o gate na cascade.

**Arquivos modified (Gap 2):**

- `docs/schemas/memory.md` — `status.json.subtype` field + MEM-L1-008
- `docs/design/07-discipline.md` — nova §8 "Non-product feature track"
- `docs/design/05-filesystem-layout.md` — `non-product/{slug}/` tree
  + artifact-per-subtype matrix
- `docs/ux/forge-plan-roteiro.md` — Cena 2.5 Subtype detection
- `agents/planning-conductor.md` — Phase 1 (subtype detection) + Phase 4
  (wave dispatch branching) + closing format (refactor variant)
- `agents/tech-spec-agent.md` — context pack subtype field + Document
  structure subtype-conditional rendering + Phase 2/3 patches
- `engine/plan.py` — `detect_subtype_from_input`, `_wave_order_for_subtype`,
  `_resolve_subtype_for_run`, `_handle_stub_subtype`,
  `_run_waves_for_subtype`, `_resolve_features_root` subtype param,
  `_feature_path` subtype param
- `engine/memory/l1.py` — `_VALID_SUBTYPES`, `L1State.subtype`,
  `current_subtype()`, `set_subtype()`, write/read validation
- `validators/check_no_behavior_change.py` — NEW, 175 LOC
- `templates/feature-intake-refactor.template.md` — NEW, 178 LOC
- `tests/unit/test_plan_subtype.py` — NEW, 31 tests

### Gap 3 — Cenário B1: Migração grande sem shape próprio

**Severidade:** média. Migrações (KMP migration, Nav2→Nav3, etc.) tocam N
features iguais. Modelar como 1 feature mãe (N tasks, retrospective só na
semana 8) OU N features paralelas (N plans, N retrospectives) — ambas geram
overhead que o forge poderia evitar com shape próprio. Caso real porque
01-decisions cita "estou modularizando outro projeto que também é Android +
iOS + KMP".

**Origem:** `task-breakdown.yaml` schema não tem conceito de "meta-task =
template + N alvos"; retrospective auto-trigger só na última task (decisão 11)
impede learning real-time durante migração longa; `proposed-evolutions.yaml`
single-file gera hotspot de merge em multi-dev.

**Remediação proposta (v1.1):**

- [ ] Card novo `migration-batch` com template "meta-task-breakdown"
      (1 template + lista de N alvos). Plan-mode mostra "vou aplicar template
      X em bonsai-list" pra cada alvo
- [ ] Retrospective incremental: a cada N=3 tasks fechadas em feature batch,
      retrospective parcial roda e queue learnings. Não substitui o final
- [ ] `status.json` schema upgrade pra `active-tasks: [list]` em vez de
      singular — abre caminho pra E1 também (multi-dev)

### Gap 4 — Cenário C1: PRD muda mid-implement, sem validação post-fact

**Severidade:** baixa. Decisão 9 + 06-command-surface §"Amend plan" cobrem o
fluxo. Gap pequeno no post-fact: tasks done antes do re-plan não são
validadas contra novo PRD — código legacy passa silentemente desalinhado.

**Origem:** Cena 1 do plan-roteiro oferece "Retomar/Começar feature nova/
Abortar e começar do zero", mas não há validator que confronta tasks done
existentes com novo plano gerado.

**Remediação proposta (v1.1):**

- [ ] Validator novo `validate_pre_existing_tasks_vs_new_plan.py` dispara no
      início do re-plan: (a) task done existe no novo task-breakdown?
      (b) allowed_files batem? (c) contracts batem? Gera findings STALE
- [ ] Documentar explicitamente em `task-contract.template.yaml` que IDs de
      tasks done são imutáveis em re-plan; tasks novas pegam IDs incrementais
      a partir de `max(done)`
- [ ] Novo finding type `STALE-DELIVERY-{n}` com proposed-remediation
      surfaceada em `forge evolve`

### Gap 5 — Cenário D2: Stack fora do catálogo (gap grande pra portabilidade)

**Severidade:** alta. Decisão 22 ("absorb essences, no dependencies") +
princípio "portabilidade" (00-vision) batem de frente com catálogo fechado.
Forge atual é portátil só dentro do espaço amostral coberto pelos 20 cards
canônicos. Projetos com Hilt (não Koin), Apollo GraphQL, Realm, etc., não
têm caminho oficial.

**Origem:** `card.md` §"Out of scope for v1" declara "Marketplace de cards"
out-of-scope; `validate_capability_labels.py` (Fase 5b) força "labels ∈
catalog"; `forge reconfigure` opção "adicionar card" referencia só
canonical; init detection com 0 matches em stack desconhecida pode propor
default conflitante.

**Remediação proposta (v1.1):**

- [ ] `.claude/cards/local/{name}/` como overlay aos canônicos. Documentar
      em `card.md` §"Where cards live"
- [ ] `.claude/inventory/capability-labels.local.yaml` que estende o catálogo;
      `validate_capability_labels.py` aceita catalog ∪ local
- [ ] `forge reconfigure` ganha opções "adicionar card local (criar do
      skeleton)" e "importar card de path"
- [ ] Init fail-safe quando stack ambígua: signals batem em label custom
      mas card ausente → 3-caminhos (criar local skeleton / `forge ignore` /
      abortar até v1.1+)
- [ ] Roadmap explícito de cards v1.1+ priorizando labels reservadas:
      `hilt-di`, `apollo-graphql-client`, `realm-database`,
      `auth-oauth2-rest`

### Gap 6 — Cenário E1: Multi-dev mesma feature (out-of-scope v1 honesto)

**Severidade:** —. `memory-and-graph.md` §"Out of scope for v1" declara
explícito "Single-user assumed in v1". Não é gap escondido — é decisão
arquitetural honesta. Mas é caso de uso real frequente em times mobile.

**Workaround atual:** features que precisam multi-dev → split em 2 features
com dependência declarada (`lembrete-rega-shared`, `lembrete-rega-android-ui`).

**Remediação proposta (v1.1+):**

- [ ] `status.json` schema upgrade pra `active-tasks: [{task, actor}]` (também
      atende Gap 3)
- [ ] `history.jsonl` schema com campo `actor` + estratégia de merge
      sort-by-timestamp (resiliente a git merge automático)
- [ ] L1 sync seletivo via L2 proposal proativa: Finding com `severity: high`
      → forge propõe promoção pra L2 em real-time
- [ ] ADR formal documentando trade-offs single-user vs multi-user

### Gap 7 — Cenário B2: Feature em múltiplos releases (time-shifted shipping)

**Severidade:** média. Forge assume 1 feature = 1 ship moment. Realidade
mobile é commonly multi-ship: Android sai em Q3, iOS sai em Q4. Mesma
feature, 3 meses entre shipments. Time real ships partial constantly.

**Origem:** retrospective auto-trigger só após ÚLTIMA task verificada
(decisão 11); estados de feature não comportam "parcialmente released";
`status.json.current-task=null` durante o vácuo confunde retomada;
`forge status` board mostra feature como `implementing` por meses com
last-action defasado.

**Remediação proposta (v1.1):**

- [ ] Estado intermediário `partial-released` entre `implementing` e `done`,
      disparado quando subset de tasks foi taggeado como release-shipped
- [ ] Retrospective incremental disparado por **release events** (não só
      "última task verificada"): após Q3 ship Android, retrospective Wave 1
      analisa tasks do ship-group. Compartilha implementação com Gap 3
      (migração incremental)
- [ ] `task-breakdown.yaml` ganha campo opcional `release-group:
      q3-android | q4-ios`. Tasks no mesmo group compartilham ship-moment
- [ ] `forge status` mostra "shipping schedule" — quais tasks já shipadas
      vs pending por grupo (substitui visão linear single-track)

### Gap 8 — Cenário B3: Dependência externa não pronta (estado `blocked-on-external`) ✅ resolvido 2026-05-30 (schema + engine + manual unblock; MCP polling stubbed)

**Severidade:** média-alta. Caso super comum em mobile (backend atrás de
mobile). Feature plan completo, readiness=ready, mas implement das tasks
dependentes do endpoint não pode rolar — backend só sai daqui 2 sprints.

**Origem:** lifecycle não tinha estado `blocked-on-external`; schema de
task-contract só tinha dependências internas (`depends-on: [TASK-0003]`);
forge não tinha mecanismo de unblock quando ticket externo fecha;
`forge status` não distinguia blocked vs idle — dev tentava task qualquer,
esbarrava na dep, perdia tempo.

**Solução aplicada — schema + engine ship completo, MCP polling stubbed:**

- [x] **Novo estado `blocked-on-external` no `status.json`**, paralelo a
      `deferred` (engine-driven, não pause humano). Documentado em
      `docs/schemas/memory.md §state.blocked-on-external` com semântica
      completa (quando trigga, quando libera, transitions allowed). `MEM-L1-008`
      estendida para aceitar o novo valor.
- [x] **`task-contract.template.yaml` ganhou `depends_on_external`** —
      campo opcional, lista de entries com schema:
      ```yaml
      depends_on_external:
        - ticket: BACKEND-1284
          integration: jira          # jira | linear | github-issues | manual
          description: "..."
          blocking: true
          declared-at: 2026-05-30T...
          resolved-at: null          # null until forge reconfigure
      ```
      `validators/validate_task_contract.py` valida shape (ticket required,
      integration ∈ enum, blocking bool, resolved-at ISO 8601 ou null).
- [x] **`forge status` board separa in-flight / blocked / deferred / done**
      (engine/status.py reescrito; nova seção "blocked on external" lista
      cada feature + ticket + integration + age).
- [x] **`forge implement` recusa task bloqueada com 3-caminhos canônico**:
      (a) marcar dep resolvida via reconfigure, (b) pegar outra task livre,
      (c) pausar feature. Flipa `state` pra `blocked-on-external` no
      primeiro refuse de uma session (idempotente em refuses subsequentes).
      Auto-recovery: feature em blocked-on-external faz re-scan no startup
      e flipa de volta pra `implementing` quando todas deps blocking estão
      `resolved-at`.
- [x] **`forge plan` em modo "partial-ready"**: readiness-reviewer ganha
      verdict `ready-with-blocks` quando ≥1 task tem dep externa mas o
      subset não-blocked é completo. `forge implement` aceita
      `ready-with-blocks` igual a `ready`; rejeita as tasks blocked
      individualmente (3-caminhos).
- [x] **`forge reconfigure` ganhou opção "marcar dep externa como resolvida"**
      (novo handler em `engine/reconfigure.py`). Lista features blocked,
      dedupe por ticket (mesmo ticket em N tasks = 1 confirmação =
      N entries atualizadas atomically), escreve `resolved-at` com
      backup `.bak` per file + re-scan + state flip + history entry.
- [x] **Discipline §9 nova** em `docs/design/07-discipline.md` —
      semantics formais, distinção de §7 (deferred = pause humano) e
      `aborted` (terminal), interação ortogonal com §8 (subtype),
      formato canônico do 3-caminhos block, scope-out explícito do
      MCP polling.
- [x] **Roteiros patcheados:**
  - `docs/ux/forge-plan-roteiro.md` — Cena 10.5 (External dep
    detection during elicitation) com 4 sub-cenários (happy/vague/
    resolved-mid-planning/multiple-deps-same-ticket)
  - `docs/ux/forge-implement-roteiro.md` — Cena 2.5 (Blocked task
    refusal) com 4 sub-cenários (happy/no-alternative/cleared-mid-
    session/multiple-deps-same-task)
  - `docs/ux/forge-reconfigure-roteiro.md` — sub-cena 5.6
    (External-deps) com 4 sub-cenários (happy/multi-task/empty/
    ticket-not-found)
- [x] **Agents patcheados:**
  - `planning-conductor.md` Phase 2 ganhou "External dependency
    drill-down" table com triggers e drill-down rules. Phase 4
    declara context-pack field `external-deps`. Closing format
    ganhou ready-with-blocks variant.
  - `task-contract-writer.md` Phase 4 ganhou step 6 (External
    dependencies) explicando task-hint resolution + dedupe rules.
    `external-deps` agora documentado no context pack input.
  - `readiness-reviewer.md` Phase 4.5 (External dependencies audit)
    + verdict matrix atualizada com `ready-with-blocks` distinto de
    `partial`. JSON output ganhou `external-blocks` array.
- [x] **`L1State` extendido em `engine/memory/l1.py`**:
  - `_VALID_STATES` aceita `blocked-on-external`
  - `is_blocked(slug, project_root) -> bool`
  - `blocking_deps(slug, project_root) -> list[dict]` (walks tasks/)
  - `list_blocked_features(project_root) -> list[str]`
  - Forward-compat: status.json sem blocked state parse normal (não
    requer migration)
- [x] **`engine/plan.py` ganhou `record_external_dep()`** helper para
      planning-conductor persistir em `elicitation.yaml.external-deps[]`
      com dedupe por (ticket, task-hint).
- [x] **`engine/implement.py`:**
  - `TaskContract.external_deps` field
  - `_task_blocking_deps()` helper
  - `_pick_next_task(skip_blocked=True)` para alternativa
  - `_print_blocked_refusal()` renderiza 3-caminhos canônico
  - Refusal flow com exit code 7 (distintinto de 130 pause / 5 not-ready)
  - Auto-recovery no startup quando state==blocked-on-external mas
    deps foram resolvidas externamente
- [x] **`engine/status.py` rewrite** — board partitionado por estado
      (in-flight / blocked on external / deferred / other), com helper
      `_format_blocked_summary` que agrupa por ticket.
- [x] **`engine/reconfigure.py`** ganhou `_handle_external_deps` +
      menu option "external-deps". Discovery → ticket selection →
      dedupe confirmation → atomic write (backup + write + re-scan +
      state flip + history append) com rollback em falha.
- [x] **Testes novos** em `tests/unit/test_l1_blocked_state.py`:
  19 testes cobrindo state enum, blocking_deps semantics,
  list_blocked_features, validator schema (accept/reject), record_external_dep
  helper, implement refusal + auto-recovery, status board rendering.

**Princípio preservado:** Decision 9 (12 commands — unblock vive dentro
de `forge reconfigure`), Decision 10 (zero flags — interactive menu),
discipline §1 (3-caminhos canônico no refusal), §3 (`.bak` per file
afetado), §7 (pause vs abort intactos — blocked-on-external é
sibling, não replacement).

**O que ficou como TODO residual (v1.1+):**

- [ ] **MCP polling pra auto-unblock** — Jira/Linear webhook →
      `forge ingest --event external-dep-resolved` → auto-flip. Stub
      documentado em `docs/lifecycle/memory-and-graph.md §Out of scope
      for v1`. Decisão consciente: trust gate requer human confirmation
      em v1.0; webhook misfire pode mentir pro implement.
- [ ] **`forge undo` para "external-dep-marked-resolved"** — engine
      grava `history.jsonl` com kind = "external-dep-marked-resolved" e
      ticket id, então undo poderia restaurar `resolved-at: null` nas N
      entries afetadas. Não implementado em v1.0; via edição manual
      do task-contract por enquanto.
- [ ] **`forge plan` mid-implement add external dep** — usuário descobre
      mid-task que precisa esperar backend. Atualmente: edit
      task-contract manualmente. v1.1+: `forge reconfigure` →
      "adicionar dep externa a task em flight" com confirmação que
      flippa state.
- [ ] **TTL/stale warnings** — quando uma dep está aberta há >14d, doctor
      poderia alertar. v1.1+ quando houver dados sobre o que "stale"
      significa em prática.
- [ ] **Cross-feature dedupe** — mesmo ticket afetando features
      diferentes (BACKEND-1284 em lembrete-rega + bonsai-detail).
      Hoje `forge reconfigure` resolve por feature. v1.1+: 1
      confirmação resolve em todas as features.
- [ ] **Retrospective awareness** — quando uma feature destrava via
      external-dep-resolved, retrospective deveria notar "tempo morto
      = X dias por dep externa" pra L2 promovendo padrão de planning
      (ex.: features que tocam weather API sempre adicionar BACKEND-deps).

**Validation pendente para piloto smoke test:**

- [ ] Smoke test happy: planejar feature com dep externa real (e.g.,
      lembrete-rega waiting on BACKEND-1284), verificar que Cena 10.5
      captura a dep, task-contract-writer emite `depends_on_external`
      em `TASK-NNNN.yaml`, readiness emite `ready-with-blocks`,
      `forge implement` rejeita TASK-bloqueada com 3-caminhos e
      aceita TASK-livre.
- [ ] Smoke test unblock: marcar BACKEND-1284 como resolved via
      `forge reconfigure`, verificar state flipa pra `implementing`,
      `.bak` criado, history.jsonl com kind=external-dep-marked-resolved,
      `forge implement` aceita a task agora destravada.
- [ ] Smoke test board: rodar `forge status` com feature blocked,
      verificar seção "blocked on external" com ticket id visível e
      hint de desbloqueio.
- [ ] Smoke test multi-dep-same-ticket: feature com TASK-A e TASK-B
      ambas deps de BACKEND-1284, verificar que reconfigure dedupa
      e marca as 2 atomically.
- [ ] Smoke test forward-compat: status.json escrito antes do Gap 8
      (sem `state: blocked-on-external` no enum, sem
      `depends_on_external` em task-contracts) carrega sem
      crash + state default funciona.
- [ ] Smoke test concorrência: `forge implement` retrieve refuse em
      task blocked enquanto outro processo escreve `resolved-at` —
      garantir que o file_lock em status.json (já existente) protege
      a transição.

**Arquivos modified (Gap 8):**

- `docs/schemas/memory.md` — `blocked-on-external` no state enum +
  semantics + MEM-L1-008 atualizada
- `docs/design/07-discipline.md` — nova §9 "External dependencies"
  + cheat-sheet entry
- `templates/task-contract.template.yaml` — `depends_on_external`
  field com schema documentado
- `agents/planning-conductor.md` — Phase 2 external-dep drill-down +
  Phase 4 context-pack injection + closing format ready-with-blocks
- `agents/task-contract-writer.md` — context pack `external-deps` +
  Phase 4 step 6 + cheat-sheet additions + `after:External Dependencies`
  extension-point
- `agents/readiness-reviewer.md` — Phase 4.5 external deps audit +
  verdict matrix + JSON output + Example 4
- `docs/ux/forge-plan-roteiro.md` — Cena 10.5 (4 sub-cenários)
- `docs/ux/forge-implement-roteiro.md` — Cena 2.5 (4 sub-cenários)
- `docs/ux/forge-reconfigure-roteiro.md` — sub-cena 5.6 + menu option
- `engine/memory/l1.py` — state enum + 3 helpers (`is_blocked`,
  `blocking_deps`, `list_blocked_features`) + `_feature_tasks_dir`
- `engine/plan.py` — `record_external_dep()` helper + reads/writes
  elicitation.yaml.external-deps
- `engine/implement.py` — `external_deps` field, refusal flow,
  auto-recovery, exit code 7
- `engine/status.py` — board reescrito com 4 sections + summary helper
- `engine/reconfigure.py` — `_handle_external_deps` + menu option
- `validators/validate_task_contract.py` — schema validation pra
  `depends_on_external`
- `tests/unit/test_l1_blocked_state.py` — NEW, 19 testes

### Gap 9 — Cenário C2: Plataforma nova mid-projeto (multi-target retroativo)

**Severidade:** alta. Time decide adicionar Apple Watch (ou Wear OS, TV) a
features existentes + futuras. Cards canônicos atuais cobrem só
Android/iOS — Watch/TV/Wear caem em Gap 5 (D2). Mas há dimensão extra:
**features já feitas não ganham nova plataforma retroativamente**, e
forge não tem mecânica explícita pra isso.

**Origem:** cards `watchos-screens`, `watchos-navigation`, `wear-os-screens`
inexistentes em catálogo v1; kmp-shared não declara `watchOSArm64` target;
inventory design-system não distingue componentes por target; feature done é
done — forge não tem `forge extend-feature {slug} --add-platform watchos`
(proibido por decisão 9 + 10).

**Remediação proposta (v1.1):**

- [ ] Cards multi-target v1.1: `watchos-screens`, `watchos-navigation`,
      `wear-os-screens`, `tv-screens` (paralelos a swiftui-screens,
      swiftui-navigation, compose-screens)
- [ ] `workflow-config.yaml.targets: [android, ios, watchos]` declarativo;
      cards condicionais por target ativado
- [ ] Inventory design-system schema upgrade:
      `components/MeoButton.platforms: [android, ios, watchos]` por
      componente
- [ ] Convenção "extension feature" pra features feitas que ganham nova
      plataforma: `forge plan {slug}-watch-extension` com
      `extends-feature: {slug}` no intake — auto-importa context da feature
      pai e gera só tasks da nova plataforma

### Gap 10 — Cenário D3: Monorepo cross-project UX

**Severidade:** média. Decisão 14 cobre o caso básico (1 config por
sub-projeto). Mas monorepos com forte cross-cutting (mobile+backend+web do
mesmo produto) sofrem com features cross-project, inventories sem
cross-reference, e ausência de status agregado.

**Origem:** L4 cross-project patterns out-of-scope v1 explícito em
`memory-and-graph.md`; features cross-project (endpoint+UI) viram 2 features
ligadas só por ticket externo (também afetado por Gap 8); inventories de
i18n entre sub-projects não são cross-checkáveis; CI hooks por sub-project
não correlacionam PRs.

**Remediação proposta (v1.1):**

- [ ] `forge status` ganha prompt interativo: "ver só esse sub-projeto ou
      varrer todos?" — escaneia `**/.claude/workflow-config.yaml` no parent
      dir (preserva decisão 10, zero flags)
- [ ] L4 cross-project habilitado por opt-in:
      `workflow-config.yaml.shared-memory-with: ['../backend']` permite L2
      patterns cruzarem
- [ ] Documento `monorepo-feature.yaml` no parent dir linkando feature-slug
      entre sub-projetos (e.g., `weather-integration` está em
      mobile+backend)
- [ ] Inventory cross-check validator opt-in: confere consistência de
      i18n keys entre sub-projects que opt-in via shared-memory-with

### Gap 11 — Cenário E4: Compliance regulatório (LGPD/PCI/HIPAA)

**Severidade:** média-específica. Forge cobre "security thinking" via
`security-contract.yaml` na Wave C mas não compliance formal. Casos reais:
checkout PCI-DSS, app saúde HIPAA, qualquer feature brasileira LGPD.
Compliance exige artefatos extras (DPIA, threat model dedicado, scope
marking de arquivos, audit trail formal).

**Origem:** security-contract.yaml schema provavelmente não cobre DPIA
completo (data flow + lawful basis + retention + DPO contact); sem
template de threat model (STRIDE, attack trees); scope marking de arquivos
não modelado em task-contract; history.jsonl é audit interno, não atende
audit formal externo (assinatura, WORM retention).

**Remediação proposta (v1.1+):**

- [ ] Cards regulatórios: `lgpd-track`, `pci-dss-scope-tracking`,
      `hipaa-track`. Cada um contribui:
      - templates: DPIA-template.md, threat-model-template.md,
        scope-marking.yaml
      - validators: `scope-leak-detection.py`,
        `encryption-at-rest-check.py`, `pii-not-logged.py`
      - agent-prompts: "compliance lawyer mode" pro contract-planner-agent
- [ ] `workflow-config.yaml.compliance-track: [lgpd, pci-dss]` — opt-in
      que ativa cards correspondentes
- [ ] `task-contract.yaml.scope-tags: [pci-dss]` por task: tasks em scope
      levam validators extra
- [ ] history.jsonl extension WORM-mode opcional via filesystem flags
      pra retention legal

### Gap 12 — Cenário B4: A/B test com 2 variantes da mesma feature

**Severidade:** média-específica. Forge não tem conceito de fork/variant.
Caso comum em apps de produto (checkout A vs B, onboarding A vs B). 1 feature
= 1 slug = 1 PRD; PRD com 2 variantes formal é ambíguo no schema atual.

**Origem:** screen-analysis-agent presume 1 mockup por tela (dual mockup
quebra); analytics-spec não declara `experiment-name` + `variant-id` como
dimensions obrigatórias quando feature é A/B; estado "experiment-running"
inexistente; sem flow "promote variant" pra promover vencedor + deprecar
loser quando experimento termina.

**Remediação proposta (v1.1+):**

- [ ] Card novo `experimentation-track` ou `ab-testing-track` contribui:
      - templates: `variant-comparison-spec.yaml` (A vs B side-by-side)
      - analytics-spec extension: `experiment-name` + `variant-id` como
        dimensions obrigatórias
      - task-contract field: `variant: a | b | shared`
- [ ] Feature pode declarar `variants: [a, b]` no intake — gera 2 PRDs
      ligados, 2 screen-analysis, mas tech-spec compartilhada
- [ ] Estado intermediário `experiment-running` entre verified e done — não
      promove até experiment terminar (gradual rollout 5% → 20% → 50%)
- [ ] "Promote variant" flow: `forge plan {slug}-finalize` quando experiment
      termina — migra winner pra mainline + marca loser como deprecated

### Gap 13 — Cenário C4: Engine forge sobe de versão (schema breaking)

**Severidade:** alta na primeira transição v1.0 → v1.1. UX de migration
atualmente é escape hatch via `forge raw migrator-N-to-M` — sem UX
cinematic, sem mentor calmo, scary pra user real.

**Origem:** `forge raw` é escape hatch por design (06-command-surface §12);
migration mid-feature não documentada explicitamente (`card.md` diz
reconfigure refuses com L1 ativo, migration deveria seguir mesmo princípio);
cards locais ficam `pinned: true` e não auto-update no upgrade do forge —
drift silencioso entre canonical v1.1 e snapshot v1.0; L2 schema breaking
exige distillation; history.jsonl format change cria audit trail confuso
sem marker line.

**Remediação proposta (v1.1):**

- [ ] `forge reconfigure` ganha opção interativa "atualizar versão do forge"
      (preserva os 12 comandos, sem `forge upgrade` novo): UX guiada com
      detecção de versão, diff de schema, opção de rollback
- [ ] Pre-flight obrigatório: bloqueia migration se features `state:
      implementing|planning` — força pause primeiro (paralelo à regra
      L1-lock do card.md)
- [ ] Auto-snapshot pré-migration ampliado: workflow-config + L2 + todos
      os cards + agents snapshots — todos com `.bak`
- [ ] Transação atomic: rolls forward TODAS as dimensões juntas
      (workflow-config + cards + L2 + agents) + history.jsonl marker line
      `{"event":"schema-migration","from":1,"to":2}`
- [ ] Doctor pós-migration roda automático e exige zero issues antes de
      marcar `forge-version-lock.yaml` como atualizado

### Gap 14 — Cenário D1: Preset coverage (web, android-only, ios-only)

**Severidade:** alta-específica. Projetos web puros (React+TS) ou
single-platform (Android-only legado pré-KMP) não têm preset apropriado em
v1. Cards canônicos v1 cobrem só stack KMP-mobile. Preset coverage gap é
explícito em `filesystem-layout §1` ("planejado v1.x") mas sem timeline ou
roadmap concreto.

**Origem:** 20 cards canônicos focados em Kotlin/KMP/Compose/SwiftUI;
agent prompts treinados com exemplos KMP (vocabulary "shared layer",
"SKIE bridge" não cabe em web puro); tech-spec template é
backend-agnostic (Phase 3.5) mas §Shared (KMP) layer / §iOS / §Android
não aplicam a single-platform; inventory design-system assume Meo* +
Compose + SwiftUI — React puro com Storybook não é coberto.

**Distinção do Gap 5 (D2):** Gap 5 é "stack canônica + algumas peças
exóticas" (init detecta maioria). Gap 14 é "preset canônico errado pra
começar" (init nem decola direito).

**Remediação proposta (v1.x):**

- [ ] Cards web canônicos: `react-screens`, `next-js`, `vite-build`,
      `typescript-language`, `tailwind-design-system` — paralelos a
      compose-screens / swiftui-screens
- [ ] Presets v1.x ativados (existem como placeholders, faltam conteúdo):
      `web/`, `android-only/`, `ios-only/`, `kmp-fullstack/`
- [ ] Agent prompts ganham target-aware sections via extension-points
      (mecânica já existe via card.md — só falta material)
- [ ] Inventory extractors ganham web variants em
      `engine/inventory/design_system.py` (parser de Storybook adicional
      aos parsers Compose/SwiftUI)

### Gap 15 — Cenário D4: Brownfield com vocabulary idiossincrático

**Severidade:** média. Princípio 5 ("vocabulário nativo — lê CLAUDE.md e
rules/, usa as palavras do projeto") declara intent mas a mecânica está
parcial. Inventory captura naming patterns via regex, mas vocabulário
semântico ("Cuidador" = "user que cuida do bonsai") precisa de tradução
declarada — não inferida.

**Origem:** mecanismo concreto de "ler CLAUDE.md" não documentado além de
captura de patterns; agent prompts fixos no canonical (vocabulary
substitution não é template-substitution declarada); validators rejeitam
naming não-padrão (`Cuidador.kt` em folder `cuidadores/` pode falhar regras
que esperam `users/`); graph similarity-queries podem não casar vocabulário
do projeto.

**Remediação proposta (v1.1):**

- [ ] `inventory/conventions.yaml` ganha seção `vocabulary` explícita:
      ```yaml
      vocabulary:
        user-entity: "Cuidador"
        service: "engine"
        use-case: "Trato"
      ```
- [ ] Agent prompts ganham template substitution:
      `{{ project.vocabulary.user-entity }}` — render dinâmico no
      dispatch
- [ ] Validators ganham vocabulary-aware mode: aceita "Cuidador" se
      conventions declara user-entity = Cuidador
- [ ] `forge init` questionnaire detecta vocabulário próprio: "Detectei
      'Cuidador', 'engine' — vocabulário do projeto?" → grava em
      vocabulary

### Gap 16 — Cenário E2: Persona modes pra não-dev (PM, designer)

**Severidade:** média. Decisão 6 ("Init reveals project map") + Mentor
calmo assume usuário técnico. PM rodando `forge plan` esbarra em
elicitations técnicas ("Outbox queue vs Optimistic-write") que não tem como
responder — drill-down propõe default mas PM pode aceitar coisa errada por
não entender alternativas.

**Origem:** vocabulário técnico embutido em prompts (Firestore, SKIE,
kmp-shared); decisões de arquitetura forçadas em ambiguity-map; hypothesis
cita similarity graph que non-dev não entende; ausência de persona-aware
prompt filtering; risco de plan "tecnicamente válido mas semanticamente
errado".

**Remediação proposta (v1.1+):**

- [ ] Persona modes opt-in via workflow-config:
      `interlocutor-persona: developer | product-manager | designer`
- [ ] Modo product-manager: hide arch decisions; drill-down em UX/scope/
      business value; defer técnicas pra "depois eng decide"
- [ ] Modo designer: focus em screen states, visual decisions; defer
      everything else
- [ ] Cruza com Gap 15: persona-mode também substitui jargão técnico por
      equivalentes do vocabulary
- [ ] Automatic open-question escalation: questions técnicas em non-dev
      mode → automaticamente vira open-question bloqueante pra dev
      resolver depois
- [ ] Documentar trade-off explícito: simplicidade pra non-dev vs
      cerimônia obrigatória pra correctness técnica

### Gap 17 — Cenário E3: Escalabilidade de feature visualmente complexa

**Severidade:** média. Features grandes (onboarding com 12 telas + 8 ramos
condicionais) batem em vários gates de threshold do planning-conductor.
Caso comum (todo app tem onboarding ou wizard multi-step).

**Origem:** ambiguity-map declara "27 nós + threshold 8 unresolved → refuse"
em planning-conductor §Phase 2 — pode bater em features grandes;
state-matrix com 8 ramos pode não ser modelado first-class no schema;
navigation-spec.yaml conditional branching pode não ser first-class;
screen-analysis-agent context pack infla com 12+ mockups; task-breakdown
12 tasks UI tecnicamente viável mas frágil em deps cross-screen.

**Remediação proposta (v1.1):**

- [ ] Ambiguity-map threshold adaptive: feature com N telas > 5 expandir
      threshold pra 8 × log(N) ou similar (vs 8 fixo). Documentar
      heurística
- [ ] `navigation-spec.yaml` schema first-class para conditional branching:
      ```yaml
      conditional-routes:
        - when: user.is-new
          to: screen-3
          else: screen-5
      ```
- [ ] screen-analysis-agent pipelining: processa mockups em batches
      paralelos quando N > 5, evitando context pack > 100kb
- [ ] task-breakdown ganha `screen-group` opcional (paralelo ao
      `release-group` do Gap 7) — agrupa tasks por tela
- [ ] Validator advisory: feature com >10 telas → sugere split
      ("onboarding tem 12 telas — considere split?"). Não bloqueia, só
      sugere via 3-caminhos discipline (07-discipline §1)

### Gap 18 — Detecção de helpers/extensions existentes no tech-spec ✅ resolvido 2026-05-30

**Severidade:** média. Brownfield (MeoBonsai, outros projetos modularizando)
acumula dezenas de extensions em `shared/core/util/`, `shared/feature/*/util/`.
Tech-spec-agent não detectava reuso — propunha helpers novos como se não
houvesse prior art, criando duplicação latente.

**Origem:** prompt do `tech-spec-agent` explicitamente proíbe consultar
codebase graph live ("never fetch from network, codebase graph, or Jira") —
restrição é deliberada (determinismo + reprodutibilidade do dispatch). Sem
mecanismo de prefetch, agente não tinha acesso ao inventário de helpers
existentes.

**Solução aplicada (não criar inventário novo, usar graph existente):**

- [x] **Q11 — `reusable-helpers`** adicionada ao catálogo canônico
      (`docs/schemas/graph.md`). Query lista funções `kind='fun'` no módulo
      `shared` cujos signatures referenciam entity types da feature OU vivem
      em paths de utility (`/util/`, `/extensions/`, `/core/`).
- [x] **`engine/graph/queries.find_reusable_helpers()`** implementa Q11
      programaticamente. Parâmetro `entity_types` extraído pelo conductor
      de `data-contract-spec.yaml`. ~70 LOC.
- [x] **`forge graph` menu** ganhou opção 11 (`reusable-helpers`) —
      interactive prompt pra tipos de entidade.
- [x] **`planning-conductor.md` Phase 4.5** (entre Wave B e Wave C):
      conductor parseia entities do data-contract-spec, roda Q11, persiste
      resultado em `.claude/memory/L1/{slug}/existing-helpers.yaml`. Empty
      result é normal — sempre escreve arquivo.
- [x] **`tech-spec-agent.md` context pack** atualizado para incluir
      `existing-helpers.yaml`. Phase 5 (CFR scan) reescrita em 2 steps:
      Step 1 checa reuse contra existing-helpers antes de Step 2 propor
      novos.
- [x] **`tech-spec.template.md` §14** splittado em 3 sub-seções: `14.1
      Reuse existing` (omitida em greenfield), `14.2 Propose new — qualifies`,
      `14.3 Propose new — defer to rule-of-three`. Output JSON do agent
      ganhou 3 counters distintos.

**Princípio preservado:** tech-spec-agent continua sem acesso live ao graph.
Conductor pré-computa via Q11 e injeta resultado no context pack
(deterministic-context discipline mantida — agente recebe sempre o mesmo
input dado o mesmo estado de repo).

**Arquivos modificados:**

- `docs/schemas/graph.md` — Q11 canonical query
- `agents/planning-conductor.md` — Phase 4.5
- `agents/tech-spec-agent.md` — context pack + Phase 5 (2 steps) + output JSON
- `templates/tech-spec.template.md` — §14 splittado em 14.1/14.2/14.3
- `engine/graph/queries.py` — `find_reusable_helpers()`
- `engine/graph_cli.py` — opção 11 no menu interativo

**Validação pendente:**

- [ ] Rodar `pytest tests/unit/test_graph_queries.py` (se existir cobertura
      pra queries.py) — atualmente sem teste pra `find_reusable_helpers`
- [ ] Smoke test: rodar `forge graph` → opção 11 num projeto com graph
      construído (precisa MeoBonsai com `.claude/graph.db`)
- [ ] Smoke test: rodar `forge plan` numa feature de teste e verificar
      que `existing-helpers.yaml` é escrito após Wave B

**Expansão 2026-06-01 — init-time + incremental + 6 categorias** ✅

A solução original cobria APENAS o momento de planejar uma feature
(prefetch de helpers via Q11 antes de tech-spec). Não cobria **duplicações
já existentes no codebase** nem **edits que introduzem novas duplicações**.

Expansão completa shipada em 2026-06-01 — feature-forge agora "nasce com
inteligência": primeira vez que vê o projeto (`forge init` Step 11.5), já
detecta o backlog acumulado.

- [x] **6 categorias de finding** (`engine/graph/duplicates.py`):
  - `duplicate-within-module` (Kotlin extension repetida em 1 módulo, conf 0.95)
  - `duplicate-cross-module` (sibling modules → smallest-common-ancestor
    via parsed Gradle dependency closure, conf 0.85)
  - `redundant-platform-specific` (Android Kotlin idêntico a
    `commonMain` shared, conf 0.90)
  - `near-duplicate` (mesma signature, body_hash diferente — drift signal,
    conf 0.40, manual review demanded)
  - `kmp-migration-candidate` (Swift extension ↔ Kotlin shared com token
    Jaccard ≥0.4, conf 0.50–0.75 escalando com similarity)
  - `duplicate-ts-helper` (TypeScript top-level duplicado num módulo,
    conf 0.95)
- [x] **Schema v2** (`engine/utils/sqlite_io.py`): colunas
  `files.source_set` + `symbols.{receiver_type, body_hash, body_tokens,
  modifiers}`, tabelas `module_deps` + `reuse_findings` +
  `reuse_finding_locations`.
- [x] **Parser overhaul** (Kotlin / Swift / TS): visibility agora
  persistida (era hardcoded "public"), signature normalizada, body
  extraction brace-aware em `engine/graph/_body_text.py`, body_hash
  (SHA-1[:16]) + body_tokens (JSON) para Jaccard cross-language. Swift
  two-pass captura receiver de `extension Type { func ... }`.
- [x] **Module inference** (`engine/graph/gradle_modules.py` +
  `gradle_deps.py`): settings.gradle parsing com longest-prefix match
  (suporta `:shared:feature:auth`, `:androidApp:feature:bonsai`, etc.) +
  build.gradle parsing → transitive closure → smallest-common-ancestor
  para `duplicate-cross-module` target inference.
- [x] **Q11 backward-compat**: filtro `f.module = 'shared'` → `LIKE
  'shared:%'` para multi-módulo shared.
- [x] **Q12–Q17 queries** (`engine/graph/queries.py`) + opções 12–17 no
  menu `forge graph` + `r` (combined view).
- [x] **Init Step 11.5** (`engine/init.py`):
  `queue_proposals_from_table` após graph build → 6 novos `kind` em
  `proposed-evolutions.yaml` reviewable via `forge evolve`.
- [x] **Init Step 11.6** (`engine/init.py`): escreve
  `.claude/hooks/post-edit-detect-duplications.sh` (opt-in via
  `.claude/settings.local.json`).
- [x] **Apply integration com Gap 2** (`engine/graph/reuse_apply.py`):
  6 novos `kind` no `_VALID_KINDS` do distiller. Apply renderiza
  `templates/feature-intake-refactor.template.md` + escreve L1
  `status.json` com `subtype="refactor"` → `forge plan {slug}` detecta e
  pula Wave A discovery (Gap 2 integration nativa).
- [x] **Reconfigure rebuild hook**: `_handle_graph` re-queue após
  rebuild — idempotente por fingerprint.
- [x] **Doctor** (`engine/doctor.py`): `_check_reuse_findings`
  aggregated por categoria.
- [x] **Incremental detection** (`engine/graph/incremental.py`):
  `detect_after_update` re-parsa arquivos editados, roda mini-detection
  e retorna findings novos. Subcomando `forge graph detect-incremental
  <file>` non-interactive para hook entrypoint.
- [x] **Tests**: 20 unit tests novos em
  `tests/unit/test_reuse_intelligence.py` (body extraction, gradle
  parsing, parser fields, end-to-end pipeline, apply + status.json).
  **367 passed / 0 regressões.**
- [x] **Smoke test MeoBonsai**: detecta
  `FirebaseAnalytics.logEventSafely` como `duplicate-cross-module`
  através de `:shared:feature:home/auth/bonsai`, suggested target via
  closure = `:shared:resources/.../util/` (493 files, 3528 symbols,
  10.3s).
- [x] **Schema docs**: `docs/schemas/graph.md` +
  `docs/schemas/proposed-evolutions.md` ganham seção "Reuse Intelligence
  (schema v2)".

**Princípios preservados**:
- Discipline §4 (deterministic context) — apply NUNCA mexe em código
  diretamente; só materializa intake stub e delega refactor flow.
- Discipline §5 (rejection veto) — fingerprints SHA-256 64-char
  compatíveis com `rejected-evolutions.yaml`. Rejeitar uma vez
  persiste.
- Decision 9 + 10 (12 verbos, zero flags) — `forge graph detect-incremental`
  é subcomando (positional argv), não flag.

**Conhecidos limites v1.1**:
- `kmp-migration-candidate` confidence é shallow (token Jaccard, não AST
  semântico). False positives possíveis — confidence baixa força revisão
  manual; rejection veto persiste decisão.
- Hook script é escrito no init, mas wiring em
  `.claude/settings.local.json` é manual (opt-in por design — não queremos
  surpreender o usuário).
- Gradle dependency parsing cobre `implementation(project(...))` e
  variantes comuns. DSL Kotlin avançado ou `includeBuild` exigem extensão
  futura.

### Gaps pós-rules-system (2026-06-01)

Itens emergidos durante a instalação do Claude Code rules system (CLAUDE.md
+ `.claude/rules/` + 4 hooks + 36 integration tests). Não bloqueiam o
rules system v1, mas merecem cobertura futura.

- **forge audit-rules** — comando que audita git log + `.claude/state/load-bearing-edits.jsonl` pra verificar conformidade com Mandamento 0 (orchestrator não escreveu direto) + ceremony de "Revisita decisão N" + doc-sync per commit. Mencionado em `.claude/rules/README.md` §Auditoria. Target v1.2+.
- **test_build_full_creates_meta_schema_version** — teste assume `meta.schema_version == "1"` mas `engine/utils/sqlite_io.py:20` declara `SCHEMA_VERSION = "2"` desde commit `65c358c` (reuse-intelligence schema bump). Fix: atualizar test pra ler `sqlite_io.SCHEMA_VERSION` em vez de hardcoded "1". Pré-existente, não causado pelo rules system. Quick fix; pode ser próximo item de manutenção.
- **Hooks Claude Code — observabilidade em subagente** — doc oficial (https://code.claude.com/docs/en/hooks) confirma que `PreToolUse`/`PostToolUse` disparam em subagentes; o JSON de input inclui `agent_id` e `agent_type` (presentes só em subagent context). Smoke 2026-06-01 confirmou via side-effect (`load-bearing-edits.jsonl` gravado de dentro de subagente) que **PreToolUse de fato dispara**; contudo investigação subsequente observou que a entrega ao hook script é **inconsistente em prática** — uma segunda passada de Edit no mesmo subagente não produziu side-effect nem entrada no debug log instrumentado, indicando que nem toda tool call de subagente é encaminhada aos hooks. Adicionalmente: stderr do hook não aparece de forma confiável no transcript do subagente mesmo quando o hook executou. Gaps menores pra revisão futura: (a) próximas revisões dos scripts devem logar `agent_id` no audit JSON quando presente, pra facilitar correlação com runs específicos; (b) ferramentas de audit do projeto devem priorizar side-effect persistente sobre stderr capture; (c) anotar reprodutor mínimo da inconsistência observada e considerar abrir bug-report upstream pra Anthropic se reproduzir consistentemente. Target v1.2+ (não bloqueia operação — Mandamento 0 segura o orchestrator via CLAUDE.md mesmo se hooks falharem silentemente).

### Resumo da fila pós-stress-test (cumulativo)

Total: 18 gaps mapeados a partir de 20 cenários analisados (3 rounds).
**4 resolvidos** (Gap 18 em 2026-05-30 manhã; Gap 2 em 2026-05-30 tarde —
refactor only, spike+chore stubbed; Gap 8 em 2026-05-30 noite — schema +
engine + manual unblock, MCP polling stubbed; Gap 1 em 2026-05-30 noite — bugfix
subtype completo, A2 small-feature explicit non-goal) · 14 pendentes.

| Gap | Cenário(s) | Severidade | Esforço estimado |
|---|---|---|---|
| ~~1~~ | ~~A1 — Hotfix urgente + A2 small feature~~ | ~~Média~~ | ~~1 card `quick-track` + 2 patches em prompts~~ — bugfix subtype ship 2026-05-30; A2 explicit non-goal (small features = product subtype) |
| ~~2~~ | ~~A3 + A4 — Non-product feature (spike/refactor/chore)~~ | ~~Alta~~ | ~~Novo guarda-chuva de estado + subdir + UX + 1 validator~~ — refactor ship 2026-05-30; spike+chore stubbed |
| 3 | B1 — Migração grande | Média | 1 card + schema upgrade + retrospective patch |
| 4 | C1 — PRD muda mid-implement | Baixa | 1 validator + doc + finding type |
| 5 | D2 — Stack fora do catálogo | Alta | Overlay mechanism + capability ext + 4 menu options |
| 6 | E1 — Multi-dev | — (v1.1+) | Schema upgrades + ADR |
| 7 | B2 — Feature em múltiplos releases | Média | Estado intermediário + release-group + status patch |
| ~~8~~ | ~~B3 — Dependência externa~~ | ~~Média-alta~~ | ~~Estado novo + schema task-contract + MCP polling~~ — schema + engine + manual unblock ship 2026-05-30; MCP polling stubbed para v1.1+ |
| 9 | C2 — Plataforma nova mid-projeto | Alta | Cards multi-target + inventory schema + extension feature UX |
| 10 | D3 — Monorepo cross-project UX | Média | Status agregado + shared-memory opt-in + cross-checks |
| 11 | E4 — Compliance regulatório | Média-específica | 3 cards regulatórios + scope-tags + WORM mode |
| 12 | B4 — A/B test (2 variantes) | Média-específica | Card experimentation + analytics dimensions + estado `experiment-running` |
| 13 | C4 — Forge sobe de versão | Alta na 1ª transição | reconfigure UX + pre-flight + atomic transaction |
| 14 | D1 — Preset coverage (web/single-platform) | Alta-específica | 5 cards web + 4 presets ativados + inventory parsers |
| 15 | D4 — Brownfield vocabulary | Média | conventions.vocabulary + prompt substitution + validators |
| 16 | E2 — Persona modes (non-dev) | Média | interlocutor-persona config + prompt filtering + auto-escalation |
| 17 | E3 — Escala features visualmente complexas | Média | Threshold adaptive + conditional-routes schema + screen-group + pipelining |

Nenhum desses gaps demanda revisitar as 27 decisões locked. Todos cabem dentro
das disciplinas universais (07-discipline §1-7) e do command surface
(06-command-surface, 12 verbos, zero flags).

### Padrões cruzados — gaps que se reforçam mutuamente

Análise pós-stress-test revelou que vários gaps **compartilham mecânicas** —
atacar uma feature-base destrava múltiplos gaps:

| Mecânica base | Destrava |
|---|---|
| `status.json` schema upgrade (`active-tasks: [list]` + `state: blocked-on-external`) | Gaps 3, 6, 7, 8 |
| Card local overlay (`.claude/cards/local/` + capability-labels.local) | Gaps 5, 9, 14 |
| Persona/vocabulary substitution em agent prompts | Gaps 15, 16 |
| Retrospective incremental disparado por eventos (não só "última task") | Gaps 3, 7 |
| Validators advisory com 3-caminhos (vs hard-fail) | Gaps 4, 17 |
| Non-product feature track | Gaps 1 (bugfix) + 2 (spike + refactor + chore) |

### Priorização sugerida (ordem de ataque)

Considerando severidade × esforço × multiplicador de destrancamento:

1. **`status.json` + lifecycle states upgrade** — destrava 4 gaps (3, 6, 7, 8)
   com 1 schema change + migrations
2. **Card local overlay** — destrava 3 gaps grandes (5, 9, 14), atende
   portabilidade real
3. **Non-product feature track (Gap 2)** — gap fundamental, alta severidade,
   custo médio
4. **Persona modes + vocabulary (Gaps 15+16)** — atende uso real por
   non-devs e brownfield, custo médio
5. **Migration UX (Gap 13)** — antes do primeiro v1.0 → v1.1 real

Gaps remanescentes (1, 4, 10, 11, 12, 17) podem ser endereçados conforme
demanda real surgir.

### Conclusão do stress-test

20 cenários analisados em 3 rounds. **18 gaps identificados**, dos quais
**4 foram resolvidos** dentro do ciclo v1.0+ (Gaps 1, 2, 8, 18) e
**11 permanecem acionáveis pra v1.1** (não-out-of-scope, não-bem-coberto-já).

Resultado positivo do stress-test: **as 27 decisões locked permanecem
intactas**. Nenhum cenário forçou revisitar princípios ou disciplinas
universais. Forge tem espinha dorsal sólida — os gaps são **superfície de
cobertura**, não fundação.

Resultado a observar: forge v1 é **excelente pro happy path** (feature de
produto Android+iOS+KMP com backend Firebase/REST, 1 dev, 5-10 tasks). Fora
do happy path, há cobertura parcial — o roadmap v1.1+ deve preencher essa
superfície sistematicamente.

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
