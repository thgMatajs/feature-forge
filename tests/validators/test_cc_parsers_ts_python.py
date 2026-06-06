"""Unit tests for _parse_eslint and _parse_radon.

Cobre Task 5 do plan cc-gate: parsers que normalizam saída JSON nativa
de eslint (TS/TSX, regra `complexity`) e Radon (Python, `radon cc -j`)
para `list[CCResult]`.

Spec source: `docs/superpowers/specs/2026-06-03-cc-gate-design.md §3`
(tabela tools + CCResult shape).

Disciplina de robustez (mesma do T4): tool crash / non-JSON → list[]
vazia, nunca raise. Orchestrator emite `result_warn` quando o parser
devolver vazio para input esperado conter issues — cascade fica viva
(trust-but-verify, spec §3).

Parsers deixam `status="unchanged"` + `cc_before=None`; o classifier
(T8) sobrescreve depois usando diff hunks.
"""

from __future__ import annotations

from pathlib import Path

import check_cyclomatic_complexity as v

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "cc_gate"


# ── eslint ───────────────────────────────────────────────────────────────────

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
    assert r.status == "unchanged"
    assert r.cc_before is None


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


# ── Radon ────────────────────────────────────────────────────────────────────

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
    assert r.status == "unchanged"
    assert r.cc_before is None


def test_parse_radon_ignores_classes() -> None:
    # Radon emits class-level aggregates with type="class"; gate só conta
    # functions/methods individuais (spec §3).
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
