"""Canonical backend axes (DET-6 multi-axis backend model).

PR #13 review #3405254057. Antes existiam duas tuplas duplicadas:

  · ``engine.init._BACKEND_AXES``
  · ``engine.reconfigure._BACKEND_AXES_RECONFIGURE``

Ambas com os mesmos 8 axes na mesma ordem. O comentário em
reconfigure documentava a duplicação como "deliberate pra evitar
ciclo de import init↔reconfigure". O ciclo nunca existiu (init não
importa de reconfigure nem vice-versa em runtime); a duplicação era
defensiva por hábito.

Esta extração consolida o set num módulo neutro (sem deps em
init/reconfigure), eliminando a fonte dupla. ``BACKEND_AXES`` (sem
underscore) é o nome canônico — agora é shared, não module-private.

Ordem: reflete o roteiro de prompt em init.W7.2 (greenfield bundle
picker — data primeiro porque é o que mais difere entre stacks).
Stable iteration order é load-bearing — vira a ordem dos prompts
per-axis e a ordem do ask_multi em opt override.

Fonte canônica do conceito: SPEC det-6-multi-axis-backend.md
§"Eixos canônicos" + docs/schemas/backend-axes.md §"Os 8 axes
canônicos".
"""

from __future__ import annotations

# Frozen tuple — 8 axes canônicos. Ordem é parte do contrato (init
# greenfield picker + reconfigure backend submenu dependem dela).
BACKEND_AXES: tuple[str, ...] = (
    "data",
    "auth",
    "observability",
    "analytics",
    "storage",
    "persistence",
    "notifications",
    "flags",
)
