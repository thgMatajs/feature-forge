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

import os
import textwrap
from pathlib import Path

import pytest

from engine.qa.sandbox import (
    Fixture,
    SandboxBreachError,
    SandboxResult,
    _hardened_env,
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


def test_hardened_env_delegates_to_build_safe_env(tmp_path, monkeypatch):
    """_hardened_env constrói env a partir de build_safe_env (não dict(os.environ))."""
    # Set var sensitive no pai — não deve aparecer no env retornado
    monkeypatch.setenv("AWS_SECRET", "leak")
    guard_dir = tmp_path / "guard"
    guard_dir.mkdir()

    env = _hardened_env(guard_dir)

    assert "AWS_SECRET" not in env, "env do sandbox não pode incluir var sensitive do pai"


def test_hardened_env_drops_parent_pythonpath(tmp_path, monkeypatch):
    """deep-001: PYTHONPATH do parent é DROPADO — não herda.

    Regressão crítica: a versão anterior concatenava
    ``os.environ['PYTHONPATH']`` ao guard_dir, permitindo que um parent
    process hostil (ou shell poluído) injetasse paths de import arbitrários
    no subprocess do sandbox. PYTHONPATH é vetor de code-execution — todo
    módulo sob ele pode ser importado pelo validator. Defense-in-depth
    exige drop incondicional; callers que precisem de paths extras devem
    declarar via ``extras`` (que passa pelo grant flow).
    """
    monkeypatch.setenv("PYTHONPATH", "/evil/path:/another/evil")
    guard_dir = tmp_path / "guard"
    guard_dir.mkdir()

    env = _hardened_env(guard_dir)

    # Só o guard_dir, sem traço do PYTHONPATH herdado
    assert env["PYTHONPATH"] == str(guard_dir)
    assert "/evil/path" not in env["PYTHONPATH"]
    assert "/another/evil" not in env["PYTHONPATH"]


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


# ---------------------------------------------------------------------------
# F-1 (A.1) — mini-tree + invocação --project-root
# ---------------------------------------------------------------------------


# Validator stub que espelha validators forge reais: lê --project-root via
# argparse, tolera --scope/--id (parse-only), escaneia o tree e dá exit 1 se
# achar um arquivo offending. Contrato canônico:
#   python3 validator.py --project-root <path> [--scope <kind> --id <target>]
_PROJECT_ROOT_VALIDATOR = """
import argparse
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--project-root", required=True)
parser.add_argument("--scope")
parser.add_argument("--id")
args = parser.parse_args()

root = Path(args.project_root)
# Imprime o project-root recebido pra o teste poder asserir a invocação.
print(f"PROJECT_ROOT={root}")

offending = list(root.rglob("offending.kt"))
if offending:
    for f in offending:
        print(f"OFFENDING: {f}", file=sys.stderr)
    sys.exit(1)
sys.exit(0)
"""


# Validator stub posicional legado: lê argv[1] como input path (caminho
# antigo, pré-F-1). Usado pra confirmar que tree_rel_path=None preserva a
# invocação posicional.
_POSITIONAL_VALIDATOR = """
import sys
# argv[1] é o input posicional. Se chegou --project-root como argv[1], o
# validator legado não saberia o que fazer — então imprimimos o argv cru
# pra o teste asserir a forma da invocação.
print(f"ARGV1={sys.argv[1] if len(sys.argv) > 1 else 'NONE'}")
sys.exit(0)
"""


def test_run_sandbox_project_root_invocation(tmp_path: Path) -> None:
    """Fixture com tree_rel_path → validator invocado com --project-root.

    O validator argparse escaneia o mini-tree e acha o arquivo offending,
    devolvendo exit 1 (validator "deveria falhar" — vetor validator-claim
    funcional). Sem F-1 a invocação seria posicional e o argparse sairia 2
    sem nunca ler o arquivo.
    """
    run_dir = tmp_path / "run"
    validators_dir = tmp_path / "validators"
    sandbox_fixtures = run_dir / "fixtures"

    validator = _write_validator(
        validators_dir, "project_root_validator.py", _PROJECT_ROOT_VALIDATOR
    )

    # mini-tree DENTRO de run_dir/fixtures/<name>/, com o arquivo offending
    # no rel-path declarado.
    mini_tree = sandbox_fixtures / "vc-foo"
    offending = mini_tree / "src" / "offending.kt"
    offending.parent.mkdir(parents=True, exist_ok=True)
    offending.write_text("// offending content\n", encoding="utf-8")

    fixture = Fixture(
        name="vc-foo",
        input_path=offending,
        validator_path=validator,
        tree_rel_path="src/offending.kt",
    )
    results = run_sandbox(
        run_dir, [fixture], budget_total_s=30.0, per_validator_s=10.0
    )

    assert len(results) == 1
    r = results[0]
    assert r.status == "ok", f"status={r.status} error={r.error!r} stderr={r.stderr!r}"
    assert r.exit_code == 1, (
        f"validator deveria achar offending.kt via --project-root e sair 1; "
        f"exit={r.exit_code} stdout={r.stdout!r} stderr={r.stderr!r}"
    )
    # O project-root recebido aponta pro mini-tree dentro do sandbox.
    assert str(mini_tree.resolve()) in r.stdout


def test_run_sandbox_project_root_clean_tree_passes(tmp_path: Path) -> None:
    """Mini-tree sem arquivo offending → validator passa (exit 0)."""
    run_dir = tmp_path / "run"
    validators_dir = tmp_path / "validators"
    sandbox_fixtures = run_dir / "fixtures"

    validator = _write_validator(
        validators_dir, "project_root_validator.py", _PROJECT_ROOT_VALIDATOR
    )

    mini_tree = sandbox_fixtures / "vc-clean"
    clean_file = mini_tree / "src" / "Clean.kt"
    clean_file.parent.mkdir(parents=True, exist_ok=True)
    clean_file.write_text("// clean\n", encoding="utf-8")

    fixture = Fixture(
        name="vc-clean",
        input_path=clean_file,
        validator_path=validator,
        tree_rel_path="src/Clean.kt",
    )
    results = run_sandbox(
        run_dir, [fixture], budget_total_s=30.0, per_validator_s=10.0
    )

    assert len(results) == 1
    r = results[0]
    assert r.status == "ok"
    assert r.exit_code == 0


def test_run_sandbox_legacy_positional_invocation(tmp_path: Path) -> None:
    """tree_rel_path=None preserva a invocação posicional legada (compat)."""
    run_dir = tmp_path / "run"
    validators_dir = tmp_path / "validators"
    sandbox_fixtures = run_dir / "fixtures"

    validator = _write_validator(
        validators_dir, "positional_validator.py", _POSITIONAL_VALIDATOR
    )
    inp = _input_file(sandbox_fixtures, "fx-legacy.json")

    fixture = Fixture(name="fx-legacy", input_path=inp, validator_path=validator)
    results = run_sandbox(
        run_dir, [fixture], budget_total_s=5.0, per_validator_s=2.0
    )

    assert len(results) == 1
    r = results[0]
    assert r.status == "ok"
    assert r.exit_code == 0
    # O input chegou como argv posicional (não --project-root).
    assert f"ARGV1={inp.resolve()}" in r.stdout
    assert "--project-root" not in r.stdout


# ---------------------------------------------------------------------------
# F-1 (A.4) — hardening preservado sob mini-tree (Decisão 30/31)
#
# Gate de segurança explícito: A.1 ADICIONA cobertura ao containment, nunca
# afrouxa. Estes testes confirmam que traversal via tree_rel_path vira
# sandbox-breach, que o chdir guard segue intacto sob a invocação --project-root,
# e que o mini-tree não vaza paths absolutos fora do sandbox.
# ---------------------------------------------------------------------------


def test_tree_rel_path_traversal_is_breach(tmp_path: Path) -> None:
    """tree_rel_path='../../escape.kt' → sandbox-breach, sem subprocess.

    O containment estendido pega o arquivo materializado resolvendo fora do
    mini-tree (e do sandbox). Decisão 30: traversal é breach, não exit do
    validator. O subprocess nem dispara.
    """
    run_dir = tmp_path / "run"
    validators_dir = tmp_path / "validators"
    sandbox_fixtures = run_dir / "fixtures"

    validator = _write_validator(
        validators_dir, "project_root_validator.py", _PROJECT_ROOT_VALIDATOR
    )
    # input_path dentro do sandbox (pra isolar que o breach vem do
    # tree_rel_path, não do input).
    inp = _input_file(sandbox_fixtures, "fx-evil.json")

    fixture = Fixture(
        name="evil",
        input_path=inp,
        validator_path=validator,
        tree_rel_path="../../escape.kt",
    )
    results = run_sandbox(
        run_dir, [fixture], budget_total_s=5.0, per_validator_s=2.0
    )

    assert len(results) == 1
    r = results[0]
    assert r.status == "sandbox-breach", (
        f"esperado sandbox-breach pra tree_rel_path com traversal, obtido "
        f"{r.status} (stdout={r.stdout!r})"
    )
    # Subprocess não disparou: sem stdout/exit_code do validator.
    assert r.exit_code is None
    assert r.stdout == ""
    # A mensagem nomeia o vetor (tree_rel_path) ou o sandbox.
    assert (
        "tree_rel_path" in r.error
        or "mini-tree" in r.error
        or "sandbox" in r.error.lower()
    )


def test_tree_rel_path_input_outside_sandbox_is_breach(tmp_path: Path) -> None:
    """tree_rel_path setado mas input_path FORA do sandbox → sandbox-breach.

    Mesmo com tree_rel_path "inocente", o input_path continua sob o
    containment check estendido (o guard não regrediu pro caminho legado).
    """
    run_dir = tmp_path / "run"
    validators_dir = tmp_path / "validators"
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir(parents=True, exist_ok=True)

    validator = _write_validator(
        validators_dir, "project_root_validator.py", _PROJECT_ROOT_VALIDATOR
    )
    outside_input = outside_dir / "offending.kt"
    outside_input.write_text("// outside\n", encoding="utf-8")

    fixture = Fixture(
        name="vc-outside",
        input_path=outside_input,
        validator_path=validator,
        tree_rel_path="src/offending.kt",
    )
    results = run_sandbox(
        run_dir, [fixture], budget_total_s=5.0, per_validator_s=2.0
    )

    assert len(results) == 1
    r = results[0]
    assert r.status == "sandbox-breach"


def test_chdir_guard_intact_under_project_root(tmp_path: Path) -> None:
    """chdir guard segue bloqueando sob a invocação --project-root (F-1).

    A.1 não tocou env/guard, mas confirmamos explicitamente que um validator
    --project-root que tenta os.chdir é bloqueado pelo sitecustomize preload.
    """
    run_dir = tmp_path / "run"
    validators_dir = tmp_path / "validators"
    sandbox_fixtures = run_dir / "fixtures"

    # Validator --project-root que tenta escapar via os.chdir antes de
    # escanear. O guard deve levantar RuntimeError → exit != 0.
    chdir_pr_validator = _write_validator(
        validators_dir,
        "project_root_chdir.py",
        """
        import argparse
        import os
        import sys

        parser = argparse.ArgumentParser()
        parser.add_argument("--project-root", required=True)
        parser.add_argument("--scope")
        parser.add_argument("--id")
        args = parser.parse_args()

        try:
            os.chdir("/")
            print("CHDIR_NOT_BLOCKED", file=sys.stderr)
            sys.exit(0)
        except RuntimeError as e:
            print(f"BLOCKED: {e}", file=sys.stderr)
            sys.exit(2)
        """,
    )

    mini_tree = sandbox_fixtures / "vc-chdir"
    target = mini_tree / "src" / "Foo.kt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("// foo\n", encoding="utf-8")

    fixture = Fixture(
        name="vc-chdir",
        input_path=target,
        validator_path=chdir_pr_validator,
        tree_rel_path="src/Foo.kt",
    )
    results = run_sandbox(
        run_dir, [fixture], budget_total_s=5.0, per_validator_s=2.0
    )

    assert len(results) == 1
    r = results[0]
    assert r.status == "ok", (
        f"chdir guard test exige subprocess completar; status={r.status} "
        f"stderr={r.stderr!r}"
    )
    assert r.exit_code != 0, (
        f"esperado exit_code != 0 (chdir blocked sob --project-root), obtido "
        f"status={r.status} code={r.exit_code} stderr={r.stderr!r}"
    )
    assert (
        "bloqueado pelo sandbox" in r.stderr.lower() or "blocked" in r.stderr.lower()
    )


def test_project_root_stays_inside_sandbox(tmp_path: Path) -> None:
    """O --project-root passado ao validator mora DENTRO do sandbox.

    Garante que o mini-tree nunca aponta pro projeto real (vazamento de path
    absoluto fora do sandbox). O validator imprime o project-root recebido;
    asseguramos que ele é prefixado por run_dir/fixtures.
    """
    run_dir = tmp_path / "run"
    validators_dir = tmp_path / "validators"
    sandbox_fixtures = run_dir / "fixtures"

    validator = _write_validator(
        validators_dir, "project_root_validator.py", _PROJECT_ROOT_VALIDATOR
    )
    mini_tree = sandbox_fixtures / "vc-scope"
    f = mini_tree / "src" / "Clean.kt"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("// clean\n", encoding="utf-8")

    fixture = Fixture(
        name="vc-scope",
        input_path=f,
        validator_path=validator,
        tree_rel_path="src/Clean.kt",
    )
    results = run_sandbox(
        run_dir, [fixture], budget_total_s=5.0, per_validator_s=2.0
    )

    r = results[0]
    assert r.status == "ok"
    # O project-root recebido está sob run_dir/fixtures (não fora do sandbox).
    received = r.stdout.split("PROJECT_ROOT=", 1)[1].splitlines()[0].strip()
    Path(received).resolve().relative_to(sandbox_fixtures.resolve())


# ---------------------------------------------------------------------------
# R8 (Item 4) — extra_args threada --scope/--id; engine controla --project-root
#
# Validators feature/task-scoped (ex.: validate_task_contract.py) exigem
# --scope feature --id <slug>. A Fixture ganha extra_args (lista) que o
# run_sandbox concatena APÓS o --project-root <mini-tree> que o engine
# controla. HARDENING (Decisão 30): extra_args NÃO pode redefinir
# --project-root — o engine sempre aponta pro mini-tree.
# ---------------------------------------------------------------------------


# Stub que ecoa o argv inteiro pra o teste asserir a forma exata da invocação
# E lê --project-root via argparse pra confirmar o root efetivo. parse-only
# pra --scope/--id (espelha validators feature-scoped reais).
_ARGV_ECHO_VALIDATOR = """
import argparse
import sys
from pathlib import Path

print("ARGV=" + repr(sys.argv[1:]))

parser = argparse.ArgumentParser()
parser.add_argument("--project-root", required=True)
parser.add_argument("--scope")
parser.add_argument("--id")
# argparse com --project-root duplicado fica com o ÚLTIMO; por isso o
# teste de segurança confia no neutralize do run_sandbox, não no argparse.
args, _unknown = parser.parse_known_args()
print(f"EFFECTIVE_ROOT={Path(args.project_root)}")
print(f"SCOPE={args.scope}")
print(f"ID={args.id}")
sys.exit(0)
"""


def test_extra_args_appended_after_project_root(tmp_path: Path) -> None:
    """Fixture.extra_args=['--scope','feature','--id','foo'] → invocação
    recebe --project-root <tree> --scope feature --id foo (nessa ordem)."""
    run_dir = tmp_path / "run"
    validators_dir = tmp_path / "validators"
    sandbox_fixtures = run_dir / "fixtures"

    validator = _write_validator(
        validators_dir, "argv_echo.py", _ARGV_ECHO_VALIDATOR
    )
    mini_tree = sandbox_fixtures / "vc-args"
    f = mini_tree / "src" / "Clean.kt"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("// clean\n", encoding="utf-8")

    fixture = Fixture(
        name="vc-args",
        input_path=f,
        validator_path=validator,
        tree_rel_path="src/Clean.kt",
        extra_args=["--scope", "feature", "--id", "foo"],
    )
    results = run_sandbox(
        run_dir, [fixture], budget_total_s=5.0, per_validator_s=2.0
    )

    r = results[0]
    assert r.status == "ok", f"status={r.status} stderr={r.stderr!r}"
    argv = r.stdout.split("ARGV=", 1)[1].splitlines()[0]
    # --project-root <tree> vem primeiro (engine controla), depois extra_args.
    assert "'--project-root'" in argv
    assert "'--scope', 'feature', '--id', 'foo'" in argv
    # O --project-root antecede o --scope na invocação.
    assert argv.index("'--project-root'") < argv.index("'--scope'")
    assert "SCOPE=feature" in r.stdout
    assert "ID=foo" in r.stdout
    # O root efetivo continua o mini-tree.
    assert str(mini_tree.resolve()) in r.stdout


def test_extra_args_cannot_override_project_root(tmp_path: Path) -> None:
    """SEGURANÇA: extra_args tentando re-setar --project-root é neutralizado.

    Uma fixture (gerada por LLM) que injeta --project-root /etc NÃO pode
    mudar o root efetivo — o engine controla o --project-root <mini-tree>.
    """
    run_dir = tmp_path / "run"
    validators_dir = tmp_path / "validators"
    sandbox_fixtures = run_dir / "fixtures"

    validator = _write_validator(
        validators_dir, "argv_echo.py", _ARGV_ECHO_VALIDATOR
    )
    mini_tree = sandbox_fixtures / "vc-breach"
    f = mini_tree / "src" / "Clean.kt"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("// clean\n", encoding="utf-8")

    fixture = Fixture(
        name="vc-breach",
        input_path=f,
        validator_path=validator,
        tree_rel_path="src/Clean.kt",
        # Hostil: tenta apontar o root pra fora do sandbox.
        extra_args=["--project-root", "/etc", "--scope", "feature"],
    )
    results = run_sandbox(
        run_dir, [fixture], budget_total_s=5.0, per_validator_s=2.0
    )

    r = results[0]
    assert r.status == "ok", f"status={r.status} stderr={r.stderr!r}"
    # /etc NUNCA chega como argv — o engine remove o --project-root injetado.
    argv = r.stdout.split("ARGV=", 1)[1].splitlines()[0]
    assert "/etc" not in argv, (
        f"extra_args conseguiu injetar --project-root /etc: argv={argv!r}"
    )
    # Há exatamente UM --project-root, e ele aponta pro mini-tree do engine.
    assert argv.count("'--project-root'") == 1
    assert str(mini_tree.resolve()) in r.stdout
    # O --scope legítimo (não-perigoso) sobrevive ao scrub.
    assert "SCOPE=feature" in r.stdout


def test_extra_args_none_preserves_legacy_command(tmp_path: Path) -> None:
    """extra_args=None (default) → invocação inalterada (compat R7)."""
    run_dir = tmp_path / "run"
    validators_dir = tmp_path / "validators"
    sandbox_fixtures = run_dir / "fixtures"

    validator = _write_validator(
        validators_dir, "argv_echo.py", _ARGV_ECHO_VALIDATOR
    )
    mini_tree = sandbox_fixtures / "vc-none"
    f = mini_tree / "src" / "Clean.kt"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("// clean\n", encoding="utf-8")

    fixture = Fixture(
        name="vc-none",
        input_path=f,
        validator_path=validator,
        tree_rel_path="src/Clean.kt",
    )
    results = run_sandbox(
        run_dir, [fixture], budget_total_s=5.0, per_validator_s=2.0
    )

    r = results[0]
    assert r.status == "ok"
    argv = r.stdout.split("ARGV=", 1)[1].splitlines()[0]
    # Apenas --project-root <tree>, sem extras.
    assert "'--project-root'" in argv
    assert "'--scope'" not in argv


# ---------------------------------------------------------------------------
# C1/C2 (review pr27) — sandbox escape via argparse abbreviation (Decisão 30)
#
# Validators forge usam argparse; com allow_abbrev=True (default histórico),
# --p / --proj / --project / --project-roo (e formas =valor) TODOS setam
# project_root e, como ÚLTIMA ocorrência após o --project-root <sandbox> que o
# engine controla, OVERRIDE o root (last-wins). Uma fixture LLM com
# invocation_args ['--p','/etc'] rodaria o validator REAL contra /etc → escape
# total. O scrub vira ALLOWLIST (passa só --scope/--id + valores, dropa o resto)
# e o argparser compartilhado ganha allow_abbrev=False (defense-in-depth).
#
# Asserção FORTE (C2): o root EFETIVO visto pelo validator == mini-tree, não
# mera ausência de substring "/etc" no argv.
# ---------------------------------------------------------------------------


# Matriz de spellings abreviados de --project-root, cada um em forma de espaço
# (2 tokens) E forma "=" (1 token). allow_abbrev=True honraria todos.
_ABBREV_SPELLINGS = ["--p", "--proj", "--project", "--project-roo"]


def _abbrev_cases() -> list[list[str]]:
    cases: list[list[str]] = []
    for flag in _ABBREV_SPELLINGS:
        cases.append([flag, "/etc"])  # forma espaço (2 tokens)
        cases.append([f"{flag}=/etc"])  # forma "=" (1 token)
    return cases


@pytest.mark.parametrize("hostile_args", _abbrev_cases())
def test_extra_args_abbreviation_cannot_override_project_root(
    tmp_path: Path, hostile_args: list[str]
) -> None:
    """SEGURANÇA C1/C2: abreviação de --project-root via extra_args é dropada.

    O scrub é allowlist: só --scope/--id + valores passam. Qualquer prefixo
    --p…/--project… (espaço OU "=") é dropado. O root efetivo continua o
    mini-tree dentro do sandbox — nunca /etc.
    """
    run_dir = tmp_path / "run"
    validators_dir = tmp_path / "validators"
    sandbox_fixtures = run_dir / "fixtures"

    validator = _write_validator(
        validators_dir, "argv_echo.py", _ARGV_ECHO_VALIDATOR
    )
    mini_tree = sandbox_fixtures / "vc-abbrev"
    f = mini_tree / "src" / "Clean.kt"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("// clean\n", encoding="utf-8")

    fixture = Fixture(
        name="vc-abbrev",
        input_path=f,
        validator_path=validator,
        tree_rel_path="src/Clean.kt",
        extra_args=hostile_args,
    )
    results = run_sandbox(
        run_dir, [fixture], budget_total_s=5.0, per_validator_s=2.0
    )

    r = results[0]
    assert r.status == "ok", f"status={r.status} stderr={r.stderr!r}"
    # Asserção FORTE: o ROOT EFETIVO visto pelo validator é o mini-tree.
    assert f"EFFECTIVE_ROOT={mini_tree.resolve()}" in r.stdout, (
        f"abreviação {hostile_args!r} conseguiu override; stdout={r.stdout!r}"
    )
    # Defense-in-depth: /etc nunca chega como argv.
    argv = r.stdout.split("ARGV=", 1)[1].splitlines()[0]
    assert "/etc" not in argv, (
        f"abreviação {hostile_args!r} vazou pro argv: {argv!r}"
    )


def test_extra_args_last_wins_override_neutralized(tmp_path: Path) -> None:
    """SEGURANÇA C1: last-wins clássico (--project-root literal repetido)
    é neutralizado — o root efetivo continua o mini-tree."""
    run_dir = tmp_path / "run"
    validators_dir = tmp_path / "validators"
    sandbox_fixtures = run_dir / "fixtures"

    validator = _write_validator(
        validators_dir, "argv_echo.py", _ARGV_ECHO_VALIDATOR
    )
    mini_tree = sandbox_fixtures / "vc-lastwins"
    f = mini_tree / "src" / "Clean.kt"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("// clean\n", encoding="utf-8")

    fixture = Fixture(
        name="vc-lastwins",
        input_path=f,
        validator_path=validator,
        tree_rel_path="src/Clean.kt",
        # Last-wins: o argparse default ficaria com o ÚLTIMO --project-root.
        extra_args=["--scope", "feature", "--project-root=/etc"],
    )
    results = run_sandbox(
        run_dir, [fixture], budget_total_s=5.0, per_validator_s=2.0
    )

    r = results[0]
    assert r.status == "ok", f"status={r.status} stderr={r.stderr!r}"
    assert f"EFFECTIVE_ROOT={mini_tree.resolve()}" in r.stdout, (
        f"last-wins conseguiu override; stdout={r.stdout!r}"
    )
    # O --scope legítimo sobrevive ao allowlist.
    assert "SCOPE=feature" in r.stdout


def test_extra_args_allowlist_drops_unknown_flags(tmp_path: Path) -> None:
    """C1: o scrub é allowlist — flags fora de {--scope,--id} são dropadas
    junto com seus valores; --scope/--id legítimos sobrevivem."""
    run_dir = tmp_path / "run"
    validators_dir = tmp_path / "validators"
    sandbox_fixtures = run_dir / "fixtures"

    validator = _write_validator(
        validators_dir, "argv_echo.py", _ARGV_ECHO_VALIDATOR
    )
    mini_tree = sandbox_fixtures / "vc-allowlist"
    f = mini_tree / "src" / "Clean.kt"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("// clean\n", encoding="utf-8")

    fixture = Fixture(
        name="vc-allowlist",
        input_path=f,
        validator_path=validator,
        tree_rel_path="src/Clean.kt",
        # Mistura: --scope/--id legítimos + flag desconhecida + bare value órfão.
        extra_args=[
            "--scope",
            "feature",
            "--evil-flag",
            "payload",
            "--id=foo",
            "orphan-bare-value",
        ],
    )
    results = run_sandbox(
        run_dir, [fixture], budget_total_s=5.0, per_validator_s=2.0
    )

    r = results[0]
    assert r.status == "ok", f"status={r.status} stderr={r.stderr!r}"
    argv = r.stdout.split("ARGV=", 1)[1].splitlines()[0]
    assert "'--evil-flag'" not in argv, f"flag desconhecida vazou: {argv!r}"
    assert "'payload'" not in argv, f"valor de flag dropada vazou: {argv!r}"
    assert "'orphan-bare-value'" not in argv, f"bare value órfão vazou: {argv!r}"
    # --scope (forma espaço) e --id (forma "=") sobrevivem.
    assert "SCOPE=feature" in r.stdout
    assert "ID=foo" in r.stdout
