"""Testes do wiring de `impl-vs-spec` em _CORE_AUDITORS + Phase 0 (Task A3).

C-001: o vetor `impl-vs-spec` é um 5º vetor core. Precisa estar consistente em
TODOS os sítios do contrato qa pra o gate NÃO rejeitar o output do próprio
vetor: _CORE_AUDITORS (wiring), validate_qa_finding/_qa_report (enum), o seed
de synthesis (by_vector), e o handoff.
"""

from __future__ import annotations

from engine.qa import _CORE_AUDITORS


def test_impl_vs_spec_in_core_auditors():
    assert "impl-vs-spec" in _CORE_AUDITORS


def test_impl_vs_spec_flows_into_handoff_auditors():
    # Espelha o construct de _write_conductor_handoff:
    # auditors = [a for a in _CORE_AUDITORS if a not in disabled]
    disabled: tuple[str, ...] = ()
    auditors = [a for a in _CORE_AUDITORS if a not in disabled]
    assert "impl-vs-spec" in auditors


def test_impl_vs_spec_honors_extensions_disabled():
    # O filtro defensivo extensions_disabled é honrado (espelha os outros core).
    disabled = ("impl-vs-spec",)
    auditors = [a for a in _CORE_AUDITORS if a not in disabled]
    assert "impl-vs-spec" not in auditors
    # mas os outros core seguem presentes
    assert "spec-vs-spec" in auditors


def test_validate_qa_finding_accepts_impl_vs_spec():
    """C-001: um finding com vector=impl-vs-spec PASSA pelo validator de
    contrato (antes do fix, o enum core o rejeitava com raise)."""
    from validators.validate_qa_finding import validate_qa_finding

    finding = {
        "id": "impl-vs-spec-0001",
        "fingerprint": "a" * 64,
        "vector": "impl-vs-spec",
        "severity": "high",
        "title": "email sem validação",
        "description": "data-contract exige regex; impl aceita sem validar.",
        "scope": {"files": ["snapshot/impl/RegisterScreen.kt"]},
        "evidence": {
            "auditor": "impl-vs-spec",
            "auditor_reasoning": "RegisterScreen.kt:42 aceita email sem validar; data-contract exige regex.",
        },
        "proposed_evolution": {
            "type": "qa-finding-impl-vs-spec",
            "target": "RegisterScreen.kt",
            "summary": "adicionar validação de email",
            "actionable": True,
        },
        "created_at": "2026-06-30T12:00:00Z",
    }
    # Não deve raise.
    validate_qa_finding(finding)


def test_validate_qa_report_requires_impl_vs_spec_in_by_vector():
    """C-001: o report exige a key impl-vs-spec em summary.by_vector
    (subset de _REQUIRED_VECTOR_KEYS)."""
    from validators.validate_qa_report import _REQUIRED_VECTOR_KEYS

    assert "impl-vs-spec" in _REQUIRED_VECTOR_KEYS


def test_synthesis_seeds_impl_vs_spec_in_by_vector():
    """C-001: o synthesizer seeda impl-vs-spec com 0 — sem isso, um report sem
    findings impl-vs-spec quebraria validate_qa_report (subset check)."""
    from engine.qa.synthesis import synthesize

    result = synthesize([])
    assert "impl-vs-spec" in result.by_vector
    assert result.by_vector["impl-vs-spec"] == 0


def test_synthesis_counts_impl_vs_spec_finding():
    from engine.qa.synthesis import synthesize

    finding = {
        "id": "impl-vs-spec-0001",
        "fingerprint": "b" * 64,
        "vector": "impl-vs-spec",
        "severity": "medium",
        "title": "rota ausente",
        "description": "navigation-spec declara rota; impl não navega.",
        "scope": {"files": ["snapshot/impl/Nav.kt"]},
        "evidence": {"auditor": "impl-vs-spec"},
        "proposed_evolution": {
            "type": "qa-finding-impl-vs-spec",
            "target": "Nav.kt",
            "summary": "implementar transição",
            "actionable": True,
        },
        "created_at": "2026-06-30T12:00:00Z",
    }
    result = synthesize([finding])
    assert result.by_vector["impl-vs-spec"] == 1
