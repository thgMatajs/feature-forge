"""BUG-QA-4 (T7): o mapa de verbos do SKILL.md instalado cobre todos os
verbos dirigíveis IA-first.

Regressão: a tabela "Workflow — mapa de verbos" só listava
init/plan/implement/verify/status — um host genérico não dirigia
qa/evolve/memory/reconfigure/upgrade/undo/graph/doctor pelos artefatos.

Cross-check contra ``engine.cli._VISIBLE_ORDER`` pra a lista não driftar.
"""

from __future__ import annotations

from pathlib import Path

from engine.cli import _VISIBLE_ORDER

_SKILL_MD = Path(__file__).resolve().parents[2] / "skills" / "feature-forge" / "SKILL.md"


def test_skill_md_covers_all_user_verbs() -> None:
    text = _SKILL_MD.read_text(encoding="utf-8")
    missing = [verb for verb in _VISIBLE_ORDER if f"forge {verb}" not in text]
    assert not missing, (
        f"SKILL.md não cobre verbos dirigíveis: {missing} "
        f"(esperado todos de _VISIBLE_ORDER={list(_VISIBLE_ORDER)})"
    )


def test_skill_md_does_not_invent_verbs() -> None:
    """Não documenta verbos que não existem no registry (anti-drift)."""
    text = _SKILL_MD.read_text(encoding="utf-8")
    # Heurística: cada linha de tabela `| `forge <verbo>` ...` referencia um
    # verbo real. Extrai os tokens após "forge " em backticks de tabela.
    import re

    verbs_in_table = set()
    for m in re.finditer(r"\|\s*`forge\s+([a-z-]+)", text):
        verbs_in_table.add(m.group(1))
    unknown = verbs_in_table - set(_VISIBLE_ORDER)
    assert not unknown, f"SKILL.md inventa verbos inexistentes: {unknown}"
