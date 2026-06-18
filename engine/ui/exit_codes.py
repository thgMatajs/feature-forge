"""
Códigos de saída canônicos do CLI forge.

Fonte única de verdade — referenciado por ``engine.cli`` e pelos host
adapters (``engine.host.adapters``) pra evitar drift entre constantes
duplicadas (#27 do master-review do PR #11). O antigo
``engine.ui.tty_bridge`` consumia daqui também; foi removido na Wave 2
(clean break, superseded pelo TtyAdapter in-process).

NUNCA importe ``engine.cli`` aqui — esse módulo deve ficar no fundo
do grafo de imports da engine pra quebrar o ciclo (um consumidor de
``engine.cli`` poderia, transitivamente, puxar de volta pra
``engine.cli`` se este módulo dependesse de algo).

Convenção (SPEC §8 do drift-1-intent-protocol):

    0    sucesso
    1    erro fatal (mensagem mentor-calmo no stderr)
    2    pausado aguardando input (drift-1 protocol)
    130  usuário cancelou (convenção POSIX SIGINT)
"""
from __future__ import annotations

import sys
from typing import TextIO

EXIT_OK: int = 0
EXIT_ERROR: int = 1
EXIT_PAUSED: int = 2
EXIT_CANCELLED: int = 130

# ── C3 EXIT-2-COLLISION — tags machine-readable ───────────────────────────────
#
# A escada legada (exit 3/4/5/6/7/8 + not-a-project=2) colapsou em EXIT_ERROR
# (1) + uma tag estável em stderr no formato ``[FORGE-ERR:<TAG>]``. O host/
# driver parseia a tag pra ramificar comportamento sem depender de um código
# numérico ambíguo. Exit 2 ficou reservado SÓ pra pausa (PausedForInputError +
# UserPausedError). Exit 127 (editor-not-found) permanece como exceção POSIX
# documentada em ``forge raw edit-config``.
ERR_PROJECT_NOT_FOUND: str = "PROJECT-NOT-FOUND"
ERR_LOCKED: str = "LOCKED"
ERR_FEATURE_MISSING: str = "FEATURE-MISSING"
ERR_NOT_READY: str = "NOT-READY"
ERR_WAVE_INCOMPLETE: str = "WAVE-INCOMPLETE"
ERR_BLOCKED_EXTERNAL: str = "BLOCKED-EXTERNAL"
ERR_QA_BLOCK: str = "QA-BLOCK"
ERR_UPGRADE_FAILED: str = "UPGRADE-FAILED"
ERR_USAGE: str = "USAGE"
ERR_ABORTED: str = "ABORTED"
ERR_INIT_FAILED: str = "INIT-FAILED"


def fail_with_tag(
    tag: str,
    message: str | None = None,
    *,
    stream: TextIO | None = None,
) -> int:
    """Emite ``[FORGE-ERR:<tag>]`` (+ ``message``) em stderr e retorna 1.

    Fonte única do contrato C3: todo exit-site de ERRO dos handlers chama este
    helper em vez de ``return <N>``. Quando o site já escreveu sua própria prosa
    mentor-calmo (ex.: a mensagem 3-caminhos de phase-lock), passe
    ``message=None`` — o helper emite só a tag, sem duplicar a prosa.

    A tag é estável e machine-readable; o host/driver ramifica por ela.
    """
    out = stream if stream is not None else sys.stderr
    if message:
        out.write(f"[FORGE-ERR:{tag}] {message}\n")
    else:
        out.write(f"[FORGE-ERR:{tag}]\n")
    return EXIT_ERROR


__all__ = [
    "EXIT_OK", "EXIT_ERROR", "EXIT_PAUSED", "EXIT_CANCELLED",
    "ERR_PROJECT_NOT_FOUND", "ERR_LOCKED", "ERR_FEATURE_MISSING",
    "ERR_NOT_READY", "ERR_WAVE_INCOMPLETE", "ERR_BLOCKED_EXTERNAL",
    "ERR_QA_BLOCK", "ERR_UPGRADE_FAILED", "ERR_USAGE", "ERR_ABORTED",
    "ERR_INIT_FAILED", "fail_with_tag",
]
