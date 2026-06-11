#!/usr/bin/env python3
"""
check-crashlytics-shared-exception.py

Card: firebase-crashlytics
Runs-on: pre-commit, verify-task
Severity: error

Goal
----
Fail the gate if `analytics-spec.yaml` declares any event whose name ends
in `_error` WITHOUT a corresponding binding in `crashlytics.bindings`
pointing to a shared exception class `Firebase{Feature}AnalyticsException`.

This enforces the canonical pattern from MeoBonsai
`.claude/rules/observability.md` §Crashlytics:

    Every `*_error` analytics event MUST trigger
    `Firebase.crashlytics.recordException(...)` with a feature-scoped shared
    exception class carrying `(errorCode, causeType)` for Android↔iOS parity.

# TODO Phase 5
----------
Implement:
  1. Locate `analytics-spec.yaml` for the feature passed via $1 (feature dir)
     or auto-discover via `.planning/features/<slug>/`.
  2. Parse YAML; collect every entry under `events:` with name ending `_error`.
  3. For each such event, check `crashlytics.bindings` contains:
       - matching `event:` name
       - `exception-class:` matching pattern `Firebase<Feature>AnalyticsException`
       - non-empty `error-code-source` and `cause-type-source`
  4. Cross-check that the referenced exception class file actually exists at:
       shared/feature/<feature>/src/commonMain/kotlin/**/analytics/
         Firebase<Feature>AnalyticsException.kt
  5. Emit machine-readable findings to stdout (JSON) and human-readable
     summary to stderr.
  6. Exit code:
       0 — all good
       1 — at least one violation
       2 — invocation error (missing file, bad YAML)

Skeleton
--------
The actual implementation lands in Phase 5. This stub keeps the contract
discoverable and lets `forge doctor` enumerate it without exploding.
"""

from __future__ import annotations

import sys


VALIDATOR_NAME = "check-crashlytics-shared-exception"
CARD = "firebase-crashlytics"
SEVERITY = "error"


def main(argv: list[str]) -> int:
    # TODO Phase 5: replace stub with real implementation.
    print(
        f"[{VALIDATOR_NAME}] STUB — Phase 5 not yet implemented. "
        f"Card={CARD} severity={SEVERITY}.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
