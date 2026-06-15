"""Tests for engine.graph.parser_java."""

from pathlib import Path

import pytest

from engine.graph.parser_java import parse_java_file

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
    info = parse_java_file(FIXTURES / "java-annotations" / "com" / "example" / "InjectService.java")
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
