"""Smoke tests for engine.implement — module imports OK + run([]) doesn't crash."""

from __future__ import annotations

import pytest

from engine import implement


def test_module_imports() -> None:
    assert hasattr(implement, "run")
    assert callable(implement.run)


def test_run_empty_args_returns_nonzero_on_non_forge_project(
    monkeypatch: pytest.MonkeyPatch, tmp_project_root, capsys
) -> None:
    """Empty argv on a non-forge project (no .claude/) must return non-zero exit
    with a message pointing the user at `forge init`."""
    monkeypatch.chdir(tmp_project_root)
    monkeypatch.setattr("engine.ui.question.ask", lambda *a, **kw: "abort", raising=False)
    monkeypatch.setattr("engine.ui.question.ask_text", lambda *a, **kw: "", raising=False)
    monkeypatch.setattr("engine.ui.question.confirm", lambda *a, **kw: False, raising=False)
    monkeypatch.setattr("engine.ui.question.ask_multi", lambda *a, **kw: [], raising=False)
    # B-007 (master review PR #15): pin exit code in {1, 2} pra detectar
    # regressão silenciosa caso outro SystemExit colateral passe pelo assert.
    # 2 = ProjectRootNotFoundError; 1 = qualquer outro erro de domínio.
    try:
        rc = implement.run([])
        assert rc in (1, 2), f"expected exit 1 or 2 on non-forge project, got {rc!r}"
    except SystemExit as exc:
        assert exc.code in (1, 2), f"expected SystemExit code in {{1,2}}, got {exc.code!r}"
    captured = capsys.readouterr()
    combined = (captured.out + captured.err).lower()
    assert ".claude" in combined, (
        f"expected message referencing '.claude' to guide user, got: {combined!r}"
    )
