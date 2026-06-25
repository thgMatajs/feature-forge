"""Unit tests — reuse-intelligence pipeline (schema v2).

Covers the critical paths added by ``feat/reuse-intelligence-complete``:
- ``engine.graph._body_text`` — extraction + normalization + tokenization
- ``engine.graph.gradle_modules`` — settings.gradle parsing + module inference
- ``engine.graph.gradle_deps`` — build.gradle parsing + dependency closure
- ``engine.graph.parser_kotlin / parser_swift / parser_typescript`` — new fields
- ``engine.graph.duplicates`` — 6-category detection + proposal queuing
- ``engine.graph.reuse_apply`` — slug derivation + intake stub rendering
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from engine.graph import _body_text as body_text
from engine.graph.gradle_deps import (
    build_dependency_closure,
    find_smallest_common_ancestor,
    infer_suggested_target,
    parse_module_dependencies,
)
from engine.graph.gradle_modules import (
    infer_module_and_source_set,
    load_gradle_modules,
)
from engine.graph.parser_kotlin import parse_kotlin_file
from engine.graph.parser_swift import parse_swift_file
from engine.graph.parser_typescript import parse_typescript_file


# ── body_text helpers ───────────────────────────────────────────────────────


def test_extract_function_body_respects_strings_and_comments():
    src = """
    fun foo() {
        val s = "ignore { brace } in string"
        // ignore // comment {
        /* and */
        return 42
    }
    """
    brace = src.index("{")
    body = body_text.extract_function_body(src, brace, language="kotlin")
    assert body is not None
    assert "return 42" in body
    assert "ignore" not in body or "return" in body  # body kept


def test_extract_function_body_returns_none_on_mismatch():
    src = "fun foo() { val x = 1"  # unbalanced
    brace = src.index("{")
    assert body_text.extract_function_body(src, brace, language="kotlin") is None


def test_hash_body_is_deterministic_and_strips_comments():
    a = "val x = 1\nreturn x // first"
    b = "val x = 1\nreturn x  // second"
    c = "val x = 2\nreturn x"
    assert body_text.hash_body(a) == body_text.hash_body(b)
    assert body_text.hash_body(a) != body_text.hash_body(c)
    assert len(body_text.hash_body(a)) == 16


def test_jaccard_similarity_basic():
    a = frozenset({"foo", "bar", "baz"})
    b = frozenset({"foo", "bar", "qux"})
    assert body_text.jaccard_similarity(a, b) == 0.5
    assert body_text.jaccard_similarity(frozenset(), frozenset()) == 0.0
    assert body_text.jaccard_similarity(a, a) == 1.0


def test_extract_body_tokens_filters_noise_per_lang():
    kotlin_tokens = body_text.extract_body_tokens("val x = doStuff()", "kotlin")
    assert "val" not in kotlin_tokens
    assert "dostuff" in kotlin_tokens

    swift_tokens = body_text.extract_body_tokens("let y = work()", "swift")
    assert "let" not in swift_tokens
    assert "work" in swift_tokens


def test_tokens_roundtrip_via_json():
    tokens = body_text.extract_body_tokens("doStuff(a, b)", "kotlin")
    payload = body_text.tokens_to_json(tokens)
    restored = body_text.tokens_from_json(payload)
    assert restored == tokens


# ── Gradle modules inference ────────────────────────────────────────────────


def test_load_gradle_modules_parses_kts(tmp_path: Path):
    (tmp_path / "settings.gradle.kts").write_text(
        'rootProject.name = "demo"\n'
        'include(":shared:core")\n'
        'include(":shared:feature:auth")\n'
        'include(":androidApp:core")\n',
        encoding="utf-8",
    )
    modules = load_gradle_modules(tmp_path)
    assert modules["shared/core"] == "shared:core"
    assert modules["shared/feature/auth"] == "shared:feature:auth"
    assert modules["androidApp/core"] == "androidApp:core"


def test_infer_module_uses_longest_prefix(tmp_path: Path):
    modules = {
        "shared/core": "shared:core",
        "shared/feature/auth": "shared:feature:auth",
    }
    assert infer_module_and_source_set(
        "shared/feature/auth/src/commonMain/kotlin/A.kt", modules
    ) == ("shared:feature:auth", "commonMain")
    assert infer_module_and_source_set(
        "shared/core/src/androidMain/kotlin/X.kt", modules
    ) == ("shared:core", "androidMain")


def test_infer_module_falls_back_to_first_segment(tmp_path: Path):
    # Mono-module project: no settings.gradle, no matches
    module, source_set = infer_module_and_source_set("app/src/main/Foo.kt", {})
    assert module == "app"
    assert source_set is None


# ── Gradle dependency parsing + closure ─────────────────────────────────────


def test_parse_module_dependencies_extracts_implementation(tmp_path: Path):
    (tmp_path / "settings.gradle.kts").write_text(
        'include(":shared:core")\ninclude(":shared:feature:auth")\n',
        encoding="utf-8",
    )
    (tmp_path / "shared" / "feature" / "auth").mkdir(parents=True)
    (tmp_path / "shared" / "feature" / "auth" / "build.gradle.kts").write_text(
        'dependencies { implementation(project(":shared:core")) }\n', encoding="utf-8"
    )
    modules = load_gradle_modules(tmp_path)
    deps = parse_module_dependencies(tmp_path, modules)
    assert ("shared:feature:auth", "shared:core", "implementation") in deps


def test_dependency_closure_is_transitive():
    deps = [
        ("a", "b", "implementation"),
        ("b", "c", "implementation"),
        ("d", "c", "implementation"),
    ]
    closure = build_dependency_closure(deps)
    assert "c" in closure["a"]
    assert "c" in closure["b"]
    assert "a" not in closure["d"]


def test_find_smallest_common_ancestor_picks_most_depended():
    deps = [
        ("auth", "core", "implementation"),
        ("bonsai", "core", "implementation"),
        ("home", "core", "implementation"),
    ]
    closure = build_dependency_closure(deps)
    ancestor = find_smallest_common_ancestor(["auth", "bonsai"], closure)
    assert ancestor == "core"


def test_infer_suggested_target_uses_closure_for_cross_module():
    deps = [
        ("shared:feature:auth", "shared:core", "implementation"),
        ("shared:feature:bonsai", "shared:core", "implementation"),
    ]
    closure = build_dependency_closure(deps)
    target = infer_suggested_target(
        "duplicate-cross-module",
        ["shared:feature:auth", "shared:feature:bonsai"],
        closure,
        {
            "shared/feature/auth": "shared:feature:auth",
            "shared/feature/bonsai": "shared:feature:bonsai",
            "shared/core": "shared:core",
        },
    )
    assert "shared/core" in target


# ── Parsers — new field extraction ──────────────────────────────────────────


def test_kotlin_parser_extracts_extension_receiver(tmp_path: Path):
    f = tmp_path / "X.kt"
    f.write_text(
        "package x.y\n"
        "private fun FirebaseAnalytics.logEventSafely(eventName: String): Boolean {\n"
        "  return runCatching { logEvent(eventName, null) }.isSuccess\n"
        "}\n",
        encoding="utf-8",
    )
    info = parse_kotlin_file(f)
    funs = [s for s in info.symbols if s.kind == "fun"]
    assert len(funs) == 1
    sym = funs[0]
    assert sym.name == "logEventSafely"
    assert sym.receiver_type == "FirebaseAnalytics"
    assert sym.visibility == "private"
    assert sym.body_hash is not None
    assert "FirebaseAnalytics.fun(String)" in (sym.signature or "")
    assert "Boolean" in (sym.signature or "")


def test_swift_parser_attaches_extension_receiver(tmp_path: Path):
    f = tmp_path / "X.swift"
    f.write_text(
        "extension View {\n"
        "    public func bonsaiFormDiscardDialog(isPresented: Binding<Bool>) -> some View {\n"
        "        return self\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    info = parse_swift_file(f)
    funs = [s for s in info.symbols if s.kind == "func"]
    assert len(funs) == 1
    sym = funs[0]
    assert sym.receiver_type == "View"
    assert sym.body_hash is not None
    assert "View.func" in (sym.signature or "")


def test_typescript_parser_extracts_function_body(tmp_path: Path):
    f = tmp_path / "X.ts"
    f.write_text(
        "export function add(a: number, b: number): number {\n"
        "  return a + b\n"
        "}\n",
        encoding="utf-8",
    )
    info = parse_typescript_file(f)
    funs = [s for s in info.symbols if s.kind == "function"]
    assert any(s.name == "add" and s.body_hash for s in funs)


# ── Detection + queuing end-to-end ─────────────────────────────────────────


def _scaffold_two_module_duplicate(root: Path) -> None:
    (root / "settings.gradle.kts").write_text(
        'include(":shared:core")\n'
        'include(":shared:feature:a")\n'
        'include(":shared:feature:b")\n',
        encoding="utf-8",
    )
    for module in ("shared/feature/a", "shared/feature/b"):
        (root / module).mkdir(parents=True, exist_ok=True)
        (root / module / "build.gradle.kts").write_text(
            'dependencies { implementation(project(":shared:core")) }\n',
            encoding="utf-8",
        )
    body = (
        "package x\n"
        "import com.google.firebase.analytics.FirebaseAnalytics\n\n"
        "private fun FirebaseAnalytics.logEventSafely(eventName: String) {\n"
        "    runCatching { logEvent(eventName, null) }\n"
        "}\n"
    )
    for module in ("shared/feature/a", "shared/feature/b"):
        target = root / module / "src/androidMain/kotlin/X.kt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")


def test_full_pipeline_detects_cross_module_duplicate(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FORGE_HOME", str(Path(__file__).resolve().parents[2]))
    _scaffold_two_module_duplicate(tmp_path)

    claude = tmp_path / ".claude"
    claude.mkdir(parents=True)

    from engine.graph.builder import build_full
    from engine.graph.duplicates import queue_proposals_from_table
    from engine.memory.distiller import read_proposals_queue

    build_full(tmp_path, db_path=claude / "graph.db")
    n_queued = queue_proposals_from_table(tmp_path)
    assert n_queued >= 1

    proposals = read_proposals_queue(tmp_path)
    assert any(p.kind == "promote-to-shared-helper" for p in proposals)


def test_pipeline_is_idempotent_on_rebuild(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FORGE_HOME", str(Path(__file__).resolve().parents[2]))
    _scaffold_two_module_duplicate(tmp_path)
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True)

    from engine.graph.builder import build_full
    from engine.graph.duplicates import queue_proposals_from_table
    from engine.memory.distiller import read_proposals_queue

    build_full(tmp_path, db_path=claude / "graph.db")
    queue_proposals_from_table(tmp_path)
    first = read_proposals_queue(tmp_path)

    build_full(tmp_path, db_path=claude / "graph.db")
    queue_proposals_from_table(tmp_path)
    second = read_proposals_queue(tmp_path)

    assert len(first) == len(second)
    assert {p.fingerprint for p in first} == {p.fingerprint for p in second}


# ── Reuse apply — slug + intake materialization ────────────────────────────


def test_slug_for_kebabifies_receiver_and_name():
    from engine.graph.reuse_apply import _slug_for
    from engine.memory.distiller import DistillationProposal

    proposal = DistillationProposal(
        id="P-0001",
        kind="promote-to-shared-helper",
        title="(t)",
        description="(d)",
        payload={
            "payload": {
                "receiver_type": "FirebaseAnalytics",
                "symbol_name": "logEventSafely",
            }
        },
    )
    assert _slug_for(proposal) == "refactor-firebase-analytics-log-event-safely"


def test_apply_writes_intake_and_status(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FORGE_HOME", str(Path(__file__).resolve().parents[2]))
    _scaffold_two_module_duplicate(tmp_path)
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True)

    from engine.graph.builder import build_full
    from engine.graph.duplicates import queue_proposals_from_table
    from engine.memory.distiller import apply_proposal_to_l2, read_proposals_queue

    build_full(tmp_path, db_path=claude / "graph.db")
    queue_proposals_from_table(tmp_path)

    proposals = read_proposals_queue(tmp_path)
    assert proposals
    apply_proposal_to_l2(tmp_path, proposals[0])

    intake = (
        tmp_path
        / "docs/forge-specs/non-product"
        / "refactor-firebase-analytics-log-event-safely"
        / "feature-intake.md"
    )
    assert intake.exists()
    contents = intake.read_text(encoding="utf-8")
    assert "subtype: \"refactor\"" in contents
    assert "FirebaseAnalytics.logEventSafely" in contents

    status_path = (
        claude / "memory/L1" / "refactor-firebase-analytics-log-event-safely" / "status.json"
    )
    assert status_path.exists()
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["subtype"] == "refactor"
    assert status["source-proposal-id"]


def test_build_template_context_tolerates_non_dict_locations() -> None:
    """C-13 (PR18-B1): location malformada (não-dict) no payload não estoura
    AttributeError nas comprehensions de paths/languages — é ignorada."""
    from engine.graph.reuse_apply import _build_template_context, DistillationProposal

    proposal = DistillationProposal(
        id="P1", kind="promote", title="Helper", description="d"
    )
    locations = [
        {"path": "a/A.kt", "language": "kotlin"},
        None,            # malformada
        "garbage",       # malformada
        {"path": "b/B.kt"},
    ]
    ctx = _build_template_context("slug", proposal, {}, locations)
    assert ctx["feature_slug"] == "slug"  # não crashou
