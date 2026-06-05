#!/usr/bin/env python3
"""check_cyclomatic_complexity.py — multi-language CC gate.

Runs in two contexts (per design spec §2):

1. `forge verify` cascade — feature-wide gate, after check_no_invented_behavior.
2. `forge implement` per-task — between Review and Commit, blocks the commit
   when a staged function exceeds its threshold (or when a modified function
   got worse than HEAD).

Threshold precedence (per design spec §2 + helpers in _common):
    card cc-gate-override > workflow-config cc-gate > DEFAULTS_CC

On fail, emits the canonical 3-paths block (see _common.format_three_paths_message).
Override-justify: `CC-OVERRIDE: <file>:<func> cc=<N> — <reason>` in the commit
body silences a specific function for THAT commit only — no persistent
whitelist (auditable via `git log --grep='CC-OVERRIDE'`).
"""

from __future__ import annotations

import json  # noqa: F401  — used by parser tasks (T4/T5)
import re  # noqa: F401  — used by override-detect task (T7)
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from _common import (
    format_three_paths_message,  # noqa: F401  — wired in T8 validate()
    gate_threshold_lookup,  # noqa: F401  — wired in T8 validate()
    make_paths,  # noqa: F401  — wired in T8 validate()
    result_fail,  # noqa: F401  — wired in T8 validate()
    result_pass,
    result_warn,  # noqa: F401  — wired in T6/T8
    run_cli,
)
from _diff import (
    DiffHunk,  # noqa: F401  — re-exported for back-compat in tests
    classify_range_against_hunks,
    extract_diff_hunks,
    git_staged_files,
    read_commit_body,
)
from _gate_infra import (
    DispatchResult,
    apply_overrides as _gate_apply_overrides,
    check_tool_available,  # noqa: F401  — re-exported for back-compat in tests
    dispatch_native_tool,
    parse_overrides as _gate_parse_overrides,
    render_config_with_placeholders,  # noqa: F401  — re-exported (cmd_builders use it indirectly via dispatch_native_tool)
)

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.utils.paths import feature_dir  # noqa: E402,F401  — wired in T8
from engine.utils.yaml_io import read_yaml_or_default  # noqa: E402,F401  — wired in T8


SUPPORTED_EXTENSIONS = {
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".swift": "swift",
    ".ts": "ts",
    ".tsx": "ts",
    ".py": "python",
}


@dataclass(frozen=True)
class CCResult:
    """Normalized cyclomatic-complexity result, tool-agnostic.

    Emitted by the per-tool parsers (_parse_detekt, _parse_swiftlint,
    _parse_eslint, _parse_radon) and consumed by the rule-application
    step (run + classify_range_against_hunks).
    """

    file: str           # path relative to project root
    function: str       # name + signature when available
    line_start: int     # 1-indexed
    line_end: int
    cc: int             # CC computed on the staged blob
    language: str       # "kotlin" | "swift" | "ts" | "python"
    status: str         # "new" | "modified" | "unchanged"
    cc_before: Optional[int]  # None when status == "new" or unknown


# ── Tool output parsers ──────────────────────────────────────────────────────
#
# Each parser converts the tool's native JSON output into a list of CCResult.
# Tool crash / non-JSON → return [] so the orchestrator can emit result_warn
# and keep the cascade alive (per spec §3 trust-but-verify).

_DETEKT_FUNC_RE = re.compile(r"function\s+(\w+)\s+appears", re.IGNORECASE)
_SWIFTLINT_FUNC_RE = re.compile(r"\bFunction\s+(\w+)\s*\(", re.IGNORECASE)


def _parse_detekt(raw: str) -> list[CCResult]:
    """Parse Detekt JSON report (CyclomaticComplexMethod issues only)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    issues = data.get("issues") if isinstance(data, dict) else None
    if not isinstance(issues, list):
        return []
    out: list[CCResult] = []
    for it in issues:
        if not isinstance(it, dict):
            continue
        if it.get("ruleName") != "CyclomaticComplexMethod":
            continue
        loc = it.get("location") or {}
        pos = loc.get("position") or {}
        end_pos = loc.get("endPosition") or {}
        message = str(it.get("message") or "")
        match = _DETEKT_FUNC_RE.search(message)
        func_name = match.group(1) if match else "<unknown>"
        try:
            cc_value = int((it.get("metric") or {}).get("value"))
        except (TypeError, ValueError):
            continue
        out.append(
            CCResult(
                file=str(loc.get("filePath") or ""),
                function=func_name,
                line_start=int(pos.get("line") or 0),
                line_end=int(end_pos.get("line") or pos.get("line") or 0),
                cc=cc_value,
                language="kotlin",
                status="unchanged",  # filled by orchestrator
                cc_before=None,
            )
        )
    return out


def _parse_swiftlint(raw: str) -> list[CCResult]:
    """Parse SwiftLint JSON report (cyclomatic_complexity rule only)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[CCResult] = []
    for it in data:
        if not isinstance(it, dict):
            continue
        if it.get("rule_id") != "cyclomatic_complexity":
            continue
        reason = str(it.get("reason") or "")
        match = _SWIFTLINT_FUNC_RE.search(reason)
        func_name = match.group(1) if match else "<unknown>"
        try:
            cc_value = int(it.get("complexity"))
        except (TypeError, ValueError):
            # SwiftLint older versions don't expose `complexity` — extract from reason
            tail = re.search(r"complexity is (\d+)", reason)
            if not tail:
                continue
            cc_value = int(tail.group(1))
        line_start = int(it.get("line") or 0)
        out.append(
            CCResult(
                file=str(it.get("file") or ""),
                function=func_name,
                line_start=line_start,
                line_end=line_start,  # SwiftLint doesn't emit end-line; orchestrator widens later
                cc=cc_value,
                language="swift",
                status="unchanged",
                cc_before=None,
            )
        )
    return out


_ESLINT_FUNC_RE = re.compile(r"['\"]?(\w+)['\"]?\s+has a complexity of (\d+)", re.IGNORECASE)


def _parse_eslint(raw: str, *, project_root: str) -> list[CCResult]:
    """Parse eslint --format json output (complexity rule only).

    eslint emits ``[{filePath, messages: [{ruleId, line, endLine, message}], ...}]``.
    The `complexity` rule message has the canonical shape
    ``Function 'name' has a complexity of N. Maximum allowed is M.``;
    we extract `name` + `N` via regex and discard the configured maximum
    (gate uses its own threshold table, not eslint's).

    Tool crash / non-JSON → ``[]`` so the orchestrator can emit
    ``result_warn`` and keep the cascade alive (spec §3 trust-but-verify).
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    root_prefix = project_root.rstrip("/") + "/"
    out: list[CCResult] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        file_abs = str(entry.get("filePath") or "")
        file_rel = (
            file_abs[len(root_prefix):] if file_abs.startswith(root_prefix) else file_abs
        )
        for msg in entry.get("messages") or []:
            if not isinstance(msg, dict):
                continue
            if msg.get("ruleId") != "complexity":
                continue
            text = str(msg.get("message") or "")
            match = _ESLINT_FUNC_RE.search(text)
            if not match:
                continue
            func_name = match.group(1)
            try:
                cc_value = int(match.group(2))
            except (TypeError, ValueError):
                continue
            out.append(
                CCResult(
                    file=file_rel,
                    function=func_name,
                    line_start=int(msg.get("line") or 0),
                    line_end=int(msg.get("endLine") or msg.get("line") or 0),
                    cc=cc_value,
                    language="ts",
                    status="unchanged",
                    cc_before=None,
                )
            )
    return out


def _parse_radon(raw: str) -> list[CCResult]:
    """Parse ``radon cc -j`` output (per-file → list of blocks).

    Shape: ``{file_path: [{type, name, lineno, endline, complexity, rank, classname?}, ...]}``.
    Gate counts only `type == "function"` entries — class-level aggregates
    are reported separately by radon and would double-count the methods
    they contain.

    Tool crash / non-JSON → ``[]`` (same robustness contract as the other
    parsers; spec §3 trust-but-verify).
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    out: list[CCResult] = []
    for file_path, blocks in data.items():
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "function":
                continue  # classes / methods aggregated separately
            try:
                cc_value = int(block.get("complexity"))
            except (TypeError, ValueError):
                continue
            out.append(
                CCResult(
                    file=str(file_path),
                    function=str(block.get("name") or "<unknown>"),
                    line_start=int(block.get("lineno") or 0),
                    line_end=int(block.get("endline") or block.get("lineno") or 0),
                    cc=cc_value,
                    language="python",
                    status="unchanged",
                    cc_before=None,
                )
            )
    return out


# Subsequent tasks (7–8) append: override, run().


# ── Tool dispatch ────────────────────────────────────────────────────────────
#
# Per-language invocation of the 4 native CC tools (Detekt/SwiftLint/eslint/Radon).
# Trust-but-verify de availability via shutil.which: tool missing → tool_found=False
# (caller emits result_warn, cascade segue alive — spec §3).
#
# Comandos exatos batem com docs/superpowers/specs/2026-06-03-cc-gate-design.md
# §3 tabela. Threshold passado via CLI args (não embutido em config).


_TOOL_BIN = {
    "kotlin": "detekt",
    "swift": "swiftlint",
    "ts": "eslint",
    "python": "radon",
}

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "engine" / "_cc_configs"


# ── Command builders (per-language cmd construction) ────────────────────────
#
# Cada cmd_builder recebe `(tool_bin, files, rendered_config_path)` e devolve
# o cmd final pro subprocess.run em `dispatch_native_tool`. Builders ficam
# aqui (CC-específicos pelas tools nativas que conhecem) enquanto o dispatch
# canônico vive em `_gate_infra`. Próximos gates definem seus próprios
# builders sem duplicar a lógica de subprocess / cleanup / error handling.


def _build_detekt_cmd(
    tool_bin: str, files: list[str], rendered_config: Optional[str]
) -> list[str]:
    """Detekt: --input vírgula-separado + --config (rendered) + --report json:-.

    Threshold é rendered dinamicamente no config (Detekt não aceita CLI
    override por regra). Spec §3 threshold-via-CLI honored via tmpfile render
    feito por `dispatch_native_tool` antes de chamar este builder.
    """
    return [
        tool_bin,
        "--input", ",".join(files),
        "--config", str(rendered_config),
        "--report", "json:-",
    ]


def _build_swiftlint_cmd(
    tool_bin: str, files: list[str], rendered_config: Optional[str]
) -> list[str]:
    """SwiftLint: `lint` subcomando + --reporter json + --config (rendered).

    Threshold rendered dinamicamente no config (SwiftLint não aceita CLI
    override per-rule). Spec §3 threshold-via-CLI honored via tmpfile render.
    """
    return [
        tool_bin, "lint",
        "--reporter", "json",
        "--config", str(rendered_config),
        *files,
    ]


def _build_eslint_cmd_factory(threshold: int) -> Callable[
    [str, list[str], Optional[str]], list[str]
]:
    """Factory para o cmd_builder do eslint (threshold via closure).

    eslint aceita threshold via `--rule` inline, então não precisa render de
    config (config_template fica None em `dispatch_native_tool`). Factory
    captura o threshold no scope da iteração de `_run_tools_for_staged`.
    """

    def _build(
        tool_bin: str, files: list[str], rendered_config: Optional[str]
    ) -> list[str]:
        return [
            tool_bin,
            "--no-eslintrc",
            "--rule", f'{{"complexity": ["error", {{"max": {threshold}}}]}}',
            "--format", "json",
            *files,
        ]

    return _build


def _build_radon_cmd(
    tool_bin: str, files: list[str], rendered_config: Optional[str]
) -> list[str]:
    """radon cc -j -n A: JSON output, rank mínimo "A" (mostra TODAS as funções).

    H2 regression guard — flag `-n F` antigo mascarava CC ∈ [11..40], o sweet
    spot do gate. Filtragem fina por threshold acontece no validator depois.
    Threshold via CLI não aplicável (radon não aceita override per-tool aqui),
    e gate filtra Python por threshold após parsing.
    """
    return [tool_bin, "cc", "-j", "-n", "A", *files]


# Subsequent tasks (7–8) append: override, run().


# ── Override-justify ─────────────────────────────────────────────────────────
#
# Single-line override declared in the commit body. Anchored to start-of-line
# (re.MULTILINE) so it can't be smuggled mid-sentence. The format is
# load-bearing — `.claude/rules/disciplines.md §1` references it directly.
#
# Parse + apply são generalizados em `_gate_infra.parse_overrides` /
# `_gate_infra.apply_overrides`. Esta seção mantém apenas a especialização CC
# (prefix + key_pattern + key fields + key_extractor + converter de `cc`).

_CC_OVERRIDE_PREFIX = "CC-OVERRIDE"
_CC_OVERRIDE_KEY_PATTERN = r"(?P<file>\S+):(?P<func>\S+)\s+cc=(?P<cc>\d+)"
_CC_OVERRIDE_KEY_FIELDS = ["file", "func"]
_CC_OVERRIDE_VALUE_CONVERTERS = {"cc": int}


def _cc_fail_key_extractor(fail: CCResult) -> tuple[str, str]:
    """Extrai a tupla (file, function) do CCResult — cover key do CC gate."""
    return (fail.file, fail.function)


def parse_overrides(
    commit_body: str,
    *,
    return_warnings: bool = False,
):
    """Thin CC-specific wrapper around `_gate_infra.parse_overrides`.

    Preserva o contrato do antigo `_parse_overrides`: dicts com
    ``{file, func, cc: int, reason}``. Generalização vive em
    `_gate_infra.parse_overrides` — esta wrapper fixa prefix/key_pattern/
    value_converters do CC gate pra manter callsites enxutos e tests legíveis.
    """
    return _gate_parse_overrides(
        commit_body,
        prefix=_CC_OVERRIDE_PREFIX,
        key_pattern=_CC_OVERRIDE_KEY_PATTERN,
        value_converters=_CC_OVERRIDE_VALUE_CONVERTERS,
        return_warnings=return_warnings,
    )


def apply_overrides(
    fails: list[CCResult],
    commit_body: str,
) -> tuple[list[CCResult], list[CCResult], list[str]]:
    """Thin CC-specific wrapper around `_gate_infra.apply_overrides`.

    Match key: ``(file, function)`` — cobre apenas o par declarado, sem
    wildcards. Cada override aplica-se a UM commit; auditoria via
    ``git log --grep='CC-OVERRIDE'``.

    Malformed-override warnings (linhas com prefix mas sem ``— razão``)
    sobem como terceiro elemento — preserva H4 do CC gate (warning emitido
    mesmo quando o gate passa).
    """
    return _gate_apply_overrides(
        fails,
        commit_body,
        prefix=_CC_OVERRIDE_PREFIX,
        key_pattern=_CC_OVERRIDE_KEY_PATTERN,
        fail_key_extractor=_cc_fail_key_extractor,
        override_key_fields=_CC_OVERRIDE_KEY_FIELDS,
        value_converters=_CC_OVERRIDE_VALUE_CONVERTERS,
    )


# ── Orchestrator ─────────────────────────────────────────────────────────────
#
# `validate(project_root, **kwargs)` é o main entry-point — chamado tanto pelo
# CLI runner (_common.run_cli quando o script roda standalone) quanto pelo
# cascade do engine (forge verify) e pelo per-task hook (forge implement).
#
# Pipeline (per design spec §2):
#   1. Lê workflow-config; short-circuit warn quando enabled=false.
#   2. Coleta staged files (git diff --cached --name-only) filtrados pelas
#      extensões suportadas (.kt .kts .swift .ts .tsx .py).
#   3. Aplica ignore-paths (defaults pra tests + entradas do workflow-config).
#   4. Resolve threshold por linguagem via gate_threshold_lookup (card override
#      > workflow-config > DEFAULTS_CC).
#   5. Extrai diff hunks pra classificar new/modified/unchanged.
#   6. Dispatch tool per linguagem (Detekt/SwiftLint/eslint/radon) numa única
#      invocação por batch. Tool missing/crash → warning, sem fail.
#   7. Classifica cada função encontrada via classify_range_against_hunks.
#   8. Aplica a regra: new → fail se cc > threshold; modified → fail se
#      cc_after > cc_before (delta-rule). unchanged → ignora.
#   9. Aplica CC-OVERRIDE silencing lendo o commit body.
#   10. Se sobrarem violations → emit result_fail com 3-paths block.
#   11. Senão → result_pass (ou result_warn se houve tool warnings).


_TEST_IGNORE_DEFAULTS = [
    r"(^|/)tests?/",
    r"(^|/)__tests__/",
    r"\.test\.(ts|tsx|js|jsx|kt|swift|py)$",
    r"_test\.(kt|swift|py)$",
]


def _load_active_cards(project_root: Path) -> list[dict[str, Any]]:
    """Read each active card's card.yaml (snapshot) e devolve lista de dicts.

    Active cards declarados em ``.claude/workflow-config.yaml`` sob
    ``cards.active``. Para cada entrada, lê ``.claude/cards/<name>/card.yaml``.
    Card file ausente → silenciosamente ignorado (não bloqueia o gate).
    """
    cfg_path = project_root / ".claude" / "workflow-config.yaml"
    config = read_yaml_or_default(cfg_path, {}) or {}
    cards_root = project_root / ".claude" / "cards"
    out: list[dict[str, Any]] = []
    cards_block = config.get("cards") if isinstance(config, dict) else None
    active_list = (cards_block or {}).get("active") if isinstance(cards_block, dict) else None
    for entry in active_list or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "")
        if not name:
            continue
        card_yaml = cards_root / name / "card.yaml"
        if card_yaml.is_file():
            out.append(read_yaml_or_default(card_yaml, {}) or {})
    return out


def _load_workflow_config(project_root: Path) -> dict[str, Any]:
    """Read ``.claude/workflow-config.yaml`` ou retorna {} se ausente/inválido."""
    cfg_path = project_root / ".claude" / "workflow-config.yaml"
    return read_yaml_or_default(cfg_path, {}) or {}


def _compile_ignore_patterns(patterns: list[str]) -> tuple[list[str], list[str]]:
    """Valida cada regex em ``patterns`` uma única vez.

    Retorna ``(valid_patterns, warnings)``:
      - ``valid_patterns`` contém apenas regex que compilam sem erro;
      - ``warnings`` lista mensagens descritivas pra cada pattern inválido
        (formato canônico: "cc-gate.ignore-paths: regex inválida '<pat>' (<erro>)").

    Caller (``validate``) emite a lista no result dict — assim o user vê o
    motivo de o filtro ter ignorado a entrada da config dele em vez de
    debugar silenciosamente (fix D-006).
    """
    valid: list[str] = []
    warnings: list[str] = []
    for pat in patterns:
        try:
            re.compile(pat)
        except re.error as e:
            warnings.append(
                f"cc-gate.ignore-paths: regex inválida '{pat}' ({e})"
            )
            continue
        valid.append(pat)
    return valid, warnings


def _path_matches_ignore(rel_path: str, patterns: list[str]) -> bool:
    """True se ``rel_path`` casa com QUALQUER regex em ``patterns``.

    Espera ``patterns`` pré-validados via ``_compile_ignore_patterns`` (caller
    é ``validate``). A blindagem ``re.error → continue`` aqui é belt-and-
    suspenders pra caller que entregue regex bruto (testes diretos, callers
    futuros).
    """
    for pat in patterns:
        try:
            if re.search(pat, rel_path):
                return True
        except re.error:
            continue
    return False


def _run_tools_for_staged(
    *,
    files_by_lang: dict[str, list[str]],
    thresholds_by_lang: dict[str, int],
    diff_hunks: dict[str, list[DiffHunk]],
    project_root: Path,
) -> tuple[list[CCResult], list[str]]:
    """Dispatch every per-language tool. Return ``(results, warnings)``.

    Cada tool roda UMA VEZ por batch (Detekt sobre todos .kt staged, etc.) —
    overhead amortizado mesmo em features grandes. Tool missing → warning
    (não fail) por aquela linguagem; outras linguagens prosseguem (cascade
    alive per spec §3 trust-but-verify).

    `status` em cada CCResult é re-classificado aqui via
    ``classify_range_against_hunks`` contra ``diff_hunks`` — os parsers
    emitem ``status="unchanged"`` por default (não conhecem o diff) e o
    orchestrator faz o overlay correto.
    """
    parsers = {
        "kotlin": lambda raw: _parse_detekt(raw),
        "swift": lambda raw: _parse_swiftlint(raw),
        "ts": lambda raw: _parse_eslint(raw, project_root=str(project_root)),
        "python": lambda raw: _parse_radon(raw),
    }
    results: list[CCResult] = []
    warnings: list[str] = []
    for lang, files in files_by_lang.items():
        if not files:
            continue
        threshold = thresholds_by_lang.get(lang, 10)
        tool_bin = _TOOL_BIN[lang]
        if lang == "kotlin":
            d = dispatch_native_tool(
                language=lang,
                files=files,
                cmd_builder=_build_detekt_cmd,
                project_root=project_root,
                tool_bin=tool_bin,
                config_template=_CONFIG_DIR / "detekt.yml",
                placeholders={"__CC_THRESHOLD__": str(threshold)},
            )
        elif lang == "swift":
            d = dispatch_native_tool(
                language=lang,
                files=files,
                cmd_builder=_build_swiftlint_cmd,
                project_root=project_root,
                tool_bin=tool_bin,
                config_template=_CONFIG_DIR / "swiftlint.yml",
                placeholders={"__CC_THRESHOLD__": str(threshold)},
            )
        elif lang == "ts":
            d = dispatch_native_tool(
                language=lang,
                files=files,
                cmd_builder=_build_eslint_cmd_factory(threshold),
                project_root=project_root,
                tool_bin=tool_bin,
                benign_nonzero_codes=(1,),
            )
        elif lang == "python":
            d = dispatch_native_tool(
                language=lang,
                files=files,
                cmd_builder=_build_radon_cmd,
                project_root=project_root,
                tool_bin=tool_bin,
            )
        else:
            # Unsupported language — caller (validate) filters by
            # SUPPORTED_EXTENSIONS so this branch is defensive only.
            continue
        # D-009 — antes ambos casos emitiam `d.error_message` cru, indistinguíveis
        # do ponto de vista do usuário. Prefixo `[<tool>] tool ausente:` vs
        # `[<tool>] tool crashou:` deixa claro o que aconteceu sem perder a
        # mensagem original (que ainda traz o caminho/snippet do stderr).
        # `tool_bin` já foi resolvido antes do dispatch (linha acima).
        if not d.tool_found:
            warnings.append(f"[{tool_bin}] tool ausente: {d.error_message}")
            continue
        if d.crashed:
            warnings.append(f"[{tool_bin}] tool crashou: {d.error_message}")
            continue
        for r in parsers[lang](d.raw_stdout):
            hunks = diff_hunks.get(r.file, [])
            status = classify_range_against_hunks((r.line_start, r.line_end), hunks)
            results.append(
                CCResult(
                    file=r.file,
                    function=r.function,
                    line_start=r.line_start,
                    line_end=r.line_end,
                    cc=r.cc,
                    language=r.language,
                    status=status,
                    cc_before=r.cc_before,
                )
            )
    return results, warnings


def validate(project_root: Path, **kwargs: Any) -> dict[str, Any]:
    """Main entry-point — orquestra o pipeline CC gate completo.

    Args:
        project_root: Raiz do projeto consumidor (contém .claude/).
        **kwargs: Reservado pra extensões futuras (scope, id, etc. via run_cli).

    Returns:
        Result dict no formato canônico ``{status, message, ...}`` produzido
        por result_pass / result_warn / result_fail (vide _common.py). Em
        result_fail, o campo ``paths`` carrega o 3-paths block obrigatório.

    Pipeline detalhado: vide bloco de cabeçalho desta seção.
    """
    config = _load_workflow_config(project_root)
    cc_block = (config.get("cc-gate") or {}) if isinstance(config, dict) else {}
    if isinstance(cc_block, dict) and cc_block.get("enabled") is False:
        return result_warn(
            "cc-gate disabled in workflow-config (cc-gate.enabled=false)"
        )

    staged_paths = git_staged_files(
        project_root, extensions=set(SUPPORTED_EXTENSIONS)
    )
    if not staged_paths:
        return result_pass("nenhum arquivo staged — nada a checar")

    ignore_patterns = list(_TEST_IGNORE_DEFAULTS)
    extra_ignore = cc_block.get("ignore-paths") if isinstance(cc_block, dict) else None
    if isinstance(extra_ignore, list):
        ignore_patterns.extend(str(p) for p in extra_ignore)
    # Pre-valida regex uma vez (D-006): patterns inválidas em config viram
    # warnings concretos no result em vez de serem silenciosamente engolidas
    # toda vez que `_path_matches_ignore` itera.
    ignore_patterns, ignore_warnings = _compile_ignore_patterns(ignore_patterns)

    files_by_lang: dict[str, list[str]] = {
        "kotlin": [],
        "swift": [],
        "ts": [],
        "python": [],
    }
    for p in staged_paths:
        try:
            rel = str(p.relative_to(project_root))
        except ValueError:
            continue
        if _path_matches_ignore(rel, ignore_patterns):
            continue
        lang = SUPPORTED_EXTENSIONS.get(p.suffix)
        if lang:
            files_by_lang[lang].append(rel)

    if not any(files_by_lang.values()):
        res = result_pass("no candidate files after ignore-paths filter")
        if ignore_warnings:
            res["warnings"] = list(ignore_warnings)
        return res

    active_cards = _load_active_cards(project_root)
    thresholds_by_lang: dict[str, int] = {}
    for lang in files_by_lang:
        try:
            thresholds_by_lang[lang] = gate_threshold_lookup(
                lang, active_cards=active_cards, workflow_config=config
            )
        except ValueError:
            # Linguagem fora do scope CC — não deveria acontecer (filtrada
            # antes), mas defesa contra desvio futuro em SUPPORTED_EXTENSIONS.
            thresholds_by_lang[lang] = 10

    diff_hunks = extract_diff_hunks(project_root, staged_paths)

    results, tool_warnings = _run_tools_for_staged(
        files_by_lang=files_by_lang,
        thresholds_by_lang=thresholds_by_lang,
        diff_hunks=diff_hunks,
        project_root=project_root,
    )

    # Aplica a regra: new → cc > threshold; modified → cc_after > cc_before.
    fails: list[CCResult] = []
    for r in results:
        threshold = thresholds_by_lang.get(r.language, 10)
        if r.status == "new" and r.cc > threshold:
            fails.append(r)
        elif r.status == "modified":
            if r.cc_before is not None and r.cc > r.cc_before:
                fails.append(r)
        # "unchanged" ou modified sem regressão → não conta.

    # Override-justify aplicado antes de emitir fail (spec §4).
    commit_body = read_commit_body(project_root)
    silenced, surviving, override_warnings = apply_overrides(fails, commit_body)

    # H4 — malformed CC-OVERRIDE attempts must surface as warnings even when
    # the gate passes. Spec §4 step 5: "Validator emite warning ...".
    # D-006 — patterns regex inválidas em `cc-gate.ignore-paths` também
    # propagam (antes silently swallowed em `_path_matches_ignore`).
    all_warnings: list[str] = (
        list(ignore_warnings) + list(tool_warnings) + list(override_warnings)
    )

    if not surviving:
        if all_warnings:
            res = result_warn(
                f"cc-gate ok ({len(silenced)} silenced via override); "
                f"tools incompletas: " + "; ".join(all_warnings)
            )
            res["warnings"] = all_warnings
            return res
        if silenced:
            return result_pass(
                f"cc-gate ok ({len(results)} funções inspecionadas, "
                f"{len(silenced)} silenced via CC-OVERRIDE)"
            )
        return result_pass(
            f"cc-gate ok ({len(results)} funções inspecionadas)"
        )

    # Build canonical 3-paths message.
    violations = [
        {
            "file": r.file,
            "line": r.line_start,
            "function": r.function,
            "cc": r.cc,
            "threshold": thresholds_by_lang.get(r.language, 10),
            "status": r.status,
            "cc_before": r.cc_before,
            "language": r.language,
        }
        for r in surviving
    ]
    affected_thresholds = {
        r.language: thresholds_by_lang.get(r.language, 10) for r in surviving
    }

    # H3 — render the canonical 3-paths block (format_three_paths_message) AND
    # attach it to the result dict so engine.implement._render_cc_gate_block
    # can surface mentor-calmo prose to the user. Spec §4 + disciplines §1
    # treat this render as load-bearing UX contract.
    canonical_render = format_three_paths_message(violations, affected_thresholds)

    sample = ", ".join(
        f"{r.file}:{r.function}(cc={r.cc})" for r in surviving[:3]
    )
    res = result_fail(
        f"Cyclomatic Complexity gate: {len(surviving)} função(ões) acima do threshold",
        what_failed=sample,
        where="staged files",
        why=[
            "Funções com CC alto são mais difíceis de testar/revisar/evoluir.",
            "Threshold vigente: "
            + ", ".join(
                f"{lang}={n}" for lang, n in sorted(affected_thresholds.items())
            ),
            "Hard gate da cascade (Decision 23 fail-fast).",
        ],
        paths=make_paths(
            "Refatorar — quebrar em helpers menores",
            "Extrair branches / validações / loops em métodos privados nomeados.",
            "Override-justify no commit body — CC-OVERRIDE: <file>:<func> cc=<N> — <razão>",
            "Use APENAS quando a complexidade é genuinamente irredutível.",
            "Split-task — dividir a task atual em sub-tasks menores",
            "Sintoma típico: 'task fez coisa demais'. Re-rodar `forge implement`.",
        ),
    )
    res["render"] = canonical_render
    if all_warnings:
        res["warnings"] = all_warnings
    return res


if __name__ == "__main__":
    sys.exit(run_cli(__doc__ or "", validate))
