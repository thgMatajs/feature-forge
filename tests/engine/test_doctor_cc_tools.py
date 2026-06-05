"""Tests for the cc-gate-tools doctor category.

Cobre a 13ª categoria do `forge doctor` introduzida pelo Task 11 do
CC gate plan: trust-but-verify das 4 tools nativas usadas por
`validators/check_cyclomatic_complexity.py` (detekt, swiftlint, eslint,
radon). Tools NÃO são instaladas pelo forge — doctor apenas reporta
status + comando de install quando ausentes.

Voz: mentor calmo. Spec ref: docs/superpowers/specs/2026-06-03-cc-gate-design.md §3.
"""

from __future__ import annotations

from pathlib import Path

from engine import doctor


def test_check_cc_gate_tools_returns_category(tmp_path: Path) -> None:
    """Categoria registra as 4 tools com nomes exatos."""
    cat = doctor._check_cc_gate_tools(tmp_path)
    assert cat.title.lower().startswith("cc-gate")
    names = [c.name for c in cat.checks]
    assert "detekt" in names
    assert "swiftlint" in names
    assert "eslint" in names
    assert "radon" in names


def test_cc_gate_tools_marks_missing_with_install_instructions(
    monkeypatch, tmp_path: Path
) -> None:
    """Tool ausente → WARN com hint de install — nunca FAIL."""
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    cat = doctor._check_cc_gate_tools(tmp_path)
    for check in cat.checks:
        assert check.status == doctor._STATUS_WARN
        assert check.remediation  # must include install hint
    install_hints = " ".join(c.remediation for c in cat.checks)
    assert "brew install swiftlint" in install_hints
    # Asserção específica pro tool eslint — antes "npm install" podia bater
    # com hint de qualquer outra tool e o teste passaria mesmo se a hint
    # de eslint estivesse errada (codereviewbot 3353045999).
    assert any(
        "npm install" in c.remediation or "npm i" in c.remediation
        for c in cat.checks
        if c.name == "eslint"
    )
    assert "pip install radon" in install_hints


def test_cc_gate_tools_marks_present_as_ok(monkeypatch, tmp_path: Path) -> None:
    """Tool encontrada no PATH → OK, mensagem inclui o path."""
    monkeypatch.setattr(
        doctor.shutil, "which", lambda name: f"/usr/local/bin/{name}"
    )
    cat = doctor._check_cc_gate_tools(tmp_path)
    for check in cat.checks:
        assert check.status == doctor._STATUS_OK
        assert "/usr/local/bin/" in check.message


def test_full_scope_includes_cc_gate_tools_category() -> None:
    """`run()` chama `_check_cc_gate_tools` no branch `full`."""
    src = Path(doctor.__file__).read_text(encoding="utf-8")
    assert "_check_cc_gate_tools" in src
    # Garante que está registrado dentro do bloco full (não apenas declarado).
    # Aproximação: aparece pelo menos 2 vezes (def + call).
    assert src.count("_check_cc_gate_tools") >= 2
