"""Tests for engine.graph.parser_objc."""

from pathlib import Path

import pytest

from engine.graph.parser_objc import _parse_objc, parse_objc_file

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


# ---------------------------------------------------------------------------
# C-002 (REVIEW v1.3.0) — regressão: selector composto precisa juntar TODOS
# os labels ObjC (``label1:label2:label3:``) em vez de duplicar group 3 +
# group 5 (param name).
# ---------------------------------------------------------------------------

def test_objc_multi_segment_selector() -> None:
    src = (
        "@implementation Foo\n"
        "- (void)initWithId:(NSString *)userId name:(NSString *)name { }\n"
        "@end\n"
    )
    info = _parse_objc(src)
    methods = [s for s in info.symbols if s.kind == "method"]
    assert len(methods) == 1
    assert methods[0].name == "initWithId:name:", (
        f"Expected ObjC-canonical composite selector, got {methods[0].name!r}"
    )


def test_objc_three_segment_selector() -> None:
    src = (
        "@implementation Foo\n"
        "- (void)setUser:(NSString *)u email:(NSString *)e password:(NSString *)p { }\n"
        "@end\n"
    )
    info = _parse_objc(src)
    methods = [s for s in info.symbols if s.kind == "method"]
    assert len(methods) == 1
    assert methods[0].name == "setUser:email:password:"


def test_objc_no_arg_method_keeps_simple_name() -> None:
    src = (
        "@implementation Foo\n"
        "- (NSString *)displayName { return @\"x\"; }\n"
        "@end\n"
    )
    info = _parse_objc(src)
    methods = [s for s in info.symbols if s.kind == "method"]
    assert len(methods) == 1
    assert methods[0].name == "displayName"


# ---------------------------------------------------------------------------
# L-003 (REVIEW v1.3.0) — comentário ``// - text`` não pode virar method.
# ---------------------------------------------------------------------------

def test_objc_no_match_in_comment() -> None:
    src = (
        "@implementation Foo\n"
        "// - here's a note\n"
        "- (void)real { }\n"
        "@end\n"
    )
    info = _parse_objc(src)
    methods = [s for s in info.symbols if s.kind == "method"]
    assert len(methods) == 1
    assert methods[0].name == "real"


# ---------------------------------------------------------------------------
# L-007 (REVIEW v1.3.0) — implementation/protocol também populam body_hash
# e signature, igual @interface.
# ---------------------------------------------------------------------------

def test_objc_implementation_body_hash_populated() -> None:
    src = (
        "@implementation Foo\n"
        "- (void)bar { }\n"
        "@end\n"
    )
    info = _parse_objc(src)
    impls = [s for s in info.symbols if s.kind == "implementation"]
    assert len(impls) == 1
    assert impls[0].body_hash is not None
    assert impls[0].signature == "@implementation Foo"


def test_objc_protocol_body_hash_populated() -> None:
    src = (
        "@protocol Foo\n"
        "- (void)bar;\n"
        "@end\n"
    )
    info = _parse_objc(src)
    protos = [s for s in info.symbols if s.kind == "protocol"]
    assert len(protos) == 1
    assert protos[0].body_hash is not None
    assert protos[0].signature == "@protocol Foo"


# ---------------------------------------------------------------------------
# L-002 (REVIEW v1.3.0) — @property aceita generics no tipo (NSArray<UserModel *>).
# ---------------------------------------------------------------------------

def test_objc_property_with_generics() -> None:
    src = (
        "@interface Foo\n"
        "@property (nonatomic, strong) NSArray<UserModel *> *users;\n"
        "@property (nonatomic, copy) NSString *name;\n"
        "@end\n"
    )
    info = _parse_objc(src)
    props = [s for s in info.symbols if s.kind == "property"]
    names = {p.name for p in props}
    assert "users" in names, (
        f"Property com generics ``NSArray<UserModel *> *users`` não foi capturada — "
        f"L-002 regression. Properties vistas: {names}"
    )
    assert "name" in names


# ---------------------------------------------------------------------------
# H-009 (REVIEW v1.3.0) — visibility detection precisa rodar por kind no
# builder (testa indireta via parser_objc.py + _persist_objc no Group A).
# Aqui validamos APENAS que o parser entrega kind separado pra
# implementation vs class — o mapping kind→visibility é builder.py.
# ---------------------------------------------------------------------------

def test_objc_parser_distinguishes_class_from_implementation() -> None:
    src = (
        "@interface Foo : NSObject\n"
        "@end\n"
        "@implementation Foo\n"
        "@end\n"
    )
    info = _parse_objc(src)
    kinds = {s.kind for s in info.symbols}
    assert "class" in kinds
    assert "implementation" in kinds
