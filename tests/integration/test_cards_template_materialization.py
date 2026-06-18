"""CARDS-DISCONNECT (W-DEBT) — materialização de templates mergeados per-projeto.

O fluxo default `init`→`plan` ignorava as contribuições de TEMPLATE dos cards:
`plan._templates_dir()` lia só de `FORGE_HOME/templates/` (global, flat), nunca
da merge per-projeto. Só `forge raw rebuild-templates` fazia a ponte (mutando o
FORGE_HOME global compartilhado).

A correção: `init` materializa o resultado de `merge_contributions` num dir
per-projeto (`.claude/forge/templates/`) reusando `render_merged_template` (o
mesmo render que `rebuild-templates` usa); `plan._templates_dir(project_root)`
prefere esse dir quando presente, com fallback pro global.

Marker: integration (cruza init.materialize + cards.merger + plan resolução).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.cards.loader import CardManifest
from engine.cards.merger import merge_contributions
from engine.init import _materialize_merged_templates
from engine.plan import _templates_dir
from engine.utils.paths import forge_dir, forge_home

pytestmark = pytest.mark.integration


def _seed_card_with_template_section(project: Path, *, base_template: str) -> CardManifest:
    """Card local que contribui uma seção `append-section` pra `base_template`.

    O fragmento vive no snapshot do card (`card_source`); `render_merged_template`
    lê o base de FORGE_HOME/templates e aplica o fragmento.
    """
    card_dir = project / ".claude" / "cards" / "demo-card"
    card_dir.mkdir(parents=True, exist_ok=True)
    fragment_rel = "template-contributions/extra.md"
    fragment_path = card_dir / fragment_rel
    fragment_path.parent.mkdir(parents=True, exist_ok=True)
    fragment_path.write_text(
        "Seção contribuída pelo demo-card — marcador único xyz123.\n",
        encoding="utf-8",
    )
    return CardManifest(
        name="demo-card",
        version="1.0.0",
        schema_version=1,
        description="stub para materialization test",
        category="language",
        maturity="experimental",
        provides=[],
        requires=[],
        conflicts_with=[],
        contributes={
            "templates": [
                {
                    "target": base_template,
                    "section": None,
                    "file": fragment_rel,
                    "merge": "append-section",
                }
            ]
        },
        source_path=card_dir,
    )


def _pick_markdown_template() -> str:
    """Escolhe um template .md real do FORGE_HOME pra servir de base de merge."""
    templates_root = forge_home() / "templates"
    for cand in sorted(templates_root.glob("*.template.md")):
        return cand.name
    pytest.skip("nenhum template .md no FORGE_HOME — ambiente incompleto")


def test_materialize_writes_merged_templates_per_project(tmp_forge_project: Path) -> None:
    base_template = _pick_markdown_template()
    card = _seed_card_with_template_section(tmp_forge_project, base_template=base_template)
    merged = merge_contributions([card])

    written = _materialize_merged_templates(tmp_forge_project, merged)

    per_project = forge_dir(tmp_forge_project) / "templates"
    assert per_project.is_dir(), "init deve materializar templates mergeados"
    target = per_project / base_template
    assert target.is_file(), f"{base_template} deve existir no dir per-projeto"
    assert base_template in [p.name for p in written]
    body = target.read_text(encoding="utf-8")
    assert "marcador único xyz123" in body, "a seção contribuída deve estar materializada"


def test_templates_dir_prefers_per_project_when_present(tmp_forge_project: Path) -> None:
    base_template = _pick_markdown_template()
    card = _seed_card_with_template_section(tmp_forge_project, base_template=base_template)
    merged = merge_contributions([card])
    _materialize_merged_templates(tmp_forge_project, merged)

    resolved = _templates_dir(tmp_forge_project)
    assert resolved == forge_dir(tmp_forge_project) / "templates"


def test_templates_dir_falls_back_to_global_when_no_per_project(
    tmp_forge_project: Path,
) -> None:
    """Projeto sem materialização (sem cards-de-template) usa o global — backward-compat."""
    resolved = _templates_dir(tmp_forge_project)
    assert resolved == forge_home() / "templates"


def test_materialize_noop_when_no_template_contributions(tmp_forge_project: Path) -> None:
    """Card sem contribuições de template → nada materializado, sem dir criado."""
    merged = merge_contributions([])
    written = _materialize_merged_templates(tmp_forge_project, merged)
    assert written == []
    assert not (forge_dir(tmp_forge_project) / "templates").exists()
