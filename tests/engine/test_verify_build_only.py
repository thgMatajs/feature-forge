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
    """android com gradlew presente + exit 0 → build gate pass (gate name: build:android)."""
    monkeypatch.setattr(verify, "run_external_tool", _fake_run("pass", exit_code=0))
    config = {
        "platforms": {"active": ["android"]},
        "native-gates": {"build": {"enabled": True}, "ktlint": {"enabled": False}},
    }

    results = verify._run_native_gates(config, android_project, interactive=False)

    # FIX #2: gate name é agora por-plataforma (build:android, build:ios, etc.)
    build = [r for r in results if r.name == "build:android"]
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
        if r.name == "build:android"
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
        if r.name == "build:android"
    )
    assert build.status == "fail"


def test_build_web_only_produces_no_build_gate(tmp_path, monkeypatch):
    """web não tem build-only no Nível 1 → nenhum _ValidatorResult com prefixo 'build:'."""
    monkeypatch.setattr(
        verify, "run_external_tool", _fake_run("pass", exit_code=0)
    )
    config = {
        "platforms": {"active": ["web"]},
        "native-gates": {"build": {"enabled": True}, "ktlint": {"enabled": False}},
    }
    results = verify._run_native_gates(config, tmp_path, interactive=False)
    assert [r for r in results if r.name.startswith("build")] == []


def test_build_toolchain_absent_skips(tmp_path, monkeypatch):
    """ios ativo mas sem xcodebuild → skipped (não fail). tmp_path sem gradlew."""
    monkeypatch.setattr(verify, "resolve_invocation", lambda c, p: None)
    config = {
        "platforms": {"active": ["ios"]},
        "native-gates": {"build": {"enabled": True}, "ktlint": {"enabled": False}},
    }
    build = next(
        r for r in verify._run_native_gates(config, tmp_path, interactive=False)
        if r.name == "build:ios"
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
        if r.name == "build:android"
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
    # FIX #2: gate name agora é por-plataforma (build:android para stack android)
    assert any(n.startswith("build:") for n in names), f"Esperado gate 'build:*', obtido: {names}"
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
        if r.name == "build:android"
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
        if r.name == "build:android"
    )
    assert build.status == "fail"
    # Mensagem NÃO deve dizer "não reprova" quando fail_on_violation=True
    assert "não reprova" not in build.message.lower()
    # Mensagem deve indicar que reprova
    assert "fail-on-violation" in build.message.lower() or "reprova" in build.message.lower()


# ── FIX #2 (TDD — RED first): multi-platform build deve rodar TODAS as plataformas ──

def test_build_all_active_platforms_run_not_just_first(tmp_path, monkeypatch):
    """FIX #2 (cross-AI review): com android+ios ambos buildáveis, AMBOS os gates devem rodar.

    Comportamento buggy atual: o loop faz `return` no primeiro que resolve
    (android com gradlew) → ios nunca roda → quebra de build de iOS invisível.
    Comportamento correto: iterar TODAS as plataformas buildable, acumulando um
    _ValidatorResult por plataforma com gate name distinto (build:android, build:ios).

    TDD: este teste falha com o código atual (só 1 resultado, nome 'build').
    """
    import stat as _stat

    # Gradlew presente → android resolve
    gradlew = tmp_path / "gradlew"
    gradlew.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    gradlew.chmod(gradlew.stat().st_mode | _stat.S_IXUSR | _stat.S_IXGRP | _stat.S_IXOTH)

    calls: list[str] = []

    def _fake_resolve(candidates, project_root):
        # resolve_invocation real: usa o candidates para decidir.
        # Simplificamos: se o primeiro candidato contém "gradlew", resolve.
        # Se contém "xcodebuild", também resolve (simulamos xcode presente via monkeypatch).
        first = candidates[0] if candidates else []
        if isinstance(first, list):
            tool = first[0]
        else:
            tool = first
        if "gradlew" in str(tool) or "xcodebuild" in str(tool):
            return first if isinstance(first, list) else [first]
        return None

    def _fake_run_tracking(argv, project_root, *, timeout=120):
        calls.append(str(argv[0]))
        return ExternalToolResult(
            tool=argv[0],
            status="pass",
            exit_code=0,
            stdout="",
            stderr="",
            duration_ms=10,
            skipped_reason="",
        )

    monkeypatch.setattr(verify, "resolve_invocation", _fake_resolve)
    monkeypatch.setattr(verify, "run_external_tool", _fake_run_tracking)

    config = {
        "platforms": {"active": ["android", "ios"]},
        "native-gates": {"build": {"enabled": True}, "ktlint": {"enabled": False}},
    }

    results = verify._run_native_gates(config, tmp_path, interactive=False)
    build_results = [r for r in results if r.name.startswith("build")]

    # FIX #2: ambas as plataformas devem produzir um resultado cada
    assert len(build_results) == 2, (
        f"Esperado 2 resultados de build (um por plataforma), obtido {len(build_results)}: "
        f"{[r.name for r in build_results]}"
    )
    names = {r.name for r in build_results}
    assert "build:android" in names, f"Esperado 'build:android', obtido: {names}"
    assert "build:ios" in names, f"Esperado 'build:ios', obtido: {names}"


def test_build_android_ios_one_absent_still_runs_other(tmp_path, monkeypatch):
    """FIX #2: se uma plataforma é buildável mas toolchain ausente, a outra ainda roda.

    android presente (gradlew), ios ausente (sem xcodebuild) →
    build:android pass, build:ios skipped (não fail, não omitido).
    """
    import stat as _stat

    gradlew = tmp_path / "gradlew"
    gradlew.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    gradlew.chmod(gradlew.stat().st_mode | _stat.S_IXUSR | _stat.S_IXGRP | _stat.S_IXOTH)

    def _partial_resolve(candidates, project_root):
        first = candidates[0] if candidates else []
        tool = first[0] if isinstance(first, list) else first
        if "gradlew" in str(tool):
            return first if isinstance(first, list) else [first]
        return None  # xcodebuild ausente

    monkeypatch.setattr(verify, "resolve_invocation", _partial_resolve)
    monkeypatch.setattr(verify, "run_external_tool", _fake_run("pass", exit_code=0))

    config = {
        "platforms": {"active": ["android", "ios"]},
        "native-gates": {"build": {"enabled": True}, "ktlint": {"enabled": False}},
    }

    results = verify._run_native_gates(config, tmp_path, interactive=False)
    build_results = [r for r in results if r.name.startswith("build")]

    assert len(build_results) == 2
    statuses = {r.name: r.status for r in build_results}
    assert statuses.get("build:android") == "pass"
    assert statuses.get("build:ios") == "skipped"
