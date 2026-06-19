"""Smoke tests for engine.reconfigure — module imports OK + run([]) doesn't crash."""

from __future__ import annotations

import pytest

from engine import reconfigure


def test_module_imports() -> None:
    assert hasattr(reconfigure, "run")
    assert callable(reconfigure.run)


def test_reconfigure_invalid_config_emits_config_tag(
    tmp_forge_project, monkeypatch, capsys
) -> None:
    """C-23 (PR20-R2): forge-config.yaml inválido → exit 1 + tag CONFIG-INVALID.

    Antes era `return 1` bare + `except Exception` largo. Agora roteia via
    fail_with_tag(ERR_CONFIG_INVALID) + narrow YamlIOError.
    """
    cfg = tmp_forge_project / ".claude" / "forge" / "forge-config.yaml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text("identity: [unclosed\n", encoding="utf-8")
    monkeypatch.chdir(tmp_forge_project)
    rc = reconfigure.run([])
    assert rc == 1
    combined = capsys.readouterr()
    assert "[FORGE-ERR:CONFIG-INVALID]" in (combined.out + combined.err)


def test_run_empty_args_doesnt_crash(monkeypatch: pytest.MonkeyPatch, tmp_project_root, capsys) -> None:
    """Greenfield com argv vazio: pode falhar com mensagem útil, mas não crashar."""
    monkeypatch.chdir(tmp_project_root)
    monkeypatch.setattr("engine.ui.question.ask", lambda *a, **kw: "abort", raising=False)
    monkeypatch.setattr("engine.ui.question.ask_text", lambda *a, **kw: "", raising=False)
    monkeypatch.setattr("engine.ui.question.confirm", lambda *a, **kw: False, raising=False)
    monkeypatch.setattr("engine.ui.question.ask_multi", lambda *a, **kw: [], raising=False)
    try:
        rc = reconfigure.run([])
        assert rc in (0, 1, 2, 3), f"unexpected exit code: {rc}"
    except SystemExit as exc:
        assert exc.code in (0, 1, 2, 3)
    except (RuntimeError, ValueError, OSError, KeyError, FileNotFoundError):
        pass
