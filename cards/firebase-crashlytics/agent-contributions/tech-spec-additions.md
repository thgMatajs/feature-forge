<!--
Injected into: tech-spec-agent
Extension-point: section:Observability hooks
Target artifact: tech-spec.md
Card: crashlytics
-->

## Crashlytics observability — physical layout and runtime contract

When this card is active, your `tech-spec.md` MUST include — under
"Observability hooks" or an equivalent subsection — the following:

### Shared exception class

Declare the file path explicitly. Canonical layout:

```
shared/feature/{feature}/src/commonMain/kotlin/
  br/com/{org}/{app}/shared/feature/{feature}/analytics/
    Firebase{Feature}AnalyticsException.kt
```

Forma:

```kotlin
class Firebase{Feature}AnalyticsException(
    val errorCode: String,
    val causeType: String,
    cause: Throwable? = null,
) : Throwable(message = "$errorCode/$causeType", cause = cause)
```

One class per feature. Do NOT centralize across features — paridade
Analytics↔Crashlytics depende do nome único.

### Tracker invocation

In the tracker implementation (`{Feature}AnalyticsImpl` in shared or per
platform), every `*_error` event must:

1. `analytics.logEvent(...)` with `error_code` + `cause_type` params.
2. Immediately after, `crashReporter.recordException(Firebase{Feature}AnalyticsException(errorCode, causeType, cause))`.
3. Before step 2, set custom keys for breadcrumb context:
   `setCustomKey("feature", "{feature}")`,
   `setCustomKey("screen", currentScreen)`,
   `setCustomKey("user_type", session.userType)`.

### Abstraction over Firebase

In shared code, do NOT import `com.google.firebase.crashlytics.*` directly
— that ties commonMain to the Android SDK. Use a `CrashReporter` interface
from `shared/core/observability/` whose `actual` implementations call
the SDK on Android (Kotlin) and iOS (via SKIE bridge).

If the project does not yet have `CrashReporter`, declare it as a
cross-feature reusability candidate (see "Cross-feature reusability
candidates" section) so the next feature inherits the abstraction.

### Opt-out path

Document in this section how the feature respects telemetry consent:

- `CrashlyticsManager.setCollectionEnabled(consent.crashReporting)` is
  called at app boot.
- Any feature-level fallback that ignores the flag is forbidden — there is
  no "this error is important enough to bypass consent."

### Test plan implication

Add to "Test plan summary":

- Unit test: tracker exposing `*_error` invokes `crashReporter.recordException`
  with the expected exception class instance carrying matching
  `(errorCode, causeType)`. Use a fake `CrashReporter`.
- Unit test: tracker DOES NOT call `recordException` for non-`_error`
  events.

### Threats and edge cases

- **Re-entry / double logging**: if `recordException` is called twice for
  the same logical error (e.g., retry path), Crashlytics deduplicates by
  stack — but Analytics counts twice. Resolution: log the event exactly
  once at the boundary where the error becomes terminal.
- **Loss of `cause`**: when crossing the iOS bridge, original `NSError`
  may not preserve causal chain. The `cause:` parameter is best-effort,
  not contractual.
