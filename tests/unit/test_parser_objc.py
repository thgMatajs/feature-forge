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


# ---------------------------------------------------------------------------
# P-N-001 (REVIEW PR #16) — body extraction de método ObjC tem que popular
# ``body`` e ``body_hash``. Antes do fix, ``find_opening_brace`` recebia um
# offset DEPOIS do ``{`` (regex consumia o delimitador) e procurava o
# próximo ``{`` ou retornava None → body sempre None.
# ---------------------------------------------------------------------------

def test_objc_method_body_is_populated() -> None:
    """Método com corpo precisa entregar ``body`` não-None."""
    src = (
        "@implementation Foo\n"
        "- (NSString *)greet {\n"
        "    return @\"hello\";\n"
        "}\n"
        "@end\n"
    )
    info = _parse_objc(src)
    methods = [s for s in info.symbols if s.kind == "method"]
    assert len(methods) == 1
    assert methods[0].body is not None, (
        "Method body retornou None — P-N-001 regression. "
        f"Symbol: {methods[0]!r}"
    )
    assert "return @\"hello\"" in methods[0].body
    assert methods[0].body_hash is not None


def test_objc_fixture_method_has_body() -> None:
    """Fixture canônica: ``UserModel.m initWithId:name:`` precisa de body."""
    info = parse_objc_file(FIXTURES / "objc-basic" / "Models" / "UserModel.m")
    methods = [s for s in info.symbols if s.kind == "method"]
    init_m = next((m for m in methods if m.name == "initWithId:name:"), None)
    assert init_m is not None, (
        f"Selector composto initWithId:name: ausente. Vistos: "
        f"{[m.name for m in methods]}"
    )
    assert init_m.body is not None, (
        "Body do init na fixture saiu None — P-N-001 regression."
    )
    assert "super init" in init_m.body


# ---------------------------------------------------------------------------
# P-N-011 (REVIEW PR #16) — method header multi-linha (3+ selectors) é
# padrão ObjC; antes do fix, ``[^\n{;]+?`` no rest group bloqueava ``\n``.
# ---------------------------------------------------------------------------

def test_objc_multiline_method_header() -> None:
    """Header quebrado em múltiplas linhas continua casando."""
    src = (
        "@implementation Foo\n"
        "- (void)setUser:(NSString *)u\n"
        "          email:(NSString *)e\n"
        "       password:(NSString *)p {\n"
        "    return;\n"
        "}\n"
        "@end\n"
    )
    info = _parse_objc(src)
    methods = [s for s in info.symbols if s.kind == "method"]
    assert len(methods) == 1, (
        f"Multi-line header não casou — P-N-011 regression. Symbols: "
        f"{[(s.kind, s.name) for s in info.symbols]}"
    )
    assert methods[0].name == "setUser:email:password:"
    assert methods[0].body is not None


# ---------------------------------------------------------------------------
# P-N-002 (REVIEW PR #16) — body vazio (``@interface Foo\n@end``) deve
# preservar body_hash distinto de None (alinhamento com parser_java).
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# P-N-003 + T-N-003 (REVIEW PR #16) — categories e class extensions.
# ``@interface Foo (Bar)`` é category nomeada; ``@interface Foo ()`` é
# class extension (privado, definido no .m).
# ---------------------------------------------------------------------------

def test_objc_category_named() -> None:
    """``@interface UIView (Animations)`` vira symbol kind=category."""
    src = (
        "@interface UIView (Animations)\n"
        "- (void)fadeIn;\n"
        "@end\n"
    )
    info = _parse_objc(src)
    categories = [s for s in info.symbols if s.kind == "category"]
    assert len(categories) == 1, (
        f"Category não foi emitida — P-N-003 regression. "
        f"Symbols: {[(s.kind, s.name) for s in info.symbols]}"
    )
    assert categories[0].name == "UIView(Animations)"
    assert "@interface UIView (Animations)" in (categories[0].signature or "")


def test_objc_class_extension_anonymous() -> None:
    """``@interface Foo ()`` vira kind=class_extension."""
    src = (
        "@interface Foo ()\n"
        "@property NSString *privateField;\n"
        "@end\n"
    )
    info = _parse_objc(src)
    exts = [s for s in info.symbols if s.kind == "class_extension"]
    assert len(exts) == 1, (
        f"Class extension não foi emitida — P-N-003 regression. "
        f"Symbols: {[(s.kind, s.name) for s in info.symbols]}"
    )
    assert exts[0].name == "Foo"


def test_objc_category_does_not_double_emit_as_class() -> None:
    """``@interface Foo (Bar)`` não pode também aparecer como kind=class."""
    src = (
        "@interface Foo (Bar)\n"
        "- (void)baz;\n"
        "@end\n"
    )
    info = _parse_objc(src)
    classes_named_foo = [s for s in info.symbols if s.kind == "class" and s.name == "Foo"]
    assert classes_named_foo == [], (
        f"Foo apareceu como kind=class além de category — double-emission bug. "
        f"Symbols: {[(s.kind, s.name) for s in info.symbols]}"
    )


def test_objc_fixture_class_extension_parsed() -> None:
    """Fixture UserModel.m tem ``@interface UserModel ()`` — precisa virar class_extension."""
    info = parse_objc_file(FIXTURES / "objc-basic" / "Models" / "UserModel.m")
    exts = [s for s in info.symbols if s.kind == "class_extension"]
    assert len(exts) >= 1, (
        f"UserModel ()` na fixture não virou class_extension. "
        f"Symbols: {[(s.kind, s.name) for s in info.symbols]}"
    )
    assert exts[0].name == "UserModel"


def test_objc_empty_interface_keeps_body_hash() -> None:
    """``@interface Empty\n@end`` produz body="" — hash precisa existir."""
    src = "@interface Empty\n@end\n"
    info = _parse_objc(src)
    classes = [s for s in info.symbols if s.kind == "class"]
    assert len(classes) == 1
    # body string vazia (entre @interface e @end) é um valor válido — não None.
    assert classes[0].body is not None
    assert classes[0].body_hash is not None, (
        "Empty interface caiu pra body_hash=None — P-N-002 regression "
        "(truthiness vs is-not-none)."
    )
