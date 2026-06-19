#!/usr/bin/env python3
"""check_unfilled_placeholders.py — gate AI-first: artefatos de feature não
podem carregar `{{...}}` crus.

Um template não-preenchido passando como 'verificado' (PLACEHOLDER-VERIFY) é
detection-failure. Escaneia os artefatos DENTRO do dir da feature
(.md/.yaml/.yml/.json) procurando tokens `{{token}}` não-substituídos. Tokens
em arquivos-fonte de `templates/` (não-preenchidos por design) NÃO contam — só
artefatos da feature, que `_render_template` deveria ter preenchido.

C-43-B (PR22-R-001): o scan varre o FILESYSTEM do dir da feature
(`f_root.rglob`), não `git_staged_files`. Os sibling validators do cascade
rodam pré-staging (hook pre-commit roda ANTES do `git add` em vários fluxos),
então depender de staged-files deixava o gate inerte. O escopo `--scope`/`--id`
é threadado pelo `engine.verify._invoke_validator` (parte A do C-43).

C-52: tokens escapados deliberadamente são ignorados — `{{{token}}}` (triple-
brace literal) ou linha marcada com `<!-- placeholder-ok -->` logo acima.

Compõe a infra existente (`_common` + `engine.utils.paths.feature_path`) — sem
helper de scan novo (reuse-first, Mandamento #3).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from _common import make_paths, result_fail, result_pass, run_cli

# A-014 pattern: o path patch precisa rodar ANTES de qualquer `from engine....`.
sys.path.insert(0, str(Path(__file__).parent.parent))  # noqa: E402

from engine.memory.l1 import current_subtype  # noqa: E402
from engine.utils.paths import feature_path  # noqa: E402

# Token de 2 chaves. O lookbehind `(?<!\{)` exclui a forma escapada de 3 chaves
# `{{{token}}}` (C-52 — literal intencional): o `{{token}}` interno tem `{` à
# esquerda e é descartado. WR-01: NÃO usar lookahead `(?!\})` no fechamento —
# ele fazia tokens crus colados a `}` escaparem a detecção (`{{val}}}` malformado
# ou `{"x": {{val}}}` dentro de JSON). O lookbehind sozinho já isola o escape
# deliberado sem criar essa janela de false-negative à direita.
_PLACEHOLDER_RE = re.compile(r"(?<!\{)\{\{\s*[\w.\-]+\s*\}\}")
# C-45: slug-id de task é estritamente `TASK-<dígitos>`. Uma feature slugada
# `task-foo` (kebab) NÃO casa — então não é mis-classificada como task id.
_TASK_ID_RE = re.compile(r"^TASK-\d+$", re.IGNORECASE)
_ARTIFACT_SUFFIXES = {".md", ".yaml", ".yml", ".json"}
_ESCAPE_MARKER = "placeholder-ok"


def _resolve_slug(kwargs: dict[str, Any]) -> str | None:
    scope = kwargs.get("scope") or "inferred"
    given = kwargs.get("id")
    if scope == "feature" and given:
        return given
    # C-45: só descarta quando o id é estritamente um TASK-<n>. Uma feature
    # cujo slug começa com `task-` (kebab) segue sendo tratada como slug.
    if given and not _TASK_ID_RE.match(given.strip()):
        return given
    return None


def _has_unescaped_placeholder(text: str) -> str | None:
    """Retorna o primeiro token cru não-escapado, ou ``None``.

    Linhas precedidas por `<!-- placeholder-ok -->` (na mesma linha ou na linha
    imediatamente anterior) são puladas — escape deliberado (C-52).
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = _PLACEHOLDER_RE.search(line)
        if not m:
            continue
        if _ESCAPE_MARKER in line.lower():
            continue
        if i > 0 and _ESCAPE_MARKER in lines[i - 1].lower():
            continue
        return m.group(0)
    return None


def validate(project_root: Path, **kwargs: Any) -> dict[str, Any]:
    slug = _resolve_slug(kwargs)
    if not slug:
        return result_pass("nenhum slug de feature — placeholder scan pulado")
    subtype = current_subtype(slug, project_root)
    f_root = feature_path(project_root, slug, subtype=subtype)
    hits: dict[str, str] = {}
    if f_root.is_dir():
        for f in sorted(f_root.rglob("*")):
            if not f.is_file() or f.suffix not in _ARTIFACT_SUFFIXES:
                continue
            try:
                text = f.read_text(encoding="utf-8")
            except OSError:
                continue
            tok = _has_unescaped_placeholder(text)
            if tok:
                rel = str(f.relative_to(project_root))
                hits.setdefault(rel, tok)
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
