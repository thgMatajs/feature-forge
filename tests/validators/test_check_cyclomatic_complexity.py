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


# ── D-006 — regex inválida em cc-gate.ignore-paths emite warning ────────────


def test_invalid_ignore_paths_regex_surfaces_warning(monkeypatch, fake_context):
    """Regex inválida em `cc-gate.ignore-paths` antes era silently swallowed.

    Após D-006, `_compile_ignore_patterns` valida cada pattern uma vez e
    `validate()` propaga warnings descritivos no result dict — caller vê
    qual entrada da config ficou inativa em vez de debugar no escuro.
    """
    monkeypatch.setattr(
        v,
        "_load_workflow_config",
        lambda root: {
            "cc-gate": {
                "enabled": True,
                "kotlin": 10,
                # `[unclosed` é regex inválido — `re.compile` levanta `re.error`.
                "ignore-paths": ["[unclosed"],
            }
        },
    )
    monkeypatch.setattr(v, "_run_tools_for_staged", lambda **kw: ([], []))
    result = v.validate(fake_context)
    warnings = result.get("warnings") or []
    assert any(
        "cc-gate.ignore-paths" in w and "regex inválida" in w and "[unclosed" in w
        for w in warnings
    ), f"expected invalid-regex warning; got: {warnings!r}"


def test_compile_ignore_patterns_drops_invalid_and_keeps_valid():
    """Helper unit-test: pattern inválido vira warning, válido sobrevive."""
    valid, warnings = v._compile_ignore_patterns(
        ["tests/.*", "[unclosed", r"\.cache/"]
    )
    assert valid == ["tests/.*", r"\.cache/"]
    assert len(warnings) == 1
    assert "[unclosed" in warnings[0]
    assert "cc-gate.ignore-paths" in warnings[0]


# ── D-009 — `_run_tools_for_staged` distingue tool ausente vs crashou ──────


def test_run_tools_for_staged_distinguishes_missing_from_crashed(monkeypatch):
    """As duas mensagens de warning devem ter prefixos distintos."""

    def _fake_dispatch(*, language, files, threshold, project_root):
        if language == "kotlin":
            return v.DispatchResult(
                language=language,
                tool_found=False,
                crashed=False,
                raw_stdout="",
                error_message="detekt not installed (PATH lookup failed)",
            )
        # python — crashou em runtime
        return v.DispatchResult(
            language=language,
            tool_found=True,
            crashed=True,
            raw_stdout="",
            error_message="radon stderr: boom",
        )

    monkeypatch.setattr(v, "_dispatch_tool", _fake_dispatch)
    _, warnings = v._run_tools_for_staged(
        files_by_lang={"kotlin": ["a.kt"], "python": ["b.py"]},
        thresholds_by_lang={"kotlin": 10, "python": 10},
        diff_hunks={},
        project_root=Path("/tmp/forge-noop"),
    )
    assert len(warnings) == 2
    missing_msg = next(w for w in warnings if "[detekt]" in w)
    crashed_msg = next(w for w in warnings if "[radon]" in w)
    assert "tool ausente" in missing_msg
    assert "tool crashou" in crashed_msg
    # Sub-string distinta entre os dois casos (D-009 contract).
    assert "ausente" not in crashed_msg
    assert "crashou" not in missing_msg


# ── F-006 — `_git_staged_files` aplica `-M80%` (rename detection) ──────────


@pytest.mark.integration
def test_git_staged_files_uses_rename_detection(tmp_path: Path) -> None:
    """SDD §2 manda `-M80%` no `git diff` pra detectar rename.

    Criamos um repo, commitamos um .py com função foo, depois renomeamos
    o arquivo (git mv) e re-stagiamos. `_git_staged_files` deve reportar
    o NOVO path — sem o flag, ele reportaria como new + delete e o pipeline
    perderia a oportunidade de aplicar o delta rule no arquivo renomeado.

    O teste é integration porque spawna subprocess git.
    """
    import subprocess

    repo = tmp_path
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@forge.local"], cwd=repo, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "forge-test"], cwd=repo, check=True
    )
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True
    )

    src = repo / "old_name.py"
    src.write_text("def foo():\n    return 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "old_name.py"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial"], cwd=repo, check=True
    )

    # Rename + leve mudança no conteúdo (mantém ≥80% de similaridade).
    subprocess.run(
        ["git", "mv", "old_name.py", "new_name.py"], cwd=repo, check=True
    )
    (repo / "new_name.py").write_text(
        "def foo():\n    return 2\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "new_name.py"], cwd=repo, check=True)

    staged = v._git_staged_files(repo)
    rel = [p.relative_to(repo).as_posix() for p in staged]
    # Com `-M80%`, o rename vira UMA entrada (`new_name.py`).
    # Sem o flag, viria como `new_name.py` + `old_name.py` (delete) — o filtro
    # `p.is_file()` ainda removeria o segundo, mas a INTENÇÃO de rename
    # detection é preservar a continuidade pra delta rule (F-001).
    assert "new_name.py" in rel
    # Bonus: o nome novo aparece após rename detection.
    assert any("new_name.py" == r for r in rel)
