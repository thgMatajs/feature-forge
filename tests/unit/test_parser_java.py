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


# ---------------------------------------------------------------------------
# P-N-010 / gemini parser_java:65 (REVIEW PR #16) — generics com bounds e
# nested generics em class declarations precisam casar.
# ---------------------------------------------------------------------------

def test_java_class_with_generic_bound() -> None:
    """``class Box<T extends Serializable>`` precisa casar."""
    src = "class Box<T extends Serializable> { void m() { } }"
    info = _parse_java(src)
    classes = [s for s in info.symbols if s.kind == "class"]
    assert any(c.name == "Box" for c in classes), (
        f"class com bound não casou — P-N-010 regression. Symbols: "
        f"{[(s.kind, s.name) for s in info.symbols]}"
    )


def test_java_class_with_nested_generic_bound() -> None:
    """``class Box<T extends Comparable<T>>`` precisa casar (1 nível de aninhamento)."""
    src = "class Box<T extends Comparable<T>> { void m() { } }"
    info = _parse_java(src)
    classes = [s for s in info.symbols if s.kind == "class"]
    assert any(c.name == "Box" for c in classes), (
        f"class com nested generic bound não casou — P-N-010 regression."
    )


# ---------------------------------------------------------------------------
# P-N-010 / gemini parser_java:89 — nested generics em return types.
# ---------------------------------------------------------------------------

def test_java_method_nested_generic_return_type() -> None:
    """``List<Map<String, Object>> values()`` precisa casar."""
    src = (
        "class Repo {\n"
        "    public List<Map<String, Object>> values() {\n"
        "        return null;\n"
        "    }\n"
        "}\n"
    )
    info = _parse_java(src)
    methods = [(s.kind, s.name) for s in info.symbols]
    assert ("method", "values") in methods, (
        f"Method com nested generic return type quebrou — "
        f"P-N-010 regression. Symbols: {methods}"
    )


def test_java_method_array_return_type() -> None:
    """``String[] toArray()`` precisa casar (array return type)."""
    src = (
        "class Foo {\n"
        "    public String[] toArray() {\n"
        "        return new String[0];\n"
        "    }\n"
        "}\n"
    )
    info = _parse_java(src)
    methods = [(s.kind, s.name) for s in info.symbols]
    assert ("method", "toArray") in methods, (
        f"Method com array return type não casou. Symbols: {methods}"
    )


# ---------------------------------------------------------------------------
# P-N-008 / gemini parser_java:273 (REVIEW PR #16) — ``final`` em params
# não pode virar modifier do método.
# ---------------------------------------------------------------------------

def test_java_method_modifier_does_not_leak_from_params() -> None:
    """``void m(final int x)`` — final pertence ao param, não ao método."""
    src = (
        "class Foo {\n"
        "    public void m(final int x) { }\n"
        "}\n"
    )
    info = _parse_java(src)
    method = next(
        (s for s in info.symbols if s.kind == "method" and s.name == "m"),
        None,
    )
    assert method is not None
    assert "final" not in method.modifiers, (
        f"``final`` param vazou pros modifiers do método — P-N-008 "
        f"regression. Modifiers: {method.modifiers}"
    )


def test_java_method_static_modifier_still_detected() -> None:
    """``public static void m()`` ainda precisa detectar ``static``."""
    src = (
        "class Foo {\n"
        "    public static void m() { }\n"
        "}\n"
    )
    info = _parse_java(src)
    method = next(
        (s for s in info.symbols if s.kind == "method" and s.name == "m"),
        None,
    )
    assert method is not None
    assert "static" in method.modifiers, (
        f"``static`` modifier sumiu do método — P-N-008 over-fix. "
        f"Modifiers: {method.modifiers}"
    )


# ---------------------------------------------------------------------------
# T-N-008 (REVIEW PR #16) — cobertura adversarial Java parser.
# ---------------------------------------------------------------------------

def test_java_empty_class() -> None:
    """``class Foo {}`` é classe válida."""
    info = _parse_java("class Foo {}")
    classes = [(s.kind, s.name) for s in info.symbols if s.kind == "class"]
    assert ("class", "Foo") in classes


def test_java_method_with_throws_clause() -> None:
    """``void m() throws IOException`` — throws não pode bloquear match."""
    src = (
        "class Foo {\n"
        "    public void m() throws IOException, SQLException {\n"
        "        return;\n"
        "    }\n"
        "}\n"
    )
    info = _parse_java(src)
    # throws clause é detalhe não testado por enquanto; só queremos que o
    # método seja capturado.
    methods = [(s.kind, s.name) for s in info.symbols if s.kind == "method"]
    assert ("method", "m") in methods, (
        f"throws clause quebrou o match. Symbols: {methods}"
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
