"""Regression test for ``_RE_RFC_ARROW`` handling nested parentheses.

The ``\\([^)]*\\)`` snippet in the arrow-RFC regex stops at the first
``)``, so destructured props with a default arrow value — for example
``({ callback = (x) => x })`` — produced no match and the component
went missing from ``components``. See R2.6.
"""

from __future__ import annotations

from pathlib import Path

from engine.graph.parser_typescript import parse_typescript_file


def _write_tsx(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "Foo.tsx"
    p.write_text(content, encoding="utf-8")
    return p


def test_rfc_with_nested_default_arrow_in_destructure(tmp_path: Path) -> None:
    """Component with a destructured prop carrying a nested ``(x) => x`` default."""
    src = (
        "import React from 'react';\n"
        "const FooBar = ({callback = (x) => x}) => <div/>;\n"
    )
    info = parse_typescript_file(_write_tsx(tmp_path, src))
    assert "FooBar" in info.components, (
        f"FooBar should be detected as RFC; got components={info.components}"
    )


def test_rfc_simple_typed_arrow(tmp_path: Path) -> None:
    """Regression guard: basic typed-arg RFC still detected."""
    src = (
        "import React from 'react';\n"
        "const Simple = (x: string) => <div/>;\n"
    )
    info = parse_typescript_file(_write_tsx(tmp_path, src))
    assert "Simple" in info.components


def test_rfc_simple_destructure(tmp_path: Path) -> None:
    """Plain destructured props with no defaults — common case."""
    src = (
        "import React from 'react';\n"
        "const Anon = ({foo, bar}) => <span/>;\n"
    )
    info = parse_typescript_file(_write_tsx(tmp_path, src))
    assert "Anon" in info.components
