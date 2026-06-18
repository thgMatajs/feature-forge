#!/usr/bin/env python3
"""check_unfilled_placeholders.py — gate AI-first: artefatos de feature não
podem carregar `{{...}}` crus.

Um template não-preenchido passando como 'verificado' (PLACEHOLDER-VERIFY) é
detection-failure. Escaneia os artefatos staged DENTRO do dir da feature
(.md/.yaml/.yml/.json) procurando tokens `{{token}}` não-substituídos. Tokens
em arquivos-fonte de `templates/` (não-preenchidos por design) NÃO contam — só
artefatos da feature, que `_render_template` deveria ter preenchido.

Compõe a infra existente (`_common` + `_diff` + `engine.utils.paths.feature_path`)
— sem helper de scan novo (reuse-first, Mandamento #3).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from _common import make_paths, result_fail, result_pass, run_cli
from _diff import git_staged_files

# A-014 pattern: o path patch precisa rodar ANTES de qualquer `from engine....`.
sys.path.insert(0, str(Path(__file__).parent.parent))  # noqa: E402

from engine.memory.l1 import current_subtype  # noqa: E402
from engine.utils.paths import feature_path  # noqa: E402

_PLACEHOLDER_RE = re.compile(r"\{\{\s*[\w.\-]+\s*\}\}")
_ARTIFACT_SUFFIXES = {".md", ".yaml", ".yml", ".json"}


def _resolve_slug(kwargs: dict[str, Any]) -> str | None:
    scope = kwargs.get("scope") or "inferred"
    given = kwargs.get("id")
    if scope == "feature" and given:
        return given
    if given and not given.upper().startswith("TASK-"):
        return given
    return None


def validate(project_root: Path, **kwargs: Any) -> dict[str, Any]:
    slug = _resolve_slug(kwargs)
    if not slug:
        return result_pass("nenhum slug de feature — placeholder scan pulado")
    subtype = current_subtype(slug, project_root)
    f_root = feature_path(project_root, slug, subtype=subtype)
    staged = git_staged_files(project_root, extensions=_ARTIFACT_SUFFIXES)
    hits: dict[str, str] = {}
    for f in staged:
        try:
            f.relative_to(f_root)
        except ValueError:
            continue  # fora do dir da feature — ignora
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        m = _PLACEHOLDER_RE.search(text)
        if m:
            rel = str(f.relative_to(project_root))
            hits.setdefault(rel, m.group(0))
    if not hits:
        return result_pass(f"sem placeholders crus em {slug}")
    where = "; ".join(f"{p} → {tok}" for p, tok in list(hits.items())[:5])
    return result_fail(
        f"{len(hits)} artefato(s) com placeholder não-preenchido em {slug}",
        what_failed="; ".join(tok for tok in list(hits.values())[:5]),
        where=where,
        why=[
            "Template não-preenchido não pode passar como 'verificado'.",
            "PLACEHOLDER-VERIFY: o host deve preencher os {{...}} entre as waves.",
        ],
        paths=make_paths(
            "Preencher os campos restantes — `forge plan <slug>` (continua de onde parou)",
            "A wave do plan re-abre o artefato pra completar.",
            "Reverter o artefato cru — `git restore --staged <file>`",
            "Se foi staged por engano antes de preencher.",
            "Escalar pro user se o campo exige decisão de produto",
            "Quando o valor não é derivável do contexto.",
        ),
    )


if __name__ == "__main__":
    raise SystemExit(run_cli(__doc__ or "", validate))
