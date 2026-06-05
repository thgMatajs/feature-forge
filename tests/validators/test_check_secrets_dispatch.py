"""Dispatch tests for `check_secrets` validator (R1.1 Task 3).

Cobre o segundo bloco de mecânica do gate de secrets:

- `_build_gitleaks_cmd` — cmd literal pra ``gitleaks detect`` com staged
  files via ``--source <path>`` repetível. Reuso direto de
  ``dispatch_native_tool`` da Phase 0 (sem reinventar subprocess).
- `_build_trufflehog_cmd` — cmd literal pra ``trufflehog filesystem
  --only-verified --json``. Decisão ``--only-verified`` é locked do
  brainstorm 2026-06-05 (zero false positives ativos).
- `_dispatch_for_stage` — resolve stage → (tool_bin, cmd_builder),
  forwarda ``benign_nonzero_codes=(1,)`` porque ambas as tools emitem
  exit=1 pra sinalizar "encontrei findings" (não crash, mesmo padrão
  do eslint).

Robustness: stage desconhecido levanta ``KeyError`` (fail-fast, sem
fallback silencioso — caller sempre passa stage explícito ``per_task``
ou ``cascade``).

Patches de ``subprocess.run`` / ``shutil.which`` apontam pra
``_gate_infra`` (não pro módulo do validator) — segue o padrão
estabelecido em ``test_cc_dispatch.py``.

Spec source: ``docs/superpowers/specs/2026-06-05-check-secrets-design.md
§3 (stage dispatch)``.
Plan: ``docs/superpowers/plans/2026-06-05-check-secrets-implementation.md``
Task 3.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import _gate_infra
import check_secrets as v


# ── _build_gitleaks_cmd ──────────────────────────────────────────────────────


def test_build_gitleaks_cmd_shape() -> None:
    """gitleaks cmd: literal exato com ``--source`` repetível por staged file."""
    cmd = v._build_gitleaks_cmd("gitleaks", ["a.kt", "b.ts"], None)
    assert cmd == [
        "gitleaks",
        "detect",
        "--no-git",
        "--report-format=json",
        "--report-path=-",
        "--source", "a.kt",
        "--source", "b.ts",
    ]


def test_build_gitleaks_cmd_empty_files_keeps_base_args() -> None:
    """gitleaks com 0 files: args base preservados, sem ``--source`` extra.

    Edge defensiva — caller de alto nível (Task 4) filtra empty antes, mas
    o builder não deve corromper nem crashar se receber lista vazia.
    """
    cmd = v._build_gitleaks_cmd("gitleaks", [], None)
    assert cmd == [
        "gitleaks",
        "detect",
        "--no-git",
        "--report-format=json",
        "--report-path=-",
    ]


def test_build_gitleaks_cmd_ignores_rendered_config() -> None:
    """gitleaks cmd não consome ``rendered_config`` em v1.2-dev (gap SECRETS-1)."""
    cmd_none = v._build_gitleaks_cmd("gitleaks", ["a.kt"], None)
    cmd_with = v._build_gitleaks_cmd("gitleaks", ["a.kt"], "/tmp/ignored.toml")
    # rendered_config não deve aparecer no cmd em qualquer forma.
    assert cmd_none == cmd_with
    assert "/tmp/ignored.toml" not in cmd_with


# ── _build_trufflehog_cmd ────────────────────────────────────────────────────


def test_build_trufflehog_cmd_shape() -> None:
    """trufflehog cmd: ``filesystem --only-verified --json <files...>`` literal."""
    cmd = v._build_trufflehog_cmd("trufflehog", ["app/Foo.kt"], None)
    assert cmd == [
        "trufflehog",
        "filesystem",
        "--only-verified",
        "--json",
        "app/Foo.kt",
    ]


def test_build_trufflehog_cmd_appends_multiple_files() -> None:
    """trufflehog: files aparecem após os flags, na ordem recebida."""
    cmd = v._build_trufflehog_cmd(
        "trufflehog", ["app/Foo.kt", "lib/Bar.swift", "web/Baz.ts"], None
    )
    assert cmd[:4] == ["trufflehog", "filesystem", "--only-verified", "--json"]
    assert cmd[4:] == ["app/Foo.kt", "lib/Bar.swift", "web/Baz.ts"]


def test_build_trufflehog_cmd_ignores_rendered_config() -> None:
    """trufflehog cmd não consome ``rendered_config`` em v1.2-dev."""
    cmd_none = v._build_trufflehog_cmd("trufflehog", ["a.kt"], None)
    cmd_with = v._build_trufflehog_cmd("trufflehog", ["a.kt"], "/tmp/x.yaml")
    assert cmd_none == cmd_with
    assert "/tmp/x.yaml" not in cmd_with


# ── _dispatch_for_stage ──────────────────────────────────────────────────────


def _make_fake_dispatch(captured: dict) -> object:
    """Builder de fake p/ capturar kwargs do dispatch sem rodar subprocess."""

    def fake(**kwargs):
        captured.update(kwargs)
        return _gate_infra.DispatchResult(
            language=kwargs.get("language", ""),
            tool_found=True,
            crashed=False,
            raw_stdout="",
            error_message="",
        )

    return fake


def test_dispatch_for_stage_per_task_uses_gitleaks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``per_task`` resolve pra ``gitleaks`` + ``_build_gitleaks_cmd``."""
    captured: dict = {}
    monkeypatch.setattr(v, "dispatch_native_tool", _make_fake_dispatch(captured))

    v._dispatch_for_stage(
        "per_task", [Path("a.kt"), Path("b.ts")], project_root=Path("/repo")
    )

    assert captured["tool_bin"] == "gitleaks"
    assert captured["cmd_builder"] is v._build_gitleaks_cmd
    # files convertido pra list[str] antes de chegar no dispatch.
    assert captured["files"] == ["a.kt", "b.ts"]
    assert captured["project_root"] == Path("/repo")


def test_dispatch_for_stage_cascade_uses_trufflehog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``cascade`` resolve pra ``trufflehog`` + ``_build_trufflehog_cmd``."""
    captured: dict = {}
    monkeypatch.setattr(v, "dispatch_native_tool", _make_fake_dispatch(captured))

    v._dispatch_for_stage(
        "cascade", [Path("app/Foo.kt")], project_root=Path("/repo")
    )

    assert captured["tool_bin"] == "trufflehog"
    assert captured["cmd_builder"] is v._build_trufflehog_cmd
    assert captured["files"] == ["app/Foo.kt"]


def test_dispatch_for_stage_forwards_benign_nonzero_codes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``benign_nonzero_codes=(1,)`` é forwarded — ambas as tools usam exit=1
    pra sinalizar "encontrei findings" (não crash). Sem este kwarg, o
    dispatch trataria findings como crash e cobertura cascade falharia.
    """
    captured: dict = {}
    monkeypatch.setattr(v, "dispatch_native_tool", _make_fake_dispatch(captured))

    v._dispatch_for_stage("per_task", [Path("a.kt")], project_root=Path("/repo"))

    assert captured["benign_nonzero_codes"] == (1,)


def test_dispatch_for_stage_language_is_any(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Secrets atravessam linguagens — campo ``language="any"`` é descritivo,
    não load-bearing (per plan anti-padrão #1).
    """
    captured: dict = {}
    monkeypatch.setattr(v, "dispatch_native_tool", _make_fake_dispatch(captured))

    v._dispatch_for_stage("cascade", [Path("x.kt")], project_root=Path("/repo"))

    assert captured["language"] == "any"


def test_dispatch_for_stage_raises_on_unknown_stage() -> None:
    """Stage desconhecido levanta ``KeyError`` — fail-fast, sem fallback."""
    with pytest.raises(KeyError):
        v._dispatch_for_stage(
            "misc", [Path("a.kt")], project_root=Path("/repo")
        )


def test_dispatch_for_stage_returns_dispatch_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retorno é ``DispatchResult`` (forwardado do ``dispatch_native_tool``)."""

    def fake(**kwargs):
        return _gate_infra.DispatchResult(
            language="any",
            tool_found=True,
            crashed=False,
            raw_stdout='[{"RuleID": "aws_key"}]',
            error_message="",
        )

    monkeypatch.setattr(v, "dispatch_native_tool", fake)

    result = v._dispatch_for_stage(
        "per_task", [Path("a.kt")], project_root=Path("/repo")
    )

    assert isinstance(result, _gate_infra.DispatchResult)
    assert result.tool_found is True
    assert result.raw_stdout == '[{"RuleID": "aws_key"}]'


# ── Integration smoke: cmd_builder via dispatch_native_tool ──────────────────
#
# Confere que o cmd_builder do gate compõe corretamente com a infra real
# (sem stub do dispatch). Patch só do subprocess.run + shutil.which.


def test_dispatch_for_stage_per_task_integrates_with_real_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end leve: ``_dispatch_for_stage`` → ``dispatch_native_tool`` real
    → ``_build_gitleaks_cmd`` real → ``subprocess.run`` mockado. Confere que o
    cmd que chegaria no shell é o esperado (``--source`` repetido).
    """
    captured_cmd: list[str] = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return subprocess.CompletedProcess(
            cmd, returncode=0, stdout="[]", stderr=""
        )

    monkeypatch.setattr(_gate_infra.subprocess, "run", fake_run)
    monkeypatch.setattr(
        _gate_infra.shutil, "which", lambda name: "/usr/local/bin/" + name
    )

    result = v._dispatch_for_stage(
        "per_task",
        [Path("app/A.kt"), Path("lib/B.swift")],
        project_root=Path("/repo"),
    )

    assert result.tool_found is True
    assert result.crashed is False
    assert captured_cmd == [
        "gitleaks",
        "detect",
        "--no-git",
        "--report-format=json",
        "--report-path=-",
        "--source", "app/A.kt",
        "--source", "lib/B.swift",
    ]
