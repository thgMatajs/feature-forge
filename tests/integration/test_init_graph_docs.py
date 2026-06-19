"""Graph-first docs escritos por forge init (W-GRAPH Camadas 1+3).

Cobre: forge init escreve .claude/forge/GRAPH-FIRST.md + graph-skill.md com
markers de conteúdo esperados; canonical-wins (re-init sobrescreve edições do
usuário com a versão canônica — docs forge-managed, comportamento deliberado).

Refs: docs/reports/auditoria-consolidada-2026-06-17.md §5/§6 (NO-ONBOARDING P1)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import init as forge_init


pytestmark = pytest.mark.integration


def test_write_graph_docs_creates_both_files(tmp_forge_project: Path) -> None:
    graph_first, graph_skill = forge_init._write_graph_docs(tmp_forge_project)
    assert graph_first == tmp_forge_project / ".claude" / "forge" / "GRAPH-FIRST.md"
    assert graph_skill == tmp_forge_project / ".claude" / "forge" / "graph-skill.md"
    assert graph_first.is_file()
    assert graph_skill.is_file()


def test_graph_first_has_expected_markers(tmp_forge_project: Path) -> None:
    graph_first, _ = forge_init._write_graph_docs(tmp_forge_project)
    body = graph_first.read_text(encoding="utf-8")
    # Regra graph-first + quick-start das 5 queries de orientação.
    assert "graph first" in body.lower()
    assert "forge graph --json" in body
    for query in ("q1", "q2", "q3", "q4", "q8"):
        assert query in body, query


def test_graph_skill_has_task_query_table(tmp_forge_project: Path) -> None:
    _, graph_skill = forge_init._write_graph_docs(tmp_forge_project)
    body = graph_skill.read_text(encoding="utf-8")
    # Tabela tarefa→query→exemplo cobrindo o catálogo + a seção "quando NÃO usar".
    for query in ("q1", "q2", "q3", "q4", "q7", "q8", "q9", "q11", "q12", "q13", "q14"):
        assert query in body, query
    assert "reuse-findings" in body  # alias `r`
    assert "quando NÃO usar" in body.lower() or "quando não usar" in body.lower()
    # Os três casos de "leia o source direto".
    assert "Grep" in body
    assert "Read" in body


def test_write_graph_docs_canonical_wins_over_user_edits(tmp_forge_project: Path) -> None:
    """Re-init sobrescreve edições do usuário com a versão canônica (canonical-wins).

    Estes dois `.md` são instrução-pro-host forge-managed, não conteúdo do
    usuário — o design (init.py:_write_graph_docs docstring) é deliberadamente
    canonical-wins: re-escreve o conteúdo a cada init, sem marker-guard nem
    backup. Este teste PROVA o comportamento destrutivo intencional: escreve
    conteúdo divergente, re-roda, e assere que o canônico sobrescreveu a edição.
    """
    graph_first, graph_skill = forge_init._write_graph_docs(tmp_forge_project)

    # Usuário edita ambos os arquivos com conteúdo divergente do canônico.
    graph_first.write_text("EDIÇÃO DO USUÁRIO — graph first", encoding="utf-8")
    graph_skill.write_text("EDIÇÃO DO USUÁRIO — graph skill", encoding="utf-8")

    # Re-init (2ª escrita) — canonical-wins: a edição é descartada.
    forge_init._write_graph_docs(tmp_forge_project)

    assert graph_first.read_text(encoding="utf-8") == forge_init._GRAPH_FIRST_MD
    assert graph_skill.read_text(encoding="utf-8") == forge_init._GRAPH_SKILL_MD


def test_skill_file_path_matches_hook_reference(tmp_forge_project: Path) -> None:
    """A costura Camada 2 ↔ 3: o path que o hook cita é o que o init escreve.

    O hook (Camada 2) imprime 'referência completa: .claude/forge/graph-skill.md'.
    Este teste garante que esse path é exatamente onde o init grava o arquivo —
    sem essa amarração, o hook apontaria pra um arquivo inexistente.
    """
    _, graph_skill = forge_init._write_graph_docs(tmp_forge_project)
    rel = graph_skill.relative_to(tmp_forge_project)
    assert rel.as_posix() == ".claude/forge/graph-skill.md"
    # O conteúdo escrito é o constant canônico (não um stub divergente).
    assert graph_skill.read_text(encoding="utf-8") == forge_init._GRAPH_SKILL_MD
