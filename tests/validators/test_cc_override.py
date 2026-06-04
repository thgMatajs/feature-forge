"""Unit tests for CC-OVERRIDE parsing + application.

Cobre Task 7 do plan cc-gate: detecção e aplicação do override-justify
declarado no commit body (`CC-OVERRIDE: <file>:<func> cc=<N> — <razão>`).

Spec source: `docs/superpowers/specs/2026-06-03-cc-gate-design.md §4`
(formato literal + regex anchored a start-of-line via re.MULTILINE).

Contrato:
- Override válido (regex strict) → vira dict com {file, func, cc, reason}.
- Override LOOSE (sem `— razão`) → não conta + warning emitido.
- _apply_overrides retorna tupla (silenced, surviving) sobre CCResult list.
- Match key: (file, function). Sem wildcards.
"""

from __future__ import annotations

import check_cyclomatic_complexity as v


def _make(file: str, func: str, cc: int) -> v.CCResult:
    return v.CCResult(
        file=file,
        function=func,
        line_start=1,
        line_end=10,
        cc=cc,
        language="kotlin",
        status="new",
        cc_before=None,
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
        _make("app/foo.kt", "baz", 12),  # NOT covered — função diferente
    ]
    silenced, surviving = v._apply_overrides(fails, body)
    assert len(silenced) == 1 and silenced[0].function == "bar"
    assert len(surviving) == 1 and surviving[0].function == "baz"


def test_override_multiple_lines_cover_independently() -> None:
    body = "\n".join(
        [
            "CC-OVERRIDE: a.kt:foo cc=14 — reason A",
            "CC-OVERRIDE: b.kt:bar cc=11 — reason B",
        ]
    )
    fails = [_make("a.kt", "foo", 14), _make("b.kt", "bar", 11)]
    silenced, surviving = v._apply_overrides(fails, body)
    assert len(silenced) == 2
    assert surviving == []


def test_override_file_mismatch_does_not_silence() -> None:
    body = "CC-OVERRIDE: a.kt:foo cc=14 — reason"
    fails = [_make("b.kt", "foo", 14)]  # arquivo diferente — não silencia
    silenced, surviving = v._apply_overrides(fails, body)
    assert silenced == []
    assert len(surviving) == 1


def test_override_empty_body_returns_all_as_surviving() -> None:
    fails = [_make("a.kt", "foo", 14)]
    silenced, surviving = v._apply_overrides(fails, "")
    assert silenced == []
    assert surviving == fails


def test_override_regex_anchors_at_line_start() -> None:
    # Não deve casar quando CC-OVERRIDE aparece mid-sentence (defensivo).
    body = "see also CC-OVERRIDE: a.kt:foo cc=14 — reason"
    assert v._parse_overrides(body) == []
