"""Unit tests for check_tool_available and _dispatch_tool.

Cobre Task 6 do plan cc-gate: dispatcher per-language das 4 tools
nativas (Detekt/SwiftLint/eslint/Radon) + trust-but-verify de
availability via shutil.which.

`check_tool_available` vive em `validators/_gate_infra.py` desde Phase 0
(gate-infra-extract Task 2); patches de `shutil.which` apontam para esse
módulo. CC validator re-exporta o helper via import, preservando o
contrato observável.

Spec source: `docs/superpowers/specs/2026-06-03-cc-gate-design.md §3`
(tabela tools + trust-but-verify de tool availability + edge cases).

Disciplina de robustez:
  - tool missing → DispatchResult(tool_found=False)
  - tool crash (non-zero exit / timeout / OSError) → DispatchResult(crashed=True)
  - eslint exit=1 (issues encontrados) NÃO é crash — exit 1 é benign
  - dispatcher nunca raise: caller emite result_warn e mantém cascade.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest import mock  # noqa: F401  — kept for parity with plan template

import pytest

import _gate_infra
import check_cyclomatic_complexity as v


def test_check_tool_available_returns_true_when_on_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_gate_infra.shutil, "which", lambda name: "/usr/local/bin/" + name)
    assert v.check_tool_available("detekt") is True


def test_check_tool_available_returns_false_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_gate_infra.shutil, "which", lambda name: None)
    assert v.check_tool_available("swiftlint") is False


def test_dispatch_tool_kotlin_builds_correct_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, list[str]] = {}

    def fake_run(cmd, **kwargs):
        calls["cmd"] = list(cmd)
        return subprocess.CompletedProcess(
            cmd, returncode=0, stdout='{"issues":[]}', stderr=""
        )

    monkeypatch.setattr(v.subprocess, "run", fake_run)
    monkeypatch.setattr(_gate_infra.shutil, "which", lambda name: "/usr/local/bin/" + name)

    result = v._dispatch_tool(
        language="kotlin",
        files=["app/A.kt", "app/B.kt"],
        threshold=10,
        project_root=Path("/repo"),
    )

    assert result.tool_found is True
    assert result.raw_stdout == '{"issues":[]}'
    assert calls["cmd"][0] == "detekt"
    assert "--config" in calls["cmd"]
    # files passados via --input separados por vírgula (per spec §3 tabela)
    assert any("app/A.kt" in arg for arg in calls["cmd"])
    assert any("app/B.kt" in arg for arg in calls["cmd"])


def test_dispatch_tool_swift_builds_correct_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="[]", stderr="")

    monkeypatch.setattr(v.subprocess, "run", fake_run)
    monkeypatch.setattr(_gate_infra.shutil, "which", lambda name: "/usr/local/bin/swiftlint")

    result = v._dispatch_tool(
        language="swift",
        files=["app/Login.swift"],
        threshold=10,
        project_root=Path("/repo"),
    )

    assert result.tool_found is True
    assert captured["cmd"][0] == "swiftlint"
    assert "--reporter" in captured["cmd"]
    assert "json" in captured["cmd"]
    assert "app/Login.swift" in captured["cmd"]


def test_dispatch_tool_ts_builds_correct_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        # eslint emits exit=1 quando acha issue — NÃO é crash, é normal
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="[]", stderr="")

    monkeypatch.setattr(v.subprocess, "run", fake_run)
    monkeypatch.setattr(_gate_infra.shutil, "which", lambda name: "/usr/local/bin/eslint")

    result = v._dispatch_tool(
        language="ts",
        files=["src/foo.ts"],
        threshold=15,
        project_root=Path("/repo"),
    )

    # benign exit=1 → NOT crashed
    assert result.tool_found is True
    assert result.crashed is False
    assert captured["cmd"][0] == "eslint"
    assert "--format" in captured["cmd"]
    assert "json" in captured["cmd"]
    # threshold injetado na rule inline
    assert any('"max": 15' in arg or "'max': 15" in arg for arg in captured["cmd"])
    assert "src/foo.ts" in captured["cmd"]


def test_dispatch_tool_python_calls_radon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr(v.subprocess, "run", fake_run)
    monkeypatch.setattr(_gate_infra.shutil, "which", lambda name: "/usr/local/bin/radon")

    result = v._dispatch_tool(
        language="python",
        files=["engine/cli.py"],
        threshold=10,
        project_root=Path("/repo"),
    )
    assert result.tool_found is True
    assert captured["cmd"][0] == "radon"
    assert "cc" in captured["cmd"]
    assert "-j" in captured["cmd"]
    assert "engine/cli.py" in captured["cmd"]
    # H2 regression — `-n F` mask hides CC 11..40 from the parser. Gate
    # must observe ALL functions and filter by threshold in Python.
    assert "F" not in captured["cmd"], (
        "radon must not use -n F (masks CC 11..40); use -n A or no rank filter"
    )


def test_dispatch_tool_kotlin_propagates_threshold_via_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H1 — Detekt threshold must be the dynamic value, not the static 10.

    Detekt does not accept a threshold via CLI; the validator therefore
    renders a temp config file with the requested threshold and passes
    `--config <tmpfile>`. The rendered config must contain the dynamic
    threshold so card overrides actually tighten the gate (spec §3).
    """
    captured: dict[str, list[str]] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        # Read the config path passed via --config and snapshot its contents
        # so the assertion can confirm the dynamic threshold reached the file.
        if "--config" in cmd:
            idx = cmd.index("--config")
            cfg_path = Path(cmd[idx + 1])
            captured["config_contents"] = cfg_path.read_text(encoding="utf-8")
        return subprocess.CompletedProcess(
            cmd, returncode=0, stdout='{"issues":[]}', stderr=""
        )

    monkeypatch.setattr(v.subprocess, "run", fake_run)
    monkeypatch.setattr(_gate_infra.shutil, "which", lambda name: "/usr/local/bin/detekt")

    result = v._dispatch_tool(
        language="kotlin",
        files=["app/A.kt"],
        threshold=5,
        project_root=Path("/repo"),
    )

    assert result.tool_found is True
    assert "--config" in captured["cmd"]
    cfg = captured.get("config_contents", "")
    assert "threshold: 5" in cfg, (
        f"detekt config must carry dynamic threshold 5; got:\n{cfg}"
    )
    # And must NOT carry the hardcoded fallback when override demanded 5.
    assert "threshold: 10" not in cfg


def test_dispatch_tool_swift_propagates_threshold_via_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H1 — SwiftLint threshold must be rendered into the temp config.

    SwiftLint's `cyclomatic_complexity` rule reads `warning:` / `error:`
    from the config. CLI cannot override per-rule thresholds, so the
    validator renders the config dynamically (spec §3 threshold-via-CLI
    contract honored by tmpfile render).
    """
    captured: dict[str, list[str]] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        if "--config" in cmd:
            idx = cmd.index("--config")
            cfg_path = Path(cmd[idx + 1])
            captured["config_contents"] = cfg_path.read_text(encoding="utf-8")
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="[]", stderr="")

    monkeypatch.setattr(v.subprocess, "run", fake_run)
    monkeypatch.setattr(_gate_infra.shutil, "which", lambda name: "/usr/local/bin/swiftlint")

    result = v._dispatch_tool(
        language="swift",
        files=["app/Login.swift"],
        threshold=7,
        project_root=Path("/repo"),
    )

    assert result.tool_found is True
    cfg = captured.get("config_contents", "")
    assert "warning: 7" in cfg, (
        f"swiftlint config must carry warning=7; got:\n{cfg}"
    )
    assert "error: 7" in cfg, (
        f"swiftlint config must carry error=7; got:\n{cfg}"
    )


def test_dispatch_tool_missing_returns_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_gate_infra.shutil, "which", lambda name: None)

    result = v._dispatch_tool(
        language="kotlin",
        files=["app/A.kt"],
        threshold=10,
        project_root=Path("/repo"),
    )
    assert result.tool_found is False
    assert result.raw_stdout == ""
    assert (
        "not installed" in result.error_message.lower()
        or "missing" in result.error_message.lower()
        or "path" in result.error_message.lower()
    )


def test_dispatch_tool_crash_returns_error_with_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd, returncode=2, stdout="", stderr="boom: tool exploded"
        )

    monkeypatch.setattr(v.subprocess, "run", fake_run)
    monkeypatch.setattr(_gate_infra.shutil, "which", lambda name: "/usr/local/bin/detekt")

    result = v._dispatch_tool(
        language="kotlin",
        files=["app/A.kt"],
        threshold=10,
        project_root=Path("/repo"),
    )
    assert result.tool_found is True
    assert result.crashed is True
    assert "boom" in result.error_message


def test_dispatch_tool_timeout_returns_crashed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=60)

    monkeypatch.setattr(v.subprocess, "run", fake_run)
    monkeypatch.setattr(_gate_infra.shutil, "which", lambda name: "/usr/local/bin/detekt")

    result = v._dispatch_tool(
        language="kotlin",
        files=["app/A.kt"],
        threshold=10,
        project_root=Path("/repo"),
    )
    assert result.tool_found is True
    assert result.crashed is True
    assert "timeout" in result.error_message.lower()


def test_dispatch_tool_unsupported_language_returns_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Defensive: even though caller filters by SUPPORTED_EXTENSIONS, dispatcher
    # must not raise when given an unknown language — emit a clean not_found.
    monkeypatch.setattr(_gate_infra.shutil, "which", lambda name: "/usr/local/bin/whatever")

    with pytest.raises(KeyError):
        # _TOOL_BIN lookup falha pra lang desconhecida; este é o contrato:
        # caller deve garantir language ∈ {kotlin, swift, ts, python}.
        v._dispatch_tool(
            language="rust",
            files=["src/lib.rs"],
            threshold=10,
            project_root=Path("/repo"),
        )
