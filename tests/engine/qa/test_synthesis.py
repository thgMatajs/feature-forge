"""Tests for engine.qa.synthesis — Phase 4 dedup + verdict logic (§5.4).

Cobertura TDD-strict (5 obrigatorios + 3 defensive):

  Verdict logic boundary (spec §5.4):
    BLOCK if critical>=1 OR high>=3
    FLAG  if high in {1,2} OR medium>=3
    PASS  otherwise

  1. test_verdict_block_on_one_critical
  2. test_verdict_block_on_three_high
  3. test_verdict_flag_on_one_high
     test_verdict_flag_on_two_high
     test_verdict_flag_on_three_medium
  4. test_verdict_pass_when_below_thresholds
  5. test_dedup_collapses_findings_with_same_fingerprint

  Defensive (Decisão 25 canonical-form):
  6. test_canonical_fingerprint_stable_against_cosmetic_edits
  7. test_canonical_fingerprint_changes_when_content_changes
  8. test_synthesize_returns_by_severity_with_all_keys

Cada finding sintético é mínimo (só campos consumidos por synthesis: vector,
severity, scope, evidence, title, description). Não usa
validate_qa_finding (orthogonal — synthesis aceita drafts, validação shape
é responsabilidade do consumidor).
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from engine.qa.synthesis import (
    SandboxResultStub,
    SynthesisResult,
    canonical_fingerprint,
    compute_verdict,
    dedup_findings,
    hydrate_validator_claim_evidence,
    synthesize,
)
from validators.validate_qa_finding import validate_qa_finding


def _mk(
    severity: str = "low",
    vector: str = "spec-vs-spec",
    title: str = "t",
    description: str = "d",
    files: list[str] | None = None,
    evidence: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Helper — finding draft mínimo pra testes de synthesis."""
    f: dict[str, Any] = {
        "severity": severity,
        "vector": vector,
        "title": title,
        "description": description,
        "scope": {"files": list(files or [])},
        "evidence": evidence or {"detail": "default"},
    }
    f.update(extra)
    return f


# ---------------------------------------------------------------------------
# Verdict logic (§5.4)
# ---------------------------------------------------------------------------


def test_verdict_block_on_one_critical():
    findings = [_mk(severity="critical")]
    assert compute_verdict(findings) == "BLOCK"


def test_verdict_block_on_three_high():
    findings = [
        _mk(severity="high", title="a"),
        _mk(severity="high", title="b"),
        _mk(severity="high", title="c"),
    ]
    assert compute_verdict(findings) == "BLOCK"


def test_verdict_flag_on_one_high():
    findings = [_mk(severity="high")]
    assert compute_verdict(findings) == "FLAG"


def test_verdict_flag_on_two_high():
    findings = [
        _mk(severity="high", title="a"),
        _mk(severity="high", title="b"),
    ]
    assert compute_verdict(findings) == "FLAG"


def test_verdict_flag_on_three_medium():
    findings = [
        _mk(severity="medium", title="a"),
        _mk(severity="medium", title="b"),
        _mk(severity="medium", title="c"),
    ]
    assert compute_verdict(findings) == "FLAG"


def test_verdict_pass_when_below_thresholds():
    findings = (
        [_mk(severity="medium", title=f"m{i}") for i in range(2)]
        + [_mk(severity="low", title=f"l{i}") for i in range(5)]
        + [_mk(severity="info", title=f"i{i}") for i in range(3)]
    )
    assert compute_verdict(findings) == "PASS"


# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------


def test_dedup_collapses_findings_with_same_fingerprint():
    """Sobrevive o primeiro; demais auditor names entram em
    ``evidence.duplicates`` (per agents/qa-synthesizer.md §dedup).

    Findings sem ``evidence.auditor`` não contribuem pra duplicates —
    evita poluir o registro com strings vazias.
    """
    fp = "a" * 64
    f1 = _mk(
        severity="high",
        title="dup",
        evidence={"auditor": "a1", "step": 1},
        fingerprint=fp,
    )
    f2 = _mk(
        severity="high",
        title="dup",
        evidence={"auditor": "a2", "step": 2},
        fingerprint=fp,
    )
    out = dedup_findings([f1, f2])
    assert len(out) == 1
    survivor = out[0]
    assert survivor["fingerprint"] == fp
    # evidence.auditor do survivor preservado; duplicates anexado.
    assert survivor["evidence"]["auditor"] == "a1"
    assert survivor["evidence"].get("duplicates") == ["a2"]
    # Pattern antigo (evidence_extras) não deve mais existir.
    assert "evidence_extras" not in survivor


# ---------------------------------------------------------------------------
# canonical_fingerprint (Decisão 25 — stable canonical-form)
# ---------------------------------------------------------------------------


def test_canonical_fingerprint_stable_against_cosmetic_edits():
    base = _mk(
        title="Race condition no checkout",
        description="Validator falha em fixture sintética sem race guard.",
        files=["a.py", "b.py"],
    )
    cosmetic = _mk(
        title="  RACE CONDITION NO CHECKOUT  ",
        description="\tValidator falha em fixture sintética sem race guard.\n",
        files=["a.py", "b.py"],
    )
    assert canonical_fingerprint(base) == canonical_fingerprint(cosmetic)


def test_canonical_fingerprint_changes_when_content_changes():
    base = _mk(
        title="Race condition",
        description="Original description.",
        files=["a.py"],
    )
    different = _mk(
        title="Race condition",
        description="Different description.",
        files=["a.py"],
    )
    assert canonical_fingerprint(base) != canonical_fingerprint(different)


def test_canonical_fingerprint_stable_against_files_order():
    f1 = _mk(files=["a.py", "b.py", "c.py"])
    f2 = _mk(files=["c.py", "a.py", "b.py"])
    assert canonical_fingerprint(f1) == canonical_fingerprint(f2)


def test_canonical_fingerprint_returns_64_char_lowercase_hex():
    fp = canonical_fingerprint(_mk())
    assert len(fp) == 64
    assert all(c in "0123456789abcdef" for c in fp)


# ---------------------------------------------------------------------------
# synthesize() — top-level integration
# ---------------------------------------------------------------------------


def test_synthesize_returns_by_severity_with_all_keys():
    findings = [_mk(severity="high")]
    result = synthesize(findings)
    assert isinstance(result, SynthesisResult)
    for key in ("critical", "high", "medium", "low", "info"):
        assert key in result.by_severity, f"missing severity key: {key}"
    assert result.by_severity["high"] == 1
    assert result.by_severity["critical"] == 0
    assert result.verdict == "FLAG"


def test_synthesize_raises_typeerror_on_non_list():
    with pytest.raises(TypeError, match="draft_findings"):
        synthesize("not a list")  # type: ignore[arg-type]


def test_synthesize_frozen_dataclass():
    """SynthesisResult é frozen (shallow): rebind de atributo top-level raise.

    Containers internos (findings, by_severity, by_vector) continuam mutáveis
    por design — frozen detecta apenas reassignment do atributo, não mutação
    interna. Ver docstring de SynthesisResult.
    """
    result = synthesize([_mk(severity="low")])
    with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
        result.verdict = "BLOCK"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# FIX-13: dedup usa evidence.duplicates (lista de auditor names) per spec
# agents/qa-synthesizer.md — não mais evidence_extras
# ---------------------------------------------------------------------------


def test_dedup_records_duplicate_auditors_in_evidence_duplicates():
    """Quando 2+ findings batem no mesmo fingerprint, os auditor names dos
    demais entram em ``survivor.evidence.duplicates`` (ordem de chegada,
    sem repetir). Spec: agents/qa-synthesizer.md §dedup.

    Survivor mantém evidence.auditor original; duplicates aparece SÓ
    quando há fingerprint colidindo. evidence_extras NÃO deve existir.
    """
    fp = "b" * 64
    f1 = _mk(
        severity="high",
        title="same",
        evidence={"auditor": "qa-auditor-spec-vs-spec", "step": 1},
        fingerprint=fp,
    )
    f2 = _mk(
        severity="high",
        title="same",
        evidence={"auditor": "qa-auditor-chaos", "step": 2},
        fingerprint=fp,
    )
    f3 = _mk(
        severity="high",
        title="same",
        evidence={"auditor": "qa-auditor-coverage", "step": 3},
        fingerprint=fp,
    )
    out = dedup_findings([f1, f2, f3])

    assert len(out) == 1
    survivor = out[0]
    assert "evidence_extras" not in survivor, (
        "evidence_extras é o pattern antigo — synthesis agora usa "
        "evidence.duplicates per agents/qa-synthesizer.md"
    )
    evidence = survivor["evidence"]
    assert evidence["auditor"] == "qa-auditor-spec-vs-spec"
    duplicates = evidence.get("duplicates")
    assert duplicates == ["qa-auditor-chaos", "qa-auditor-coverage"]


def test_dedup_duplicates_dedupes_same_auditor_name():
    """Mesmo auditor aparecendo 2x na fingerprint não duplica o nome
    em ``duplicates`` (set semantics preservando ordem)."""
    fp = "c" * 64
    f1 = _mk(severity="high", title="x", evidence={"auditor": "a"}, fingerprint=fp)
    f2 = _mk(severity="high", title="x", evidence={"auditor": "b"}, fingerprint=fp)
    f3 = _mk(severity="high", title="x", evidence={"auditor": "b"}, fingerprint=fp)
    out = dedup_findings([f1, f2, f3])

    assert len(out) == 1
    assert out[0]["evidence"]["duplicates"] == ["b"]


# ---------------------------------------------------------------------------
# F-4: hydrate_validator_claim_evidence
# ---------------------------------------------------------------------------


def _mk_validator_claim_draft(
    *,
    fixture_path: str | None = "fixtures/validator-claim-foo.yaml",
    sandbox_result: Any = None,
) -> dict[str, Any]:
    """Draft validator-claim COMPLETO (passa validate_qa_finding quando
    sandbox_result é None ou dict válido)."""
    evidence: dict[str, Any] = {
        "auditor": "qa-auditor-validator-claim",
        "auditor_reasoning": "validator deveria pegar mas nao pegou",
        "sandbox_result": sandbox_result,
    }
    if fixture_path is not None:
        evidence["fixture_path"] = fixture_path
    return {
        "id": "vc-0001",
        "fingerprint": "a" * 64,
        "vector": "validator-claim",
        "severity": "high",
        "title": "validator que mente",
        "description": "validator forge nao detecta o caso",
        "scope": {"files": ["validators/x.py"]},
        "evidence": evidence,
        "proposed_evolution": {
            "type": "qa-finding-validator-claim",
            "summary": "endurecer o validator",
            "actionable": True,
        },
        "created_at": "2026-06-19T12:00:00Z",
    }


def test_hydrate_validator_claim_evidence():
    """F-4: draft validator-claim com fixture executável casa com stub
    (exit_code int) e ganha evidence.sandbox_result dict válido."""
    draft = _mk_validator_claim_draft()
    stub = SandboxResultStub(
        fixture_name="validator-claim-foo",
        status="ok",
        exit_code=0,
        stdout="",
        stderr="",
        duration_s=0.3,
    )

    out = hydrate_validator_claim_evidence([draft], [stub])

    sr = out[0]["evidence"]["sandbox_result"]
    assert isinstance(sr, dict)
    assert sr["exit_code"] == 0
    assert sr["stdout"] == ""
    assert sr["stderr"] == ""
    assert sr["duration_s"] == 0.3
    # finding hidratado passa o validator de shape.
    validate_qa_finding(out[0])
    # nao muta o input.
    assert draft["evidence"]["sandbox_result"] is None


def test_hydrate_validator_claim_no_matching_stub_stays_null():
    """F-4: draft validator-claim sem stub correspondente permanece None
    (draft-válido); não inventa evidência."""
    draft = _mk_validator_claim_draft()
    other = SandboxResultStub(
        fixture_name="validator-claim-bar", status="ok", exit_code=0
    )

    out = hydrate_validator_claim_evidence([draft], [other])

    assert out[0]["evidence"]["sandbox_result"] is None
    validate_qa_finding(out[0])


def test_hydrate_validator_claim_other_vector_untouched():
    """F-4: drafts de outro vetor (chaos) não são tocados."""
    chaos = _mk(vector="chaos", evidence={"auditor": "qa-auditor-chaos"})
    stub = SandboxResultStub(fixture_name="anything", status="ok", exit_code=0)

    out = hydrate_validator_claim_evidence([chaos], [stub])

    assert out[0] == chaos


def test_hydrate_validator_claim_exit_code_none_stays_null():
    """F-4: stub com exit_code None (timeout/skipped) NÃO hidrata dict
    inválido — finding permanece None (validate_qa_finding aceita None)."""
    draft = _mk_validator_claim_draft()
    stub = SandboxResultStub(
        fixture_name="validator-claim-foo",
        status="timeout",
        exit_code=None,
        duration_s=10.0,
    )

    out = hydrate_validator_claim_evidence([draft], [stub])

    assert out[0]["evidence"]["sandbox_result"] is None
    validate_qa_finding(out[0])


def test_hydrate_validator_claim_already_hydrated_not_overwritten():
    """F-4: sandbox_result já preenchido pelo conductor não é sobrescrito."""
    existing_sr = {
        "exit_code": 2,
        "stdout": "conductor",
        "stderr": "",
        "duration_s": 1.0,
    }
    draft = _mk_validator_claim_draft(sandbox_result=existing_sr)
    stub = SandboxResultStub(
        fixture_name="validator-claim-foo", status="ok", exit_code=0, duration_s=0.3
    )

    out = hydrate_validator_claim_evidence([draft], [stub])

    assert out[0]["evidence"]["sandbox_result"] == existing_sr
