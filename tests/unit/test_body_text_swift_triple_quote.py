"""Regression: Swift multiline `\"\"\"` strings must be honored by the brace counter.

Bug A5 (PR #1): `extract_function_body` only enters triple-quote mode when
``language == "kotlin"``. Swift also supports `\"\"\"` multiline strings, so a
Swift body containing `{` or `}` inside a triple-quoted literal made the brace
counter desync and either truncated the body early or failed to close it.
"""

from __future__ import annotations

from engine.graph._body_text import extract_function_body, find_opening_brace


def _body_for(source: str, after_marker: str) -> str:
    """Locate `{` after the given marker and return the extracted body."""
    idx = source.index(after_marker) + len(after_marker)
    brace = find_opening_brace(source, idx)
    assert brace is not None, "test source must include a `{` after the marker"
    return extract_function_body(source, brace, language="swift")


def test_swift_triple_quoted_string_with_odd_quotes_and_close_brace():
    """A single unbalanced `"` inside `\"\"\"...\"\"\"` desyncs the parser.

    Without the fix, Swift `\"\"\"` is treated as three independent `"` tokens
    which happen to leave in_string_double=True when followed by an odd
    number of single `"` inside the literal. The next `}` is then parsed as
    code and pops the outer function scope prematurely.

    Layout: triple-open `\"\"\"`, then ``alone"`` (one bare quote), then
    triple-close `\"\"\"`. Total `"` characters inside the literal scope: 7
    (odd). After processing the open triple, in_string_double cycles end at
    odd parity, so the closing triple's three `"` end with in_string_double
    flipped from default — leaving the closing `}` of the function
    misread.

    With the fix (`\"\"\"` triple recognized for Swift), the entire literal
    body is skipped wholesale.
    """
    source = (
        'func render() {\n'
        '    let json = """\n'
        '    a"b\n'
        '    """\n'
        '    return json\n'
        '}\n'
    )
    body = _body_for(source, "func render()")
    assert body is not None, (
        "Swift parser must enter triple-quote mode and skip the whole literal."
    )
    assert "return json" in body


def test_kotlin_triple_quote_still_works():
    """Regression guard: don't break Kotlin while fixing Swift."""
    source = '''
    fun render() {
        val payload = """
        {
            key = value
        }
        """.trimIndent()
        println(payload)
    }
    '''
    idx = source.index("fun render()") + len("fun render()")
    brace = find_opening_brace(source, idx)
    assert brace is not None
    body = extract_function_body(source, brace, language="kotlin")
    assert body is not None
    assert "println(payload)" in body
