"""Unit tests — engine.memory.l2.

Validates L2Entry round-trip across the disk schema, duplicate-id detection,
confidence bounds enforcement, kind filtering, and add/remove flow.
"""

from __future__ import annotations

import pytest

from engine.memory import MemoryError
from engine.memory import l2
from engine.memory.l2 import L2Entry


def test_read_l2_empty_returns_empty_list(tmp_path):
    assert l2.read_l2(tmp_path) == []


def test_write_and_read_pattern_entry(tmp_path):
    entry = L2Entry(
        id="P-001",
        kind="pattern",
        title="use-stateflow",
        body="Use MutableStateFlow for screen state",
        provenance=["auth"],
        confidence=0.9,
    )
    l2.write_l2(tmp_path, [entry])
    read = l2.read_l2(tmp_path)
    assert len(read) == 1
    assert read[0].id == "P-001"
    assert read[0].kind == "pattern"
    assert read[0].title == "use-stateflow"
    assert read[0].confidence == 0.9


def test_write_l2_duplicate_id_raises(tmp_path):
    a = L2Entry(id="P-001", kind="pattern", title="x", body="d")
    b = L2Entry(id="P-001", kind="finding", title="y", body="d")
    with pytest.raises(MemoryError):
        l2.write_l2(tmp_path, [a, b])


def test_write_l2_invalid_kind_raises(tmp_path):
    bad = L2Entry(id="X-1", kind="fictional", title="x", body="d")
    with pytest.raises(MemoryError):
        l2.write_l2(tmp_path, [bad])


def test_write_l2_confidence_out_of_range_raises(tmp_path):
    bad = L2Entry(id="X-1", kind="pattern", title="x", body="d", confidence=1.5)
    with pytest.raises(MemoryError):
        l2.write_l2(tmp_path, [bad])


def test_remove_entry_removes_when_present(tmp_path):
    e = L2Entry(id="P-1", kind="pattern", title="x", body="d")
    l2.write_l2(tmp_path, [e])
    l2.remove_entry(tmp_path, "P-1")
    assert l2.find_entry(tmp_path, "P-1") is None


def test_remove_entry_noop_when_absent(tmp_path):
    # Should not raise.
    l2.remove_entry(tmp_path, "ghost")


def test_filter_entries_by_kind(tmp_path):
    l2.write_l2(
        tmp_path,
        [
            L2Entry(id="P-1", kind="pattern", title="p", body="d"),
            L2Entry(id="F-1", kind="finding", title="f", body="d"),
            L2Entry(id="D-1", kind="decision-frozen", title="d", body="d"),
        ],
    )
    patterns = l2.filter_entries(tmp_path, kind="pattern")
    assert len(patterns) == 1 and patterns[0].id == "P-1"
    findings = l2.filter_entries(tmp_path, kind="finding")
    assert len(findings) == 1 and findings[0].id == "F-1"


def test_filter_entries_invalid_kind_raises(tmp_path):
    with pytest.raises(MemoryError):
        l2.filter_entries(tmp_path, kind="bogus")


def test_read_l2_entries_sorted_by_id(tmp_path):
    l2.write_l2(
        tmp_path,
        [
            L2Entry(id="P-zzz", kind="pattern", title="z", body=""),
            L2Entry(id="P-aaa", kind="pattern", title="a", body=""),
            L2Entry(id="P-mmm", kind="pattern", title="m", body=""),
        ],
    )
    ids = [e.id for e in l2.read_l2(tmp_path)]
    assert ids == ["P-aaa", "P-mmm", "P-zzz"]


def test_decision_frozen_entry_round_trip(tmp_path):
    e = L2Entry(
        id="D-001",
        kind="decision-frozen",
        title="use-koin-annotations",
        body="use-koin-annotations",
        promoted_at="2026-01-01T00:00:00Z",
        promoted_from="memory-distiller",
    )
    l2.write_l2(tmp_path, [e])
    read = l2.read_l2(tmp_path)
    assert read[0].kind == "decision-frozen"
    assert read[0].title == "use-koin-annotations"


def test_naming_extra_round_trip(tmp_path):
    e = L2Entry(
        id="N-001",
        kind="naming-extra",
        title="repository-naming",
        body="{Feature}Repository",
        provenance=["AuthRepository", "BonsaiRepository"],
    )
    l2.write_l2(tmp_path, [e])
    read = l2.read_l2(tmp_path)
    assert read[0].kind == "naming-extra"
    assert read[0].provenance == ["AuthRepository", "BonsaiRepository"]


# ── Task 4 (6c): add_entry removido de l2.py ──────────────────────────────────


def test_l2_add_entry_removed_from_module() -> None:
    """add_entry foi deletada de engine.memory.l2 em 6c (write-path órfão).

    O write-path de conhecimento agora vai pro mem inbox (6b). l2.add_entry
    era o único caller de produção; após 6b nenhum engine code a chamava.
    """
    import engine.memory.l2 as _l2
    assert not hasattr(_l2, "add_entry"), (
        "add_entry ainda existe em engine.memory.l2; "
        "deveria ter sido removida na Task 4 de 6c (W-ROUTE orphan-cleanup)."
    )


def test_l2_add_entry_not_in_all() -> None:
    """add_entry não deve estar em __all__ de engine.memory.l2."""
    import engine.memory.l2 as _l2
    assert "add_entry" not in _l2.__all__, (
        "add_entry ainda está em l2.__all__; "
        "deveria ter sido removida junto com a função em 6c."
    )
