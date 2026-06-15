"""Tests for engine.graph.parser_java."""

from pathlib import Path

import pytest

from engine.graph.parser_java import _parse_java, parse_java_file

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_java_basic_parses_package() -> None:
    info = parse_java_file(FIXTURES / "java-basic" / "com" / "example" / "LoginUseCase.java")
    assert info.package == "com.example"


def test_java_basic_parses_imports() -> None:
    info = parse_java_file(FIXTURES / "java-basic" / "com" / "example" / "LoginUseCase.java")
    assert "com.example.domain.User" in info.imports
    assert "com.example.repository.AuthRepository" in info.imports
    assert "java.util.List" in info.imports


def test_java_basic_parses_class() -> None:
    info = parse_java_file(FIXTURES / "java-basic" / "com" / "example" / "LoginUseCase.java")
    classes = [s for s in info.symbols if s.kind == "class"]
    assert len(classes) == 1
    assert classes[0].name == "LoginUseCase"


def test_java_basic_parses_methods() -> None:
    info = parse_java_file(FIXTURES / "java-basic" / "com" / "example" / "LoginUseCase.java")
    methods = [s for s in info.symbols if s.kind == "method"]
    method_names = {s.name for s in methods}
    assert "execute" in method_names


def test_java_annotations_parses_annotation() -> None:
    # L-004 (REVIEW v1.3.0): fixture renomeada java-annotations → java-annotated-class.
    info = parse_java_file(FIXTURES / "java-annotated-class" / "com" / "example" / "InjectService.java")
    classes = [s for s in info.symbols if s.kind == "class"]
    assert len(classes) >= 1
    assert classes[0].name == "InjectService"


def test_java_methods_have_body() -> None:
    info = parse_java_file(FIXTURES / "java-basic" / "com" / "example" / "LoginUseCase.java")
    methods = [s for s in info.symbols if s.kind == "method"]
    for m in methods:
        if m.name == "execute":
            assert m.body is not None
            assert "authRepo.login" in m.body
            assert m.body_hash is not None


def test_java_constructor_body() -> None:
    info = parse_java_file(FIXTURES / "java-basic" / "com" / "example" / "LoginUseCase.java")
    ctors = [s for s in info.symbols if s.kind == "constructor"]
    assert len(ctors) >= 1
    assert ctors[0].body is not None


# ---------------------------------------------------------------------------
# C-001 (REVIEW v1.3.0) — regressão: o regex _RE_METHOD não pode mais
# capturar símbolos fantasma a partir de call expressions (``return foo(x);``,
# ``new Foo(z);``, ``super(args);``) nem operadores ``new``/``this``/``super``.
# ---------------------------------------------------------------------------

def test_java_no_phantom_symbols_from_call_expressions() -> None:
    src = "class Foo { void m() { return foo(x); new Foo(z); } }"
    info = _parse_java(src)
    kinds_names = [(s.kind, s.name) for s in info.symbols]
    # Esperado: apenas ``class Foo`` e ``method m``.
    assert ("class", "Foo") in kinds_names
    assert ("method", "m") in kinds_names
    # Fantasmas que o regex casava antes do fix:
    assert ("constructor", "Foo") not in kinds_names, (
        "``new Foo(z);`` virou constructor fantasma — C-001 regression"
    )
    assert ("method", "foo") not in kinds_names, (
        "``return foo(x);`` virou method fantasma — C-001 regression"
    )


def test_java_no_phantom_from_throw_and_super() -> None:
    src = """
    class Bar {
        void m() {
            throw err(x);
            super(args);
            this(y);
        }
    }
    """
    info = _parse_java(src)
    kinds_names = {(s.kind, s.name) for s in info.symbols}
    # ``throw err(x);``, ``super(args);``, ``this(y);`` não podem virar method/ctor.
    assert ("method", "err") not in kinds_names
    assert ("method", "args") not in kinds_names
    assert ("method", "y") not in kinds_names
    # ``class Bar`` + ``method m`` é o esperado.
    assert ("class", "Bar") in kinds_names
    assert ("method", "m") in kinds_names
