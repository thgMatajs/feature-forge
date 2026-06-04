#!/usr/bin/env python3
"""check_cyclomatic_complexity.py — multi-language CC gate.

Runs in two contexts (per design spec §2):

1. `forge verify` cascade — feature-wide gate, after check_no_invented_behavior.
2. `forge implement` per-task — between Review and Commit, blocks the commit
   when a staged function exceeds its threshold (or when a modified function
   got worse than HEAD).

Threshold precedence (per design spec §2 + helpers in _common):
    card cc-gate-override > workflow-config cc-gate > DEFAULTS_CC

On fail, emits the canonical 3-paths block (see _common.cc_format_three_paths).
Override-justify: `CC-OVERRIDE: <file>:<func> cc=<N> — <reason>` in the commit
body silences a specific function for THAT commit only — no persistent
whitelist (auditable via `git log --grep='CC-OVERRIDE'`).
"""

from __future__ import annotations

import json  # noqa: F401  — used by parser tasks (T4/T5)
import re  # noqa: F401  — used by override-detect task (T7)
import shutil  # noqa: F401  — used by tool-availability task (T6)
import subprocess  # noqa: F401  — used by dispatch task (T6)
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from _common import (
    cc_format_three_paths,  # noqa: F401  — wired in T8 validate()
    cc_threshold_lookup,  # noqa: F401  — wired in T8 validate()
    make_paths,  # noqa: F401  — wired in T8 validate()
    result_fail,  # noqa: F401  — wired in T8 validate()
    result_pass,
    result_warn,  # noqa: F401  — wired in T6/T8
    run_cli,
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
    step (run + classify_function).
    """

    file: str           # path relative to project root
    function: str       # name + signature when available
    line_start: int     # 1-indexed
    line_end: int
    cc: int             # CC computed on the staged blob
    language: str       # "kotlin" | "swift" | "ts" | "python"
    status: str         # "new" | "modified" | "unchanged"
    cc_before: Optional[int]  # None when status == "new" or unknown


def classify_function(
    func_range: tuple[int, int],
    diff_hunks: list[dict[str, Any]],
) -> str:
    """Classify a function as new | modified | unchanged using diff hunks.

    Args:
        func_range: (line_start, line_end) inclusive, 1-indexed.
        diff_hunks: list of {"start": int, "end": int, "kind": "add"|"del"|"ctx"}.

    Rules (per design spec §2 step 9):
        - new       — entire func_range falls inside an "add" hunk
        - modified  — func_range intersects any hunk (partial overlap)
        - unchanged — no overlap with any hunk
    """
    if not diff_hunks:
        return "unchanged"

    f_start, f_end = func_range
    add_hunks = [h for h in diff_hunks if h.get("kind", "add") == "add"]

    # "new" — entire function range contained within a single add hunk
    for h in add_hunks:
        if h["start"] <= f_start and h["end"] >= f_end:
            return "new"

    # "modified" — any intersection
    for h in diff_hunks:
        if h["start"] <= f_end and h["end"] >= f_start:
            return "modified"

    return "unchanged"


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


@dataclass(frozen=True)
class _DispatchResult:
    """Outcome of a single tool invocation.

    Contract:
        tool_found=False  → tool not on PATH; caller emits result_warn with
                            install hint. raw_stdout / crashed irrelevantes.
        crashed=True      → non-zero exit (exceto eslint exit=1 benigno),
                            timeout, ou OSError. error_message tem stderr
                            snippet ou descrição. raw_stdout pode ter parcial.
        otherwise         → raw_stdout vai para o parser correspondente
                            (_parse_detekt / _parse_swiftlint / etc.).
    """

    language: str
    tool_found: bool
    crashed: bool
    raw_stdout: str
    error_message: str


def _check_tool_available(tool: str) -> bool:
    """Return True iff `tool` is on PATH (shutil.which lookup).

    Não tenta executar — apenas PATH lookup. Suficiente porque tool crash
    em runtime é tratado separadamente em _dispatch_tool.
    """
    return shutil.which(tool) is not None


def _dispatch_tool(
    *,
    language: str,
    files: list[str],
    threshold: int,
    project_root: Path,
) -> _DispatchResult:
    """Invoke the per-language tool over `files`. Never raises (exceto KeyError
    para language não suportada — contrato é caller filtra por SUPPORTED_EXTENSIONS).

    Per spec §3 trust-but-verify:
      - tool not on PATH → tool_found=False, no execution attempted.
      - subprocess timeout → crashed=True, error_message contém "timeout".
      - OSError (ex: permissions) → crashed=True, error_message com causa.
      - exit != 0 (exceto eslint exit=1 que é benigno por design) → crashed=True
        com stderr snippet (cap 400 chars).
      - exit == 0 (ou eslint exit=1) → raw_stdout entregue ao caller.

    Timeout fixo 60s — tools nativas em batches razoáveis de files (poucas
    centenas) terminam bem antes disso. Timeout maior mascararia tool hang.
    """
    tool = _TOOL_BIN[language]
    if not _check_tool_available(tool):
        return _DispatchResult(
            language=language,
            tool_found=False,
            crashed=False,
            raw_stdout="",
            error_message=f"{tool} not installed (PATH lookup failed)",
        )

    if language == "kotlin":
        # Detekt: --input aceita lista vírgula-separada; --report json:- escreve
        # JSON em stdout (sem precisar tempfile). Config interno desabilita
        # tudo exceto CyclomaticComplexMethod.
        cmd = [
            tool,
            "--input", ",".join(files),
            "--config", str(_CONFIG_DIR / "detekt.yml"),
            "--report", "json:-",
        ]
    elif language == "swift":
        # SwiftLint: subcomando `lint` + reporter json + config interno que
        # ativa só cyclomatic_complexity. Files vão posicionalmente no final.
        cmd = [
            tool, "lint",
            "--reporter", "json",
            "--config", str(_CONFIG_DIR / "swiftlint.yml"),
            *files,
        ]
    elif language == "ts":
        # eslint: --no-eslintrc ignora config do projeto consumidor (evita
        # interferência); --rule inline com threshold dinâmico. Format json
        # produz array file-by-file (parseado por _parse_eslint).
        cmd = [
            tool,
            "--no-eslintrc",
            "--rule", f'{{"complexity": ["error", {{"max": {threshold}}}]}}',
            "--format", "json",
            *files,
        ]
    elif language == "python":
        # radon cc -j: JSON output; -n F filtra só blocks com rank ≥ F (CC ≥ 41).
        # Mas mantemos -n F porque baseline padrão; validator compara CC numérico
        # contra threshold direto. -n F é só pra evitar ruído de funções triviais.
        cmd = [
            tool, "cc", "-j", "-n", "F",
            *files,
        ]
    else:
        # Inalcançável: _TOOL_BIN[language] já teria raised KeyError acima.
        # Mantido por simetria/defesa.
        return _DispatchResult(
            language=language,
            tool_found=False,
            crashed=False,
            raw_stdout="",
            error_message=f"unsupported language: {language}",
        )

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _DispatchResult(
            language=language,
            tool_found=True,
            crashed=True,
            raw_stdout="",
            error_message=f"{tool} timeout (>60s)",
        )
    except OSError as exc:
        return _DispatchResult(
            language=language,
            tool_found=True,
            crashed=True,
            raw_stdout="",
            error_message=f"{tool} OS error: {exc}",
        )

    # eslint exits 1 quando issues encontrados — NÃO é crash, é normal.
    # Outros tools: exit != 0 é crash genuíno.
    benign_nonzero = language == "ts" and proc.returncode == 1
    if proc.returncode != 0 and not benign_nonzero:
        return _DispatchResult(
            language=language,
            tool_found=True,
            crashed=True,
            raw_stdout=proc.stdout or "",
            error_message=(proc.stderr or "").strip()[:400]
            or f"{tool} exit={proc.returncode}",
        )

    return _DispatchResult(
        language=language,
        tool_found=True,
        crashed=False,
        raw_stdout=proc.stdout or "",
        error_message="",
    )


# Subsequent tasks (7–8) append: override, run().


# ── Override-justify ─────────────────────────────────────────────────────────
#
# Single-line override declared in the commit body. Anchored to start-of-line
# (re.MULTILINE) so it can't be smuggled mid-sentence. The format is
# load-bearing — `.claude/rules/disciplines.md §1` references it directly.
#
# Strict regex exige o trailing ` — <razão concreta>` (em-dash U+2014).
# Loose regex captura tentativas malformadas (sem `—`) pra emitir warning;
# isso mantém o gate honesto sobre tentativas de silenciar fails sem razão.

_CC_OVERRIDE_RE = re.compile(
    r"^CC-OVERRIDE:\s+(?P<file>\S+):(?P<func>\S+)\s+cc=(?P<cc>\d+)\s+—\s+(?P<reason>.+)$",
    re.MULTILINE,
)

_CC_OVERRIDE_LOOSE_RE = re.compile(
    r"^CC-OVERRIDE:\s+(?P<file>\S+):(?P<func>\S+)\s+cc=(?P<cc>\d+)\b",
    re.MULTILINE,
)


def _parse_overrides(
    commit_body: str,
    *,
    return_warnings: bool = False,
):
    """Parse CC-OVERRIDE lines from a commit body.

    Returns a list of override dicts (file/func/cc/reason). When
    `return_warnings=True`, returns a (overrides, warnings) tuple.

    Lines starting with CC-OVERRIDE but missing the `— <reason>` tail are
    flagged as warnings and NOT counted as valid overrides — keeps the gate
    honest about silenced fails.
    """
    overrides: list[dict[str, Any]] = []
    warnings: list[str] = []

    # First pass: strict regex (must have reason).
    valid_spans: set[tuple[int, int]] = set()
    for m in _CC_OVERRIDE_RE.finditer(commit_body):
        try:
            cc = int(m.group("cc"))
        except (TypeError, ValueError):
            continue
        overrides.append(
            {
                "file": m.group("file"),
                "func": m.group("func"),
                "cc": cc,
                "reason": m.group("reason").strip(),
            }
        )
        valid_spans.add(m.span())

    # Second pass: loose match — anything that LOOKS like an override but
    # didn't pass strict regex is a malformed attempt → warn.
    for m in _CC_OVERRIDE_LOOSE_RE.finditer(commit_body):
        if m.span() in valid_spans:
            continue
        # Skip if the strict regex DID match on the same line (different span).
        nl = commit_body.find("\n", m.start())
        line_end = nl if nl != -1 else len(commit_body)
        line = commit_body[m.start():line_end]
        if " — " in line:
            continue
        warnings.append(
            f"CC-OVERRIDE sem razão concreta: '{line.strip()}' — adicione texto após —"
        )

    if return_warnings:
        return overrides, warnings
    return overrides


def _apply_overrides(
    fails: list[CCResult],
    commit_body: str,
) -> tuple[list[CCResult], list[CCResult]]:
    """Split `fails` into (silenced, surviving) using CC-OVERRIDE lines.

    Match key: (file, function). Override cobre APENAS o par (file, func)
    declarado — sem wildcards. Cada override aplica-se a UM commit; auditoria
    via `git log --grep='CC-OVERRIDE'`.
    """
    overrides = _parse_overrides(commit_body)
    if not overrides:
        return [], list(fails)

    cover: set[tuple[str, str]] = {(o["file"], o["func"]) for o in overrides}
    silenced: list[CCResult] = []
    surviving: list[CCResult] = []
    for f in fails:
        if (f.file, f.function) in cover:
            silenced.append(f)
        else:
            surviving.append(f)
    return silenced, surviving


if __name__ == "__main__":
    sys.exit(run_cli(__doc__ or "", lambda root, **kw: result_pass("skeleton — not wired yet")))
