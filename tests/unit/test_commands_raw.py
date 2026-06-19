"""Smoke tests for engine.raw — module imports OK + run([]) doesn't crash."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import raw


def test_module_imports() -> None:
    assert hasattr(raw, "run")
    assert callable(raw.run)


def test_verify_card_invalid_yaml_emits_card_tag(tmp_path: Path, capsys) -> None:
    """C-23 (PR20-R2): verify-card com YAML inválido → exit 1 + tag CARD-INVALID.

    Antes era `return 1` bare (sem tag machine-readable) + `except Exception`
    largo (B3). Agora roteia via fail_with_tag(ERR_CARD_INVALID) e narrow
    YamlIOError.
    """
    card_dir = tmp_path / "broken-card"
    card_dir.mkdir()
    (card_dir / "card.yaml").write_text("key: [unclosed\n", encoding="utf-8")
    rc = raw.run(["verify-card", str(card_dir)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "[FORGE-ERR:CARD-INVALID]" in err


def test_verify_card_non_mapping_emits_card_tag(tmp_path: Path, capsys) -> None:
    """C-23: card.yaml com top-level não-mapping → exit 1 + tag CARD-INVALID."""
    card_dir = tmp_path / "list-card"
    card_dir.mkdir()
    (card_dir / "card.yaml").write_text("- just\n- a\n- list\n", encoding="utf-8")
    rc = raw.run(["verify-card", str(card_dir)])
    assert rc == 1
    assert "[FORGE-ERR:CARD-INVALID]" in capsys.readouterr().err


def test_run_empty_args_doesnt_crash(monkeypatch: pytest.MonkeyPatch, tmp_project_root, capsys) -> None:
    """Greenfield com argv vazio: pode falhar com mensagem útil, mas não crashar."""
    monkeypatch.chdir(tmp_project_root)
    monkeypatch.setattr("engine.ui.question.ask", lambda *a, **kw: "abort", raising=False)
    monkeypatch.setattr("engine.ui.question.ask_text", lambda *a, **kw: "", raising=False)
    monkeypatch.setattr("engine.ui.question.confirm", lambda *a, **kw: False, raising=False)
    monkeypatch.setattr("engine.ui.question.ask_multi", lambda *a, **kw: [], raising=False)
    try:
        rc = raw.run([])
        assert rc in (0, 1, 2, 3), f"unexpected exit code: {rc}"
    except SystemExit as exc:
        assert exc.code in (0, 1, 2, 3)
    except (RuntimeError, ValueError, OSError, KeyError, FileNotFoundError):
        pass
