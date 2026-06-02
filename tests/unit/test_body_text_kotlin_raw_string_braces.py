"""Regression — Kotlin raw strings (``\"\"\"...\"\"\"``) containing ``{`` and ``}``.

The brace counter inside ``extract_function_body`` must skip the entire
raw-string literal — any ``{`` or ``}`` inside ``\"\"\"...\"\"\"`` is text,
not code. If triple-quote mode is not entered or is exited prematurely,
a ``}`` inside the raw string is mis-counted and the function body
closes early (or fails to close at all).

This guard supplements ``test_body_text_swift_triple_quote.py`` —
specifically the ``test_kotlin_triple_quote_still_works`` case — by
pinning the exact pattern called out in the master review (R2.21).
"""

from __future__ import annotations

from engine.graph._body_text import extract_function_body, find_opening_brace


def test_kotlin_raw_string_with_nested_braces_keeps_counter_in_sync() -> None:
    """A Kotlin function whose body holds a ``\"\"\"...\"\"\"`` containing ``{}``.

    Layout of the source:

        fun foo() {
            val raw = \"\"\"
            object FakeClass {
                val x = 1
            }
            \"\"\"
            println(raw)
        }

    Without raw-string handling, the ``{`` after ``FakeClass`` would
    bump ``depth`` to 2 and the matching ``}`` would NOT bring it back
    to 1 properly — actually, the deeper risk is the OUTER ``}`` of
    ``foo`` getting consumed by an unbalanced inner pair. Either way
    the extracted body would miss ``println(raw)`` or be ``None``.

    With the fix in ``_body_text.py`` (Kotlin + Swift triple-quote
    handling), the brace counter skips the entire raw literal and the
    outer ``}`` correctly closes ``fun foo``.
    """
    source = (
        "fun foo() {\n"
        "    val raw = \"\"\"\n"
        "    object FakeClass {\n"
        "        val x = 1\n"
        "    }\n"
        "    \"\"\"\n"
        "    println(raw)\n"
        "}\n"
    )
    idx = source.index("fun foo()") + len("fun foo()")
    brace = find_opening_brace(source, idx)
    assert brace is not None, "test fixture must include opening `{` of fun foo"

    body = extract_function_body(source, brace, language="kotlin")

    assert body is not None, "Kotlin raw-string ``{}`` desynced the brace counter"
    # The entire function body must be captured — the println line lives
    # AFTER the raw literal, so it can only be present when the counter
    # stayed in sync through the literal.
    assert "println(raw)" in body
    # And of course the inner literal's text rides along verbatim.
    assert "object FakeClass" in body
