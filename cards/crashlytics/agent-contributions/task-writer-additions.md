<!--
Injected into: task-contract-writer
Extension-point: after:Allowed Files
Target artifact: tasks/TASK-NNNN.yaml
Card: crashlytics
-->

## Crashlytics integration — allowed_files and validations addendum

When the task you are writing touches analytics (tracker implementation,
exception class introduction, or `*_error` event addition), apply these
additions.

### `allowed_files` patterns to permit (when relevant to the task)

```yaml
allowed_files:
  # Shared exception class (one per feature) — created or modified.
  - "shared/feature/{feature}/src/commonMain/kotlin/**/analytics/Firebase{Feature}AnalyticsException.kt"

  # Tracker interface + impl in shared (or per-platform if shimmed).
  - "shared/feature/{feature}/src/commonMain/kotlin/**/analytics/{Feature}Analytics*.kt"

  # Cross-cutting CrashReporter abstraction (only if this task introduces it).
  - "shared/core/src/commonMain/kotlin/**/core/observability/CrashReporter.kt"
  - "shared/core/src/androidMain/kotlin/**/core/observability/CrashReporter.android.kt"
  - "shared/core/src/iosMain/kotlin/**/core/observability/CrashReporter.ios.kt"

  # Analytics contract artifact (consumed by the validator).
  - ".planning/features/{feature}/analytics-spec.yaml"
```

Do NOT add direct platform Crashlytics imports to feature code outside the
analytics package — that is a code-smell the validator may flag in a
future iteration.

### `validations` block — add validator entry

```yaml
validations:
  - id: crashlytics-shared-exception
    command: "python .claude/cards/crashlytics/validators/check-crashlytics-shared-exception.py {feature}"
    severity: error
    description: "Every *_error event must bind to Firebase{Feature}AnalyticsException."
    runs-on:
      - pre-commit
      - verify-task
```

### Parity check — Android↔iOS

If the task scope includes BOTH platforms (typical for analytics work),
add a manual verification step in the `gates:` block:

```yaml
gates:
  - id: crashlytics-parity
    type: manual
    description: |
      Run the feature on Android and iOS. Force the *_error path. Verify
      both clients emit the SAME (errorCode, causeType) pair to:
        - Analytics console (event params)
        - Crashlytics console (non-fatal exception attributes)
      Mismatch → task is NOT done.
```

### Anti-patterns to encode in `forbidden_patterns:` (if your schema
supports it; otherwise document under `notes:`)

- `recordException(Throwable(...))` — must use the shared exception class.
- `recordException(e)` where `e` is the raw Firebase/Ktor throwable —
  wrap in the shared class with explicit `errorCode/causeType`.
- `setCrashlyticsCollectionEnabled(true)` hard-coded anywhere outside the
  consent gate.
- Importing `com.google.firebase.crashlytics.*` in `commonMain` — must go
  through `CrashReporter`.
