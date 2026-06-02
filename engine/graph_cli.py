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


def _q_reusable(project_root: Path) -> None:
    raw = question.ask_text(
        "Tipos de entidade (separe com vírgula, ex.: Bonsai, Task). "
        "Deixe vazio pra buscar só em /util/, /extensions/, /core/.",
        default="",
    )
    entities = [e.strip() for e in raw.split(",") if e.strip()]
    rows = gq.find_reusable_helpers(project_root, entities)
    label = (
        f"reusable-helpers({', '.join(entities)})"
        if entities
        else "reusable-helpers(utility paths only)"
    )
    _render_result(label, rows)


def _q_dup_within(project_root: Path) -> None:
    rows = gq.find_duplicates_within_module(project_root)
    _render_result("dup-within-module (Q12)", rows)


def _q_dup_cross(project_root: Path) -> None:
    rows = gq.find_duplicates_cross_module(project_root)
    _render_result("dup-cross-module (Q13)", rows)


def _q_kmp_migration(project_root: Path) -> None:
    rows = gq.find_kmp_migration_candidates(project_root)
    _render_result("kmp-migration (Q14)", rows)


def _q_near_dup(project_root: Path) -> None:
    rows = gq.find_near_duplicates(project_root)
    _render_result("near-duplicates (Q15)", rows)


def _q_redundant_platform(project_root: Path) -> None:
    rows = gq.find_redundant_platform_specific(project_root)
    _render_result("redundant-platform (Q16)", rows)


def _q_dup_ts(project_root: Path) -> None:
    rows = gq.find_duplicate_ts_helpers(project_root)
    _render_result("dup-ts-helpers (Q17)", rows)


def _q_reuse_findings_all(project_root: Path) -> None:
    rows = gq.list_reuse_findings(project_root)
    _render_result("reuse-findings (all categories)", rows)


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
    "11": ("reusable-helpers",  _q_reusable),
    "12": ("dup-within-module", _q_dup_within),
    "13": ("dup-cross-module",  _q_dup_cross),
    "14": ("kmp-migration",     _q_kmp_migration),
    "15": ("near-duplicates",   _q_near_dup),
    "16": ("redundant-platform", _q_redundant_platform),
    "17": ("dup-ts-helpers",    _q_dup_ts),
    "r":  ("reuse-findings",    _q_reuse_findings_all),
}


def _run_detect_incremental(project_root: Path, file_args: list[str]) -> int:
    """Non-interactive entrypoint used by the post-edit hook.

    Args:
        project_root: project root with .claude/graph.db
        file_args: edited file paths (relative or absolute).

    Prints any reuse_findings that include the edited files. Always exits 0
    — the hook must not fail the developer's edit, even on internal errors.
    """
    from engine.graph.incremental import detect_after_update

    if not file_args:
        return 0

    paths: list[Path] = []
    for arg in file_args:
        candidate = Path(arg)
        if not candidate.is_absolute():
            candidate = (project_root / candidate).resolve()
        paths.append(candidate)

    try:
        findings = detect_after_update(project_root, paths)
    except Exception as exc:
        sys.stderr.write(f"forge graph detect-incremental: {exc}\n")
        return 0

    if not findings:
        return 0

    renderer.write("")
    renderer.write(renderer.bold(
        f"⚠ {len(findings)} reuse-intelligence finding(s) touching edited files:"
    ))
    for f in findings:
        receiver = f["receiver_type"] or "(top-level)"
        renderer.write(
            f"  · [{f['category']}] {receiver}.{f['symbol_name']} "
            f"(conf={f['confidence']:.2f}) → {f['suggested_target']}"
        )
        for loc in f["locations"][:3]:
            renderer.write(f"      {loc['path']}:{loc['line_start']}")
    renderer.write(renderer.dim("  Run `forge evolve` to review proposals."))
    renderer.write("")
    return 0


def run(argv: list[str]) -> int:
    """Interactive query menu — Q1..Q17, read-only.

    Non-interactive subcommand:
      ``forge graph detect-incremental <file>...`` — used by post-edit hooks.
    """
    try:
        project_root = find_project_root()
    except ProjectRootNotFoundError as exc:
        sys.stderr.write(f"forge graph: {exc}\n")
        return 2

    if argv and argv[0] == "detect-incremental":
        return _run_detect_incremental(project_root, argv[1:])

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
        "11": "reusable-helpers {types}   (Q11)",
        "12": "dup-within-module          (Q12)",
        "13": "dup-cross-module           (Q13)",
        "14": "kmp-migration              (Q14)",
        "15": "near-duplicates            (Q15)",
        "16": "redundant-platform         (Q16)",
        "17": "dup-ts-helpers             (Q17)",
        "r":  "reuse-findings (combined)",
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
