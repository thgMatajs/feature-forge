"""Unit tests — engine.memory.l1.

Validates status.json round-trip, phase_lock semantics (reentrant for same
id, exclusive otherwise), JSONL append-only history, and archive lifecycle.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.memory import MemoryError
from engine.memory import l1


def test_status_round_trip(tmp_path):
    state = l1.L1State(
        feature_slug="my-feature",
        status="planning",
        last_action_at="2026-05-29T10:00:00Z",
        last_action_kind="created",
    )
    l1.write_l1_status(state, tmp_path)
    read = l1.read_l1_status("my-feature", tmp_path)
    assert read is not None
    assert read.status == "planning"
    assert read.feature_slug == "my-feature"
    assert read.last_action_kind == "created"


def test_status_missing_returns_none(tmp_path):
    assert l1.read_l1_status("ghost", tmp_path) is None


def test_status_invalid_state_raises(tmp_path):
    bad = l1.L1State(
        feature_slug="x",
        status="totally-fake-state",
        last_action_at="2026-05-29T10:00:00Z",
        last_action_kind="x",
    )
    with pytest.raises(MemoryError):
        l1.write_l1_status(bad, tmp_path)


def test_acquire_phase_lock_first_time(tmp_path):
    ok = l1.acquire_phase_lock("feat", tmp_path, "lock-A")
    assert ok is True
    assert l1.current_phase_lock("feat", tmp_path) == "lock-A"


def test_acquire_phase_lock_reentrant_same_id(tmp_path):
    l1.acquire_phase_lock("feat", tmp_path, "lock-A")
    again = l1.acquire_phase_lock("feat", tmp_path, "lock-A")
    assert again is True


def test_acquire_phase_lock_blocks_other_id(tmp_path):
    l1.acquire_phase_lock("feat", tmp_path, "lock-A")
    blocked = l1.acquire_phase_lock("feat", tmp_path, "lock-B")
    assert blocked is False
    assert l1.current_phase_lock("feat", tmp_path) == "lock-A"


def test_release_phase_lock_clears(tmp_path):
    l1.acquire_phase_lock("feat", tmp_path, "lock-A")
    l1.release_phase_lock("feat", tmp_path)
    assert l1.current_phase_lock("feat", tmp_path) is None


def test_release_phase_lock_noop_when_no_status(tmp_path):
    # Should not raise.
    l1.release_phase_lock("ghost", tmp_path)


def test_acquire_phase_lock_empty_id_raises(tmp_path):
    with pytest.raises(MemoryError):
        l1.acquire_phase_lock("feat", tmp_path, "")


def test_append_history_is_append_only(tmp_path):
    l1.append_history("feat", tmp_path, {"event": "started", "actor": "test"})
    l1.append_history("feat", tmp_path, {"event": "step", "actor": "test"})
    rows = l1.read_history("feat", tmp_path)
    assert len(rows) == 2
    assert rows[0]["kind"] == "started"
    assert rows[1]["kind"] == "step"


def test_read_history_tail(tmp_path):
    for i in range(5):
        l1.append_history("feat", tmp_path, {"event": f"e{i}"})
    tail = l1.read_history("feat", tmp_path, tail=2)
    assert len(tail) == 2
    assert tail[0]["kind"] == "e3"
    assert tail[1]["kind"] == "e4"


def test_read_history_negative_tail_raises(tmp_path):
    with pytest.raises(MemoryError):
        l1.read_history("feat", tmp_path, tail=-1)


def test_archive_feature_moves_dir(tmp_path):
    # Set up an active feature.
    l1.acquire_phase_lock("done-feat", tmp_path, "lock-1")
    l1.append_history("done-feat", tmp_path, {"event": "x"})
    assert "done-feat" in l1.list_active_features(tmp_path)

    l1.archive_feature("done-feat", tmp_path, {"summary": "complete"})

    assert "done-feat" not in l1.list_active_features(tmp_path)
    assert "done-feat" in l1.list_archived_features(tmp_path)
    archive_file = tmp_path / ".claude" / "forge" / "state" / "lifecycle" / "archived" / "done-feat.summary.yaml"
    assert archive_file.is_file()


def test_archive_feature_missing_raises(tmp_path):
    with pytest.raises(MemoryError):
        l1.archive_feature("nope", tmp_path, {})


def test_yaml_helpers_round_trip(tmp_path):
    l1.write_hypothesis("feat", tmp_path, {"goal": "X"})
    assert l1.read_hypothesis("feat", tmp_path) == {"goal": "X"}

    l1.write_ambiguity_map("feat", tmp_path, {"items": []})
    assert l1.read_ambiguity_map("feat", tmp_path) == {"items": []}

    l1.write_elicitation("feat", tmp_path, {"answered": []})
    assert l1.read_elicitation("feat", tmp_path) == {"answered": []}

    l1.write_rationale_trace("feat", tmp_path, {"decisions": []})
    assert l1.read_rationale_trace("feat", tmp_path) == {"decisions": []}


def test_list_active_features_skips_archived_and_dotfiles(tmp_path):
    l1.acquire_phase_lock("real", tmp_path, "lock")
    (tmp_path / ".claude" / "forge" / "state" / "lifecycle" / ".hidden").mkdir(parents=True)
    (tmp_path / ".claude" / "forge" / "state" / "lifecycle" / "archived").mkdir(exist_ok=True)
    active = l1.list_active_features(tmp_path)
    assert active == ["real"]


def test_append_verify_log_validates_scope(tmp_path):
    bad = {
        "verify-id": "v1",
        "scope": "bogus-scope",
        "validators-run": [],
        "result": "pass",
    }
    with pytest.raises(MemoryError):
        l1.append_verify_log("feat", tmp_path, bad)


def test_append_verify_log_validates_result(tmp_path):
    bad = {
        "verify-id": "v1",
        "scope": "task",
        "validators-run": [],
        "result": "explosion",
    }
    with pytest.raises(MemoryError):
        l1.append_verify_log("feat", tmp_path, bad)
