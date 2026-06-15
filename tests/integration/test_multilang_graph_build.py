"""Integration: full build sobre fixture multilíngue.

Confirma que ``build_full`` dispatcha pros 3 parsers novos (Java, XML,
ObjC) e persiste symbols com a shape esperada. Cobre o caminho ``ext →
language → _persist_*`` para .java, .xml e .m simultaneamente.

Refs:
- docs/superpowers/specs/2026-06-12-graph-ia-evolution.md AC-2/AC-7
- engine/graph/builder.py ``build_full`` + ``_ingest_file``
- engine/graph/parser_{java,xml,objc}.py

Marker: ``integration`` — escrita em filesystem real + walk completo.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from engine.graph.builder import build_full

pytestmark = pytest.mark.integration


@pytest.fixture
def multilang_project(tmp_path: Path) -> Path:
    """Greenfield mínimo com 1 arquivo .java + 1 .xml de layout + 1 .m.

    Estrutura:
        .git/                            # marker de project root
        .claude/                         # forge bootstraps the graph aqui
        src/main/java/Foo.java           # Java class detection
        src/main/res/layout/main.xml     # layout → view_id + class_ref kicks
        src/Bar.m                        # ObjC @implementation

    O path ``res/layout/`` é o trigger pro parser XML emitir symbols
    (resources fora desse layout viram no-op deliberadamente).
    """
    (tmp_path / ".git").mkdir()
    (tmp_path / ".claude").mkdir()

    java_dir = tmp_path / "src" / "main" / "java"
    java_dir.mkdir(parents=True)
    (java_dir / "Foo.java").write_text(
        "package com.example;\n"
        "public class Foo {\n"
        "    public void greet() { }\n"
        "}\n",
        encoding="utf-8",
    )

    layout_dir = tmp_path / "src" / "main" / "res" / "layout"
    layout_dir.mkdir(parents=True)
    (layout_dir / "main.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"\n'
        '    android:id="@+id/root"\n'
        '    android:orientation="vertical">\n'
        '    <TextView android:id="@+id/title" />\n'
        '</LinearLayout>\n',
        encoding="utf-8",
    )

    objc_dir = tmp_path / "src"
    (objc_dir / "Bar.m").write_text(
        "#import <Foundation/Foundation.h>\n"
        "@implementation Bar\n"
        "- (void)doStuff { }\n"
        "@end\n",
        encoding="utf-8",
    )

    return tmp_path


def test_full_build_dispatches_to_java_xml_objc_parsers(multilang_project: Path) -> None:
    """build_full visita .java, .xml e .m → cada um produz pelo menos 1 symbol.

    Não precisamos pinar count exato (parsers regex-based podem evoluir).
    Asserção minimal: cada language tem ≥1 entry em ``files`` E cada
    language tem ≥1 symbol persistido. Isso é suficiente pra detectar
    regressão "parser deixou de ser chamado" ou "_persist_* quebrou".
    """
    result = build_full(multilang_project)
    assert result["files_scanned"] >= 3  # java + xml + objc

    db = multilang_project / ".claude" / "graph.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        languages = {
            row["language"]
            for row in conn.execute("SELECT DISTINCT language FROM files").fetchall()
        }
        assert "java" in languages
        assert "xml" in languages
        assert "objc" in languages

        # Símbolos por linguagem — pelo menos 1 cada.
        rows = conn.execute(
            "SELECT files.language AS lang, symbols.kind AS kind "
            "FROM symbols JOIN files ON symbols.file_id = files.id "
            "WHERE files.language IN ('java', 'xml', 'objc')"
        ).fetchall()
        kinds_by_lang: dict[str, set[str]] = {}
        for r in rows:
            kinds_by_lang.setdefault(r["lang"], set()).add(r["kind"])

        assert "java" in kinds_by_lang, "Java parser não produziu symbols"
        assert "class" in kinds_by_lang["java"], (
            "Java parser deveria detectar `public class Foo`"
        )

        assert "objc" in kinds_by_lang, "ObjC parser não produziu symbols"
        assert any(k.startswith("objc_") for k in kinds_by_lang["objc"]), (
            "ObjC kinds deveriam ter prefixo `objc_` (cf. _persist_objc)"
        )

        assert "xml" in kinds_by_lang, "XML parser não produziu symbols"
        # XML em /layout/ deve emitir pelo menos view_id ou class_ref
        xml_kinds = kinds_by_lang["xml"]
        assert xml_kinds & {"view_id", "class_ref"}, (
            f"XML em /layout/ deveria emitir view_id ou class_ref; got {xml_kinds}"
        )
    finally:
        conn.close()
