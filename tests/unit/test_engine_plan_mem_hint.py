"""W-ROUTE 6c Task 1 — prova que o hint de mem chega ao artefato renderizado.

D1 exige consumidor real: não basta o token estar em intake_tokens; o
_render_template faz re.sub e descarta tokens sem placeholder no template. Estes
testes renderizam o template de Wave A passando o hint via extra_tokens e assertam
que o texto renderizado contém o hint (ou fica em branco no degrade — sem o token
cru vazando).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from engine import plan


def _render_intake(
    tmp_project_root: Path, template_name: str, extra_tokens: dict[str, str]
) -> str:
    """Renderiza um template de intake e devolve o texto resultante."""
    target = tmp_project_root / "feature-intake.md"
    plan._render_template(
        template_name,
        target,
        "minha-feature",
        tmp_project_root,
        extra_tokens=extra_tokens,
    )
    return target.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "template_name",
    [
        "feature-intake.template.md",
        "feature-intake-bugfix.template.md",
        "feature-intake-refactor.template.md",
    ],
)
def test_mem_hint_reaches_rendered_artifact(template_name, tmp_project_root):
    """O placeholder {{mem_context_hint}} existe no template e recebe o hint.

    Prova que o token NÃO é descartado pelo re.sub — chega ao artefato que o
    subagente lê.
    """
    hint = "Memória relevante (mem find):\n  · [feedback] use-stateflow"
    # extra_tokens deve cobrir os tokens de source obrigatórios pra não deixar
    # placeholders crus de source (irrelevante pro assert do hint, mas evita ruído).
    rendered = _render_intake(
        tmp_project_root,
        template_name,
        {"{{mem_context_hint}}": hint},
    )
    assert "use-stateflow" in rendered, (
        f"hint não chegou ao artefato renderizado de {template_name}; "
        "o placeholder {{mem_context_hint}} provavelmente está ausente no template."
    )
    # E o token cru NÃO deve sobreviver (foi substituído).
    assert "{{mem_context_hint}}" not in rendered


@pytest.mark.parametrize(
    "template_name",
    [
        "feature-intake.template.md",
        "feature-intake-bugfix.template.md",
        "feature-intake-refactor.template.md",
    ],
)
def test_mem_hint_blank_when_degraded(template_name, tmp_project_root):
    """Degrade (hint vazio): token vira string vazia, sem token cru no artefato."""
    rendered = _render_intake(
        tmp_project_root,
        template_name,
        {"{{mem_context_hint}}": ""},
    )
    # Sem o token cru vazando — substituído por vazio.
    assert "{{mem_context_hint}}" not in rendered
