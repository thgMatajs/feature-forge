"""`forge graph` — read-only query menu over the project knowledge graph.

Each menu item maps to one of the canonical Q1–Q10 queries documented in
`docs/schemas/graph.md`. The handler only collects arguments
interactively, invokes `engine.graph.queries.*`, and renders the result
via `engine.ui.tree.render_tree` or `engine.ui.renderer.box`.

Strictly read-only. Graph rebuilds belong to `forge reconfigure`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

from engine.graph import queries as gq
from engine.ui import question, renderer
from engine.ui.question import PromptAbortedError
from engine.ui.tree import render_tree
from engine.utils.paths import (
    ProjectRootNotFoundError,
    find_project_root,
    graph_db_path,
)


def _slug_validator(raw: str) -> bool:
    return raw.replace("-", "").replace("_", "").isalnum() and raw[:1].isalpha()


def _render_result(label: str, payload: Any) -> None:
    renderer.write("")
    renderer.write(renderer.section_header(label, width=78))
    renderer.write("")
    if not payload:
        renderer.write(renderer.dim("  (vazio)"))
        return
    if isinstance(payload, (list, dict)):
        renderer.write(render_tree(payload))
    else:
        renderer.write(f"  {payload}")
    renderer.write("")


def _ask_slug(prompt: str) -> str:
    return question.ask_text(
        prompt,
        validator=_slug_validator,
        validator_hint="kebab-case (ex.: lembrete-rega).",
    )


def _ask_paths(prompt: str) -> list[Path]:
    raw = question.ask_text(
        prompt
        + "  (separe múltiplos com vírgula, ex.: shared/feature/x/Foo.kt,…)"
    )
    return [Path(p.strip()) for p in raw.split(",") if p.strip()]


# ── Query dispatchers ───────────────────────────────────────────────────────


def _q_similar(project_root: Path) -> None:
    slug = _ask_slug("Slug da feature alvo:")
    rows = gq.find_similar_features(project_root, slug)
    _render_result(f"similar-features({slug})", rows)


def _q_blast(project_root: Path) -> None:
    paths = _ask_paths("Arquivos:")
    if not paths:
        renderer.write(renderer.colored("  Nenhum arquivo informado.", "yellow"))
        return
    result = gq.blast_radius(project_root, paths)
    _render_result(f"blast-radius({len(paths)} arquivo(s))", result)


def _q_orphans(project_root: Path) -> None:
    orphans = gq.find_orphan_files(project_root)
    _render_result(
        "orphan-files",
        [str(p) for p in orphans] if orphans else [],
    )


def _q_symbols(project_root: Path) -> None:
    module = question.ask_text("Nome do módulo Gradle (ex.: :feature:auth):")
    rows = gq.find_symbols_in_module(project_root, module)
    _render_result(f"symbols({module})", rows)


def _q_ds(project_root: Path) -> None:
    slug = _ask_slug("Slug da feature:")
    rows = gq.find_ds_components_used_in(project_root, slug)
    _render_result(f"ds-used-in({slug})", rows)


def _q_i18n(project_root: Path) -> None:
    slug = _ask_slug("Slug da feature:")
    rows = gq.find_i18n_keys_used_in(project_root, slug)
    _render_result(f"i18n-used-in({slug})", rows)


def _q_routes(project_root: Path) -> None:
    slug = _ask_slug("Slug da feature:")
    rows = gq.find_routes_in_feature(project_root, slug)
    _render_result(f"routes({slug})", rows)


def _q_di(project_root: Path) -> None:
    cls = question.ask_text("Nome da classe (ex.: AuthRepositoryImpl):")
    rows = gq.find_di_dependencies(project_root, cls)
    _render_result(f"di-deps({cls})", rows)


def _q_tests(project_root: Path) -> None:
    raw = question.ask_text("Caminho do arquivo de produção:")
    rows = gq.find_tests_covering_file(project_root, Path(raw))
    _render_result(f"tests-for({raw})", [str(p) for p in rows])


def _q_commits(project_root: Path) -> None:
    slug = _ask_slug("Slug da feature:")
    rows = gq.commits_touching_feature(project_root, slug)
    _render_result(f"commits({slug})", rows)


_HANDLERS: dict[str, tuple[str, Callable[[Path], None]]] = {
    "1":  ("similar-features",  _q_similar),
    "2":  ("blast-radius",      _q_blast),
    "3":  ("orphan-files",      _q_orphans),
    "4":  ("symbols",           _q_symbols),
    "5":  ("ds-used-in",        _q_ds),
    "6":  ("i18n-used-in",      _q_i18n),
    "7":  ("routes",            _q_routes),
    "8":  ("di-deps",           _q_di),
    "9":  ("tests-for",         _q_tests),
    "10": ("commits",           _q_commits),
}


def run(argv: list[str]) -> int:
    """Interactive query menu — Q1..Q10, read-only."""
    _ = argv

    try:
        project_root = find_project_root()
    except ProjectRootNotFoundError as exc:
        sys.stderr.write(f"forge graph: {exc}\n")
        return 2

    if not graph_db_path(project_root).exists():
        renderer.write(renderer.colored(
            "  graph.db não encontrado. Rode `forge reconfigure` → "
            "\"rebuild graph\" antes.",
            "yellow",
        ))
        return 1

    renderer.write(renderer.bold("forge graph — query:"))
    options: dict[str, str] = {
        "1":  "similar-features {slug}     (Q1)",
        "2":  "blast-radius {file...}     (Q2)",
        "3":  "orphan-files               (Q3)",
        "4":  "symbols {module}           (Q4)",
        "5":  "ds-used-in {slug}          (Q5)",
        "6":  "i18n-used-in {slug}        (Q6)",
        "7":  "routes {slug}              (Q7)",
        "8":  "di-deps {class}            (Q8)",
        "9":  "tests-for {file}           (Q9)",
        "10": "commits {slug}             (Q10)",
        "c":  "cancelar",
    }

    try:
        choice = question.ask(
            "Qual query?",
            options,
            default="3",
            allow_pause=True,
        )
    except PromptAbortedError:
        return 130

    if choice == "c":
        return 0

    _, handler = _HANDLERS[choice]
    try:
        handler(project_root)
    except PromptAbortedError:
        renderer.write("  cancelado.")
        return 130
    except Exception as exc:
        sys.stderr.write(f"forge graph: query falhou — {exc}\n")
        return 1

    return 0


__all__ = ["run"]
