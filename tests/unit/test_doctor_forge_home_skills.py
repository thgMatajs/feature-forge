"""Tests for the forge-home-driver doctor category (FORGE_HOME-carries-skills).

Follow-up Wave 1 (DRIVER-001): após o clone parcial/sparse de FORGE_HOME deixar
o driver dormente, o `forge doctor` ganha uma categoria que assere que
FORGE_HOME carrega `skills/feature-forge/SKILL.md` — o ponto de entrada que o
host (Claude Code / opencode) lê pra dirigir o lifecycle. Espelha a categoria
de `hooks/` (presença de arquivo esperado no FORGE_HOME).

Voz: mentor calmo. Spec ref: docs/superpowers/specs/2026-06-18-w-debt.md §2.3.
"""

from __future__ import annotations

from pathlib import Path

from engine import doctor


def _seed_skill(home: Path) -> Path:
    skill = home / "skills" / "feature-forge" / "SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text("# feature-forge driver\n", encoding="utf-8")
    return skill


def test_forge_home_driver_ok_when_skill_present(monkeypatch, tmp_path: Path) -> None:
    """SKILL.md presente em FORGE_HOME/skills/feature-forge → OK."""
    _seed_skill(tmp_path)
    monkeypatch.setattr(doctor, "forge_home", lambda: tmp_path)
    cat = doctor._check_forge_home_driver(tmp_path)
    assert cat.worst == doctor._STATUS_OK
    assert any(c.status == doctor._STATUS_OK for c in cat.checks)


def test_forge_home_driver_fails_when_skill_missing(monkeypatch, tmp_path: Path) -> None:
    """SKILL.md ausente em FORGE_HOME → FAIL com hint de driver dormente."""
    monkeypatch.setattr(doctor, "forge_home", lambda: tmp_path)
    cat = doctor._check_forge_home_driver(tmp_path)
    assert cat.worst == doctor._STATUS_FAIL
    failing = [c for c in cat.checks if c.status == doctor._STATUS_FAIL]
    assert failing, "ausência do SKILL.md deve ser FAIL"
    hint = " ".join(c.remediation for c in cat.checks)
    assert "FORGE_HOME" in hint or "skills" in hint


def test_full_scope_includes_forge_home_driver_category() -> None:
    """`run()` chama `_check_forge_home_driver` no branch `full`."""
    src = Path(doctor.__file__).read_text(encoding="utf-8")
    assert src.count("_check_forge_home_driver") >= 2  # def + call no full
