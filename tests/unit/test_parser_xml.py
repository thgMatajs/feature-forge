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
