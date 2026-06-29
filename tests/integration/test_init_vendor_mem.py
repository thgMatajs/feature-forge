"""Fase 1 W-VENDOR Task 1 — testa a vendorização do mem via `forge init`.

TDD estrito: teste escrito PRIMEIRO (vermelho — `_vendor_mem` ainda não existe
em `engine.init`), depois a implementação mínima o torna verde.

Coberturas:
- Binário copiado em `.claude/bin/mem` e marcado executável.
- Scaffold do mem (gitignore mem.db + AGENTS.md) aplicado via `mem init`.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from engine import init
from engine.utils import paths


@pytest.mark.integration
def test_vendor_mem_copies_binary_and_scaffolds(tmp_path, monkeypatch):
    """_vendor_mem copia o asset e roda o scaffold do mem no consumidor."""
    # Projeto consumidor limpo com um .git pra find_project_root.
    (tmp_path / ".git").mkdir()
    monkeypatch.delenv("FORGE_HOME", raising=False)  # usa o fallback p/ o repo real

    init._vendor_mem(tmp_path)

    vendored = paths.vendored_mem_path(tmp_path)
    assert vendored.is_file(), "binário do mem não vendorizado"
    assert vendored.stat().st_mode & stat.S_IXUSR, "mem vendorizado não é executável"

    # scaffold do mem: gitignore do mem.db + índice no AGENTS.md
    gi = (tmp_path / ".gitignore").read_text() if (tmp_path / ".gitignore").exists() else ""
    assert "mem.db" in gi
    assert (tmp_path / "AGENTS.md").exists()
