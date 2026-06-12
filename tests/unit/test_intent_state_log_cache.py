"""Regression — _read_intent_log usa cache process-level.

PR #13 review #3405256063. Antes, cada chamada de `read_response`
re-parseava o JSONL inteiro do disco. Em multi-intent handlers
(init brownfield/greenfield, reconfigure backend submenu) isso era
O(n) por prompt — n linhas × n prompts.

Este test confirma:

  1. Duas leituras seguidas com mesmo `project_root` parseiam o
     arquivo apenas 1× (cache hit no segundo call).
  2. `_append_intent_log` atualiza o cache incrementalmente — sem
     re-leitura subsequente.
  3. `clear_intent_files(also_log=True)` invalida o cache.
  4. `clear_intent_log_only` invalida o cache.
  5. `_reset_log_cache` é escape hatch idempotente pra tests.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from engine.ui import intent_state


@pytest.fixture(autouse=True)
def _reset_cache_between_tests() -> None:
    """Garante isolamento — cache survives entre tests senão fica frágil."""
    intent_state._reset_log_cache()
    yield
    intent_state._reset_log_cache()


def _seed_log(project_root: Path, *, intent_id: str, payload: dict) -> Path:
    """Gravar uma entry via API canônica pra popular o JSONL."""
    intent_state._append_intent_log(
        project_root, intent_id=intent_id, response=payload
    )
    return intent_state._log_path(project_root)


def test_read_intent_log_caches_disk_read(tmp_path: Path) -> None:
    """Dois `_read_intent_log` seguidos parseiam o arquivo apenas 1×."""
    _seed_log(tmp_path, intent_id="id-1", payload={"choice": "a"})
    # Limpa o cache pra simular cold start (fixture ja resetou, mas o seed
    # populou via append — limpa de novo).
    intent_state._reset_log_cache()

    log_path = intent_state._log_path(tmp_path)
    real_read = Path.read_text
    call_count = {"n": 0}

    def counting_read(self, *args, **kwargs):
        if self == log_path:
            call_count["n"] += 1
        return real_read(self, *args, **kwargs)

    with patch.object(Path, "read_text", counting_read):
        first = intent_state._read_intent_log(tmp_path)
        second = intent_state._read_intent_log(tmp_path)
        third = intent_state._read_intent_log(tmp_path)

    assert first == second == third == {"id-1": {"choice": "a"}}
    assert call_count["n"] == 1, (
        f"esperava 1 read_text cached, observou {call_count['n']} — cache não pegou"
    )


def test_append_intent_log_updates_cache_incrementally(tmp_path: Path) -> None:
    """Append novo intent reflete no cache sem re-ler o disco."""
    _seed_log(tmp_path, intent_id="id-1", payload={"choice": "a"})
    # Primeira leitura popula cache.
    first = intent_state._read_intent_log(tmp_path)
    assert first == {"id-1": {"choice": "a"}}

    # Append novo intent — deve atualizar cache in-place.
    intent_state._append_intent_log(
        tmp_path, intent_id="id-2", response={"choice": "b"}
    )

    # Leitura imediata deve ver as duas entries SEM re-parsear o arquivo.
    log_path = intent_state._log_path(tmp_path)
    real_read = Path.read_text
    call_count = {"n": 0}

    def counting_read(self, *args, **kwargs):
        if self == log_path:
            call_count["n"] += 1
        return real_read(self, *args, **kwargs)

    with patch.object(Path, "read_text", counting_read):
        second = intent_state._read_intent_log(tmp_path)

    assert second == {"id-1": {"choice": "a"}, "id-2": {"choice": "b"}}
    assert call_count["n"] == 0, (
        f"cache deveria absorver o append; observou {call_count['n']} disk reads"
    )


def test_clear_intent_files_also_log_invalidates_cache(tmp_path: Path) -> None:
    """clear_intent_files(also_log=True) limpa cache + arquivo."""
    _seed_log(tmp_path, intent_id="id-1", payload={"choice": "a"})
    # Popula cache.
    assert intent_state._read_intent_log(tmp_path) == {"id-1": {"choice": "a"}}

    intent_state.clear_intent_files(tmp_path, also_log=True)

    # Arquivo apagado E cache invalidado.
    assert intent_state._read_intent_log(tmp_path) == {}


def test_clear_intent_log_only_invalidates_cache(tmp_path: Path) -> None:
    """clear_intent_log_only invalida cache em paralelo ao delete."""
    _seed_log(tmp_path, intent_id="id-1", payload={"choice": "a"})
    assert intent_state._read_intent_log(tmp_path) == {"id-1": {"choice": "a"}}

    intent_state.clear_intent_log_only(tmp_path)

    assert intent_state._read_intent_log(tmp_path) == {}


def test_reset_log_cache_is_idempotent() -> None:
    """`_reset_log_cache` pode ser chamado N× sem erro."""
    intent_state._reset_log_cache()
    intent_state._reset_log_cache()
    intent_state._reset_log_cache()
    # Sem assertion forte — só confirma que não levanta.


def test_read_returns_copy_not_cache_reference(tmp_path: Path) -> None:
    """Mutar o retorno de `_read_intent_log` não corrompe o cache."""
    _seed_log(tmp_path, intent_id="id-1", payload={"choice": "a"})
    first = intent_state._read_intent_log(tmp_path)
    first["mutation"] = {"injected": True}  # type: ignore[assignment]

    second = intent_state._read_intent_log(tmp_path)
    assert "mutation" not in second
