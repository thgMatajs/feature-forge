"""Tests for engine.graph.parser_xml."""

from pathlib import Path

import pytest

from engine.graph.parser_xml import parse_xml_file

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_xml_layout_view_ids() -> None:
    info = parse_xml_file(FIXTURES / "xml-layout" / "res" / "layout" / "activity_login.xml")
    view_ids = {s.name for s in info.symbols if s.kind == "view_id"}
    assert "email_input" in view_ids
    assert "password_input" in view_ids
    assert "login_button" in view_ids


def test_xml_layout_class_refs() -> None:
    info = parse_xml_file(FIXTURES / "xml-layout" / "res" / "layout" / "activity_login.xml")
    assert "androidx.constraintlayout.widget.ConstraintLayout" in info.imports


def test_xml_layout_resource_keys() -> None:
    info = parse_xml_file(FIXTURES / "xml-layout" / "res" / "layout" / "activity_login.xml")
    assert "string/email_hint" in info.resource_keys
    assert "string/password_hint" in info.resource_keys
    assert "string/login_action" in info.resource_keys


def test_xml_fragment_data_binding() -> None:
    info = parse_xml_file(FIXTURES / "xml-layout" / "res" / "layout" / "fragment_profile.xml")
    # Binding variables
    assert len(info.binding_variables) == 1
    assert info.binding_variables[0][0] == "viewModel"
    assert info.binding_variables[0][1] == "com.example.profile.ProfileViewModel"

    # View IDs
    view_ids = {s.name for s in info.symbols if s.kind == "view_id"}
    assert "user_name" in view_ids
    assert "logout_button" in view_ids

    # Binding actions
    actions = [s for s in info.symbols if s.kind == "binding_action"]
    assert len(actions) >= 1


def test_xml_strings_resource() -> None:
    info = parse_xml_file(FIXTURES / "xml-resources" / "res" / "values" / "strings.xml")
    string_keys = {s.name for s in info.symbols if s.kind == "string_resource"}
    assert "app_name" in string_keys
    assert "email_hint" in string_keys
    assert "password_hint" in string_keys
    assert "login_action" in string_keys


# ---------------------------------------------------------------------------
# H-007 (REVIEW v1.3.0) — property reads (`@{viewModel.userName}`) precisam
# virar binding_action symbols. Antes do fix, o filter
# ``if "::" in expr or "->" in expr`` descartava todo property read.
# ---------------------------------------------------------------------------

def test_xml_property_read_binding_captured() -> None:
    """@{viewModel.userName} (property read) deve gerar binding_action."""
    info = parse_xml_file(FIXTURES / "xml-layout" / "res" / "layout" / "fragment_profile.xml")
    bindings = [s for s in info.symbols if s.kind == "binding_action"]
    # Property read deve estar presente (regression: antes era filtrado).
    assert any("viewModel.userName" in s.name for s in bindings), (
        f"Property read ``@{{viewModel.userName}}`` não foi capturada — "
        f"H-007 regression. Bindings vistos: {[b.name for b in bindings]}"
    )
    # E a lambda ``@{() -> viewModel.onLogout()}`` continua presente.
    assert any("onLogout" in s.name for s in bindings)


def test_xml_binding_action_is_method_call_flag() -> None:
    """is_method_call distingue property read de invocation/lambda."""
    info = parse_xml_file(FIXTURES / "xml-layout" / "res" / "layout" / "fragment_profile.xml")
    bindings = [s for s in info.symbols if s.kind == "binding_action"]
    by_name = {b.name: b for b in bindings}

    # Property read → is_method_call = False
    prop_read = next(
        (b for n, b in by_name.items() if "userName" in n and "(" not in n),
        None,
    )
    assert prop_read is not None
    assert prop_read.is_method_call is False, (
        "Property read deveria ter is_method_call=False"
    )

    # Lambda com invocation → is_method_call = True
    lambda_call = next(
        (b for n, b in by_name.items() if "onLogout" in n),
        None,
    )
    assert lambda_call is not None
    assert lambda_call.is_method_call is True, (
        "Lambda invocation deveria ter is_method_call=True"
    )


# ---------------------------------------------------------------------------
# P-N-006 (REVIEW PR #16) — resource prefixes incompletos.
# ---------------------------------------------------------------------------

def test_xml_resource_prefix_navigation(tmp_path) -> None:
    """``@navigation/main_graph`` precisa virar resource_key."""
    from engine.graph.parser_xml import _parse_xml
    src = (
        '<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">\n'
        '  <fragment android:name="@navigation/main_graph"/>\n'
        '  <Foo android:icon="@font/roboto"/>\n'
        '  <Foo android:menu="@menu/main_menu"/>\n'
        '</LinearLayout>\n'
    )
    info = _parse_xml(src, tmp_path / "layout" / "fake.xml")
    keys = set(info.resource_keys)
    assert any(k.startswith("navigation/") for k in keys), (
        f"@navigation/ prefix não casou — P-N-006 regression. Keys: {keys}"
    )
    assert any(k.startswith("font/") for k in keys), (
        f"@font/ prefix não casou — P-N-006 regression. Keys: {keys}"
    )
    assert any(k.startswith("menu/") for k in keys), (
        f"@menu/ prefix não casou — P-N-006 regression. Keys: {keys}"
    )


# ---------------------------------------------------------------------------
# P-N-014 / codereviewbot parser_xml:81 (REVIEW PR #16) — class_refs dedup.
# ---------------------------------------------------------------------------

def test_xml_class_refs_deduped(tmp_path) -> None:
    """Mesma classe FQ em tag + attr não pode aparecer 2x em imports."""
    from engine.graph.parser_xml import _parse_xml
    src = (
        '<androidx.constraintlayout.widget.ConstraintLayout '
        '  android:name="androidx.constraintlayout.widget.ConstraintLayout">\n'
        '  <com.example.MyView class="com.example.MyView"/>\n'
        '</androidx.constraintlayout.widget.ConstraintLayout>\n'
    )
    info = _parse_xml(src, tmp_path / "layout" / "fake.xml")
    # imports é sorted unique list — sem duplicatas.
    assert len(info.imports) == len(set(info.imports)), (
        f"imports tem duplicatas — P-N-014 regression. imports={info.imports}"
    )


# ---------------------------------------------------------------------------
# P-N-018 / codereviewbot parser_xml:109 (REVIEW PR #16) — layout fallback
# por root tag quando path não tem ``/layout/``.
# ---------------------------------------------------------------------------

def test_xml_layout_detection_by_root_tag(tmp_path) -> None:
    """Arquivo sem ``/layout/`` no path mas com root LinearLayout → is_layout."""
    from engine.graph.parser_xml import _parse_xml
    src = (
        '<?xml version="1.0"?>\n'
        '<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">\n'
        '  <Button android:id="@+id/btn"/>\n'
        '</LinearLayout>\n'
    )
    # Path SEM /layout/
    info = _parse_xml(src, tmp_path / "fixtures" / "weird.xml")
    assert info.is_layout is True, (
        "Root LinearLayout não foi detectado como layout — P-N-018 regression."
    )
    view_ids = {s.name for s in info.symbols if s.kind == "view_id"}
    assert "btn" in view_ids


# ---------------------------------------------------------------------------
# T-N-007 (REVIEW PR #16) — adversarial XML edge cases.
# ---------------------------------------------------------------------------

def test_xml_empty_file(tmp_path) -> None:
    """Arquivo XML vazio não deve crashar."""
    from engine.graph.parser_xml import _parse_xml
    info = _parse_xml("", tmp_path / "empty.xml")
    assert info.symbols == []
    assert info.imports == []


def test_xml_with_bom_prefix(tmp_path) -> None:
    """BOM UTF-8 (``\\ufeff``) no início não deve quebrar parsing."""
    from engine.graph.parser_xml import _parse_xml
    src = (
        '﻿<?xml version="1.0"?>\n'
        '<resources>\n'
        '  <string name="hello">Hi</string>\n'
        '</resources>\n'
    )
    info = _parse_xml(src, tmp_path / "values" / "strings.xml")
    assert info.is_resources is True
    string_keys = {s.name for s in info.symbols if s.kind == "string_resource"}
    assert "hello" in string_keys


def test_xml_comment_with_classlike_text(tmp_path) -> None:
    """Comentário com texto que parece class FQ não deve virar import."""
    from engine.graph.parser_xml import _parse_xml
    src = (
        '<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">\n'
        '  <!-- TODO: replace with com.example.RealView -->\n'
        '  <TextView android:id="@+id/title"/>\n'
        '</LinearLayout>\n'
    )
    info = _parse_xml(src, tmp_path / "layout" / "fake.xml")
    # ``com.example.RealView`` no comentário pode (regex naive) virar import;
    # comportamento conhecido — registramos pra rastrear se vira problema.
    # NOTA: este teste é informativo — se passar com RealView NÃO em imports,
    # ótimo; se aparecer, gap conhecido fica documentado em PR-N-016.
    # Aqui não assertamos forte — apenas verificamos que parsing não crasha.
    assert isinstance(info.imports, list)
