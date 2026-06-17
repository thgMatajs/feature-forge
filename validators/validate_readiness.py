#!/usr/bin/env python3
"""validate_readiness.py — Implementation readiness verdict check.

Reads `implementation-readiness-review.md` from the feature directory, extracts
the trailing YAML `readiness_verdict:` block, and requires `status: ready`.
Anything else (`partial`, `blocked`) → fail with 3-paths block.

Schema source: templates/implementation-readiness-review.template.md §verdict.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

from _common import (
    make_paths,
    result_fail,
    result_pass,
    result_warn,
    run_cli,
)

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.utils.paths import feature_dir  # noqa: E402

# Capture the LAST fenced ```yaml block that contains `readiness_verdict:` —
# the template ends with this block as the machine-readable verdict.
_YAML_BLOCK_RE = re.compile(
    r"```ya?ml\s*\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)


def _resolve_slug(kwargs: dict[str, Any]) -> str | None:
    scope = kwargs.get("scope") or "inferred"
    given_id = kwargs.get("id")
    if scope == "feature" and given_id:
        return given_id
    if given_id and not given_id.upper().startswith("TASK-"):
        return given_id
    return None


def _extract_verdict(text: str) -> dict[str, Any] | None:
    """Extract the readiness_verdict YAML block from the .md text.

    Strategy: walk all ```yaml fences in reverse, return the first one whose
    parse contains a `readiness_verdict` key. The template puts it last but
    drafts may have other yaml fences (open-questions, blockers, …).
    """
    matches = list(_YAML_BLOCK_RE.finditer(text))
    for m in reversed(matches):
        try:
            parsed = yaml.safe_load(m.group(1))
        except yaml.YAMLError:
            continue
        if isinstance(parsed, dict) and "readiness_verdict" in parsed:
            verdict = parsed["readiness_verdict"]
            if isinstance(verdict, dict):
                return verdict
    return None


# Contract specs onde needs-elicitation não-promovido é block-severity.
_CONTRACT_GLOBS = ("*-spec.yaml", "tasks/task-*.md", "*-contract*.yaml")


def _scan_needs_elicitation(f_root: Path) -> list[str]:
    """Retorna `arquivo:linha` com `needs-elicitation` ativo em contract specs.

    spec §4 C5 — fecha o ponto-cego "thin-but-structurally-complete": um campo
    `needs-elicitation` que o conductor não promoveu a `blocking: true` open
    question pode escapar como ready se a cadeia story→task fecha nominalmente.
    """
    hits: list[str] = []
    for pattern in _CONTRACT_GLOBS:
        for path in sorted(f_root.glob(pattern)):
            if not path.is_file():
                continue
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if "needs-elicitation" in line:
                    rel = path.relative_to(f_root)
                    hits.append(f"{rel}:{lineno}")
    return hits


def validate(project_root: Path, **kwargs: Any) -> dict[str, Any]:
    """Validate the readiness verdict for the active feature."""
    slug = _resolve_slug(kwargs)
    if not slug:
        return result_warn(
            "no feature slug provided — readiness check skipped",
            what_failed="no slug",
            where="--scope feature --id <slug>",
            why=["readiness is per-feature"],
        )

    f_root = feature_dir(project_root, slug)

    # spec C5 — needs-elicitation não-promovido bloqueia ANTES de parsear o
    # verdict (um verdict 'ready' não pode mascarar campo não-elicitado).
    elicitation_hits = _scan_needs_elicitation(f_root)
    if elicitation_hits:
        return result_fail(
            f"needs-elicitation não-promovido em {len(elicitation_hits)} contract spec(s)",
            what_failed="needs-elicitation: true sobreviveu em contract spec",
            where="; ".join(elicitation_hits[:5]),
            why=[
                "Campo needs-elicitation deve virar blocking:true open-question, não escapar como ready.",
                "Fecha o ponto-cego thin-but-structurally-complete (spec C5).",
            ],
            paths=make_paths(
                "Promover cada needs-elicitation a blocking:true em open-questions.yaml",
                "O conductor elicita na próxima rodada de Phase 3.",
                "Resolver inline se o valor já é conhecido",
                "Se foi marcado por engano e o default é claro.",
                "Reverter pra antes do plan — `forge undo`",
                "Se o escopo da feature mudou.",
            ),
        )

    review = f_root / "implementation-readiness-review.md"
    if not review.is_file():
        return result_fail(
            "implementation-readiness-review.md ausente",
            what_failed=f"missing {review.name}",
            where=str(review.relative_to(project_root)),
            why=[
                "readiness-reviewer (Wave E) ainda não rodou.",
                "execution-conductor refusa de implementar sem verdict.",
            ],
            paths=make_paths(
                "Rodar Wave E — `forge plan <slug>` (continua de onde parou)",
                "Última wave do plan — escreve o review.",
                "Reverter pra antes do plan — `forge undo last-plan`",
                "Se o feature mudou de escopo, refazer faz mais sentido.",
                "Marcar como exploratory — `forge memory forget L1 <slug>`",
                "Spike sem implementation contract.",
            ),
        )

    text = review.read_text(encoding="utf-8")
    verdict = _extract_verdict(text)
    if verdict is None:
        return result_fail(
            "readiness_verdict YAML block não encontrado em implementation-readiness-review.md",
            what_failed="missing trailing ```yaml block with readiness_verdict:",
            where=str(review.relative_to(project_root)),
            why=[
                "Template requer YAML bloco final com `readiness_verdict.status`.",
                "Conductors parsing falha sem isso.",
            ],
            paths=make_paths(
                "Adicionar o bloco ```yaml com readiness_verdict no fim do MD",
                "Copiar do template implementation-readiness-review.template.md §verdict.",
                "Re-gerar o review — `forge plan <slug> --rerun=readiness`",
                "Se foi escrito à mão e ficou inconsistente.",
                "Reverter pro último review bom — `forge undo`",
                "Se a corrupção é recente.",
            ),
        )

    status = str(verdict.get("status") or "").lower()
    if status == "ready":
        return result_pass(f"readiness verdict = ready (slug={slug})")

    blockers = list(verdict.get("blockers") or [])
    warnings = list(verdict.get("warnings") or [])
    blocker_count = len(blockers)

    if status == "blocked":
        return result_fail(
            f"readiness verdict = blocked ({blocker_count} blocker(s))",
            what_failed=", ".join(str(b) for b in blockers[:3]) or "blockers unspecified",
            where=str(review.relative_to(project_root)),
            why=[
                "execution-conductor refusa de iniciar quando blocked.",
                "Hard gate: readiness-must-be-ready.",
            ],
            paths=make_paths(
                "Resolver os blockers — siga os 3-caminhos de cada B-NNN no §9 do review",
                "Cada blocker já tem fix/revert/split documentado.",
                "Reverter o plan inteiro — `forge undo last-plan`",
                "Se os blockers vieram de uma wave anterior com bug.",
                "Split a feature em sub-features — re-rodar Wave A com escopo menor",
                "Quando o blocker é estrutural (escopo grande demais).",
            ),
        )

    # partial / unknown
    return result_fail(
        f"readiness verdict = {status or 'unknown'} (esperado: ready)",
        what_failed=f"status={status!r}, warnings={len(warnings)}, blockers={blocker_count}",
        where=str(review.relative_to(project_root)),
        why=[
            "Sub-states 'partial' / 'unknown' indicam questões em aberto.",
            "Implementar com verdict != ready arrisca invented behavior downstream.",
        ],
        paths=make_paths(
            "Resolver as questões pending — `forge plan <slug>` continua",
            "Conductor abre as questões e pede elicitação humana.",
            "Reverter para o último ready checkpoint — `forge undo`",
            "Se o downgrade foi acidental.",
            "Baixar strictness — `forge reconfigure → readiness-strictness=lean`",
            "Quando partial é aceitável pro tipo de feature (discovery).",
        ),
    )


if __name__ == "__main__":
    sys.exit(run_cli(__doc__ or "", validate))
