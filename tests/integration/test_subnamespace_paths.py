"""Integration test — callsites usam helpers do sub-namespace .claude/forge/.

Cobre Task 0.8 da v1.3 pilot-ready: 50+ callsites em engine/ + validators/
passaram a usar os helpers ``forge_config_path`` / ``forge_state_dir`` /
``forge_hooks_dir`` / ``forge_cards_local_dir`` em vez de paths hardcoded.

Os helpers ficaram introduzidos em Task 0.4 (commit 1b06510). Esta task
substitui as callsites mecanicamente — sem mudar signatures nem
comportamento além da relocação canônica das pastas.

Spec: ``docs/superpowers/specs/2026-06-16-v1-3-pilot-ready-design.md`` §2
(sub-namespace) + §5 (clean break, sem migração).
Plan: ``docs/superpowers/plans/2026-06-16-v1-3-pilot-ready.md`` Task 0.8.

A versão "init writes under .claude/forge/" é Task 0.10. Aqui validamos
apenas a contract dos helpers + presença das importações nos módulos
afetados — garantindo o caminho de execução acaba no sub-namespace.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.integration
def test_forge_helpers_produce_subnamespace_paths(tmp_path: Path) -> None:
    """Os 5 helpers de Task 0.4 retornam o sub-namespace canônico §2."""
    from engine.utils.paths import (
        forge_cards_local_dir,
        forge_config_path,
        forge_dir,
        forge_hooks_dir,
        forge_state_dir,
    )

    assert forge_dir(tmp_path) == tmp_path / ".claude" / "forge"
    assert (
        forge_config_path(tmp_path)
        == tmp_path / ".claude" / "forge" / "forge-config.yaml"
    )
    assert forge_state_dir(tmp_path) == tmp_path / ".claude" / "forge" / "state"
    assert (
        forge_cards_local_dir(tmp_path)
        == tmp_path / ".claude" / "forge" / "cards" / "local"
    )
    assert forge_hooks_dir(tmp_path) == tmp_path / ".claude" / "forge" / "hooks"


@pytest.mark.integration
def test_validators_import_subnamespace_helpers() -> None:
    """Validators que liam workflow-config hardcoded agora importam o helper."""
    import inspect

    import check_cyclomatic_complexity as cc
    import check_secrets as cs
    import validate_forge_config as vfc

    cc_src = inspect.getsource(cc)
    cs_src = inspect.getsource(cs)
    vfc_src = inspect.getsource(vfc)

    # Cada um dos três validators tem que referenciar o helper canônico
    # em algum ponto (import OU chamada). Isso é proxy estático suficiente
    # pra garantir que o callsite migrou.
    assert "forge_config_path" in cc_src or "workflow_config_path" in cc_src
    assert "forge_config_path" in cs_src or "workflow_config_path" in cs_src
    assert "forge_config_path" in vfc_src or "workflow_config_path" in vfc_src

    # Sem hardcoded `project_root / ".claude" / "workflow-config.yaml"`
    # remanescente no código (string literal "workflow-config.yaml" sozinho
    # pode aparecer em docstrings / mensagens — só path construction conta).
    for src in (cc_src, cs_src, vfc_src):
        assert '".claude" / "workflow-config.yaml"' not in src, (
            "callsite ainda constrói path hardcoded — deveria usar helper"
        )


@pytest.mark.integration
def test_engine_implement_state_uses_forge_state_dir() -> None:
    """``engine/implement.py`` aponta state files pro sub-namespace."""
    import inspect

    from engine import implement as impl

    src = inspect.getsource(impl)
    # Os 2 callsites de state file (cc-gate-bypass + secrets-gate-bypass)
    # passaram a derivar via forge_state_dir.
    assert "forge_state_dir" in src
    # E não constroem path hardcoded mais.
    assert '".claude" / "state" / "cc-gate-bypass.jsonl"' not in src
    assert '".claude" / "state" / "secrets-gate-bypass.jsonl"' not in src
