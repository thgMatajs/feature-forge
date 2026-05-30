"""E2E — pause + auto-resume.

Skipped unless RUN_E2E=1. Validates the pause/resume invariant by simulating
that a feature with a `phase_lock` in `status.json` survives a process kill
and can be detected by the L1 status reader on the next run.

This is exercised at the API level here; the full CLI handshake (Ctrl+C →
deferred state → next-run detection) is too interactive to script reliably
in a subprocess.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from engine.memory import l1


_RUN_E2E = os.environ.get("RUN_E2E") == "1"


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_pause_state_persists_across_processes(tmp_path):
    # Process 1 — acquire lock, append history.
    l1.acquire_phase_lock("paused-feat", tmp_path, "wave-B")
    l1.append_history(
        "paused-feat",
        tmp_path,
        {"event": "wave-B-started", "actor": "test"},
    )

    # "Kill" the process — drop in-memory state.
    # (No state to drop in this in-process test, but the semantics are: nothing
    # in memory survives, only the on-disk JSON file.)

    # Process 2 — re-read state from disk.
    state = l1.read_l1_status("paused-feat", tmp_path)
    assert state is not None
    assert state.phase_lock == "wave-B"
    history = l1.read_history("paused-feat", tmp_path)
    assert any(h["kind"] == "wave-B-started" for h in history)


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
def test_resume_marks_continuation(tmp_path):
    l1.acquire_phase_lock("feat", tmp_path, "wave-A")
    l1.append_history("feat", tmp_path, {"event": "started"})
    # Pause + resume cycle.
    l1.append_history("feat", tmp_path, {"event": "paused"})
    state = l1.read_l1_status("feat", tmp_path)
    assert state.phase_lock == "wave-A"

    # On resume the same lock id can be re-acquired (reentrant).
    again = l1.acquire_phase_lock("feat", tmp_path, "wave-A")
    assert again is True
    l1.append_history("feat", tmp_path, {"event": "resumed"})

    rows = l1.read_history("feat", tmp_path)
    kinds = [r["kind"] for r in rows]
    assert kinds == ["started", "paused", "resumed"]
