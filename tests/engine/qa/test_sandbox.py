"""Tests for engine.qa.sandbox — Phase 3 subprocess hardening (Decisão 30).

Cobertura TDD-strict (6 obrigatorios + 2 defensive):

  1. test_happy_path_validator_runs_ok
  2. test_per_validator_timeout_fires
  3. test_budget_total_exhausted_skips_remaining
  4. test_sandbox_breach_on_absolute_input_path_outside
  5. test_chdir_guard_blocks_os_chdir
  6. test_empty_fixtures_returns_empty_list
  7. test_negative_budget_raises (defensive)
  8. test_run_dir_created_if_missing (defensive)

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
    # primeiro rodou (timeout ou ok), os demais skipped-budget
    skipped = [r for r in results if r.status == "skipped-budget"]
    assert len(skipped) >= 3, f"esperado >=3 skipped, obtidos: {[r.status for r in results]}"


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
