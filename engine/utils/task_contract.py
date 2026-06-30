"""Helpers puros pra ler campos de um Task Contract (TASK-NNNN.yaml).

Centraliza o parsing que antes vivia inline em
:func:`engine.implement._load_task_contract` (Mandamento #3 — reuso antes de
criar). Hoje dois consumidores precisam da mesma leitura de ``allowed_files``:

1. ``engine/implement.py`` — surfa o contrato no Plan Mode.
2. ``engine/qa/ingest.py::snapshot_impl_files`` — snapshota o conteúdo dos
   ``allowed_files`` declarados pro vetor ``impl-vs-spec``.

Módulo puro, sem I/O e sem dep de ``engine.qa.*`` / ``engine.implement`` —
qualquer um dos dois pode importar daqui sem risco circular.
"""

from __future__ import annotations

from typing import Any

__all__ = ["parse_allowed_files"]


def parse_allowed_files(contract: Any) -> list[str]:
    """Extrai ``allowed_files`` de um dict de task contract já carregado.

    Aceita as duas variantes de chave (``allowed_files`` snake-case e
    ``allowed-files`` kebab-case), espelhando o comportamento histórico de
    ``engine.implement._load_task_contract``. Snake-case tem precedência
    quando ambos presentes e o valor snake é truthy (mesma semântica de
    ``raw.get("allowed_files") or raw.get("allowed-files")``).

    Robustez: ``contract`` não-dict, campo ausente, ou valor não-list
    degradam pra lista vazia em vez de raise — o caller não precisa
    blindar contra YAML mal-formado.

    Args:
        contract: dict carregado de um TASK-NNNN.yaml (ou qualquer valor;
            não-dict vira ``[]``).

    Returns:
        Lista de paths declarados como strings (entries são coagidos com
        ``str``, espelhando ``[str(x) for x in allowed]`` do consumidor
        original). Ordem preservada.
    """
    if not isinstance(contract, dict):
        return []
    allowed = contract.get("allowed_files") or contract.get("allowed-files") or []
    if not isinstance(allowed, list):
        return []
    return [str(x) for x in allowed]
