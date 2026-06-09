"""Unit tests for CCResult dataclass + classify_range_against_hunks.

Cobre a dataclass normalizada do CC validator + o classificador
``new/modified/unchanged`` baseado em diff hunks (agora vivendo em
``validators/_diff.py`` após Phase 0 gate-infra-extract). Os símbolos
``DiffHunk`` e ``classify_range_against_hunks`` são re-exportados pelo CC
validator (back-compat), então os testes seguem importando via ``v``.

Spec source: ``docs/superpowers/specs/2026-06-03-cc-gate-design.md §3``
(CCResult shape) + §2 step 9 (regra de classificação via overlap entre
range da função e hunks do diff).
"""

from __future__ import annotations

import dataclasses

import check_cyclomatic_complexity as v


def test_ccresult_is_frozen_dataclass() -> None:
    assert dataclasses.is_dataclass(v.CCResult)
    params = v.CCResult.__dataclass_params__
    assert params.frozen is True


def test_ccresult_fields_match_spec() -> None:
    fields = {f.name for f in dataclasses.fields(v.CCResult)}
    expected = {
        "file",
        "function",
        "line_start",
        "line_end",
        "cc",
        "language",
        "status",
        "cc_before",
    }
    assert fields == expected


def test_ccresult_constructs_with_all_fields() -> None:
    r = v.CCResult(
        file="a.kt",
        function="foo",
        line_start=10,
        line_end=30,
        cc=12,
        language="kotlin",
        status="new",
        cc_before=None,
    )
    assert r.cc == 12
    assert r.cc_before is None
    assert r.status == "new"


def test_classify_new_function_entirely_in_added_hunk() -> None:
    # Function spans lines 10..20; the hunk also added lines 10..20.
    hunks = [v.DiffHunk(start=10, end=20, kind="add")]
    assert v.classify_range_against_hunks((10, 20), hunks) == "new"


def test_classify_modified_when_range_intersects_hunk() -> None:
    # Function spans 5..40; hunk touches 20..25 (partial overlap).
    hunks = [v.DiffHunk(start=20, end=25, kind="add")]
    assert v.classify_range_against_hunks((5, 40), hunks) == "modified"


def test_classify_unchanged_when_no_overlap() -> None:
    hunks = [v.DiffHunk(start=100, end=110, kind="add")]
    assert v.classify_range_against_hunks((5, 40), hunks) == "unchanged"


def test_classify_empty_hunks_means_unchanged() -> None:
    assert v.classify_range_against_hunks((1, 100), []) == "unchanged"


def test_classify_function_starts_above_hunk_ends_inside_is_modified() -> None:
    # Function 5..25; hunk 20..30 (function tail overlaps hunk head).
    hunks = [v.DiffHunk(start=20, end=30, kind="add")]
    assert v.classify_range_against_hunks((5, 25), hunks) == "modified"
