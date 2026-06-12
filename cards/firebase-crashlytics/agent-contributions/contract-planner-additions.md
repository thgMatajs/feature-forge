<!--
Injected into: contract-planner-agent
Extension-point: section:Analytics Contract
Target artifact: analytics-spec.yaml
Card: crashlytics
-->

## Crashlytics binding — required for every `*_error` event

This project uses Firebase Crashlytics as the single crash-reporting
provider. When you author `analytics-spec.yaml`, you MUST emit a
`crashlytics.bindings` entry for every event whose name ends in `_error`.

### Hard rules (validator will block otherwise)

1. **Every event listed in `events:` whose name matches `*_error` requires
   a binding entry under `crashlytics.bindings`.**
2. **The binding's `exception_class:` value must be
   `Firebase{Feature}AnalyticsException`** where `{Feature}` is the
   feature slug PascalCased. Example: feature `auth` →
   `FirebaseAuthAnalyticsException` (reference impl:
   `~/Documents/MeoBonsai/shared/feature/auth/.../data/analytics/FirebaseAuthAnalyticsException.kt`).
   Feature `bonsai-form` → `FirebaseBonsaiFormAnalyticsException`.
3. **`error_code_source:` must point to the event param that carries the
   error code** — by convention `error_code` (snake_case). The string
   logged to Analytics goes verbatim to `errorCode` in the exception.
4. **`cause_type_source:` must point to the event param that carries the
   cause type** — by convention `cause_type`. Same verbatim contract:
   the exception's `causeType` mirrors the Analytics param so the
   console can cross-filter.
5. **`(errorCode, causeType)` reported to Crashlytics MUST be identical
   strings to the values logged in the analytics event** — no
   transformation, no mapping. This guarantees Analytics↔Crashlytics
   cross-filter in the console.

### Soft guidance (mention in `notes:` of the artifact)

- Add `feature`, `screen`, `user_type` as custom keys before
  `recordException`. Forbid PII (`email`, `phone`, `name`, `uid`,
  `form_content`).
- Respect telemetry opt-out: the tracker checks
  `CrashlyticsManager.setCollectionEnabled` before logging.
- A non-`_error` event MUST NOT appear in `crashlytics.bindings`. Crashes
  belong to crashes; success/attempt events belong to Analytics only.

### Cross-check with `tech-spec.md`

The tech-spec-agent (Wave C, after you) will declare the physical location
of the shared exception class. Your job is the contract; theirs is the
file layout. If the feature already has an exception class declared in
upstream memory L2 (`patterns.observability`), reuse its name verbatim.

### Failure mode you must avoid

If you emit an `*_error` event WITHOUT a binding, the validator
`check-crashlytics-shared-exception.py` fails with severity `error` and
blocks pre-commit + verify-task. The feature cannot ship. Better to ask
for clarification via the conductor than to skip the binding.
