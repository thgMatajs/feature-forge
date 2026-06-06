"""Unit tests for _parse_detekt and _parse_swiftlint.

Cobre Task 4 do plan cc-gate: parsers que normalizam saída JSON nativa
de Detekt (Kotlin) e SwiftLint (Swift) para `list[CCResult]` — sem
preencher status/cc_before (esses vêm depois no validate()).

Spec source: `docs/superpowers/specs/2026-06-03-cc-gate-design.md §3`
(tabela tools + CCResult shape).

Disciplina de robustez: tool crash / non-JSON → list[] vazia, nunca
raise. O orchestrator emite `result_warn` quando o parser devolver vazio
para input que era esperado conter issues — mantém a cascade viva
(trust-but-verify, spec §3).
"""

from __future__ import annotations

from pathlib import Path

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
    # status + cc_before são preenchidos depois pelo orchestrator;
    # parsers deixam defaults.
    assert r0.status == "unchanged"
    assert r0.cc_before is None

    r1 = results[1]
    assert r1.function == "validateForm"
    assert r1.cc == 11
    assert r1.line_end == 120


def test_parse_detekt_handles_empty_issues() -> None:
    assert v._parse_detekt('{"issues": []}') == []


def test_parse_detekt_handles_malformed_json_returns_empty() -> None:
    # Tool crash / non-JSON → return [] so caller can emit result_warn
    assert v._parse_detekt("not json {{") == []


def test_parse_detekt_skips_non_cc_rules() -> None:
    raw = (
        '{"issues": [{"ruleName": "MagicNumber", "message": "irrelevant", '
        '"location": {"filePath": "x.kt", "position": {"line": 1}, '
        '"endPosition": {"line": 2}}, "metric": {"value": 1}}]}'
    )
    assert v._parse_detekt(raw) == []


def test_parse_swiftlint_basic() -> None:
    raw = (FIXTURES / "swiftlint_output_sample.json").read_text(encoding="utf-8")
    results = v._parse_swiftlint(raw)
    assert len(results) == 1
    r = results[0]
    assert r.file == "ios/Auth/LoginCoordinator.swift"
    assert r.function == "performLogin"  # extracted from `reason` via regex
    assert r.line_start == 67
    assert r.cc == 12
    assert r.language == "swift"
    assert r.status == "unchanged"
    assert r.cc_before is None


def test_parse_swiftlint_empty_array() -> None:
    assert v._parse_swiftlint("[]") == []


def test_parse_swiftlint_malformed() -> None:
    assert v._parse_swiftlint("oops") == []


def test_parse_swiftlint_skips_non_cc_rules() -> None:
    raw = (
        '[{"rule_id": "force_unwrapping", "reason": "Function bad() unwraps", '
        '"file": "x.swift", "line": 5, "complexity": 0}]'
    )
    assert v._parse_swiftlint(raw) == []
