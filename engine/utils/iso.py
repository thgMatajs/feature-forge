"""ISO-8601 UTC timestamp helper compartilhado.

Consolida 10 cópias locais de ``_utc_now_iso`` / ``_utc_now_iso_<module>``
em ``engine/{init,plan,implement,verify,reconfigure,evolve,undo,memory_cli,
graph_cli,doctor}.py``. Mandamento #3 (reuso) — finding #21 do master
review do PR #11 (drift-1-intent-protocol).

Formato canônico mantido bit-a-bit: ``%Y-%m-%dT%H:%M:%SZ`` (zulu UTC,
segundos truncados, sem microssegundos). Qualquer checkpoint pre-existente
no disco continua sendo lido sem migração — o formato emitido é o mesmo
que os 10 helpers locais geravam.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    """Timestamp UTC no formato ISO-8601 com sufixo ``Z`` (zulu).

    Espelha o contract dos 10 helpers locais que substitui:

    >>> from engine.utils.iso import utc_now_iso
    >>> ts = utc_now_iso()
    >>> ts.endswith("Z")
    True
    >>> len(ts)
    20

    Segundos truncados (sem microssegundos) preservam a parity com os
    checkpoints gravados antes do consolidação — diffs binários dos
    arquivos ``.claude/state/*.yaml`` continuam idênticos.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
