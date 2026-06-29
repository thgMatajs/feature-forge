"""Tests for engine/qa/emit.py — Phase 5 emit (spec §5.5).

Cobertura:
- Filtra severity ∈ {critical, high, medium} (low/info ignorados).
- Dedup contra rejected-fingerprints.yaml (Decisão 25).
- Atomic write via tmp file + os.replace.
- OSError graceful: write_failed=True, tmp file limpo, sem propagar.
- Defensive: empty findings, only low/info, append (não overwrite),
  rejected-fingerprints.yaml ausente.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from engine.qa.emit import (
    _ACTIONABLE_SEVERITIES,
    emit_proposed_evolutions,
    filter_actionable,
    load_rejected_fingerprints,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_finding(
    *,
    severity: str,
    fingerprint: str,
    vector: str = "stub-detection",
    title: str = "stub remanescente",
) -> dict[str, Any]:
    """Constrói finding shape mínimo aceito por emit_proposed_evolutions."""
    return {
        "vector": vector,
        "severity": severity,
        "fingerprint": fingerprint,
        "title": title,
        "description": "detalhe técnico",
        "proposed_evolution": {
            "type": f"qa-finding-{vector}",
            "summary": f"resumo {title}",
        },
    }


def _claude_l1_dir(project_root: Path) -> Path:
    return project_root / ".claude" / "forge" / "state" / "lifecycle" / "proposed-evolutions"


# ── Constante canônica ───────────────────────────────────────────────────────


def test_actionable_severities_is_exact_set():
    """Decisão alinhada à spec §5.5: só critical/high/medium viram proposed-evolution."""
    assert _ACTIONABLE_SEVERITIES == {"critical", "high", "medium"}


# ── 4 obrigatórios ───────────────────────────────────────────────────────────


def test_writes_actionable_findings_to_proposed_yaml(tmp_path: Path) -> None:
    """Filtra severity actionable; low/info ignorados; demais escritos."""
    findings = [
        _make_finding(severity="critical", fingerprint="fp-crit"),
        _make_finding(severity="high", fingerprint="fp-high"),
        _make_finding(severity="medium", fingerprint="fp-med"),
        _make_finding(severity="low", fingerprint="fp-low"),
        _make_finding(severity="info", fingerprint="fp-info"),
    ]

    result = emit_proposed_evolutions(findings, project_root=tmp_path)

    assert result["written"] == 3
    assert result["skipped"] == 0
    assert result["write_failed"] is False

    out_path = _claude_l1_dir(tmp_path) / "proposed.yaml"
    assert out_path.exists()
    data = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    entries = data["entries"]
    fingerprints_written = {e["fingerprint"] for e in entries}
    assert fingerprints_written == {"fp-crit", "fp-high", "fp-med"}


def test_skips_findings_with_fingerprint_in_rejected(tmp_path: Path) -> None:
    """Decisão 25: finding com fingerprint em rejected-fingerprints.yaml não escrito."""
    rejected_dir = _claude_l1_dir(tmp_path)
    rejected_dir.mkdir(parents=True, exist_ok=True)
    rejected_path = rejected_dir / "rejected-fingerprints.yaml"
    rejected_path.write_text(
        yaml.safe_dump({"rejected": ["fp-vetoed"]}),
        encoding="utf-8",
    )

    findings = [
        _make_finding(severity="high", fingerprint="fp-vetoed"),
        _make_finding(severity="high", fingerprint="fp-novo"),
    ]

    result = emit_proposed_evolutions(findings, project_root=tmp_path)

    assert result["written"] == 1
    assert result["skipped"] == 1
    assert result["write_failed"] is False

    data = yaml.safe_load((rejected_dir / "proposed.yaml").read_text(encoding="utf-8"))
    entries = data["entries"]
    assert len(entries) == 1
    assert entries[0]["fingerprint"] == "fp-novo"


def test_atomic_write_via_tmp_rename(tmp_path: Path) -> None:
    """Após emit, tmp file foi renomeado — não persiste no fs."""
    findings = [_make_finding(severity="high", fingerprint="fp-x")]
    emit_proposed_evolutions(findings, project_root=tmp_path)

    out_dir = _claude_l1_dir(tmp_path)
    assert (out_dir / "proposed.yaml").exists()
    assert not (out_dir / "proposed.yaml.tmp").exists()


def test_oserror_returns_write_failed_true_gracefully(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Disk full sim: Path.write_text raise OSError → write_failed=True, sem propagar."""
    original_write_text = Path.write_text

    def fake_write_text(self: Path, *args: Any, **kwargs: Any) -> int:
        if self.name.endswith(".tmp"):
            raise OSError("simulated disk full")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fake_write_text)

    findings = [_make_finding(severity="high", fingerprint="fp-x")]
    # Não deve propagar
    result = emit_proposed_evolutions(findings, project_root=tmp_path)

    assert result["write_failed"] is True
    out_dir = _claude_l1_dir(tmp_path)
    # Tmp file cleanup — não vaza no fs
    assert not (out_dir / "proposed.yaml.tmp").exists()
    # Final path não foi criado (rename nunca rolou)
    assert not (out_dir / "proposed.yaml").exists()


# ── Defensive extras ─────────────────────────────────────────────────────────


def test_empty_findings_returns_zero_zero_no_write(tmp_path: Path) -> None:
    """findings=[] → counts zero, nenhum arquivo final criado."""
    result = emit_proposed_evolutions([], project_root=tmp_path)

    assert result == {"written": 0, "skipped": 0, "write_failed": False}
    out_path = _claude_l1_dir(tmp_path) / "proposed.yaml"
    assert not out_path.exists()


def test_only_low_info_findings_writes_nothing(tmp_path: Path) -> None:
    """Todos abaixo do threshold actionable → written=0."""
    findings = [
        _make_finding(severity="low", fingerprint="fp-1"),
        _make_finding(severity="info", fingerprint="fp-2"),
    ]
    result = emit_proposed_evolutions(findings, project_root=tmp_path)

    assert result["written"] == 0
    assert result["skipped"] == 0
    assert result["write_failed"] is False
    out_path = _claude_l1_dir(tmp_path) / "proposed.yaml"
    assert not out_path.exists()


def test_existing_proposed_yaml_appends_not_overwrites(tmp_path: Path) -> None:
    """proposed.yaml já tem 1 entry; emit adiciona 1; total 2 entries."""
    out_dir = _claude_l1_dir(tmp_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "proposed.yaml"
    existing_entry = {
        "type": "qa-finding-other",
        "fingerprint": "fp-pre-existente",
        "summary": "preexistente",
        "payload": {"vector": "other"},
    }
    out_path.write_text(
        yaml.safe_dump({"entries": [existing_entry]}, sort_keys=False),
        encoding="utf-8",
    )

    findings = [_make_finding(severity="high", fingerprint="fp-novo")]
    result = emit_proposed_evolutions(findings, project_root=tmp_path)

    assert result["written"] == 1
    data = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    entries = data["entries"]
    assert len(entries) == 2
    fps = {e["fingerprint"] for e in entries}
    assert fps == {"fp-pre-existente", "fp-novo"}


def test_rejected_fingerprints_yaml_missing_returns_empty_set(tmp_path: Path) -> None:
    """Sem arquivo rejected-fingerprints.yaml → load retorna set() sem raise."""
    result = load_rejected_fingerprints(tmp_path)
    assert result == set()
    assert isinstance(result, set)


# ── Helpers de robustez (não nos 4 obrigatórios, mas curam regressões reais) ─


def test_load_rejected_fingerprints_handles_corrupted_yaml(tmp_path: Path) -> None:
    """yaml.safe_load retornando None ou non-dict não deve raise."""
    rejected_dir = _claude_l1_dir(tmp_path)
    rejected_dir.mkdir(parents=True, exist_ok=True)
    rejected_path = rejected_dir / "rejected-fingerprints.yaml"

    # Caso 1: arquivo vazio (yaml.safe_load retorna None)
    rejected_path.write_text("", encoding="utf-8")
    assert load_rejected_fingerprints(tmp_path) == set()

    # Caso 2: top-level é list (não dict)
    rejected_path.write_text("- foo\n- bar\n", encoding="utf-8")
    assert load_rejected_fingerprints(tmp_path) == set()


def test_filter_actionable_helper_returns_only_actionable_severities() -> None:
    """filter_actionable() respeita _ACTIONABLE_SEVERITIES."""
    findings = [
        _make_finding(severity="critical", fingerprint="a"),
        _make_finding(severity="high", fingerprint="b"),
        _make_finding(severity="medium", fingerprint="c"),
        _make_finding(severity="low", fingerprint="d"),
        _make_finding(severity="info", fingerprint="e"),
        {"severity": "unknown", "fingerprint": "f"},  # severity inválida
        {"fingerprint": "g"},  # sem severity
    ]
    out = filter_actionable(findings)
    assert {f["fingerprint"] for f in out} == {"a", "b", "c"}
