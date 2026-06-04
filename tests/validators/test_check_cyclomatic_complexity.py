"""Entry-point tests for check_cyclomatic_complexity.validate.

Most paths are mocked at the dispatch layer — these tests pin the
orchestration logic (threshold lookup, override application, ignore-paths,
disabled-config short-circuit, tool-missing warn).

Spec source: `docs/superpowers/specs/2026-06-03-cc-gate-design.md §2` (pipeline
11 passos) + `.claude/rules/disciplines.md §1` (3-paths block contract). Plan
source: `docs/superpowers/plans/2026-06-03-cc-gate-implementation.md` (Task 8).

Estratégia de mock:
- `_run_tools_for_staged` é monkeypatchado pra simular cada combinação de
  resultados sem invocar Detekt/SwiftLint/eslint/radon de verdade. Subprocess
  fica completamente isolado.
- `_git_staged_files` retorna paths fake controlados pelo teste.
- `_load_workflow_config` injeta config arbitrária por cenário.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import check_cyclomatic_complexity as v


def _mk_result(**overrides) -> v.CCResult:
    """Helper pra montar CCResult com defaults sensatos."""
    defaults = dict(
        file="app/A.kt",
        function="foo",
        line_start=10,
        line_end=30,
        cc=12,
        language="kotlin",
        status="new",
        cc_before=None,
    )
    defaults.update(overrides)
    return v.CCResult(**defaults)


@pytest.fixture
def fake_context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Build a minimal context the orchestrator can consume.

    Monkeypatches all I/O helpers (git, config, cards, commit body) ao seu
    estado mais simples — testes individuais sobreescrevem o que importa.
    """
    monkeypatch.setattr(
        v,
        "_git_staged_files",
        lambda root: [tmp_path / "app/A.kt"],
    )
    monkeypatch.setattr(
        v,
        "_extract_diff_hunks",
        lambda root, files: {"app/A.kt": [{"start": 1, "end": 100, "kind": "add"}]},
    )
    monkeypatch.setattr(v, "_read_commit_body", lambda root: "")
    monkeypatch.setattr(v, "_load_active_cards", lambda root: [])
    monkeypatch.setattr(
        v,
        "_load_workflow_config",
        lambda root: {"cc-gate": {"enabled": True, "kotlin": 10}},
    )
    # Faz tmp_path / "app/A.kt" "existir" pra is_file() na coleta — vital pra
    # _git_staged_files real, mas a versão mockada nem chama; deixamos por
    # robustez se algum teste reverter o mock.
    (tmp_path / "app").mkdir(exist_ok=True)
    (tmp_path / "app" / "A.kt").write_text("// stub\n", encoding="utf-8")
    return tmp_path


def test_happy_path_all_below_threshold(monkeypatch, fake_context):
    """Todas as funções com cc < threshold → result_pass."""
    monkeypatch.setattr(
        v,
        "_run_tools_for_staged",
        lambda **kw: ([_mk_result(cc=8)], []),
    )
    result = v.validate(fake_context)
    assert result["status"] == "pass"


def test_fail_when_new_function_exceeds_threshold(monkeypatch, fake_context):
    """Função nova com cc > threshold → result_fail + 3-paths block."""
    monkeypatch.setattr(
        v,
        "_run_tools_for_staged",
        lambda **kw: ([_mk_result(cc=14, status="new")], []),
    )
    result = v.validate(fake_context)
    assert result["status"] == "fail"
    assert "Cyclomatic Complexity" in (result.get("message") or "")
    assert len(result["paths"]) == 3


def test_fail_includes_canonical_three_paths_render(monkeypatch, fake_context):
    """H3 — `validate()` must expose the canonical 3-paths render so the
    consumer (engine.implement) can surface mentor-calmo prose to the user.

    Spec §4 + disciplines §1: the literal header `🛑 Cyclomatic Complexity
    gate` and the section `Três caminhos pra resolver:` are load-bearing
    UX contract — they must appear in the result dict's `render` field
    (or `message`), not only in the snapshot test.
    """
    monkeypatch.setattr(
        v,
        "_run_tools_for_staged",
        lambda **kw: ([_mk_result(cc=14, status="new")], []),
    )
    result = v.validate(fake_context)
    rendered = result.get("render") or result.get("message") or ""
    assert "🛑 Cyclomatic Complexity gate" in rendered, (
        f"canonical header missing from result; got: {rendered!r}"
    )
    assert "Três caminhos pra resolver" in rendered


def test_fail_warnings_include_malformed_override_attempts(
    monkeypatch, fake_context
):
    """H4 — malformed CC-OVERRIDE in commit body must surface as a warning
    on the result dict (currently swallowed by `_apply_overrides`).

    Spec §4 step 5: "Falta o `— <texto>` (razão concreta) → override **não
    conta**. Validator emite warning 'CC-OVERRIDE sem razão — adicione
    texto após —'. Mantém o fail."
    """
    monkeypatch.setattr(
        v,
        "_run_tools_for_staged",
        lambda **kw: ([_mk_result(cc=14, status="new", function="bar")], []),
    )
    monkeypatch.setattr(
        v,
        "_read_commit_body",
        lambda root: "feat: x\n\nCC-OVERRIDE: app/A.kt:bar cc=14 missing-dash\n",
    )
    result = v.validate(fake_context)
    # The fail still surfaces (override malformed doesn't silence).
    assert result["status"] == "fail"
    # The warning is visible in the result (under `warnings`).
    warnings = result.get("warnings") or []
    assert any("CC-OVERRIDE sem razão" in w for w in warnings), (
        f"expected malformed-override warning in result.warnings; got: {warnings!r}"
    )


def test_delta_rule_modified_worse_fails(monkeypatch, fake_context):
    """Modified com cc_after > cc_before (mesmo se < threshold) → fail."""
    monkeypatch.setattr(
        v,
        "_run_tools_for_staged",
        lambda **kw: ([_mk_result(cc=11, status="modified", cc_before=9)], []),
    )
    result = v.validate(fake_context)
    assert result["status"] == "fail"


def test_delta_rule_modified_same_or_better_passes(monkeypatch, fake_context):
    """Modified com cc_after == cc_before NÃO é regressão → pass mesmo > thr."""
    monkeypatch.setattr(
        v,
        "_run_tools_for_staged",
        lambda **kw: ([_mk_result(cc=12, status="modified", cc_before=12)], []),
    )
    result = v.validate(fake_context)
    assert result["status"] == "pass"


def test_override_silences_specific_function(monkeypatch, fake_context):
    """CC-OVERRIDE em commit body silencia (file, func) específico."""
    monkeypatch.setattr(
        v,
        "_run_tools_for_staged",
        lambda **kw: ([_mk_result(cc=14, function="bar")], []),
    )
    monkeypatch.setattr(
        v,
        "_read_commit_body",
        lambda root: "feat: x\n\nCC-OVERRIDE: app/A.kt:bar cc=14 — irreducible DSL\n",
    )
    result = v.validate(fake_context)
    assert result["status"] == "pass"


def test_ignore_paths_filters_test_files(monkeypatch, fake_context, tmp_path):
    """Files em tests/ devem ser filtrados via ignore-paths regex."""
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "tests" / "foo_test.kt").write_text("// stub\n", encoding="utf-8")
    monkeypatch.setattr(
        v,
        "_git_staged_files",
        lambda root: [tmp_path / "tests/foo_test.kt"],
    )
    monkeypatch.setattr(
        v,
        "_load_workflow_config",
        lambda root: {
            "cc-gate": {"enabled": True, "kotlin": 10, "ignore-paths": ["tests/.*"]}
        },
    )
    monkeypatch.setattr(v, "_run_tools_for_staged", lambda **kw: ([], []))
    result = v.validate(fake_context)
    assert result["status"] == "pass"
    msg = (result.get("message") or "").lower()
    assert "ignorados" in msg or "no candidate" in msg or "candidate" in msg


def test_disabled_config_returns_warn_early(monkeypatch, fake_context):
    """cc-gate.enabled=false → result_warn early, sem invocar tools."""
    monkeypatch.setattr(
        v, "_load_workflow_config", lambda root: {"cc-gate": {"enabled": False}}
    )
    # Sentinel: se chegar a chamar _run_tools_for_staged, falha o teste.
    def _should_not_run(**kw):
        raise AssertionError("disabled config must short-circuit before dispatch")

    monkeypatch.setattr(v, "_run_tools_for_staged", _should_not_run)
    result = v.validate(fake_context)
    assert result["status"] == "warn"
    msg = (result.get("message") or "").lower()
    assert "disabled" in msg or "desligado" in msg


def test_tool_missing_emits_warn_not_fail(monkeypatch, fake_context):
    """Tool ausente (Detekt missing) → warn, não fail. Cascade alive."""

    def _runner(**kw):
        return [], ["detekt not installed (PATH lookup failed)"]

    monkeypatch.setattr(v, "_run_tools_for_staged", _runner)
    result = v.validate(fake_context)
    # Sem violations → pass com warning concatenado OU warn. Spec aceita ambos
    # desde que NÃO seja fail e a info de tool missing apareça.
    assert result["status"] in ("warn", "pass")
    if result["status"] == "warn":
        assert "detekt" in (result.get("message") or "").lower()


def test_no_staged_files_returns_pass(monkeypatch, fake_context):
    """git diff --cached vazio → pass com mensagem informativa, sem dispatch."""
    monkeypatch.setattr(v, "_git_staged_files", lambda root: [])

    def _should_not_run(**kw):
        raise AssertionError("no staged files must short-circuit before dispatch")

    monkeypatch.setattr(v, "_run_tools_for_staged", _should_not_run)
    result = v.validate(fake_context)
    assert result["status"] == "pass"
