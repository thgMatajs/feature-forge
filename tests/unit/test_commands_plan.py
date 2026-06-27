"""Smoke tests for engine.plan — module imports OK + run([]) doesn't crash."""

from __future__ import annotations

import pytest

from engine import plan


def test_module_imports() -> None:
    assert hasattr(plan, "run")
    assert callable(plan.run)


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
    try:
        rc = plan.run([])
        assert rc in (1, 2), f"expected exit 1 or 2 on non-forge project, got {rc!r}"
    except SystemExit as exc:
        assert exc.code in (1, 2), f"expected SystemExit code in {{1,2}}, got {exc.code!r}"
    captured = capsys.readouterr()
    combined = (captured.out + captured.err).lower()
    assert ".claude" in combined, (
        f"expected message referencing '.claude' to guide user, got: {combined!r}"
    )


# ── Task 1 (6c): read em plan + degrade-soft ──────────────────────────────────


def test_plan_imports_mem_context_hint() -> None:
    """engine.plan importa mem_context_hint sem erro de import."""
    from engine import plan
    from engine.integrations.mem import mem_context_hint
    # Basta importar sem exceção — confirma que a dependência existe.
    assert callable(mem_context_hint)


def test_plan_run_degrades_soft_when_mem_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_project_root, capsys
) -> None:
    """plan.run com mem indisponível (binary missing) não crasha — degrade soft.

    Stubamos mem_context_hint pra retornar None (degrade), depois rodamos
    plan.run em projeto sem .claude/ pra confirmar que o comportamento de
    'project not found' ainda é o que vence (não um crash de mem).
    O output pode conter "forge init" do erro de projeto-não-encontrado —
    isso é esperado. O que NÃO pode acontecer é crash ou traceback do mem.
    """
    import engine.plan as _plan
    from engine.integrations import mem as _mem

    monkeypatch.setattr(_mem, "mem_context_hint", lambda *a, **kw: None)
    monkeypatch.chdir(tmp_project_root)
    monkeypatch.setattr("engine.ui.question.ask", lambda *a, **kw: "abort", raising=False)
    monkeypatch.setattr("engine.ui.question.ask_text", lambda *a, **kw: "", raising=False)
    monkeypatch.setattr("engine.ui.question.confirm", lambda *a, **kw: False, raising=False)
    try:
        rc = _plan.run([])
        assert rc in (1, 2)
    except SystemExit as exc:
        assert exc.code in (1, 2)
    # Nenhum traceback de mem deve aparecer — degrade silencioso (D1).
    # (O "forge init" no output é do project-not-found, não do mem — esperado.)
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "mem_context_hint" not in combined
    assert "AttributeError" not in combined
    assert "Traceback" not in combined
