"""Unit tests — engine.graph.parser_{kotlin,swift,typescript}.

Each parser is regex-based — these tests assert the right shape of facts is
extracted from small, hand-crafted samples (package + imports + annotations,
SwiftUI View detection, React functional component detection).
"""

from __future__ import annotations

from pathlib import Path

from engine.graph.parser_kotlin import parse_kotlin_file
from engine.graph.parser_swift import parse_swift_file
from engine.graph.parser_typescript import parse_typescript_file


# ── Kotlin ───────────────────────────────────────────────────────────────────


def test_parse_kotlin_extracts_package_and_imports(tmp_path):
    p = tmp_path / "F.kt"
    p.write_text(
        "package com.example.feature\n"
        "\n"
        "import kotlinx.coroutines.flow.MutableStateFlow\n"
        "import androidx.compose.runtime.Composable\n"
        "\n"
        "class FeatureViewModel\n",
        encoding="utf-8",
    )
    info = parse_kotlin_file(p)
    assert info.package == "com.example.feature"
    assert "kotlinx.coroutines.flow.MutableStateFlow" in info.imports
    assert "androidx.compose.runtime.Composable" in info.imports
    assert any(s.name == "FeatureViewModel" and s.kind == "class" for s in info.symbols)


def test_parse_kotlin_detects_composable(tmp_path):
    p = tmp_path / "Screen.kt"
    p.write_text(
        "package x\n"
        "import androidx.compose.runtime.Composable\n"
        "@Composable\n"
        "fun MyScreen() { }\n",
        encoding="utf-8",
    )
    info = parse_kotlin_file(p)
    matches = [s for s in info.symbols if s.name == "MyScreen"]
    assert matches
    assert matches[0].kind == "composable_fun"
    assert "Composable" in matches[0].annotations


def test_parse_kotlin_detects_koin_annotations(tmp_path):
    p = tmp_path / "DI.kt"
    p.write_text(
        "package x\n"
        "@Single\n"
        "class AuthRepository\n"
        "@Module\n"
        "@ComponentScan\n"
        "class AuthModule\n",
        encoding="utf-8",
    )
    info = parse_kotlin_file(p)
    ann_kinds = {(d["annotation"], d["class_name"]) for d in info.di_annotations}
    assert ("Single", "AuthRepository") in ann_kinds
    assert ("Module", "AuthModule") in ann_kinds


def test_parse_kotlin_test_tag_literal(tmp_path):
    p = tmp_path / "Screen.kt"
    p.write_text(
        "package x\n"
        'fun s() = Modifier.testTag("register_field_password")\n',
        encoding="utf-8",
    )
    info = parse_kotlin_file(p)
    assert "register_field_password" in info.test_tags_used


def test_parse_kotlin_sealed_class_kind(tmp_path):
    p = tmp_path / "S.kt"
    p.write_text("package x\nsealed class StateUI\n", encoding="utf-8")
    info = parse_kotlin_file(p)
    assert any(s.name == "StateUI" and s.kind == "sealed_class" for s in info.symbols)


# ── Swift ────────────────────────────────────────────────────────────────────


def test_parse_swift_detects_view_struct(tmp_path):
    p = tmp_path / "LoginScreen.swift"
    p.write_text(
        "import SwiftUI\n"
        "struct LoginScreenView: View {\n"
        '    var body: some View { Text("Login") }\n'
        "}\n",
        encoding="utf-8",
    )
    info = parse_swift_file(p)
    assert "SwiftUI" in info.imports
    matches = [s for s in info.symbols if s.name == "LoginScreenView"]
    assert matches and matches[0].is_view


def test_parse_swift_extracts_accessibility_identifier(tmp_path):
    p = tmp_path / "X.swift"
    p.write_text(
        "import SwiftUI\n"
        "struct X: View {\n"
        '   var body: some View { Text("hi").accessibilityIdentifier("login_submit") }\n'
        "}\n",
        encoding="utf-8",
    )
    info = parse_swift_file(p)
    assert "login_submit" in info.accessibility_ids


def test_parse_swift_detects_observable_object(tmp_path):
    p = tmp_path / "VM.swift"
    p.write_text(
        "import Combine\n"
        "class FeatureVM: ObservableObject {\n"
        "    @Published var state = 0\n"
        "}\n",
        encoding="utf-8",
    )
    info = parse_swift_file(p)
    matches = [s for s in info.symbols if s.name == "FeatureVM"]
    assert matches and matches[0].is_observable


# ── TypeScript ───────────────────────────────────────────────────────────────


def test_parse_typescript_extracts_imports_and_exports(tmp_path):
    p = tmp_path / "LoginPage.tsx"
    p.write_text(
        "import React from 'react';\n"
        "import { useTranslation } from 'react-i18next';\n"
        "export const LoginPage = () => {\n"
        "  const { t } = useTranslation();\n"
        '  return <div data-testid="login_submit">{t("login.title")}</div>;\n'
        "};\n",
        encoding="utf-8",
    )
    info = parse_typescript_file(p)
    assert "react" in info.imports
    assert "react-i18next" in info.imports
    assert "LoginPage" in info.components
    assert "login_submit" in info.test_ids
    assert "login.title" in info.i18n_keys_used
    assert info.uses_translation_hook is True


def test_parse_typescript_detects_arrow_component(tmp_path):
    p = tmp_path / "Btn.tsx"
    # Body wrapped in parens so the regex matches `=>(`/`=>{`.
    p.write_text(
        "import React from 'react';\n"
        "const MyButton = (props) => (<button>{props.children}</button>);\n"
        "export default MyButton;\n",
        encoding="utf-8",
    )
    info = parse_typescript_file(p)
    assert "MyButton" in info.components


def test_parse_typescript_tailwind_classes(tmp_path):
    p = tmp_path / "X.tsx"
    p.write_text(
        'const X = () => <div className="bg-primary text-on-primary">x</div>;\n'
        "export default X;\n",
        encoding="utf-8",
    )
    info = parse_typescript_file(p)
    assert "bg-primary" in info.tailwind_classes
    assert "text-on-primary" in info.tailwind_classes
