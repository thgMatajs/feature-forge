"""Install do driver AI-first (SKILL.md + AGENTS.md) via forge init.

Cobre: idempotência, brownfield (preserva conteúdo existente), conteúdo
mínimo (legenda de exit + regra de dispatch do conductor).

Refs: docs/superpowers/specs/2026-06-17-ai-first-interaction-layer-design.md §4 C1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import init as forge_init


pytestmark = pytest.mark.integration


def test_install_ai_driver_creates_skill_and_agents(
    tmp_forge_project: Path,
) -> None:
    forge_init._install_ai_driver(tmp_forge_project)
    skill = tmp_forge_project / ".claude" / "skills" / "feature-forge" / "SKILL.md"
    agents = tmp_forge_project / "AGENTS.md"
    assert skill.is_file()
    assert agents.is_file()
    body = skill.read_text(encoding="utf-8")
    # Conteúdo mínimo: legenda de exit + regra de dispatch.
    assert "exit 2" in body
    assert "planning-conductor.md" in body
    assert "argv idêntico" in body


def test_install_ai_driver_idempotent(tmp_forge_project: Path) -> None:
    forge_init._install_ai_driver(tmp_forge_project)
    skill = tmp_forge_project / ".claude" / "skills" / "feature-forge" / "SKILL.md"
    first = skill.read_text(encoding="utf-8")
    forge_init._install_ai_driver(tmp_forge_project)
    assert skill.read_text(encoding="utf-8") == first  # sem duplicar/clobber


def test_install_ai_driver_brownfield_preserves_existing_agents(
    tmp_forge_project: Path,
) -> None:
    agents = tmp_forge_project / "AGENTS.md"
    agents.write_text("# Meu AGENTS.md\nregras do usuário\n", encoding="utf-8")
    forge_init._install_ai_driver(tmp_forge_project)
    body = agents.read_text(encoding="utf-8")
    assert "regras do usuário" in body  # conteúdo do usuário preservado
    assert "feature-forge" in body  # bloco do forge anexado
