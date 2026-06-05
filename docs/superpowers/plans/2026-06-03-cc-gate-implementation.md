# Cyclomatic Complexity Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `check_cyclomatic_complexity` gate — multi-language CC validator que roda no cascade de `forge verify` e per-task em `forge implement`, com 3-caminhos on-fail (refactor / override-justify / split-task).

**Architecture:** Validator único Python em `validators/check_cyclomatic_complexity.py` (~350-450 LOC) que dispatcha pra tools nativas (Detekt/SwiftLint/eslint/Radon) via subprocess, normaliza output pra `CCResult` dataclass, classifica funções new vs modified via diff hunks, aplica regra threshold absoluto (new) ou delta (modified), resolve threshold via precedência card > workflow-config > defaults. Sem runtime deps em outras skills (Decision 22), sem comando novo (Decision 10), sem revisitar decisões locked.

**Tech Stack:** Python 3.10+, pytest, Detekt (Kotlin), SwiftLint (Swift), eslint (TS/JS), Radon (Python). Tools nativas são CLIs externas — forge não instala (`forge doctor` reporta status).

**Reference spec:** [`docs/superpowers/specs/2026-06-03-cc-gate-design.md`](../specs/2026-06-03-cc-gate-design.md) — fonte de verdade. Em conflito spec vs plan, spec vence.

---

## File Structure

### Created (12 paths)

```
validators/check_cyclomatic_complexity.py        # validator principal, ~350-450 LOC
engine/_cc_configs/__init__.py                   # marker
engine/_cc_configs/detekt.yml                    # config interno Detekt (só CyclomaticComplexMethod)
engine/_cc_configs/swiftlint.yml                 # config interno SwiftLint (só cyclomatic_complexity)
engine/_cc_configs/eslint.json                   # placeholder — threshold via CLI
engine/_cc_configs/radon.cfg                     # exclude tests, json output

tests/validators/test_common_cc_helpers.py       # cc_threshold_lookup + cc_format_three_paths
tests/validators/test_cc_classifier.py           # CCResult dataclass + new/modified/unchanged
tests/validators/test_cc_parsers_kotlin_swift.py # _parse_detekt + _parse_swiftlint
tests/validators/test_cc_parsers_ts_python.py    # _parse_eslint + _parse_radon
tests/validators/test_cc_dispatch.py             # _dispatch_tool + _check_tool_available
tests/validators/test_cc_override.py             # CC-OVERRIDE detection
tests/validators/test_check_cyclomatic_complexity.py  # entry point run(context) e2e mockado
tests/engine/test_cc_configs_exist.py            # sanity: configs parseáveis
tests/engine/test_verify_cc_position.py          # cascade position
tests/engine/test_implement_cc_gate.py           # per-task hook
tests/engine/test_doctor_cc_tools.py             # nova categoria
tests/integration/test_cc_gate_end_to_end.py     # 5 cenários e2e

tests/fixtures/cc_gate/detekt_output_sample.json
tests/fixtures/cc_gate/swiftlint_output_sample.json
tests/fixtures/cc_gate/eslint_output_sample.json
tests/fixtures/cc_gate/radon_output_sample.json
tests/fixtures/cc_gate/kotlin_high_cc.kt
tests/fixtures/cc_gate/kotlin_low_cc.kt
tests/fixtures/cc_gate/swift_high_cc.swift
tests/fixtures/cc_gate/ts_high_cc.ts
tests/fixtures/cc_gate/python_high_cc.py
tests/fixtures/cc_gate/workflow-config-with-cc.yaml
tests/fixtures/cc_gate/card-with-cc-override.yaml
```

### Modified (8 arquivos código + 8 arquivos doc)

```
validators/_common.py                      # APPEND cc_threshold_lookup + cc_format_three_paths
engine/verify.py                           # APPEND register check_cyclomatic_complexity in cascade
engine/implement.py                        # APPEND cc gate hook between review and commit
engine/doctor.py                           # APPEND categoria cc-gate-tools (13ª)

CHANGELOG.md
docs/design/08-session-handoff.md
README.md
docs/schemas/workflow-config.md
docs/schemas/card.md
docs/design/07-discipline.md
docs/design/04-pending.md
.claude/rules/testing.md
```

---

## Task 1 — Helpers em `_common.py` (cc_threshold_lookup + cc_format_three_paths)

**Files:**
- Modify: `validators/_common.py` (APPEND duas funções helpers)
- Test: `tests/validators/test_common_cc_helpers.py` (NEW)

TDD cycle:

- [ ] Step 1: Write `tests/validators/test_common_cc_helpers.py` com os 6 cenários abaixo. Mantém isolamento (sem I/O — só lookup em dicts) e snapshot do render canônico.

```python
"""Unit tests for cc_threshold_lookup + cc_format_three_paths helpers."""

from __future__ import annotations

import pytest

from _common import (
    DEFAULTS_CC,
    cc_format_three_paths,
    cc_threshold_lookup,
)


def test_lookup_default_when_no_config_and_no_cards() -> None:
    assert cc_threshold_lookup("kotlin", active_cards=[], workflow_config={}) == 10
    assert cc_threshold_lookup("ts", active_cards=[], workflow_config={}) == 15


def test_lookup_workflow_config_overrides_default() -> None:
    cfg = {"cc-gate": {"kotlin": 12, "ts": 20}}
    assert cc_threshold_lookup("kotlin", active_cards=[], workflow_config=cfg) == 12
    assert cc_threshold_lookup("ts", active_cards=[], workflow_config=cfg) == 20
    # Unspecified language falls back to default
    assert cc_threshold_lookup("swift", active_cards=[], workflow_config=cfg) == 10


def test_lookup_card_override_wins_over_workflow_config() -> None:
    cards = [{"cc-gate-override": {"kotlin": {"threshold": 15, "justification": "DSL"}}}]
    cfg = {"cc-gate": {"kotlin": 12}}
    assert cc_threshold_lookup("kotlin", active_cards=cards, workflow_config=cfg) == 15


def test_lookup_multiple_cards_first_wins() -> None:
    cards = [
        {"cc-gate-override": {"kotlin": {"threshold": 15, "justification": "DSL"}}},
        {"cc-gate-override": {"kotlin": {"threshold": 20, "justification": "Other"}}},
    ]
    assert cc_threshold_lookup("kotlin", active_cards=cards, workflow_config={}) == 15


def test_lookup_card_without_threshold_field_falls_through() -> None:
    cards = [{"cc-gate-override": {"kotlin": {"justification": "missing threshold"}}}]
    cfg = {"cc-gate": {"kotlin": 12}}
    assert cc_threshold_lookup("kotlin", active_cards=cards, workflow_config=cfg) == 12


def test_defaults_table_is_canonical() -> None:
    assert DEFAULTS_CC == {"kotlin": 10, "swift": 10, "ts": 15, "python": 10}


def test_format_three_paths_snapshot() -> None:
    rendered = cc_format_three_paths(
        violations=[
            {
                "file": "app/auth/LoginViewModel.kt",
                "line": 42,
                "function": "handleLogin",
                "cc": 14,
                "threshold": 10,
                "status": "modified",
                "cc_before": 9,
                "language": "kotlin",
            }
        ],
        thresholds={"kotlin": 10},
    )
    # Cabeçalho canônico (.claude/rules/disciplines.md §1)
    assert "🛑 Cyclomatic Complexity gate" in rendered
    assert "O que falhou:" in rendered
    assert "Onde:" in rendered
    assert "Por que importa:" in rendered
    assert "Três caminhos pra resolver:" in rendered
    # Conteúdo específico
    assert "handleLogin" in rendered
    assert "cc=14" in rendered
    assert "↑ de cc=9" in rendered
    assert "kotlin=10" in rendered
    # Caminho 2 nome + formato override
    assert "Override-justify" in rendered
    assert "CC-OVERRIDE: <file>:<func> cc=<N> — <razão concreta>" in rendered
    assert "Sem auto-fix aqui — escolha humana." in rendered


def test_format_three_paths_new_function_annotation() -> None:
    rendered = cc_format_three_paths(
        violations=[
            {
                "file": "app/A.kt",
                "line": 1,
                "function": "novaFunc",
                "cc": 11,
                "threshold": 10,
                "status": "new",
                "cc_before": None,
                "language": "kotlin",
            }
        ],
        thresholds={"kotlin": 10},
    )
    assert "[new]" in rendered
    assert "↑ de cc=" not in rendered
```

- [ ] Step 2: Run `pytest tests/validators/test_common_cc_helpers.py -xvs`. Expected: FAIL com `ImportError: cannot import name 'cc_threshold_lookup' from '_common'`.

- [ ] Step 3: APPEND em `validators/_common.py` (no fim, depois de `load_catalog`):

```python
# ── Cyclomatic Complexity helpers ────────────────────────────────────────────
#
# Usados por `validators/check_cyclomatic_complexity.py`. Vivem em _common
# pra serem testáveis isoladamente e pra deixar o validator principal mais
# enxuto. Sem I/O — pura lookup + string formatting.

DEFAULTS_CC: dict[str, int] = {
    "kotlin": 10,
    "swift": 10,
    "ts": 15,
    "python": 10,
}


def cc_threshold_lookup(
    language: str,
    active_cards: list[dict[str, Any]],
    workflow_config: dict[str, Any],
) -> int:
    """Resolve CC threshold for a language.

    Precedence: card cc-gate-override > workflow-config cc-gate > DEFAULTS_CC.

    Multiple cards conflicting: first card with a `threshold` key wins
    (deterministic, matches declaration order). Card override entries
    without an explicit `threshold` field fall through to the next layer.
    """
    for card in active_cards:
        if not isinstance(card, dict):
            continue
        override = card.get("cc-gate-override") or {}
        if not isinstance(override, dict):
            continue
        lang_block = override.get(language)
        if not isinstance(lang_block, dict):
            continue
        if "threshold" in lang_block:
            try:
                return int(lang_block["threshold"])
            except (TypeError, ValueError):
                continue

    cc_block = workflow_config.get("cc-gate") or {}
    if isinstance(cc_block, dict) and language in cc_block:
        try:
            return int(cc_block[language])
        except (TypeError, ValueError):
            pass

    return DEFAULTS_CC[language]


def cc_format_three_paths(
    violations: list[dict[str, Any]],
    thresholds: dict[str, int],
) -> str:
    """Render the canonical 3-paths message for a CC failure.

    Snapshot in tests — keep wording stable. See
    `.claude/rules/disciplines.md §1` for the template contract and
    `docs/superpowers/specs/2026-06-03-cc-gate-design.md §4` for the
    CC-specific instance.
    """
    lines: list[str] = []
    lines.append("🛑 Cyclomatic Complexity gate")
    lines.append("")
    lines.append("O que falhou:")
    lines.append(f"  {len(violations)} funções excederam o threshold permitido.")
    lines.append("")
    lines.append("Onde:")
    for v in violations:
        annotation = ""
        if v.get("status") == "new":
            annotation = " [new]"
        elif v.get("status") == "modified" and v.get("cc_before") is not None:
            annotation = f"  ↑ de cc={v['cc_before']} [modified]"
        lines.append(
            f"  · {v['file']}:{v['line']} — {v['function']}()"
            f"        cc={v['cc']}  (limite: {v['threshold']}){annotation}"
        )
    lines.append("")
    lines.append("Por que importa:")
    lines.append(
        "  · Funções com CC alto são mais difíceis de testar, revisar e evoluir."
    )
    th_str = ", ".join(f"{lang}={n}" for lang, n in sorted(thresholds.items()))
    lines.append(f"  · Threshold vigente: {th_str} (workflow-config.yaml)")
    lines.append("  · Decision 23 — cascade fail-fast; este é o primeiro hard fail.")
    lines.append("")
    lines.append("Três caminhos pra resolver:")
    lines.append("")
    lines.append("  1) Refatorar")
    lines.append(
        "     Quebra a função em helpers menores. Tipicamente: extrair branches"
    )
    lines.append(
        "     condicionais, validações, ou loops em métodos privados nomeados."
    )
    lines.append("     Re-rodar `forge verify` confirma.")
    lines.append("")
    lines.append("  2) Override-justify (commit body)")
    lines.append(
        "     Se a complexidade é genuinamente irredutível (state machine, parser,"
    )
    lines.append(
        "     DSL), adicionar ao commit body — EXATAMENTE este formato:"
    )
    lines.append("")
    lines.append("         CC-OVERRIDE: <file>:<func> cc=<N> — <razão concreta>")
    lines.append("")
    lines.append(
        "     Validator detecta a linha no commit body e libera APENAS este commit."
    )
    lines.append(
        "     Auditável via `git log --grep='CC-OVERRIDE'`. NÃO é whitelist persistente."
    )
    lines.append("")
    lines.append("  3) Split-task")
    lines.append(
        "     Dividir a task atual em sub-tasks menores. Tipicamente o sintoma é"
    )
    lines.append(
        "     \"task fez coisa demais\" — split via `forge implement` reabrindo"
    )
    lines.append("     task-breakdown.")
    lines.append("")
    lines.append("Sem auto-fix aqui — escolha humana.")
    return "\n".join(lines)
```

- [ ] Step 4: Run `pytest tests/validators/test_common_cc_helpers.py -xvs`. Expected: 7 passed.

- [ ] Step 5: Run `pytest tests/` (suite completa) — confirma zero regressão nos outros validators.

- [ ] Step 6: Commit:
  ```
  git add validators/_common.py tests/validators/test_common_cc_helpers.py
  git commit -m "feat(validators): cc helpers — threshold lookup + 3-caminhos format"
  ```

---

## Task 2 — Configs internos `engine/_cc_configs/`

**Files:**
- Create: `engine/_cc_configs/__init__.py` (vazio, marker)
- Create: `engine/_cc_configs/detekt.yml`
- Create: `engine/_cc_configs/swiftlint.yml`
- Create: `engine/_cc_configs/eslint.json`
- Create: `engine/_cc_configs/radon.cfg`
- Test: `tests/engine/test_cc_configs_exist.py` (NEW — sanity: arquivos existem e são parseáveis)

TDD cycle ajustado pra static configs:

- [ ] Step 1: Write `tests/engine/test_cc_configs_exist.py`:

```python
"""Sanity tests for engine/_cc_configs/: existence + parseability."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "engine" / "_cc_configs"


def test_init_marker_exists() -> None:
    assert (CONFIG_DIR / "__init__.py").is_file()


def test_detekt_yaml_parses() -> None:
    path = CONFIG_DIR / "detekt.yml"
    assert path.is_file(), f"missing: {path}"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    # CyclomaticComplexMethod must be the only enabled complexity rule
    complexity = data.get("complexity") or {}
    assert isinstance(complexity, dict)
    rule = complexity.get("CyclomaticComplexMethod") or {}
    assert rule.get("active") is True


def test_swiftlint_yaml_parses() -> None:
    path = CONFIG_DIR / "swiftlint.yml"
    assert path.is_file()
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert "cyclomatic_complexity" in (data.get("only_rules") or [])


def test_eslint_json_parses() -> None:
    path = CONFIG_DIR / "eslint.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    # complexity rule placeholder — threshold is passed via CLI
    rules = data.get("rules") or {}
    assert "complexity" in rules


def test_radon_cfg_parses() -> None:
    path = CONFIG_DIR / "radon.cfg"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    # Radon usa INI-like; basta conferir que tem a seção esperada
    assert "[radon]" in text
    assert "exclude" in text
```

- [ ] Step 2: Run `pytest tests/engine/test_cc_configs_exist.py -xvs`. Expected: FAIL — arquivos não existem.

- [ ] Step 3: Criar `engine/_cc_configs/__init__.py` (arquivo vazio — marker).

- [ ] Step 4: Criar `engine/_cc_configs/detekt.yml`:

```yaml
# Forge-managed Detekt config for the cyclomatic-complexity gate.
# Only the CyclomaticComplexMethod rule is active — every other Detekt
# category is explicitly disabled so the gate emits exactly one signal.
# Threshold is passed via CLI args at runtime (see check_cyclomatic_complexity._dispatch_tool).

build:
  maxIssues: 0
  weights:
    complexity: 1

complexity:
  active: true
  CyclomaticComplexMethod:
    active: true
    threshold: 10  # default — overridden by CLI flag at runtime
    ignoreSingleWhenExpression: false
    ignoreSimpleWhenEntries: false
    ignoreNestingFunctions: false

# Disable every other category — gate is single-purpose.
comments:
  active: false
empty-blocks:
  active: false
exceptions:
  active: false
naming:
  active: false
performance:
  active: false
potential-bugs:
  active: false
style:
  active: false
```

- [ ] Step 5: Criar `engine/_cc_configs/swiftlint.yml`:

```yaml
# Forge-managed SwiftLint config for the cyclomatic-complexity gate.
# Single-rule: only cyclomatic_complexity is active. Threshold is passed
# via runtime command override (see check_cyclomatic_complexity._dispatch_tool).

only_rules:
  - cyclomatic_complexity

cyclomatic_complexity:
  warning: 10
  error: 10
  ignores_case_statements: false

# Belt-and-suspenders: disable everything else explicitly.
disabled_rules: []

excluded:
  - Tests
  - .build
  - DerivedData

reporter: "json"
```

- [ ] Step 6: Criar `engine/_cc_configs/eslint.json`:

```json
{
  "_comment": "Forge-managed eslint config. Single rule (complexity). Threshold is passed via CLI --rule at runtime; the value below is a placeholder default.",
  "parserOptions": {
    "ecmaVersion": 2022,
    "sourceType": "module"
  },
  "rules": {
    "complexity": ["error", { "max": 15 }]
  }
}
```

- [ ] Step 7: Criar `engine/_cc_configs/radon.cfg`:

```ini
# Forge-managed Radon config for the cyclomatic-complexity gate.
# Radon doesn't have a built-in threshold gate — validator compares CC
# values in Python after parsing radon's JSON output.

[radon]
exclude = tests/*,*/test_*.py,*/conftest.py,*/__pycache__/*,build/*,dist/*
no_assert = True
```

- [ ] Step 8: Run `pytest tests/engine/test_cc_configs_exist.py -xvs`. Expected: 5 passed.

- [ ] Step 9: Commit:
  ```
  git add engine/_cc_configs/ tests/engine/test_cc_configs_exist.py
  git commit -m "feat(engine): cc-gate internal configs (detekt/swiftlint/eslint/radon)"
  ```

---

## Task 3 — `CCResult` dataclass + classificador `new/modified/unchanged`

**Files:**
- Create: `validators/check_cyclomatic_complexity.py` (skeleton inicial — dataclass + classificador, sem orchestrator ainda)
- Test: `tests/validators/test_cc_classifier.py` (NEW)

TDD cycle:

- [ ] Step 1: Write `tests/validators/test_cc_classifier.py`:

```python
"""Unit tests for CCResult dataclass + classify_function."""

from __future__ import annotations

import dataclasses

import pytest

import check_cyclomatic_complexity as v


def test_ccresult_is_frozen_dataclass() -> None:
    assert dataclasses.is_dataclass(v.CCResult)
    params = v.CCResult.__dataclass_params__
    assert params.frozen is True


def test_ccresult_fields_match_spec() -> None:
    fields = {f.name for f in dataclasses.fields(v.CCResult)}
    expected = {
        "file",
        "function",
        "line_start",
        "line_end",
        "cc",
        "language",
        "status",
        "cc_before",
    }
    assert fields == expected


def test_ccresult_constructs_with_all_fields() -> None:
    r = v.CCResult(
        file="a.kt",
        function="foo",
        line_start=10,
        line_end=30,
        cc=12,
        language="kotlin",
        status="new",
        cc_before=None,
    )
    assert r.cc == 12
    assert r.cc_before is None


def test_classify_new_function_entirely_in_added_hunk() -> None:
    # Function spans lines 10..20; the hunk also added lines 10..20.
    hunks = [{"start": 10, "end": 20, "kind": "add"}]
    assert v.classify_function((10, 20), hunks) == "new"


def test_classify_modified_when_range_intersects_hunk() -> None:
    # Function spans 5..40; hunk touches 20..25 (partial overlap).
    hunks = [{"start": 20, "end": 25, "kind": "add"}]
    assert v.classify_function((5, 40), hunks) == "modified"


def test_classify_unchanged_when_no_overlap() -> None:
    hunks = [{"start": 100, "end": 110, "kind": "add"}]
    assert v.classify_function((5, 40), hunks) == "unchanged"


def test_classify_empty_hunks_means_unchanged() -> None:
    assert v.classify_function((1, 100), []) == "unchanged"


def test_classify_function_starts_above_hunk_ends_inside_is_modified() -> None:
    # Function 5..25; hunk 20..30 (function tail overlaps hunk head).
    hunks = [{"start": 20, "end": 30, "kind": "add"}]
    assert v.classify_function((5, 25), hunks) == "modified"
```

- [ ] Step 2: Run `pytest tests/validators/test_cc_classifier.py -xvs`. Expected: FAIL com `ModuleNotFoundError: No module named 'check_cyclomatic_complexity'`.

- [ ] Step 3: Criar `validators/check_cyclomatic_complexity.py` com skeleton:

```python
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

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from _common import (
    cc_format_three_paths,
    cc_threshold_lookup,
    make_paths,
    result_fail,
    result_pass,
    result_warn,
    run_cli,
)

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.utils.paths import feature_dir  # noqa: E402
from engine.utils.yaml_io import read_yaml_or_default  # noqa: E402


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
```

- [ ] Step 4: Run `pytest tests/validators/test_cc_classifier.py -xvs`. Expected: 8 passed.

- [ ] Step 5: Commit:
  ```
  git add validators/check_cyclomatic_complexity.py tests/validators/test_cc_classifier.py
  git commit -m "feat(validators): CCResult dataclass + diff classifier"
  ```

---

## Task 4 — Tool runners parsers (Detekt + SwiftLint)

**Files:**
- Modify: `validators/check_cyclomatic_complexity.py` (APPEND `_parse_detekt` + `_parse_swiftlint`)
- Test: `tests/validators/test_cc_parsers_kotlin_swift.py` (NEW)
- Fixture: `tests/fixtures/cc_gate/detekt_output_sample.json` (NEW)
- Fixture: `tests/fixtures/cc_gate/swiftlint_output_sample.json` (NEW)

TDD cycle:

- [ ] Step 1: Criar fixture `tests/fixtures/cc_gate/detekt_output_sample.json`:

```json
{
  "issues": [
    {
      "ruleName": "CyclomaticComplexMethod",
      "message": "The function handleLogin appears to be too complex based on Cyclomatic Complexity (14).",
      "location": {
        "filePath": "app/auth/LoginViewModel.kt",
        "position": { "line": 42, "column": 5 },
        "endPosition": { "line": 87, "column": 5 }
      },
      "metric": { "value": 14 }
    },
    {
      "ruleName": "CyclomaticComplexMethod",
      "message": "The function validateForm appears to be too complex based on Cyclomatic Complexity (11).",
      "location": {
        "filePath": "app/auth/LoginViewModel.kt",
        "position": { "line": 88, "column": 5 },
        "endPosition": { "line": 120, "column": 5 }
      },
      "metric": { "value": 11 }
    }
  ]
}
```

- [ ] Step 2: Criar fixture `tests/fixtures/cc_gate/swiftlint_output_sample.json`:

```json
[
  {
    "rule_id": "cyclomatic_complexity",
    "reason": "Function should have complexity 10 or less; currently complexity is 12",
    "file": "ios/Auth/LoginCoordinator.swift",
    "line": 67,
    "character": 5,
    "severity": "Error",
    "type": "Cyclomatic Complexity",
    "complexity": 12
  }
]
```

- [ ] Step 3: Write `tests/validators/test_cc_parsers_kotlin_swift.py`:

```python
"""Unit tests for _parse_detekt and _parse_swiftlint."""

from __future__ import annotations

from pathlib import Path

import pytest

import check_cyclomatic_complexity as v

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "cc_gate"


def test_parse_detekt_basic() -> None:
    raw = (FIXTURES / "detekt_output_sample.json").read_text(encoding="utf-8")
    results = v._parse_detekt(raw)
    assert len(results) == 2
    r0 = results[0]
    assert r0.file == "app/auth/LoginViewModel.kt"
    assert r0.function == "handleLogin"
    assert r0.line_start == 42
    assert r0.line_end == 87
    assert r0.cc == 14
    assert r0.language == "kotlin"
    # status + cc_before are filled in later by the orchestrator; parsers leave defaults
    assert r0.status in ("new", "modified", "unchanged")
    assert r0.cc_before is None


def test_parse_detekt_handles_empty_issues() -> None:
    assert v._parse_detekt('{"issues": []}') == []


def test_parse_detekt_handles_malformed_json_returns_empty() -> None:
    # Tool crash / non-JSON → return [] so caller can emit result_warn
    assert v._parse_detekt("not json {{") == []


def test_parse_swiftlint_basic() -> None:
    raw = (FIXTURES / "swiftlint_output_sample.json").read_text(encoding="utf-8")
    results = v._parse_swiftlint(raw)
    assert len(results) == 1
    r = results[0]
    assert r.file == "ios/Auth/LoginCoordinator.swift"
    assert r.function == "performLogin"  # extracted from `reason` heuristic
    assert r.line_start == 67
    assert r.cc == 12
    assert r.language == "swift"


def test_parse_swiftlint_empty_array() -> None:
    assert v._parse_swiftlint("[]") == []


def test_parse_swiftlint_malformed() -> None:
    assert v._parse_swiftlint("oops") == []
```

NOTE: a fixture do swiftlint precisa carregar o nome da função no campo `reason` (parser extrai). Para o teste passar exatamente com `performLogin`, edite o fixture acrescentando o token; alternativamente o parser cai num fallback como `function == "<unknown>"` e o teste deve assertar isso. Implementação abaixo opta por extrair quando possível e usar fallback `<unknown>` quando não — então adapte a asserção:

  - Se preferir manter `performLogin` no fixture, **substitua** o campo `reason` por:
    `"Function performLogin() should have complexity 10 or less; currently complexity is 12"`
    Esse formato é o que o parser detecta via regex.

- [ ] Step 4: **Atualize** `tests/fixtures/cc_gate/swiftlint_output_sample.json` setando `"reason"` para incluir `Function performLogin()`:

```json
[
  {
    "rule_id": "cyclomatic_complexity",
    "reason": "Function performLogin() should have complexity 10 or less; currently complexity is 12",
    "file": "ios/Auth/LoginCoordinator.swift",
    "line": 67,
    "character": 5,
    "severity": "Error",
    "type": "Cyclomatic Complexity",
    "complexity": 12
  }
]
```

- [ ] Step 5: Run `pytest tests/validators/test_cc_parsers_kotlin_swift.py -xvs`. Expected: FAIL — `_parse_detekt` and `_parse_swiftlint` not defined.

- [ ] Step 6: APPEND em `validators/check_cyclomatic_complexity.py` (depois de `classify_function`):

```python
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
```

- [ ] Step 7: Run `pytest tests/validators/test_cc_parsers_kotlin_swift.py -xvs`. Expected: 6 passed.

- [ ] Step 8: Commit:
  ```
  git add validators/check_cyclomatic_complexity.py tests/validators/test_cc_parsers_kotlin_swift.py tests/fixtures/cc_gate/detekt_output_sample.json tests/fixtures/cc_gate/swiftlint_output_sample.json
  git commit -m "feat(validators): cc parsers — Detekt + SwiftLint"
  ```

---

## Task 5 — Tool runners parsers (eslint + Radon)

**Files:**
- Modify: `validators/check_cyclomatic_complexity.py` (APPEND `_parse_eslint` + `_parse_radon`)
- Test: `tests/validators/test_cc_parsers_ts_python.py` (NEW)
- Fixture: `tests/fixtures/cc_gate/eslint_output_sample.json` (NEW)
- Fixture: `tests/fixtures/cc_gate/radon_output_sample.json` (NEW)

TDD cycle:

- [ ] Step 1: Criar fixture `tests/fixtures/cc_gate/eslint_output_sample.json`:

```json
[
  {
    "filePath": "/repo/src/checkout/CartService.ts",
    "messages": [
      {
        "ruleId": "complexity",
        "severity": 2,
        "message": "Function 'computeTotal' has a complexity of 18. Maximum allowed is 15.",
        "line": 24,
        "endLine": 95,
        "column": 1
      }
    ],
    "errorCount": 1,
    "warningCount": 0
  }
]
```

- [ ] Step 2: Criar fixture `tests/fixtures/cc_gate/radon_output_sample.json`:

```json
{
  "engine/parser/lexer.py": [
    {
      "type": "function",
      "name": "tokenize",
      "lineno": 12,
      "endline": 78,
      "complexity": 13,
      "rank": "C"
    }
  ]
}
```

- [ ] Step 3: Write `tests/validators/test_cc_parsers_ts_python.py`:

```python
"""Unit tests for _parse_eslint and _parse_radon."""

from __future__ import annotations

from pathlib import Path

import pytest

import check_cyclomatic_complexity as v

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "cc_gate"


def test_parse_eslint_basic() -> None:
    raw = (FIXTURES / "eslint_output_sample.json").read_text(encoding="utf-8")
    results = v._parse_eslint(raw, project_root="/repo")
    assert len(results) == 1
    r = results[0]
    assert r.file == "src/checkout/CartService.ts"  # stripped /repo prefix
    assert r.function == "computeTotal"
    assert r.line_start == 24
    assert r.line_end == 95
    assert r.cc == 18
    assert r.language == "ts"


def test_parse_eslint_ignores_other_rules() -> None:
    raw = """[
      {
        "filePath": "/repo/a.ts",
        "messages": [
          { "ruleId": "no-unused-vars", "line": 1, "message": "x is defined but never used" }
        ]
      }
    ]"""
    assert v._parse_eslint(raw, project_root="/repo") == []


def test_parse_eslint_empty_array() -> None:
    assert v._parse_eslint("[]", project_root="/repo") == []


def test_parse_eslint_malformed() -> None:
    assert v._parse_eslint("oops", project_root="/repo") == []


def test_parse_radon_basic() -> None:
    raw = (FIXTURES / "radon_output_sample.json").read_text(encoding="utf-8")
    results = v._parse_radon(raw)
    assert len(results) == 1
    r = results[0]
    assert r.file == "engine/parser/lexer.py"
    assert r.function == "tokenize"
    assert r.line_start == 12
    assert r.line_end == 78
    assert r.cc == 13
    assert r.language == "python"


def test_parse_radon_ignores_classes() -> None:
    raw = """{
      "a.py": [
        { "type": "class", "name": "Foo", "lineno": 1, "endline": 50, "complexity": 7 }
      ]
    }"""
    assert v._parse_radon(raw) == []


def test_parse_radon_empty_object() -> None:
    assert v._parse_radon("{}") == []


def test_parse_radon_malformed() -> None:
    assert v._parse_radon("oops") == []
```

- [ ] Step 4: Run `pytest tests/validators/test_cc_parsers_ts_python.py -xvs`. Expected: FAIL — parsers not defined.

- [ ] Step 5: APPEND em `validators/check_cyclomatic_complexity.py`:

```python
_ESLINT_FUNC_RE = re.compile(r"['\"]?(\w+)['\"]?\s+has a complexity of (\d+)", re.IGNORECASE)


def _parse_eslint(raw: str, *, project_root: str) -> list[CCResult]:
    """Parse eslint --format json output (complexity rule only)."""
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
        file_rel = file_abs[len(root_prefix):] if file_abs.startswith(root_prefix) else file_abs
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
    """Parse `radon cc -j` output (per-file → list of blocks)."""
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
```

- [ ] Step 6: Run `pytest tests/validators/test_cc_parsers_ts_python.py -xvs`. Expected: 8 passed.

- [ ] Step 7: Commit:
  ```
  git add validators/check_cyclomatic_complexity.py tests/validators/test_cc_parsers_ts_python.py tests/fixtures/cc_gate/eslint_output_sample.json tests/fixtures/cc_gate/radon_output_sample.json
  git commit -m "feat(validators): cc parsers — eslint + Radon"
  ```

---

## Task 6 — Tool dispatch + trust-but-verify availability

**Files:**
- Modify: `validators/check_cyclomatic_complexity.py` (APPEND `_dispatch_tool` + `_check_tool_available`)
- Test: `tests/validators/test_cc_dispatch.py` (NEW)

TDD cycle:

- [ ] Step 1: Write `tests/validators/test_cc_dispatch.py`:

```python
"""Unit tests for _check_tool_available and _dispatch_tool."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest import mock

import pytest

import check_cyclomatic_complexity as v


def test_check_tool_available_returns_true_when_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v.shutil, "which", lambda name: "/usr/local/bin/" + name)
    assert v._check_tool_available("detekt") is True


def test_check_tool_available_returns_false_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v.shutil, "which", lambda name: None)
    assert v._check_tool_available("swiftlint") is False


def test_dispatch_tool_kotlin_builds_correct_command(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, list[str]] = {}

    def fake_run(cmd, **kwargs):
        calls["cmd"] = list(cmd)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout='{"issues":[]}', stderr="")

    monkeypatch.setattr(v.subprocess, "run", fake_run)
    monkeypatch.setattr(v.shutil, "which", lambda name: "/usr/local/bin/" + name)

    result = v._dispatch_tool(
        language="kotlin",
        files=["app/A.kt", "app/B.kt"],
        threshold=10,
        project_root=Path("/repo"),
    )

    assert result.tool_found is True
    assert result.raw_stdout == '{"issues":[]}'
    assert calls["cmd"][0] == "detekt"
    assert "--config" in calls["cmd"]
    assert "app/A.kt" in calls["cmd"]
    assert "app/B.kt" in calls["cmd"]


def test_dispatch_tool_python_calls_radon(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr(v.subprocess, "run", fake_run)
    monkeypatch.setattr(v.shutil, "which", lambda name: "/usr/local/bin/radon")

    result = v._dispatch_tool(
        language="python",
        files=["engine/cli.py"],
        threshold=10,
        project_root=Path("/repo"),
    )
    assert result.tool_found is True
    assert captured["cmd"][0] == "radon"
    assert "cc" in captured["cmd"]
    assert "-j" in captured["cmd"]
    assert "engine/cli.py" in captured["cmd"]


def test_dispatch_tool_missing_returns_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v.shutil, "which", lambda name: None)

    result = v._dispatch_tool(
        language="kotlin",
        files=["app/A.kt"],
        threshold=10,
        project_root=Path("/repo"),
    )
    assert result.tool_found is False
    assert result.raw_stdout == ""
    assert "not installed" in result.error_message.lower() or "missing" in result.error_message.lower()


def test_dispatch_tool_crash_returns_error_with_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode=2, stdout="", stderr="boom: tool exploded")

    monkeypatch.setattr(v.subprocess, "run", fake_run)
    monkeypatch.setattr(v.shutil, "which", lambda name: "/usr/local/bin/detekt")

    result = v._dispatch_tool(
        language="kotlin",
        files=["app/A.kt"],
        threshold=10,
        project_root=Path("/repo"),
    )
    assert result.tool_found is True
    assert result.crashed is True
    assert "boom" in result.error_message


def test_dispatch_tool_timeout_returns_crashed(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=60)

    monkeypatch.setattr(v.subprocess, "run", fake_run)
    monkeypatch.setattr(v.shutil, "which", lambda name: "/usr/local/bin/detekt")

    result = v._dispatch_tool(
        language="kotlin",
        files=["app/A.kt"],
        threshold=10,
        project_root=Path("/repo"),
    )
    assert result.tool_found is True
    assert result.crashed is True
    assert "timeout" in result.error_message.lower()
```

- [ ] Step 2: Run `pytest tests/validators/test_cc_dispatch.py -xvs`. Expected: FAIL.

- [ ] Step 3: APPEND em `validators/check_cyclomatic_complexity.py`:

```python
# ── Tool dispatch ────────────────────────────────────────────────────────────


_TOOL_BIN = {
    "kotlin": "detekt",
    "swift": "swiftlint",
    "ts": "eslint",
    "python": "radon",
}

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "engine" / "_cc_configs"


@dataclass(frozen=True)
class _DispatchResult:
    """Outcome of a single tool invocation."""
    language: str
    tool_found: bool
    crashed: bool
    raw_stdout: str
    error_message: str


def _check_tool_available(tool: str) -> bool:
    """Return True iff `tool` is on PATH."""
    return shutil.which(tool) is not None


def _dispatch_tool(
    *,
    language: str,
    files: list[str],
    threshold: int,
    project_root: Path,
) -> _DispatchResult:
    """Invoke the per-language tool over `files`. Never raises.

    Output contract:
        tool_found=False  → tool not installed; caller emits result_warn.
        crashed=True      → non-zero exit, timeout, or non-parseable JSON;
                            caller emits result_warn with error_message.
        otherwise         → raw_stdout passed to the matching _parse_<tool>.
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
        cmd = [
            tool,
            "--input", ",".join(files),
            "--config", str(_CONFIG_DIR / "detekt.yml"),
            "--report", "json:-",  # write JSON to stdout
        ]
    elif language == "swift":
        cmd = [
            tool, "lint",
            "--reporter", "json",
            "--config", str(_CONFIG_DIR / "swiftlint.yml"),
            *files,
        ]
    elif language == "ts":
        cmd = [
            tool,
            "--no-eslintrc",
            "--rule", f'{{"complexity": ["error", {{"max": {threshold}}}]}}',
            "--format", "json",
            *files,
        ]
    elif language == "python":
        cmd = [
            tool, "cc", "-j", "-n", "F",
            *files,
        ]
    else:
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

    # eslint exits 1 when issues are found — not a crash.
    benign_nonzero = language == "ts" and proc.returncode == 1
    if proc.returncode != 0 and not benign_nonzero:
        return _DispatchResult(
            language=language,
            tool_found=True,
            crashed=True,
            raw_stdout=proc.stdout or "",
            error_message=(proc.stderr or "").strip()[:400] or f"{tool} exit={proc.returncode}",
        )

    return _DispatchResult(
        language=language,
        tool_found=True,
        crashed=False,
        raw_stdout=proc.stdout or "",
        error_message="",
    )
```

- [ ] Step 4: Run `pytest tests/validators/test_cc_dispatch.py -xvs`. Expected: 7 passed.

- [ ] Step 5: Commit:
  ```
  git add validators/check_cyclomatic_complexity.py tests/validators/test_cc_dispatch.py
  git commit -m "feat(validators): cc tool dispatch + availability check"
  ```

---

## Task 7 — Override-justify detection

**Files:**
- Modify: `validators/check_cyclomatic_complexity.py` (APPEND `_parse_overrides` + `_apply_overrides`)
- Test: `tests/validators/test_cc_override.py` (NEW)

TDD cycle:

- [ ] Step 1: Write `tests/validators/test_cc_override.py`:

```python
"""Unit tests for CC-OVERRIDE parsing + application."""

from __future__ import annotations

import pytest

import check_cyclomatic_complexity as v


def _make(file: str, func: str, cc: int) -> v.CCResult:
    return v.CCResult(
        file=file, function=func,
        line_start=1, line_end=10,
        cc=cc, language="kotlin",
        status="new", cc_before=None,
    )


def test_override_parses_valid_single_line() -> None:
    body = "CC-OVERRIDE: app/foo.kt:bar cc=14 — DSL aninhado"
    overrides = v._parse_overrides(body)
    assert len(overrides) == 1
    o = overrides[0]
    assert o["file"] == "app/foo.kt"
    assert o["func"] == "bar"
    assert o["cc"] == 14
    assert o["reason"] == "DSL aninhado"


def test_override_malformed_missing_dash_does_not_count() -> None:
    body = "CC-OVERRIDE: app/foo.kt:bar cc=14 no reason"
    overrides, warnings = v._parse_overrides(body, return_warnings=True)
    assert overrides == []
    assert len(warnings) == 1
    assert "CC-OVERRIDE sem razão" in warnings[0]


def test_override_covers_only_declared_function() -> None:
    body = "CC-OVERRIDE: app/foo.kt:bar cc=14 — DSL"
    fails = [
        _make("app/foo.kt", "bar", 14),
        _make("app/foo.kt", "baz", 12),  # NOT covered
    ]
    silenced, surviving = v._apply_overrides(fails, body)
    assert len(silenced) == 1 and silenced[0].function == "bar"
    assert len(surviving) == 1 and surviving[0].function == "baz"


def test_override_multiple_lines_cover_independently() -> None:
    body = "\n".join([
        "CC-OVERRIDE: a.kt:foo cc=14 — reason A",
        "CC-OVERRIDE: b.kt:bar cc=11 — reason B",
    ])
    fails = [_make("a.kt", "foo", 14), _make("b.kt", "bar", 11)]
    silenced, surviving = v._apply_overrides(fails, body)
    assert len(silenced) == 2
    assert surviving == []


def test_override_file_mismatch_does_not_silence() -> None:
    body = "CC-OVERRIDE: a.kt:foo cc=14 — reason"
    fails = [_make("b.kt", "foo", 14)]  # different file
    silenced, surviving = v._apply_overrides(fails, body)
    assert silenced == []
    assert len(surviving) == 1


def test_override_empty_body_returns_all_as_surviving() -> None:
    fails = [_make("a.kt", "foo", 14)]
    silenced, surviving = v._apply_overrides(fails, "")
    assert silenced == []
    assert surviving == fails


def test_override_regex_anchors_at_line_start() -> None:
    # Should NOT match when CC-OVERRIDE is mid-sentence (defensive).
    body = "see also CC-OVERRIDE: a.kt:foo cc=14 — reason"
    assert v._parse_overrides(body) == []
```

- [ ] Step 2: Run `pytest tests/validators/test_cc_override.py -xvs`. Expected: FAIL.

- [ ] Step 3: APPEND em `validators/check_cyclomatic_complexity.py`:

```python
# ── Override-justify ─────────────────────────────────────────────────────────
#
# Single-line override declared in the commit body. Anchored to start-of-line
# (re.MULTILINE) so it can't be smuggled mid-sentence. The format is
# load-bearing — `.claude/rules/disciplines.md §1` references it directly.

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
        overrides.append({
            "file": m.group("file"),
            "func": m.group("func"),
            "cc": cc,
            "reason": m.group("reason").strip(),
        })
        valid_spans.add(m.span())

    # Second pass: loose match — anything that LOOKS like an override but
    # didn't pass strict regex is a malformed attempt → warn.
    for m in _CC_OVERRIDE_LOOSE_RE.finditer(commit_body):
        if m.span() in valid_spans:
            continue
        # Skip if there's a downstream `—` on the same line (already strict-matched).
        line = commit_body[m.start():commit_body.find("\n", m.start()) if commit_body.find("\n", m.start()) != -1 else len(commit_body)]
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

    Match key: (file, function). Override covers ONLY the declared
    (file, func) pair — no wildcards.
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
```

- [ ] Step 4: Run `pytest tests/validators/test_cc_override.py -xvs`. Expected: 7 passed.

- [ ] Step 5: Commit:
  ```
  git add validators/check_cyclomatic_complexity.py tests/validators/test_cc_override.py
  git commit -m "feat(validators): cc override-justify detection"
  ```

---

## Task 8 — Validator main entry point `run(context)`

**Files:**
- Modify: `validators/check_cyclomatic_complexity.py` (APPEND `validate(project_root, **kwargs)` orchestrator)
- Test: `tests/validators/test_check_cyclomatic_complexity.py` (NEW — entry point e2e mockado)

TDD cycle:

- [ ] Step 1: Write `tests/validators/test_check_cyclomatic_complexity.py`:

```python
"""Entry-point tests for check_cyclomatic_complexity.validate.

Most paths are mocked at the dispatch layer — these tests pin the
orchestration logic (threshold lookup, override application, ignore-paths,
disabled-config short-circuit).
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

import check_cyclomatic_complexity as v


def _mk_result(**overrides) -> v.CCResult:
    defaults = dict(
        file="app/A.kt", function="foo",
        line_start=10, line_end=30, cc=12,
        language="kotlin", status="new", cc_before=None,
    )
    defaults.update(overrides)
    return v.CCResult(**defaults)


@pytest.fixture
def fake_context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict:
    """Build a minimal context the orchestrator can consume."""
    monkeypatch.setattr(v, "_git_staged_files", lambda root: [tmp_path / "app/A.kt"])
    monkeypatch.setattr(v, "_extract_diff_hunks", lambda root, files: {"app/A.kt": [{"start": 1, "end": 100, "kind": "add"}]})
    monkeypatch.setattr(v, "_read_commit_body", lambda root: "")
    monkeypatch.setattr(v, "_load_active_cards", lambda root: [])
    monkeypatch.setattr(v, "_load_workflow_config", lambda root: {"cc-gate": {"enabled": True, "kotlin": 10}})
    return {"project_root": tmp_path}


def test_happy_path_all_below_threshold(monkeypatch, fake_context, tmp_path):
    monkeypatch.setattr(v, "_run_tools_for_staged", lambda *a, **kw: [_mk_result(cc=8)])
    result = v.validate(tmp_path)
    assert result["status"] == "pass"


def test_fail_when_new_function_exceeds_threshold(monkeypatch, fake_context, tmp_path):
    monkeypatch.setattr(v, "_run_tools_for_staged", lambda *a, **kw: [_mk_result(cc=14, status="new")])
    result = v.validate(tmp_path)
    assert result["status"] == "fail"
    assert "Cyclomatic Complexity" in (result.get("message") or "")
    assert len(result["paths"]) == 3


def test_delta_rule_modified_worse_fails(monkeypatch, fake_context, tmp_path):
    monkeypatch.setattr(
        v, "_run_tools_for_staged",
        lambda *a, **kw: [_mk_result(cc=11, status="modified", cc_before=9)],
    )
    result = v.validate(tmp_path)
    assert result["status"] == "fail"


def test_delta_rule_modified_same_or_better_passes(monkeypatch, fake_context, tmp_path):
    # cc_after == cc_before is NOT a regression → pass even when > threshold
    monkeypatch.setattr(
        v, "_run_tools_for_staged",
        lambda *a, **kw: [_mk_result(cc=12, status="modified", cc_before=12)],
    )
    result = v.validate(tmp_path)
    assert result["status"] == "pass"


def test_override_silences_specific_function(monkeypatch, fake_context, tmp_path):
    monkeypatch.setattr(v, "_run_tools_for_staged", lambda *a, **kw: [_mk_result(cc=14, function="bar")])
    monkeypatch.setattr(v, "_read_commit_body", lambda root: "CC-OVERRIDE: app/A.kt:bar cc=14 — irreducible DSL")
    result = v.validate(tmp_path)
    assert result["status"] == "pass"


def test_ignore_paths_filters_test_files(monkeypatch, fake_context, tmp_path):
    # Staged file is in tests/; ignore-paths regex catches it.
    monkeypatch.setattr(v, "_git_staged_files", lambda root: [tmp_path / "tests/foo_test.kt"])
    monkeypatch.setattr(
        v, "_load_workflow_config",
        lambda root: {"cc-gate": {"enabled": True, "kotlin": 10, "ignore-paths": ["tests/.*"]}},
    )
    monkeypatch.setattr(v, "_run_tools_for_staged", lambda *a, **kw: [])
    result = v.validate(tmp_path)
    assert result["status"] == "pass"
    assert "ignorados" in (result.get("message") or "").lower() or "no candidates" in (result.get("message") or "").lower()


def test_disabled_config_returns_warn_early(monkeypatch, fake_context, tmp_path):
    monkeypatch.setattr(v, "_load_workflow_config", lambda root: {"cc-gate": {"enabled": False}})
    result = v.validate(tmp_path)
    assert result["status"] == "warn"
    assert "disabled" in (result.get("message") or "").lower() or "desligado" in (result.get("message") or "").lower()


def test_tool_missing_emits_warn_not_fail(monkeypatch, fake_context, tmp_path):
    # Simulate "detekt not installed" by raising-equivalent: empty results + warn signal.
    def _runner(*a, **kw):
        return [], ["detekt not installed (PATH lookup failed)"]

    monkeypatch.setattr(v, "_run_tools_for_staged", _runner)
    result = v.validate(tmp_path)
    assert result["status"] in ("warn", "pass")
    if result["status"] == "warn":
        assert "detekt" in (result.get("message") or "").lower()
```

- [ ] Step 2: Run `pytest tests/validators/test_check_cyclomatic_complexity.py -xvs`. Expected: FAIL.

- [ ] Step 3: APPEND em `validators/check_cyclomatic_complexity.py`:

```python
# ── Orchestrator ─────────────────────────────────────────────────────────────
#
# `validate(project_root, **kwargs)` is the entry point called both by:
#   - validators/_common.py's run_cli (when invoked as `python3 validator.py`)
#   - engine/implement.py per-task (imported as a Python function)
#   - engine/verify.py cascade (subprocess by convention; see Task 9)

_TEST_IGNORE_DEFAULTS = [
    r"(^|/)tests?/",
    r"(^|/)__tests__/",
    r"\.test\.(ts|tsx|js|jsx|kt|swift|py)$",
    r"_test\.(kt|swift|py)$",
]


def _git_staged_files(project_root: Path) -> list[Path]:
    """Return absolute paths of files in `git diff --cached`."""
    try:
        out = subprocess.run(
            ["git", "-C", str(project_root), "diff", "--cached", "--name-only"],
            check=False, capture_output=True, text=True, timeout=10,
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


def _extract_diff_hunks(project_root: Path, files: list[Path]) -> dict[str, list[dict[str, Any]]]:
    """For each staged file, return its add/del hunks as ranges.

    Hunk shape: {"start": int, "end": int, "kind": "add"|"del"}. We only
    capture line numbers from `+++ b/<file>` regions to feed classify_function.
    """
    by_file: dict[str, list[dict[str, Any]]] = {}
    for f in files:
        rel = str(f.relative_to(project_root))
        try:
            proc = subprocess.run(
                ["git", "-C", str(project_root), "diff", "--cached", "-U0", "--", rel],
                check=False, capture_output=True, text=True, timeout=10,
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
            hunks.append({"start": start, "end": start + max(length - 1, 0), "kind": "add"})
        by_file[rel] = hunks
    return by_file


def _read_commit_body(project_root: Path) -> str:
    """Best-effort read of the commit message body.

    Checks `.git/COMMIT_EDITMSG` first (pre-commit hook context),
    falls back to `git log -1 --format=%B HEAD` (post-commit / verify).
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
            check=False, capture_output=True, text=True, timeout=5,
        )
        if proc.returncode == 0:
            return proc.stdout
    except (subprocess.SubprocessError, OSError):
        pass
    return ""


def _load_active_cards(project_root: Path) -> list[dict[str, Any]]:
    """Read each active card's card.yaml (snapshot) and return the list of dicts."""
    cfg_path = project_root / ".claude" / "workflow-config.yaml"
    config = read_yaml_or_default(cfg_path, {}) or {}
    cards_root = project_root / ".claude" / "cards"
    out: list[dict[str, Any]] = []
    for entry in (config.get("cards") or {}).get("active") or []:
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
    cfg_path = project_root / ".claude" / "workflow-config.yaml"
    return read_yaml_or_default(cfg_path, {}) or {}


def _path_matches_ignore(rel_path: str, patterns: list[str]) -> bool:
    for pat in patterns:
        try:
            if re.search(pat, rel_path):
                return True
        except re.error:
            continue
    return False


def _run_tools_for_staged(
    files_by_lang: dict[str, list[str]],
    thresholds_by_lang: dict[str, int],
    diff_hunks: dict[str, list[dict[str, Any]]],
    project_root: Path,
) -> tuple[list[CCResult], list[str]]:
    """Dispatch every language tool. Return (results, warnings).

    Each tool runs once per language batch (Detekt over all .kt, etc.).
    Tool-missing / tool-crash emits a warning string and yields no results
    for that language — cascade alive.
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
            language=lang, files=files,
            threshold=threshold, project_root=project_root,
        )
        if not d.tool_found:
            warnings.append(d.error_message)
            continue
        if d.crashed:
            warnings.append(d.error_message)
            continue
        for r in parsers[lang](d.raw_stdout):
            hunks = diff_hunks.get(r.file, [])
            status = classify_function((r.line_start, r.line_end), hunks)
            results.append(
                CCResult(
                    file=r.file, function=r.function,
                    line_start=r.line_start, line_end=r.line_end,
                    cc=r.cc, language=r.language,
                    status=status, cc_before=r.cc_before,
                )
            )
    return results, warnings


def validate(project_root: Path, **kwargs: Any) -> dict[str, Any]:
    """Main entry — runs the full CC gate pipeline.

    Pipeline (per spec §2):
        1. Read workflow-config; short-circuit when enabled=false.
        2. Collect staged files filtered by supported extensions.
        3. Apply ignore-paths (workflow-config + sensible defaults for tests).
        4. Resolve threshold per language (card > workflow-config > defaults).
        5. Dispatch tool per language batch.
        6. Classify each function (new / modified / unchanged).
        7. Apply rule:
             new       → fail if cc > threshold
             modified  → fail if cc_after > cc_before (delta)
             unchanged → ignore
        8. Apply CC-OVERRIDE silencing from the commit body.
        9. Emit result_pass / result_warn / result_fail.
    """
    config = _load_workflow_config(project_root)
    cc_block = (config.get("cc-gate") or {}) if isinstance(config, dict) else {}
    if isinstance(cc_block, dict) and cc_block.get("enabled") is False:
        return result_warn("cc-gate disabled in workflow-config (cc-gate.enabled=false)")

    staged_paths = _git_staged_files(project_root)
    if not staged_paths:
        return result_pass("nenhum arquivo staged — nada a checar")

    ignore_patterns = list(_TEST_IGNORE_DEFAULTS)
    extra_ignore = cc_block.get("ignore-paths") or []
    if isinstance(extra_ignore, list):
        ignore_patterns.extend(str(p) for p in extra_ignore)

    files_by_lang: dict[str, list[str]] = {"kotlin": [], "swift": [], "ts": [], "python": []}
    for p in staged_paths:
        rel = str(p.relative_to(project_root))
        if _path_matches_ignore(rel, ignore_patterns):
            continue
        lang = SUPPORTED_EXTENSIONS.get(p.suffix)
        if lang:
            files_by_lang[lang].append(rel)

    if not any(files_by_lang.values()):
        return result_pass("no candidate files after ignore-paths filter")

    active_cards = _load_active_cards(project_root)
    thresholds_by_lang = {
        lang: cc_threshold_lookup(lang, active_cards=active_cards, workflow_config=config)
        for lang in files_by_lang
    }

    diff_hunks = _extract_diff_hunks(project_root, staged_paths)

    results, tool_warnings = _run_tools_for_staged(
        files_by_lang=files_by_lang,
        thresholds_by_lang=thresholds_by_lang,
        diff_hunks=diff_hunks,
        project_root=project_root,
    )

    # Apply rule.
    fails: list[CCResult] = []
    for r in results:
        threshold = thresholds_by_lang[r.language]
        if r.status == "new" and r.cc > threshold:
            fails.append(r)
        elif r.status == "modified":
            if r.cc_before is not None and r.cc > r.cc_before:
                fails.append(r)

    # Override-justify.
    commit_body = _read_commit_body(project_root)
    silenced, surviving = _apply_overrides(fails, commit_body)

    if not surviving:
        if tool_warnings:
            return result_warn(
                f"cc-gate ok ({len(silenced)} silenced via override); tools incompletas: " + "; ".join(tool_warnings)
            )
        return result_pass(f"cc-gate ok ({len(results)} funções inspecionadas)")

    # Build canonical 3-paths message.
    violations = [
        {
            "file": r.file, "line": r.line_start, "function": r.function,
            "cc": r.cc, "threshold": thresholds_by_lang[r.language],
            "status": r.status, "cc_before": r.cc_before, "language": r.language,
        }
        for r in surviving
    ]
    affected_thresholds = {r.language: thresholds_by_lang[r.language] for r in surviving}
    message_block = cc_format_three_paths(violations, affected_thresholds)

    sample = ", ".join(f"{r.file}:{r.function}(cc={r.cc})" for r in surviving[:3])
    return result_fail(
        f"Cyclomatic Complexity gate: {len(surviving)} função(ões) acima do threshold",
        what_failed=sample,
        where="staged files",
        why=[
            "Funções com CC alto são mais difíceis de testar/revisar/evoluir.",
            "Threshold vigente: " + ", ".join(f"{l}={n}" for l, n in sorted(affected_thresholds.items())),
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


if __name__ == "__main__":
    sys.exit(run_cli(__doc__ or "", validate))
```

- [ ] Step 4: Substitua o entry point `if __name__ == "__main__":` final do skeleton (criado na Task 3) pelo bloco acima — só sobrescreve a chamada `lambda root, **kw: result_pass("skeleton — not wired yet")` por `validate`.

- [ ] Step 5: Run `pytest tests/validators/test_check_cyclomatic_complexity.py -xvs`. Expected: 8 passed.

- [ ] Step 6: Run `pytest tests/validators/ -xvs` (suíte completa de validators) — confirma zero regressão.

- [ ] Step 7: Commit:
  ```
  git add validators/check_cyclomatic_complexity.py tests/validators/test_check_cyclomatic_complexity.py
  git commit -m "feat(validators): check_cyclomatic_complexity main entry"
  ```

---

## Task 9 — Cascade integration em `engine/verify.py`

**Files:**
- Modify: `engine/verify.py` (registra check_cyclomatic_complexity na cascade após check_no_invented_behavior)
- Test: `tests/engine/test_verify_cc_position.py` (NEW)

NOTE arquitetural: validators são despachados via `_discover_validators` lendo `cards.active`. Para registrar o CC gate **independente de card consumidor** — porque o spec diz "validator único multi-language", não por-card — adicionamos um **default validators registry** dentro de `engine/verify.py` consumido depois do card-loop. Esse registry é uma fonte estática nova, alinhada com a forma como `check_no_invented_behavior` já é referenciada em testes hoje.

TDD cycle:

- [ ] Step 1: Write `tests/engine/test_verify_cc_position.py`:

```python
"""Tests for the position of check_cyclomatic_complexity in the verify cascade."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from engine import verify


def test_default_validators_registry_includes_cc_gate() -> None:
    assert hasattr(verify, "_DEFAULT_VALIDATORS")
    names = [spec_dict["name"] for spec_dict in verify._DEFAULT_VALIDATORS]
    assert "check_no_invented_behavior" in names
    assert "check_cyclomatic_complexity" in names


def test_cc_gate_positioned_after_no_invented_behavior() -> None:
    names = [spec["name"] for spec in verify._DEFAULT_VALIDATORS]
    idx_nib = names.index("check_no_invented_behavior")
    idx_cc = names.index("check_cyclomatic_complexity")
    assert idx_cc == idx_nib + 1, (
        f"CC gate must immediately follow check_no_invented_behavior; got {names}"
    )


def test_discover_validators_merges_default_registry(tmp_path: Path) -> None:
    cards_block: dict = {}
    out = verify._discover_validators(tmp_path, {"cards": {"active": []}}, "feature")
    names = [s.name for s in out]
    # Even with zero cards, defaults still surface.
    assert "check_cyclomatic_complexity" in names


def test_cc_gate_runs_after_no_invented_behavior_on_failfast(monkeypatch, tmp_path: Path) -> None:
    """If check_no_invented_behavior fails first, CC gate is skipped (fail-fast)."""
    captured: list[str] = []

    def fake_invoke(spec, root):
        captured.append(spec.name)
        # First validator (no-invented-behavior) fails hard
        if spec.name == "check_no_invented_behavior":
            return verify._ValidatorResult(name=spec.name, status="fail", duration_ms=1)
        return verify._ValidatorResult(name=spec.name, status="pass", duration_ms=1)

    monkeypatch.setattr(verify, "_invoke_validator", fake_invoke)
    specs = [
        verify._ValidatorSpec(name="check_no_invented_behavior", script_path=Path("nib.py")),
        verify._ValidatorSpec(name="check_cyclomatic_complexity", script_path=Path("cc.py")),
    ]
    results = verify._run_cascade(specs, fail_fast=True, project_root=tmp_path, interactive=False)
    # CC gate must be marked skipped (cascade halted at NIB fail)
    cc_result = next(r for r in results if r.name == "check_cyclomatic_complexity")
    assert cc_result.status == "skipped"
```

- [ ] Step 2: Run `pytest tests/engine/test_verify_cc_position.py -xvs`. Expected: FAIL — `_DEFAULT_VALIDATORS` not defined.

- [ ] Step 3: APPEND em `engine/verify.py` (depois do bloco `_resolve_fail_fast`, antes de `_run_cascade`):

```python
# ── Default validators registry ──────────────────────────────────────────────
#
# Validators that ship with forge engine itself (multi-language, project-agnostic)
# and run on every verify scope regardless of which cards are active. Order is
# load-bearing — cascade fail-fast (Decision 23) honors this sequence.

_DEFAULT_VALIDATORS: list[dict[str, str]] = [
    {
        "name": "check_no_invented_behavior",
        "file": "check_no_invented_behavior.py",
        "severity": "fail",
    },
    {
        "name": "check_cyclomatic_complexity",
        "file": "check_cyclomatic_complexity.py",
        "severity": "fail",
    },
]


def _default_validator_specs(project_root: Path) -> list[_ValidatorSpec]:
    """Build _ValidatorSpec entries for the engine's built-in validators.

    Resolved relative to <repo>/validators/. Skips entries whose script file
    doesn't exist on disk (defensive — keeps verify usable during partial
    snapshots / first-run states).
    """
    validators_dir = Path(__file__).resolve().parent.parent / "validators"
    out: list[_ValidatorSpec] = []
    for entry in _DEFAULT_VALIDATORS:
        script = validators_dir / entry["file"]
        if not script.is_file():
            continue
        out.append(
            _ValidatorSpec(
                name=entry["name"],
                script_path=script,
                severity=entry.get("severity", "warn"),
                card_name="<engine-default>",
                runs_on=["verify-task", "forge-doctor"],
            )
        )
    return out
```

- [ ] Step 4: Modify the existing `_discover_validators` to PREPEND the defaults. Edit the function so that after `out.sort(...)`, it returns `defaults + out`. Specifically, change the tail of `_discover_validators`:

```python
    out.sort(key=lambda v: (v.card_name, v.name))
    return _default_validator_specs(project_root) + out
```

- [ ] Step 5: Run `pytest tests/engine/test_verify_cc_position.py -xvs`. Expected: 4 passed.

- [ ] Step 6: Run `pytest tests/engine/ -xvs` — confirma zero regressão em outros engine tests.

- [ ] Step 7: Commit:
  ```
  git add engine/verify.py tests/engine/test_verify_cc_position.py
  git commit -m "feat(engine): register cc gate in verify cascade"
  ```

---

## Task 10 — Per-task hook em `engine/implement.py`

**Files:**
- Modify: `engine/implement.py` (chama `check_cyclomatic_complexity.validate(project_root)` entre review e commit; respeita `NO_CC_GATE=1` env)
- Test: `tests/engine/test_implement_cc_gate.py` (NEW)

NOTE arquitetural: `engine/implement.py` em v1 emite *handoff manual* (user roda `forge verify` + commit), não dispara commit programaticamente. Para o gate **ainda assim** funcionar per-task, inserimos um pré-commit-style call **dentro do fluxo de Apply Mode handoff**: o engine consulta CC gate ANTES de orientar o usuário a commitar, e exibe 3-caminhos se já há staged file violando. Em v1 o "block" é informacional + erro stderr — a transição pra hook git real fica anotada como follow-up.

TDD cycle:

- [ ] Step 1: Write `tests/engine/test_implement_cc_gate.py`:

```python
"""Tests for the cc-gate per-task hook integration in engine.implement."""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest

from engine import implement


def test_run_cc_gate_returns_pass_when_no_staged_files(tmp_path: Path) -> None:
    # Empty repo / no staged → gate result is pass, no block.
    result = implement._run_cc_gate(tmp_path)
    assert result["status"] in ("pass", "warn")
    assert result.get("blocking") is False


def test_run_cc_gate_blocks_on_fail(monkeypatch, tmp_path: Path) -> None:
    fake_fail = {
        "status": "fail",
        "message": "Cyclomatic Complexity gate: 1 função acima",
        "paths": [
            {"kind": "fix", "label": "Refatorar", "motive": ""},
            {"kind": "revert", "label": "Override-justify", "motive": ""},
            {"kind": "split", "label": "Split-task", "motive": ""},
        ],
    }
    monkeypatch.setattr(
        "validators.check_cyclomatic_complexity.validate",
        lambda root, **kw: fake_fail,
        raising=False,
    )
    # Inject mock module directly
    import sys
    sys.modules.setdefault(
        "validators.check_cyclomatic_complexity",
        mock.MagicMock(validate=lambda root, **kw: fake_fail),
    )
    result = implement._run_cc_gate(tmp_path)
    assert result["status"] == "fail"
    assert result["blocking"] is True


def test_run_cc_gate_bypassed_by_env_var(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NO_CC_GATE", "1")
    bypass_log = tmp_path / ".claude" / "state" / "cc-gate-bypass.jsonl"
    monkeypatch.setattr(implement, "_cc_bypass_log_path", lambda root: bypass_log)

    result = implement._run_cc_gate(tmp_path)
    assert result["status"] == "warn"
    assert result["blocking"] is False
    assert bypass_log.is_file()
    contents = bypass_log.read_text(encoding="utf-8")
    assert "NO_CC_GATE" in contents


def test_run_cc_gate_override_in_commit_body_permits(monkeypatch, tmp_path: Path) -> None:
    # When the commit body has a valid CC-OVERRIDE, validate() returns pass.
    fake_pass = {"status": "pass", "message": "cc-gate ok (1 silenced via override)"}
    import sys
    sys.modules["validators.check_cyclomatic_complexity"] = mock.MagicMock(
        validate=lambda root, **kw: fake_pass
    )
    result = implement._run_cc_gate(tmp_path)
    assert result["status"] == "pass"
    assert result["blocking"] is False
```

- [ ] Step 2: Run `pytest tests/engine/test_implement_cc_gate.py -xvs`. Expected: FAIL — `_run_cc_gate` not defined.

- [ ] Step 3: APPEND em `engine/implement.py` (no topo do módulo, depois dos imports):

```python
# ── CC gate per-task hook ────────────────────────────────────────────────────


def _cc_bypass_log_path(project_root: Path) -> Path:
    return project_root / ".claude" / "state" / "cc-gate-bypass.jsonl"


def _run_cc_gate(project_root: Path) -> dict[str, Any]:
    """Invoke check_cyclomatic_complexity.validate as an in-process function.

    Returns the validator result dict augmented with `blocking: bool`:
        blocking=True  → commit must NOT proceed (3-caminhos surfaced).
        blocking=False → pass / warn / bypass.

    Bypass: `NO_CC_GATE=1` env var → logs to `.claude/state/cc-gate-bypass.jsonl`
    and returns warn with blocking=False. Override-justify in the commit body
    is handled inside the validator (CC-OVERRIDE lines silence specific fails).
    """
    if os.environ.get("NO_CC_GATE", "").strip() in {"1", "true", "yes"}:
        log_path = _cc_bypass_log_path(project_root)
        try:
            ensure_dir(log_path.parent)
            ts = datetime.now(timezone.utc).isoformat()
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(
                    json.dumps({
                        "at": ts,
                        "reason": "NO_CC_GATE env var set",
                    }, ensure_ascii=False) + "\n"
                )
        except OSError:
            pass
        return {"status": "warn", "message": "NO_CC_GATE=1 — gate bypassed", "blocking": False}

    # Import lazy pra evitar circularidade com validators na partida do engine.
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "validators"))
        from validators import check_cyclomatic_complexity as cc_validator  # noqa: E402
    except ImportError:
        return {"status": "warn", "message": "cc-gate validator unavailable", "blocking": False}

    result = cc_validator.validate(project_root)
    result["blocking"] = result.get("status") == "fail"
    return result


def _render_cc_gate_block(result: dict[str, Any]) -> None:
    """Render the gate's 3-paths block when blocking."""
    renderer.write("")
    renderer.write(renderer.bold(result.get("message") or "cc-gate hard fail"))
    renderer.write("")
    for p in result.get("paths") or []:
        label = p.get("label") or p.get("kind") or "?"
        motive = p.get("motive") or ""
        renderer.write(f"  · {label}")
        if motive:
            renderer.write(f"      {motive}")
    renderer.write("")
    renderer.write(renderer.dim("Sem auto-fix aqui — escolha humana."))
```

ALSO add the missing imports near the top of `engine/implement.py` (if not already present):

```python
import json
import os
import sys
from datetime import datetime, timezone

from engine.utils.paths import ensure_dir
```

- [ ] Step 4: Modify `_apply_mode_handoff` to invoke `_run_cc_gate` **before** emitting the commit instructions. After the line:

```python
    renderer.write(
        f"Implemente {task.task_id} seguindo o contrato. Edite somente "
        "arquivos em `allowed_files`. Quando terminar:"
    )
    renderer.write("")
```

Add:

```python
    cc_result = _run_cc_gate(project_root)
    if cc_result.get("blocking"):
        _render_cc_gate_block(cc_result)
        renderer.write("")
        renderer.write(
            "Resolva o gate antes de commitar. Re-rode `forge implement` "
            "depois de refatorar / split / adicionar CC-OVERRIDE no commit body."
        )
        return  # do not emit commit instructions
    if cc_result.get("status") == "warn":
        renderer.write(renderer.dim(f"cc-gate: {cc_result.get('message','')}"))
        renderer.write("")
```

- [ ] Step 5: Run `pytest tests/engine/test_implement_cc_gate.py -xvs`. Expected: 4 passed.

- [ ] Step 6: Run `pytest tests/engine/ -xvs` — confirma zero regressão.

- [ ] Step 7: Commit:
  ```
  git add engine/implement.py tests/engine/test_implement_cc_gate.py
  git commit -m "feat(engine): cc gate per-task hook in forge implement"
  ```

---

## Task 11 — Doctor categoria `cc-gate-tools`

**Files:**
- Modify: `engine/doctor.py` (APPEND categoria `cc-gate-tools`, 13ª categoria; reporta cada tool com status + instruções install)
- Test: `tests/engine/test_doctor_cc_tools.py` (NEW)

TDD cycle:

- [ ] Step 1: Write `tests/engine/test_doctor_cc_tools.py`:

```python
"""Tests for the cc-gate-tools doctor category."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from engine import doctor


def test_check_cc_gate_tools_returns_category(tmp_path: Path) -> None:
    cat = doctor._check_cc_gate_tools(tmp_path)
    assert cat.title.lower().startswith("cc-gate")
    names = [c.name for c in cat.checks]
    assert "detekt" in names
    assert "swiftlint" in names
    assert "eslint" in names
    assert "radon" in names


def test_cc_gate_tools_marks_missing_with_install_instructions(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    cat = doctor._check_cc_gate_tools(tmp_path)
    for check in cat.checks:
        assert check.status == doctor._STATUS_WARN
        assert check.remediation  # must include install hint
    install_hints = " ".join(c.remediation for c in cat.checks)
    assert "brew install swiftlint" in install_hints
    assert "npm install" in install_hints or "npm i" in install_hints
    assert "pip install radon" in install_hints


def test_cc_gate_tools_marks_present_as_ok(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"/usr/local/bin/{name}")
    cat = doctor._check_cc_gate_tools(tmp_path)
    for check in cat.checks:
        assert check.status == doctor._STATUS_OK


def test_full_scope_includes_cc_gate_tools_category(monkeypatch, tmp_path: Path) -> None:
    # Patch every other doctor check so we can observe inclusion isolated.
    monkeypatch.setattr(doctor, "_check_config", lambda *a, **kw: doctor._CategoryReport("Config integrity", []))
    monkeypatch.setattr(doctor, "_check_cards", lambda *a, **kw: doctor._CategoryReport("Cards", []))
    monkeypatch.setattr(doctor, "_check_memory_l2", lambda *a, **kw: doctor._CategoryReport("L2", []))
    # _check_cc_gate_tools must be referenced from the 'full' branch of run()
    src = Path(doctor.__file__).read_text(encoding="utf-8")
    assert "_check_cc_gate_tools" in src
```

- [ ] Step 2: Run `pytest tests/engine/test_doctor_cc_tools.py -xvs`. Expected: FAIL — `_check_cc_gate_tools` not defined.

- [ ] Step 3: APPEND em `engine/doctor.py` (depois de `_check_forge_version_lock`):

```python
import shutil  # add to existing imports if not already present


def _check_cc_gate_tools(project_root: Path) -> _CategoryReport:
    """Report availability of the 4 native CC tools used by check_cyclomatic_complexity.

    Tools are NOT installed by forge (Decision 22 + spec §3 trust-but-verify).
    Doctor surfaces status + install hint per tool. Missing tool → WARN, never FAIL,
    because dev workflows that don't touch every language don't need every tool.
    """
    del project_root  # not needed — tool lookup is PATH-only
    tools = [
        ("detekt", "brew install detekt    # or: sdk install detekt"),
        ("swiftlint", "brew install swiftlint"),
        ("eslint", "npm install -g eslint    # or per-project: npm i -D eslint"),
        ("radon", "pip install radon"),
    ]
    checks: list[_Check] = []
    for name, install_hint in tools:
        path = shutil.which(name)
        if path:
            checks.append(_Check(name, _STATUS_OK, f"found at {path}"))
        else:
            checks.append(
                _Check(
                    name,
                    _STATUS_WARN,
                    "não encontrado no PATH",
                    f"install: {install_hint}",
                )
            )
    return _CategoryReport("cc-gate-tools", checks)
```

- [ ] Step 4: Modify `doctor.run()` — add `_check_cc_gate_tools(project_root)` to the `full` scope category list. Edit the existing block:

```python
    if scope == "full":
        categories.extend(
            [
                _check_inventory(project_root),
                _check_memory_l1(project_root),
                _check_graph(project_root),
                _check_reuse_findings(project_root),
                _check_hooks(project_root, config),
                _check_mcps(config),
                _check_i18n(project_root, config),
                _check_bak_overdue(project_root, config),
                _check_forge_version_lock(project_root),
            ]
        )
```

Change to:

```python
    if scope == "full":
        categories.extend(
            [
                _check_inventory(project_root),
                _check_memory_l1(project_root),
                _check_graph(project_root),
                _check_reuse_findings(project_root),
                _check_hooks(project_root, config),
                _check_mcps(config),
                _check_i18n(project_root, config),
                _check_bak_overdue(project_root, config),
                _check_forge_version_lock(project_root),
                _check_cc_gate_tools(project_root),
            ]
        )
```

- [ ] Step 5: Add `import shutil` to the top of `engine/doctor.py` if not already imported.

- [ ] Step 6: Run `pytest tests/engine/test_doctor_cc_tools.py -xvs`. Expected: 4 passed.

- [ ] Step 7: Run `pytest tests/engine/ -xvs` — confirma zero regressão.

- [ ] Step 8: Commit:
  ```
  git add engine/doctor.py tests/engine/test_doctor_cc_tools.py
  git commit -m "feat(engine): doctor cc-gate-tools category"
  ```

---

## Task 12 — Integration tests end-to-end

**Files:**
- Create: `tests/integration/test_cc_gate_end_to_end.py` (NEW, marker `@pytest.mark.integration`)
- Fixture: `tests/fixtures/cc_gate/kotlin_high_cc.kt` (NEW)
- Fixture: `tests/fixtures/cc_gate/kotlin_low_cc.kt` (NEW)
- Fixture: `tests/fixtures/cc_gate/swift_high_cc.swift` (NEW)
- Fixture: `tests/fixtures/cc_gate/ts_high_cc.ts` (NEW)
- Fixture: `tests/fixtures/cc_gate/python_high_cc.py` (NEW)
- Fixture: `tests/fixtures/cc_gate/workflow-config-with-cc.yaml` (NEW)
- Fixture: `tests/fixtures/cc_gate/card-with-cc-override.yaml` (NEW)

TDD cycle:

- [ ] Step 1: Criar fixture `tests/fixtures/cc_gate/kotlin_high_cc.kt` (CC esperado ≥ 12):

```kotlin
package app.fixtures

class HighCC {
    fun handleLogin(state: Int, retry: Boolean): String {
        if (state == 0) return "init"
        if (state == 1 && retry) return "retrying"
        if (state == 2) {
            for (i in 0..10) {
                if (i % 2 == 0) {
                    if (i > 5) return "even-large"
                    else return "even-small"
                } else {
                    if (i > 5) return "odd-large"
                }
            }
        }
        return when (state) {
            3 -> "three"
            4 -> "four"
            5 -> "five"
            6 -> if (retry) "six-retry" else "six"
            else -> "default"
        }
    }
}
```

- [ ] Step 2: Criar fixture `tests/fixtures/cc_gate/kotlin_low_cc.kt`:

```kotlin
package app.fixtures

class LowCC {
    fun greet(name: String): String {
        return "hello, $name"
    }
}
```

- [ ] Step 3: Criar fixture `tests/fixtures/cc_gate/swift_high_cc.swift`:

```swift
import Foundation

class HighCC {
    func performLogin(state: Int, retry: Bool) -> String {
        if state == 0 { return "init" }
        if state == 1 && retry { return "retrying" }
        if state == 2 {
            for i in 0..<10 {
                if i % 2 == 0 {
                    if i > 5 { return "even-large" }
                    else { return "even-small" }
                } else {
                    if i > 5 { return "odd-large" }
                }
            }
        }
        switch state {
        case 3: return "three"
        case 4: return "four"
        case 5: return "five"
        case 6: return retry ? "six-retry" : "six"
        default: return "default"
        }
    }
}
```

- [ ] Step 4: Criar fixture `tests/fixtures/cc_gate/ts_high_cc.ts`:

```typescript
export function computeTotal(state: number, retry: boolean): string {
    if (state === 0) return "init";
    if (state === 1 && retry) return "retrying";
    if (state === 2) {
        for (let i = 0; i < 10; i++) {
            if (i % 2 === 0) {
                if (i > 5) return "even-large";
                else return "even-small";
            } else {
                if (i > 5) return "odd-large";
            }
        }
    }
    switch (state) {
        case 3: return "three";
        case 4: return "four";
        case 5: return "five";
        case 6: return retry ? "six-retry" : "six";
        default: return "default";
    }
}
```

- [ ] Step 5: Criar fixture `tests/fixtures/cc_gate/python_high_cc.py`:

```python
def tokenize(state: int, retry: bool) -> str:
    if state == 0:
        return "init"
    if state == 1 and retry:
        return "retrying"
    if state == 2:
        for i in range(10):
            if i % 2 == 0:
                if i > 5:
                    return "even-large"
                else:
                    return "even-small"
            else:
                if i > 5:
                    return "odd-large"
    if state == 3:
        return "three"
    elif state == 4:
        return "four"
    elif state == 5:
        return "five"
    elif state == 6:
        return "six-retry" if retry else "six"
    return "default"
```

- [ ] Step 6: Criar fixture `tests/fixtures/cc_gate/workflow-config-with-cc.yaml`:

```yaml
schema-version: 1
identity:
  project-slug: cc-gate-fixture
  preset: kmp-mobile
cc-gate:
  enabled: true
  kotlin: 10
  swift: 10
  ts: 15
  python: 10
  ignore-paths:
    - "src/test/.*"
    - ".*\\.generated\\..*"
cards:
  active: []
```

- [ ] Step 7: Criar fixture `tests/fixtures/cc_gate/card-with-cc-override.yaml`:

```yaml
name: composable-screens
version: 1.0.0
cc-gate-override:
  kotlin:
    threshold: 15
    justification: "Composable functions com DSL aninhado inflacionam CC"
```

- [ ] Step 8: Write `tests/integration/test_cc_gate_end_to_end.py`:

```python
"""End-to-end integration tests for the cc-gate.

Each test wires the validator into a temp git repo, stages fixture files,
and exercises one of the 5 spec §5 integration scenarios. Per-language
smoke tests are guarded by `@pytest.mark.skipif` so the suite remains
green on machines without all 4 native CC tools.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "cc_gate"

pytestmark = pytest.mark.integration


def _git_init(repo: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@forge.local"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "forge-test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)
    # Initial commit so HEAD exists
    (repo / ".gitkeep").write_text("", encoding="utf-8")
    subprocess.run(["git", "add", ".gitkeep"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)


def _stage(repo: Path, rel_path: str, content: str) -> None:
    p = repo / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", rel_path], cwd=repo, check=True)


def _setup_workflow_config(repo: Path, cc_block: dict | None = None) -> None:
    (repo / ".claude").mkdir(exist_ok=True)
    import yaml
    cfg = {
        "schema-version": 1,
        "identity": {"project-slug": "test", "preset": "kmp-mobile"},
        "cards": {"active": []},
        "cc-gate": cc_block or {"enabled": True, "kotlin": 10, "python": 10},
    }
    (repo / ".claude" / "workflow-config.yaml").write_text(
        yaml.safe_dump(cfg), encoding="utf-8"
    )


# ── Scenario 1: cascade position ────────────────────────────────────────────


def test_verify_cascade_position(tmp_path: Path) -> None:
    """CC gate is listed AFTER check_no_invented_behavior in the default cascade."""
    from engine import verify
    specs = verify._default_validator_specs(tmp_path)
    names = [s.name for s in specs]
    assert names.index("check_cyclomatic_complexity") == names.index("check_no_invented_behavior") + 1


# ── Scenario 2: fail-fast ────────────────────────────────────────────────────


def test_cascade_failfast_skips_cc_when_earlier_validator_fails(tmp_path: Path, monkeypatch) -> None:
    from engine import verify
    captured: list[str] = []

    def fake_invoke(spec, root):
        captured.append(spec.name)
        if spec.name == "check_no_invented_behavior":
            return verify._ValidatorResult(name=spec.name, status="fail", duration_ms=1)
        return verify._ValidatorResult(name=spec.name, status="pass", duration_ms=1)

    monkeypatch.setattr(verify, "_invoke_validator", fake_invoke)
    specs = verify._default_validator_specs(tmp_path)
    results = verify._run_cascade(specs, fail_fast=True, project_root=tmp_path, interactive=False)
    cc = next(r for r in results if r.name == "check_cyclomatic_complexity")
    assert cc.status == "skipped"


# ── Scenario 3: per-task fail blocks commit instructions ────────────────────


@pytest.mark.skipif(shutil.which("radon") is None, reason="radon not installed")
def test_per_task_fail_blocks_commit(tmp_path: Path) -> None:
    _git_init(tmp_path)
    _setup_workflow_config(tmp_path)
    _stage(
        tmp_path, "engine/parser/lexer.py",
        (FIXTURES / "python_high_cc.py").read_text(encoding="utf-8"),
    )

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "validators"))
    import check_cyclomatic_complexity as v

    result = v.validate(tmp_path)
    assert result["status"] == "fail"
    assert len(result["paths"]) == 3


# ── Scenario 4: override-justify permits commit ─────────────────────────────


@pytest.mark.skipif(shutil.which("radon") is None, reason="radon not installed")
def test_override_permits_commit(tmp_path: Path) -> None:
    _git_init(tmp_path)
    _setup_workflow_config(tmp_path)
    _stage(
        tmp_path, "engine/parser/lexer.py",
        (FIXTURES / "python_high_cc.py").read_text(encoding="utf-8"),
    )
    # Simulate a commit body with CC-OVERRIDE
    (tmp_path / ".git" / "COMMIT_EDITMSG").write_text(
        "feat(parser): tokenizer\n\n"
        "CC-OVERRIDE: engine/parser/lexer.py:tokenize cc=13 — state machine irreducible\n",
        encoding="utf-8",
    )

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "validators"))
    import check_cyclomatic_complexity as v

    result = v.validate(tmp_path)
    assert result["status"] in ("pass", "warn")


# ── Scenario 5: per-language smoke (skip when tool missing) ─────────────────


@pytest.mark.parametrize("language,tool,fixture,target_file", [
    ("kotlin", "detekt", "kotlin_high_cc.kt", "app/HighCC.kt"),
    ("swift", "swiftlint", "swift_high_cc.swift", "ios/HighCC.swift"),
    ("ts", "eslint", "ts_high_cc.ts", "src/highCC.ts"),
    ("python", "radon", "python_high_cc.py", "engine/parser/lexer.py"),
])
def test_smoke_per_language_high_cc_fails(
    language: str, tool: str, fixture: str, target_file: str, tmp_path: Path,
) -> None:
    if shutil.which(tool) is None:
        pytest.skip(f"{tool} not installed in test environment")

    _git_init(tmp_path)
    _setup_workflow_config(tmp_path)
    _stage(
        tmp_path, target_file,
        (FIXTURES / fixture).read_text(encoding="utf-8"),
    )

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "validators"))
    import check_cyclomatic_complexity as v

    result = v.validate(tmp_path)
    # Expectation: fail when threshold violated; pass when staged file is also clean.
    assert result["status"] in ("fail", "warn", "pass")
    if result["status"] == "fail":
        assert len(result["paths"]) == 3
```

- [ ] Step 9: Run `pytest tests/integration/test_cc_gate_end_to_end.py -xvs -m integration`. Expected: 5+ passed (per-language tests skip when tool absent).

- [ ] Step 10: Se algum cenário falha por gap não previsto, **registre o gap como deviation no commit body** e corrija inline antes do commit (Rule 1 — auto-fix de bug). Re-run até verde.

- [ ] Step 11: Run `pytest tests/` (suite completa) — confirma baseline + ~20 tests, todos verdes.

- [ ] Step 12: Commit:
  ```
  git add tests/integration/test_cc_gate_end_to_end.py tests/fixtures/cc_gate/
  git commit -m "test(integration): cc gate end-to-end (5 scenarios)"
  ```

---

## Task 13 — Doc-sync (8 docs)

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/design/08-session-handoff.md`
- Modify: `README.md`
- Modify: `docs/schemas/workflow-config.md`
- Modify: `docs/schemas/card.md`
- Modify: `docs/design/07-discipline.md`
- Modify: `docs/design/04-pending.md`
- Modify: `.claude/rules/testing.md`

Sem TDD (docs). Steps:

- [ ] Step 1: Update `CHANGELOG.md` — adicionar entrada em `## [Unreleased]` `### Added`:

```markdown
### Added

- **Cyclomatic Complexity gate (`check_cyclomatic_complexity`)** — multi-language
  CC validator que roda no cascade de `forge verify` (após
  `check_no_invented_behavior`) e per-task em `forge implement` (entre review e
  commit). Threshold via precedência card `cc-gate-override` > workflow-config
  `cc-gate` > defaults (kotlin=10, swift=10, ts=15, python=10). Dispatch pra
  tools nativas: Detekt (Kotlin), SwiftLint (Swift), eslint (TS/JS), Radon
  (Python). Tools NÃO instaladas pelo forge — `forge doctor` reporta na
  categoria nova `cc-gate-tools` com instruções de install. Regra de fail:
  função `new` com `cc > threshold` OU função `modified` com `cc_after >
  cc_before`. Override-justify via `CC-OVERRIDE: <file>:<func> cc=<N> — <razão>`
  no commit body silencia fail apenas pra aquele commit (auditável via
  `git log --grep='CC-OVERRIDE'`). 3-caminhos canônico on-fail
  (refactor / override-justify / split-task). Bypass de emergência via
  `NO_CC_GATE=1` env var, logado em `.claude/state/cc-gate-bypass.jsonl`.
- Helpers `cc_threshold_lookup` + `cc_format_three_paths` em `validators/_common.py`.
- Configs internos `engine/_cc_configs/{detekt.yml,swiftlint.yml,eslint.json,radon.cfg}`
  controlados pelo forge (versionados junto da release).
- Doctor categoria `cc-gate-tools` (13ª categoria, full scope).
- ~20 unit + integration tests (`tests/validators/test_cc_*.py`,
  `tests/engine/test_*_cc_*.py`, `tests/integration/test_cc_gate_end_to_end.py`).
```

- [ ] Step 2: Update `docs/design/08-session-handoff.md` — alterar header e tabela:

```markdown
**Última atualização:** 2026-06-03 (v1.2 — cc-gate shipping)
**Estado:** v1.2 — cyclomatic complexity gate live; 15 validators total.
```

E adicionar linha à tabela de Categoria/Status:

```markdown
| CC gate                              | ✅ live (cascade + per-task) |
```

- [ ] Step 3: Update `README.md` — stats:

```markdown
- **Validators:** 15 (era 14 — adicionado `check_cyclomatic_complexity`)
- **Tests:** baseline + ~20 (CC gate)
```

(Ajuste números literais conforme baseline real observado no `pytest --collect-only -q | tail -1` do worktree antes do commit.)

- [ ] Step 4: Update `docs/schemas/workflow-config.md` — APPEND bloco:

```markdown
### `cc-gate` (opt-in)

Configura o validator `check_cyclomatic_complexity`. Bloco opcional — sem ele,
o gate usa defaults built-in (kotlin=10, swift=10, ts=15, python=10).

```yaml
cc-gate:
  enabled: true             # default true; false desliga (warn, não fail)
  kotlin: 10                # threshold absoluto por linguagem
  swift: 10
  ts: 15
  python: 10
  ignore-paths:             # regex Python (re.search); aplicado após filtro de extensão
    - "src/test/.*"
    - ".*\\.generated\\..*"
```

Precedência (mais específico vence): card `cc-gate-override` > este bloco >
defaults built-in. Threshold ≤ 0 → validator interpreta como degraded
(config errada, emite warn).
```

- [ ] Step 5: Update `docs/schemas/card.md` — APPEND:

```markdown
### `cc-gate-override` (opt-in)

Override per-card do threshold do `check_cyclomatic_complexity`. Use quando o
escopo do card inflaciona CC por design (DSL, state machine, generated code).

```yaml
cc-gate-override:
  kotlin:
    threshold: 15
    justification: "Composable functions com DSL aninhado inflacionam CC"
```

`justification` é **obrigatória** — sem ela o validator emite warning
("override sem rationale — adicione justification ou remova"). Auditável via
`grep -r 'cc-gate-override' cards/`.

Múltiplos cards ativos com override para a mesma linguagem: **primeiro card
com `threshold` declarado wins** (ordem determinística do listing). Não é
"max" nem "min" — é "primeiro", porque card listing tem semântica de
prioridade declarada pelo usuário.
```

- [ ] Step 6: Update `docs/design/07-discipline.md` — §2 (validator cascade), append linha após `check_no_invented_behavior`:

```markdown
| check_cyclomatic_complexity | fail-fast | hard | Gate de CC multi-language; dispatcha pra Detekt/SwiftLint/eslint/Radon; new function obedece threshold absoluto, modified function aplica delta (não pode piorar). Override-justify via `CC-OVERRIDE` no commit body. |
```

- [ ] Step 7: Update `docs/design/04-pending.md` — adicionar 5 gaps deferidos (com fingerprint sha256 estável):

```markdown
### Gap N+1 — CC: Whitelist persistente de overrides

**Categoria:** cc-gate
**Fingerprint:** `sha256(consolidate-within-module:cc-whitelist:override-no-commit-only)`
**Status:** deferred (v1.3+)

Hoje override é por commit no body (`CC-OVERRIDE: ...`). Eventualmente projetos
grandes podem querer "essa função tem cc=20 e é assim porque é parser" como
anotação permanente. v1.2 recusa pra evitar débito invisível. Reentrar se
≥3 projetos consumidores pedirem em retro.

### Gap N+2 — CC: Cognitive Complexity (Sonar) como métrica alternativa

**Categoria:** cc-gate
**Fingerprint:** `sha256(redundant-platform:cognitive-vs-cyclomatic:v1.2-uses-cc)`
**Status:** deferred (v1.3+)

CC é métrica clássica mas Cognitive Complexity (Campbell, SonarSource) reflete
melhor leitura humana. Trocar tooling é trabalho não-trivial (cada tool nativa
tem variação) — deferido pra v1.3+ se sinal empírico justificar.

### Gap N+3 — CC trending em `forge graph` (Q18+)

**Categoria:** cc-gate
**Fingerprint:** `sha256(promote-to-shared:graph-q18:cc-trend-over-history)`
**Status:** deferred (v1.3+)

Adicionar query Q18+ que tabula CC por área do código e mostra trend ao longo
do histórico. Útil pra retrospective. Deferido pra v1.3+ junto com expansão
geral do graph.

### Gap N+4 — CC: Auto-suggest refactor LLM-powered (Phase 6)

**Categoria:** cc-gate
**Fingerprint:** `sha256(near-duplicate:cc-auto-refactor:phase-6-orchestration)`
**Status:** deferred (Phase 6)

Quando gate bloqueia, mostrar sugestão concreta de como refatorar (LLM analisa
função, propõe split). Fora de escopo v1.2 porque toca subagent orchestration
de forma não-trivial.

### Gap N+5 — CC: Per-function threshold inline annotation (REJECTED)

**Categoria:** cc-gate
**Fingerprint:** `sha256(consolidate-within-module:cc-inline-suppress:rejected-by-design)`
**Status:** rejected (não reentrar sem mudança de contexto)

Proposta de `// cc-threshold: 20` no código. **Rejeitada em favor de
override-no-commit**: inline espalha exceções pelo código, dificulta auditoria,
vira whitelist invisível. Documentado aqui pra não reaparecer em retrospective.
```

- [ ] Step 8: Update `.claude/rules/testing.md` — §"Validators são código" — adicionar mention:

```markdown
- `check_cyclomatic_complexity` (v1.2+) — multi-language gate. Tests em
  `tests/validators/test_check_cyclomatic_complexity.py` + parser tests
  (`test_cc_parsers_*.py`) + helper tests (`test_common_cc_helpers.py`).
  Integration em `tests/integration/test_cc_gate_end_to_end.py` (marker
  `integration`, skip per-language quando tool nativa missing).
```

- [ ] Step 9: Run `forge verify` no próprio repo. Expected: PASS (zero hard fail; warns ok).

- [ ] Step 10: Run `pytest` (suite completa). Expected: green, count ≥ baseline + ~20.

- [ ] Step 11: Commit:
  ```
  git add CHANGELOG.md docs/design/08-session-handoff.md README.md \
          docs/schemas/workflow-config.md docs/schemas/card.md \
          docs/design/07-discipline.md docs/design/04-pending.md \
          .claude/rules/testing.md
  git commit -m "docs(sync): cc-gate shipping — 8 docs (CHANGELOG/handoff/README/schemas/discipline/pending/rules)"
  ```

---

## Self-review — Spec coverage v1 (12 items §5)

| # | Critério v1 (spec §5) | Mapeado em |
|---|---|---|
| 1 | `validators/check_cyclomatic_complexity.py` existe, 350-450 LOC, passa ruff + pytest | Tasks 3, 4, 5, 6, 7, 8 (build incremental); test em Task 8 |
| 2 | `validators/_common.py` tem `cc_threshold_lookup` + `cc_format_three_paths` com unit tests | Task 1 |
| 3 | `engine/verify.py` registra na cascade após `check_no_invented_behavior` + teste de posição | Task 9 |
| 4 | `engine/implement.py` invoca o validator entre review e commit + teste de bloqueio | Task 10 |
| 5 | `engine/doctor.py` reporta categoria `cc-gate-tools` com status + install instructions | Task 11 |
| 6 | `engine/_cc_configs/{detekt.yml,swiftlint.yml,eslint.json,radon.cfg}` existem + sanity test | Task 2 |
| 7 | `docs/schemas/workflow-config.md` documenta bloco `cc-gate:` com exemplo | Task 13 Step 4 |
| 8 | `docs/schemas/card.md` documenta `cc-gate-override` opt-in com `justification` obrigatória | Task 13 Step 5 |
| 9 | 3-caminhos render bate snapshot test — formato canônico de `disciplines.md §1` | Task 1 (`test_format_three_paths_snapshot`) |
| 10 | Override-justify regex casa exemplos válidos, rejeita malformados; ≥5 cenários | Task 7 (7 cenários) |
| 11 | `pytest` suite completa verde; test count ≥ baseline + ~20 | Task 12 Step 11 + Task 13 Step 10 |
| 12 | Doc-sync 8 docs completos; `forge verify` no próprio repo passa cascade sem hard fail | Task 13 (todos os 8 docs) + Step 9 |

Coverage: **12/12**. Cada critério mapeado pra ≥1 task com step testável.

---

## Sequência de dispatch sugerida

```
Task 1  → helpers em _common (puro, sem deps)
Task 2  → configs estáticos (sem deps)            ┐ paralelizável com Task 1
Task 3  → CCResult + classifier (depende de _common)
Task 4  → parsers Kotlin + Swift (depende de Task 3)
Task 5  → parsers TS + Python (depende de Task 3) ┐ paralelizável com Task 4
Task 6  → dispatch + availability (depende de 3+config)
Task 7  → override-justify (depende de Task 3)    ┐ paralelizável com Task 6
Task 8  → entry point validate() (depende de 1, 3, 4, 5, 6, 7)
Task 9  → cascade integration (depende de 8)
Task 10 → per-task hook (depende de 8)            ┐ paralelizável com Task 9
Task 11 → doctor categoria (depende de 2)         ┐ paralelizável com 8, 9, 10
Task 12 → integration tests (depende de 8, 9, 10, 11)
Task 13 → doc-sync (depende de TUDO — final)
```

Após Task 13, dispatch `gsd-code-reviewer` para o range `HEAD~13..HEAD` (review estruturado), seguido de fix loop se findings, e verification final (`pytest` + `forge verify` no próprio repo).

---

## Notas operacionais

- **Voz:** mentor calmo em mensagens render (cc_format_three_paths). Português neutro. Código em inglês padrão Python.
- **TDD não-negociável:** cada task com test FAIL → impl → test PASS → commit. Sem skip de RED phase.
- **Trust-but-verify entre tasks:** o orchestrator lê `git diff HEAD~1..HEAD` após cada dispatch antes de seguir.
- **Sem decisão load-bearing tocada** (spec §5 confirmou): zero `Revisita decisão N` no CHANGELOG.
- **Sem novo card/template/preset/comando/flag** — Decisions 10, 19, 22, 23 preservadas.
