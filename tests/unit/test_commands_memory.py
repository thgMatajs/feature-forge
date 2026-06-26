"""W-ROUTE 6a — testes do `forge memory` arg-driven (substitui o smoke de menu).

Cobre: dispatch por ação (equivalência — cada ação chama o wrapper certo),
usage em ação ausente/desconhecida, contrato pré-init (exit 1), e a PROVA
estrutural de BUG-M1 (zero prompt pausável / zero checkpoint no módulo).

Os testes de dispatch monkeypatcham `memory_cli.find_project_root` pra isolar
a unidade do resolver de projeto (find_project_root exige marker forge, não só
.git/ — não é o que estes testes exercitam).
"""
from __future__ import annotations

import inspect

import pytest

from engine import memory_cli
from engine.integrations.mem import MemQuery
from engine.utils.paths import ProjectRootNotFoundError


def _patch_root(monkeypatch, tmp_path):
    monkeypatch.setattr(memory_cli, "find_project_root", lambda: tmp_path)


def test_module_imports() -> None:
    assert callable(memory_cli.run)


def test_pre_init_returns_exit_1(monkeypatch) -> None:
    def _raise():
        raise ProjectRootNotFoundError("sem projeto forge")
    monkeypatch.setattr(memory_cli, "find_project_root", _raise)
    assert memory_cli.run([]) == 1


def test_empty_argv_is_usage(monkeypatch, tmp_path) -> None:
    _patch_root(monkeypatch, tmp_path)
    # fail_with_tag(ERR_USAGE) retorna 1 (exit 2 reservado para pausa em cli.py)
    assert memory_cli.run([]) == 1


def test_unknown_action_is_usage(monkeypatch, tmp_path) -> None:
    _patch_root(monkeypatch, tmp_path)
    assert memory_cli.run(["bogus"]) == 1


# ── Equivalência: cada ação delega ao wrapper correto ────────────────────

def test_search_calls_mem_find(monkeypatch, tmp_path) -> None:
    _patch_root(monkeypatch, tmp_path)
    seen: dict = {}

    def _fake_find(root, query, **kw):
        seen["query"] = query
        return MemQuery(ok=True, data=[])

    monkeypatch.setattr(memory_cli, "mem_find", _fake_find)
    assert memory_cli.run(["search", "reuse", "first"]) == 0
    assert seen["query"] == "reuse first"


def test_search_without_query_is_usage(monkeypatch, tmp_path) -> None:
    _patch_root(monkeypatch, tmp_path)
    assert memory_cli.run(["search"]) == 1


def test_inspect_with_id_calls_mem_get(monkeypatch, tmp_path) -> None:
    _patch_root(monkeypatch, tmp_path)
    seen: dict = {}

    def _fake_get(root, note_id):
        seen["id"] = note_id
        return MemQuery(ok=True, data={"id": note_id, "title": "t", "body": "b", "type": "feedback"})

    monkeypatch.setattr(memory_cli, "mem_get", _fake_get)
    assert memory_cli.run(["inspect", "01ABC"]) == 0
    assert seen["id"] == "01ABC"


def test_inspect_without_id_calls_mem_stats(monkeypatch, tmp_path) -> None:
    _patch_root(monkeypatch, tmp_path)
    called: dict = {}

    def _fake_stats(root):
        called["hit"] = True
        return MemQuery(ok=True, data={"total": 0, "live": 0})

    monkeypatch.setattr(memory_cli, "mem_stats", _fake_stats)
    assert memory_cli.run(["inspect"]) == 0
    assert called.get("hit") is True


def test_export_calls_mem_brief(monkeypatch, tmp_path) -> None:
    _patch_root(monkeypatch, tmp_path)
    seen: dict = {}

    def _fake_brief(root, *, budget=None):
        seen["budget"] = budget
        return MemQuery(ok=True, data=[])

    monkeypatch.setattr(memory_cli, "mem_brief", _fake_brief)
    assert memory_cli.run(["export", "--budget", "200"]) == 0
    assert seen["budget"] == 200


def test_distill_calls_mem_evolve(monkeypatch, tmp_path) -> None:
    _patch_root(monkeypatch, tmp_path)
    seen: dict = {}

    def _fake_evolve(root, *, apply=False):
        seen["apply"] = apply
        return MemQuery(ok=True, data={"archive": [], "dup_clusters": [], "applied": 0})

    monkeypatch.setattr(memory_cli, "mem_evolve", _fake_evolve)
    assert memory_cli.run(["distill", "--apply"]) == 0
    assert seen["apply"] is True


def test_degraded_mem_returns_1(monkeypatch, tmp_path) -> None:
    _patch_root(monkeypatch, tmp_path)
    monkeypatch.setattr(
        memory_cli, "mem_find",
        lambda root, q, **kw: MemQuery(ok=False, data=None, message="mem indisponível. Três caminhos: ..."),
    )
    assert memory_cli.run(["search", "x"]) == 1


# ── C-002: --json não polui os args posicionais do dispatch ──────────────

def test_json_flag_stripped_from_query(monkeypatch, tmp_path) -> None:
    _patch_root(monkeypatch, tmp_path)
    seen: dict = {}

    def _fake_find(root, query, **kw):
        seen["query"] = query
        return MemQuery(ok=True, data=[])

    monkeypatch.setattr(memory_cli, "mem_find", _fake_find)
    assert memory_cli.run(["search", "reuse", "--json"]) == 0
    assert seen["query"] == "reuse"  # --json removido, não poluiu a query


# ── C-001: JSON-mode emite o JSON do mem (substitui test_memory_json) ────

def test_inspect_json_mode_emits_stats_json(monkeypatch, tmp_path, capsys) -> None:
    import json as _json
    _patch_root(monkeypatch, tmp_path)
    monkeypatch.setattr(memory_cli.output_mode, "is_json_mode", lambda: True)
    monkeypatch.setattr(
        memory_cli, "mem_stats",
        lambda root: MemQuery(ok=True, data={"total": 2, "live": 2}),
    )
    assert memory_cli.run(["inspect", "--json"]) == 0
    out = capsys.readouterr().out
    assert _json.loads(out) == {"total": 2, "live": 2}


def test_search_json_mode_emits_hits_json(monkeypatch, tmp_path, capsys) -> None:
    import json as _json
    _patch_root(monkeypatch, tmp_path)
    monkeypatch.setattr(memory_cli.output_mode, "is_json_mode", lambda: True)
    monkeypatch.setattr(
        memory_cli, "mem_find",
        lambda root, q, **kw: MemQuery(ok=True, data=[{"id": "X", "title": "t"}]),
    )
    assert memory_cli.run(["search", "reuse", "--json"]) == 0
    out = capsys.readouterr().out
    assert _json.loads(out) == [{"id": "X", "title": "t"}]


# ── Prova estrutural de BUG-M1: ausência de estado multi-passo ───────────

def test_no_interactive_prompts_in_module() -> None:
    src = inspect.getsource(memory_cli)
    assert "question.ask" not in src
    assert "allow_pause" not in src


def test_checkpoint_machinery_removed() -> None:
    for name in (
        "_save_memory_cli_checkpoint",
        "_load_memory_cli_checkpoint",
        "_clear_memory_cli_checkpoint",
        "_MemoryCliCheckpoint",
        "_memory_snapshot",
    ):
        assert not hasattr(memory_cli, name), f"{name} deveria ter sumido"
