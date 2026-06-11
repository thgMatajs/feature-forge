# W1 Verification Log — DRIFT-1

**Wave:** W1 — Schema + intent_state foundation
**Date:** 2026-06-10
**Branch:** worktree-agent-a544059689cebc37e (PR-target: feat/drift-1-intent-protocol)

## Tasks delivered

| Task | Status | Commit |
|------|--------|--------|
| W1.T1 — `docs/schemas/intent-protocol.md` | ✅ shipped | `7b97f31` |
| W1.T2 — `engine/utils/json_io.py` + tests | ✅ shipped | `588dc44` |
| W1.T3 — `engine/ui/intent_state.py` + tests | ✅ shipped | `093eeb0` |
| W1.T4 — Verification | ✅ this log |   |

## TDD evidence

| Test file | RED moment | GREEN moment |
|-----------|------------|--------------|
| `tests/unit/test_utils_json_io.py` | `ImportError: cannot import name 'json_io'` (pre-impl) | 13/13 passed |
| `tests/unit/test_ui_intent_state.py` | `ImportError: cannot import name 'intent_state'` (pre-impl) | 18/18 passed |

Total new tests: **31**, all green.

## Full-suite regression

```
1143 passed, 1 failed, 20 skipped in 318.11s
```

- 1133 → 1143 + 1 = 1144 collected (pytest count includes parametrization)
- Baseline (1133, from `pytest --collect-only -q` pre-W1) preserved
- Single failure: `tests/integration/test_claude_rules_system.py::test_bootstrap_is_idempotent`

### Pre-existing failure (deferred — out of scope for W1)

```
ln: .git/hooks/pre-commit: Not a directory
```

Root cause: `.claude/bootstrap.sh` tries to create a symlink at
`.git/hooks/pre-commit`. Inside a git worktree, `.git` is a file
(pointer to the main repo's `.git/worktrees/<name>/`), not a directory,
so the symlink target path is invalid.

This failure pre-dates W1 — none of the W1 deliverables touch
`bootstrap.sh`, `.git/hooks`, or `tests/integration/test_claude_rules_system.py`.
Recommendation for follow-up gap: make bootstrap detect worktree
context (`[ -f .git ] && resolve via git rev-parse --git-dir`) before
attempting hook symlinks. Owner: separate task, not DRIFT-1 scope.

## Acceptance criteria covered (partial — full coverage lands in later waves)

| AC | W1 coverage |
|----|-------------|
| AC-1 (intent emit on first prompt) | partial — schema + write_pending tested; emit-site lands in W2.T1 |
| AC-2 (resume consumes + deletes) | partial — `clear_intent_files` tested unit-level; integration in W5.T1 |
| AC-6 (state files deleted after consume) | covered at unit level via `test_clear_intent_files_deletes_both` |
| AC-7 (race detection) | covered at unit level — 4 race-detection tests in `test_ui_intent_state.py` |

AC-3, AC-4, AC-5, AC-8, AC-9 require W2/W3/W4/W5 surface — not in W1 scope.

## Smoke

```bash
./bin/forge --version
# forge 1.2.0
```

`forge verify` requires a `.claude/workflow-config.yaml` in the cwd
chain; the worktree itself is not a forge-managed project, so this
step is skipped here — `forge verify` will run inside the main
checkout post-merge.

## Foundation ready for W2

- `engine/utils/json_io.py` — atomic JSON I/O reusable by any caller
- `engine/ui/intent_state.py` — chokepoint for state files;
  `write_pending`, `read_response`, `clear_intent_files`,
  `detect_race` ready
- `IntentMismatchError`, `RaceDetectedError` defined and tested
- Schema doc canonical — W2 implementers consult
  `docs/schemas/intent-protocol.md` directly

Next: W2.T0 (checkpoint infrastructure audit) → W2.T1 (`question.py`
refactor with TDD).
