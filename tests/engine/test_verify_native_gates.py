"""Track A1 — native gate ktlint no forge verify.

Fixtures: fake gradle wrapper (script trivial em tmp que sai com exit code
controlado) + monkeypatch de run_external_tool. NÃO depende de gradle/ktlint
reais. Cobre: pass / violação→warn / ausente→skipped / timeout→degraded / a
mescla no run_scope / o opt-in warn→fail.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from engine import verify
from engine.external_exec import ExternalToolResult
from tests.engine.helpers.external_exec import _write_fake_gradlew, _fake_run


@pytest.fixture
def project_with_wrapper(tmp_path: Path) -> Path:
    """Project root com ./gradlew presente (exit 0 por default)."""
    _write_fake_gradlew(tmp_path, exit_code=0)
    return tmp_path


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


def test_run_scope_validators_empty_native_gates_still_run(tmp_path, monkeypatch, capsys):
    """FIX #1 (cross-AI review): run_scope com validators=[] deve rodar gates nativos.

    O comportamento CORRETO: gates nativos são independentes do cascade de validators.
    Mesmo quando validators==[], _run_native_gates deve ser chamado. O early-return
    "pass" só vale se validators E native-gate-results forem ambos vazios.

    Antes (comportamento buggy, documentado como FR-04): o early-return (validators
    vazio) disparava ANTES dos gates nativos — run_external_tool nunca era chamado.
    Este teste INVERTE o comportamento: com validators=[] mas gate nativo configurado
    e resolvível, o gate RODA e aparece no resultado.

    TDD: falha com o código antigo (early-return antes dos gates), passa após o fix.
    """
    import json as _json
    from engine.ui import output_mode
    import stat as _stat

    # Gradlew presente → ktlint e build resolvem (monkeypatch do run_external_tool).
    gradlew = tmp_path / "gradlew"
    gradlew.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    gradlew.chmod(gradlew.stat().st_mode | _stat.S_IXUSR | _stat.S_IXGRP | _stat.S_IXOTH)

    gate_called = {"hit": False}

    def _fake_run(argv, project_root, *, timeout=120):
        gate_called["hit"] = True
        return ExternalToolResult(
            tool=argv[0],
            status="pass",
            exit_code=0,
            stdout="",
            stderr="",
            duration_ms=10,
            skipped_reason="",
        )

    monkeypatch.setattr(verify, "run_external_tool", _fake_run)
    monkeypatch.setattr(verify, "_discover_validators", lambda *a, **k: [])
    monkeypatch.setattr(verify, "_write_verify_log_entry", lambda *a, **k: None)
    monkeypatch.setattr(verify, "_restore_l1_status", lambda *a, **k: None)
    monkeypatch.setattr(verify, "_clear_verify_checkpoint", lambda *a, **k: None)
    monkeypatch.setattr(verify, "_scope_to_feature_slug", lambda *a, **k: "")
    monkeypatch.setattr(
        verify,
        "read_yaml_or_default",
        lambda path, default: {
            "platforms": {"active": ["android"]},
            "native-gates": {"ktlint": {"enabled": True}, "build": {"enabled": False}},
        },
    )
    monkeypatch.setattr(output_mode, "is_json_mode", lambda: True)

    exit_code = verify.run_scope("feature", "demo", tmp_path, interactive=False)

    payload = _json.loads(capsys.readouterr().out)
    # Gate nativo ktlint rodou → aparece no payload
    assert gate_called["hit"] is True, (
        "run_external_tool devia ter sido chamado: gates nativos são independentes dos validators"
    )
    names = [v["name"] for v in payload["validators"]]
    assert "ktlint" in names, f"ktlint devia estar no payload validators, obtido: {names}"
    assert exit_code == 0


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


# ── FIX #3: verify-log validators-run inclui native gates ────────────────────

def test_verify_log_validators_run_includes_native_gate(project_with_wrapper, monkeypatch):
    """FIX #3 (cross-AI review): o verify-log deve listar native gates em validators-run.

    Comportamento buggy: `_write_verify_log_entry` gravava `[v.name for v in validators]`
    (só o cascade), omitindo native gates mesmo quando eles contribuíram pro overall.
    Resultado: entrada auto-inconsistente — `result: "warn"` com `hard-fails: ["ktlint"]`
    mas `validators-run: []` (sem mencionar ktlint).

    Fix: `[r.name for r in results]` — inclui todos os gates que rodaram.
    """
    import json as _json
    from engine.utils.paths import lifecycle_root

    log_calls: list[dict] = []

    def _capture_log(*args, **kwargs):
        """Captura os kwargs de _write_verify_log_entry sem escrever no disco."""
        log_calls.append(kwargs)

    monkeypatch.setattr(verify, "_write_verify_log_entry", _capture_log)
    monkeypatch.setattr(verify, "_restore_l1_status", lambda *a, **k: None)
    monkeypatch.setattr(verify, "_clear_verify_checkpoint", lambda *a, **k: None)
    monkeypatch.setattr(verify, "_scope_to_feature_slug", lambda *a, **k: "")

    # 1 validator no cascade (evita early-return) + ktlint nativo em warn.
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
    monkeypatch.setattr(verify, "run_external_tool", _fake_run("fail", exit_code=1))
    monkeypatch.setattr(
        verify,
        "read_yaml_or_default",
        lambda path, default: {"native-gates": {"ktlint": {"enabled": True}}},
    )

    verify.run_scope("feature", "demo", project_with_wrapper, interactive=False)

    assert len(log_calls) == 1, f"Esperado 1 chamada ao log, obtido {len(log_calls)}"
    validators_run = log_calls[0].get("validators", [])

    # FIX #3: ktlint (native gate) deve aparecer em validators-run
    assert "ktlint" in validators_run, (
        f"'ktlint' devia estar em validators-run (FIX #3). Obtido: {validators_run}"
    )
    # O validator do cascade também deve aparecer
    assert "dummy" in validators_run, (
        f"'dummy' (cascade) devia estar em validators-run. Obtido: {validators_run}"
    )
