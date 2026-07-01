"""Helpers compartilhados pros testes de gates de execução externa.

Extraídos de test_verify_build_only.py + test_verify_native_gates.py (I-02).
Reconciliação de assinatura: build_only tinha `exit_code=0` (default) e
native_gates tinha `exit_code` required — adotado o SUPERSET (`exit_code=0`
default), compatível com ambos os call-sites.
"""
from __future__ import annotations

import stat
from pathlib import Path

from engine.external_exec import ExternalToolResult


def _write_fake_gradlew(project_root: Path, *, exit_code: int = 0) -> Path:
    """Cria um ./gradlew trivial que sai com `exit_code` (visível a resolve_invocation)."""
    gradlew = project_root / "gradlew"
    gradlew.write_text(f"#!/bin/sh\nexit {exit_code}\n", encoding="utf-8")
    mode = gradlew.stat().st_mode
    gradlew.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return gradlew


def _fake_run(status: str, *, exit_code: int | None, skipped_reason: str = ""):
    """Factory de stub pra monkeypatch de run_external_tool (ignora timeout)."""

    def _runner(argv, project_root, *, timeout=120):
        return ExternalToolResult(
            tool=argv[0],
            status=status,
            exit_code=exit_code,
            stdout="",
            stderr="",
            duration_ms=20,
            skipped_reason=skipped_reason,
        )

    return _runner
