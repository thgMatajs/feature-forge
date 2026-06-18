"""CARDS-DISCONNECT (W-DEBT) — materialização de templates mergeados per-projeto.

O fluxo default `init`→`plan` ignorava as contribuições de TEMPLATE dos cards:
`plan._templates_dir()` lia só de `FORGE_HOME/templates/` (global, flat), nunca
da merge per-projeto. Só `forge raw rebuild-templates` fazia a ponte (mutando o
FORGE_HOME global compartilhado).

A correção: `init` materializa o resultado de `merge_contributions` num dir
per-projeto (`.claude/forge/templates/`) reusando `render_merged_template` (o
mesmo render que `rebuild-templates` usa); `plan._resolve_template(project_root,
template_name)` prefere esse dir per-FILE quando o arquivo existe lá, com
fallback per-FILE pro global.

Convenção canônica (docs/schemas/card.md + cards/*/card.yaml): o campo `target`
do card carrega o nome de OUTPUT do documento (`tech-spec.md`), NÃO o nome do
template-fonte (`tech-spec.template.md`). A materialização mapeia output→fonte
via `_source_template_name` e escreve o materializado sob o nome do FONTE —
porque `plan._render_template` resolve por `template_name`. Estes testes usam o
formato de target REAL (output-name), não o template-name, pra não mascarar o
mismatch que o CR-01 (holistic review W-DEBT) flagou.

Marker: integration (cruza init.materialize + cards.merger + plan resolução).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.cards.loader import CardManifest
from engine.cards.merger import merge_contributions
from engine.init import _materialize_merged_templates, _source_template_name
from engine.plan import _resolve_template, _templates_dir
from engine.utils.paths import forge_dir, forge_home

pytestmark = pytest.mark.integration


def _seed_card_with_template_section(
    project: Path, *, target_output: str
) -> CardManifest:
    """Card local que contribui uma seção `append-section` pra `target_output`.

    `target_output` é o nome de OUTPUT (formato REAL dos cards de produção, ex.
    `tech-spec.md`) — NÃO o nome do template-fonte. O fragmento vive no snapshot
    do card (`card_source`); `render_merged_template` lê o base-fonte de
    FORGE_HOME/templates e aplica o fragmento.
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
                    "target": target_output,
                    "section": None,
                    "file": fragment_rel,
                    "merge": "append-section",
                }
            ]
        },
        source_path=card_dir,
    )


# ── target→fonte mapping — convenção canônica ────────────────────────────────


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("tech-spec.md", "tech-spec.template.md"),
        ("task-contract.yaml", "task-contract.template.yaml"),
        ("data-contract-spec.yaml", "data-contract-spec.template.yaml"),
        # Defensivo: target já no formato de template não duplica o sufixo.
        ("tech-spec.template.md", "tech-spec.template.md"),
        # Sem extensão — devolve cru (será pulado se base ausente).
        ("README", "README"),
    ],
)
def test_source_template_name_maps_output_to_source(target: str, expected: str) -> None:
    assert _source_template_name(target) == expected


# ── materialização com target REAL (output-name) ─────────────────────────────


def test_materialize_writes_merged_templates_from_real_target(
    tmp_forge_project: Path,
) -> None:
    """Card declara `target: tech-spec.md` (formato REAL). A materialização DEVE
    resolver o fonte `tech-spec.template.md`, criar o dir per-projeto e escrever
    o materializado sob o nome do FONTE (que `plan` procura).

    Este é o teste que o CR-01 pediu: com o target no formato que os cards de
    produção usam (output-name), a materialização precisa funcionar de verdade —
    não cair no branch "ausente em FORGE_HOME" como o código pré-fix fazia.
    """
    card = _seed_card_with_template_section(
        tmp_forge_project, target_output="tech-spec.md"
    )
    merged = merge_contributions([card])

    written = _materialize_merged_templates(tmp_forge_project, merged)

    per_project = forge_dir(tmp_forge_project) / "templates"
    assert per_project.is_dir(), "init deve materializar templates mergeados"
    # Materializado sob o nome do FONTE (template-name), não o de output.
    source_name = "tech-spec.template.md"
    target_file = per_project / source_name
    assert target_file.is_file(), (
        f"{source_name} deve existir no dir per-projeto (materialização != [])"
    )
    assert written != [], "a materialização não pode ser inerte contra cards reais"
    assert source_name in [p.name for p in written]
    body = target_file.read_text(encoding="utf-8")
    assert "marcador único xyz123" in body, "a seção contribuída deve estar materializada"


def test_plan_resolves_materialized_template_for_real_card(
    tmp_forge_project: Path,
) -> None:
    """End-to-end do CR-01: após materialização (card real → output-name),
    `plan._resolve_template` resolve o template-fonte materializado per-projeto,
    e o corpo carrega a seção contribuída. Prova que `init`→`plan` enxerga a
    contribuição do card (a dívida que T2 deveria fechar).
    """
    card = _seed_card_with_template_section(
        tmp_forge_project, target_output="tech-spec.md"
    )
    merged = merge_contributions([card])
    _materialize_merged_templates(tmp_forge_project, merged)

    source_name = "tech-spec.template.md"
    resolved = _resolve_template(tmp_forge_project, source_name)
    assert resolved == forge_dir(tmp_forge_project) / "templates" / source_name
    assert "marcador único xyz123" in resolved.read_text(encoding="utf-8")


# ── per-FILE fallback — materialização parcial não quebra não-contribuídos ────


def test_resolve_template_falls_back_per_file_for_non_contributed(
    tmp_forge_project: Path,
) -> None:
    """Latência do CR-01: materialização PARCIAL (só `tech-spec` contribuído).
    Um template SEM contribuição (ex.: `feature-prd.template.md`) NÃO existe no
    dir per-projeto — `_resolve_template` deve cair per-FILE pro global em vez de
    quebrar com FileNotFoundError (que o per-DIR antigo causaria).
    """
    card = _seed_card_with_template_section(
        tmp_forge_project, target_output="tech-spec.md"
    )
    merged = merge_contributions([card])
    _materialize_merged_templates(tmp_forge_project, merged)

    per_project = forge_dir(tmp_forge_project) / "templates"
    assert per_project.is_dir()

    # Contribuído → per-projeto.
    contributed = _resolve_template(tmp_forge_project, "tech-spec.template.md")
    assert contributed == per_project / "tech-spec.template.md"
    assert contributed.is_file()

    # NÃO contribuído → fallback per-FILE pro global (não FileNotFoundError).
    not_contributed = "feature-prd.template.md"
    resolved = _resolve_template(tmp_forge_project, not_contributed)
    assert resolved == forge_home() / "templates" / not_contributed
    assert resolved.is_file(), "fallback per-FILE deve resolver pro template global"


def test_templates_dir_prefers_per_project_when_present(tmp_forge_project: Path) -> None:
    card = _seed_card_with_template_section(
        tmp_forge_project, target_output="tech-spec.md"
    )
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
