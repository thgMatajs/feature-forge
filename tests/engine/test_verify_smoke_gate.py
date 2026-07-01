"""Tema 6 Nível 2 — smoke gate no forge verify (Caminho A: consumidor declara cmd)."""
from __future__ import annotations

from pathlib import Path

import pytest

from engine import verify
from tests.engine.helpers.external_exec import _write_fake_gradlew, _fake_run


def _cfg(**smoke):
    return {"native-gates": {"smoke": smoke, "ktlint": {"enabled": False}, "build": {"enabled": False}}}


def test_smoke_disabled_by_default(tmp_path, monkeypatch):
    """smoke sem enabled → gate não roda (opt-in default off)."""
    monkeypatch.setattr(verify, "run_external_tool", _fake_run("pass", exit_code=0))
    results = verify._run_native_gates(_cfg(cmd=["./gradlew", "test"]), tmp_path, interactive=False)
    assert [r for r in results if r.name == "smoke"] == []


def test_smoke_enabled_no_cmd_skipped(tmp_path):
    """enabled mas sem cmd declarado → skipped ensinando a declarar."""
    results = verify._run_native_gates(_cfg(enabled=True), tmp_path, interactive=False)
    smoke = [r for r in results if r.name == "smoke"]
    assert len(smoke) == 1 and smoke[0].status == "skipped"
    assert "native-gates.smoke.cmd" in smoke[0].message


def test_smoke_pass(tmp_path, monkeypatch):
    """cmd declarado + exit 0 → pass (substantive)."""
    _write_fake_gradlew(tmp_path, exit_code=0)
    monkeypatch.setattr(verify, "run_external_tool", _fake_run("pass", exit_code=0))
    results = verify._run_native_gates(_cfg(enabled=True, cmd=["./gradlew", "test"]), tmp_path, interactive=False)
    smoke = [r for r in results if r.name == "smoke"]
    assert len(smoke) == 1 and smoke[0].status == "pass" and smoke[0].coverage == "substantive"


def test_smoke_fail_is_warn(tmp_path, monkeypatch):
    """exit ≠ 0 sem fail-on-violation → warn (informativo)."""
    _write_fake_gradlew(tmp_path, exit_code=0)
    monkeypatch.setattr(verify, "run_external_tool", _fake_run("fail", exit_code=1))
    results = verify._run_native_gates(_cfg(enabled=True, cmd=["./gradlew", "test"]), tmp_path, interactive=False)
    smoke = [r for r in results if r.name == "smoke"]
    assert len(smoke) == 1 and smoke[0].status == "warn"


def test_smoke_fail_on_violation(tmp_path, monkeypatch):
    """exit ≠ 0 + fail-on-violation → fail."""
    _write_fake_gradlew(tmp_path, exit_code=0)
    monkeypatch.setattr(verify, "run_external_tool", _fake_run("fail", exit_code=1))
    cfg = _cfg(enabled=True, cmd=["./gradlew", "test"], **{"fail-on-violation": True})
    results = verify._run_native_gates(cfg, tmp_path, interactive=False)
    smoke = [r for r in results if r.name == "smoke"]
    assert len(smoke) == 1 and smoke[0].status == "fail"


def test_smoke_toolchain_absent_skipped(tmp_path):
    """cmd declara ./gradlew inexistente → resolve None → skipped."""
    results = verify._run_native_gates(_cfg(enabled=True, cmd=["./gradlew", "test"]), tmp_path, interactive=False)
    smoke = [r for r in results if r.name == "smoke"]
    assert len(smoke) == 1 and smoke[0].status == "skipped"


def test_smoke_timeout_degraded(tmp_path, monkeypatch):
    """timeout → degraded, nunca fail."""
    _write_fake_gradlew(tmp_path, exit_code=0)
    monkeypatch.setattr(verify, "run_external_tool", _fake_run("degraded", exit_code=None, skipped_reason="timeout"))
    results = verify._run_native_gates(_cfg(enabled=True, cmd=["./gradlew", "test"]), tmp_path, interactive=False)
    smoke = [r for r in results if r.name == "smoke"]
    assert len(smoke) == 1 and smoke[0].status == "degraded"


def test_smoke_real_degraded_on_oserror(tmp_path):
    """Path REAL (sem stub): ./gradlew não-executável → run_external_tool levanta
    OSError (PermissionError) → degraded, nunca fail. Exercita engine/external_exec.py
    (não o stub), cobrindo a razão-de-ser do gate: dependência externa quebrada degrada."""
    gradlew = tmp_path / "gradlew"
    gradlew.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")  # SEM chmod +x de propósito
    # NÃO monkeypatcha run_external_tool — o real roda e captura o OSError.
    results = verify._run_native_gates(
        _cfg(enabled=True, cmd=["./gradlew", "test"]), tmp_path, interactive=False
    )
    smoke = [r for r in results if r.name == "smoke"]
    assert len(smoke) == 1 and smoke[0].status == "degraded"


def test_smoke_greenfield_empty_config(tmp_path):
    """config vazio (mid-init) → _run_native_gates devolve [] (não roda smoke)."""
    assert verify._run_native_gates({}, tmp_path, interactive=False) == []


def test_smoke_cmd_as_string_shlex(tmp_path, monkeypatch):
    """cmd como string multi-palavra → shlex.split → resolve OK (não skip enganoso)."""
    _write_fake_gradlew(tmp_path, exit_code=0)
    monkeypatch.setattr(verify, "run_external_tool", _fake_run("pass", exit_code=0))
    results = verify._run_native_gates(_cfg(enabled=True, cmd="./gradlew test"), tmp_path, interactive=False)
    smoke = [r for r in results if r.name == "smoke"]
    assert len(smoke) == 1 and smoke[0].status == "pass"


def test_smoke_cmd_non_string_or_list_skipped(tmp_path):
    """cmd malformado (int/None) → tratado como ausente → skipped (não crash)."""
    results = verify._run_native_gates(_cfg(enabled=True, cmd=123), tmp_path, interactive=False)
    smoke = [r for r in results if r.name == "smoke"]
    assert len(smoke) == 1 and smoke[0].status == "skipped"
