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
import os
import re  # noqa: F401  — used by override-detect task (T7)
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
from _gate_infra import (
    DispatchResult,
    check_tool_available,
    render_config_with_placeholders,
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


def _dispatch_tool(
    *,
    language: str,
    files: list[str],
    threshold: int,
    project_root: Path,
) -> DispatchResult:
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
    if not check_tool_available(tool):
        return DispatchResult(
            language=language,
            tool_found=False,
            crashed=False,
            raw_stdout="",
            error_message=f"{tool} not installed (PATH lookup failed)",
        )

    # Tempfile path is set only for languages whose tool does not accept
    # per-rule threshold via CLI (Detekt, SwiftLint). We render the config
    # template substituting __CC_THRESHOLD__ per invocation (spec §3), then
    # remove the tempfile after subprocess returns regardless of outcome.
    rendered_config: Optional[str] = None

    try:
        if language == "kotlin":
            # Detekt: --input aceita lista vírgula-separada; --report json:- escreve
            # JSON em stdout (sem precisar tempfile pro report). Threshold é
            # rendered dinamicamente no config (Detekt não aceita CLI override
            # por regra). Spec §3 threshold-via-CLI honored via tmpfile render.
            rendered_config = render_config_with_placeholders(
                _CONFIG_DIR / "detekt.yml",
                {"__CC_THRESHOLD__": str(threshold)},
            )
            cmd = [
                tool,
                "--input", ",".join(files),
                "--config", rendered_config,
                "--report", "json:-",
            ]
        elif language == "swift":
            # SwiftLint: subcomando `lint` + reporter json. Threshold rendered
            # dinamicamente no config (SwiftLint não aceita CLI override per-rule).
            # Spec §3 threshold-via-CLI honored via tmpfile render.
            rendered_config = render_config_with_placeholders(
                _CONFIG_DIR / "swiftlint.yml",
                {"__CC_THRESHOLD__": str(threshold)},
            )
            cmd = [
                tool, "lint",
                "--reporter", "json",
                "--config", rendered_config,
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
            # radon cc -j: JSON output sem rank filter (-n A é rank mínimo "A",
            # mostra TODAS as funções). H2 fix: o flag `-n F` antigo mascarava
            # toda função com CC ∈ [11..40] — exatamente o sweet spot do gate.
            # Filtragem fina por threshold acontece no validator depois.
            cmd = [
                tool, "cc", "-j", "-n", "A",
                *files,
            ]
        else:
            # Inalcançável: _TOOL_BIN[language] já teria raised KeyError acima.
            # Mantido por simetria/defesa.
            return DispatchResult(
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
            return DispatchResult(
                language=language,
                tool_found=True,
                crashed=True,
                raw_stdout="",
                error_message=f"{tool} timeout (>60s)",
            )
        except OSError as exc:
            return DispatchResult(
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
            return DispatchResult(
                language=language,
                tool_found=True,
                crashed=True,
                raw_stdout=proc.stdout or "",
                error_message=(proc.stderr or "").strip()[:400]
                or f"{tool} exit={proc.returncode}",
            )

        return DispatchResult(
            language=language,
            tool_found=True,
            crashed=False,
            raw_stdout=proc.stdout or "",
            error_message="",
        )
    finally:
        if rendered_config:
            try:
                os.unlink(rendered_config)
            except OSError:
                # Best-effort cleanup — tempfile leak is a minor leak, never
                # a behavior bug. Don't shadow the real exception.
                pass


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
        reason = m.group("reason").strip()
        # D-008 — `.+` no regex casa whitespace puro após `—`. Sem este guard,
        # `CC-OVERRIDE: foo:bar cc=11 —    ` viraria override válido com
        # reason="". Skipa pro loose-pass, que emite o warning canônico.
        if not reason:
            continue
        overrides.append(
            {
                "file": m.group("file"),
                "func": m.group("func"),
                "cc": cc,
                "reason": reason,
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
        # Detect the em-dash and inspect what follows: a concrete reason after
        # ` — ` means the strict regex already accepted it (skip); a trailing
        # em-dash with empty/whitespace tail is still malformed and must warn
        # (D-008 — the previous `if " — " in line: continue` swallowed these).
        if " — " in line:
            _, _, tail = line.partition(" — ")
            if tail.strip():
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
) -> tuple[list[CCResult], list[CCResult], list[str]]:
    """Split `fails` into (silenced, surviving, warnings) using CC-OVERRIDE lines.

    Match key: (file, function). Override cobre APENAS o par (file, func)
    declarado — sem wildcards. Cada override aplica-se a UM commit; auditoria
    via `git log --grep='CC-OVERRIDE'`.

    Malformed-override warnings (lines that look like CC-OVERRIDE but miss the
    `— <razão>` tail) are surfaced as the third tuple element so the validator
    can include them in the final result dict (H4 fix — spec §4 step 5
    mandates "Validator emite warning 'CC-OVERRIDE sem razão — adicione texto
    após —'. Mantém o fail.").
    """
    overrides, warnings = _parse_overrides(commit_body, return_warnings=True)
    if not overrides:
        return [], list(fails), warnings

    cover: set[tuple[str, str]] = {(o["file"], o["func"]) for o in overrides}
    silenced: list[CCResult] = []
    surviving: list[CCResult] = []
    for f in fails:
        if (f.file, f.function) in cover:
            silenced.append(f)
        else:
            surviving.append(f)
    return silenced, surviving, warnings


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
#   4. Resolve threshold por linguagem via cc_threshold_lookup (card override
#      > workflow-config > DEFAULTS_CC).
#   5. Extrai diff hunks pra classificar new/modified/unchanged.
#   6. Dispatch tool per linguagem (Detekt/SwiftLint/eslint/radon) numa única
#      invocação por batch. Tool missing/crash → warning, sem fail.
#   7. Classifica cada função encontrada via classify_function.
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


def _git_staged_files(project_root: Path) -> list[Path]:
    """Return absolute paths of files in ``git diff --cached --name-only``.

    Filtra pelas extensões em SUPPORTED_EXTENSIONS antes de devolver. Git
    indisponível / não-repo / errors → lista vazia (caller trata como
    "nenhum arquivo a checar"). Timeout 10s evita hang em repo gigante.
    """
    try:
        # `-M80%`: rename detection per SDD §2 — função renomeada (até 20% de
        # mudança) é classificada como "modified" pelo delta rule (cf. F-001),
        # não como "new" + delete. Sem isso, renames viram falso-positivo de
        # função nova com absolute-rule.
        out = subprocess.run(
            ["git", "-C", str(project_root), "diff", "--cached", "-M80%", "--name-only"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        return []
    if out.returncode != 0:
        return []
    files: list[Path] = []
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        p = project_root / line
        if p.is_file() and p.suffix in SUPPORTED_EXTENSIONS:
            files.append(p)
    return files


def _extract_diff_hunks(
    project_root: Path, files: list[Path]
) -> dict[str, list[dict[str, Any]]]:
    """For each staged file, return its add hunks as line-range dicts.

    Hunk shape: ``{"start": int, "end": int, "kind": "add"}``. Apenas o lado
    "+" do diff é capturado — caller usa pra classify_function (new vs
    modified vs unchanged). git diff -U0 dá hunks compactos sem context.
    """
    by_file: dict[str, list[dict[str, Any]]] = {}
    for f in files:
        try:
            rel = str(f.relative_to(project_root))
        except ValueError:
            # Arquivo fora do project_root — skip silenciosamente.
            continue
        try:
            proc = subprocess.run(
                ["git", "-C", str(project_root), "diff", "--cached", "-U0", "--", rel],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (subprocess.SubprocessError, OSError):
            by_file[rel] = []
            continue
        hunks: list[dict[str, Any]] = []
        for line in proc.stdout.splitlines():
            if not line.startswith("@@"):
                continue
            # Hunk header: @@ -a,b +c,d @@
            m = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if not m:
                continue
            start = int(m.group(1))
            length = int(m.group(2)) if m.group(2) else 1
            hunks.append(
                {"start": start, "end": start + max(length - 1, 0), "kind": "add"}
            )
        by_file[rel] = hunks
    return by_file


def _read_commit_body(project_root: Path) -> str:
    """Best-effort read do commit message body (pra detectar CC-OVERRIDE).

    Ordem:
      1. ``.git/COMMIT_EDITMSG`` — populado pelo pre-commit hook (caso
         comum em forge implement). Lê mesmo se commit ainda não foi feito.
      2. ``git log -1 --format=%B HEAD`` — fallback pós-commit (forge verify
         rodando depois do commit já formado).

    Não-encontrado / erro → string vazia (sem overrides aplicáveis).
    """
    editmsg = project_root / ".git" / "COMMIT_EDITMSG"
    if editmsg.is_file():
        try:
            return editmsg.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
    try:
        proc = subprocess.run(
            ["git", "-C", str(project_root), "log", "-1", "--format=%B"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0:
            return proc.stdout
    except (subprocess.SubprocessError, OSError):
        pass
    return ""


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
    diff_hunks: dict[str, list[dict[str, Any]]],
    project_root: Path,
) -> tuple[list[CCResult], list[str]]:
    """Dispatch every per-language tool. Return ``(results, warnings)``.

    Cada tool roda UMA VEZ por batch (Detekt sobre todos .kt staged, etc.) —
    overhead amortizado mesmo em features grandes. Tool missing → warning
    (não fail) por aquela linguagem; outras linguagens prosseguem (cascade
    alive per spec §3 trust-but-verify).

    `status` em cada CCResult é re-classificado aqui via classify_function
    contra ``diff_hunks`` — os parsers emitem ``status="unchanged"`` por
    default (não conhecem o diff) e o orchestrator faz o overlay correto.
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
        d = _dispatch_tool(
            language=lang,
            files=files,
            threshold=threshold,
            project_root=project_root,
        )
        # D-009 — antes ambos casos emitiam `d.error_message` cru, indistinguíveis
        # do ponto de vista do usuário. Prefixo `[<tool>] tool ausente:` vs
        # `[<tool>] tool crashou:` deixa claro o que aconteceu sem perder a
        # mensagem original (que ainda traz o caminho/snippet do stderr).
        tool_bin = _TOOL_BIN[lang]
        if not d.tool_found:
            warnings.append(f"[{tool_bin}] tool ausente: {d.error_message}")
            continue
        if d.crashed:
            warnings.append(f"[{tool_bin}] tool crashou: {d.error_message}")
            continue
        for r in parsers[lang](d.raw_stdout):
            hunks = diff_hunks.get(r.file, [])
            status = classify_function((r.line_start, r.line_end), hunks)
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

    staged_paths = _git_staged_files(project_root)
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
            thresholds_by_lang[lang] = cc_threshold_lookup(
                lang, active_cards=active_cards, workflow_config=config
            )
        except ValueError:
            # Linguagem fora do scope CC — não deveria acontecer (filtrada
            # antes), mas defesa contra desvio futuro em SUPPORTED_EXTENSIONS.
            thresholds_by_lang[lang] = 10

    diff_hunks = _extract_diff_hunks(project_root, staged_paths)

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
    commit_body = _read_commit_body(project_root)
    silenced, surviving, override_warnings = _apply_overrides(fails, commit_body)

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

    # H3 — render the canonical 3-paths block (cc_format_three_paths) AND
    # attach it to the result dict so engine.implement._render_cc_gate_block
    # can surface mentor-calmo prose to the user. Spec §4 + disciplines §1
    # treat this render as load-bearing UX contract.
    canonical_render = cc_format_three_paths(violations, affected_thresholds)

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
