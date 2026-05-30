# Schemas — `.claude/inventory/*.yaml`

The inventory is the **factual snapshot** of the project as observed at
`forge init` (or refreshed by `forge reconfigure`). It is the engine's
read-mostly reference for what exists in the codebase: components, strings,
conventions, structural patterns.

Three files, each with its own schema.

## Distinguishing inventory from config / memory / graph

| Where | Question it answers |
|---|---|
| `workflow-config.yaml` | "What did we **choose**?" |
| `inventory/*.yaml` | "What **exists**?" |
| `memory/L*.yaml` | "What did we **learn**?" |
| `graph.db` | "How is it **connected**?" |

Inventory is "what exists" — refreshed when reality changes.

---

## `inventory/design-system.yaml`

What design system components are catalogued, where they live, what state
they're in.

### Schema (annotated)

```yaml
schema-version: 1
last-scan:       2026-05-28T14:33:11Z
scan-confidence: 0.94                 # 0-1, how confident the auto-detection was

# How was the design system detected?
detection:
  naming-pattern: "Meo*"               # detected by frequency in component dirs
  alternative-patterns-considered: ["App*", "Ds*", "DS*"]
  base-paths:
    android: androidApp/core/designsystem/src/main/kotlin/.../designsystem
    ios:     iosApp/iosApp/DesignSystem
    web:     webApp/src/shared/components

# Components catalogued
components:
  - id: meo-button
    name: MeoButton
    level: atom                        # atom | molecule | organism | template | model
    status: beta                       # stable | beta | legacy | deprecated | planned | unknown
    paths:
      android: androidApp/core/designsystem/.../atoms/MeoButton.kt
      ios:     iosApp/iosApp/DesignSystem/Atoms/MeoButton.swift
      web:     webApp/src/shared/components/atoms/MeoButton/MeoButton.tsx
    api:
      params: [label, onClick, variant, enabled, loading]
      variants: [primary, secondary, tertiary]
      states: [default, hover, pressed, disabled, loading]
    used-in:
      - feature: auth
        screens: [login, register]
      - feature: bonsai
        screens: [bonsai-detail]
    has-preview: true                  # @Preview / #Preview present?
    has-tests: true
    last-modified: 2026-04-12
    docs-manifest: docs/design-system/components/meo-button/

# Tokens
tokens:
  colors:
    pattern: semantic                  # semantic | numeric | hybrid
    names:
      - primary
      - on-primary
      - surface
      - on-surface
      - outline
      - error
    values:
      primary:
        light: "#496900"
        dark:  "#BAFF29"

  spacing:
    pattern: named                     # named | numeric
    values:
      xs: 4
      sm: 8
      md: 12
      lg: 16
      xl: 20
      xxl: 24
      xxxl: 32
      huge: 48
      giant: 64

  typography:
    - name: headline
      family: "Plus Jakarta Sans"
      weights: [400, 500, 700]
    - name: body
      family: "DM Sans"
      weights: [400, 500]

  radii:
    pattern: named
    values:
      none: 0
      xs: 4
      sm: 8
      md: 12
      lg: 16
      xl: 20
      full: 9999

# Coverage analysis
coverage:
  total-components: 28
  by-level:
    atom: 8
    molecule: 14
    organism: 6
  by-status:
    stable: 4
    beta: 24
  parity:
    android-ios: 0.96                  # 27/28 components exist on both
    android-only: []
    ios-only: [MeoTopBarVariant]
    web-only: []
  notes:
    - "Web has legacy components — see legacy-components"

# Legacy components (not in canonical Meo* set but still in repo)
legacy-components:
  - id: web-button
    name: Button
    paths:
      web: webApp/src/shared/components/atoms/Button/Button.tsx
    status: legacy
    note: "Pre-Meo design system component; use MeoButton instead"
```

### Refresh triggers

- `forge init` — full scan
- `forge reconfigure` — full re-scan with diff
- `forge ingest --event post-commit` if commit touches files matching
  `inventory/design-system.yaml.refresh-globs` (configurable)
- Manual: via menu de `forge reconfigure` → "re-extrair inventory design-system"

> **`forge ingest` is the internal event-router invoked by hooks.** It is not
> part of the 12 user-facing commands and is not typed manually. See
> `docs/design/06-command-surface.md` § "Hidden internal entrypoints".

### Validation rules

```text
INV-DS-001  schema-version must be 1
INV-DS-002  every component must have at least one platform path
INV-DS-003  status must be in allowed set
INV-DS-004  level must be in allowed set
INV-DS-005  if has-preview is true, path file must contain "@Preview" or "#Preview"
INV-DS-006  tokens.spacing.pattern must match value structure (named ↔ keys are strings)
INV-DS-007  coverage.* must reflect components count
INV-DS-008  parity.android-only + ios-only + web-only must not overlap
```

---

## `inventory/i18n.yaml`

Internationalization keys, locales, source of truth, generation scripts.

### Schema (annotated)

```yaml
schema-version: 1
last-scan:       2026-05-28T14:33:11Z

# Where keys live (source of truth)
source-of-truth:
  path:           shared/resources/i18n
  format:         json-per-locale     # json-per-locale | xml-per-locale | toml | csv | other
  locales:        [pt-BR, en-US, es-ES]
  primary-locale: pt-BR

# Build pipeline
generation:
  script: scripts/i18n/generate.py
  outputs:
    android: composeApp/src/main/res/values*/strings.xml
    ios:     iosApp/iosApp/Resources/*.lproj/Localizable.strings
    web:     webApp/src/shared/i18n/locales/*.json

verification:
  script: scripts/i18n/verify.py
  checks: [no-orphan-keys, all-locales-complete, naming-consistent]

# Naming convention
naming:
  pattern: "screen.element.action"
  segments:
    - description: "feature or screen scope"
      examples: [auth, bonsai, register]
    - description: "element or section"
      examples: [field, button, snackbar, title]
    - description: "modifier or action (optional)"
      examples: [error, hint, label]
  examples:
    - "auth.register.field.password.error"
    - "bonsai.list.empty.title"

# Stats
stats:
  total-keys: 487
  by-locale:
    pt-BR: 487
    en-US: 487
    es-ES: 487
  parity: 1.0                       # all locales have all keys
  missing-translations: []

# Keys grouped by feature (fast lookup)
keys-by-feature:
  auth:
    count: 67
    keys-sample: ["auth.login.title", "auth.register.cta", ...]
  bonsai:
    count: 89
    keys-sample: ["bonsai.list.title", ...]

# Orphan keys (defined but not used anywhere — surfaced by graph)
orphan-keys: []                     # ideally empty

# Hardcoded strings detected (should be migrated to keys)
hardcoded-detected: []
```

### Refresh triggers

- `forge init` — full scan
- `forge reconfigure` — full re-scan
- `forge ingest --event post-edit` for files matching i18n source globs
  (internal event-router; see note above)
- Manual: via menu de `forge reconfigure` → "re-extrair inventory i18n"

### Validation rules

```text
INV-I18N-001  schema-version must be 1
INV-I18N-002  source-of-truth.path must exist
INV-I18N-003  generation.script must exist and be executable
INV-I18N-004  verification.script must exist and be executable
INV-I18N-005  parity must reflect actual key counts per locale
INV-I18N-006  orphan-keys — warn if > 5 entries
INV-I18N-007  hardcoded-detected — warn if > 0 entries
INV-I18N-008  naming.pattern must be parsable (segments adjacent to value examples)
```

---

## `inventory/conventions.yaml`

Coding and architectural conventions extracted from existing features.

### Schema (annotated)

```yaml
schema-version: 1
last-scan:       2026-05-28T14:33:11Z

# Where were conventions extracted from?
extraction:
  sources:
    - feature: auth
      modules: [shared/feature/auth, androidApp/feature/auth, iosApp/.../Auth]
    - feature: bonsai
      modules: [shared/feature/bonsai, androidApp/feature/bonsai, iosApp/.../Bonsai]
    - feature: register
      modules: [shared/feature/register, ...]
  features-analyzed: 3
  confidence: 0.92                  # higher = more consistent across features

# Folder layout per platform
folder-layout:
  android:
    pattern: "{screen}Screen.kt + {Screen}Content.kt + {Screen}Components.kt + {Screen}Mappers.kt"
    rationale: "Stateful host + stateless content + helpers + mappers"
    examples-where-applied:
      - androidApp/feature/auth/.../ui/login/LoginScreen.kt
      - androidApp/feature/auth/.../ui/login/LoginContent.kt
  ios:
    pattern: "{Screen}ScreenView.swift + {Screen}ScreenContentView.swift + {Screen}Components.swift"
    examples-where-applied:
      - iosApp/iosApp/Features/Auth/Login/LoginScreenView.swift
  shared:
    pattern: "ViewModel + UseCase(s) + Repository (impl + interface)"
    examples-where-applied:
      - shared/feature/auth/.../presentation/LoginViewModel.kt

# State pattern
state-pattern:
  name: stateui                     # stateui | stateflow-pure | custom-sealed
  type: "StateUI<T>"
  sealed-class-location: shared/core/state/StateUI.kt
  examples-where-applied:
    - LoginViewModel uses StateUI<LoginUI>

# DI pattern
di-pattern:
  name: koin-annotations
  annotations-used: ["@Module", "@ComponentScan", "@Single", "@Factory", "@KoinViewModel"]
  scope-strategy: per-feature-module
  ios-strategy: factory-functions   # iOS doesn't run Koin runtime
  ios-factory-naming: "create{ClassName}()"

# Test pattern
test-pattern:
  frameworks:
    android: junit5
    shared:  kotlin-test
    ios:     swift-testing
  flow-assertion: turbine
  type-assertion: assertIs<T>()
  fakes-vs-mocks: fakes-preferred
  required-scenarios:               # mandatory per .claude/rules/testing.md
    - happy-path
    - null-empty-input
    - network-io-failure
    - loading-guard
    - unknown-value

# Naming conventions
naming:
  service:     "{Feature}Service"
  dto:         "{Entity}Response | {Entity}Request"
  room-entity: "{Entity}Entity | {Feature}Dao | {Feature}Database"
  domain-model: "PascalCase, no suffix (e.g., Bonsai, UserSession)"
  repository:  "{Feature}Repository | {Feature}RepositoryImpl"
  usecase:     "{Verb}{Noun}UseCase"
  viewmodel:   "{Feature}{Concept}ViewModel"
  ui-model:    "{Concept}UI | {Concept}UIEvents"

# Branch / commit conventions
branch:
  pattern: "feature/{slug}"
  examples:
    - feature/auth-register
    - feature/bonsai-list

commit:
  format: conventional-commits     # conventional-commits | semantic | freeform
  examples:
    - "feat(auth): add password strength indicator"
    - "fix(bonsai): handle empty state"

# Comment conventions (from .claude/rules/kotlin-idioms.md)
comments:
  policy: kdoc-for-non-obvious-contracts
  inline-allowed: false
  emoji-in-code: false

# Quality thresholds
quality:
  cyclomatic-complexity-max: 15
  block-depth-max: 4
  lines-per-class-max: 600
  functions-per-class-max: 15

# Conflicts detected (warn — multiple patterns coexist)
conflicts-detected: []              # empty = single consistent pattern

# Cross-references to project rules
rule-references:
  - .claude/rules/architecture.md
  - .claude/rules/architecture_kmp.md
  - .claude/rules/architecture_android.md
  - .claude/rules/architecture_ios.md
  - .claude/rules/kotlin-idioms.md
  - .claude/rules/testing.md
  - .claude/rules/design-system.md
  - .claude/rules/observability.md
```

### Refresh triggers

- `forge init` — extract from existing features
- `forge reconfigure` — re-extract with diff
- `forge ingest --event feature-done` — re-confirm patterns held

### Validation rules

```text
INV-CONV-001  schema-version must be 1
INV-CONV-002  extraction.features-analyzed must be > 0 or marked greenfield
INV-CONV-003  extraction.confidence must be in [0, 1]
INV-CONV-004  state-pattern.name must be in allowed values
INV-CONV-005  di-pattern.name must be in allowed values
INV-CONV-006  test-pattern.frameworks per platform must be in allowed values
INV-CONV-007  quality.* values must be > 0 and reasonable
INV-CONV-008  conflicts-detected — warn if non-empty
```

---

## Refresh strategy summary

| Inventory | Refresh trigger | Latency budget |
|---|---|---|
| design-system.yaml | post-commit if DS dir touched | < 5s incremental |
| i18n.yaml | post-commit if i18n source touched OR i18n generation runs | < 3s incremental |
| conventions.yaml | feature-done (re-confirm) OR reconfigure | < 10s full re-extract |

All cheap enough to re-extract incrementally. Full rebuild only on init or
reconfigure.

## Out of scope for v1

- Multi-design-system support (e.g., main DS + brand variant)
- Inventory of analytics events (lives in observability contract, not here)
- Inventory of Firebase collections (lives in data-contract, not here)
- Inventory of feature flags (deferred)
