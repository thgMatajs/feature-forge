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


def test_double_abort_preserves_original_pre_abort_status(
    tmp_project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C-48 (PR22-R-006): abortar uma feature JÁ aborted não envenena o
    pre-abort-status com 'aborted'. O status real pré-1º-abort é preservado, e
    o un-abort restaura pra ele (não fica em dead-end 'aborted')."""
    monkeypatch.setattr("engine.undo.question.confirm", lambda *a, **k: True)
    _seed(tmp_project_root, "demo", "implementing")
    _abort_feature(tmp_project_root, "demo", reason="1º abort")
    # 2º abort (double) — NÃO deve sobrescrever pre-abort-status com 'aborted'.
    _abort_feature(tmp_project_root, "demo", reason="2º abort")
    st = read_l1_status("demo", tmp_project_root)
    assert st is not None
    assert st.raw.get("pre-abort-status") == "implementing", (
        "double-abort não pode envenenar pre-abort-status com 'aborted'"
    )
    # un-abort restaura pro estado real, não pra 'aborted'.
    assert _undo_abort(tmp_project_root, "demo") is True
    st2 = read_l1_status("demo", tmp_project_root)
    assert st2 is not None
    assert st2.status == "implementing"


def test_abort_tolerates_non_dict_raw(tmp_project_root: Path) -> None:
    """C-50 (PR22-B-03): status.json com `raw` não-dict não derruba _abort_feature."""
    # Escreve um status.json com raw corrompido (top-level não-dict no campo).
    write_l1_status(
        L1State(
            feature_slug="corrupt",
            status="planning",
            last_action_at="2026-06-18T00:00:00Z",
            last_action_kind="seed",
        ),
        tmp_project_root,
    )
    state = read_l1_status("corrupt", tmp_project_root)
    assert state is not None
    state.raw = "not-a-dict"  # type: ignore[assignment]
    # _abort_feature deve coagir raw pra dict sem estourar AttributeError.
    import engine.undo as undo_mod
    monkeypatch_state = state

    def _fake_read(slug, root):
        return monkeypatch_state if slug == "corrupt" else None

    orig = undo_mod.read_l1_status
    undo_mod.read_l1_status = _fake_read  # type: ignore[assignment]
    try:
        assert undo_mod._abort_feature(tmp_project_root, "corrupt", "x") is True
    finally:
        undo_mod.read_l1_status = orig  # type: ignore[assignment]
    assert isinstance(monkeypatch_state.raw, dict)
    assert monkeypatch_state.raw.get("pre-abort-status") == "planning"


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


def test_undo_abort_restores_deferred_when_prior_status_invalid(
    tmp_project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WR-01 (T1×T3): pre-abort-status com valor que não é mais membro de
    `_VALID_STATES` (ex.: `verified` — removido por T1, ou abort de versão mista)
    cai pro default seguro `deferred` SEM traceback (não propaga o `MemoryError`
    de `write_l1_status`).
    """
    monkeypatch.setattr("engine.undo.question.confirm", lambda *a, **k: True)
    write_l1_status(
        L1State(
            feature_slug="stale",
            status="aborted",
            last_action_at="2026-06-18T00:00:00Z",
            last_action_kind="aborted",
            # `verified` foi removido de _VALID_STATES por T1 (PHANTOM-STATES).
            raw={"state": "aborted", "pre-abort-status": "verified"},
        ),
        tmp_project_root,
    )
    # Não deve levantar — restaura `deferred` em vez de explodir no write.
    assert _undo_abort(tmp_project_root, "stale") is True
    st = read_l1_status("stale", tmp_project_root)
    assert st is not None
    assert st.status == "deferred"
    assert "pre-abort-status" not in st.raw


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
