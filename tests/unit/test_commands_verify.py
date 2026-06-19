"""Smoke tests for engine.verify — module imports OK + run([]) doesn't crash."""

from __future__ import annotations

import pytest

from engine import verify


def test_module_imports() -> None:
    assert hasattr(verify, "run")
    assert callable(verify.run)


def test_resolve_scope_strips_json_meta_flag(tmp_project_root) -> None:
    """C-39 (PR21-I8): `--json` posicional não é consumido como slug de feature.

    Antes do fix, `forge verify --json` resolveria `--json` como feature slug.
    Agora a meta-flag é removida antes do parse posicional → cai na inferência
    de feature ativa (vazia neste tmp → "").
    """
    kind, target = verify._resolve_scope(
        ["--json"], tmp_project_root, allow_prompt=False
    )
    assert kind == "feature"
    assert target == "", f"--json não deveria virar slug; got {target!r}"
    # E não atrapalha um TASK- legítimo que venha depois da flag.
    kind2, target2 = verify._resolve_scope(
        ["--json", "TASK-0007"], tmp_project_root, allow_prompt=False
    )
    assert kind2 == "task"
    assert target2 == "TASK-0007"


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
        rc = verify.run([])
        assert rc in (1, 2), f"expected exit 1 or 2 on non-forge project, got {rc!r}"
    except SystemExit as exc:
        assert exc.code in (1, 2), f"expected SystemExit code in {{1,2}}, got {exc.code!r}"
    captured = capsys.readouterr()
    combined = (captured.out + captured.err).lower()
    assert ".claude" in combined, (
        f"expected message referencing '.claude' to guide user, got: {combined!r}"
    )
