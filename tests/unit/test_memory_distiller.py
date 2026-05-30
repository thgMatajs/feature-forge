"""Unit tests — engine.memory.distiller.

Drives the proposal queue lifecycle, fingerprint guards against re-queuing
vetoed proposals, and rejection record creation.
"""

from __future__ import annotations

import pytest

from engine.memory import MemoryError
from engine.memory import distiller
from engine.memory.distiller import DistillationProposal


def _make_proposal(id_: str = "P-001") -> DistillationProposal:
    return DistillationProposal(
        id=id_,
        kind="promote-to-l2",
        title="use-stateflow",
        description="Use MutableStateFlow for screen state",
        provenance=["auth"],
        confidence=0.8,
    )


def test_queue_proposal_appends(tmp_path):
    p = _make_proposal()
    distiller.queue_proposal(tmp_path, p)
    queue = distiller.read_proposals_queue(tmp_path)
    assert len(queue) == 1
    assert queue[0].id == "P-001"
    assert queue[0].title == "use-stateflow"


def test_queue_proposal_invalid_kind_raises(tmp_path):
    bad = DistillationProposal(
        id="P-x",
        kind="bogus-kind",
        title="x",
        description="d",
    )
    with pytest.raises(MemoryError):
        distiller.queue_proposal(tmp_path, bad)


def test_queue_proposal_empty_id_raises(tmp_path):
    bad = DistillationProposal(id="", kind="promote-to-l2", title="x", description="d")
    with pytest.raises(MemoryError):
        distiller.queue_proposal(tmp_path, bad)


def test_queue_proposal_duplicate_id_raises(tmp_path):
    p = _make_proposal()
    distiller.queue_proposal(tmp_path, p)
    with pytest.raises(MemoryError):
        distiller.queue_proposal(tmp_path, p)


def test_remove_from_queue_drains_id(tmp_path):
    distiller.queue_proposal(tmp_path, _make_proposal("P-1"))
    distiller.queue_proposal(tmp_path, _make_proposal("P-2"))
    distiller.remove_from_queue(tmp_path, "P-1")
    queue = distiller.read_proposals_queue(tmp_path)
    assert [p.id for p in queue] == ["P-2"]


def test_remove_from_queue_noop_for_missing(tmp_path):
    distiller.remove_from_queue(tmp_path, "ghost")
    assert distiller.read_proposals_queue(tmp_path) == []


def test_compute_proposal_fingerprint_stable():
    payload = {
        "type": "promote-to-l2",
        "name": "x",
        "description": "y",
        "provenance": {"feature-slugs": ["a"]},
    }
    f1 = distiller.compute_proposal_fingerprint(payload)
    f2 = distiller.compute_proposal_fingerprint(payload)
    assert f1 == f2 and len(f1) == 64


def test_record_rejection_persists(tmp_path):
    fingerprint = "a" * 64
    distiller.record_rejection(
        tmp_path,
        fingerprint,
        rationale="not aligned with project",
        proposal_snapshot={
            "id": "P-001",
            "type": "promote-to-l2",
            "name": "x",
            "description": "y",
            "provenance": {"feature-slugs": ["a"]},
        },
    )
    assert distiller.is_fingerprint_rejected(tmp_path, fingerprint) is True


def test_record_rejection_invalid_fingerprint_raises(tmp_path):
    with pytest.raises(MemoryError):
        distiller.record_rejection(tmp_path, "short")


def test_record_rejection_idempotent(tmp_path):
    fingerprint = "b" * 64
    distiller.record_rejection(tmp_path, fingerprint, rationale="r")
    # Second call must not raise nor duplicate the entry.
    distiller.record_rejection(tmp_path, fingerprint, rationale="r")
    assert distiller.is_fingerprint_rejected(tmp_path, fingerprint) is True


def test_queue_proposal_skips_when_rejected(tmp_path):
    p = _make_proposal()
    # Compute the fingerprint that queue_proposal will derive.
    fingerprint = distiller.compute_proposal_fingerprint(
        {
            "type": p.kind,
            "name": p.title,
            "description": p.description,
            "provenance": {"feature-slugs": list(p.provenance)},
        }
    )
    distiller.record_rejection(tmp_path, fingerprint, rationale="vetoed")
    # Now queue — should silently skip.
    distiller.queue_proposal(tmp_path, p)
    assert distiller.read_proposals_queue(tmp_path) == []
