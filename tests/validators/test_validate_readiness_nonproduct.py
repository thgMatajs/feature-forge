"""validate_readiness resolve features non-product (follow-up Wave 1).

Bug: `validate()` resolvia o dir da feature via `feature_dir` (hardcoded
`features/`), cego pra features non-product (refactor/spike/chore/bugfix) que
vivem em `non-product/{slug}/`. Resultado: readiness varria o dir product vazio
e reportava "review ausente" falso pra toda feature non-product.

Fix: resolver via `feature_path(project_root, slug, subtype=current_subtype(...))`
— mesmo pattern de `undo._delete_feature_artifacts`. Cobre o needs_elicitation
scan E o lookup do implementation-readiness-review.md de uma vez.

Refs: docs/superpowers/specs/2026-06-18-w-debt.md §2.3 (validate_readiness non-product blind)
"""

from __future__ import annotations

from pathlib import Path

from engine.memory.l1 import set_subtype
from engine.utils.paths import feature_path
from validators import validate_readiness


def _write_ready_review(f_root: Path) -> None:
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


def test_validate_finds_review_for_nonproduct_feature(tmp_forge_project: Path) -> None:
    """Feature non-product (subtype refactor) → readiness encontra o review no
    dir non-product/{slug}/, não reporta 'review ausente' falso."""
    slug = "tidy-imports"
    set_subtype(slug, tmp_forge_project, "refactor")
    f_root = feature_path(tmp_forge_project, slug, subtype="refactor")
    f_root.mkdir(parents=True)
    _write_ready_review(f_root)

    result = validate_readiness.validate(tmp_forge_project, scope="feature", id=slug)
    assert result["status"] == "pass", (
        f"non-product readiness deveria achar o review em {f_root}; result={result}"
    )


def test_validate_blocks_nonproduct_needs_elicitation(tmp_forge_project: Path) -> None:
    """needs_elicitation ativo numa feature non-product também bloqueia — prova
    que o scan resolve o dir non-product, não o product vazio."""
    slug = "spike-cache"
    set_subtype(slug, tmp_forge_project, "spike")
    f_root = feature_path(tmp_forge_project, slug, subtype="spike")
    f_root.mkdir(parents=True)
    _write_ready_review(f_root)
    (f_root / "ui-state-spec.yaml").write_text(
        "screens:\n  - name: home\n    states:\n"
        "      - id: empty\n        needs_elicitation: true\n",
        encoding="utf-8",
    )

    result = validate_readiness.validate(tmp_forge_project, scope="feature", id=slug)
    assert result["status"] == "fail"
    assert "needs_elicitation" in result.get("what-failed", "")
