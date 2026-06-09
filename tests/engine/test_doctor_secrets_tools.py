"""Tests for the secrets-tools doctor category.

Cobre Sub-Task 5C: 14ª categoria do ``forge doctor`` introduzida pelo
check_secrets gate. Trust-but-verify das 2 tools nativas usadas por
``validators/check_secrets.py`` — ``gitleaks`` (per-task hook,
``forge implement``) e ``trufflehog`` (cascade, ``forge verify``).

Tools NÃO são instaladas pelo forge (Decision 22 + spec §3 trust-but-verify).
Doctor apenas reporta status + comando de install quando ausentes.

Voz: mentor calmo. Spec ref: docs/superpowers/specs/2026-06-05-check-secrets-design.md.
"""

from __future__ import annotations

from pathlib import Path

from engine import doctor


def test_check_secrets_tools_reports_both_binaries(tmp_path: Path) -> None:
    """Categoria registra as 2 tools com nomes exatos: gitleaks + trufflehog."""
    cat = doctor._check_secrets_tools(tmp_path)
    assert "secrets" in cat.title.lower()
    names = [c.name for c in cat.checks]
    assert "gitleaks" in names
    assert "trufflehog" in names
    assert len(names) >= 2


def test_check_secrets_tools_warns_when_missing(
    monkeypatch, tmp_path: Path
) -> None:
    """Tool ausente → WARN com hint de install — nunca FAIL.

    Tools missing não derrubam ``forge doctor`` — só sinalizam o gap. Quem
    realmente precisa descobre via secrets-gate em ``forge verify`` ou
    ``forge implement``.
    """
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    cat = doctor._check_secrets_tools(tmp_path)
    for check in cat.checks:
        assert check.status == doctor._STATUS_WARN
        assert check.remediation  # install hint obrigatório
    install_hints = " ".join(c.remediation for c in cat.checks)
    # Asserção específica por tool — evita false positive (codereviewbot
    # 3353045999): se hint de uma estivesse no slot da outra, o teste
    # passaria mesmo com mapping errado.
    gitleaks_hints = [
        c.remediation for c in cat.checks if c.name == "gitleaks"
    ]
    trufflehog_hints = [
        c.remediation for c in cat.checks if c.name == "trufflehog"
    ]
    assert gitleaks_hints and "gitleaks" in gitleaks_hints[0]
    assert trufflehog_hints and "trufflehog" in trufflehog_hints[0]
    assert "brew install" in install_hints


def test_check_secrets_tools_ok_when_found(monkeypatch, tmp_path: Path) -> None:
    """Tool encontrada no PATH → OK, message inclui o path."""
    monkeypatch.setattr(
        doctor.shutil, "which", lambda name: f"/usr/local/bin/{name}"
    )
    cat = doctor._check_secrets_tools(tmp_path)
    for check in cat.checks:
        assert check.status == doctor._STATUS_OK
        assert "/usr/local/bin/" in check.message


def test_full_scope_includes_secrets_tools_category() -> None:
    """`run()` chama `_check_secrets_tools` no branch `full`.

    Source-level check (paralelo do que ``test_doctor_cc_tools`` faz pro
    CC gate): garante que ``_check_secrets_tools`` aparece chamado, não
    apenas declarado, no ``engine/doctor.py``.
    """
    src = Path(doctor.__file__).read_text(encoding="utf-8")
    assert "_check_secrets_tools" in src
    # def + call → ≥ 2 ocorrências
    assert src.count("_check_secrets_tools") >= 2
