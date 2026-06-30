"""Track A2 — build-only no forge verify (reusa o step de A1).

Mesmas fixtures-padrão do A1 (fake gradlew + monkeypatch de run_external_tool).
Cobre por plataforma: android pass / build-falha→warn / opt-in fail / ausente→
skipped / timeout→degraded / web→sem build / mescla no run_scope / guard greenfield.
"""
from __future__ import annotations

import stat
from pathlib import Path

import pytest

from engine import verify
from engine.external_exec import ExternalToolResult


def _write_fake_gradlew(project_root: Path, *, exit_code: int = 0) -> Path:
    gradlew = project_root / "gradlew"
    gradlew.write_text(f"#!/bin/sh\nexit {exit_code}\n", encoding="utf-8")
    mode = gradlew.stat().st_mode
    gradlew.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return gradlew


def _fake_run(status: str, *, exit_code: int | None, skipped_reason: str = ""):
    def _runner(argv, project_root, *, timeout=120):
        return ExternalToolResult(
            tool=argv[0],
            status=status,
            exit_code=exit_code,
            stdout="",
            stderr="",
            duration_ms=20,
            skipped_reason=skipped_reason,
        )

    return _runner


@pytest.fixture
def android_project(tmp_path: Path) -> Path:
    _write_fake_gradlew(tmp_path, exit_code=0)
    return tmp_path


# ── A2 Step 1 (RED): android build pass ──────────────────────────────────────

def test_build_android_pass(android_project, monkeypatch):
    """android com gradlew presente + exit 0 → build gate pass."""
    monkeypatch.setattr(verify, "run_external_tool", _fake_run("pass", exit_code=0))
    config = {
        "platforms": {"active": ["android"]},
        "native-gates": {"build": {"enabled": True}, "ktlint": {"enabled": False}},
    }

    results = verify._run_native_gates(config, android_project, interactive=False)

    build = [r for r in results if r.name == "build"]
    assert len(build) == 1
    assert build[0].status == "pass"


# ── A2 Step 3: build-falha→warn + opt-in fail + ios + web-skip + ausente→skipped + timeout→degraded

def test_build_failure_maps_to_warn(android_project, monkeypatch):
    monkeypatch.setattr(verify, "run_external_tool", _fake_run("fail", exit_code=1))
    config = {
        "platforms": {"active": ["android"]},
        "native-gates": {"build": {"enabled": True}, "ktlint": {"enabled": False}},
    }
    build = next(
        r for r in verify._run_native_gates(config, android_project, interactive=False)
        if r.name == "build"
    )
    assert build.status == "warn"


def test_build_failure_opt_in_fail(android_project, monkeypatch):
    monkeypatch.setattr(verify, "run_external_tool", _fake_run("fail", exit_code=1))
    config = {
        "platforms": {"active": ["android"]},
        "native-gates": {
            "build": {"enabled": True, "fail-on-violation": True},
            "ktlint": {"enabled": False},
        },
    }
    build = next(
        r for r in verify._run_native_gates(config, android_project, interactive=False)
        if r.name == "build"
    )
    assert build.status == "fail"


def test_build_web_only_produces_no_build_gate(tmp_path, monkeypatch):
    """web não tem build-only no Nível 1 → nenhum _ValidatorResult 'build'."""
    monkeypatch.setattr(
        verify, "run_external_tool", _fake_run("pass", exit_code=0)
    )
    config = {
        "platforms": {"active": ["web"]},
        "native-gates": {"build": {"enabled": True}, "ktlint": {"enabled": False}},
    }
    results = verify._run_native_gates(config, tmp_path, interactive=False)
    assert [r for r in results if r.name == "build"] == []


def test_build_toolchain_absent_skips(tmp_path, monkeypatch):
    """ios ativo mas sem xcodebuild → skipped (não fail). tmp_path sem gradlew."""
    monkeypatch.setattr(verify, "resolve_invocation", lambda c, p: None)
    config = {
        "platforms": {"active": ["ios"]},
        "native-gates": {"build": {"enabled": True}, "ktlint": {"enabled": False}},
    }
    build = next(
        r for r in verify._run_native_gates(config, tmp_path, interactive=False)
        if r.name == "build"
    )
    assert build.status == "skipped"
    assert "não foi reprovada" in build.message


def test_build_timeout_maps_to_degraded(android_project, monkeypatch):
    monkeypatch.setattr(
        verify,
        "run_external_tool",
        _fake_run("degraded", exit_code=None, skipped_reason="timeout (>600s)"),
    )
    config = {
        "platforms": {"active": ["android"]},
        "native-gates": {"build": {"enabled": True}, "ktlint": {"enabled": False}},
    }
    build = next(
        r for r in verify._run_native_gates(config, android_project, interactive=False)
        if r.name == "build"
    )
    assert build.status == "degraded"
    assert "timeout" in build.message.lower()


# ── A2 Step 4: guard greenfield + mescla no run_scope com ktlint+build juntos ─


def test_greenfield_empty_config_runs_no_gates(tmp_path):
    """Config vazio (mid-init) → nenhum gate roda (silent skip)."""
    assert verify._run_native_gates({}, tmp_path, interactive=False) == []


def test_ktlint_and_build_both_merge_into_run_scope(android_project, monkeypatch, capsys):
    """ktlint + build juntos fluem pro payload --json do run_scope."""
    import json as _json
    from engine.ui import output_mode

    monkeypatch.setattr(
        verify,
        "_discover_validators",
        lambda root, cfg, scope: [
            verify._ValidatorSpec(name="dummy", script_path=Path("/x"))
        ],
    )
    monkeypatch.setattr(
        verify,
        "_run_cascade",
        lambda validators, **k: [
            verify._ValidatorResult(name="dummy", status="pass", coverage="substantive")
        ],
    )
    monkeypatch.setattr(verify, "run_external_tool", _fake_run("pass", exit_code=0))
    monkeypatch.setattr(verify, "_write_verify_log_entry", lambda *a, **k: None)
    monkeypatch.setattr(verify, "_restore_l1_status", lambda *a, **k: None)
    monkeypatch.setattr(verify, "_clear_verify_checkpoint", lambda *a, **k: None)
    monkeypatch.setattr(verify, "_scope_to_feature_slug", lambda *a, **k: "")
    monkeypatch.setattr(
        verify,
        "read_yaml_or_default",
        lambda path, default: {
            "platforms": {"active": ["android"]},
            "native-gates": {"ktlint": {"enabled": True}, "build": {"enabled": True}},
        },
    )
    monkeypatch.setattr(output_mode, "is_json_mode", lambda: True)

    exit_code = verify.run_scope("feature", "demo", android_project, interactive=False)

    payload = _json.loads(capsys.readouterr().out)
    names = [v["name"] for v in payload["validators"]]
    assert "ktlint" in names
    assert "build" in names
    assert payload["overall"] == "pass"
    assert exit_code == 0


# ── FR-02: ktlint stack guard — só roda em projetos Kotlin ───────────────────

def test_ktlint_skips_on_non_kotlin_stack(tmp_path, monkeypatch):
    """ktlint não roda quando platforms.active não tem android/kmp.

    FR-02: guard de stack evita 'verde inerte' em projetos não-Kotlin.
    Se active está definido mas sem android/kmp, ktlint é skipped — não chama
    run_external_tool mesmo com ktlint no PATH. Build gate também desabilitado
    para isolar o comportamento do ktlint.
    """
    boom_called = {"hit": False}

    def _boom(*a, **k):
        boom_called["hit"] = True
        raise AssertionError("run_external_tool não devia ser chamado")

    monkeypatch.setattr(verify, "run_external_tool", _boom)
    config = {
        "platforms": {"active": ["web"]},
        # build disabled para isolar: web não tem build-only → _run_build_gates retorna []
        # sem chamar run_external_tool. ktlint enabled mas stack não-Kotlin.
        "native-gates": {"ktlint": {"enabled": True}, "build": {"enabled": False}},
    }

    results = verify._run_native_gates(config, tmp_path, interactive=False)

    # ktlint não deve estar em results nem como warn — must be absent or skipped
    ktlint_results = [r for r in results if r.name == "ktlint"]
    assert not any(r.status in ("pass", "warn", "fail") for r in ktlint_results), (
        "ktlint não deve rodar em stack sem android/kmp"
    )
    assert boom_called["hit"] is False


def test_ktlint_runs_when_active_is_empty(tmp_path, monkeypatch):
    """Quando platforms.active está vazio (projeto não-inicializado), ktlint roda.

    FR-02: ativo-vazio = projeto não registrou plataformas ainda. Não sabemos que
    NÃO é Kotlin, então ktlint tenta resolver (pode ser skipped por ausência do tool).
    """
    monkeypatch.setattr(verify, "resolve_invocation", lambda c, p: None)
    config = {
        "platforms": {"active": []},
        "native-gates": {"ktlint": {"enabled": True}},
    }

    results = verify._run_native_gates(config, tmp_path, interactive=False)

    # ktlint deve ter tentado e ficado skipped (sem gradlew nem ktlint no PATH)
    ktlint_results = [r for r in results if r.name == "ktlint"]
    assert len(ktlint_results) == 1
    assert ktlint_results[0].status == "skipped"


def test_ktlint_runs_when_platforms_key_absent(tmp_path, monkeypatch):
    """Sem bloco platforms no config, ktlint tenta rodar (assume stack desconhecida).

    FR-02: config sem platforms.active = não sabemos a stack → ktlint tenta.
    """
    monkeypatch.setattr(verify, "resolve_invocation", lambda c, p: None)
    config = {
        "native-gates": {"ktlint": {"enabled": True}},
    }

    results = verify._run_native_gates(config, tmp_path, interactive=False)

    ktlint_results = [r for r in results if r.name == "ktlint"]
    assert len(ktlint_results) == 1
    assert ktlint_results[0].status == "skipped"


# ── FR-01: _map_external_result mensagem condicional a fail_on_violation ──────

def test_map_external_result_message_when_fail_on_violation_false(android_project, monkeypatch):
    """fail_on_violation=False → mensagem diz 'informativo; não reprova por default'."""
    monkeypatch.setattr(verify, "run_external_tool", _fake_run("fail", exit_code=1))
    config = {
        "platforms": {"active": ["android"]},
        "native-gates": {"build": {"enabled": True, "fail-on-violation": False}, "ktlint": {"enabled": False}},
    }
    build = next(
        r for r in verify._run_native_gates(config, android_project, interactive=False)
        if r.name == "build"
    )
    assert build.status == "warn"
    assert "informativo" in build.message.lower()
    assert "não reprova" in build.message.lower()


def test_map_external_result_message_when_fail_on_violation_true(android_project, monkeypatch):
    """FR-01: fail_on_violation=True → mensagem deve refletir que REPROVA.

    Antes o texto dizia 'informativo; não reprova por default' mesmo com
    fail-on-violation: true — contradição: o glyph era 🛑 e REPROVAVA.
    """
    monkeypatch.setattr(verify, "run_external_tool", _fake_run("fail", exit_code=1))
    config = {
        "platforms": {"active": ["android"]},
        "native-gates": {
            "build": {"enabled": True, "fail-on-violation": True},
            "ktlint": {"enabled": False},
        },
    }
    build = next(
        r for r in verify._run_native_gates(config, android_project, interactive=False)
        if r.name == "build"
    )
    assert build.status == "fail"
    # Mensagem NÃO deve dizer "não reprova" quando fail_on_violation=True
    assert "não reprova" not in build.message.lower()
    # Mensagem deve indicar que reprova
    assert "fail-on-violation" in build.message.lower() or "reprova" in build.message.lower()
