"""needs-elicitation scan no validate_readiness (Wave 1 C5).

Block-severity quando `needs-elicitation: true` sobrevive não-promovido em
contract spec; warning em narrativa.

Cobre dois níveis:
- **Isolado:** `_scan_needs_elicitation` flagueia o marker em `*-spec.yaml` e
  retorna `[]` quando o spec não carrega o marker.
- **Integração (prova de wiring):** `validate()` retorna `result_fail` mesmo
  com verdict nominal `ready` quando há `needs-elicitation` não-promovido —
  provando que o scan preempta o parse do verdict — e o caso espelho
  (`ready` + sem marker → `result_pass`, sem regressão).

Refs: docs/superpowers/specs/2026-06-17-ai-first-interaction-layer-design.md §4 C5
"""

from __future__ import annotations

from pathlib import Path

from validators import validate_readiness


# ── Isolado — _scan_needs_elicitation ────────────────────────────────────────


def test_scan_flags_needs_elicitation_in_contract(tmp_path: Path) -> None:
    f_root = tmp_path
    spec = f_root / "data-contract-spec.yaml"
    spec.write_text(
        "fields:\n  - name: starred\n    persist: needs-elicitation\n",
        encoding="utf-8",
    )
    hits = validate_readiness._scan_needs_elicitation(f_root)
    assert any("data-contract-spec.yaml" in h for h in hits)


def test_scan_clean_when_no_marker(tmp_path: Path) -> None:
    f_root = tmp_path
    (f_root / "data-contract-spec.yaml").write_text(
        "fields:\n  - name: starred\n    persist: true\n",
        encoding="utf-8",
    )
    assert validate_readiness._scan_needs_elicitation(f_root) == []


# ── Integração — scan preempta o parse do verdict em validate() ──────────────


def _write_ready_review(f_root: Path) -> None:
    """Escreve um implementation-readiness-review.md com verdict `ready`.

    Mirror de tests/unit/test_validators_readiness.py
    ::test_review_md_with_ready_verdict_passes — o caminho canônico que
    `validate()` parseia pra um result_pass.
    """
    (f_root / "implementation-readiness-review.md").write_text(
        "# Readiness review\n\n"
        "```yaml\n"
        "readiness_verdict:\n"
        "  status: ready\n"
        "  blockers: []\n"
        "  warnings: []\n"
        "```\n",
        encoding="utf-8",
    )


def test_validate_blocks_needs_elicitation_even_with_ready_verdict(
    tmp_forge_project: Path,
) -> None:
    """Verdict nominal `ready` NÃO mascara um contract spec não-elicitado.

    O scan roda no topo de validate(), antes do parse do verdict — então um
    needs-elicitation não-promovido força fail mesmo quando o verdict diz ready.
    """
    slug = "thin-but-complete"
    f_root = (
        tmp_forge_project
        / "docs"
        / "feature-implementation-workflow"
        / "features"
        / slug
    )
    f_root.mkdir(parents=True)
    _write_ready_review(f_root)
    # Contract spec com needs-elicitation não-promovido sobrevive até o readiness.
    (f_root / "data-contract-spec.yaml").write_text(
        "fields:\n  - name: starred\n    persist: needs-elicitation\n",
        encoding="utf-8",
    )

    result = validate_readiness.validate(tmp_forge_project, scope="feature", id=slug)
    assert result["status"] == "fail"
    assert len(result["paths"]) == 3
    assert "needs-elicitation" in result.get("what-failed", "")


def test_validate_ready_without_marker_still_passes(
    tmp_forge_project: Path,
) -> None:
    """Espelho: ready + sem needs-elicitation → result_pass (sem regressão)."""
    slug = "clean-ready-feature"
    f_root = (
        tmp_forge_project
        / "docs"
        / "feature-implementation-workflow"
        / "features"
        / slug
    )
    f_root.mkdir(parents=True)
    _write_ready_review(f_root)
    # Contract spec presente mas LIMPO (sem o marker).
    (f_root / "data-contract-spec.yaml").write_text(
        "fields:\n  - name: starred\n    persist: true\n",
        encoding="utf-8",
    )

    result = validate_readiness.validate(tmp_forge_project, scope="feature", id=slug)
    assert result["status"] == "pass"
