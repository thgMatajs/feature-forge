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


# Subsequent tasks (4–8) append: parsers, dispatch, override, run().


if __name__ == "__main__":
    sys.exit(run_cli(__doc__ or "", lambda root, **kw: result_pass("skeleton — not wired yet")))
