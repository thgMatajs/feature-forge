"""Unit tests for CC-OVERRIDE parsing + application.

Cobre Task 7 do plan cc-gate: detecção e aplicação do override-justify
declarado no commit body (`CC-OVERRIDE: <file>:<func> cc=<N> — <razão>`).

Spec source: `docs/superpowers/specs/2026-06-03-cc-gate-design.md §4`
(formato literal + regex anchored a start-of-line via re.MULTILINE).

Contrato:
- Override válido (regex strict) → vira dict com {file, func, cc, reason}.
- Override LOOSE (sem `— razão`) → não conta + warning emitido.
- apply_overrides retorna tupla (silenced, surviving) sobre CCResult list.
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
    overrides = v.parse_overrides(body)
    assert len(overrides) == 1
    o = overrides[0]
    assert o["file"] == "app/foo.kt"
    assert o["func"] == "bar"
    assert o["cc"] == 14
    assert o["reason"] == "DSL aninhado"


def test_override_malformed_missing_dash_does_not_count() -> None:
    body = "CC-OVERRIDE: app/foo.kt:bar cc=14 no reason"
    overrides, warnings = v.parse_overrides(body, return_warnings=True)
    assert overrides == []
    assert len(warnings) == 1
    assert "CC-OVERRIDE sem razão" in warnings[0]


def test_override_covers_only_declared_function() -> None:
    body = "CC-OVERRIDE: app/foo.kt:bar cc=14 — DSL"
    fails = [
        _make("app/foo.kt", "bar", 14),
        _make("app/foo.kt", "baz", 12),  # NOT covered — função diferente
    ]
    silenced, surviving, _warnings = v.apply_overrides(fails, body)
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
    silenced, surviving, _warnings = v.apply_overrides(fails, body)
    assert len(silenced) == 2
    assert surviving == []


def test_override_file_mismatch_does_not_silence() -> None:
    body = "CC-OVERRIDE: a.kt:foo cc=14 — reason"
    fails = [_make("b.kt", "foo", 14)]  # arquivo diferente — não silencia
    silenced, surviving, _warnings = v.apply_overrides(fails, body)
    assert silenced == []
    assert len(surviving) == 1


def test_override_empty_body_returns_all_as_surviving() -> None:
    fails = [_make("a.kt", "foo", 14)]
    silenced, surviving, _warnings = v.apply_overrides(fails, "")
    assert silenced == []
    assert surviving == fails


def test_override_regex_anchors_at_line_start() -> None:
    # Não deve casar quando CC-OVERRIDE aparece mid-sentence (defensivo).
    body = "see also CC-OVERRIDE: a.kt:foo cc=14 — reason"
    assert v.parse_overrides(body) == []


def test_apply_overrides_surfaces_malformed_warnings() -> None:
    """H4 — `apply_overrides` must propagate malformed-override warnings.

    Spec §4 step 5: malformed CC-OVERRIDE lines do NOT silence the fail,
    AND the validator must emit a warning so the user sees why their
    override attempt didn't count.
    """
    body = "\n".join(
        [
            "feat: refactor login",
            "",
            "CC-OVERRIDE: a.kt:foo cc=14 missing-dash",
            "CC-OVERRIDE: b.kt:bar cc=11 — DSL legítimo",
        ]
    )
    fails = [_make("a.kt", "foo", 14), _make("b.kt", "bar", 11)]
    silenced, surviving, warnings = v.apply_overrides(fails, body)
    # b.kt:bar silenced by valid override; a.kt:foo survives the malformed.
    assert [s.function for s in silenced] == ["bar"]
    assert [s.function for s in surviving] == ["foo"]
    assert any("CC-OVERRIDE sem razão" in w for w in warnings), (
        f"expected malformed warning; got {warnings!r}"
    )


def test_apply_overrides_no_warnings_when_all_valid() -> None:
    """When every override is well-formed, warnings list is empty."""
    body = "CC-OVERRIDE: a.kt:foo cc=14 — irreducible DSL"
    silenced, surviving, warnings = v.apply_overrides(
        [_make("a.kt", "foo", 14)], body
    )
    assert len(silenced) == 1
    assert surviving == []
    assert warnings == []


def test_override_trailing_dash_empty_reason_warns() -> None:
    """D-008 — `CC-OVERRIDE: ... cc=N — ` (em-dash com tail vazio) é malformado.

    Antes do fix, o loose-pass fazia `if " — " in line: continue` e engolia
    o warning. Agora a parte após o `—` é inspecionada; tail vazio cai no
    `warnings.append`.
    """
    body = "feat: x\n\nCC-OVERRIDE: app/foo.kt:bar cc=12 — \n"
    overrides, warnings = v.parse_overrides(body, return_warnings=True)
    # Strict regex exige reason concreta — não conta como override válido.
    assert overrides == []
    # Loose-pass agora detecta o tail vazio e emite warning (D-008).
    assert len(warnings) == 1
    assert "CC-OVERRIDE sem razão" in warnings[0]
    assert "app/foo.kt:bar" in warnings[0]


def test_override_trailing_dash_whitespace_only_reason_warns() -> None:
    """Variação D-008: vários espaços após `—` continuam sendo razão vazia."""
    body = "CC-OVERRIDE: x.py:y cc=11 —    \n"
    overrides, warnings = v.parse_overrides(body, return_warnings=True)
    assert overrides == []
    assert len(warnings) == 1
    assert "CC-OVERRIDE sem razão" in warnings[0]
