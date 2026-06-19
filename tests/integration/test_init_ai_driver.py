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


def test_install_ai_driver_preserves_user_skill_without_marker(
    tmp_forge_project: Path,
) -> None:
    """H-002: skill homônima do usuário SEM o marker não é clobbed.

    A detecção "é a nossa skill" é por marker (`_FORGE_DRIVER_MARKER`), não
    por substring de front-matter. Um SKILL.md do usuário no mesmo path —
    mesmo citando `name: feature-forge` na prosa — é preservado.
    """
    skill = tmp_forge_project / ".claude" / "skills" / "feature-forge" / "SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    user_body = (
        "---\n"
        "name: minha-skill\n"
        "description: compatível com a skill name: feature-forge do usuário\n"
        "---\n\n"
        "# Skill do usuário\nconteúdo que NÃO pode ser clobbed\n"
    )
    skill.write_text(user_body, encoding="utf-8")
    forge_init._install_ai_driver(tmp_forge_project)
    # Preservado byte-a-byte: marker ausente → branch "preserva".
    assert skill.read_text(encoding="utf-8") == user_body


def test_install_ai_driver_overwrites_own_skill_with_marker(
    tmp_forge_project: Path,
) -> None:
    """H-002: skill nossa (com marker) mas STALE é sobrescrita pela canonical.

    Distingue o branch de overwrite do branch de idempotência: o destino
    carrega o marker mas com corpo diferente; após o install, bate com a
    canonical do FORGE_HOME (canonical wins).
    """
    skill = tmp_forge_project / ".claude" / "skills" / "feature-forge" / "SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    stale = forge_init._FORGE_DRIVER_MARKER + "\nconteúdo STALE da nossa skill\n"
    skill.write_text(stale, encoding="utf-8")
    forge_init._install_ai_driver(tmp_forge_project)
    canonical = (
        forge_init.forge_home() / "skills" / "feature-forge" / "SKILL.md"
    ).read_text(encoding="utf-8")
    body = skill.read_text(encoding="utf-8")
    assert body == canonical  # canonical wins
    assert body != stale  # de fato sobrescreveu


def test_install_ai_driver_noop_warns_when_forge_home_missing_artifacts(
    tmp_forge_project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """M-002: FORGE_HOME sem skills/ → no-op + warning observável (não crash).

    Monkeypatch `forge_home` pra um dir vazio: nem SKILL.md nem AGENTS.md são
    criados, o install não levanta, e um aviso mentor-calmo é emitido.
    """
    empty_home = tmp_path / "empty-forge-home"
    empty_home.mkdir()
    monkeypatch.setattr(forge_init, "forge_home", lambda: empty_home)

    forge_init._install_ai_driver(tmp_forge_project)  # não deve crashar

    skill = tmp_forge_project / ".claude" / "skills" / "feature-forge" / "SKILL.md"
    agents = tmp_forge_project / "AGENTS.md"
    assert not skill.exists()  # no-op: nada copiado
    assert not agents.exists()
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "driver AI-first não instalado" in combined  # warning emitido


def test_install_ai_driver_agents_marker_idempotent_over_user_file(
    tmp_forge_project: Path,
) -> None:
    """M-001/L-001: 2ª install sobre AGENTS.md de usuário não duplica o bloco.

    Contrato do marker: presença ⇒ no-op. Conteúdo do usuário preservado e o
    bloco do forge aparece exatamente uma vez após dois installs.
    """
    agents = tmp_forge_project / "AGENTS.md"
    agents.write_text("# Meu AGENTS.md\nregras do usuário\n", encoding="utf-8")
    forge_init._install_ai_driver(tmp_forge_project)  # 1ª: append
    after_first = agents.read_text(encoding="utf-8")
    forge_init._install_ai_driver(tmp_forge_project)  # 2ª: marker presente → no-op
    after_second = agents.read_text(encoding="utf-8")
    assert after_second == after_first  # idempotente, sem re-append
    assert "regras do usuário" in after_second  # conteúdo do usuário intacto
    # Marker (e portanto o bloco do forge) aparece exatamente uma vez.
    assert after_second.count(forge_init._FORGE_DRIVER_MARKER) == 1
