"""Phase 4 — Synthesis. Dedup + verdict calculation (spec §5.4).

Consumidor canonico: ``engine/qa.py`` Phase 4 (forge qa). Recebe lista de
findings draft (de Phase 2/3 auditores), deduplica por fingerprint canonical-
form (Decisão 25), atribui contagens por severity/vector, calcula verdict
global.

Verdict logic (§5.4) é informativo — não bloqueia retrospective nem commit
(§12.2 / Decisão 5). Exit code é responsabilidade de Phase 5 emit.

Reuso (mandamento #3):
- ``engine.utils.sha256.normalise_description`` — normalização NFC +
  casefold + whitespace collapse pra estabilidade contra cosmetic edits.
- Pattern de ``canonical_form_fingerprint`` em ``engine/utils/sha256.py`` —
  estrutura json.dumps(sort_keys=True, separators).

API publica:

    from engine.qa.synthesis import (
        synthesize, canonical_fingerprint, dedup_findings,
        compute_verdict, SynthesisResult,
        hydrate_validator_claim_evidence,
    )

    result = synthesize(draft_findings)
    # result.verdict, result.findings, result.by_severity, result.by_vector
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from engine.utils.sha256 import normalise_description


@dataclass(frozen=True)
class SandboxResultStub:
    """Subset estavel do ``SandboxResult`` consumido por
    ``findings_from_sandbox_results``.

    Evita coupling com ``Fixture`` (que exige ``Path``-typed input/validator)
    e permite re-hidratar a partir de ``sandbox-results.json`` escrito pelo
    conductor — onde apenas o nome do fixture e os campos de status sao
    relevantes pro finding emergente.

    Attributes:
        fixture_name: identificador do fixture (mapeia pra ``Fixture.name``).
        status: ``"ok" | "timeout" | "sandbox-breach" | "skipped-budget" |
            "error"`` (espelha ``SandboxStatus`` em ``engine.qa.sandbox``).
        exit_code: codigo de saida quando ``status == "ok"``.
        stdout / stderr: capturas. Vazios sao validos.
        duration_s: tempo de wall-clock; 0.0 quando subprocess nao chegou
            a rodar (skipped-budget, breach pre-spawn).
        error: mensagem livre, populada em ``status == "sandbox-breach" |
            "error"`` pra carregar contexto humano.
    """

    fixture_name: str
    status: str
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_s: float = 0.0
    error: str = ""


def hydrate_sandbox_results(
    raw: list[dict[str, Any]],
) -> list[SandboxResultStub]:
    """Converte lista de dicts (sandbox-results.json) em stubs.

    Tolerante a shapes diversos: aceita ``fixture: {name: ...}`` (espelha
    ``SandboxResult`` serializado) ou ``fixture_name: ...`` (forma flat).
    Itens nao-dict ou sem nome sao silenciosamente pulados — defesa
    contra arquivos corrompidos.
    """
    if not isinstance(raw, list):
        return []

    out: list[SandboxResultStub] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue

        # Resolver nome do fixture
        name = None
        fixture_blob = entry.get("fixture")
        if isinstance(fixture_blob, dict):
            name = fixture_blob.get("name")
        if not name:
            name = entry.get("fixture_name")
        if not isinstance(name, str) or not name:
            continue

        status = entry.get("status", "ok")
        if not isinstance(status, str):
            status = "error"

        exit_code = entry.get("exit_code")
        if exit_code is not None and (
            isinstance(exit_code, bool) or not isinstance(exit_code, int)
        ):
            exit_code = None

        stdout = entry.get("stdout", "")
        stderr = entry.get("stderr", "")
        error = entry.get("error", "")
        try:
            duration_s = float(entry.get("duration_s", 0.0))
        except (TypeError, ValueError):
            duration_s = 0.0

        out.append(
            SandboxResultStub(
                fixture_name=name,
                status=status,
                exit_code=exit_code,
                stdout=str(stdout) if stdout is not None else "",
                stderr=str(stderr) if stderr is not None else "",
                duration_s=duration_s,
                error=str(error) if error is not None else "",
            )
        )
    return out


def findings_from_sandbox_results(
    results: list[Any],
    *,
    run_id: str | None = None,
    validator_claim_fixtures: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Converte SandboxResult/SandboxResultStub problematicos em findings.

    Spec §5.3:
      - ``status == "sandbox-breach"`` -> finding severity=critical,
        vector=sandbox-breach (always BLOCK per §5.4 critical>=1).
      - ``status == "timeout"`` -> finding severity=medium,
        vector=sandbox-timeout.

    A4 (review pr27): ``status == "error"`` num fixture VALIDATOR-CLAIM
    (``fixture_name`` em ``validator_claim_fixtures``) -> finding
    severity=medium, vector=validator-claim-unresolvable. Antes isso era
    DROPADO; pro vetor "validator que mente", um validator irresolvível
    (project nem FORGE_HOME) significava NO evidence + NO sinal → false-clean.
    Agora é surfaced. ``error`` de fixtures fora desse set continua dropado
    (pode ser bug do validator, não do sandbox — deixa pro auditor LLM julgar).

    Status ``ok`` / ``skipped-budget`` nao geram findings automaticos.

    Os findings sao deterministicos: fingerprint canonical-form (Decisao
    25) garante que re-runs com mesmo breach/timeout dedupam corretamente
    em Phase 4. Inclui ``evidence.sandbox_result`` populado pra audit
    trail.

    Args:
        results: lista de ``SandboxResult`` ou ``SandboxResultStub`` (ou
            qualquer objeto com atributos ``fixture``-or-``fixture_name``,
            ``status``, ``error``, ``stdout``, ``stderr``, ``duration_s``,
            ``exit_code``).
        run_id: opcional — se fornecido, ID dos findings vira ``qa-<run_id>-
            <NNNN>`` no formato canonico. Default usa
            ``sandbox-{breach|timeout}-<fixture_name>-<NNNN>``.

    Returns:
        Lista de findings dict prontos pra entrar em ``synthesize``. Pode
        ser vazia (todos os results foram ``ok`` / ``skipped-budget``).
    """
    findings: list[dict[str, Any]] = []
    seq = 0
    for r in results:
        # Suporta tanto SandboxResult (com .fixture.name) quanto
        # SandboxResultStub (com .fixture_name)
        fixture_name = getattr(r, "fixture_name", None)
        if not fixture_name:
            fixture = getattr(r, "fixture", None)
            fixture_name = getattr(fixture, "name", None) if fixture else None
        if not fixture_name:
            fixture_name = "unknown-fixture"

        status = getattr(r, "status", "ok")
        # A4: ``error`` só vira finding pra fixture validator-claim conhecido.
        vc_set = validator_claim_fixtures or set()
        is_unresolvable_vc = status == "error" and fixture_name in vc_set
        if status not in ("sandbox-breach", "timeout") and not is_unresolvable_vc:
            continue

        seq += 1
        suffix = f"{seq:04d}"

        if is_unresolvable_vc:
            severity = "medium"
            vector = "validator-claim-unresolvable"
            title = (
                f"validator irresolvível em fixture '{fixture_name}' — "
                f"claim não verificável"
            )
            description = (
                f"O validator do claim '{fixture_name}' não pôde ser resolvido "
                f"(nem em project/validators/ nem em FORGE_HOME/validators/), "
                f"então o sandbox não conseguiu verificar se o validator de fato "
                f"detecta o contra-exemplo. Erro: "
                f"{getattr(r, 'error', '') or 'sem mensagem'}"
            )
            auditor_reasoning = (
                "Validator-claim com validator irresolvível NÃO pode ser "
                "settlado como clean: a ausência de evidência não é evidência "
                "de ausência. Medium porque o claim fica não-verificável (pode "
                "ser path errado no descritor OU validator realmente ausente) — "
                "user decide via forge evolve."
            )
            evolution_summary = (
                f"resolver o validator_path do claim '{fixture_name}' "
                f"(corrigir descritor ou confirmar validator ausente)"
            )
        elif status == "sandbox-breach":
            severity = "critical"
            vector = "sandbox-breach"
            title = f"sandbox breach detectado em fixture '{fixture_name}'"
            description = (
                f"Validator subprocess violou isolamento do sandbox "
                f"(Decisao 30) durante execucao do fixture '{fixture_name}'. "
                f"Erro: {getattr(r, 'error', '') or 'sem mensagem'}"
            )
            auditor_reasoning = (
                "Sandbox detectou tentativa de escape (chdir, path traversal "
                "ou similar). Critical porque rompe a invariante de "
                "isolamento — qualquer finding deste validator e suspeito "
                "ate o breach ser entendido."
            )
            evolution_summary = (
                f"investigar fixture '{fixture_name}' / validator pra "
                f"entender o vetor de breach"
            )
        else:  # timeout
            severity = "medium"
            vector = "sandbox-timeout"
            title = f"timeout em fixture '{fixture_name}'"
            description = (
                f"Validator subprocess excedeu agent-timeout-seconds "
                f"durante execucao do fixture '{fixture_name}'. "
                f"Duracao observada: {getattr(r, 'duration_s', 0.0):.2f}s."
            )
            auditor_reasoning = (
                "Validator demorou mais que o budget per-validator. Medium "
                "porque pode ser validator lento (ajustar budget) ou loop "
                "infinito (bug). User decide via forge evolve."
            )
            evolution_summary = (
                f"investigar se fixture '{fixture_name}' / validator tem "
                f"loop ou se budget precisa aumentar"
            )

        if run_id:
            finding_id = f"qa-{run_id}-{suffix}"
        else:
            # Fallback ID legível: usa o sufixo do vector (breach/timeout) ou o
            # vector inteiro pro novo validator-claim-unresolvable.
            vector_tag = (
                vector.split("-", 1)[1] if vector.startswith("sandbox-") else vector
            )
            finding_id = f"sandbox-{vector_tag}-{fixture_name}-{suffix}"

        sandbox_result_evidence: dict[str, Any] = {
            "status": status,
            "duration_s": float(getattr(r, "duration_s", 0.0)),
        }
        exit_code = getattr(r, "exit_code", None)
        if exit_code is not None:
            sandbox_result_evidence["exit_code"] = int(exit_code)
        stdout = getattr(r, "stdout", "")
        if stdout:
            sandbox_result_evidence["stdout"] = str(stdout)
        stderr = getattr(r, "stderr", "")
        if stderr:
            sandbox_result_evidence["stderr"] = str(stderr)
        err = getattr(r, "error", "")
        if err:
            sandbox_result_evidence["error"] = str(err)

        finding = {
            "id": finding_id,
            "vector": vector,
            "severity": severity,
            "title": title,
            "description": description,
            "scope": {"files": [f"<sandbox>/{fixture_name}"]},
            "evidence": {
                "auditor": "qa-sandbox",
                "auditor_reasoning": auditor_reasoning,
                "sandbox_result": sandbox_result_evidence,
            },
            "proposed_evolution": {
                "type": f"qa-finding-{vector}",
                "summary": evolution_summary,
                "actionable": severity in ("critical", "high", "medium"),
            },
        }
        # Fingerprint canonical-form (Decisao 25) deterministico
        finding["fingerprint"] = canonical_fingerprint(finding)
        findings.append(finding)

    return findings


def hydrate_validator_claim_evidence(
    draft_findings: list[dict[str, Any]],
    stubs: list[SandboxResultStub],
) -> list[dict[str, Any]]:
    """F-4: hidrata ``evidence.sandbox_result`` em findings validator-claim.

    Diferente de ``findings_from_sandbox_results`` (que DERIVA findings
    novos pra breach/timeout), este helper ENRIQUECE drafts validator-claim
    existentes — emitidos pelo auditor com ``sandbox_result: null`` — casando
    cada um com a entrada de ``sandbox-results.json`` que executou a sua
    fixture. Sem isso, o headline "validator que mente" perde o audit trail
    do subprocess no ``qa-report.json`` final.

    Matching rule (A-4): ``Path(evidence["fixture_path"]).stem`` (basename sem
    extensão) ↔ ``stub.fixture_name``. Alinhado ao exemplo do conductor
    (``"validator-claim-traversal"`` sem extensão) e ao nome que o auditor
    gera.

    WR-04: o índice ``stub.fixture_name → stub`` colapsava colisões com
    "último vence" — dois fixtures de mesmo basename em dirs distintos
    (``fixtures/a/validator-claim-foo`` e ``fixtures/b/validator-claim-foo``)
    casavam ambos o mesmo stub, trocando o audit trail. Agora a colisão é
    detectada ao montar o índice: ``fixture_name`` ambíguo (2+ stubs) NÃO
    hidrata nenhum finding que case nele — conservador, alinhado ao "não
    inventar evidência". O draft permanece ``sandbox_result=None`` (válido).

    Determinístico e conservador — só hidrata quando há casamento seguro:

    - vetor != ``validator-claim`` → intocado.
    - ``evidence`` não-dict → intocado.
    - ``sandbox_result`` já preenchido (pelo conductor) → NÃO sobrescreve.
    - ``fixture_path`` ausente/não-str → intocado (sem adivinhação).
    - sem stub correspondente → permanece ``None`` (draft-válido).
    - ``fixture_name`` ambíguo (2+ stubs colidem no mesmo nome) → permanece
      ``None`` (WR-04 — sem cross-contaminação).
    - stub com ``exit_code is None`` (timeout/skipped) → permanece ``None``;
      ``validate_qa_finding`` exige ``exit_code: int`` quando o
      ``sandbox_result`` é dict, então hidratar nesse caso geraria shape
      inválido. ``None`` é placeholder aceito em draft.

    Não muta o input — retorna cópias rasas dos findings (e do evidence)
    tocados, pattern de ``dedup_findings``.

    Args:
        draft_findings: lista de findings draft (dicts).
        stubs: ``SandboxResultStub`` de ``hydrate_sandbox_results``.

    Returns:
        Lista nova; findings validator-claim com fixture executável e stub
        casado ganham ``evidence.sandbox_result`` dict. Demais inalterados.
    """
    if not isinstance(draft_findings, list):
        raise TypeError(
            f"draft_findings deve ser list pra "
            f"hydrate_validator_claim_evidence, recebido tipo "
            f"{type(draft_findings).__name__}"
        )

    # WR-04: index por fixture_name detectando colisões. Em vez de "último
    # vence" (que cross-contamina o audit trail quando dois fixtures
    # compartilham basename cross-dir), marcamos nomes ambíguos pra NÃO
    # hidratar nenhum finding que case neles.
    by_name: dict[str, SandboxResultStub] = {}
    ambiguous: set[str] = set()
    for s in stubs:
        if s.fixture_name in by_name:
            ambiguous.add(s.fixture_name)
        else:
            by_name[s.fixture_name] = s

    out: list[dict[str, Any]] = []
    for f in draft_findings:
        if not isinstance(f, dict) or f.get("vector") != "validator-claim":
            out.append(f)
            continue
        ev = f.get("evidence")
        if not isinstance(ev, dict):
            out.append(f)
            continue
        if ev.get("sandbox_result") is not None:
            out.append(f)  # já hidratado pelo conductor — não sobrescrever
            continue
        fp = ev.get("fixture_path")
        if not isinstance(fp, str):
            out.append(f)
            continue
        name = Path(fp).stem
        if name in ambiguous:
            # WR-04: fixture_name ambíguo → não hidrata (conservador, sem
            # cross-contaminação). Permanece None (draft-válido).
            # B3 (review pr27): loga o skip pra traceability — sem isso o
            # finding fica sem sandbox_result e o operador não sabe por quê.
            print(
                f"⚠ hydrate validator-claim: fixture_name '{name}' ambíguo "
                f"(2+ stubs colidem no basename) — sandbox_result NÃO hidratado "
                f"pra evitar cross-contaminação (WR-04). Draft permanece sem "
                f"evidence de sandbox.",
                file=sys.stderr,
            )
            out.append(f)
            continue
        stub = by_name.get(name)
        if stub is None or stub.exit_code is None:
            # sem casamento OU exit_code ausente → permanece None (válido).
            out.append(f)
            continue

        new_evidence = dict(ev)
        new_evidence["sandbox_result"] = {
            "exit_code": int(stub.exit_code),
            "stdout": stub.stdout,
            "stderr": stub.stderr,
            "duration_s": float(stub.duration_s),
        }
        new_finding = dict(f)
        new_finding["evidence"] = new_evidence
        out.append(new_finding)

    return out


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

    Normalização (alinhada com ``engine/utils/sha256.normalise_description``):
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
        "title": normalise_description(str(finding.get("title") or "")),
        "description": normalise_description(str(finding.get("description") or "")),
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
    """Colapsa findings com mesma fingerprint, registrando auditores duplicados.

    Cada finding ganha campo ``fingerprint`` (calculado se ausente).
    Quando 2+ findings batem no mesmo fingerprint:
      - sobrevive o primeiro encontrado (cópia rasa)
      - nomes de auditores dos demais entram em
        ``evidence.duplicates`` (list, ordem de chegada, sem repetir).

    Alinhado com ``agents/qa-synthesizer.md`` §dedup spec: duplicates carrega
    apenas auditor names — a evidência por-auditor original já vive no draft
    arquivo do auditor em ``<run>/findings/``. Synthesis registra "outros
    auditores também viram isto" pra reforço estatístico no verdict humano.

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
            evidence = existing.setdefault("evidence", {})
            if not isinstance(evidence, dict):
                # Defensive: existing.evidence pode ter vindo não-dict do
                # draft original — substitui por dict pra poder registrar
                # duplicates sem AttributeError downstream.
                evidence = {}
                existing["evidence"] = evidence
            duplicates = evidence.setdefault("duplicates", [])
            if not isinstance(duplicates, list):
                duplicates = []
                evidence["duplicates"] = duplicates
            dup_evidence = f.get("evidence") or {}
            if isinstance(dup_evidence, dict):
                auditor = dup_evidence.get("auditor")
            else:
                auditor = None
            if isinstance(auditor, str) and auditor and auditor not in duplicates:
                duplicates.append(auditor)
        else:
            survivor = dict(f)
            survivor["fingerprint"] = fp
            # Deep-ish copy de evidence pra impedir mutação do input quando
            # findings subsequentes acrescentarem entradas em
            # ``evidence.duplicates`` (path do branch ``fp in by_fp``).
            if isinstance(survivor.get("evidence"), dict):
                evidence_copy = dict(survivor["evidence"])
                if isinstance(evidence_copy.get("duplicates"), list):
                    evidence_copy["duplicates"] = list(evidence_copy["duplicates"])
                survivor["evidence"] = evidence_copy
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
        else:
            # Docstring promete: findings sem severity reconhecida contam
            # como info (não pesa em BLOCK/FLAG). Alinha impl à promessa.
            sev_count["info"] += 1

    if sev_count["critical"] >= 1 or sev_count["high"] >= 3:
        return "BLOCK"
    if sev_count["high"] in (1, 2) or sev_count["medium"] >= 3:
        return "FLAG"
    return "PASS"


@dataclass(frozen=True)
class SynthesisResult:
    """Resultado de ``synthesize()``. Consumido por Phase 5.

    Shallow-frozen — atributos top-level são imutáveis (rebind raises
    ``dataclasses.FrozenInstanceError``), mas os containers internos
    (``findings``, ``by_severity``, ``by_vector``) são mutáveis em si.
    Callers devem tratar como read-only por convenção; não mutate
    post-creation pra evitar confusão de estado entre Phase 4 (synthesis)
    e Phase 5 (emit). Frozen serve pra detectar reassignment acidental
    do atributo inteiro — não pra impedir append em list interna.
    """

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

    # Inicializa todos os 4 vectors core com 0 — validate_qa_report exige
    # presença das 4 keys (_REQUIRED_VECTOR_KEYS.issubset). Sem isso, run
    # com zero findings em algum vector quebraria a validação downstream.
    by_vec: dict[str, int] = {
        "spec-vs-spec": 0,
        "coverage": 0,
        "chaos": 0,
        "validator-claim": 0,
    }
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
