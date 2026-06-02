# Schema — `card.yaml`

A **card** is the atomic composition unit of feature-forge. Every capability
(language, framework, DI pattern, backend service, navigation pattern)
declares itself as a card. Presets are aliases for card combinations, not
fixed structures.

## Philosophy

A card is **NOT**:
- A skill, plugin, or runtime extension
- A code generator
- A wrapper around a framework

A card **IS**:
- A declarative manifest that says "when this capability is active, contribute
  these templates, these validators, these agent prompts, these hooks"
- A static bundle of files
- A composable unit with explicit dependencies and conflicts

Cards are merged by the engine into the active workflow. A project with
12 cards active has merged contributions from all 12 in a deterministic order.

## Where cards live

Cards have two physical locations:

**Canonical (source of truth):**

```
~/Documents/feature-forge/cards/{card-name}/
```

All cards are siblings here, regardless of preset. A card can be referenced by
multiple presets.

**Snapshot (per project):**

```
{project}/.claude/cards/{card-name}/
```

When `forge init` activates a card, it **copies** the canonical version into
the project's snapshot folder. Edits to the snapshot are local; edits to the
canonical are upstream.

The sha256 of each snapshot is recorded in `workflow-config.yaml` for
integrity verification by `forge doctor`.

## Card anatomy

```
cards/{card-name}/
├── card.yaml                       manifest — see schema below
├── README.md                       human-readable description
├── templates/                      files contributed to feature packages
│   ├── tech-spec-section.md
│   ├── task-contract-fragment.yaml
│   └── ...
├── validators/                     scripts that run as part of workflow
│   ├── check-koin-modules.py
│   └── ...
├── agent-contributions/            prompt fragments injected into sub-agents
│   ├── contract-planner-additions.md
│   ├── tech-spec-additions.md
│   └── ...
├── hooks/                          event-driven scripts
│   └── post-edit-koin-module.sh
├── detection/                      how init detects this card should activate
│   └── signals.yaml
└── examples/                       reference usage (informational)
    └── ...
```

Required files: `card.yaml`, `README.md`. Everything else is optional and
declared via `card.yaml`.

## Optional top-level `legacy-marker` (since v1.1)

`legacy-marker: bool` é campo opcional top-level (default `false`) que sinaliza
ao init que este card provê uma capability em forma legacy. Quando 2+ cards
ativos proveem a mesma capability label e ao menos um carrega
`legacy-marker: true`, init Step 7.5 surfaca prompt 3-caminhos antes de
materializar o plan (manter legacy / migrar / coexistir).

Política de versionamento: adição é aditiva, `schema-version` permanece `1`.
Cards existentes (todos os 20 v1.1) seguem válidos sem mexer. Promoção a
schema-version 2 só acontece em mudança breaking (remoção, mudança de tipo,
novo required field).

Validator (`validate_card_yaml.py`) aceita o campo intacto — quem age sobre
o valor é o init Step 7.5.

## The `card.yaml` schema (full annotated)

```yaml
# cards/{card-name}/card.yaml
# ──────────────────────────────────────────────────────────────────────────
# Schema version: 1
# Read by:        forge init (detection + install), forge doctor (validation),
#                 engine resolver (dependency + conflict + merge)
#
# Capability labels (`provides`, `requires`, `conflicts-with`) MUST come from
# the canonical catalog: docs/schemas/capability-labels.md (v1 = 35 labels).
# Any label used here that is absent from the catalog is a CARD-* validation
# error in forge doctor.
# ──────────────────────────────────────────────────────────────────────────

schema-version: 1


# ── IDENTITY ──────────────────────────────────────────────────────────────
identity:
  name:        koin-annotations              # filesystem-safe slug, [a-z0-9-]+
  version:     1.0.0                          # semver
  description: "Koin Annotations DI for KMP/Android with @Module @ComponentScan"
  category:    dependency-injection           # grouping for menu listing inside `forge reconfigure`
                                              # one of: language, kmp, ui,
                                              # di OR dependency-injection,
                                              # navigation, backend, persistence,
                                              # network, observability, auth,
                                              # storage, testing, build,
                                              # design-system, ticketing
  maturity:    stable                         # one of: experimental, beta, stable, deprecated
  maintainer:  feature-forge-core             # who owns this card
  created-at:  2026-05-15
  last-updated: 2026-05-28
  license:     MIT


# ── LEGACY MARKER ─────────────────────────────────────────────────────────
# Campo top-level opcional, aditivo ao schema v1 (não bumpa schema-version).
# Quando true, sinaliza ao init Step 7.5 que este card provê uma capability
# em forma legacy — caso 2+ cards proveem a mesma label e ao menos um tem
# legacy-marker: true, o init dispara prompt 3-caminhos (manter legacy /
# migrar pro moderno / coexistir explicitamente) antes de materializar o plan.
# Default ausente = false.
legacy-marker: false


# ── CAPABILITIES ──────────────────────────────────────────────────────────
# Abstract things this card provides. Other cards depend on these labels,
# not on this card's name directly.
provides:
  - dependency-injection
  - kmp-di
  - android-di


# ── DEPENDENCIES — capabilities this card requires ────────────────────────
# Listed as capability labels (provided by some other card).
# Resolver finds at least one active card providing each.
requires:
  - kotlin-language


# ── CONFLICTS — capabilities incompatible with this card ──────────────────
# If any active card provides any of these, this card cannot be installed.
# Listed as capability labels OR specific card names.
conflicts-with:
  - hilt-di           # capability label
  - koin-dsl          # capability label  
  - manual-di         # capability label


# ── CONTRIBUTIONS — what this card adds to the system ─────────────────────
contributes:
  
  # Template fragments — inserted into feature package documents
  templates:
    - target:  tech-spec.md
      section: "DI Strategy"
      file:    templates/di-section.md
      merge:   append-section          # one of: append-section, replace-section, before-section, after-section
    
    - target:  task-contract.yaml
      section: "allowed-files-koin-modules"
      file:    templates/koin-allowed-files.yaml
      merge:   merge-keys              # for YAML: merge top-level keys

  # Validators — scripts that run at specific lifecycle points
  validators:
    - name:     validate-koin-modules
      file:     validators/check-koin-modules.py
      runs-on:  [pre-commit, verify-task]
      severity: error                   # one of: warn, error, block
      description: "Ensure @Module annotations are paired with @ComponentScan"

  # Agent prompts — fragments injected into sub-agents at extension points
  agent-prompts:
    - inject-into:     contract-planner-agent
      extension-point: "after:Strategy"     # see "Agent Extension Points" below
      file:            agent-contributions/contract-planner-additions.md
    
    - inject-into:     tech-spec-agent
      extension-point: "section:DI Strategy"
      file:            agent-contributions/tech-spec-additions.md
    
    - inject-into:     task-contract-writer
      extension-point: "after:Allowed Files"
      file:            agent-contributions/task-writer-additions.md

  # Hooks — event-driven scripts
  hooks:
    - file:    hooks/post-edit-koin-module.sh
      events:  [post-edit]
      glob:    "**/*Module.kt"
      events-mapping:                    # passed as ENV to the hook
        FILE: "$1"

  # Config defaults — values this card sets if no other card or user input
  # provides them. Resolver merges with user-provided values winning.
  config-defaults:
    conventions.di-pattern: koin-annotations


# ── DETECTION — how `forge init` knows to activate this card ──────────────
detection:
  signals:
    - type:       file-content
      glob:       "**/*.kt"
      contains:   "@Module"
      confidence: 0.4
    
    - type:       file-content
      glob:       "**/*.kt"
      contains:   "@ComponentScan"
      confidence: 0.4
    
    - type:       dependency
      file:       "**/build.gradle*"
      contains:   "koin-annotations"
      confidence: 0.5
  
  threshold: 0.6           # cumulative confidence ≥ 0.6 → auto-activate
                           # < 0.6 → ask user during init
  
  alternative-cards:       # if detection fails, what else might match?
    - koin-dsl             # if @Module not found but `single { ... }` is
    - hilt-di              # if @HiltAndroidApp is found instead


# ── DOCUMENTATION ─────────────────────────────────────────────────────────
documentation:
  readme:      README.md           # full description
  examples:    examples/           # reference usage
  rules-link:  "kotlin-idioms"     # rule slug in project's .claude/rules/ that
                                   # this card aligns with (if any)
```

## Contribution types in depth

### Templates

Cards contribute fragments to feature package documents. The engine knows
the canonical structure of each document (its sections) and merges fragments
in deterministic order.

**Merge modes:**

| Mode | Behavior |
|---|---|
| `append-section` | Add as a new section at end (or before a named section) |
| `replace-section` | Replace an existing section entirely |
| `before-section: X` | Insert before existing section `X` |
| `after-section: X` | Insert after existing section `X` |
| `merge-keys` | For YAML files, merge top-level keys (cards must not conflict on keys) |

**Conflict resolution at merge:**

If two cards both contribute `append-section: "DI Strategy"` to `tech-spec.md`,
the engine appends both, ordered by card name alphabetically. Cards can
declare `merge-order: <N>` to override (lower N = earlier).

### Validators

Cards contribute scripts that run at specific lifecycle points. The engine
collects all active validators and runs them at the declared point.

**Runs-on values:**

| Value | When |
|---|---|
| `pre-commit` | Before commit hook |
| `pre-push` | Before push |
| `verify-task` | During `forge verify` |
| `forge-doctor` | On `forge doctor` |
| `post-init` | After `forge init` completes |
| `post-reconfigure` | After `forge reconfigure` |

**Severity:**

| Value | Behavior |
|---|---|
| `warn` | Log warning, do not block |
| `error` | Log error, block if part of a hard gate |
| `block` | Always block |

### Agent prompts

Cards inject prompt fragments into sub-agents at declared **extension points**.

#### Agent extension points

Each agent declares extension points in its frontmatter:

```yaml
# agents/contract-planner-agent.md frontmatter
extension-points:
  - id: "before:Strategy"
    purpose: "Card-specific context before strategy section"
  - id: "after:Strategy"
    purpose: "Card-specific addendums to strategy"
  - id: "section:DI Strategy"
    purpose: "DI-specific contract considerations"
  - id: "examples:end"
    purpose: "Card-specific worked examples"
```

Cards target by `extension-point: <id>`. The engine inlines the contribution
at that point when the agent is invoked.

#### Resolution order at extension point

If multiple cards inject into the same extension point:

1. Sort by card name alphabetically
2. Override with explicit `merge-order: <N>` (lower first)
3. Insert with separator `\n\n---\n\n` between contributions

This is deterministic and stable across runs.

### Hooks

Cards contribute hook scripts. The engine registers active card hooks in
`.claude/hooks/` during install and removes them on uninstall.

**Glob filtering:** hooks fire only when the event payload matches `glob`.
Example: `post-edit` event for `path/to/foo.kt` fires hooks with
`glob: "**/*.kt"` but not hooks with `glob: "**/*.swift"`.

### Config defaults

Cards declare values that should populate `workflow-config.yaml` if nothing
else provides them. Conflict resolution: **user-provided > card-default**.

If two cards declare conflicting defaults for the same key, the engine
errors at install (one of them must be removed or made non-default).

## Detection mechanism

`forge init` walks the repo and evaluates each known card's detection signals
in parallel. For each card:

```
total_confidence = sum(matched_signals_confidence)

if total_confidence >= threshold:
   auto-activate
elif total_confidence >= 0.3:
   ask user to confirm
else:
   do not activate
```

### Signal types

| Type | Schema |
|---|---|
| `file-exists` | `glob: <pattern>` |
| `file-content` | `glob: <pattern>` + `contains: <string>` or `matches: <regex>` |
| `dependency` | `file: <pattern>` + `contains: <string>` (e.g., for gradle/package.json) |
| `directory-exists` | `path: <relative>` |
| `command-success` | `command: <string>` (rare, use sparingly) |

Detection runs in **parallel** across all cards. Timeout per card: 2s.
Card that exceeds timeout = signal failure, not error.

## Resolver behavior

When `forge init` activates a set of cards (auto-detected or user-chosen),
the engine resolves them:

### Step 1 — Dependency check

For each card, every `requires:` capability must be provided by another
active card. If missing:

- If the missing capability is provided by exactly one known card, suggest
  activating it.
- If multiple options, ask user.
- If none known, error.

### Step 2 — Conflict check

For each card, every `conflicts-with:` capability or name must NOT be
provided by any other active card. If conflict:

- Error: "Cannot activate `koin-annotations` because `hilt-di` is also
  active (both provide `dependency-injection`)."
- User must remove one.

### Step 3 — Topological sort

Cards are sorted by dependency order. Result is deterministic.

### Step 4 — Contribution merge

For each contribution type (templates, validators, agent-prompts, hooks):

1. Collect all contributions from all active cards.
2. Group by target (e.g., all contributions to `tech-spec.md`).
3. Within each group, sort by `merge-order` (default 50), then alphabetic.
4. Apply merge mode (append-section, replace-section, etc.).
5. Validate result (e.g., no duplicate section headers).

### Step 5 — Defaults application

Apply all `config-defaults:` to `workflow-config.yaml`. Conflicts at this
step are install-time errors.

## Card lifecycle

> Card lifecycle operations are **not** addressed by dedicated subcommands.
> They live as interactive menu options inside `forge init` (initial install)
> and `forge reconfigure` (any post-init mutation). See
> `docs/design/06-command-surface.md` for the formal command-surface mapping:
> 12 commands, zero flags, all parameterization via interactive prompts.
>
> Menu options inside `forge reconfigure` → cards section:
> - "adicionar card"          → triggers Install protocol
> - "atualizar card do canonical" → triggers Update protocol
> - "remover card"            → triggers Remove protocol
> - "travar edição local"     → marks `pinned: true`, no install/update/remove
> - "inspecionar card"        → read-only; shows sha256, conflicts, contributions

### Install (triggered by `forge init` or `forge reconfigure` menu choice "adicionar card")

```
1. Validate card.yaml against schema
2. Run dependency + conflict check
3. Compute sha256 of all files in cards/{name}/
4. Copy cards/{name}/ → .claude/cards/{name}/
5. Add entry to workflow-config.yaml cards.active with sha256
6. Re-run merge for all contribution types
7. Re-install hooks (.claude/hooks/)
8. Run any `post-install` script declared by card (rare)
```

### Update (triggered by `forge reconfigure` menu choice "atualizar card do canonical")

```
1. Compute new sha256 from canonical
2. Diff old snapshot vs new canonical
3. Show diff to user
4. If accepted:
   a. Backup .claude/cards/{name}/ → .claude/cards/{name}/.bak/
   b. Re-copy from canonical
   c. Update sha256 in workflow-config.yaml
   d. Re-run merge + hooks
5. If rejected: keep current snapshot, mark card as `pinned: true`
```

### Remove (triggered by `forge reconfigure` menu choice "remover card")

```
1. Check no other active card requires this card's capabilities
   (if yes, error — must remove dependents first)
2. Remove .claude/cards/{name}/
3. Remove entry from workflow-config.yaml cards.active
4. Remove hooks contributed by this card
5. Re-run merge for contribution types (other cards remain)
6. Suggest cleanup of artifacts this card may have inspired (manual)
```

## Validation of `card.yaml`

Schema validators enforced when card is loaded:

```text
CARD-001  schema-version must be in [1]
CARD-002  identity.name must match [a-z0-9-]+, max 40 chars
CARD-003  identity.version must be valid semver
CARD-004  identity.category must be in known categories
CARD-005  identity.maturity must be one of allowed values
CARD-006  provides must be non-empty list of capability labels
CARD-007  requires must reference known capability labels
CARD-008  conflicts-with must reference known labels or card names
CARD-009  contributes.templates.* targets must reference known package documents
CARD-010  contributes.validators.* files must exist and be executable
CARD-011  contributes.agent-prompts.* inject-into must reference known agents
CARD-012  contributes.agent-prompts.* extension-point must exist in target agent
CARD-013  contributes.hooks.* events must be in known event list
CARD-014  contributes.config-defaults.* keys must exist in workflow-config schema
CARD-015  detection.signals.threshold ∈ [0.0, 1.0]
CARD-016  detection.signals confidence sum cannot exceed 2.0 (sanity check)
CARD-017  no circular dependency in requires graph
CARD-018  README.md must exist
```

## Examples

### Example A — a leaf card with no dependencies

```yaml
# cards/kotlin-language/card.yaml
schema-version: 1

identity:
  name: kotlin-language
  version: 1.0.0
  description: "Kotlin as primary language for shared and Android"
  category: language
  maturity: stable

provides:
  - kotlin
  - jvm-language

requires: []         # no dependencies — this is a leaf

conflicts-with: []

contributes:
  agent-prompts:
    - inject-into: tech-spec-agent
      extension-point: "section:Shared (KMP) layer"
      file: agent-contributions/kotlin-conventions.md

  config-defaults:
    conventions.test-pattern.framework-shared: kotlin-test

detection:
  signals:
    - type: file-exists
      glob: "**/*.kt"
      confidence: 0.5
    - type: file-content
      glob: "**/settings.gradle*"
      contains: "kotlin"
      confidence: 0.4
  threshold: 0.6
```

### Example B — a card that depends on others

```yaml
# cards/compose-screens/card.yaml
schema-version: 1

identity:
  name: compose-screens
  version: 1.0.0
  description: "Jetpack Compose for Android UI"
  category: ui
  maturity: stable

provides:
  - android-ui
  - compose

requires:
  - kotlin
  - android-platform

conflicts-with:
  - android-xml-views

contributes:
  templates:
    - target: tech-spec.md
      section: "UI — Android"
      file: templates/compose-tech-spec-section.md
    - target: task-contract.yaml
      section: "compose-file-patterns"
      file: templates/compose-allowed-files.yaml
  
  validators:
    - name: validate-compose-suppress-banned
      file: validators/check-no-suppress.py
      runs-on: [pre-commit]
      severity: error
  
  agent-prompts:
    - inject-into: screen-analysis-agent
      extension-point: "after:Component Detection"
      file: agent-contributions/compose-component-hints.md
    - inject-into: tech-spec-agent
      extension-point: "section:UI Strategy"
      file: agent-contributions/compose-tech-spec.md
  
  config-defaults:
    conventions.folder-layout.android: "{screen}Screen.kt + {Screen}Content.kt + {Screen}Components.kt"

detection:
  signals:
    - type: file-content
      glob: "**/*.kt"
      contains: "androidx.compose"
      confidence: 0.5
    - type: file-content
      glob: "**/build.gradle*"
      contains: "androidx.compose"
      confidence: 0.4
  threshold: 0.6
  alternative-cards:
    - android-xml-views
```

### Example C — a backend-persistence card (split)

The legacy `firebase-firestore` card was split into three composable cards on
Phase 3.5: `firestore-persistence` (CRUD + queries), `firestore-realtime`
(snapshot listeners) and `firestore-security-rules` (rules + tests). The
manifest below describes the persistence half; `firestore-rules` and snapshot
listeners are now declared by sibling cards.

```yaml
# cards/firestore-persistence/card.yaml
schema-version: 1

identity:
  name: firestore-persistence
  version: 1.0.0
  description: "Cloud Firestore CRUD + one-shot queries for KMP/Android/iOS"
  category: persistence
  maturity: stable

provides:
  - persistence-server
  - api-contract-firebase-sdk

requires:
  - kotlin
  - firebase-platform

conflicts-with:
  - persistence-server         # other backends providing the same capability
                               # (rest-stack, room-local-only, etc.)

contributes:
  templates:
    - target: data-contract-spec.yaml
      section: "firestore_collections"
      file: templates/firestore-persistence-data-contract.yaml
      merge: merge-keys

  validators:
    - name: validate-firestore-indexes
      file: validators/check-firestore-indexes.py
      runs-on: [verify-task]
      severity: warn
      description: "Each custom one-shot query needs a matching firestore.indexes.json entry."

  agent-prompts:
    - inject-into: contract-planner-agent
      extension-point: "section:Data Contract"
      file: agent-contributions/contract-planner-additions.md
    - inject-into: tech-spec-agent
      extension-point: "section:Shared (KMP) layer"
      file: agent-contributions/tech-spec-additions.md

detection:
  signals:
    - type: file-exists
      glob: "**/google-services.json"
      confidence: 0.3
    - type: file-content
      glob: "**/build.gradle*"
      contains: "firebase-firestore"
      confidence: 0.5
    - type: file-content
      glob: "**/*.kt"
      contains: "FirebaseFirestore"
      confidence: 0.2
  threshold: 0.5
```

> Note: snapshot listeners and security rules are declared by sibling cards
> (`firestore-realtime`, `firestore-security-rules`). Each one carries its own
> templates, validators and agent prompts — features that need them activate
> the additional cards alongside `firestore-persistence`.

## Edge cases

### Two cards both want to be the DI provider

```text
Active set: { koin-annotations, hilt-di }
Both provide: dependency-injection
Both conflict-with: each other
```

Result: install-time error. User must remove one.

### Card depends on capability not provided

```text
Active set: { compose-screens }
compose-screens requires: kotlin, android-platform
Active provides: { android-ui, compose }
Missing: kotlin (provided by kotlin-language)
       : android-platform (provided by android-base-card)
```

Result: install-time error. Prompt to add the providers.

### Card was active, now removed, contribution lingers

When a card is removed, its contributions are removed from merged outputs.
But files already written (e.g., feature packages from past features) are
NOT modified retroactively. The contribution lives in committed history.

Recovery: run `forge reconfigure` and pick "rebuild templates" from the menu
(no flag). Regenerates templates from current active card set. Existing
feature packages are untouched.

### Card was upgraded mid-feature

When the "atualizar card do canonical" menu option inside `forge reconfigure`
runs during an active feature (forge plan or forge implement in progress):

- New snapshot of X is in place
- Current feature's open-questions/decisions reference OLD merged output
- Mismatch may cause confusion

Mitigation: reconfigure refuses entirely when an L1 lock is active (per
`memory.md` §L1 as a lock mechanism) — the user must pause/finish the feature
first. Override is not a flag; it's an explicit interactive confirmation in
the reconfigure menu when the lock is in `paused` state.

## Out of scope for v1

- **Marketplace of cards** — only canonical cards from this repo for v1
- **Per-card semver dependencies** — cards depend on capability labels, not
  on other cards' specific versions
- **Card discovery from arbitrary URLs** — cards live in canonical home only
- **Card-level i18n** — card descriptions and prompts are EN/PT-BR mixed,
  not formally translated

## Related schemas

- `workflow-config.yaml` — references active cards, sha256, version
- (future) Card resolver internal state — not exposed
- (future) Agent extension-points spec — referenced here, formalized later
