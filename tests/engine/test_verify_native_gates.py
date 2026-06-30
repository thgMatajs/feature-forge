"""Track A1 — native gate ktlint no forge verify.

Fixtures: fake gradle wrapper (script trivial em tmp que sai com exit code
controlado) + monkeypatch de run_external_tool. NÃO depende de gradle/ktlint
reais. Cobre: pass / violação→warn / ausente→skipped / timeout→degraded / a
mescla no run_scope / o opt-in warn→fail.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from engine import verify
from engine.external_exec import ExternalToolResult


def _write_fake_gradlew(project_root: Path, *, exit_code: int) -> Path:
    """Cria um ./gradlew trivial que sai com `exit_code`.

    Serve só pra `resolve_invocation` enxergar o wrapper como arquivo presente;
    a execução real é interceptada por monkeypatch de run_external_tool nos
    testes que precisam de um resultado controlado.
    """
    gradlew = project_root / "gradlew"
    gradlew.write_text(f"#!/bin/sh\nexit {exit_code}\n", encoding="utf-8")
    mode = gradlew.stat().st_mode
    gradlew.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return gradlew


@pytest.fixture
def project_with_wrapper(tmp_path: Path) -> Path:
    """Project root com ./gradlew presente (exit 0 por default)."""
    _write_fake_gradlew(tmp_path, exit_code=0)
    return tmp_path


def _fake_run(status: str, *, exit_code: int | None, skipped_reason: str = "") -> object:
    """Factory de stub pra monkeypatch de run_external_tool."""

    def _runner(argv, project_root, *, timeout=120):
        return ExternalToolResult(
            tool=argv[0],
            status=status,
            exit_code=exit_code,
            stdout="",
            stderr="",
            duration_ms=12,
            skipped_reason=skipped_reason,
        )

    return _runner


def test_ktlint_pass_maps_to_pass(project_with_wrapper, monkeypatch):
    """exit 0 → _ValidatorResult.status == 'pass'."""
    monkeypatch.setattr(
        verify, "run_external_tool", _fake_run("pass", exit_code=0)
    )
    config = {"native-gates": {"ktlint": {"enabled": True}}}

    results = verify._run_native_gates(
        config, project_with_wrapper, interactive=False
    )

    ktlint = [r for r in results if r.name == "ktlint"]
    assert len(ktlint) == 1
    assert ktlint[0].status == "pass"
    assert ktlint[0].coverage == "substantive"


def test_ktlint_violation_maps_to_warn_by_default(project_with_wrapper, monkeypatch):
    """exit≠0 (tool rodou e acusou) → warn (informativo, não fail)."""
    monkeypatch.setattr(
        verify, "run_external_tool", _fake_run("fail", exit_code=1)
    )
    config = {"native-gates": {"ktlint": {"enabled": True}}}

    results = verify._run_native_gates(config, project_with_wrapper, interactive=False)

    ktlint = next(r for r in results if r.name == "ktlint")
    assert ktlint.status == "warn"
    assert "informativo" in ktlint.message.lower()


def test_ktlint_violation_opt_in_fail(project_with_wrapper, monkeypatch):
    """fail-on-violation: true sobe warn→fail (gate com dentes, opt-in)."""
    monkeypatch.setattr(
        verify, "run_external_tool", _fake_run("fail", exit_code=1)
    )
    config = {
        "native-gates": {"ktlint": {"enabled": True, "fail-on-violation": True}}
    }

    results = verify._run_native_gates(config, project_with_wrapper, interactive=False)

    ktlint = next(r for r in results if r.name == "ktlint")
    assert ktlint.status == "fail"


def test_ktlint_disabled_skips_entirely(project_with_wrapper, monkeypatch):
    """enabled: false → gate não roda (lista vazia pro ktlint)."""
    called = {"hit": False}

    def _boom(*a, **k):
        called["hit"] = True
        raise AssertionError("run_external_tool não devia ser chamado")

    monkeypatch.setattr(verify, "run_external_tool", _boom)
    config = {"native-gates": {"ktlint": {"enabled": False}}}

    results = verify._run_native_gates(config, project_with_wrapper, interactive=False)

    assert [r for r in results if r.name == "ktlint"] == []
    assert called["hit"] is False


def test_ktlint_absent_skips_with_mentor_message(tmp_path, monkeypatch):
    """Sem ./gradlew, sem bin, sem ktlint no PATH → skipped + como habilitar."""
    monkeypatch.setattr(verify, "resolve_invocation", lambda c, p: None)
    config = {"native-gates": {"ktlint": {"enabled": True}}}

    results = verify._run_native_gates(config, tmp_path, interactive=False)

    ktlint = next(r for r in results if r.name == "ktlint")
    assert ktlint.status == "skipped"
    assert "não foi reprovada" in ktlint.message
    assert "forge-config.yaml" in ktlint.message


def test_ktlint_timeout_maps_to_degraded(project_with_wrapper, monkeypatch):
    """Timeout (run_external_tool devolve degraded) → degraded com motivo."""
    monkeypatch.setattr(
        verify,
        "run_external_tool",
        _fake_run("degraded", exit_code=None, skipped_reason="timeout (>120s)"),
    )
    config = {"native-gates": {"ktlint": {"enabled": True}}}

    results = verify._run_native_gates(config, project_with_wrapper, interactive=False)

    ktlint = next(r for r in results if r.name == "ktlint")
    assert ktlint.status == "degraded"
    assert "timeout" in ktlint.message.lower()


def test_native_gate_merges_into_run_scope_json(project_with_wrapper, monkeypatch, capsys):
    """O gate ktlint flui pro payload --json e pro overall do run_scope.

    Cascade com 1 validator pass (pra não cair no early-return de validators
    vazios) + ktlint em warn → overall 'warn', exit 0, ktlint em validators[].
    """
    import json as _json

    from engine.ui import output_mode

    # 1 validator pass no cascade (evita o early-return de validators vazios).
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
    # ktlint presente, acusa violação → warn.
    monkeypatch.setattr(verify, "run_external_tool", _fake_run("fail", exit_code=1))
    monkeypatch.setattr(
        verify, "_write_verify_log_entry", lambda *a, **k: None
    )
    monkeypatch.setattr(verify, "_restore_l1_status", lambda *a, **k: None)
    monkeypatch.setattr(verify, "_clear_verify_checkpoint", lambda *a, **k: None)
    monkeypatch.setattr(verify, "_scope_to_feature_slug", lambda *a, **k: "")

    # forge-config com bloco native-gates → read_yaml_or_default devolve dict.
    (project_with_wrapper / ".claude" / "forge").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        verify,
        "read_yaml_or_default",
        lambda path, default: {"native-gates": {"ktlint": {"enabled": True}}},
    )

    monkeypatch.setattr(output_mode, "is_json_mode", lambda: True)
    exit_code = verify.run_scope("feature", "demo", project_with_wrapper, interactive=False)

    payload = _json.loads(capsys.readouterr().out)
    names = [v["name"] for v in payload["validators"]]
    assert "ktlint" in names
    assert payload["overall"] == "warn"   # warn não reprova
    assert exit_code == 0                  # warn → exit 0
