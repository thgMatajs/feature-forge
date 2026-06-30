"""Testes do helper compartilhado `parse_allowed_files` (H-002).

O parsing de `allowed_files` vivia inline em `engine/implement.py:_load_task_contract`
sem helper standalone (Mandamento #3 — reuso antes de criar). Este helper puro
é extraído pra ser reusado por `engine/implement.py` E pelo snapshot da impl
(`engine/qa/ingest.py::snapshot_impl_files`). NÃO re-implementar o parse.
"""

from __future__ import annotations

from engine.utils.task_contract import parse_allowed_files


def test_parse_allowed_files_snake_case():
    raw = {"allowed_files": ["src/a.kt", "src/b.kt"]}
    assert parse_allowed_files(raw) == ["src/a.kt", "src/b.kt"]


def test_parse_allowed_files_kebab_case():
    raw = {"allowed-files": ["src/a.kt"]}
    assert parse_allowed_files(raw) == ["src/a.kt"]


def test_parse_allowed_files_snake_wins_over_kebab():
    # Espelha `raw.get("allowed_files") or raw.get("allowed-files")`:
    # snake-case tem precedência quando ambos presentes e snake é truthy.
    raw = {"allowed_files": ["snake.kt"], "allowed-files": ["kebab.kt"]}
    assert parse_allowed_files(raw) == ["snake.kt"]


def test_parse_allowed_files_missing_returns_empty():
    assert parse_allowed_files({}) == []


def test_parse_allowed_files_non_list_returns_empty():
    # Robustez: YAML que carregou string/dict no campo não explode.
    assert parse_allowed_files({"allowed_files": "src/a.kt"}) == []
    assert parse_allowed_files({"allowed_files": {"a": 1}}) == []


def test_parse_allowed_files_coerces_entries_to_str():
    raw = {"allowed_files": ["src/a.kt", 42]}
    assert parse_allowed_files(raw) == ["src/a.kt", "42"]


def test_parse_allowed_files_non_dict_returns_empty():
    assert parse_allowed_files(None) == []  # type: ignore[arg-type]
    assert parse_allowed_files("nope") == []  # type: ignore[arg-type]
