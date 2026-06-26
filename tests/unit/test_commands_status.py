"""Smoke tests for engine.status — module imports OK + run([]) doesn't crash."""

from __future__ import annotations

import pytest

from engine import status


def test_module_imports() -> None:
    assert hasattr(status, "run")
    assert callable(status.run)


def test_run_empty_args_doesnt_crash(monkeypatch: pytest.MonkeyPatch, tmp_project_root, capsys) -> None:
    """Greenfield com argv vazio: pode falhar com mensagem útil, mas não crashar."""
    monkeypatch.chdir(tmp_project_root)
    monkeypatch.setattr("engine.ui.question.ask", lambda *a, **kw: "abort", raising=False)
    monkeypatch.setattr("engine.ui.question.ask_text", lambda *a, **kw: "", raising=False)
    monkeypatch.setattr("engine.ui.question.confirm", lambda *a, **kw: False, raising=False)
    monkeypatch.setattr("engine.ui.question.ask_multi", lambda *a, **kw: [], raising=False)
    try:
        rc = status.run([])
        assert rc in (0, 1, 2, 3), f"unexpected exit code: {rc}"
    except SystemExit as exc:
        assert exc.code in (0, 1, 2, 3)
    except (RuntimeError, ValueError, OSError, KeyError, FileNotFoundError):
        pass


# ── Task 3 (6b): _render_memory com mem stats ─────────────────────────────


def test_render_memory_shows_mem_stats(monkeypatch, tmp_project_root, capsys):
    """_render_memory exibe total/live/stale/by_type de mem stats."""
    from engine import status
    from engine.integrations.mem import MemQuery

    monkeypatch.chdir(tmp_project_root)
    monkeypatch.setattr(
        status, "mem_stats",
        lambda root: MemQuery(
            ok=True,
            data={"total": 5, "live": 4, "stale": 1, "by_type": {"feedback": 3, "reference": 2}},
        ),
    )
    status._render_memory(tmp_project_root, {})
    out = capsys.readouterr().out
    assert "total=5" in out or "total: 5" in out
    assert "live=4" in out or "live: 4" in out
    assert "stale=1" in out or "stale: 1" in out
    assert "feedback=3" in out
    assert "reference=2" in out


def test_render_memory_degrades_soft_when_mem_unavailable(monkeypatch, tmp_project_root, capsys):
    """Se mem_stats retorna ok=False, exibe placeholder sem crash."""
    from engine import status
    from engine.integrations.mem import MemQuery

    monkeypatch.chdir(tmp_project_root)
    monkeypatch.setattr(
        status, "mem_stats",
        lambda root: MemQuery(ok=False, data=None, message="mem indisponível. Três caminhos: ..."),
    )
    # Não deve levantar exceção
    status._render_memory(tmp_project_root, {})
    out = capsys.readouterr().out
    # Deve ainda renderizar L1 counts (não crashar)
    assert "L1 active" in out or "l1" in out.lower()
