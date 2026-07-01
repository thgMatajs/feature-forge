"""Smoke tests for engine.graph_cli — module imports OK + run([]) doesn't crash."""

from __future__ import annotations

import pytest

from engine import graph_cli
from engine.graph import queries as gq
from engine.utils.sqlite_io import open_db, transaction


def _seed_modules(db_path):
    """Semeia um graph.db com módulos conhecidos pra testes de did-you-mean."""
    conn = open_db(db_path, create=True)
    try:
        with transaction(conn):
            conn.executemany(
                "INSERT INTO files(path, language, module) VALUES (?, ?, ?)",
                [
                    ("src/auth/AuthVM.kt", "kotlin", ":feature:auth"),
                    ("src/core/CoreUtil.kt", "kotlin", ":core"),
                ],
            )
    finally:
        conn.close()


def test_module_imports() -> None:
    assert hasattr(graph_cli, "run")
    assert callable(graph_cli.run)


def test_q4_unknown_module_suggests_close_match(tmp_path, monkeypatch, capsys):
    """D2 (Fase 1): Q4 com módulo inexistente sugere o mais próximo (did-you-mean)."""
    from pathlib import Path

    db = tmp_path / ".claude" / "forge" / "graph.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    _seed_modules(db)

    # Stub find_symbols_in_module e list_modules pra usar nosso DB diretamente.
    from engine.graph import queries as _orig_queries

    _orig_find = _orig_queries.find_symbols_in_module
    _orig_list = _orig_queries.list_modules
    monkeypatch.setattr(
        graph_cli.gq, "find_symbols_in_module",
        lambda root, mod, **kw: _orig_find(root, mod, db_path=db),
    )
    monkeypatch.setattr(
        graph_cli.gq, "list_modules",
        lambda root, **kw: _orig_list(root, db_path=db),
    )

    monkeypatch.setattr(
        "engine.ui.question.ask_text",
        lambda *a, **k: ":features:auth",  # typo: ":features:" em vez de ":feature:"
    )

    graph_cli._q_symbols(tmp_path)
    out, err = capsys.readouterr()
    combined = out + err
    assert ":feature:auth" in combined, (
        "did-you-mean deve sugerir ':feature:auth'; "
        f"saída={combined!r}"
    )


def test_run_empty_args_doesnt_crash(monkeypatch: pytest.MonkeyPatch, tmp_project_root, capsys) -> None:
    """Greenfield com argv vazio: pode falhar com mensagem útil, mas não crashar."""
    monkeypatch.chdir(tmp_project_root)
    monkeypatch.setattr("engine.ui.question.ask", lambda *a, **kw: "abort", raising=False)
    monkeypatch.setattr("engine.ui.question.ask_text", lambda *a, **kw: "", raising=False)
    monkeypatch.setattr("engine.ui.question.confirm", lambda *a, **kw: False, raising=False)
    monkeypatch.setattr("engine.ui.question.ask_multi", lambda *a, **kw: [], raising=False)
    try:
        rc = graph_cli.run([])
        assert rc in (0, 1, 2, 3), f"unexpected exit code: {rc}"
    except SystemExit as exc:
        assert exc.code in (0, 1, 2, 3)
    except (RuntimeError, ValueError, OSError, KeyError, FileNotFoundError):
        pass
