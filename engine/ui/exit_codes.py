"""
Códigos de saída canônicos do CLI forge.

Fonte única de verdade — referenciado por ``engine.cli`` e
``engine.ui.tty_bridge`` pra evitar drift entre constantes
duplicadas (#27 do master-review do PR #11).

NUNCA importe ``engine.cli`` aqui — esse módulo deve ficar no fundo
do grafo de imports da engine pra quebrar o ciclo
(``engine.cli`` → ``engine.ui.tty_bridge`` poderia, transitivamente,
puxar de volta pra ``engine.cli`` se este módulo dependesse de algo).

Convenção (SPEC §8 do drift-1-intent-protocol):

    0    sucesso
    1    erro fatal (mensagem mentor-calmo no stderr)
    2    pausado aguardando input (drift-1 protocol)
    130  usuário cancelou (convenção POSIX SIGINT)
"""
from __future__ import annotations

EXIT_OK: int = 0
EXIT_ERROR: int = 1
EXIT_PAUSED: int = 2
EXIT_CANCELLED: int = 130

__all__ = ["EXIT_OK", "EXIT_ERROR", "EXIT_PAUSED", "EXIT_CANCELLED"]
