"""ABORTED-DEADEND (W-DEBT) — recovery do abort via pre-abort-status preservado.

`_abort_feature` passa a gravar `raw["pre-abort-status"]` ANTES do overwrite;
o novo op `_undo_abort` restaura o status preservado (default `deferred` quando
ausente — feature abortada por engine antigo), limpando os markers e logando
no undo-log. Fecha o dead-end aborted→delete+restart.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.memory.l1 import L1State, read_l1_status, write_l1_status
from engine.undo import _abort_feature, _undo_abort


def _seed(project_root: Path, slug: str, status: str) -> None:
    write_l1_status(
        L1State(
            feature_slug=slug,
            status=status,
            last_action_at="2026-06-18T00:00:00Z",
            last_action_kind="seed",
        ),
        project_root,
    )


def test_abort_preserves_prior_status(tmp_project_root: Path) -> None:
    _seed(tmp_project_root, "demo", "implementing")
    _abort_feature(tmp_project_root, "demo", reason="user abort")
    st = read_l1_status("demo", tmp_project_root)
    assert st is not None
    assert st.status == "aborted"
    assert st.raw.get("pre-abort-status") == "implementing"


def test_undo_abort_restores_prior_status(
    tmp_project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("engine.undo.question.confirm", lambda *a, **k: True)
    _seed(tmp_project_root, "demo", "planned")
    _abort_feature(tmp_project_root, "demo", reason="oops")
    assert _undo_abort(tmp_project_root, "demo") is True
    st = read_l1_status("demo", tmp_project_root)
    assert st is not None
    assert st.status == "planned"
    assert "pre-abort-status" not in st.raw
    assert "aborted-reason" not in st.raw


def test_undo_abort_defaults_deferred_when_no_marker(
    tmp_project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Feature abortada por engine antigo (sem pre-abort-status no raw)."""
    monkeypatch.setattr("engine.undo.question.confirm", lambda *a, **k: True)
    write_l1_status(
        L1State(
            feature_slug="legacy",
            status="aborted",
            last_action_at="2026-06-18T00:00:00Z",
            last_action_kind="aborted",
            raw={"state": "aborted"},
        ),
        tmp_project_root,
    )
    assert _undo_abort(tmp_project_root, "legacy") is True
    st = read_l1_status("legacy", tmp_project_root)
    assert st is not None
    assert st.status == "deferred"


def test_undo_abort_noop_when_not_aborted(
    tmp_project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Feature que não está em 'aborted' → nada a reverter, retorna False."""
    monkeypatch.setattr("engine.undo.question.confirm", lambda *a, **k: True)
    _seed(tmp_project_root, "demo", "implementing")
    assert _undo_abort(tmp_project_root, "demo") is False
    assert read_l1_status("demo", tmp_project_root).status == "implementing"


def test_undo_abort_respects_declined_confirm(
    tmp_project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Usuário recusa o confirm → feature permanece aborted (sem mutação)."""
    monkeypatch.setattr("engine.undo.question.confirm", lambda *a, **k: False)
    _seed(tmp_project_root, "demo", "planning")
    _abort_feature(tmp_project_root, "demo", reason="x")
    assert _undo_abort(tmp_project_root, "demo") is False
    assert read_l1_status("demo", tmp_project_root).status == "aborted"
