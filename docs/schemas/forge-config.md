# Schema — `forge-config.yaml`

The canonical file that `forge init` creates, `forge reconfigure` modifies,
and all sub-agents read. Anchor for the entire skill state.

## Schema + example (annotated)

```yaml
# feature-forge / forge-config.yaml
# ──────────────────────────────────────────────────────────────────────────
# Schema version: 1.3
# Location:       .claude/forge/forge-config.yaml
#                 (em monorepo: .claude/forge/subprojects/{name}/forge-config.yaml)
# Owner:          forge init (creates) · forge reconfigure (modifies) ·
#                 planning-conductor (reads on entry) · all sub-agents (read)
# Git policy:     COMMIT este arquivo. NÃO commitar: forge/state/, graph.db
# ──────────────────────────────────────────────────────────────────────────

schema-version: 1.3


# ── IDENTITY ──────────────────────────────────────────────────────────────
identity:
  project-name:   MeoBonsai                # human-readable, livre
  project-slug:   meobonsai                 # filesystem-safe, [a-z0-9-]+
  preset:         kmp-mobile-firebase       # canonical preset chosen at init
                                            # one of: kmp-mobile, kmp-mobile-firebase,
                                            # android-only, android-only-firebase,
                                            # ios-only, ios-only-firebase, web, kmp-fullstack
  created-at:     2026-05-28T14:33:11Z
  last-reconfigure: 2026-05-28T14:33:11Z
  forge-version:  1.0.0                     # version of feature-forge that wrote this


# ── PLATFORMS ─────────────────────────────────────────────────────────────
platforms:
  active: [android, ios, kmp, web]          # any subset of these 4
  primary-language-per-platform:
    android: kotlin
    ios:     swift
    kmp:     kotlin
    web:     typescript


# ── CARDS — composition units snapshotted locally ─────────────────────────
cards:
  source:        standalone-repo            # one of: standalone-repo, embedded
  source-url:    thgMatajs/feature-forge    # null if embedded
  snapshot-root: .claude/cards/             # where snapshots live in this repo
  
  active:
    - name: kotlin-language
      version: 1.0.0
      sha256:  e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
      installed-at: 2026-05-28T14:33:11Z
    - name: kmp-shared
      version: 1.0.0
      sha256:  ...
    - name: compose-screens
      version: 1.0.0
      sha256:  ...
    - name: swiftui-screens
      version: 1.0.0
      sha256:  ...
    - name: koin-annotations
      version: 1.0.0
      sha256:  ...
    - name: skie-bridge
      version: 1.0.0
      sha256:  ...
    - name: nav3
      version: 1.0.0
      sha256:  ...
    - name: swiftui-navigation
      version: 1.0.0
      sha256:  ...
    - name: firebase-auth
      version: 1.0.0
      sha256:  ...
    - name: firebase-firestore
      version: 1.0.0
      sha256:  ...
    - name: firebase-storage
      version: 1.0.0
      sha256:  ...
    - name: crashlytics
      version: 1.0.0
      sha256:  ...


# ── PATHS — where things live in THIS project ─────────────────────────────
paths:
  # internal to feature-forge state
  features-package-root: docs/forge-specs/features
  inventory-root:        .claude/inventory
  memory-root:           .claude/memory
  graph-path:            .claude/graph.db
  hooks-root:            .claude/hooks
  
  # auto-detected from project on init; user can override on reconfigure
  feature-roots:
    android: androidApp/feature
    ios:     iosApp/iosApp/Features
    shared:  shared/feature
    web:     webApp/src/features
  
  test-roots:
    android: androidApp/feature/**/src/test
    ios:     iosApp/iosAppTests
    shared:  shared/feature/**/src/commonTest
    web:     webApp/src/__tests__
  
  design-system:
    android: androidApp/core/designsystem/src/main/kotlin/{path}/designsystem
    ios:     iosApp/iosApp/DesignSystem
    web:     webApp/src/shared/components


# ── CONVENTIONS — extracted by init from existing features ────────────────
conventions:
  folder-layout:
    android: "{screen}Screen.kt + {Screen}Content.kt + {Screen}Components.kt"
    ios:     "{Screen}ScreenView.swift + {Screen}ScreenContentView.swift + {Screen}Components.swift"
  
  state-pattern:   stateui              # one of: stateui, stateflow-pure, custom-sealed
  di-pattern:      koin-annotations     # one of: koin-annotations, koin-dsl, hilt, manual
  
  test-pattern:
    framework-android: junit5
    framework-shared:  kotlin-test
    framework-ios:     swift-testing
    flow-assertion:    turbine
    type-assertion:    assertIs
  
  i18n:
    source-path:          shared/resources/i18n
    generation-script:    scripts/i18n/generate.py
    verification-script:  scripts/i18n/verify.py
    locales:              [pt-BR, en-US, es-ES]
    naming-pattern:       "screen.element.action"   # detected
  
  branch:
    pattern:           "feature/{slug}"
    requires-ticket:   true             # if ticketing.provider != none
    convention-skill:  create-branch    # external skill if available


# ── BACKEND (multi-axis) — what features write to ────────────────────────
# Since Phase B (DET-6), `backend:` é mapa de 8 eixos canônicos
# (data / auth / observability / analytics / storage / persistence /
# notifications / flags), cada um mapa de <platform> → cell-object | null.
#
# Cell schema:
#   { card: <card-identity-name>, status: active|migrating-to|deprecated,
#     migrating-to: <card-identity-name>  (REQUIRED quando status=migrating-to,
#                                         MUST be absent caso contrário) }
#
# `null` = opt-out explícito (essa plataforma não tem provedor para esse
# eixo neste projeto; ex.: iOS consome via KMP shared, ou app local-only
# sem analytics).
#
# Plataformas vêm de `platforms.active` (não muda).
#
# Schema completo + naming rationale (`auth` vs `identity`) + detection
# composer + starter bundles: ver `docs/schemas/backend-axes.md`.
#
# Campos legacy removidos em Phase B (clean break, pre-production):
#   - `identity.backend-choice` (escolha monolítica)
#   - `backend.provider` + sub-blocos provider-específicos
#     (`backend.firebase:`, `backend.rest:`, ...)
backend:
  data:
    android:
      card: retrofit-client
      status: migrating-to
      migrating-to: ktor-client
    kmp:
      card: ktor-client
      status: active
    ios: null
  auth:
    android: { card: firebase-auth, status: active }
    ios:     { card: firebase-auth, status: active }
    kmp:     { card: firebase-auth, status: active }
  observability:
    android: { card: firebase-crashlytics, status: active }
    ios:     { card: firebase-crashlytics, status: active }
    kmp: null
  analytics:
    android: { card: firebase-analytics, status: active }
    ios:     { card: firebase-analytics, status: active }
    kmp: null
  storage:
    android: { card: firebase-storage, status: active }
    ios:     { card: firebase-storage, status: active }
    kmp: null
  persistence:
    android: { card: room-database, status: active }
    ios: null
    kmp:     { card: sqldelight, status: active }
  notifications:
    android: { card: fcm, status: active }
    ios:     { card: fcm, status: active }
    kmp: null
  flags:
    android: { card: firebase-remote-config, status: active }
    ios:     { card: firebase-remote-config, status: active }
    kmp: null

  e2e-required: true                    # requires backend_e2e in test-strategy.yaml


# ── TICKETING — external source of feature specs ──────────────────────────
ticketing:
  provider:          jira               # one of: jira, linear, github-issues, clickup, notion, none
  workspace:         inchurch.atlassian.net
  default-project:   BONSAI
  mcp-tool-prefix:   mcp__claude_ai_Atlassian
  
  fields-of-interest:
    - summary
    - description
    - acceptance_criteria
    - attachments
    - sprint
    - fix_versions
    - linked_tickets
  
  post-back:
    on-readiness-ready: true            # post comment when forge plan completes
    on-feature-done:    true            # update status when forge implement done
    require-confirmation: true          # ask user before posting


# ── WORKFLOW — strictness and gates ───────────────────────────────────────
workflow:
  readiness-strictness: strict          # one of: strict (14 docs), standard (10), lean (5)
  required-artifacts:   auto            # auto = derived from strictness; or explicit list

  # Strictness matrix — which artifacts are required per level
  # Used by readiness-reviewer; do NOT modify without versioning.
  strictness-matrix:
    strict:        # all 14
      - feature-intake.md
      - feature-prd.md
      - screen-analysis.md
      - bdd.md
      - bdd.json
      - ui-state-spec.yaml
      - navigation-spec.yaml
      - data-contract-spec.yaml
      - analytics-spec.yaml
      - test-strategy.yaml
      - tech-spec.md
      - task-breakdown.yaml
      - tasks/*.yaml                  # at least one
      - implementation-readiness-review.md
    standard:      # 10 essentials — drops evals + bdd.json + analytics + screen-analysis + ui-state
      - feature-intake.md
      - feature-prd.md
      - bdd.md
      - navigation-spec.yaml
      - data-contract-spec.yaml
      - test-strategy.yaml
      - tech-spec.md
      - task-breakdown.yaml
      - tasks/*.yaml
      - implementation-readiness-review.md
    lean:          # 5 minimum — intake/PRD/BDD/breakdown/tasks
      - feature-intake.md
      - feature-prd.md
      - bdd.md
      - task-breakdown.yaml
      - tasks/*.yaml
    # plan-feature-handoff.json + open-questions.yaml are required at ALL levels
    always-required:
      - plan-feature-handoff.json
      - open-questions.yaml

  pre-commit-review:
    enabled:        true
    blocking:       true                # commit hook blocks on review failure
    allow-override: false               # forge undo is the recovery, not --force
  
  hard-gates:
    - readiness-must-be-ready
    - no-files-outside-allowed-files
    - validations-must-pass
    - completion-evidence-required
    - no-invented-behavior

  # Validator scripts — canonical paths (per-project snapshot)
  validators-root: .claude/skills/feature-forge/validators/
  validators-canonical:
    - validate_feature_package.py
    - validate_readiness.py
    - validate_task_contract.py
    - validate_data_contract.py
    - validate_screen_analysis.py
    - validate_backend_e2e.py
    - validate_workflow_config.py
    - validate_card_yaml.py
    - validate_inventory.py
    - validate_memory.py
    - check_no_invented_behavior.py
    - check_files_in_allowed_files.py

  task-discipline:
    require-plan-mode-before-apply:    true
    require-verify-task-before-commit: true
    max-retry-on-validator-fail:       3


# ── PERSONA — voice of the super-agent ────────────────────────────────────
persona:
  name:                       mentor-calmo
  primary-language:           pt-BR
  language-mirroring:         true       # mirror user's language when different
  drill-down-aggressiveness:  medium     # low (accept first), medium (drill vague), high (drill medium-confidence too)
  explain-why-each-question:  true
  closing-style:              didactic   # silent | brief | didactic | expressive


# ── MEMORY policy ─────────────────────────────────────────────────────────
memory:
  layers-enabled: [L1, L2, L3]          # L4 (skill-global), L5 (per-card) added when present
  
  L1-per-feature:
    location:      .claude/forge/state/lifecycle/{feature-slug}/
    retention:     until-feature-archived
    max-size-mb:   2
  
  L2-project:
    location:      .claude/memory/L2-project.yaml
    retention:     forever
    max-size-mb:   0.5
    distillation-trigger: file-size-exceeds-max
  
  L3-user-global:
    location:      ~/.claude/projects/{project-hash}/memory/
    link-policy:   read-only            # forge never writes here
  
  promotion-policy:
    L1-to-L2-after-feature-done: ask    # one of: never, ask, auto-after-confirmation
    L2-to-L4-after-N-projects:   3      # threshold for suggesting cross-project lift


# ── GRAPH — codebase knowledge ────────────────────────────────────────────
graph:
  backend:         sqlite                # one of: sqlite (v1 default), kuzu, duckdb
  location:        .claude/graph.db
  rebuild-policy:  incremental           # one of: incremental, on-init, manual
  rebuild-hook:    .claude/hooks/post-edit-codebase-graph.sh
  
  tables-enabled:
    - files
    - symbols
    - imports
    - features
    - screens
    - ds_components
    - ds_usage
    - i18n_keys
    - routes
    - di_graph
    - tests


# ── EXTERNAL DOCS — version-aware library knowledge ───────────────────────
external-docs:
  primary-provider:  context7            # one of: context7, websearch, none
  mcp-tool-prefix:   mcp__context7
  cache-ttl-days:
    library-docs:        7
    framework-patterns:  14
    convention-patterns: 30
  privacy-mode:      false               # if true, never sends names/code externally


# ── HOOKS — file-watcher style automation ─────────────────────────────────
hooks:
  active:
    - name:    post-edit-codebase-graph
      file:    .claude/hooks/post-edit-codebase-graph.sh
      events:  [post-edit]
      enabled: true
    - name:    pre-commit-feature-forge
      file:    .claude/hooks/pre-commit-feature-forge.sh
      events:  [pre-commit]
      enabled: true
    - name:    post-subagent-validate
      file:    .claude/hooks/post-subagent-validate.sh
      events:  [post-subagent]
      enabled: true


# ── DOCTOR — health check state ───────────────────────────────────────────
doctor:
  last-run:    null
  last-status: null                      # null | passing | failing
  scheduled-checks:
    - cards-snapshot-integrity           # sha256 of each card matches recorded
    - paths-exist
    - memory-writable
    - graph-readable
    - ticketing-mcp-reachable
    - i18n-script-runnable
    - hooks-executable
    - cards-no-conflict                  # active cards don't conflict (per card schema)
```

## Top-level field reference

| Block | Required | Mutable by | Notes |
|---|---|---|---|
| `schema-version` | yes | migration tool only | Locked at 1 in v1. Changes require `forge raw migrator-{from-version}-to-{to-version}`. |
| `identity` | yes | reconfigure | `project-slug` is immutable after init (rename breaks paths). |
| `platforms` | yes | reconfigure | Changing this = changing preset → dedicated command. |
| `cards` | yes | reconfigure (menu: adicionar/remover/atualizar card) | sha256 is integrity check. |
| `paths` | yes | reconfigure | Auto-detect at init; user can override. |
| `conventions` | yes | re-extract during reconfigure | Init extracts from existing features; greenfield = defaults. |
| `backend` | yes | reconfigure | Multi-axis platform-keyed (8 eixos × N plataformas → cell\|null). Ver [`backend-axes.md`](backend-axes.md) e [`card.md § Backend axes`](card.md). |
| `ticketing` | no | reconfigure | `provider: none` if features live only in repo. |
| `workflow` | yes | reconfigure | Strictness affects `validate_readiness.py`. |
| `persona` | yes | reconfigure | Changing this affects tone of ALL prompts. |
| `memory` | yes | rarely | Policy — doesn't change behavior if well-defaulted. |
| `graph` | yes | only `forge raw migrator-{from-version}-to-{to-version}` | Changing backend = forced rebuild. |
| `external-docs` | no | reconfigure | `privacy-mode: true` for confidential repos. |
| `hooks` | no | reconfigure | List of active hooks. |
| `doctor` | yes | written by `forge doctor` | State of last health check. |

## Validation rules enforced by `forge doctor`

```text
RULE-001  schema-version must be in [1, 1.3]
RULE-002  identity.project-slug must match [a-z0-9-]+ regex
RULE-003  identity.preset must reference a known preset definition
RULE-004  platforms.active must be non-empty and ⊆ {android, ios, kmp, web}
RULE-005  every card in cards.active must exist at cards.snapshot-root/{name}/
RULE-006  every card's recorded sha256 must match disk
RULE-007  cards must satisfy each other's requires/conflicts-with (per card schema)
RULE-008  paths.* must point to existing directories (warn, not block, if optional)
RULE-009  conventions must be present and non-null in all sub-keys
RULE-010  (reservado — antes `backend.provider`; removido em Phase B / DET-6.
          Validação do bloco `backend:` multi-axis migrou para RULE-019..024
          abaixo; ver `backend-axes.md` §"Validação enforçada" como fonte
          canônica.)
RULE-011  (reservado — antes `backend.<provider>` sub-bloco; removido em
          Phase B / DET-6 junto com RULE-010. Ver RULE-019..024 abaixo.)
RULE-012  if ticketing.provider != none, mcp-tool-prefix must be a callable MCP
RULE-013  workflow.readiness-strictness ∈ {strict, standard, lean}
RULE-014  persona.name must reference an installed persona spec
RULE-015  memory.*.location must be writable
RULE-016  graph.location must exist or be createable; backend must be supported
RULE-017  every hook in hooks.active must exist and be executable
RULE-018  operations that mutate cards (all routed through `forge reconfigure` — menu opções "adicionar card", "remover card", "atualizar card do canonical") must verify no L1 feature has state in {planning, implementing, verifying}
RULE-019  backend.<axis> ∈ {data, auth, observability, analytics, storage,
          persistence, notifications, flags}
          (canônico em `backend-axes.md`; aplicado pela
          `validate_workflow_config.py` ao bloco `backend:`)
RULE-020  backend.<axis>.<platform> ∈ platforms.active OR é `null`
RULE-021  cell.card (quando cell != null) deve referenciar card em cards/
RULE-022  cell.status ∈ {active, migrating-to, deprecated}
RULE-023  cell.migrating-to REQUIRED quando status=migrating-to;
          MUST be absent caso contrário
RULE-024  cell.migrating-to (quando presente) deve referenciar card em cards/
```

Each failure has code + dedicated message. `forge doctor` returns 0 if all
pass, 1 if warn, 2 if block.

## Schema versioning

```text
v1     2026-05-28  initial release (.claude/workflow-config.yaml)
v1.3   2026-06-17  v1.3 pilot-ready: file moved to .claude/forge/forge-config.yaml;
                   clean-break (no migrator — pre-production status, see 04-pending.md)
v2 (future)    when breaking change needed

Migration:
  forge raw migrator-1-to-2

`raw` is the documented escape hatch for migrations — they intentionally do
not have a cinematic UX. See `docs/design/06-command-surface.md` for the full
mapping rationale.

Forge always reads `schema-version:` and:
  - if equal: proceed
  - if less than supported: offer to run `forge raw migrator-{from}-to-{to}`
  - if greater than supported: ask for feature-forge update
```

Canonical source holds **migrators** between versions. Each migrator is an
idempotent Python script that transforms config v(n) → v(n+1).

## `cc-gate` (opt-in, v1.2-dev+)

Configura o validator `check_cyclomatic_complexity`. Bloco opcional — sem
ele, o gate usa defaults built-in (kotlin=10, swift=10, ts=15, python=10).
Resolução final de threshold respeita a precedência (mais específico vence):
**card `cc-gate-override` > este bloco > defaults built-in**.

```yaml
cc-gate:
  enabled: true             # default true; false desliga o validator
                            # (warn, não fail — útil em projeto migrando)
  kotlin: 10                # threshold absoluto por linguagem (int > 0)
  swift: 10
  ts: 15                    # TS tipicamente tolera CC mais alto por causa
                            # de pattern matching exaustivo / state machines
  python: 10
  ignore-paths:             # lista de regexes Python (re.search)
    - "src/test/.*"         # aplicadas após filtro de extensão
    - ".*\\.generated\\..*" # arquivos gerados — CC alto é ruído
    - "build/.*"
    - "node_modules/.*"
```

### Semântica de campos

| Campo | Tipo | Default | Notas |
|---|---|---|---|
| `enabled` | bool | `true` | `false` → validator emite warn, não bloqueia |
| `kotlin` | int > 0 | 10 | passado via CLI args pro Detekt |
| `swift` | int > 0 | 10 | passado via CLI args pro SwiftLint |
| `ts` | int > 0 | 15 | passado via `--rule 'complexity: [error, {max: N}]'` pro eslint |
| `python` | int > 0 | 10 | Radon output comparado em Python depois |
| `ignore-paths` | lista regex | `[]` | tests/, generated, build/ ficam por conta do projeto declarar |

### Regras de validação

- Threshold ≤ 0 → validator interpreta como **degraded** (config errada,
  emite warn agrupado no fim do cascade — não bloqueia, mas sinaliza).
- `enabled: false` desliga totalmente — não invoca tools nativas, mas
  `forge doctor` ainda reporta status das tools no categoria `cc-gate-tools`.
- `ignore-paths` aceita regex Python; teste com `re.search` (não anchored).
  Match em qualquer arquivo do diff → pula este arquivo do gate.

### Precedência completa

```
1. card `cc-gate-override.{language}.threshold`  (mais específico)
2. workflow-config `cc-gate.{language}`
3. DEFAULTS = {kotlin: 10, swift: 10, ts: 15, python: 10}
```

Múltiplos cards ativos com override pra mesma linguagem: **primeiro card
com `threshold` declarado wins** (ordem determinística do listing). Não é
"max" nem "min" — é "primeiro", porque card listing tem semântica de
prioridade declarada pelo usuário. Documentado também em
`docs/schemas/card.md § cc-gate-override`.

## `secrets-gate` (opt-in, v1.2-dev+)

Configura o validator `check_secrets`. Bloco opcional — sem ele, o gate roda
com defaults (habilitado, ignore-paths cobrindo os fixtures do próprio gate).
Diferente do `cc-gate`, secrets é **binário** (detectou = fail) — não tem
threshold numérico, logo nenhuma precedência de card por linguagem.

```yaml
secrets-gate:
  enabled: true
  ignore-paths:
    - "tests/fixtures/secrets/.*"    # próprios fixtures do gate (já default)
    - ".*\\.lock$"                    # lock files — raro ter secret, evita ruído
  per_task:
    tool: gitleaks                    # fast scan no hook de forge implement
  cascade:
    tool: trufflehog
    only_verified: true               # apenas tokens validados ativamente
```

### Semântica de campos

| Campo | Tipo | Default | Notas |
|---|---|---|---|
| `enabled` | bool | `true` | `false` → validator emite warn ("secrets-gate desligado"), não bloqueia — útil em projeto migrando |
| `ignore-paths` | lista regex | `["tests/fixtures/secrets/.*"]` | regexes Python (`re.search`) aplicadas ao path relativo após coletar o staged set; o default é sempre prependado (config-extra estende, não substitui) |
| `per_task.tool` | str | `gitleaks` | tool do hook de `forge implement` (stage="per_task"); fixo em v1.2-dev |
| `cascade.tool` | str | `trufflehog` | tool da cascade de `forge verify` (stage="cascade"); fixo em v1.2-dev |
| `cascade.only_verified` | bool | `true` | `--only-verified` no trufflehog — reporta só tokens confirmados ativos na origem (zero false positives ativos) |

### Semântica de runtime

- **Override por commit body, não por arquivo.** Não há allowlist persistente.
  Pra liberar um finding pontual (test fixture genuíno), adicione ao commit body
  a linha exata `SECRETS-OVERRIDE: <file>:<line> kind=<token-type> — <razão>`.
  O override cobre apenas a tupla `(file, line, kind)` daquele commit; auditável
  via `git log --grep='SECRETS-OVERRIDE'`.
- **Hard-fail policy.** Qualquer secret que sobreviva ao filtro de ignore-paths
  e aos overrides bloqueia (security não tem soft-warn). Decision 23 fail-fast:
  posicionado após `check_cyclomatic_complexity` no cascade — se um gate anterior
  falhar, `check_secrets` nem roda.
- **Tool missing → warn.** Se gitleaks/trufflehog não estiver no PATH, o gate
  emite warn com install hint (não fail — cascade segue alive). `forge doctor`
  reporta status das duas tools na categoria `secrets-tools`.
- **Bypass de emergência.** `NO_SECRETS_GATE=1` pula o gate no per-task hook e
  registra a invocação em `.claude/state/secrets-gate-bypass.jsonl`. Não é o
  caminho normal de override — pra isso existe `SECRETS-OVERRIDE` no commit body.

## qa (since v1.2)

Section opcional. Quando ausente, defaults aplicados (todos os campos
opcionais).

```yaml
qa:
  enabled: true                              # default true. false desabilita o verbo
  auto-run-on-feature-done: false            # default false. true dispara qa pré-retrospective
  sandbox-budget-seconds-total: 60           # budget global por run
  agent-timeout-seconds: 15                  # timeout per-validator no sandbox
  scope-defaults:
    paranoid-max-features: 10                # cap pra paranoid scope
  extensions:
    disabled: []                             # auditor names desabilitados (canon ou local)
  retention-days: 14                         # .planning/qa/<run-id>/ retidos
```

### Field semantics

- `enabled`: bool. `false` desabilita o comando `forge qa` inteiro
  (mensagem mentor calma na invocação: "qa está desabilitado em
  workflow-config; rode `forge reconfigure` se quiser ativar").
- `auto-run-on-feature-done`: bool. Quando true, `engine/implement.py`
  Phase 6 dispara `forge qa scope=feature` antes do retrospective.
  Verdict NÃO bloqueia retrospective (§12.2 do spec).
- `sandbox-budget-seconds-total`: float. Budget total pra Phase 3
  sandbox execution. Default 60s. Quando estoura, fixtures restantes
  marcados `skipped-budget`.
- `agent-timeout-seconds`: float. Timeout per-validator subprocess.
  Default 15s.
- `scope-defaults.paranoid-max-features`: int. Cap pra paranoid scope
  pra evitar explosão. Default 10.
- `extensions.disabled`: list[str]. Nomes de auditores (canon ou local)
  desativados nesta instalação.
- `retention-days`: int. `.planning/qa/<run-id>/` retidos por N dias.
  `forge doctor` reporta runs overdue. Cleanup interativo via
  `forge reconfigure → menu qa → opção 5`. Pattern idêntico a Decisão 24
  (.bak retention).

### Coerência

`forge doctor` reporta warning se `qa.enabled: false` AND
`qa.auto-run-on-feature-done: true` (config inconsistente).

### qa.sensitive-env-grants (opcional, since v1.2 — QA-11)

Lista de env vars sensitive autorizadas pelo user neste projeto. Cards
que declaram `qa-extensions.env-needs` com vars sensitive precisam ter
todas elas presentes nesta lista pra serem ativados sem novo prompt.

```yaml
qa:
  sensitive-env-grants:
    - GITHUB_TOKEN      # granted em init/reconfigure pelo user
    - AWS_TOKEN         # granted via prompt 3-caminhos
```

### Semântica

- Lista vazia ou ausente: zero grants — qualquer card com sensitive
  env-needs dispara prompt na próxima ativação.
- Edição manual da lista é suportada (e auditável via git diff).
  Remoção de var → próxima ativação re-pergunta.
- Adição manual (sem passar pelo prompt) é tecnicamente possível mas
  desencorajada — log da decisão fica fora da auditoria.
- Shape malformado (não-lista) é tratado como `[]` com warning em
  stderr (não raise).

### Não-revoke automático

Quando um card declarando GITHUB_TOKEN é desinstalado, o grant
permanece em workflow-config. Revoke explícito: edite manualmente OU
aguarde gap opt-in `forge reconfigure --revoke-grants` (não
implementado v1.2).

## `native-gates` (opt-in, Tema 6 / Decisão 33)

Configura os gates de **execução externa** — o engine roda os binários de
qualidade/build do projeto consumidor (linters, build tools) via a fronteira da
Decisão 33 (distinta do sandbox de validators da Decisão 30). Bloco opcional —
sem ele, os gates usam defaults. **Filosofia:** violação é **informativa** por
default (`warn`, não reprova); subir pra `fail` é opt-in por gate. Tool ausente
→ `skipped` (não reprova); timeout → `degraded`. Nunca auto-fix.

```yaml
native-gates:
  ktlint:
    enabled: true             # default true; ausência do tool ainda → skipped
    bin: /opt/ktlint          # opcional; path/argv quando não há ./gradlew
    timeout: 120              # segundos; default 120; estouro → degraded
    fail-on-violation: false  # opt-in: true sobe warn→fail (default informativo)
  build:
    enabled: true             # default true; toolchain ausente → skipped/degraded
    timeout: 600              # builds são lentos; default 600s; estouro → degraded
    fail-on-violation: false  # opt-in: true sobe warn→fail
```

### Semântica de campos

| Campo | Tipo | Default | Notas |
|---|---|---|---|
| `<gate>.enabled` | bool | `true` | `false` desliga o gate inteiro (não invoca tool) |
| `ktlint.bin` | str \| argv | — | path/argv do ktlint quando não há `./gradlew`; ignorado se o wrapper existe |
| `<gate>.timeout` | int > 0 | ktlint 120 / build 600 | estouro → `degraded` (não `fail`) |
| `<gate>.fail-on-violation` | bool | `false` | `true` sobe `warn → fail` (gate com dentes, opt-in) |

### Descoberta do binário (skip-se-ausente)

Ordem de preferência (primeiro que resolver vence):

- **ktlint:** `./gradlew ktlintCheck` → `native-gates.ktlint.bin` → `which ktlint`.
- **build:** por plataforma de `platforms.active` — android/kmp → `./gradlew assembleDebug`;
  ios → `xcodebuild build` (forma mínima); web → sem build-only no Nível 1 (skip).

Nenhum resolve → o gate é `skipped` com aviso mentor-calmo nomeando como habilitar.
Skip-se-ausente é **requisito**, não conveniência: um gate que falha por ausência
tornaria o forge refém da toolchain de cada consumidor.

### Notas de runtime

- **Modo check, read-only (ktlint).** O ktlint roda só em `ktlintCheck` — nunca
  `ktlintFormat`/`--fix`. A garantia "não escreve" vem de escolher o subcomando.
- **O build ESCREVE artefatos** (binários, caches) no working tree do projeto.
  Isso é esperado e legítimo (é o build do próprio projeto); o forge **não
  versiona nem limpa** esses artefatos.
- **`degraded` é cidadão de primeira classe.** Ausente/estourado → `degraded`,
  distinto de `pass`/`fail`. Ataca o "verde inerte" do Tema 6: o usuário vê que o
  gate não rodou, em vez de um falso verde.
- Os gates acompanham a **cascade de validators**: num scope sem validators
  registrados, os gates nativos também não rodam (Nível 1).

## Deliberately OUT of config

| Decision | Why not in config |
|---|---|
| Time estimates | Out-of-scope (identity decision) |
| PR/commit conventions | Lives in `.claude/rules/` or `create-branch` skill |
| Meo* component list | Lives in `.claude/inventory/design-system.yaml` (dynamic) |
| i18n key list | Lives in `.claude/inventory/i18n.yaml` (dynamic) |
| Feature history | Lives in git + `docs/.../features/*/status.json` |
| Cross-project user memory | Lives in `~/.claude/...memory/` (read-only from this config) |
| Locally-installed skill | Inferred from `cards.snapshot-root` |
| Secrets / credentials | NEVER here. MCP auth lives in MCP. |

## Difference: config vs inventory vs memory vs graph

| Where | Content | Updated by | Versioned in git? |
|---|---|---|---|
| `forge-config.yaml` (at `.claude/forge/forge-config.yaml`) | **Fixed decisions** about project (preset, cards, paths, backend, persona) | Init + reconfigure | ✅ yes |
| `.claude/inventory/*.yaml` | **Factual snapshot** of project (DS, i18n, conventions) | Init + on-demand re-scan | ✅ yes |
| `.claude/forge/state/lifecycle/` + `.claude/memory/L*.yaml` | **Accumulated learning** (lifecycle state per feature in `forge/state/lifecycle/`; inferred patterns, FNDs, resolved contradictions in `memory/L2`) | Each feature | ⚠️ L2/L3 yes; L1 lifecycle no |
| `.claude/graph.db` | **Structural map** of code (queryable) | Incremental | ❌ rebuildable |

Config = "what we chose." Inventory = "what exists." Memory = "what we learned."
Graph = "how it's connected." Each with its own cycle.

## Related schemas

- [`backend-axes.md`](backend-axes.md) — bloco `backend:` multi-axis
  platform-keyed (8 eixos × N plataformas → cell\|null), cell-object
  shape, status enum, detection composer, starter bundles. Fonte canônica
  do modelo backend desde Phase B / DET-6.
- [`card.md`](card.md) — `identity.category` (categorias enumeradas
  incluindo os 8 axes), `identity.platforms`, CARD-001..022.
- [`capability-labels.md`](capability-labels.md) — catálogo de labels;
  singulares `auth-provider`, `http-client`, `crash-reporting` foram
  removidas em W3 porque cardinalidade já é enforçada pelo schema
  multi-axis.

<!-- open-detail #6: Phase A AskUserQuestion intent protocol shape — W7 (init/reconfigure UX) consome esse API. Forma exata do payload ainda não definida; W7 fica blocked até Phase A SPEC. Default conservador: AskUserQuestion single-call por cell. -->

<!-- open-detail #7: crashlytics card rename — considerar rename `crashlytics` → `firebase-crashlytics` (paridade com firebase-auth, firebase-storage, firebase-analytics). Decisão delegada à task de W4 — se rename, registra como deviation tracked no PLAN. -->

## Final notes

1. **Almost nothing is free-form** — every field has enum or regex. Reduces drift.
2. **Inline comments are contract** — `# one of: X | Y | Z` is parsed by `forge doctor`.
3. **Schema is flat enough for grep** — debug quickly (`grep -A2 "preset:" workflow-config.yaml`).
4. **Slugs instead of IDs** — human-readable > DB-efficient.
5. **Dates in ISO8601 UTC** — comparable, parseable in any language.
6. **No optional fields without explicit default** — agent never faces "field missing, what now?".
