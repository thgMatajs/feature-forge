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


# ── Task 2 (6c): read em implement + degrade-soft ─────────────────────────────


def test_implement_imports_mem_context_hint() -> None:
    """engine.implement importa mem_context_hint sem erro de import."""
    from engine import implement  # noqa: F401
    from engine.integrations.mem import mem_context_hint

    assert callable(mem_context_hint)


def test_implement_print_plan_mode_degrades_soft_when_mem_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_forge_project, capsys
) -> None:
    """_print_plan_mode com mem indisponível não crasha — degrade soft.

    Testa _print_plan_mode diretamente — ponto exato onde mem_context_hint é
    chamado — em vez de ir pelo run() completo (que exige feature+tasks criados).
    Isso garante que o caminho é exercitado sem ambiguidade.

    Correções vs. plano (WR-01-R2 + lição Task 1):
    - Alvo do monkeypatch: engine.implement.mem_context_hint (namespace do handler).
    - Spy hint_called prova que o caminho foi exercitado (não-vacuoso).
    - Assertion pura sem or vacuoso.
    """
    from dataclasses import dataclass, field
    import engine.implement as _impl

    # Stub mínimo de TaskContract pra satisfazer _print_plan_mode.
    @dataclass
    class _FakeTask:
        task_id: str = "TASK-0001"
        description: str = "descrição de teste"
        dependencies: list = field(default_factory=list)
        allowed_files: list = field(default_factory=list)
        bdd_scenarios: list = field(default_factory=list)
        validations: list = field(default_factory=list)
        gates: list = field(default_factory=list)

    hint_called = {"count": 0}

    def _fake_hint(*a: object, **kw: object) -> None:
        hint_called["count"] += 1
        return None

    monkeypatch.setattr(_impl, "mem_context_hint", _fake_hint)

    # Não deve lançar exceção.
    _impl._print_plan_mode(_FakeTask(), tmp_forge_project)

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    # Nenhum traceback de mem deve aparecer.
    assert "forge init" not in combined
    # Prova não-vacuosa: mem_context_hint foi chamado.
    assert hint_called["count"] >= 1, (
        "mem_context_hint deve ser chamado por _print_plan_mode"
    )
