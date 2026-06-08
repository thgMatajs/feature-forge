"""Tests for engine.qa.sandbox — Phase 3 subprocess hardening (Decisão 30).

Cobertura TDD-strict (6 obrigatorios + 2 defensive + 4 hardening pós-review):

  1. test_happy_path_validator_runs_ok
  2. test_per_validator_timeout_fires
  3. test_budget_total_exhausted_skips_remaining
  4. test_sandbox_breach_on_absolute_input_path_outside
  5. test_chdir_guard_blocks_os_chdir
  6. test_empty_fixtures_returns_empty_list
  7. test_negative_budget_raises (defensive)
  8. test_run_dir_created_if_missing (defensive)
  9. test_status_skipped_budget_when_remaining_below_threshold (WR-01)
 10. test_chdir_guard_blocks_os_fchdir (WR-04)
 11. test_validator_path_missing_returns_error (IN-04)
 12. test_forge_qa_sandbox_marker_present_in_env (gap coverage)

Cada test constroi validator scripts sinteticos via tmp_path. Sem fixture
de produto — sandbox testa subprocess dispatch puro.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from engine.qa.sandbox import (
    Fixture,
    SandboxBreachError,
    SandboxResult,
    run_sandbox,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_validator(dir_: Path, name: str, body: str) -> Path:
    """Write a python validator script and return its path."""
    dir_.mkdir(parents=True, exist_ok=True)
    p = dir_ / name
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def _input_file(sandbox_fixtures: Path, name: str, content: str = "{}") -> Path:
    """Write an input file inside the sandbox fixtures dir."""
    sandbox_fixtures.mkdir(parents=True, exist_ok=True)
    p = sandbox_fixtures / name
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------


def test_happy_path_validator_runs_ok(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    validators_dir = tmp_path / "validators"
    sandbox_fixtures = run_dir / "fixtures"

    validator = _write_validator(
        validators_dir,
        "ok_validator.py",
        """
        import sys
        print("validator-ok")
        sys.exit(0)
        """,
    )
    inp = _input_file(sandbox_fixtures, "fx-1.json")

    fixtures = [Fixture(name="fx-1", input_path=inp, validator_path=validator)]
    results = run_sandbox(run_dir, fixtures, budget_total_s=5.0, per_validator_s=2.0)

    assert len(results) == 1
    r = results[0]
    assert isinstance(r, SandboxResult)
    assert r.status == "ok"
    assert r.exit_code == 0
    assert "validator-ok" in r.stdout
    assert r.duration_s > 0.0


# ---------------------------------------------------------------------------
# 2. Per-validator timeout
# ---------------------------------------------------------------------------


def test_per_validator_timeout_fires(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    validators_dir = tmp_path / "validators"
    sandbox_fixtures = run_dir / "fixtures"

    validator = _write_validator(
        validators_dir,
        "slow_validator.py",
        """
        import time
        time.sleep(30)
        """,
    )
    inp = _input_file(sandbox_fixtures, "fx-slow.json")

    fixtures = [Fixture(name="fx-slow", input_path=inp, validator_path=validator)]
    results = run_sandbox(
        run_dir, fixtures, budget_total_s=5.0, per_validator_s=0.3
    )

    assert len(results) == 1
    assert results[0].status == "timeout"


# ---------------------------------------------------------------------------
# 3. Budget total exhausted
# ---------------------------------------------------------------------------


def test_budget_total_exhausted_skips_remaining(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    validators_dir = tmp_path / "validators"
    sandbox_fixtures = run_dir / "fixtures"

    # validator que dorme para consumir budget rapidamente
    burner = _write_validator(
        validators_dir,
        "burner.py",
        """
        import time
        time.sleep(0.6)
        """,
    )

    fixtures = []
    for i in range(5):
        inp = _input_file(sandbox_fixtures, f"fx-{i}.json")
        fixtures.append(Fixture(name=f"fx-{i}", input_path=inp, validator_path=burner))

    # budget total 0.5s. Per-validator 5s permite o primeiro rodar (mas estoura
    # budget). Demais devem ser skipped.
    results = run_sandbox(
        run_dir, fixtures, budget_total_s=0.5, per_validator_s=5.0
    )

    assert len(results) == 5
    # Invariante anti-flaky (IN-03): pelo menos 4 dos 5 fixtures devem cair em
    # skipped-budget OU timeout — ou seja, no máximo 1 completa com "ok".
    # CI lento pode dilatar spawn overhead e alterar a partição entre
    # skipped-budget e timeout, mas a soma é estável.
    non_ok = [r for r in results if r.status in ("skipped-budget", "timeout")]
    assert len(non_ok) >= 4, (
        f"esperado >=4 skipped-budget+timeout, obtidos: {[r.status for r in results]}"
    )


# ---------------------------------------------------------------------------
# 4. Sandbox breach on absolute input path outside
# ---------------------------------------------------------------------------


def test_sandbox_breach_on_absolute_input_path_outside(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    validators_dir = tmp_path / "validators"
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir(parents=True, exist_ok=True)

    validator = _write_validator(
        validators_dir,
        "ok_validator.py",
        """
        import sys
        sys.exit(0)
        """,
    )
    # input absoluto FORA do sandbox_cwd (run_dir/fixtures)
    outside_input = outside_dir / "evil.json"
    outside_input.write_text("{}", encoding="utf-8")

    fixtures = [
        Fixture(name="fx-breach", input_path=outside_input, validator_path=validator)
    ]
    results = run_sandbox(run_dir, fixtures, budget_total_s=5.0, per_validator_s=2.0)

    assert len(results) == 1
    r = results[0]
    assert r.status == "sandbox-breach"
    assert "fora do sandbox" in r.error or "outside" in r.error.lower() or "sandbox" in r.error.lower()


# ---------------------------------------------------------------------------
# 5. chdir guard blocks os.chdir
# ---------------------------------------------------------------------------


def test_chdir_guard_blocks_os_chdir(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    validators_dir = tmp_path / "validators"
    sandbox_fixtures = run_dir / "fixtures"

    validator = _write_validator(
        validators_dir,
        "chdir_attempt.py",
        """
        import os, sys
        try:
            os.chdir("/tmp")
            print("CHDIR_NOT_BLOCKED", file=sys.stderr)
            sys.exit(0)
        except RuntimeError as e:
            print(f"BLOCKED: {e}", file=sys.stderr)
            sys.exit(2)
        """,
    )
    inp = _input_file(sandbox_fixtures, "fx-chdir.json")

    fixtures = [Fixture(name="fx-chdir", input_path=inp, validator_path=validator)]
    results = run_sandbox(run_dir, fixtures, budget_total_s=5.0, per_validator_s=2.0)

    assert len(results) == 1
    r = results[0]
    # WR-02: assert status == "ok" antes de exit_code != 0. Sem essa âncora,
    # timeout flaky (status="timeout", exit_code=None) passaria silenciosamente
    # porque None != 0. A intenção é checar comportamento determinístico do
    # guard, não fallback de timeout.
    assert r.status == "ok", (
        f"chdir guard test exige subprocess completar; status={r.status} "
        f"stderr={r.stderr!r}"
    )
    # validator saiu com codigo != 0 porque RuntimeError foi capturado
    assert r.exit_code != 0, (
        f"esperado exit_code != 0 (chdir blocked), obtido status={r.status} "
        f"code={r.exit_code} stderr={r.stderr!r}"
    )
    assert "bloqueado pelo sandbox" in r.stderr.lower() or "blocked" in r.stderr.lower()


# ---------------------------------------------------------------------------
# 6. Empty fixtures
# ---------------------------------------------------------------------------


def test_empty_fixtures_returns_empty_list(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    results = run_sandbox(run_dir, [], budget_total_s=5.0, per_validator_s=2.0)
    assert results == []


# ---------------------------------------------------------------------------
# 7. Defensive: negative budget raises
# ---------------------------------------------------------------------------


def test_negative_budget_raises(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    with pytest.raises(ValueError, match="budget_total_s"):
        run_sandbox(run_dir, [], budget_total_s=-1.0, per_validator_s=2.0)
    with pytest.raises(ValueError, match="per_validator_s"):
        run_sandbox(run_dir, [], budget_total_s=5.0, per_validator_s=0.0)


# ---------------------------------------------------------------------------
# 8. Defensive: run_dir created if missing
# ---------------------------------------------------------------------------


def test_run_dir_created_if_missing(tmp_path: Path) -> None:
    # run_dir nao existe ainda
    run_dir = tmp_path / "nested" / "does" / "not" / "exist" / "run"
    assert not run_dir.exists()

    results = run_sandbox(run_dir, [], budget_total_s=5.0, per_validator_s=2.0)

    assert results == []
    # diretorio fixtures foi criado
    assert (run_dir / "fixtures").is_dir()


# ---------------------------------------------------------------------------
# 9. WR-01 — status semantics na fronteira budget/timeout
# ---------------------------------------------------------------------------


def test_status_skipped_budget_when_remaining_below_threshold(tmp_path: Path) -> None:
    """Quando remaining < 0.05s, deve ser skipped-budget — NÃO timeout.

    WR-01: ``subprocess.run(timeout=0.001)`` dispararia TimeoutExpired
    imediatamente e marcaria como ``timeout``. O caller pretende
    ``skipped-budget`` porque < 50ms é spawn overhead, não tempo útil de
    validator. Diferença importa pra Phase 4 synthesis (timeout = validator
    lento; skipped-budget = orchestrator decidiu pular).
    """
    run_dir = tmp_path / "run"
    validators_dir = tmp_path / "validators"
    sandbox_fixtures = run_dir / "fixtures"

    # burner que consome budget rapidamente
    burner = _write_validator(
        validators_dir,
        "burner.py",
        """
        import time
        time.sleep(0.3)
        """,
    )

    # 2 fixtures. budget_total=0.31s permite o primeiro rodar e estoura;
    # quando o segundo entra, remaining = 0.31 - ~0.30 < 0.05 → skipped-budget.
    fixtures = []
    for i in range(2):
        inp = _input_file(sandbox_fixtures, f"fx-{i}.json")
        fixtures.append(Fixture(name=f"fx-{i}", input_path=inp, validator_path=burner))

    results = run_sandbox(
        run_dir, fixtures, budget_total_s=0.31, per_validator_s=5.0
    )

    assert len(results) == 2
    # status do segundo: pode ser skipped-budget (se elapsed >= budget OU
    # remaining < threshold) — NUNCA timeout com remaining sub-threshold.
    second = results[1]
    assert second.status == "skipped-budget", (
        f"esperado skipped-budget no fixture sub-threshold, obtido {second.status}"
    )


# ---------------------------------------------------------------------------
# 10. WR-04 — chdir guard cobre os.fchdir
# ---------------------------------------------------------------------------


def test_chdir_guard_blocks_os_fchdir(tmp_path: Path) -> None:
    """``os.fchdir(fd)`` deve ser bloqueado pelo guard (defense-in-depth).

    Decisão 30 diz "CWD imutável" — qualquer canal de mudança de CWD viola
    a invariante. ``os.fchdir`` é o bypass conhecido se só ``os.chdir``
    estiver patchado.
    """
    run_dir = tmp_path / "run"
    validators_dir = tmp_path / "validators"
    sandbox_fixtures = run_dir / "fixtures"

    validator = _write_validator(
        validators_dir,
        "fchdir_attempt.py",
        """
        import os, sys
        try:
            fd = os.open("/", os.O_RDONLY)
            os.fchdir(fd)
            print("FCHDIR_NOT_BLOCKED", file=sys.stderr)
            sys.exit(0)
        except RuntimeError as e:
            print(f"BLOCKED: {e}", file=sys.stderr)
            sys.exit(2)
        finally:
            try:
                os.close(fd)
            except Exception:
                pass
        """,
    )
    inp = _input_file(sandbox_fixtures, "fx-fchdir.json")

    fixtures = [Fixture(name="fx-fchdir", input_path=inp, validator_path=validator)]
    results = run_sandbox(run_dir, fixtures, budget_total_s=5.0, per_validator_s=2.0)

    assert len(results) == 1
    r = results[0]
    assert r.status == "ok", (
        f"fchdir guard test exige subprocess completar; status={r.status} "
        f"stderr={r.stderr!r}"
    )
    assert r.exit_code != 0, (
        f"esperado exit_code != 0 (fchdir blocked), obtido status={r.status} "
        f"code={r.exit_code} stderr={r.stderr!r}"
    )
    assert "bloqueado pelo sandbox" in r.stderr.lower() or "blocked" in r.stderr.lower()


# ---------------------------------------------------------------------------
# 11. IN-04 — validator_path missing returns error with named message
# ---------------------------------------------------------------------------


def test_validator_path_missing_returns_error(tmp_path: Path) -> None:
    """Validator path inexistente deve virar status=error com mensagem nomeada.

    IN-04: sem early check, vira ``OSError: [Errno 2]`` no catch genérico,
    sem dica de qual campo foi o problema. Mensagem deve nomear
    ``validator_path`` + o path concreto pra debug.
    """
    run_dir = tmp_path / "run"
    sandbox_fixtures = run_dir / "fixtures"

    # input existe; validator NÃO existe
    inp = _input_file(sandbox_fixtures, "fx-missing.json")
    missing_validator = tmp_path / "validators" / "does_not_exist.py"

    fixtures = [
        Fixture(name="fx-missing", input_path=inp, validator_path=missing_validator)
    ]
    results = run_sandbox(run_dir, fixtures, budget_total_s=5.0, per_validator_s=2.0)

    assert len(results) == 1
    r = results[0]
    assert r.status == "error"
    assert "validator_path" in r.error, (
        f"mensagem deve nomear o campo 'validator_path', obtido: {r.error!r}"
    )
    assert str(missing_validator) in r.error or "does_not_exist" in r.error


# ---------------------------------------------------------------------------
# 12. Gap coverage — FORGE_QA_SANDBOX marker presente no env do subprocess
# ---------------------------------------------------------------------------


def test_forge_qa_sandbox_marker_present_in_env(tmp_path: Path) -> None:
    """Validators rodando no sandbox devem ver ``FORGE_QA_SANDBOX=1`` no env.

    Spec §5.3: marker permite que validators detectem que estão sob sandbox
    e adaptem comportamento (ex.: pular operações que requerem rede). Sem
    test, regressão silenciosa do ``_hardened_env`` ficaria invisível.
    """
    run_dir = tmp_path / "run"
    validators_dir = tmp_path / "validators"
    sandbox_fixtures = run_dir / "fixtures"

    validator = _write_validator(
        validators_dir,
        "marker_probe.py",
        """
        import os, sys
        marker = os.environ.get("FORGE_QA_SANDBOX", "MISSING")
        print(f"MARKER={marker}")
        sys.exit(0)
        """,
    )
    inp = _input_file(sandbox_fixtures, "fx-marker.json")

    fixtures = [Fixture(name="fx-marker", input_path=inp, validator_path=validator)]
    results = run_sandbox(run_dir, fixtures, budget_total_s=5.0, per_validator_s=2.0)

    assert len(results) == 1
    r = results[0]
    assert r.status == "ok"
    assert "MARKER=1" in r.stdout, (
        f"esperado MARKER=1 no stdout, obtido: {r.stdout!r}"
    )


from engine.qa.sandbox import _hardened_env


def test_hardened_env_delegates_to_build_safe_env(tmp_path, monkeypatch):
    """_hardened_env constrói env a partir de build_safe_env (não dict(os.environ))."""
    # Set var sensitive no pai — não deve aparecer no env retornado
    monkeypatch.setenv("AWS_SECRET", "leak")
    guard_dir = tmp_path / "guard"
    guard_dir.mkdir()

    env = _hardened_env(guard_dir)

    assert "AWS_SECRET" not in env, "env do sandbox não pode incluir var sensitive do pai"


def test_hardened_env_preserves_pythonpath_guard_prepend(tmp_path, monkeypatch):
    """guard_dir é prepended ao PYTHONPATH existente."""
    monkeypatch.setenv("PYTHONPATH", "/existing/path")
    # PYTHONPATH não está em CORE_ALLOWLIST — mas _hardened_env sobrescreve
    # com guard_dir + existing (lendo de env já reduzido). Como build_safe_env
    # não inclui PYTHONPATH, a "existing" será vista via os.environ direto pela
    # impl de _hardened_env. Garantimos que o resultado tem guard_dir primeiro.
    guard_dir = tmp_path / "guard"
    guard_dir.mkdir()

    env = _hardened_env(guard_dir)

    assert env["PYTHONPATH"].startswith(str(guard_dir))


def test_hardened_env_preserves_forge_qa_sandbox_marker(tmp_path):
    """FORGE_QA_SANDBOX=1 marker é setado."""
    guard_dir = tmp_path / "guard"
    guard_dir.mkdir()

    env = _hardened_env(guard_dir)

    assert env["FORGE_QA_SANDBOX"] == "1"


def test_hardened_env_propagates_extras_to_build_safe_env(tmp_path, monkeypatch):
    """extras passados pra _hardened_env chegam em build_safe_env."""
    monkeypatch.setenv("JAVA_HOME", "/opt/java")
    guard_dir = tmp_path / "guard"
    guard_dir.mkdir()

    env = _hardened_env(guard_dir, extras=["JAVA_HOME"])

    assert env["JAVA_HOME"] == "/opt/java"
