"""Helpers compartilhados entre submodules de ``engine.qa``.

Centraliza utilities pra evitar duplicacao cross-submodule (Mandamento #3:
"reuso antes de criar"). Sem dep cruzada — qualquer submodule de
``engine.qa.*`` pode importar daqui sem risco circular, desde que este
modulo nao importe nada de ``engine.qa.*``.

Conteudo atual:

- :func:`utc_iso_z` — timestamp ISO 8601 UTC com sufixo ``Z``. Padrao dos
  artefatos qa (``qa-report.json``, ``checkpoint.json``). Substitui as
  duplicacoes inline previas em ``engine/qa/__init__.py`` (helper privado
  ``_utc_iso_z``) e ``engine/qa/checkpoint.py`` (chamada inline em
  ``write_checkpoint``).

Outras duplicacoes do mesmo formato existem em ``engine/{evolve,plan,
undo,verify,init,memory,...}.py`` (11+ call-sites mapeados no review
CONF-004 §M-4). Migracao desses para este helper esta deferida — exige
brainstorm cross-cutting fora do escopo CONF-004. Quando promover pra
``engine/utils/timestamps.py``, mover este modulo inteiro ou re-exportar
daqui pra manter compatibilidade.
"""

from __future__ import annotations

from datetime import datetime, timezone

__all__ = ["utc_iso_z"]


def utc_iso_z() -> str:
    """Timestamp ISO 8601 UTC com sufixo ``Z`` (sem offset numerico).

    Formato: ``YYYY-MM-DDTHH:MM:SSZ``. Exigido por ``qa-report.json``
    (§6.1 do spec ``forge-qa-design``) e por ``checkpoint.json``
    (Decisao 27 + CONF-004). Centralizado aqui pra evitar drift entre
    artefatos do mesmo run.

    Returns:
        String ISO 8601 UTC com sufixo literal ``Z``.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
