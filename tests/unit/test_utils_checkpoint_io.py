"""Smoke tests para ``engine.utils.checkpoint_io``.

Cobre os contracts dos 3 helpers (save/load/clear) que substituem 30+
funções duplicadas espalhadas em 10 command handlers. Finding #5 do
master review do PR #11.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.utils.checkpoint_io import (
    clear_checkpoint,
    load_yaml_checkpoint,
    save_yaml_checkpoint,
)


@pytest.fixture
def cp_path(tmp_path: Path) -> Path:
    """Path para checkpoint dentro de subdir que ainda não existe.

    Verifica que ``save_yaml_checkpoint`` cria o parent dir
    automaticamente (parity com ``ensure_dir`` dos 10 callers legados).
    """
    return tmp_path / ".claude" / ".sample-checkpoint.yaml"


def test_save_load_roundtrip(cp_path: Path):
    payload = {
        "schema-version": 1,
        "step": "step-ask",
        "at": "2026-06-10T10:30:00Z",
        "project-root": "/tmp/proj",
        "intent-id": "abcd1234-0000-0000-0000-000000000000",
        "feature-slug": "drift-1",
    }
    save_yaml_checkpoint(cp_path, payload)

    loaded = load_yaml_checkpoint(cp_path)
    assert loaded == payload


def test_save_creates_parent_dirs(tmp_path: Path):
    """``save_yaml_checkpoint`` deve criar ``parent`` ausente — parity com 10 callers."""
    deep = tmp_path / "nested" / "deeper" / ".cp.yaml"
    assert not deep.parent.exists()
    save_yaml_checkpoint(deep, {"step": "x", "at": "2026-01-01T00:00:00Z"})
    assert deep.exists()
    assert deep.parent.is_dir()


def test_load_missing_returns_none(tmp_path: Path):
    """Arquivo ausente → ``None`` (não raise) — contract dos callers legados."""
    missing = tmp_path / "nonexistent.yaml"
    assert load_yaml_checkpoint(missing) is None


def test_load_non_dict_yaml_returns_none(tmp_path: Path):
    """YAML que parseia mas não é dict → ``None`` (defesa contra arquivos corrompidos)."""
    weird = tmp_path / "not-a-dict.yaml"
    weird.parent.mkdir(parents=True, exist_ok=True)
    # YAML escalar simples — parseia como string, não dict.
    weird.write_text("just-a-string\n", encoding="utf-8")
    assert load_yaml_checkpoint(weird) is None


def test_clear_idempotent_when_absent(tmp_path: Path):
    """``clear_checkpoint`` em arquivo ausente é no-op (não raise)."""
    missing = tmp_path / "never-existed.yaml"
    clear_checkpoint(missing)  # Não deve raise.
    assert not missing.exists()


def test_clear_removes_existing(cp_path: Path):
    save_yaml_checkpoint(cp_path, {"step": "x", "at": "2026-01-01T00:00:00Z"})
    assert cp_path.exists()

    clear_checkpoint(cp_path)
    assert not cp_path.exists()


def test_save_is_atomic(cp_path: Path):
    """Após ``save`` bem-sucedido, não deve haver ``.tmp`` residual.

    ``yaml_io.write_yaml(atomic=True)`` faz tempfile + ``os.replace``;
    em caminho feliz o ``.tmp`` é renomeado pro target. Se algum dia
    a atomicidade vazar (replace falhou silentemente), este test pega.
    """
    save_yaml_checkpoint(cp_path, {"step": "ok", "at": "2026-01-01T00:00:00Z"})
    tmp_residue = cp_path.with_suffix(cp_path.suffix + ".tmp")
    assert not tmp_residue.exists()
    assert cp_path.exists()


def test_save_overwrites_existing(cp_path: Path):
    """Re-save sobrescreve o conteúdo (write_yaml atomic-replace semantics)."""
    save_yaml_checkpoint(cp_path, {"step": "first", "at": "2026-01-01T00:00:00Z"})
    save_yaml_checkpoint(cp_path, {"step": "second", "at": "2026-01-01T00:00:01Z"})
    loaded = load_yaml_checkpoint(cp_path)
    assert loaded == {"step": "second", "at": "2026-01-01T00:00:01Z"}
