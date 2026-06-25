"""Integration — paranoid scope cross-feature.

Wave 8 Task 8.3: ``raw_target == "paranoid"`` enumera features ate o cap
``paranoid_max_features``. Cobre:

- Enumeração quando há N features (≤ cap)
- Cap respeitado quando há M > cap features
- Greenfield (zero features) → ``ScopeMissingError``

Detalhe operacional: a implementação atual de
``_list_features_for_paranoid`` (engine/qa/scope.py) enumera SEM filtrar
por estado da feature — qualquer dir sob ``features/`` conta. O briefing
do plan menciona filtro por ``state ∈ {planning, implementing,
blocked-on-external, done}`` mas isso é evolução futura; este test cobre
o contrato CORRENTE do código (enumera todos os dirs com cap).

Anti-padrão: criar 100 features dummy (lento).

Marker: integration (slow). Excluído da rapid lane.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def _make_features(tmp_path: Path, slugs: list[str]) -> Path:
    """Cria N features stub.

    Cada feature: dir com feature-spec.yaml mínimo. ``resolve_scope`` em
    paranoid mode só precisa do dir existir.
    """
    proj = tmp_path / "qa-paranoid-pilot"
    (proj / ".git").mkdir(parents=True)
    features_root = (
        proj / "docs" / "forge-specs" / "features"
    )
    features_root.mkdir(parents=True)
    for slug in slugs:
        f = features_root / slug
        f.mkdir()
        (f / "feature-spec.yaml").write_text(
            f"schema-version: 1\nslug: {slug}\n", encoding="utf-8"
        )
    return proj


def test_paranoid_enumerates_features_up_to_cap(tmp_path: Path) -> None:
    """Paranoid com 3 features e cap default (10) → enumera todas."""
    from engine.qa.scope import resolve_scope

    proj = _make_features(
        tmp_path, ["alpha-feature", "beta-feature", "gamma-feature"]
    )

    scope = resolve_scope("paranoid", project_root=proj)
    assert scope.type == "paranoid"
    assert scope.target == "paranoid"
    assert len(scope.paths) == 3
    enumerated_names = {p.name for p in scope.paths}
    assert enumerated_names == {"alpha-feature", "beta-feature", "gamma-feature"}


def test_paranoid_respects_max_features_cap(tmp_path: Path) -> None:
    """5 features + cap=3 → apenas 3 enumeradas (ordem alfabética)."""
    from engine.qa.scope import resolve_scope

    proj = _make_features(
        tmp_path,
        [
            "01-alpha",
            "02-beta",
            "03-gamma",
            "04-delta",
            "05-epsilon",
        ],
    )

    scope = resolve_scope("paranoid", project_root=proj, paranoid_max_features=3)
    assert len(scope.paths) == 3
    # _list_features_for_paranoid usa sorted() → ordem determinística
    names = [p.name for p in scope.paths]
    assert names == ["01-alpha", "02-beta", "03-gamma"]


def test_paranoid_on_greenfield_raises_scope_missing(tmp_path: Path) -> None:
    """Zero features → ScopeMissingError com mensagem de remediation."""
    from engine.qa.scope import ScopeMissingError, resolve_scope

    proj = _make_features(tmp_path, [])  # nenhuma feature

    with pytest.raises(ScopeMissingError) as exc_info:
        resolve_scope("paranoid", project_root=proj)

    # Mensagem cita o caminho de remediation (forge plan) — voz mentor calmo
    msg = str(exc_info.value)
    assert "forge plan" in msg.lower(), (
        "ScopeMissingError em paranoid greenfield deve sugerir `forge plan`"
    )


def test_paranoid_via_run_qa_handler_returns_zero_on_greenfield(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Handler-level: paranoid greenfield → exit 0 + stderr (não raise)."""
    from engine.qa import run_qa

    proj = _make_features(tmp_path, [])
    workflow_config = {"qa": {"enabled": True}}

    exit_code = run_qa("paranoid", project_root=proj, workflow_config=workflow_config)
    assert exit_code == 0  # ScopeError é absorvido no handler

    captured = capsys.readouterr()
    assert "forge plan" in captured.err.lower()
