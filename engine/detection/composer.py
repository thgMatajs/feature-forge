"""Detection composer — agrega signals de múltiplos cards em cells por
(axis, platform).

W5.1 do plano DET-6. Cobre AC-5 do SPEC det-6-multi-axis-backend.

## Contrato

```
compose_backend_axes(project_root, active_cards) -> dict[axis][platform] -> Cell | Conflict | None
```

Cada `active_card` é um dict normalizado com:
  - `card_id`:  str          — identificador do card (= identity.name no card.yaml)
  - `axis`:     str          — eixo (= identity.category no card.yaml)
  - `platforms`: list[str]   — plataformas onde o card aplica
  - `detection`: dict        — bloco `detection` do card.yaml (com `signals`)

**Platforms source (Open Detail #8 do SPEC):** card.yaml hoje não tem campo
explícito `identity.platforms` — quem invoca `compose_backend_axes` é
responsável por derivar / preencher esse campo (W5.2+ ou W7 vai fechar essa
ponta). W5.1 fica neutro: aceita o que o caller passar.

## Algoritmo (per SPEC §"Detection composer")

```
Pra cada card em active_cards:
  - score, matched = _eval_detection_signals(project_root, card.detection)
  - Se score >= threshold:
      Pra cada platform em card.platforms:
        Acumula candidato em (card.axis, platform)

Pra cada (axis, platform):
  - 0 candidatos acima do threshold: cell = None
  - 1 candidato:                     cell = Cell(...)
  - 2+ candidatos:                   cell = Conflict([Cell, ...])
```

## Reuso

Importa `_eval_detection_signals` de `engine.init`. Não reimplementa
lógica de gradle-dep, file-content, file-exists, directory-exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Union

from engine.init import _eval_detection_signals

# Threshold default — alinhado a card.yaml defaults observados (0.5-0.6 range
# em ktor-client / retrofit-client). 0.3 cobre signals fracos isolados (label
# ou import-only) sem aceitar ruído puro.
#
# Per-card override: se `card.detection.threshold` está presente, prevalece
# sobre DEFAULT_THRESHOLD. Schema card.md (CARD-016) já permite esse campo.
DEFAULT_THRESHOLD = 0.3


@dataclass(frozen=True)
class Cell:
    """Cell ativa: 1 card matched signals acima do threshold."""

    card_id: str
    score: float
    matched_signals: tuple[str, ...]


@dataclass(frozen=True)
class Conflict:
    """Cell em conflito: 2+ cards matched signals acima do threshold."""

    candidates: tuple[Cell, ...]


ComposerCell = Optional[Union[Cell, Conflict]]


def _card_threshold(card: dict[str, Any], *, default: float) -> float:
    """Threshold per-card: usa `card.detection.threshold` se presente."""
    detection = card.get("detection") or {}
    th = detection.get("threshold")
    if isinstance(th, (int, float)):
        return float(th)
    return default


def compose_backend_axes(
    project_root: Path,
    active_cards: list[dict[str, Any]],
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict[str, dict[str, ComposerCell]]:
    """Produz `Map[axis][platform] → Cell | Conflict | None`.

    Args:
        project_root: raiz do projeto sob análise (passada pra signals).
        active_cards: lista de card specs normalizados — ver módulo docstring.
        threshold: fallback global quando card não declara
            `detection.threshold`.

    Returns:
        Dict aninhado `{axis: {platform: cell}}`. Cells com 0 matches viram
        `None`. Cells com 1 candidato viram `Cell`. Cells com 2+ candidatos
        viram `Conflict` agregando os candidatos.

    Eixos / platforms presentes no resultado são exatamente os declarados
    em `active_cards` — composer não inventa cells vazias pra combinações
    não-declaradas. Se um card declara platform mas signals não casam,
    a (axis, platform) cell aparece como `None` (registra a tentativa).
    """
    # Coleta primeiro todos os pares (axis, platform) declarados —
    # garante que cells "no match" apareçam como None em vez de ausentes.
    declared: dict[str, set[str]] = {}
    for card in active_cards:
        axis = card.get("axis")
        platforms = card.get("platforms") or []
        if not isinstance(axis, str) or not axis:
            continue
        bucket = declared.setdefault(axis, set())
        for pf in platforms:
            if isinstance(pf, str) and pf:
                bucket.add(pf)

    # Acumula candidatos por (axis, platform).
    candidates: dict[tuple[str, str], list[Cell]] = {}
    for card in active_cards:
        axis = card.get("axis")
        platforms = card.get("platforms") or []
        detection = card.get("detection") or {}
        card_id = card.get("card_id")
        if not isinstance(axis, str) or not axis:
            continue
        if not isinstance(card_id, str) or not card_id:
            continue

        score, matched = _eval_detection_signals(project_root, detection)
        card_th = _card_threshold(card, default=threshold)
        if score < card_th:
            continue

        cell = Cell(
            card_id=card_id,
            score=score,
            matched_signals=tuple(matched),
        )
        for pf in platforms:
            if not isinstance(pf, str) or not pf:
                continue
            key = (axis, pf)
            candidates.setdefault(key, []).append(cell)

    # Constrói resultado preservando declared structure.
    result: dict[str, dict[str, ComposerCell]] = {}
    for axis, platforms in declared.items():
        axis_map: dict[str, ComposerCell] = {}
        for pf in platforms:
            matches = candidates.get((axis, pf), [])
            if not matches:
                axis_map[pf] = None
            elif len(matches) == 1:
                axis_map[pf] = matches[0]
            else:
                axis_map[pf] = Conflict(candidates=tuple(matches))
        result[axis] = axis_map

    return result
