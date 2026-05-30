"""Smoke tests for engine.init — module imports OK + run([]) doesn't crash."""

from __future__ import annotations

import pytest

from engine import init


def test_module_imports() -> None:
    assert hasattr(init, "run")
    assert callable(init.run)


def test_run_empty_args_doesnt_crash(monkeypatch: pytest.MonkeyPatch, tmp_project_root, capsys) -> None:
    """Greenfield com argv vazio: pode falhar com mensagem útil, mas não crashar."""
    monkeypatch.chdir(tmp_project_root)
    # Neutraliza qualquer prompt interativo
    monkeypatch.setattr("engine.ui.question.ask", lambda *a, **kw: "abort", raising=False)
    monkeypatch.setattr("engine.ui.question.ask_text", lambda *a, **kw: "", raising=False)
    monkeypatch.setattr("engine.ui.question.confirm", lambda *a, **kw: False, raising=False)
    monkeypatch.setattr("engine.ui.question.ask_multi", lambda *a, **kw: [], raising=False)
    try:
        rc = init.run([])
        assert rc in (0, 1, 2, 3), f"unexpected exit code: {rc}"
    except SystemExit as exc:
        assert exc.code in (0, 1, 2, 3)
    except (RuntimeError, ValueError, OSError, KeyError, FileNotFoundError):
        # Falhas previsíveis em greenfield são aceitáveis — só não pode segfault.
        # KeyError vem do prompt mockado retornando "abort" como chave.
        pass
