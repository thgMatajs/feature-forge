"""Unit tests — reconfigure submenu card-local (listar + remover).

Cobre:
  - listar vazio (sem dir local/ ou dir vazio)
  - listar N items (renderiza tabela)
  - remover happy (snap → .bak + history)
  - remover cancel (3-caminhos opção 2 ou 3)
  - remover quando `.bak` pré-existente (surface warning, não sobrescreve)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from engine import reconfigure


def _write_local_card(project: Path, name: str, provides: list[str] | None = None) -> None:
    card_dir = project / ".claude" / "forge" / "cards" / "local" / name
    card_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "schema-version": 1,
        "identity": {
            "name": name,
            "version": "1.0.0",
            "description": "Test local",
            "category": "kmp",
            "maturity": "stable",
        },
        "provides": provides or ["kotlin-multiplatform"],
        "requires": [],
        "conflicts-with": [],
    }
    (card_dir / "card.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    (card_dir / "README.md").write_text("# test\n", encoding="utf-8")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    proj = tmp_path / "p"
    (proj / ".claude" / "forge" / "cards" / "local").mkdir(parents=True)
    (proj / ".claude" / "state").mkdir(parents=True)
    return proj


# ── Listar ──────────────────────────────────────────────────────────────────


def test_card_local_list_empty_dir_renders_hint(project, capsys):
    reconfigure._card_local_list(project)
    captured = capsys.readouterr()
    assert "vazio" in captured.out.lower() or "nenhum" in captured.out.lower()


def test_card_local_list_with_two_cards_renders_both(project, capsys):
    _write_local_card(project, "team-a", provides=["kotlin-multiplatform"])
    _write_local_card(project, "team-b", provides=["kotlin"])
    reconfigure._card_local_list(project)
    captured = capsys.readouterr()
    assert "team-a" in captured.out
    assert "team-b" in captured.out


def test_card_local_list_when_local_dir_missing(tmp_path, capsys):
    # No .claude/cards/local dir at all → renders hint, doesn't crash
    proj = tmp_path / "pristine"
    proj.mkdir()
    reconfigure._card_local_list(proj)
    captured = capsys.readouterr()
    assert "nenhum" in captured.out.lower()


# ── Remover ─────────────────────────────────────────────────────────────────


def test_card_local_remove_happy_path_moves_to_bak(project):
    _write_local_card(project, "team-x")
    with patch.object(reconfigure.question, "ask") as ask_mock, patch.object(
        reconfigure, "_append_history"
    ) as hist_mock:
        ask_mock.side_effect = ["team-x", "remove"]
        reconfigure._card_local_remove(project, working={})
    assert not (project / ".claude" / "forge" / "cards" / "local" / "team-x").exists()
    assert (project / ".claude" / "forge" / "cards" / "local" / "team-x.bak").is_dir()
    hist_mock.assert_called_once()
    args = hist_mock.call_args.args
    assert args[1]["op"] == "card-local-remove"
    assert args[1]["name"] == "team-x"


def test_card_local_remove_cancel_keeps_card(project):
    _write_local_card(project, "team-y")
    with patch.object(reconfigure.question, "ask") as ask_mock:
        ask_mock.side_effect = ["team-y", "keep"]
        reconfigure._card_local_remove(project, working={})
    assert (project / ".claude" / "forge" / "cards" / "local" / "team-y").is_dir()
    assert not (project / ".claude" / "forge" / "cards" / "local" / "team-y.bak").exists()


def test_card_local_remove_abort_keeps_card(project):
    _write_local_card(project, "team-q")
    with patch.object(reconfigure.question, "ask") as ask_mock:
        ask_mock.side_effect = ["team-q", "abort"]
        reconfigure._card_local_remove(project, working={})
    assert (project / ".claude" / "forge" / "cards" / "local" / "team-q").is_dir()
    assert not (project / ".claude" / "forge" / "cards" / "local" / "team-q.bak").exists()


def test_card_local_remove_cancelar_at_first_prompt(project):
    _write_local_card(project, "team-z")
    with patch.object(reconfigure.question, "ask") as ask_mock:
        ask_mock.side_effect = ["cancelar"]
        reconfigure._card_local_remove(project, working={})
    assert (project / ".claude" / "forge" / "cards" / "local" / "team-z").is_dir()


def test_card_local_remove_with_preexisting_bak_surface_warning(project, capsys):
    _write_local_card(project, "team-w")
    # cria .bak fake (simula remoção anterior não limpa)
    bak = project / ".claude" / "forge" / "cards" / "local" / "team-w.bak"
    bak.mkdir()
    with patch.object(reconfigure.question, "ask") as ask_mock:
        ask_mock.side_effect = ["team-w", "remove"]
        reconfigure._card_local_remove(project, working={})
    # card original deve permanecer (não sobrescrevemos .bak)
    assert (project / ".claude" / "forge" / "cards" / "local" / "team-w").is_dir()
    captured = capsys.readouterr()
    assert "já existe" in captured.out or "cleanup-bak" in captured.out


def test_card_local_remove_empty_dir_returns_early(project, capsys):
    reconfigure._card_local_remove(project, working={})
    captured = capsys.readouterr()
    assert "vazio" in captured.out.lower() or "nada a remover" in captured.out.lower()


# ── _handle_card_local dispatch ─────────────────────────────────────────────


def test_handle_card_local_dispatches_to_list(project):
    with patch.object(reconfigure.question, "ask") as ask_mock, patch.object(
        reconfigure, "_card_local_list"
    ) as list_mock:
        ask_mock.side_effect = ["list"]
        reconfigure._handle_card_local(project, current={}, working={})
    list_mock.assert_called_once_with(project)


def test_handle_card_local_back_is_noop(project):
    with patch.object(reconfigure.question, "ask") as ask_mock, patch.object(
        reconfigure, "_card_local_list"
    ) as list_mock, patch.object(
        reconfigure, "_card_local_add"
    ) as add_mock, patch.object(
        reconfigure, "_card_local_remove"
    ) as remove_mock:
        ask_mock.side_effect = ["back"]
        reconfigure._handle_card_local(project, current={}, working={})
    list_mock.assert_not_called()
    add_mock.assert_not_called()
    remove_mock.assert_not_called()


# ── Registry wiring ─────────────────────────────────────────────────────────


def test_card_local_handler_registered_in_dispatch_table():
    assert "card-local" in reconfigure._CATEGORY_HANDLERS
    assert reconfigure._CATEGORY_HANDLERS["card-local"] is reconfigure._handle_card_local


# ── _append_history dual-signature ──────────────────────────────────────────


def test_append_history_positional_dict_writes_op_entry(project):
    reconfigure._append_history(
        project, {"op": "card-local-remove", "name": "x", "bak": "x.bak"}
    )
    history = project / ".claude" / "workflow-config-history.jsonl"
    assert history.is_file()
    import json
    entry = json.loads(history.read_text().strip())
    assert entry["op"] == "card-local-remove"
    assert entry["name"] == "x"
    assert entry["schema-version"] == 1
    assert "timestamp" in entry


def test_append_history_legacy_kwargs_still_works(project):
    reconfigure._append_history(
        project, before_sha="aaa", after_sha="bbb", notes="changed cards"
    )
    history = project / ".claude" / "workflow-config-history.jsonl"
    import json
    entry = json.loads(history.read_text().strip())
    assert entry["action"] == "reconfigure-applied"
    assert entry["before-snapshot-sha"] == "aaa"
    assert entry["notes"] == "changed cards"


# ── Adicionar (do skeleton) ─────────────────────────────────────────────────


def test_card_local_add_happy_creates_skeleton(project):
    """Adicionar happy: prompts respondidos, dir criado, validate roda."""
    with patch.object(reconfigure.question, "ask") as ask_mock, patch.object(
        reconfigure.question, "ask_text"
    ) as ask_text_mock, patch.object(
        reconfigure, "_append_history"
    ) as hist_mock:
        # ordem de prompts:
        #   ask_text("Nome do card") → "hilt-di"
        #   ask_text("Capability") → "di-framework"
        #   ask("Adicionar label local?") → "yes"
        #   ask_text("Conflicts-with") → "koin-annotations"
        #   ask_text("Target platforms") → "android"
        #   ask("Confirma 3-caminhos") → "create"
        ask_text_mock.side_effect = [
            "hilt-di",
            "di-framework",
            "koin-annotations",
            "android",
        ]
        ask_mock.side_effect = ["yes", "create"]
        reconfigure._card_local_add(project, working={})

    card_dir = project / ".claude" / "forge" / "cards" / "local" / "hilt-di"
    assert card_dir.is_dir()
    assert (card_dir / "card.yaml").is_file()
    assert (card_dir / "README.md").is_file()
    assert (card_dir / "detection" / "signals.yaml").is_file()
    parsed = yaml.safe_load((card_dir / "card.yaml").read_text(encoding="utf-8"))
    assert parsed["identity"]["name"] == "hilt-di"
    assert parsed["provides"] == ["di-framework"]
    assert parsed["conflicts-with"] == ["koin-annotations"]
    assert parsed.get("legacy-marker", False) is False
    hist_mock.assert_called_once()


def test_card_local_add_name_collision_aborts(project):
    """Se nome já existe (canon OU local), prompt repete ou aborta."""
    _write_local_card(project, "existing")
    with patch.object(reconfigure.question, "ask") as ask_mock, patch.object(
        reconfigure.question, "ask_text"
    ) as ask_text_mock:
        ask_text_mock.side_effect = ["existing"]
        ask_mock.side_effect = ["abort"]
        reconfigure._card_local_add(project, working={})
    # nenhum card novo criado
    assert len(list((project / ".claude" / "forge" / "cards" / "local").iterdir())) == 1


def test_card_local_add_cancel_at_confirmation(project):
    with patch.object(reconfigure.question, "ask") as ask_mock, patch.object(
        reconfigure.question, "ask_text"
    ) as ask_text_mock:
        ask_text_mock.side_effect = ["xyz", "some-cap", "", "android"]
        ask_mock.side_effect = ["yes", "cancel"]
        reconfigure._card_local_add(project, working={})
    assert not (project / ".claude" / "forge" / "cards" / "local" / "xyz").exists()
