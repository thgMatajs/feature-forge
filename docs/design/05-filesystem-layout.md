# Filesystem layout — the complete picture

Projeção concreta de todos os schemas da Fase 1 no filesystem. Mostra cada
arquivo que feature-forge cria, lê, ou modifica — onde vive, quem escreve,
quando é atualizado, e se entra ou não no git.

Este documento fecha a Fase 1: depois daqui, qualquer arquivo Python ou
prompt criado tem **um lugar pré-definido**, sem improviso.

---

## As três localizações

```
┌─────────────────────────────────────────────────────────────┐
│ 1. CANONICAL (v1.3 — XDG install layout)                   │
│    ~/.local/share/feature-forge/                            │
│    Source of truth. Onde a skill vive de verdade.          │
│    Versionado em git próprio.                               │
│    Symlink: ~/.local/bin/forge → canonical/bin/forge        │
│                                                             │
│    Fallback / legacy dev path:                              │
│    ~/Documents/feature-forge/                               │
│    (usada em dev direto — ver §1 abaixo)                    │
├─────────────────────────────────────────────────────────────┤
│ 2. PER-PROJECT INSTALL                                      │
│    {project}/.claude/forge/                                 │
│    O que `forge init` cria em cada projeto.                │
│    Sub-namespace v1.3 — forge não toca .claude/ raiz       │
│    Versionado no git do projeto (com exceções).            │
├─────────────────────────────────────────────────────────────┤
│ 3. FEATURE PACKAGES                                         │
│    {project}/docs/forge-specs/          │
│    O que `forge plan` e `forge implement` produzem.        │
│    Versionado no git do projeto.                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 1. Canonical repo — `~/.local/share/feature-forge/` (v1.3 XDG install)

```
~/.local/share/feature-forge/           ← XDG canonical path (Revisita Decisão 18, v1.3)
│                                         scripts/install.sh clona aqui por default
│                                         FORGE_HOME env var pode sobrescrever
│
│  Acesso principal: ~/.local/bin/forge  → .../bin/forge  (symlink criado pelo install.sh)
│
│  Durante desenvolvimento (worktree direto):
│     ~/Documents/feature-forge/         ← caminho histórico, ainda funciona
│     forge --version funciona se FORGE_HOME ou PATH apontar pra cá
│
~/Documents/feature-forge/    ← (legacy dev / worktree direto — mesmo layout abaixo)
│
├── README.md                              top-level entrypoint
├── INFLUENCES.md                          attribution table
├── LICENSE                                MIT
├── CHANGELOG.md                           per-release notes
├── .gitignore
├── pyproject.toml                         Python package metadata
├── .github/
│   └── workflows/
│       ├── test.yml                       runs validators + e2e tests
│       └── release.yml                    tags + GitHub releases
│
├── bin/
│   └── forge                              Bash dispatcher (~50 LOC)
│                                          parses subcommand, exports env,
│                                          calls engine/cli.py
│
├── engine/                                Python core
│   ├── __init__.py
│   ├── cli.py                             argparse dispatcher
│   ├── init.py                            `forge init`
│   ├── plan.py                            `forge plan` (invokes planning-conductor)
│   ├── implement.py                       `forge implement` (invokes execution-conductor)
│   ├── verify.py                          `forge verify`
│   ├── status.py                          `forge status`
│   ├── doctor.py                          `forge doctor`
│   ├── reconfigure.py                     `forge reconfigure`
│   ├── evolve.py                          `forge evolve`
│   ├── undo.py                            `forge undo`
│   ├── raw.py                             `forge raw <agent>`
│   ├── ingest.py                          `forge ingest` — event router
│   │
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── builder.py                     full rebuild
│   │   ├── incremental.py                 delta updates
│   │   ├── queries.py                     canonical queries (Q1-Q10)
│   │   ├── parser_kotlin.py
│   │   ├── parser_swift.py
│   │   └── parser_typescript.py
│   │
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── l1.py                          per-feature reader/writer
│   │   ├── l2.py                          project layer
│   │   ├── l3.py                          read-only proxy to auto-memory
│   │   └── distiller.py                   memory-distiller agent driver
│   │
│   ├── cards/
│   │   ├── __init__.py
│   │   ├── loader.py                      read card.yaml
│   │   ├── resolver.py                    deps + conflicts
│   │   ├── merger.py                      merge contributions
│   │   └── snapshotter.py                 copy canonical → .claude/cards/
│   │
│   ├── inventory/
│   │   ├── __init__.py
│   │   ├── design_system.py               extract DS from repo
│   │   ├── i18n.py                        extract i18n
│   │   └── conventions.py                 extract conventions
│   │
│   ├── mcp/
│   │   ├── __init__.py
│   │   ├── jira.py                        Atlassian MCP wrapper
│   │   ├── linear.py
│   │   ├── github_issues.py
│   │   └── context7.py                    docs lookup wrapper
│   │
│   ├── vision/
│   │   ├── __init__.py
│   │   └── screenshot.py                  vision-based analysis
│   │
│   ├── ui/                                terminal output (cinemático)
│   │   ├── __init__.py
│   │   ├── renderer.py                    box drawing, alignment
│   │   ├── progress.py                    real progress bars
│   │   ├── tree.py                        tree-ASCII output
│   │   └── question.py                    AskUserQuestion local fallback
│   │
│   ├── persona/
│   │   ├── __init__.py
│   │   └── mentor_calmo.py                phrase library + drill-down rules
│   │
│   └── utils/
│       ├── __init__.py
│       ├── yaml_io.py                     atomic YAML read/write
│       ├── sqlite_io.py                   WAL mode + transactions
│       ├── sha256.py                      content hashing for snapshots
│       └── paths.py                       cross-platform path utilities
│
├── agents/                                Agent prompts (canonical)
│   ├── planning-conductor.md
│   ├── feature-intake-agent.md
│   ├── feature-prd-agent.md
│   ├── screen-analysis-agent.md
│   ├── contract-planner-agent.md
│   ├── tech-spec-agent.md
│   ├── task-contract-writer.md
│   ├── readiness-reviewer.md
│   ├── retrospective-agent.md
│   └── memory-distiller.md
│
├── cards/                                 Canonical card library (12 in v1)
│   ├── kotlin-language/
│   │   ├── card.yaml
│   │   ├── README.md
│   │   ├── templates/
│   │   ├── validators/
│   │   ├── agent-contributions/
│   │   ├── detection/
│   │   └── examples/
│   ├── kmp-shared/
│   ├── compose-screens/
│   ├── swiftui-screens/
│   ├── koin-annotations/
│   ├── skie-bridge/
│   ├── nav3/
│   ├── swiftui-navigation/
│   ├── firebase-auth/                     (capabilities atualizadas em 3.5)
│   ├── firestore-persistence/             (NOVO 3.5 — split firebase-firestore)
│   ├── firestore-realtime/                (NOVO 3.5 — split firebase-firestore)
│   ├── firestore-security-rules/          (NOVO 3.5 — split firebase-firestore)
│   ├── firebase-storage/
│   ├── crashlytics/
│   ├── ktor-client/                       (NOVO 3.5 — REST HTTP client)
│   ├── rest-api-contract/                 (NOVO 3.5 — REST endpoints/DTOs)
│   ├── kotlinx-serialization-json/        (NOVO 3.5 — JSON serialization)
│   ├── room-database/                     (NOVO 3.5 — persistence local KMP)
│   ├── datastore-prefs/                   (NOVO 3.5 — KV prefs small)
│   ├── auth-jwt-bearer/                   (NOVO 3.5 — auth REST alternativa)
│   └── .archived/
│       └── firebase-firestore-monolithic/ (ARQUIVADO 3.5 — substituído pelos 3 splits)
│
├── presets/                               Preset manifests
│   ├── kmp-mobile/                        (BASE — só stack; backend é escolha livre)
│   │   ├── README.md
│   │   └── preset.yaml
│   ├── android-only/                      (planejado v1.x)
│   ├── ios-only/                          (planejado v1.x)
│   ├── web/                               (planejado v1.x)
│   ├── kmp-fullstack/                     (planejado v1.x)
│   └── .archived/
│       └── kmp-mobile-firebase-pre-3.5/   (ARQUIVADO 3.5 — substituído por kmp-mobile + cards backend escolhidos individualmente)
│
├── templates/                             Default templates per feature artifact
│   ├── feature-intake.template.md
│   ├── feature-prd.template.md
│   ├── screen-analysis.template.md
│   ├── bdd.template.md
│   ├── bdd.template.json
│   ├── ui-state-spec.template.yaml
│   ├── navigation-spec.template.yaml
│   ├── data-contract-spec.template.yaml
│   ├── analytics-spec.template.yaml
│   ├── test-strategy.template.yaml
│   ├── tech-spec.template.md
│   ├── task-breakdown.template.yaml
│   ├── task-contract.template.yaml
│   ├── implementation-readiness-review.template.md
│   ├── plan-feature-handoff.template.json
│   └── evals.template.json
│
├── hooks/                                 Hook scripts (copied to project on init)
│   ├── post-edit-codebase-graph.sh
│   ├── post-write-feature-artifact.sh
│   ├── pre-commit-feature-forge.sh
│   ├── post-subagent-validate.sh
│   ├── session-start-drift-check.sh
│   ├── git-pre-commit                     shim that calls forge ingest
│   ├── git-post-commit
│   ├── git-pre-push
│   └── ci-pr-ingest.yml                   GitHub Actions workflow template
│
├── validators/                            Python validators (canonical)
│   ├── validate_feature_package.py
│   ├── validate_readiness.py
│   ├── validate_task_contract.py
│   ├── validate_data_contract.py
│   ├── validate_screen_analysis.py
│   ├── validate_backend_e2e.py
│   ├── validate_workflow_config.py
│   ├── validate_card_yaml.py
│   ├── validate_inventory.py
│   ├── validate_memory.py
│   ├── check_no_invented_behavior.py
│   └── check_files_in_allowed_files.py
│
├── migrations/                            Schema migrators
│   ├── workflow-config/
│   │   └── 001_to_002.py
│   ├── card/
│   │   └── 001_to_002.py
│   └── graph/
│       └── 001_to_002.sql
│
├── docs/                                  ← já criados na Fase 1
│   ├── design/
│   │   ├── 00-vision.md
│   │   ├── 01-decisions.md
│   │   ├── 02-phases.md
│   │   ├── 03-influences.md
│   │   ├── 04-pending.md
│   │   └── 05-filesystem-layout.md        ← este documento
│   ├── ux/
│   │   ├── forge-init-roteiro.md          ✅ pronto
│   │   ├── forge-plan-roteiro.md          ⏳ Fase 2
│   │   ├── forge-implement-roteiro.md     ⏳ Fase 2
│   │   ├── forge-verify-roteiro.md        ⏳ Fase 2
│   │   ├── forge-doctor-roteiro.md        ⏳ Fase 2
│   │   ├── forge-reconfigure-roteiro.md   ⏳ Fase 2
│   │   └── forge-evolve-roteiro.md        ⏳ Fase 2
│   ├── lifecycle/
│   │   └── memory-and-graph.md            ✅ pronto
│   └── schemas/
│       ├── forge-config.md                ✅  (era workflow-config.md; renomeado v1.3)
│       ├── card.md                        ✅
│       ├── inventories.md                 ✅
│       ├── memory.md                      ✅
│       └── graph.md                       ✅
│
├── tests/
│   ├── unit/
│   │   ├── test_graph_incremental.py
│   │   ├── test_card_resolver.py
│   │   ├── test_memory_l1.py
│   │   └── ...
│   ├── integration/
│   │   ├── test_init_greenfield.py
│   │   ├── test_init_brownfield.py
│   │   └── ...
│   └── e2e/
│       ├── test_full_plan_with_jira.py
│       └── test_implement_with_gate_violations.py
│
└── examples/                              Example projects for demos/tests
    ├── greenfield-test-repo/
    └── meobonsai-fixture/                 frozen copy for E2E
```

### Canonical repo stats (estimated v1)

| Category | File count | Size |
|---|---|---|
| Docs (this Fase 1) | ~12 | ~280K |
| Python engine | ~35 | ~3,500 LOC |
| Agent prompts | 10 | ~2,000 LOC of markdown |
| Cards (12 × ~6 files each) | ~72 | ~5,000 LOC of YAML/MD/scripts |
| Presets | ~16 | small |
| Templates | 16 | ~2,000 LOC |
| Hooks | 9 | ~300 LOC of bash |
| Validators | 12 | ~1,500 LOC of Python |
| Tests | ~30 | ~2,000 LOC |
| **Total v1** | ~210 files | ~17,000 LOC |

---

## 2. Per-project install — `{project}/.claude/forge/` (v1.3 sub-namespace)

What `forge init` writes when run inside a project:

```
{project}/
├── .claude/
│   │
│   │   NOTE v1.3: forge usa sub-namespace .claude/forge/ — não polui
│   │   a raiz .claude/ de outros tools (Claude Code, etc.)
│   │
│   ├── forge/                             NOVO em v1.3 (era .claude/ raiz)
│   │   ├── forge-config.yaml              main config — committed
│   │   │                                  (era workflow-config.yaml em v1.x)
│   │   ├── state/                         runtime state files (forge-pending.json, etc.)
│   │   ├── hooks/                         Bash shims — copied from canonical
│   │   │   ├── post-edit-codebase-graph.sh
│   │   │   ├── post-write-feature-artifact.sh
│   │   │   ├── pre-commit-feature-forge.sh
│   │   │   ├── post-subagent-validate.sh
│   │   │   └── session-start-drift-check.sh
│   │   └── cards/local/                   ← overlay versionado (Gap 5)
│   │       └── <local-card-name>/
│   │           ├── card.yaml
│   │           ├── README.md
│   │           └── detection/signals.yaml
│   │
│   ├── bin/                               executáveis vendorizados pelo forge init
│   │   ├── mem                            mem CLI vendorizado (asset pinado — executável 755)
│   │   └── mem.version                    pin de versão do asset (ex.: "0.8.1")
│   │
│   │   NOTE coexistência transitória (W-VENDOR): `.claude/memory/` hospeda o mem
│   │   (JSONL commitado + mem.db SQLite derivado) e remanescentes L2/L3 enquanto
│   │   as ondas W-MIGRATE e W-ROUTE não completam o roteamento. Após W-MIGRATE/
│   │   W-ROUTE: `.claude/memory/` passa a ser exclusivamente do mem.
│   │
│   ├── settings.json                      APPEND-ONLY merge pelo forge (não sobrescreve)
│   │                                      hook registrations adicionadas, não substituídas
│   │
│   ├── .gitignore                         auto-created in .claude/forge/
│   │                                      ignores: state/, graph.db, forge/state/lifecycle/, *.bak
│   │
│   ├── cards/                             snapshots from canonical
│   │   │                                  (sha256 recorded in forge-config.yaml)
│   │   ├── kotlin-language/
│   │   ├── kmp-shared/
│   │   ├── compose-screens/
│   │   ├── swiftui-screens/
│   │   ├── koin-annotations/
│   │   ├── skie-bridge/
│   │   ├── nav3/
│   │   ├── swiftui-navigation/
│   │   ├── firebase-auth/
│   │   ├── firebase-firestore/
│   │   ├── firebase-storage/
│   │   └── crashlytics/
│   │
│   ├── inventory/                         factual snapshot — committed
│   │   ├── design-system.yaml
│   │   ├── i18n.yaml
│   │   ├── conventions.yaml
│   │   ├── capability-labels.yaml         (snapshot canon)
│   │   ├── capability-labels.local.yaml   ← overlay (Gap 5)
│   │   ├── local-cards-manifest.yaml      ← gerado pelo loader (Gap 5)
│   │   └── ignored-signals.yaml           ← gerado pelo init Step 7.5 (Gap 5)
│   │
│   ├── forge/
│   │   ├── state/
│   │   │   └── lifecycle/                 per-feature WIP — NOT committed
│   │   │       ├── {feature-slug-A}/
│   │   │       │   ├── hypothesis.yaml
│   │   │       │   ├── ambiguity-map.yaml
│   │   │       │   ├── elicitation.yaml
│   │   │       │   ├── rationale-trace.yaml
│   │   │       │   ├── dispatch-log.jsonl
│   │   │       │   └── history.jsonl
│   │   │       ├── {feature-slug-B}/...
│   │   │       └── archived/              compressed summaries of done features
│   │   │           └── {feature-slug-X}.summary.yaml
│   │   └── (forge-config.yaml + hooks/ + state/ as documented above)
│   │
│   ├── memory/
│   │   └── L2-project.yaml                team learning — committed
│   │
│   ├── graph.db                           SQLite — NOT committed (rebuildable)
│   │
│   ├── forge-version-lock.yaml            forge version pinned here — committed
│   │
│   ├── skills/                            USER-MANAGED — forge NEVER touches this
│   │   └── (other skill snapshots)
│   │
│   └── agents/                            USER-MANAGED — forge NEVER touches this
│       └── (custom agent overrides)
│
├── .git/
│   └── hooks/                             installed by forge init
│       ├── pre-commit                     → calls .claude/forge/hooks/git-pre-commit
│       ├── post-commit                    → calls .claude/forge/hooks/git-post-commit
│       └── pre-push                       → calls .claude/forge/hooks/git-pre-push
│
└── .github/                               (only if user opts into CI)
    └── workflows/
        └── feature-forge-pr-ingest.yml    posted on init with --ci flag
```

### `.claude/forge/.gitignore` (auto-created)

```gitignore
# feature-forge — auto-managed
state/
graph.db
graph.db-journal
graph.db-wal
forge/state/lifecycle/**/!archived/
forge/state/lifecycle/**/!archived/**
*.bak
```

---

## 3. Feature packages — `{project}/docs/forge-specs/`

What `forge plan` and `forge implement` produce per feature:

```
{project}/docs/forge-specs/
├── README.md                              workflow overview — copied on init
├── operating-policy.md                    rules of the road — copied
├── runtime-assets.md                      what runtime needs — copied
│
├── status.json                            overall workflow state
├── history.jsonl                          global event log
│
├── features/                              subtype=product (default)
│   └── {feature-slug}/                    one folder per product feature
│       │
│       ├── feature-intake.md              Wave A artifact
│       ├── feature-prd.md                 Wave A artifact
│       ├── screen-analysis.md             Wave B artifact
│       ├── bdd.md                         Wave B artifact
│       ├── bdd.json                       Wave B artifact (machine-readable)
│       ├── ui-state-spec.yaml             Wave B artifact
│       ├── navigation-spec.yaml           Wave B artifact
│       ├── data-contract-spec.yaml        Wave B artifact
│       ├── analytics-spec.yaml            Wave B artifact
│       ├── test-strategy.yaml             Wave B artifact
│       ├── tech-spec.md                   Wave C artifact
│       ├── task-breakdown.yaml            Wave D artifact
│       │
│       ├── tasks/                         Wave D artifacts (per task)
│       │   ├── TASK-0001.yaml
│       │   ├── TASK-0002.yaml
│       │   ├── TASK-0003.yaml
│       │   └── ...
│       │
│       ├── open-questions.yaml            tracking unresolved
│       ├── implementation-readiness-review.md   Wave E artifact
│       ├── plan-feature-handoff.json      Wave E artifact
│       ├── status.json                    feature-level state
│       ├── history.jsonl                  feature event log
│       │
│       ├── checkpoints/                   resume points
│       ├── findings/                      out-of-scope discoveries
│       ├── screenshots/                   downloaded from Jira or user-provided
│       ├── completion-evidence/           proof artifacts per task
│       ├── reviews/                       pre-commit reviews per task
│       ├── retrospective.md               written on feature-done
│       │
│       └── evals/
│           └── evals.json                 evaluation results
│
└── non-product/                           subtype ∈ {refactor, spike, chore}
    └── {feature-slug}/                    parallel to features/{slug}/
        │
        ├── feature-intake.md              Wave A — REFACTOR variant
        │                                  (template: feature-intake-refactor.template.md)
        ├── tech-spec.md                   Wave C — stripped (§§ 2, 3-7
        │                                  modified-layers, 14 only)
        ├── task-breakdown.yaml            Wave D artifact
        │
        ├── tasks/                         Wave D artifacts
        │   └── TASK-NNNN.yaml
        │
        ├── open-questions.yaml
        ├── implementation-readiness-review.md
        ├── plan-feature-handoff.json
        ├── status.json                    feature-level state (subtype field set)
        ├── history.jsonl
        │
        ├── checkpoints/
        ├── findings/
        ├── completion-evidence/
        ├── reviews/
        └── retrospective.md               written on feature-done
```

### Artifacts present per subtype

Discipline §8 — non-product feature track. Refactor packages **lack**
the entire Wave B output set because forcing those artifacts would force
sub-agents to invent (no PRD natural, no screen-analysis without UI
change, no contracts for unchanged behavior). Spike and chore are
stubbed in v1.0; their package shape is reserved for v1.1+.

| Artifact | product | refactor | spike (v1.1+) | chore (v1.1+) |
|---|---|---|---|---|
| `feature-intake.md` | ✓ canonical | ✓ refactor variant | (TBD) | (TBD) |
| `feature-prd.md` | ✓ | absent | (TBD) | (TBD) |
| `screen-analysis.md` | ✓ | **absent** | (TBD) | (TBD) |
| `bdd.md` + `bdd.json` | ✓ | **absent** | (TBD) | (TBD) |
| `ui-state-spec.yaml` | ✓ | **absent** | (TBD) | (TBD) |
| `navigation-spec.yaml` | ✓ | **absent** | (TBD) | (TBD) |
| `data-contract-spec.yaml` | ✓ | **absent** | (TBD) | (TBD) |
| `analytics-spec.yaml` | ✓ | **absent** | (TBD) | (TBD) |
| `test-strategy.yaml` | ✓ | **absent** | (TBD) | (TBD) |
| `tech-spec.md` | ✓ (full §§ 1-14) | ✓ (§§ 2, 3-7 modified-only, 14) | (TBD) | (TBD) |
| `task-breakdown.yaml` | ✓ | ✓ | (TBD) | (TBD) |
| `tasks/TASK-NNNN.yaml` | ✓ | ✓ (with `validations: [check_no_behavior_change]`) | (TBD) | (TBD) |
| `implementation-readiness-review.md` | ✓ | ✓ | (TBD) | (TBD) |
| `plan-feature-handoff.json` | ✓ | ✓ | (TBD) | (TBD) |

Wave dispatch routing: `engine/plan.py` reads `status.json.subtype` and
chooses the wave sequence — `product` → A·B·C·D·E (`features/{slug}/`)
vs `refactor` → A·C·D·E (`non-product/{slug}/`). See
`docs/design/07-discipline.md §8` and `agents/planning-conductor.md
§Phase 1 + §Phase 4` for the conductor-side flow.

### Feature lifecycle states

```
planned → active → done → archived
   │        │       │        │
   │        │       │        └─ L1 compressed to L1/archived/{slug}.summary.yaml
   │        │       │           feature folder remains in docs/
   │        │       │
   │        │       └─ retrospective.md written; L2 promotion candidates queued
   │        │
   │        └─ at least one TASK in progress
   │
   └─ created by forge plan; readiness !ready yet
```

---

## 4. Git policy summary

### ✅ Always commit (canonical repo)

Everything in `~/.local/share/feature-forge/` except `.bak`, `tests/_tmp/`,
`examples/*/.claude/` (test fixtures).

### ✅ Always commit (per project) — v1.3 sub-namespace

```
.claude/forge/forge-config.yaml             main config (era workflow-config.yaml)
.claude/forge/hooks/                        Bash shims
.claude/cards/                              entire snapshot
.claude/inventory/
.claude/memory/L2-project.yaml
.claude/forge/state/lifecycle/archived/     only archived summaries
.claude/forge-version-lock.yaml
.git/hooks/                                 git-managed; shims only
.github/workflows/feature-forge-*.yml       if CI used
docs/forge-specs/        complete tree
```

### ❌ Never commit (per project)

```
.claude/forge/state/                        runtime state files (includes lifecycle WIP)
.claude/graph.db                            rebuildable
.claude/graph.db-*                          SQLite working files
.claude/forge/state/lifecycle/{active}/     WIP per-feature, per-developer
.claude/*.bak                               distillation backups
```

### 🔧 .gitignore the project gets (auto-created)

`forge init` appends to `{project}/.gitignore`:

```gitignore
# feature-forge
.claude/forge/state/
.claude/graph.db
.claude/graph.db-*
!.claude/forge/state/lifecycle/archived/
.claude/*.bak
```

---

## 5. Per-file lifecycle reference

A matrix of every file v1 might create, who writes/reads it, when, and git
policy.

### Canonical repo files (no per-file lifecycle — versioned by feature-forge dev)

| File | Owner | Notes |
|---|---|---|
| Everything in `~/.local/share/feature-forge/` | feature-forge maintainers | Released as semver; consumed via snapshot |

### Per-project install files

| File | Created by | Updated by | Read by | Git |
|---|---|---|---|---|
| `.claude/forge/forge-config.yaml` | `forge init` | `forge reconfigure`, hooks (last-doctor-run) | all engine modules | ✅ |
| `.gitignore` (in `.claude/`) | `forge init` | rarely | git | ✅ |
| `cards/{name}/` | `forge init` / `forge reconfigure` (menu "adicionar card") | `forge reconfigure` (menu "atualizar card do canonical") | resolver, merger | ✅ |
| `inventory/design-system.yaml` | `forge init` | hooks (incremental) | DS-related cards, screen-analysis-agent | ✅ |
| `inventory/i18n.yaml` | `forge init` | hooks (i18n changes) | contract-planner-agent, validators | ✅ |
| `inventory/conventions.yaml` | `forge init` | `forge reconfigure`, feature-done | tech-spec-agent, task-writer | ✅ |
| `forge/state/lifecycle/{slug}/*.yaml` | planning-conductor, sub-agents | throughout plan/implement | planning-conductor, retrospective-agent | ❌ |
| `forge/state/lifecycle/archived/*.yaml` | retrospective-agent (on done) | never | future planning-conductor for context | ✅ |
| `memory/L2-project.yaml` | `forge init` (seed) | retrospective-agent (proposes), `forge evolve` (applies) | planning-conductor, all agents | ✅ |
| `graph.db` | `forge init` (full build) | hooks (incremental), `forge reconfigure` (rebuild) | `forge graph query` | ❌ |
| `.claude/forge/hooks/*.sh` | `forge init` | `forge reconfigure` | git/Claude hooks/CI | ✅ |
| `.claude/forge/state/` | `forge` runtime | each invocation | `forge` (intent protocol) | ❌ |
| `workflow-config-history.jsonl` | every `forge reconfigure` | append-only | `forge doctor`, debugging | ✅ |
| `proposed-evolutions.yaml` | retrospective-agent | `forge evolve` (consumes) | user via `forge evolve` | ✅ |
| `forge-version-lock.yaml` | `forge init` | `forge upgrade` | `forge doctor` | ✅ |

### Feature package files

| File | Created by | Updated by | Read by | Git |
|---|---|---|---|---|
| `feature-intake.md` | feature-intake-agent | once | all subsequent agents | ✅ |
| `feature-prd.md` | feature-prd-agent | once | screen-analysis, contract-planner | ✅ |
| `screen-analysis.md` | screen-analysis-agent | once | contract-planner, tech-spec | ✅ |
| `bdd.md` + `bdd.json` | contract-planner-agent | once | tech-spec, task-writer | ✅ |
| `ui-state-spec.yaml` | screen-analysis-agent | once | tech-spec, task-writer | ✅ |
| `navigation-spec.yaml` | contract-planner-agent | once | tech-spec, task-writer | ✅ |
| `data-contract-spec.yaml` | contract-planner-agent | once | tech-spec, task-writer | ✅ |
| `analytics-spec.yaml` | contract-planner-agent | once | tech-spec, task-writer | ✅ |
| `test-strategy.yaml` | contract-planner-agent | once | task-writer, validators | ✅ |
| `tech-spec.md` | tech-spec-agent | once | task-writer, all implementers | ✅ |
| `task-breakdown.yaml` | task-contract-writer | once | execution-conductor | ✅ |
| `tasks/TASK-NNNN.yaml` | task-contract-writer | execution-conductor (status field) | execution-conductor, validators | ✅ |
| `open-questions.yaml` | various agents | as ambiguity resolves | readiness-reviewer | ✅ |
| `implementation-readiness-review.md` | readiness-reviewer | re-run on reconfigure | execution-conductor | ✅ |
| `plan-feature-handoff.json` | planning-conductor | once | execution-conductor | ✅ |
| `status.json` | planning-conductor | every state change | `forge status` | ✅ |
| `history.jsonl` | planning-conductor + execution-conductor | append-only | `forge status`, debugging | ✅ |
| `checkpoints/*.json` | every gate pass | append-only | `forge resume` | ✅ |
| `findings/FND-*.yaml` | any agent during work | when finding occurs | retrospective-agent | ✅ |
| `screenshots/*.png` | `forge plan` (Jira fetch) | once | screen-analysis-agent | ✅ |
| `completion-evidence/TASK-*-evidence.json` | execution-conductor | per task | `forge verify`, retrospective | ✅ |
| `reviews/TASK-*-review.md` | pre-commit reviewer agent | per task | execution-conductor, retrospective | ✅ |
| `retrospective.md` | retrospective-agent | once on done | retrospective archive, L2 promotion | ✅ |
| `evals/evals.json` | retrospective-agent | once on done | `forge evolve`, future debugging | ✅ |

---

## 6. Anatomy of one card folder (concrete)

For reference, what's inside one card snapshot in `.claude/cards/`:

```
.claude/cards/firebase-firestore/
├── card.yaml                              manifest (schema in card.md)
├── README.md                              human description
│
├── templates/
│   ├── firestore-data-contract.yaml       contributed to data-contract-spec.yaml
│   ├── firestore-tech-spec.md             contributed to tech-spec.md
│   └── firestore-e2e.yaml                 contributed to test-strategy.yaml
│
├── validators/
│   ├── check-firestore-rules.py
│   └── check-firestore-indexes.py
│
├── agent-contributions/
│   ├── contract-planner-additions.md      injected at extension-point
│   └── tech-spec-additions.md
│
├── hooks/
│   └── post-edit-firestore-rules.sh
│
├── detection/
│   └── signals.yaml                       redundant copy of card.yaml.detection
│
└── examples/
    └── example-firestore-feature/         reference feature using this card
```

Every card follows this pattern. New cards copy this structure.

---

## 7. Anatomy of one feature folder (concrete)

For reference, what `forge plan` produces for a feature called `lembrete-rega`:

```
docs/forge-specs/features/lembrete-rega/
├── feature-intake.md
├── feature-prd.md
├── screen-analysis.md
├── bdd.md
├── bdd.json
├── ui-state-spec.yaml
├── navigation-spec.yaml
├── data-contract-spec.yaml
├── analytics-spec.yaml
├── test-strategy.yaml
├── tech-spec.md
├── task-breakdown.yaml
├── tasks/
│   ├── TASK-0001.yaml    (setup-feature-modules)
│   ├── TASK-0002.yaml    (shared data layer)
│   ├── TASK-0003.yaml    (shared domain layer)
│   ├── TASK-0004.yaml    (shared viewmodel)
│   ├── TASK-0005.yaml    (Android UI)
│   ├── TASK-0006.yaml    (iOS UI)
│   └── TASK-0007.yaml    (backend e2e validation)
├── open-questions.yaml                    0 blocking entries
├── implementation-readiness-review.md     status: ready
├── plan-feature-handoff.json
├── status.json
├── history.jsonl
├── checkpoints/
├── findings/                              empty initially
├── screenshots/
│   ├── mockup-list.png
│   ├── mockup-detail.png
│   └── mockup-edit.png
├── completion-evidence/                   empty until forge implement
├── reviews/                               empty until forge implement
└── evals/                                 created on feature-done
```

---

## 8. Total artifact inventory (v1 estimate)

```
Per-project install (after forge init) — v1.3 layout:
  • .claude/forge/forge-config.yaml                            1 file
  • .claude/forge/.gitignore                                    1 file
  • .claude/forge/hooks/*.sh                                    5 files
  • .claude/forge/state/                               runtime, not committed
  • .claude/cards/*/{card.yaml, README, templates, ...}      ~80 files
  • .claude/inventory/*.yaml                                    3 files
  • .claude/memory/L2-project.yaml                              1 file
  • .claude/forge/state/lifecycle/{slug}/ (per active feature)  6/feature
  • .claude/graph.db                                            1 file (not committed)
  • .claude/forge-version-lock.yaml                             1 file
  • workflow-config-history.jsonl                               1 file
  • proposed-evolutions.yaml                                    1 file
                                                          ─────────────
  Baseline after init:                                     ~95 files

Per feature package:
  • Wave A-E artifacts                                         16 files
  • tasks/TASK-NNNN.yaml                                  N (5-10) files
  • status.json + history.jsonl                                 2 files
  • screenshots/                                          M (0-N) files
  • checkpoints/                                          K (per gate)
  • completion-evidence/ + reviews/                       2N files
                                                          ─────────────
  Per feature:                                          ~25-40 files
```

A typical project with 12 features installed = baseline (95) +
features (12 × 30 = 360) = **~455 files**.

Manageable. Sortable. Inspectable.

---

## 9. Phase 1 closure

Com este documento, a Fase 1 está **100% concluída**.

Tudo declarado: schemas, lifecycle, filesystem. Próxima sessão começa Fase 2
sem ambiguidade sobre onde nada vive.

### O que sobra pra próxima fase

```
Fase 2 — Cérebros (agents)
  ├ 6 roteiros de UX restantes
  └ 9 sub-agent prompts
  
Fase 3 — Conteúdo
  ├ 16 templates
  └ 12 cards canônicos

Fase 4 — Músculos (código)
  ├ Bash dispatcher
  └ Python engine

Fase 5 — Pele e validação
  ├ Hooks
  ├ Validators
  └ E2E tests
```

Ver `docs/design/04-pending.md` pra checklist completa.

---

## 10. Constraints implícitas que este layout cristaliza

1. **Tudo é localizado em uma das 3 raízes.** Sem arquivos órfãos em `/tmp`,
   no `$HOME`, ou em paths absolutos arbitrários.
2. **Cada arquivo tem um owner único.** Nunca dois agentes escrevem o mesmo
   arquivo simultaneamente (concorrência resolvida por design, não por lock).
3. **Snapshots são imutáveis dentro de uma instalação.** Cards em
   `.claude/cards/` só mudam via `forge reconfigure` → menu cards →
   "atualizar card do canonical" (escolha explícita do usuário).
4. **Memory L1 vive ao lado do código, mas fora do git.** Continuidade local
   sem poluir histórico do time.
5. **Memory L2 é shared no git.** Time inteiro herda aprendizado.
6. **Graph é rebuildable.** Nunca depende dele estar correto pra workflow
   funcionar — só pra ser rápido.
7. **Hooks são thin shims.** Lógica em `forge ingest`, nunca nos hooks.

Estes invariantes guiam **toda decisão de implementação** nas Fases 4-5.
