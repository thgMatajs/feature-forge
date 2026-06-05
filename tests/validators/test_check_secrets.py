"""Entry-point tests for ``check_secrets.validate`` (R1.1 Task 4).

Cobre o orchestrator do gate de secrets — wiring final que costura tudo que
as Tasks 1-3 deixaram pronto:

- Workflow-config short-circuit (``secrets-gate.enabled=false`` → warn).
- ``git_staged_files`` → ``_filter_ignored`` → ``check_tool_available``.
- Dispatch via ``_dispatch_for_stage`` (per_task → gitleaks, cascade →
  trufflehog), parser correto por stage.
- ``apply_overrides`` com prefix ``SECRETS-OVERRIDE`` e cover-key
  ``(file, line, kind)`` — finding silenciado quando override bate triple
  exato; malformed (sem ``— <razão>``) propaga warning.
- ``result_fail`` carrega o campo ``render`` com o bloco 3-caminhos
  canônico (header ``🛑 Check Secrets gate`` + ``Três caminhos pra
  resolver:`` literal).
- Tool missing / dispatch crashed → ``result_warn`` (cascade alive per
  spec §3 trust-but-verify).

Estratégia de mock (mesmo padrão de ``test_check_cyclomatic_complexity.py``):

- ``git_staged_files`` / ``read_commit_body`` / ``check_tool_available`` /
  ``_dispatch_for_stage`` são monkeypatchados no módulo ``check_secrets``.
- Subprocess fica completamente isolado — nenhum teste invoca gitleaks /
  trufflehog real (smoke real fica pros integration tests da Task 6).

Spec: ``docs/superpowers/specs/2026-06-05-check-secrets-design.md §2``
(pipeline) + ``§3`` (render canônico) + ``§4`` (override mechanic).
Plan: ``docs/superpowers/plans/2026-06-05-check-secrets-implementation.md``
Task 4.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import _gate_infra
import check_secrets as v


# ── Helpers ──────────────────────────────────────────────────────────────────


def _mk_finding(**overrides) -> v.SecretFinding:
    """SecretFinding com defaults sensatos pra reduzir verbosidade dos testes."""
    defaults = dict(
        file="app/auth/AuthRepository.kt",
        line=42,
        kind="aws_access_key",
        snippet="AKIAIOSFODNN7EXAMPLE",
        verified=True,
    )
    defaults.update(overrides)
    return v.SecretFinding(**defaults)


def _ok_dispatch(raw_stdout: str = "") -> _gate_infra.DispatchResult:
    return _gate_infra.DispatchResult(
        language="any",
        tool_found=True,
        crashed=False,
        raw_stdout=raw_stdout,
        error_message="",
    )


@pytest.fixture
def fake_context(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Path:
    """Wire o validator pra um cenário "tem 1 staged file, tool presente, sem findings".

    Cada teste sobreescreve só o que importa pra ele.
    """
    (tmp_path / "app" / "auth").mkdir(parents=True, exist_ok=True)
    staged_file = tmp_path / "app" / "auth" / "AuthRepository.kt"
    staged_file.write_text("// stub\n", encoding="utf-8")

    monkeypatch.setattr(v, "git_staged_files", lambda root: [staged_file])
    monkeypatch.setattr(v, "check_tool_available", lambda tool: True)
    monkeypatch.setattr(v, "read_commit_body", lambda root: "")
    monkeypatch.setattr(v, "_load_workflow_config", lambda root: {})
    monkeypatch.setattr(
        v, "_dispatch_for_stage", lambda stage, files, *, project_root: _ok_dispatch("")
    )
    return tmp_path


# ── Short-circuits (config + staged + tool availability) ─────────────────────


def test_validate_secrets_gate_disabled_warns(monkeypatch, fake_context):
    """``secrets-gate.enabled=false`` → warn sem dispatch (cascade alive)."""
    monkeypatch.setattr(
        v,
        "_load_workflow_config",
        lambda root: {"secrets-gate": {"enabled": False}},
    )

    called = {"dispatch": False}

    def _no_dispatch(*args, **kwargs):
        called["dispatch"] = True
        return _ok_dispatch("")

    monkeypatch.setattr(v, "_dispatch_for_stage", _no_dispatch)

    result = v.validate(fake_context)
    assert result["status"] == "warn"
    assert "desligado" in result["message"] or "disabled" in result["message"].lower()
    assert called["dispatch"] is False


def test_validate_no_staged_files_passes(monkeypatch, fake_context):
    """Sem staged files → result_pass, dispatch nem é tocado."""
    monkeypatch.setattr(v, "git_staged_files", lambda root: [])
    result = v.validate(fake_context)
    assert result["status"] == "pass"


def test_validate_ignore_paths_filters_before_dispatch(monkeypatch, fake_context):
    """``ignore-paths`` (config + default) filtra staged ANTES do dispatch.

    Staged inclui ``tests/fixtures/secrets/x.kt``; pattern default cobre. Se o
    filtro funcionou, dispatch é invocado com lista enxuta — ou nem invocado
    se todos os files cairam.
    """
    fixture_path = fake_context / "tests" / "fixtures" / "secrets" / "x.kt"
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text("// fixture\n", encoding="utf-8")
    monkeypatch.setattr(v, "git_staged_files", lambda root: [fixture_path])

    called = {"dispatched": False}

    def _no_dispatch(*args, **kwargs):
        called["dispatched"] = True
        return _ok_dispatch("")

    monkeypatch.setattr(v, "_dispatch_for_stage", _no_dispatch)

    result = v.validate(fake_context)
    assert called["dispatched"] is False
    assert result["status"] == "pass"


def test_validate_tool_missing_warns(monkeypatch, fake_context):
    """``check_tool_available`` retorna False → warn com install hint."""
    monkeypatch.setattr(v, "check_tool_available", lambda tool: False)
    result = v.validate(fake_context, stage="per_task")
    assert result["status"] == "warn"
    assert "gitleaks" in result["message"]
    assert "install" in result["message"].lower() or "brew" in result["message"]


def test_validate_dispatch_crashed_warns(monkeypatch, fake_context):
    """``dispatch_res.crashed=True`` → warn cita stderr snippet (cascade alive)."""
    def _crashed(stage, files, *, project_root):
        return _gate_infra.DispatchResult(
            language="any",
            tool_found=True,
            crashed=True,
            raw_stdout="",
            error_message="permission denied",
        )

    monkeypatch.setattr(v, "_dispatch_for_stage", _crashed)
    result = v.validate(fake_context, stage="cascade")
    assert result["status"] == "warn"
    assert "permission denied" in result["message"]


# ── Findings + render canônico ───────────────────────────────────────────────


def test_validate_no_findings_passes(monkeypatch, fake_context):
    """Dispatch retorna stdout vazio (ou ``[]``) → pass."""
    monkeypatch.setattr(
        v, "_dispatch_for_stage", lambda *a, **kw: _ok_dispatch("[]")
    )
    result = v.validate(fake_context)
    assert result["status"] == "pass"


def test_validate_per_task_stage_uses_gitleaks_parser(monkeypatch, fake_context):
    """``stage="per_task"`` → parsea como gitleaks (JSON array).

    Output gitleaks tem chave ``RuleID`` e ``StartLine``; parser do trufflehog
    (NDJSON, chave ``DetectorName``) não conseguiria extrair nada disto. Se o
    finding chega no fail surviving com ``kind="aws_access_key"``, o parser
    correto foi escolhido.
    """
    gitleaks_raw = (
        '[{"RuleID":"aws_access_key","File":"app/auth/AuthRepository.kt",'
        '"StartLine":42,"Secret":"AKIAIOSFODNN7EXAMPLE"}]'
    )
    monkeypatch.setattr(
        v, "_dispatch_for_stage", lambda *a, **kw: _ok_dispatch(gitleaks_raw)
    )
    result = v.validate(fake_context, stage="per_task")
    assert result["status"] == "fail"
    # render gitleaks (per_task) usa "(unverified — gitleaks)" no Onde:
    render = result.get("render", "")
    assert "unverified" in render or "gitleaks" in render


def test_validate_cascade_stage_uses_trufflehog_parser(monkeypatch, fake_context):
    """``stage="cascade"`` → parsea como trufflehog (NDJSON)."""
    trufflehog_raw = (
        '{"DetectorName":"AWS","Verified":true,"Raw":"AKIAIOSFODNN7EXAMPLE",'
        '"SourceMetadata":{"Data":{"Filesystem":'
        '{"file":"app/auth/AuthRepository.kt","line":42}}}}'
    )
    monkeypatch.setattr(
        v, "_dispatch_for_stage", lambda *a, **kw: _ok_dispatch(trufflehog_raw)
    )
    result = v.validate(fake_context, stage="cascade")
    assert result["status"] == "fail"
    render = result.get("render", "")
    # render cascade usa "(verified)" + "trufflehog confirmou ATIVA"
    assert "verified" in render
    assert "trufflehog" in render or "ATIVA" in render


def test_validate_finding_without_override_fails(monkeypatch, fake_context):
    """Finding sobrevive (sem override) → result_fail completo.

    Confere shape canônico:
    - ``status="fail"``.
    - 3 paths exatos (Mandamento disciplina §1).
    - Campo ``render`` populated com header literal e bloco 3-caminhos.
    """
    raw = (
        '[{"RuleID":"aws_access_key","File":"app/auth/AuthRepository.kt",'
        '"StartLine":42,"Secret":"AKIAIOSFODNN7EXAMPLE"}]'
    )
    monkeypatch.setattr(
        v, "_dispatch_for_stage", lambda *a, **kw: _ok_dispatch(raw)
    )
    monkeypatch.setattr(v, "read_commit_body", lambda root: "")

    result = v.validate(fake_context, stage="per_task")
    assert result["status"] == "fail"
    assert len(result["paths"]) == 3
    render = result.get("render", "")
    assert "🛑 Check Secrets gate" in render
    assert "Três caminhos pra resolver:" in render
    assert "Sem auto-fix aqui — escolha humana." in render


def test_validate_finding_with_valid_override_passes(monkeypatch, fake_context):
    """Override válido cobrindo (file, line, kind) → fail vira pass silenciado."""
    raw = (
        '[{"RuleID":"aws_access_key","File":"app/auth/AuthRepository.kt",'
        '"StartLine":42,"Secret":"AKIAIOSFODNN7EXAMPLE"}]'
    )
    commit_body = (
        "feat: add fixture\n\n"
        "SECRETS-OVERRIDE: app/auth/AuthRepository.kt:42 kind=aws_access_key — test fixture deliberado\n"
    )
    monkeypatch.setattr(
        v, "_dispatch_for_stage", lambda *a, **kw: _ok_dispatch(raw)
    )
    monkeypatch.setattr(v, "read_commit_body", lambda root: commit_body)

    result = v.validate(fake_context, stage="per_task")
    assert result["status"] == "pass"
    assert "SECRETS-OVERRIDE" in result["message"] or "silenciado" in result["message"]


def test_validate_override_malformed_emits_warning(monkeypatch, fake_context):
    """``SECRETS-OVERRIDE: ... —`` (sem razão) NÃO silencia + emite warning."""
    raw = (
        '[{"RuleID":"aws_access_key","File":"app/auth/AuthRepository.kt",'
        '"StartLine":42,"Secret":"AKIAIOSFODNN7EXAMPLE"}]'
    )
    commit_body = (
        "feat: stuff\n\n"
        "SECRETS-OVERRIDE: app/auth/AuthRepository.kt:42 kind=aws_access_key — \n"
    )
    monkeypatch.setattr(
        v, "_dispatch_for_stage", lambda *a, **kw: _ok_dispatch(raw)
    )
    monkeypatch.setattr(v, "read_commit_body", lambda root: commit_body)

    result = v.validate(fake_context, stage="per_task")
    # Finding sobreviveu — fail, não silenced.
    assert result["status"] == "fail"
    # Warning malformed propagado.
    warnings = result.get("warnings") or []
    assert any("SECRETS-OVERRIDE" in w for w in warnings)


def test_validate_override_only_covers_matching_triple(monkeypatch, fake_context):
    """Override pra ``(file=A, line=42, kind=aws)`` NÃO silencia ``(file=B, line=42, kind=aws)``.

    Cover-key é triple exato — qualquer divergência mantém o finding ativo.
    """
    raw = (
        '[{"RuleID":"aws_access_key","File":"app/Bar.kt",'
        '"StartLine":42,"Secret":"AKIAIOSFODNN7EXAMPLE"}]'
    )
    commit_body = (
        "feat: x\n\n"
        "SECRETS-OVERRIDE: app/Foo.kt:42 kind=aws_access_key — razão concreta\n"
    )
    monkeypatch.setattr(
        v, "_dispatch_for_stage", lambda *a, **kw: _ok_dispatch(raw)
    )
    monkeypatch.setattr(v, "read_commit_body", lambda root: commit_body)

    result = v.validate(fake_context, stage="per_task")
    # finding em Bar.kt não foi coberto pelo override em Foo.kt
    assert result["status"] == "fail"


# ── Render snapshot (substring assertions) ────────────────────────────────────


def test_render_three_paths_snapshot_per_task() -> None:
    """Render per_task (gitleaks) inclui marcadores load-bearing.

    Não comparamos byte-a-byte — checamos substrings críticas pra detectar
    drift sem trancar copy edits cosméticos.
    """
    findings = [_mk_finding(verified=False, kind="aws_access_key", line=42)]
    rendered = v._render_secrets_three_paths(findings, stage="per_task")
    assert "🛑 Check Secrets gate" in rendered
    assert "O que falhou:" in rendered
    assert "Onde:" in rendered
    assert "Por que importa:" in rendered
    assert "Três caminhos pra resolver:" in rendered
    # per_task usa marcador unverified + gitleaks
    assert "(unverified — gitleaks)" in rendered
    # Razão correspondente do "por que importa" do stage per_task
    assert "gitleaks" in rendered
    # 3 caminhos numerados
    assert "1) Remover e rotacionar" in rendered
    assert "2) Override-justify" in rendered
    assert "3) Marcar como fixture" in rendered
    assert "SECRETS-OVERRIDE: <file>:<line> kind=<token-type> — <razão concreta>" in rendered
    assert "Sem auto-fix aqui — escolha humana." in rendered


def test_render_three_paths_snapshot_cascade() -> None:
    """Render cascade (trufflehog) cita verificação ativa."""
    findings = [_mk_finding(verified=True, kind="aws_access_key", line=42)]
    rendered = v._render_secrets_three_paths(findings, stage="cascade")
    assert "🛑 Check Secrets gate" in rendered
    assert "(verified)" in rendered
    assert "trufflehog confirmou ATIVA na origem (--only-verified)" in rendered
    # 3 caminhos preservados independentemente do stage
    assert "1) Remover e rotacionar" in rendered
    assert "2) Override-justify" in rendered
    assert "3) Marcar como fixture" in rendered


def test_render_three_paths_requires_at_least_one_finding() -> None:
    """Render sem findings é programming error — levanta ValueError.

    Caller (validate) só chega aqui quando `surviving` não-vazio; guard
    aqui evita criar render misleading com "0 secrets detectados".
    """
    with pytest.raises(ValueError):
        v._render_secrets_three_paths([], stage="per_task")
