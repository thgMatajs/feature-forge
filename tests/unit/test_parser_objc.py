"""Tests for engine.graph.parser_objc."""

from pathlib import Path

import pytest

from engine.graph.parser_objc import parse_objc_file

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_objc_header_parses_imports() -> None:
    info = parse_objc_file(FIXTURES / "objc-basic" / "Models" / "UserModel.h")
    assert any("Foundation.h" in imp for imp in info.imports)


def test_objc_header_parses_interface() -> None:
    info = parse_objc_file(FIXTURES / "objc-basic" / "Models" / "UserModel.h")
    classes = [s for s in info.symbols if s.kind == "class"]
    assert len(classes) >= 1
    assert classes[0].name == "UserModel"


def test_objc_implementation_parses_methods() -> None:
    info = parse_objc_file(FIXTURES / "objc-basic" / "Models" / "UserModel.m")
    methods = [s for s in info.symbols if s.kind == "method"]
    assert len(methods) >= 1


def test_objc_implementation_parses_imports() -> None:
    info = parse_objc_file(FIXTURES / "objc-basic" / "Models" / "UserModel.m")
    assert any("UserModel.h" in imp for imp in info.imports)


def test_objc_implementation_symbol() -> None:
    info = parse_objc_file(FIXTURES / "objc-basic" / "Models" / "UserModel.m")
    impls = [s for s in info.symbols if s.kind == "implementation"]
    assert len(impls) >= 1
    assert impls[0].name == "UserModel"


def test_objc_class_method_detection() -> None:
    info = parse_objc_file(FIXTURES / "objc-basic" / "Models" / "UserModel.m")
    methods = [s for s in info.symbols if s.kind == "method" and s.is_class_method]
    assert len(methods) >= 1  # +anonymousUser
