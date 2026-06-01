"""Regression: ``acquire_phase_lock`` must be atomic against TOCTOU (C1 + A1).

Bug C1 (PR #1, master review): the read-then-write sequence
  1. read_l1_status → check phase_lock
  2. write_l1_status → set phase_lock = lock_id
is non-atomic. Two processes / threads can both pass the check on step 1
and both write on step 2 — last writer wins, lock semantics break.

Fix: introduce a file-based atomic lock via ``os.open`` with
``O_CREAT | O_EXCL``. The first process to create the lock file wins; any
other concurrent caller sees ``FileExistsError`` and falls back to the
reentrant check (same lock_id → still True). status.json continues to
mirror the live lock for read APIs.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import time
from pathlib import Path

import pytest

from engine.memory import l1


def _worker_acquire(
    project_root_str: str, slug: str, lock_id: str, barrier, result_queue
):
    """Worker process — sync on barrier then try to acquire simultaneously."""
    project_root = Path(project_root_str)
    barrier.wait()  # all workers fire on the same tick
    try:
        ok = l1.acquire_phase_lock(slug, project_root, lock_id)
        current = l1.current_phase_lock(slug, project_root)
        result_queue.put((lock_id, ok, current))
    except Exception as exc:  # noqa: BLE001 — race crash is the signal we want
        # A crash here (e.g. JSONDecodeError on a half-written status.json)
        # is itself a TOCTOU symptom. Report it as a "lost the race AND
        # corrupted the file" outcome instead of crashing the worker.
        result_queue.put((lock_id, False, f"CRASH:{type(exc).__name__}:{exc}"))


def test_acquire_phase_lock_is_atomic_under_concurrent_processes(tmp_path: Path):
    """N processes race on the SAME tick — exactly one must win.

    Without the fix, the read-then-write sequence allows multiple writers
    through the gate. We force the race with a multiprocessing Barrier so
    all workers reach the acquire call at the same instant.
    """
    slug = "race"
    # Pre-seed the L1 directory so the cold-create race doesn't mask the
    # status-write race.
    (tmp_path / ".claude" / "memory" / "L1" / slug).mkdir(
        parents=True, exist_ok=True
    )

    ctx = mp.get_context("fork")
    n_workers = 16
    barrier = ctx.Barrier(n_workers)
    queue: mp.Queue = ctx.Queue()
    procs = [
        ctx.Process(
            target=_worker_acquire,
            args=(str(tmp_path), slug, f"lock-{i:02d}", barrier, queue),
        )
        for i in range(n_workers)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=15)
        assert p.exitcode == 0, f"worker crashed (exit {p.exitcode})"

    results = [queue.get_nowait() for _ in range(n_workers)]
    winners = [(lid, current) for (lid, ok, current) in results if ok]
    losers = [(lid, current) for (lid, ok, current) in results if not ok]

    assert len(winners) == 1, (
        f"exactly one worker must win; got {len(winners)} winners. "
        f"All results: {results}"
    )
    winning_lock_id = winners[0][0]
    # Every loser must NOT report itself as the active lock. A loser may
    # see the winner's id, an empty status (lost the race before the
    # winner finished mirroring to status.json), or `None` — the only
    # invalid case is "I lost AND status.json says I'm the holder",
    # which would be a partial-write artifact.
    for lid, current in losers:
        assert current != lid, (
            f"loser {lid!r} reports itself as current lock — "
            "atomic gate let through a partial state"
        )
    # And the canonical read AFTER all workers settle must report the
    # winner cleanly.
    final = l1.current_phase_lock(slug, tmp_path)
    assert final == winning_lock_id, (
        f"after race resolved, current_phase_lock must report winner "
        f"{winning_lock_id!r}, got {final!r}"
    )


def test_acquire_phase_lock_reentrant_same_id_after_atomic_acquire(
    tmp_path: Path,
):
    """Same lock_id must remain reentrant — same-process re-acquire returns True."""
    slug = "reentrant"
    assert l1.acquire_phase_lock(slug, tmp_path, "lock-A") is True
    assert l1.acquire_phase_lock(slug, tmp_path, "lock-A") is True
    assert l1.acquire_phase_lock(slug, tmp_path, "lock-A") is True
    assert l1.current_phase_lock(slug, tmp_path) == "lock-A"


def test_release_then_reacquire_with_different_id(tmp_path: Path):
    """After release, a different id must be able to acquire."""
    slug = "swap"
    assert l1.acquire_phase_lock(slug, tmp_path, "lock-A") is True
    l1.release_phase_lock(slug, tmp_path)
    assert l1.current_phase_lock(slug, tmp_path) is None
    assert l1.acquire_phase_lock(slug, tmp_path, "lock-B") is True
    assert l1.current_phase_lock(slug, tmp_path) == "lock-B"


def test_acquire_other_id_blocked_then_unblocked_after_release(tmp_path: Path):
    """Smoke: classic block-then-unblock cycle survives the atomic refactor."""
    slug = "cycle"
    assert l1.acquire_phase_lock(slug, tmp_path, "lock-A") is True
    assert l1.acquire_phase_lock(slug, tmp_path, "lock-B") is False
    l1.release_phase_lock(slug, tmp_path)
    assert l1.acquire_phase_lock(slug, tmp_path, "lock-B") is True


# ── HG-02 — sentinel is the source of truth (status.json is a mirror) ─────


def test_current_phase_lock_reads_sentinel_when_status_lags(tmp_path: Path):
    """HG-02: ``current_phase_lock`` must consult the sentinel first.

    The atomic gate that protects the lock is the O_EXCL sentinel file,
    not status.json. status.json is a human-readable mirror written AFTER
    the sentinel — so there's a window where the sentinel exists and
    status.json doesn't yet reflect the holder. Readers must consult the
    sentinel first or they'll race the mirror write and report stale
    ``None`` while a real lock is in flight.

    Repro: write a sentinel directly, leave status.json alone (or absent),
    and confirm ``current_phase_lock`` reports the sentinel value.
    """
    slug = "lag"
    sentinel = l1._phase_lock_path(slug, tmp_path)
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text("test_lock", encoding="utf-8")
    # status.json deliberately not written.

    result = l1.current_phase_lock(slug, tmp_path)
    assert result == "test_lock", (
        "current_phase_lock must consult the sentinel — status.json is "
        "the lagging mirror, not the source of truth."
    )


# ── HG-03 — reentrant empty-read race ─────────────────────────────────────


def test_acquire_phase_lock_reentrant_handles_empty_sentinel_window(
    tmp_path: Path,
):
    """HG-03: an empty sentinel must trigger a retry, not a false ``False``.

    The atomic gate is a two-step write: (a) ``os.open(O_EXCL)`` returns a
    fd, (b) ``fh.write(lock_id)`` actually places content. A racing
    same-process call between those two steps reads an empty sentinel.
    Before the fix it returned ``False`` (treating empty as "foreign
    lock"), even when the eventual write would have been by the same
    lock_id.

    Repro: pre-create an empty sentinel (winner mid-write), then schedule
    a background thread to fill it with our lock_id 30ms later. The
    acquire call from the main thread must retry through that window and
    eventually observe its own id → return True.
    """
    import threading
    import time as _time

    slug = "empty_window"
    sentinel = l1._phase_lock_path(slug, tmp_path)
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    # Pre-create EMPTY sentinel — simulates "winner has the fd but hasn't
    # written content yet".
    sentinel.touch()
    assert sentinel.exists()
    assert sentinel.read_text(encoding="utf-8") == ""

    def delayed_write():
        _time.sleep(0.030)
        sentinel.write_text("same-lock-id", encoding="utf-8")

    timer = threading.Timer(0.0, delayed_write)
    timer.start()
    try:
        # Acquire with SAME lock_id. Without the retry, we read empty,
        # treat as foreign, and return False. With the retry, we re-read
        # 20ms later, see our own id, and return True.
        result = l1.acquire_phase_lock(slug, tmp_path, "same-lock-id")
    finally:
        timer.join(timeout=2.0)

    assert result is True, (
        "Reentrant acquire must retry through the empty-sentinel window — "
        "an empty read mid-write is NOT a foreign lock signal."
    )


def test_acquire_phase_lock_truly_foreign_still_returns_false(tmp_path: Path):
    """Regression guard: after retries exhaust on a truly foreign lock, False.

    The retry must not flip foreign-lock denial into spurious acquires —
    when the sentinel really does hold a different id, the final answer
    is still False.
    """
    slug = "foreign"
    sentinel = l1._phase_lock_path(slug, tmp_path)
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text("someone-else", encoding="utf-8")

    result = l1.acquire_phase_lock(slug, tmp_path, "me")
    assert result is False
