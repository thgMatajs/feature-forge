"""Checkpoint I/O compartilhado para os 10 handlers de comando.

Consolida os pares ``_save_<module>_checkpoint`` / ``_load_<module>_checkpoint``
/ ``_clear_<module>_checkpoint`` que viviam duplicados em
``engine/{init,plan,implement,verify,reconfigure,evolve,undo,memory_cli,
graph_cli,doctor}.py``. Mandamento #3 (reuso) — finding #5 do master
review do PR #11 (drift-1-intent-protocol).

Design notes:

- A serialização é **dict-based**, não dataclass-based. Cada handler tem
  campos próprios (``feature-slug``, ``task-id``, ``scope-kind``, etc.)
  e o naming kebab-case YAML não casa 1:1 com snake_case Python. O
  caller monta o dict (mantém a tradução local, onde pertence) e este
  módulo cuida apenas do contrato I/O: ensure_dir + write_yaml atomic +
  load-or-None + idempotent delete.

- Não importamos ``engine.qa.checkpoint`` — Decision 22 (no runtime deps
  entre skills). Esta camada é stdlib + ``engine.utils.yaml_io`` puro,
  zero acoplamento com a infra de QA gates.

- O schema-version do payload é responsabilidade do caller (cada handler
  declara seu próprio schema). O helper apenas persiste o dict como
  recebeu.

Exemplos canônicos de uso (espelhando os call sites legados):

.. code-block:: python

    from engine.utils.checkpoint_io import (
        save_yaml_checkpoint,
        load_yaml_checkpoint,
        clear_checkpoint,
    )

    # Save:
    save_yaml_checkpoint(
        path,
        {
            "schema-version": 1,
            "step": cp.step,
            "at": cp.at,
            "project-root": cp.project_root,
            "intent-id": cp.intent_id,
            # ... campos específicos do handler ...
        },
    )

    # Load (None quando ausente):
    data = load_yaml_checkpoint(path)

    # Clear (idempotent, silencia OSError):
    clear_checkpoint(path)

Refs:
- docs/superpowers/specs/drift-1-intent-protocol.md §3, §5
- engine/init.py:100-160 (template canônico que motivou o refactor)
- master review PR #11, finding #5 (Mandamento #3 violation)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from engine.utils.paths import ensure_dir
from engine.utils.yaml_io import read_yaml_or_default, write_yaml


def save_yaml_checkpoint(path: Path, payload: Mapping[str, Any]) -> None:
    """Persist ``payload`` em ``path`` atomicamente.

    Garante que ``path.parent`` existe (``ensure_dir``) e delega a
    escrita atômica para ``yaml_io.write_yaml`` (tempfile + ``os.replace``,
    POSIX-safe). O caller é responsável pelo shape do dict — o helper
    não injeta nem valida campos.
    """
    ensure_dir(path.parent)
    write_yaml(path, dict(payload), atomic=True)


def load_yaml_checkpoint(path: Path) -> dict[str, Any] | None:
    """Read the checkpoint at ``path``, returning ``None`` quando ausente.

    Retorna ``None`` em três casos: (a) arquivo não existe; (b) arquivo
    existe mas YAML vazio/inválido (``read_yaml_or_default`` retorna o
    default); (c) conteúdo não é um dict (segurança defensiva contra
    arquivos corrompidos). Em todos os casos o caller trata como
    "nenhum checkpoint disponível" — semântica idêntica aos 10 helpers
    legados.
    """
    if not path.exists():
        return None
    data = read_yaml_or_default(path, None)
    return data if isinstance(data, dict) else None


def clear_checkpoint(path: Path) -> None:
    """Delete ``path`` se existir; silencia ``OSError`` (idempotente).

    Best-effort delete: se o arquivo não existe, no-op; se existe mas o
    unlink falha (race com outro processo, filesystem read-only), engole
    ``OSError`` em silêncio. Os 10 callers legados todos seguiam esse
    contract — preservamos bit-a-bit.
    """
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass
