"""Fronteira de execução externa genérica (Fase 0b).

Cobre run_external_tool (pass/fail/timeout→degraded/OSError→degraded, env
reduzido, cwd correto) e resolve_invocation (wrapper hit, path-abs hit, which
hit, none→skip). Stub Python como binário externo controlado — sem gradle/ktlint
real. Mentor calmo: o helper é genérico, sabe só rodar argv e resolver candidatos.
"""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from engine.external_exec import (
    ExternalToolResult,
    resolve_invocation,
    run_external_tool,
)


def _make_stub(path: Path, *, exit_code: int = 0, sleep: float = 0.0, echo_env: str = "") -> Path:
    """Escreve um stub Python executável que dorme, ecoa uma env var e sai com exit_code."""
    body = (
        "#!/usr/bin/env python3\n"
        "import os, sys, time\n"
        f"time.sleep({sleep})\n"
        f"v = os.environ.get({echo_env!r}, '')\n"
        "sys.stdout.write('ENV=' + v + '\\n')\n"
        "sys.stderr.write('stub-stderr\\n')\n"
        f"sys.exit({exit_code})\n"
    )
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def test_run_pass(tmp_path: Path) -> None:
    stub = _make_stub(tmp_path / "ok.py", exit_code=0)
    res = run_external_tool([sys.executable, str(stub)], tmp_path)
    assert isinstance(res, ExternalToolResult)
    assert res.status == "pass"
    assert res.exit_code == 0
    assert "stub-stderr" in res.stderr
    assert res.duration_ms >= 0


def test_run_fail(tmp_path: Path) -> None:
    stub = _make_stub(tmp_path / "bad.py", exit_code=3)
    res = run_external_tool([sys.executable, str(stub)], tmp_path)
    assert res.status == "fail"
    assert res.exit_code == 3


def test_run_timeout_is_degraded(tmp_path: Path) -> None:
    stub = _make_stub(tmp_path / "slow.py", exit_code=0, sleep=2.0)
    res = run_external_tool([sys.executable, str(stub)], tmp_path, timeout=1)
    assert res.status == "degraded"
    assert res.exit_code is None
    # No path TimeoutExpired, stderr=="" e skipped_reason sempre carrega "timeout".
    assert "timeout" in res.skipped_reason.lower()


def test_run_oserror_is_degraded(tmp_path: Path) -> None:
    res = run_external_tool([str(tmp_path / "nao-existe-binario")], tmp_path)
    assert res.status == "degraded"
    assert res.exit_code is None


def test_env_is_reduced(tmp_path: Path) -> None:
    # Var sensitive NÃO pode vazar pro subprocess; var fora da allowlist também não.
    os.environ["MY_API_KEY"] = "leak-me"
    os.environ["RANDOM_NON_ALLOWLISTED"] = "also-leak"
    try:
        stub_secret = _make_stub(tmp_path / "echo_secret.py", echo_env="MY_API_KEY")
        res = run_external_tool([sys.executable, str(stub_secret)], tmp_path)
        assert res.status == "pass"
        assert "leak-me" not in res.stdout
        assert res.stdout.strip() == "ENV="
        stub_other = _make_stub(tmp_path / "echo_other.py", echo_env="RANDOM_NON_ALLOWLISTED")
        res2 = run_external_tool([sys.executable, str(stub_other)], tmp_path)
        assert "also-leak" not in res2.stdout
    finally:
        os.environ.pop("MY_API_KEY", None)
        os.environ.pop("RANDOM_NON_ALLOWLISTED", None)


def test_cwd_is_project_root(tmp_path: Path) -> None:
    # O stub imprime o cwd; deve ser o project_root passado.
    stub = tmp_path / "pwd.py"
    stub.write_text(
        "#!/usr/bin/env python3\nimport os,sys\nsys.stdout.write(os.getcwd())\n",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    sub = tmp_path / "subdir"
    sub.mkdir()
    res = run_external_tool([sys.executable, str(stub)], sub)
    assert Path(res.stdout.strip()).resolve() == sub.resolve()


def test_resolve_wrapper_hit(tmp_path: Path) -> None:
    (tmp_path / "gradlew").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    argv = resolve_invocation([["./gradlew", "someTask"]], tmp_path)
    assert argv == ["./gradlew", "someTask"]


def test_resolve_wrapper_miss_falls_through(tmp_path: Path) -> None:
    # Wrapper ausente, mas path absoluto existente como 2º candidato vence.
    real = _make_stub(tmp_path / "real-bin.py")
    argv = resolve_invocation(
        [["./gradlew", "x"], [str(real), "--flag"]],
        tmp_path,
    )
    assert argv == [str(real), "--flag"]


def test_resolve_config_abs_path_hit(tmp_path: Path) -> None:
    real = _make_stub(tmp_path / "cfg-bin.py")
    argv = resolve_invocation([[str(real), "--reporter=json"]], tmp_path)
    assert argv == [str(real), "--reporter=json"]


def test_resolve_which_hit(tmp_path: Path) -> None:
    # "python3" (ou o executável atual) existe no PATH → which resolve.
    name = Path(sys.executable).name
    argv = resolve_invocation([name], tmp_path)
    assert argv is not None
    assert Path(argv[0]).name == name


def test_resolve_none_when_all_absent(tmp_path: Path) -> None:
    argv = resolve_invocation(
        [["./nope-wrapper", "t"], ["/definitivamente/nao/existe"], "binario-fantasma-xyz"],
        tmp_path,
    )
    assert argv is None
