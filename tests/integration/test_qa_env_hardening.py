"""Integration tests pra QA-11 env hardening (Wave 5 Task 5.1).

Cobertura E2E cross-componente:
- Env do pai (incl. secrets) nao vaza pro subprocess de validator.
- Card declara env-need legitima -> var chega ao subprocess.
- Alert dispara quando vars sensitive presentes sem grant/card.
- Alert silente quando env minimo.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from engine._sandbox.env import is_sensitive


pytestmark = pytest.mark.integration


def _write_minimal_fixture(fixtures_dir: Path, validator_script: Path) -> None:
    """Helper: escreve fixture + validator que dumpa env como JSON em stdout."""
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    (fixtures_dir / "input.txt").write_text("ignored", encoding="utf-8")
    validator_script.parent.mkdir(parents=True, exist_ok=True)
    validator_script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "json.dump(dict(os.environ), sys.stdout)\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    validator_script.chmod(0o755)


def test_secret_in_parent_env_does_not_leak_to_subprocess(tmp_path, monkeypatch):
    """AWS_TOKEN no env do pai NAO chega ao subprocess do sandbox."""
    monkeypatch.setenv("AWS_TOKEN", "leaky-AKIA-12345")

    from engine.qa.sandbox import Fixture, run_sandbox

    validator = tmp_path / "validator.py"
    _write_minimal_fixture(tmp_path / "fixtures", validator)

    fixtures = [Fixture(
        name="probe",
        input_path=tmp_path / "fixtures" / "input.txt",
        validator_path=validator,
    )]

    results = run_sandbox(tmp_path, fixtures, budget_total_s=10.0, per_validator_s=5.0)

    assert len(results) == 1
    assert results[0].status == "ok"
    subprocess_env = json.loads(results[0].stdout)
    assert "AWS_TOKEN" not in subprocess_env, (
        f"AWS_TOKEN vazou pro subprocess: {list(subprocess_env.keys())}"
    )


def test_card_env_needs_chain_grant_to_subprocess(tmp_path, monkeypatch):
    """Var declarada em extras (post-grant) chega ao subprocess."""
    monkeypatch.setenv("JAVA_HOME", "/opt/java-fixture")

    from engine.qa.sandbox import Fixture, run_sandbox

    validator = tmp_path / "validator.py"
    _write_minimal_fixture(tmp_path / "fixtures", validator)

    fixtures = [Fixture(
        name="probe",
        input_path=tmp_path / "fixtures" / "input.txt",
        validator_path=validator,
    )]

    results = run_sandbox(
        tmp_path,
        fixtures,
        budget_total_s=10.0,
        per_validator_s=5.0,
        extras=["JAVA_HOME"],
    )

    assert results[0].status == "ok"
    subprocess_env = json.loads(results[0].stdout)
    assert subprocess_env.get("JAVA_HOME") == "/opt/java-fixture"


def test_alert_fires_when_sensitive_unwhitelisted_present(monkeypatch, capsys):
    """Quando AWS_TOKEN no env e nenhum card declara -> alert mentor-calmo dispara."""
    monkeypatch.setenv("AWS_TOKEN", "secret123")

    from engine.qa import _alert_sensitive_drops

    _alert_sensitive_drops(card_extras=[])

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    # deep-005: nomes mascarados (AW********); a string completa NÃO deve
    # aparecer em log. Cheque pelo prefixo + presença de máscara, e/ou
    # pelo texto descritivo do alert.
    assert "sensitive" in combined.lower(), (
        f"Alert nao disparou. Output: {combined!r}"
    )
    assert "AWS_TOKEN" not in combined, (
        f"Nome completo de var sensitive vazou — esperava máscara. Output: {combined!r}"
    )
    assert "AW" in combined and "*" in combined, (
        f"Esperava nome mascarado 'AW********'. Output: {combined!r}"
    )


def test_alert_silent_when_no_sensitive_present(monkeypatch, capsys):
    """Quando nenhuma var sensitive no env (pos-cleanup) -> alert silencioso."""
    for k in list(os.environ):
        if is_sensitive(k):
            monkeypatch.delenv(k, raising=False)

    from engine.qa import _alert_sensitive_drops

    _alert_sensitive_drops(card_extras=[])

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "sensitive" not in combined.lower(), (
        f"Alert deveria estar silencioso. Output: {combined!r}"
    )
