"""Phase 4 — Synthesis. Dedup + verdict calculation (spec §5.4).

Consumidor canonico: ``engine/qa.py`` Phase 4 (forge qa). Recebe lista de
findings draft (de Phase 2/3 auditores), deduplica por fingerprint canonical-
form (Decisão 25), atribui contagens por severity/vector, calcula verdict
global.

Verdict logic (§5.4) é informativo — não bloqueia retrospective nem commit
(§12.2 / Decisão 5). Exit code é responsabilidade de Phase 5 emit.

Reuso (mandamento #3):
- ``engine.utils.sha256._normalise_description`` — normalização NFC +
  casefold + whitespace collapse pra estabilidade contra cosmetic edits.
- Pattern de ``canonical_form_fingerprint`` em ``engine/utils/sha256.py`` —
  estrutura json.dumps(sort_keys=True, separators).

API publica:

    from engine.qa.synthesis import (
        synthesize, canonical_fingerprint, dedup_findings,
        compute_verdict, SynthesisResult,
    )

    result = synthesize(draft_findings)
    # result.verdict, result.findings, result.by_severity, result.by_vector
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal

from engine.utils.sha256 import _normalise_description


Severity = Literal["critical", "high", "medium", "low", "info"]
Verdict = Literal["BLOCK", "FLAG", "PASS"]

_SEVERITY_KEYS: tuple[Severity, ...] = ("critical", "high", "medium", "low", "info")


def canonical_fingerprint(finding: dict[str, Any]) -> str:
    """Decisão 25 — fingerprint estável contra cosmetic edits.

    canonical-form = sha256(json-sorted({
        type:        finding.vector,
        title:       normalize(finding.title),
        description: normalize(finding.description),
        files:       sorted(finding.scope.files),
    }))

    Normalização (alinhada com ``engine/utils/sha256._normalise_description``):
    NFC + casefold + whitespace collapse. Sobrevive a case differences, extra
    whitespace, accent decomposition. Muda quando vector / title-semântico /
    description-semântico / files mudam.

    Retorna sha256 hex lowercase 64-char (compatível com
    ``validators.validate_qa_finding._FINGERPRINT_RE``).
    """
    if not isinstance(finding, dict):
        raise TypeError(
            f"finding deve ser dict pra canonical_fingerprint, "
            f"recebido tipo {type(finding).__name__}"
        )

    scope = finding.get("scope") or {}
    files = scope.get("files", []) if isinstance(scope, dict) else []
    if not isinstance(files, list):
        files = []

    norm = {
        "type": str(finding.get("vector", "")),
        "title": _normalise_description(str(finding.get("title") or "")),
        "description": _normalise_description(str(finding.get("description") or "")),
        "files": sorted(str(f) for f in files),
    }
    blob = json.dumps(
        norm,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def dedup_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Colapsa findings com mesma fingerprint, anexando evidências extras.

    Cada finding ganha campo ``fingerprint`` (calculado se ausente).
    Quando 2+ findings batem no mesmo fingerprint:
      - sobrevive o primeiro encontrado (cópia rasa)
      - evidências dos demais entram em ``evidence_extras`` (list, ordenada)

    Defensive: input não-list raise TypeError. Item não-dict raise TypeError
    nomeando o índice.
    """
    if not isinstance(findings, list):
        raise TypeError(
            f"findings deve ser list pra dedup_findings, "
            f"recebido tipo {type(findings).__name__}"
        )

    by_fp: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for idx, f in enumerate(findings):
        if not isinstance(f, dict):
            raise TypeError(
                f"findings[{idx}] deve ser dict, "
                f"recebido tipo {type(f).__name__}"
            )
        fp = f.get("fingerprint") or canonical_fingerprint(f)
        if fp in by_fp:
            existing = by_fp[fp]
            extras = existing.setdefault("evidence_extras", [])
            extras.append(f.get("evidence", {}))
        else:
            survivor = dict(f)
            survivor["fingerprint"] = fp
            by_fp[fp] = survivor
            order.append(fp)
    return [by_fp[fp] for fp in order]


def compute_verdict(findings: list[dict[str, Any]]) -> Verdict:
    """Verdict logic — spec §5.4.

    Regras (ordem importa — BLOCK antes de FLAG):

      BLOCK if critical >= 1 or high >= 3
      FLAG  if high in {1, 2} or medium >= 3
      PASS  otherwise

    Findings sem campo ``severity`` (ou com valor não-reconhecido) contam
    como ``info`` (não pesam no verdict). Decisão pragmática: synthesis não
    rejeita drafts mal-formados — validação shape é responsabilidade de
    ``validators.validate_qa_finding`` upstream.
    """
    if not isinstance(findings, list):
        raise TypeError(
            f"findings deve ser list pra compute_verdict, "
            f"recebido tipo {type(findings).__name__}"
        )

    sev_count: Counter[str] = Counter()
    for f in findings:
        if not isinstance(f, dict):
            continue
        sev = f.get("severity")
        if sev in _SEVERITY_KEYS:
            sev_count[sev] += 1

    if sev_count["critical"] >= 1 or sev_count["high"] >= 3:
        return "BLOCK"
    if sev_count["high"] in (1, 2) or sev_count["medium"] >= 3:
        return "FLAG"
    return "PASS"


@dataclass(frozen=True)
class SynthesisResult:
    """Resultado de ``synthesize()``. Imutável (frozen) — consumido por Phase 5."""

    findings: list[dict[str, Any]] = field(default_factory=list)
    verdict: Verdict = "PASS"
    by_severity: dict[str, int] = field(default_factory=dict)
    by_vector: dict[str, int] = field(default_factory=dict)


def synthesize(draft_findings: list[dict[str, Any]]) -> SynthesisResult:
    """Pipeline Phase 4 — dedup + verdict + counts.

    Args:
        draft_findings: lista de findings draft (dicts) emitidos por
            auditores Phase 2/3. Cada dict deve ter pelo menos ``vector``,
            ``severity``, ``scope`` pra contribuir corretamente. Drafts mal-
            formados são tolerados (sev/vector ignorados) — shape strict é
            responsabilidade de ``validate_qa_finding`` upstream.

    Returns:
        ``SynthesisResult`` com findings deduplicados, verdict global,
        contagens por severity (todas 5 keys sempre presentes) e por vector.

    Raises:
        TypeError: se ``draft_findings`` não é list.
    """
    if not isinstance(draft_findings, list):
        raise TypeError(
            f"draft_findings deve ser list pra synthesize, "
            f"recebido tipo {type(draft_findings).__name__}"
        )

    deduped = dedup_findings(draft_findings)
    verdict = compute_verdict(deduped)

    by_sev: dict[str, int] = {k: 0 for k in _SEVERITY_KEYS}
    for f in deduped:
        sev = f.get("severity")
        if sev in _SEVERITY_KEYS:
            by_sev[sev] += 1

    by_vec: dict[str, int] = {}
    for f in deduped:
        vec = f.get("vector")
        if isinstance(vec, str) and vec:
            by_vec[vec] = by_vec.get(vec, 0) + 1

    return SynthesisResult(
        findings=deduped,
        verdict=verdict,
        by_severity=by_sev,
        by_vector=by_vec,
    )
