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
