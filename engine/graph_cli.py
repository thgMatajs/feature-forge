"""`forge graph` — read-only query menu over the project knowledge graph.

Each menu item maps to one of the canonical Q1–Q10 queries documented in
`docs/schemas/graph.md`. The handler only collects arguments
interactively, invokes `engine.graph.queries.*`, and renders the result
via `engine.ui.tree.render_tree` or `engine.ui.renderer.box`.

Strictly read-only. Graph rebuilds belong to `forge reconfigure`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from engine.graph import queries as gq
from engine.ui import question, renderer
from engine.ui.question import PromptAbortedError
from engine.ui.tree import render_tree
from engine.utils.paths import (
    ProjectRootNotFoundError,
    claude_dir,
    ensure_dir,
    find_project_root,
    graph_db_path,
)
from engine.utils.yaml_io import read_yaml_or_default, write_yaml
from engine.utils.checkpoint_io import (
    clear_checkpoint as _clear_checkpoint_io,
    load_yaml_checkpoint as _load_yaml_checkpoint_io,
    save_yaml_checkpoint as _save_yaml_checkpoint_io,
)
from engine.utils.iso import utc_now_iso as _utc_now_iso_shared


# ── Checkpoint (DRIFT-1 W2.T3b — intent-resume, outcome C) ───────────────────
#
# Per the T3a audit (.planning/drift-1/checkpoint-audit.json,
# action="add-new", reuse_path="init-pattern"), graph_cli needs a
# checkpoint so the host can pause at any of the 7 interactive callsites
# (menu ``ask`` + 6 handler-level ``ask_text``/``ask`` invocations) and
# re-invoke cleanly. Mirrors ``_InitCheckpoint`` at
# ``engine/init.py:100-108`` — per-subcommand dataclass, no import from
# ``engine.qa.checkpoint`` (Decision 22 + outcome C lock-in).
#
# Refs:
#   - docs/superpowers/specs/drift-1-intent-protocol.md §3, §5, §8
#   - engine/init.py:100-108 (canonical template)


@dataclass
class _GraphCliCheckpoint:
    """State serialized before each ``question.ask*`` call in ``graph_cli.run``.

    Carries ``handler_key`` (a/b/c/.../17) so re-invocacao consegue
    saltar direto pra branch correta sem re-perguntar o menu. ``step``
    distingue entre o ``ask`` inicial do menu e o prompt do handler
    selecionado (ex.: ``step-menu`` vs ``step-handler:similar``).
    """

    step: str
    at: str
    project_root: str
    intent_id: str | None = None
    handler_key: str | None = None


def _graph_cli_checkpoint_path(project_root: Path) -> Path:
    return claude_dir(project_root) / ".graph-cli-checkpoint.yaml"


# Os 4 helpers abaixo são thin shims sobre ``engine.utils.checkpoint_io`` +
# ``engine.utils.iso`` — consolidação dos 30 duplicates + 10 cópias de
# ``_utc_now_iso_*`` apontada pelos findings #5 e #21 do master review do
# PR #11. Os nomes ``_save_graph_cli_checkpoint`` etc. permanecem como API
# privada do módulo para preservar os contracts dos testes em
# ``tests/unit/test_engine_graph_cli_resume.py`` (Mandamento #2 — verde).


def _save_graph_cli_checkpoint(cp: _GraphCliCheckpoint) -> None:
    """Persist the graph_cli checkpoint atomically."""
    _save_yaml_checkpoint_io(
        _graph_cli_checkpoint_path(Path(cp.project_root)),
        {
            "schema-version": 1,
            "step": cp.step,
            "at": cp.at,
            "project-root": cp.project_root,
            "intent-id": cp.intent_id,
            "handler-key": cp.handler_key,
        },
    )


def _load_graph_cli_checkpoint(project_root: Path) -> dict[str, Any] | None:
    """Read the graph_cli checkpoint, returning ``None`` when absent."""
    return _load_yaml_checkpoint_io(_graph_cli_checkpoint_path(project_root))


def _clear_graph_cli_checkpoint(project_root: Path) -> None:
    """Remove the checkpoint — best-effort; silent on OSError (idempotent)."""
    _clear_checkpoint_io(_graph_cli_checkpoint_path(project_root))


def _utc_now_iso_graph_cli() -> str:
    """ISO-8601 UTC timestamp — thin shim sobre ``engine.utils.iso``."""
    return _utc_now_iso_shared()


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


# ── Non-interactive JSON mode (Task 3, graph-ia-evolution AC-3) ─────────────
#
# ``forge graph --json <query> [args...]`` emite JSON em stdout sem ativar
# o menu interactivo. Aliases aceitos:
#   - Numeric key: ``1`` .. ``17``, ``r``
#   - Short prefix: ``q1`` .. ``q17``, ``qr``
#   - Label textual: ``orphan-files``, ``blast-radius``, ``symbols``, etc.
#
# Refs:
#   - docs/superpowers/specs/2026-06-12-graph-ia-evolution.md §AC-3
#   - docs/superpowers/plans/2026-06-12-graph-ia-evolution.md Task 3


_JSON_USAGE = (
    "Uso: forge graph --json <query> [args...]\n"
    "  Aliases: q1..q17, r, ou numeric 1..17, ou label (e.g. orphan-files).\n"
    "  Exemplos:\n"
    "    forge graph --json q3                       # orphan-files\n"
    "    forge graph --json q2 path/to/File.kt       # blast-radius\n"
    "    forge graph --json symbols :feature:auth    # Q4 por modulo\n"
    "    forge graph --json r                        # reuse-findings combined\n"
)


def _resolve_json_query_key(query_or_key: str) -> str | None:
    """Map any alias/label/numeric to canonical ``_HANDLERS`` key.

    Returns ``None`` when nothing matches.
    """
    key = query_or_key.strip().lower()

    # Strip optional ``q`` prefix on numeric/r keys: q1..q17, qr → 1..17, r
    if key.startswith("q") and len(key) > 1:
        candidate = key[1:]
        if candidate in _HANDLERS:
            return candidate

    # Direct numeric or ``r``
    if key in _HANDLERS:
        return key

    # Label match (case-insensitive against the label in _HANDLERS values)
    for k, (label, _fn) in _HANDLERS.items():
        if label.lower() == key:
            return k

    return None


def _run_json_query(
    project_root: Path,
    key: str,
    args: list[str],
) -> int:
    """Execute the resolved query and dump JSON to stdout.

    Uses the canonical ``gq.*`` functions (same as the interactive
    ``_q_*`` handlers) but bypasses ``_render_result`` and serializes
    the return value via ``json.dumps``. Each ``gq.*`` already returns
    JSON-friendly structures (list/dict of primitives + Path); ``default=str``
    handles Path coercion uniformly.

    Args:
        project_root: project root (validated upstream).
        key: canonical key in ``_HANDLERS`` (``1``..``17`` or ``r``).
        args: positional CLI args after the query identifier.

    Returns:
        ``0`` on success, ``1`` on handler failure or missing required arg.
    """
    import json as _json

    def _missing_arg(arg_name: str, query_label: str) -> int:
        sys.stderr.write(
            f"forge graph --json: {query_label} requer argumento "
            f"'{arg_name}' em modo non-interactive.\n"
        )
        return 1

    try:
        if key == "1":
            if not args:
                return _missing_arg("slug", "similar-features")
            result: Any = gq.find_similar_features(project_root, args[0])
        elif key == "2":
            if not args:
                return _missing_arg("file...", "blast-radius")
            paths = [Path(a) for a in args]
            result = gq.blast_radius(project_root, paths)
        elif key == "3":
            result = [str(p) for p in gq.find_orphan_files(project_root)]
        elif key == "4":
            if not args:
                return _missing_arg("module", "symbols")
            result = gq.find_symbols_in_module(project_root, args[0])
        elif key == "5":
            if not args:
                return _missing_arg("slug", "ds-used-in")
            result = gq.find_ds_components_used_in(project_root, args[0])
        elif key == "6":
            if not args:
                return _missing_arg("slug", "i18n-used-in")
            result = gq.find_i18n_keys_used_in(project_root, args[0])
        elif key == "7":
            if not args:
                return _missing_arg("slug", "routes")
            result = gq.find_routes_in_feature(project_root, args[0])
        elif key == "8":
            if not args:
                return _missing_arg("class", "di-deps")
            result = gq.find_di_dependencies(project_root, args[0])
        elif key == "9":
            if not args:
                return _missing_arg("file", "tests-for")
            result = [str(p) for p in gq.find_tests_covering_file(project_root, Path(args[0]))]
        elif key == "10":
            if not args:
                return _missing_arg("slug", "commits")
            result = gq.commits_touching_feature(project_root, args[0])
        elif key == "11":
            # entity_types: vazio → busca generica em /util/, /extensions/, /core/
            entities = [a.strip() for a in args if a.strip()]
            result = gq.find_reusable_helpers(project_root, entities)
        elif key == "12":
            result = gq.find_duplicates_within_module(project_root)
        elif key == "13":
            result = gq.find_duplicates_cross_module(project_root)
        elif key == "14":
            result = gq.find_kmp_migration_candidates(project_root)
        elif key == "15":
            result = gq.find_near_duplicates(project_root)
        elif key == "16":
            result = gq.find_redundant_platform_specific(project_root)
        elif key == "17":
            result = gq.find_duplicate_ts_helpers(project_root)
        elif key == "r":
            result = gq.list_reuse_findings(project_root)
        else:  # pragma: no cover — defensivo; _resolve_json_query_key filtra antes
            sys.stderr.write(f"forge graph --json: chave nao mapeada: {key!r}\n")
            return 1
    except Exception as exc:
        # Erro de runtime no handler — emite JSON-friendly error em stderr +
        # exit 1. stdout fica limpo pra consumers (Claude Code, scripts) nao
        # confundirem com payload valido.
        sys.stderr.write(f"forge graph --json: query falhou — {exc}\n")
        return 1

    # ``default=str`` coage Path e qualquer objeto nao-serializavel pra string.
    print(_json.dumps(result, indent=2, default=str))
    return 0


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

    Non-interactive flag (Task 3, graph-ia-evolution AC-3):
      ``forge graph --json <query> [args...]`` — emit JSON to stdout without
      ever prompting. Aliases: ``q1``..``q17``, ``r``, numeric ``1``..``17``,
      or labels (``orphan-files``, ``symbols``, etc.).
    """
    try:
        project_root = find_project_root()
    except ProjectRootNotFoundError as exc:
        sys.stderr.write(f"forge graph: {exc}\n")
        return 2

    if argv and argv[0] == "detect-incremental":
        return _run_detect_incremental(project_root, argv[1:])

    # --json non-interactive path (AC-3). Parsed BEFORE the interactive
    # guards so that a missing graph.db still fails with the canonical
    # message — keeps UX consistent between the two modes.
    if argv and argv[0] == "--json":
        if len(argv) < 2:
            sys.stderr.write(_JSON_USAGE)
            return 1
        if not graph_db_path(project_root).exists():
            sys.stderr.write(
                "forge graph --json: graph.db nao encontrado. Rode "
                "`forge reconfigure` → 'rebuild graph' antes.\n"
            )
            return 1
        key = _resolve_json_query_key(argv[1])
        if key is None:
            sys.stderr.write(
                f"forge graph --json: unknown query {argv[1]!r}. "
                f"Use q1..q17, r, ou label (e.g. symbols, orphan-files).\n"
            )
            return 1
        return _run_json_query(project_root, key, argv[2:])

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

    # DRIFT-1 W2.T3b — persist checkpoint with the deterministic intent-id
    # for the menu ask BEFORE invoking ``question.ask``. On exit-2 +
    # re-invoke, ``question.ask`` finds the matching forge-response.json
    # and returns the value without re-prompting. Outcome C — per-subcommand
    # dataclass, no import from ``engine.qa.checkpoint``.
    _save_graph_cli_checkpoint(
        _GraphCliCheckpoint(
            step="step-menu",
            at=_utc_now_iso_graph_cli(),
            project_root=str(project_root),
            intent_id=question.stable_intent_id(
                "ask",
                "Qual query?",
                options,
                extra={
                    "default": "3",
                    "min-selected": None,
                    "validator-hint": None,
                },
            ),
            handler_key=None,
        )
    )

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
        # DRIFT-1 W2.T3b — clear intent-resume checkpoint on clean completion.
        _clear_graph_cli_checkpoint(project_root)
        return 0

    handler_label, handler = _HANDLERS[choice]
    # DRIFT-1 W2.T3b — atualiza checkpoint pra cobrir o prompt do handler
    # antes de invoca-lo. handler_key fica registrado pra audit/forensics
    # quando o handler envolve ask_text/ask interno; o intent-id especifico
    # do prompt fica dentro do handler (cada um tem prompt distinto e
    # stable_intent_id e calculado pelo proprio question.ask*). Outcome C
    # — sem refator dos handlers individuais (Mandamento #4 / scope).
    _save_graph_cli_checkpoint(
        _GraphCliCheckpoint(
            step=f"step-handler:{handler_label}",
            at=_utc_now_iso_graph_cli(),
            project_root=str(project_root),
            intent_id=None,
            handler_key=choice,
        )
    )
    try:
        handler(project_root)
    except PromptAbortedError:
        renderer.write("  cancelado.")
        # Pause na pergunta do handler — invalid response branches preservam
        # checkpoint per SPEC §3, mas user pause e clean exit. Limpamos
        # checkpoint pra nao confundir re-invocacao seguinte.
        _clear_graph_cli_checkpoint(project_root)
        return 130
    except Exception as exc:
        sys.stderr.write(f"forge graph: query falhou — {exc}\n")
        # Hard failure no handler — clean exit, libera checkpoint. SPEC §3
        # forensic preservation aplica-se a invalid-response branches no
        # question.ask* (ValueError), nao a falhas internas do handler.
        _clear_graph_cli_checkpoint(project_root)
        return 1

    # DRIFT-1 W2.T3b — clear intent-resume checkpoint on clean completion.
    _clear_graph_cli_checkpoint(project_root)
    return 0


__all__ = ["run"]
