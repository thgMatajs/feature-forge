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
  - Se score >= threshold (inequality não-estrita — score == threshold
    qualifica):
      Pra cada platform em card.platforms:
        Acumula candidato em (card.axis, platform)

Pra cada (axis, platform):
  - 0 candidatos acima do threshold: result = None
  - 1 candidato:                     result = Cell(...)
  - 2+ candidatos:                   result = Conflict(candidates=(Cell, Cell, ...))
                                     (Conflict.candidates ordenado por card_id)
```

## Reuso

Importa `_eval_detection_signals` de `engine.detection._eval`. Não
reimplementa lógica de gradle-dep, file-content, file-exists,
directory-exists.

Antes do PR #13 review (Phase B), este módulo importava de
``engine.init`` — ciclo fechado por lazy imports. O ciclo foi quebrado
movendo ``_eval_detection_signals`` (e helpers) pra ``_eval.py``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.detection._eval import _eval_detection_signals

logger = logging.getLogger(__name__)

# Threshold default — escolhido como meta-fração dos thresholds declarados
# em cards reais do projeto (range observado 0.5–0.6, ex.:
# `cards/ktor-client/card.yaml` declara 0.5 e `cards/retrofit-client/card.yaml`
# declara 0.6). 0.3 cobre signals fracos isolados (label-only ou import-only)
# sem aceitar ruído puro, mantendo-se abaixo do range observado pra evitar
# false-negative em cards-light que não declaram threshold próprio.
#
# Schema do campo: `docs/schemas/card.md` (CARD-016). Range esperado:
# `[0.0, 1.0]` — validado em `_card_threshold` (ValueError fora do range).
#
# Per-card override: se `card.detection.threshold` está presente, prevalece
# sobre DEFAULT_THRESHOLD.
DEFAULT_THRESHOLD = 0.3


@dataclass(frozen=True)
class Cell:
    """Cell ativa: 1 card matched signals acima do threshold."""

    card_id: str
    score: float
    matched_signals: tuple[str, ...]


@dataclass(frozen=True)
class Conflict:
    """Cell em conflito: 2+ cards matched signals acima do threshold.

    `candidates` é ordenado alfabeticamente por `card_id` pra garantir
    output determinístico independente da ordem de `active_cards` no input
    — consumers downstream (W7 AskUserQuestion render do auditor humano)
    podem confiar em ordem estável entre runs.
    """

    candidates: tuple[Cell, ...]


ComposerCell = Cell | Conflict | None


def _card_threshold(card: dict[str, Any], *, default: float) -> float:
    """Threshold per-card: usa `card.detection.threshold` se presente.

    Raises:
        ValueError: se o threshold declarado no card está fora do range
            `[0.0, 1.0]`. Mantém o gating defensivo contra card.yaml
            mal-formado — preferimos falhar alto a mascarar um bug
            silenciando todo signal (threshold < 0) ou excluindo todo
            card (threshold > 1).
    """
    detection = card.get("detection") or {}
    th = detection.get("threshold")
    if isinstance(th, (int, float)):
        th_f = float(th)
        if th_f < 0.0 or th_f > 1.0:
            card_id = card.get("card_id", "<unknown>")
            raise ValueError(
                f"Card {card_id} threshold {th_f} outside [0.0, 1.0]"
            )
        return th_f
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
        Dict aninhado `{axis: {platform: result}}` onde `result` é:

        - `None` — 0 cards bateram signals acima do threshold;
        - `Cell(...)` — exatamente 1 card matched;
        - `Conflict(candidates=(Cell, ...))` — 2+ cards matched.
          `candidates` vem ordenado por `card_id` (alfabético) pra
          garantir determinismo entre runs.

    Eixos / platforms presentes no resultado são exatamente os declarados
    em `active_cards` — composer não inventa cells vazias pra combinações
    não-declaradas. Se um card declara platform mas signals não casam,
    a (axis, platform) result aparece como `None` (registra a tentativa).

    Cards com `axis` ou `card_id` vazios/ausentes são silenciosamente
    descartados, com um warning emitido via `logging.warning` por card
    descartado (motivo textual no log) — observabilidade pro auditor
    humano em W7 sem quebrar a API atual.

    Raises:
        ValueError: se algum card declara `detection.threshold` fora do
            range `[0.0, 1.0]`. Ver `_card_threshold`.
    """
    # Coleta primeiro todos os pares (axis, platform) declarados —
    # garante que cells "no match" apareçam como None em vez de ausentes.
    declared: dict[str, set[str]] = {}
    for card in active_cards:
        axis = card.get("axis")
        platforms = card.get("platforms") or []
        if not isinstance(axis, str) or not axis:
            logger.warning(
                "composer: card skipped — missing/empty 'axis' field "
                "(card_id=%r)",
                card.get("card_id"),
            )
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
            # Already warned above in the declared-pass; suppress duplicate.
            continue
        if not isinstance(card_id, str) or not card_id:
            logger.warning(
                "composer: card skipped — missing/empty 'card_id' field "
                "(axis=%r)",
                axis,
            )
            continue

        # Shape guard (PR #13 review #3405256439): se `detection.signals`
        # não é list, _eval_detection_signals silenciosamente retorna
        # score=0 mas o card aparece "ativo" no card_index — quebra o
        # contract pro auditor humano. Skip explícito + warning emite
        # observabilidade sem mascarar o card mal-formado.
        if not isinstance(detection.get("signals"), list):
            logger.warning(
                "composer: card skipped — detection.signals not a list "
                "(card_id=%r, got=%s)",
                card_id,
                type(detection.get("signals")).__name__,
            )
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
                # Ordena por card_id pra garantir determinismo entre runs
                # (HIGH-002 do review W5): consumers downstream renderizam
                # os candidatos em alguma ordem, e essa ordem não pode
                # depender de iteration order do dict de cards.
                matches_sorted = sorted(matches, key=lambda c: c.card_id)
                axis_map[pf] = Conflict(candidates=tuple(matches_sorted))
        result[axis] = axis_map

    return result
