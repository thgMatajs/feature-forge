"""Integration — handoff qa → evolve (Decisões 25 + 26).

Wave 8 Task 8.7: cobertura do contrato qa Phase 5 (emit) → ``forge evolve``
(consumer). Decisões em jogo:

- **Decisão 25** — canonical-form fingerprint pra ``rejected-fingerprints.yaml``.
  Re-propor uma ideia rejeitada é ruído; emit pula fingerprints conhecidas.
- **Decisão 26** — single-by-single evolve apply. Evolve consome 1 entry
  por iteração, NÃO batch. Aqui validamos shape do entry + que cada
  ``payload`` preserva o finding completo (consumer humano decide).

Cenários cobertos:

1. Finding actionable (high) → entry com ``type: qa-finding-validator-claim``
   + fingerprint + payload completo
2. Fingerprint rejeitada → próxima run silencia (skipped, no entry novo)
3. Evolve "apply" simulado (consumer mockado) → pega APENAS 1 entry
   por iteração (Decisão 26)

Anti-padrão: importar ou modificar ``engine.evolve`` (escopo é qa→ evolve
boundary, não evolve internals). Consumer é simulado com leitura YAML.

Marker: integration (slow). Excluído da rapid lane.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.integration


def _finding(
    severity: str,
    title: str,
    vector: str = "validator-claim",
) -> dict[str, Any]:
    """Finding mínimo actionable pra Phase 5 emit."""
    return {
        "vector": vector,
        "severity": severity,
        "title": title,
        "description": f"{title} — descrição estendida pra fingerprint stability",
        "scope": {"files": ["validators/x.py"]},
        "evidence": {"detail": "claim sem exercise"},
        "proposed_evolution": {
            "type": f"qa-finding-{vector}",
            "summary": f"resolver: {title}",
        },
    }


def _proposed_path(project: Path) -> Path:
    return (
        project
        / ".claude"
        / "memory"
        / "L1"
        / "proposed-evolutions"
        / "proposed.yaml"
    )


def _rejected_path(project: Path) -> Path:
    return (
        project
        / ".claude"
        / "memory"
        / "L1"
        / "proposed-evolutions"
        / "rejected-fingerprints.yaml"
    )


def test_actionable_finding_writes_entry_with_canonical_shape(
    tmp_path: Path,
) -> None:
    """qa finding (high) → entry em proposed.yaml com tipo + fingerprint."""
    from engine.qa.emit import emit_proposed_evolutions
    from engine.qa.synthesis import synthesize

    proj = tmp_path / "qa-evolve-pilot"
    proj.mkdir()

    finding = _finding("high", "validator x sem exercise")
    result = synthesize([finding])
    assert result.verdict == "FLAG"  # high=1 → FLAG (sanity)

    summary = emit_proposed_evolutions(result.findings, project_root=proj)
    assert summary["written"] == 1
    assert summary["write_failed"] is False

    data = yaml.safe_load(_proposed_path(proj).read_text(encoding="utf-8"))
    entries = data["entries"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["type"] == "qa-finding-validator-claim"
    assert entry["fingerprint"], "fingerprint não-vazio é contrato Decisão 25"
    assert "summary" in entry
    # Payload preserva finding completo pra consumer (evolve) inspecionar
    assert entry["payload"]["title"] == "validator x sem exercise"
    assert entry["payload"]["vector"] == "validator-claim"


def test_rejected_fingerprint_silences_next_run(tmp_path: Path) -> None:
    """Fingerprint em rejected-fingerprints.yaml → próxima run skip silencioso."""
    from engine.qa.emit import emit_proposed_evolutions
    from engine.qa.synthesis import canonical_fingerprint, synthesize

    proj = tmp_path / "qa-evolve-pilot"
    proj.mkdir()

    finding = _finding("high", "rejected idea")
    fp = canonical_fingerprint(finding)

    # Pre-seed: rejected-fingerprints.yaml contém o fingerprint deste finding
    rejected_dir = _rejected_path(proj).parent
    rejected_dir.mkdir(parents=True)
    _rejected_path(proj).write_text(
        yaml.safe_dump({"rejected": [fp]}), encoding="utf-8"
    )

    result = synthesize([finding])
    summary = emit_proposed_evolutions(result.findings, project_root=proj)

    # Skip silencioso: written=0, skipped=1, no proposed.yaml criado
    assert summary["written"] == 0
    assert summary["skipped"] == 1
    assert summary["write_failed"] is False
    assert not _proposed_path(proj).exists(), (
        "fingerprint rejected NÃO deveria gerar proposed.yaml"
    )


def test_evolve_apply_consumes_single_entry_per_iteration(
    tmp_path: Path,
) -> None:
    """Decisão 26 — evolve consome 1 entry por iteração (não batch).

    Simulamos o consumer (forge evolve apply) lendo proposed.yaml e
    removendo APENAS a primeira entry, depois re-emitindo o YAML.
    Validamos que o shape sobrevive ao round-trip e que entries restantes
    aguardam próxima iteração.
    """
    from engine.qa.emit import emit_proposed_evolutions
    from engine.qa.synthesis import synthesize

    proj = tmp_path / "qa-evolve-pilot"
    proj.mkdir()

    findings = [
        _finding("high", "primeiro finding"),
        _finding("high", "segundo finding"),
        _finding("medium", "terceiro finding"),
    ]
    result = synthesize(findings)
    summary = emit_proposed_evolutions(result.findings, project_root=proj)
    assert summary["written"] == 3

    # Simula consumer evolve: lê, pega APENAS primeira entry, reescreve resto
    data = yaml.safe_load(_proposed_path(proj).read_text(encoding="utf-8"))
    entries = list(data["entries"])
    assert len(entries) == 3

    # Pop a primeira (Decisão 26 — single-by-single)
    consumed = entries.pop(0)
    assert consumed["payload"]["title"] == "primeiro finding"

    # Reescreve com 2 entries restantes (mimicando evolve persistir state)
    _proposed_path(proj).write_text(
        yaml.safe_dump({"entries": entries}, sort_keys=False),
        encoding="utf-8",
    )

    # Próxima iteração: 2 entries aguardando
    data2 = yaml.safe_load(_proposed_path(proj).read_text(encoding="utf-8"))
    remaining = data2["entries"]
    assert len(remaining) == 2
    assert remaining[0]["payload"]["title"] == "segundo finding"
    assert remaining[1]["payload"]["title"] == "terceiro finding"
