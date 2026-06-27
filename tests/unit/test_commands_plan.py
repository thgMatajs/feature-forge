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
    monkeypatch: pytest.MonkeyPatch, tmp_forge_project, capsys
) -> None:
    """plan.run com mem indisponível: mem_context_hint é chamada (não-vacuoso) e retorna None sem crash.

    Patcha engine.plan.mem_context_hint (o nome no namespace de plan — plan.py
    usa `from ... import mem_context_hint`), e também find_project_root +
    _elicit_slug no mesmo namespace pra permitir que o fluxo alcance a chamada
    de mem_context_hint sem exigir um projeto forge completamente inicializado.

    Confirma que o degrade-soft (None) não gera crash, não vaza nag "forge init"
    do mem, e não vaza o nome da função no output.
    """
    import engine.plan as _plan

    hint_called = {"count": 0}

    def _stub_hint(*a, **kw):
        hint_called["count"] += 1
        return None

    monkeypatch.setattr(_plan, "mem_context_hint", _stub_hint)
    monkeypatch.setattr(_plan, "find_project_root", lambda *a, **kw: tmp_forge_project)
    monkeypatch.setattr(_plan, "_elicit_slug", lambda *a, **kw: "test-feature-slug")
    # Stub _run_waves_for_subtype so the test exits cleanly after mem_context_hint.
    monkeypatch.setattr(_plan, "_run_waves_for_subtype", lambda *a, **kw: 0)
    monkeypatch.chdir(tmp_forge_project)
    monkeypatch.setattr("engine.ui.question.ask", lambda *a, **kw: "abort", raising=False)
    monkeypatch.setattr("engine.ui.question.ask_text", lambda *a, **kw: "5", raising=False)
    monkeypatch.setattr("engine.ui.question.confirm", lambda *a, **kw: False, raising=False)
    try:
        rc = _plan.run([])
        assert rc in (0, 1, 2, 130)
    except SystemExit as exc:
        assert exc.code in (0, 1, 2, 130)
    # Confirma que mem_context_hint foi de facto chamada (não-vacuoso — D1).
    assert hint_called["count"] >= 1, (
        "mem_context_hint não foi chamada — o caminho de degrade não foi exercitado"
    )
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "mem_context_hint" not in combined
    assert "Traceback" not in combined
    assert "AttributeError" not in combined
