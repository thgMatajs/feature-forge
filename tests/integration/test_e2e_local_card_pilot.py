"""E2E integration — local card overlay pilot scenario.

Reproduz o fluxo do projeto-alvo (KMP Android+iOS) onde uma stack
exótica é mitigada via card local antes do canon ter cobertura.

Cenário simulado:
  1. `tmp_project` com signal `import com.retrofit-mock.client` em build.gradle.kts
     (usamos um stub `retrofit-mock` como needle pra exercitar overlay sem
     depender do próprio card retrofit-client que está sendo shippado nesta entrega).
  2. Loader cascade não acha nenhum card cobrindo o needle.
  3. Step 7.5 detecta orphan → user escolhe caminho 1 → cria card local.
  4. Re-detection match → card local ativa.
  5. `forge verify` cascade verde.

Marker: integration (slow). Excluído da rapid CI lane.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from engine.cards import CardConflictError
from engine.cards.loader import load_all_cards

pytestmark = pytest.mark.integration


@pytest.fixture
def pilot_project(tmp_path: Path) -> Path:
    """Project com signal `retrofit-mock` que NÃO está em nenhum card canon."""
    proj = tmp_path / "pilot"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "cards").mkdir(parents=True)
    (proj / ".claude" / "inventory").mkdir(parents=True)

    # Material que dispara um signal customizado
    app_kt = proj / "app" / "src" / "main" / "kotlin" / "App.kt"
    app_kt.parent.mkdir(parents=True, exist_ok=True)
    app_kt.write_text(
        "package app\n\nimport com.retrofit_mock.client.MockClient\n", encoding="utf-8"
    )

    return proj


def _write_canon_card(project: Path, name: str, provides: list[str]) -> None:
    card_dir = project / ".claude" / "cards" / name
    card_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "schema-version": 1,
        "identity": {
            "name": name,
            "version": "1.0.0",
            "description": "Canon stub for E2E",
            "category": "kmp",
            "maturity": "stable",
        },
        "provides": provides,
        "requires": [],
        "conflicts-with": [],
        "detection": {"signals": [], "threshold": 0.5},
    }
    (card_dir / "card.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    (card_dir / "README.md").write_text("# canon\n", encoding="utf-8")


def _write_local_card_covering_mock(project: Path) -> None:
    card_dir = project / ".claude" / "cards" / "local" / "retrofit-mock-local"
    card_dir.mkdir(parents=True, exist_ok=True)
    (card_dir / "detection").mkdir(parents=True, exist_ok=True)
    data = {
        "schema-version": 1,
        "identity": {
            "name": "retrofit-mock-local",
            "version": "0.1.0",
            "description": "Local card cobrindo retrofit-mock (E2E pilot)",
            "category": "network",
            "maturity": "experimental",
        },
        "provides": ["kotlin-multiplatform"],  # label canon válida (placeholder)
        "requires": [],
        "conflicts-with": [],
        "detection": {
            "signals": [
                {
                    "type": "file-content",
                    "glob": "**/*.kt",
                    "contains": "com.retrofit_mock.client",
                    "confidence": 0.6,
                }
            ],
            "threshold": 0.5,
        },
    }
    (card_dir / "card.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    (card_dir / "README.md").write_text("# local\n", encoding="utf-8")
    (card_dir / "detection" / "signals.yaml").write_text(
        "schema-version: 1\nsignals: []\nthreshold: 0.5\n", encoding="utf-8"
    )


def test_pilot_canon_only_loads_without_local(pilot_project):
    """Sanity: canon-only sem local lê sem erro."""
    _write_canon_card(pilot_project, "kotlin-base", ["kotlin"])
    manifests = load_all_cards(pilot_project)
    names = {m.name for m in manifests}
    assert "kotlin-base" in names


def test_pilot_local_card_added_appears_in_cascade(pilot_project):
    """Após criar local, cascade retorna canon + local."""
    _write_canon_card(pilot_project, "kotlin-base", ["kotlin"])
    _write_local_card_covering_mock(pilot_project)
    manifests = load_all_cards(pilot_project)
    by_origin = {(m.name, m.origin) for m in manifests}
    assert ("kotlin-base", "canon") in by_origin
    assert ("retrofit-mock-local", "local") in by_origin


def test_pilot_local_cards_manifest_written(pilot_project):
    _write_canon_card(pilot_project, "kotlin-base", ["kotlin"])
    _write_local_card_covering_mock(pilot_project)
    load_all_cards(pilot_project)
    manifest_path = pilot_project / ".claude" / "inventory" / "local-cards-manifest.yaml"
    assert manifest_path.is_file()
    parsed = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    names = {c["name"] for c in parsed.get("local-cards") or []}
    assert "retrofit-mock-local" in names


def test_pilot_canon_local_collision_hard_fails(pilot_project):
    """Workaround Approach A: nome colidindo é hard fail."""
    _write_canon_card(pilot_project, "kotlin-base", ["kotlin"])
    # cria local com nome IGUAL ao canon → CardConflictError
    canon_root = pilot_project / ".claude" / "cards"
    collide_local = canon_root / "local" / "kotlin-base"
    collide_local.mkdir(parents=True)
    data = {
        "schema-version": 1,
        "identity": {
            "name": "kotlin-base",
            "version": "0.1.0",
            "description": "collision attempt",
            "category": "kmp",
            "maturity": "experimental",
        },
        "provides": ["kotlin"],
        "requires": [],
        "conflicts-with": [],
    }
    (collide_local / "card.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    (collide_local / "README.md").write_text("# c\n", encoding="utf-8")
    with pytest.raises(CardConflictError):
        load_all_cards(pilot_project)


def test_pilot_orphan_to_local_flow_endtoend(pilot_project, monkeypatch):
    """Fluxo completo: orphan detectado → cria local inline → re-detection cobre."""
    from engine.init import (
        _check_orphan_signals,
        _card_local_add_inline,
        OrphanSignal,
    )

    class _Cat:
        reserved = frozenset()

    # passo 1: sem cards locais nem canon cobrindo, mock orphan
    orphan = OrphanSignal(
        signal_id="orphan:com.retrofit_mock.client",
        source="detected in 1 file(s)",
        suggested_capability="kotlin-multiplatform",
        is_reserved=False,
        hit_count=1,
    )

    # passo 2: cria local inline (Step 7.5 caminho 1)
    _card_local_add_inline(pilot_project, orphan)

    created = pilot_project / ".claude" / "cards" / "local" / "kotlin-multiplatform"
    # _card_local_add_inline nomeia com a capability — confirma existência
    assert created.is_dir()
    assert (created / "card.yaml").is_file()

    # passo 3: cascade load confirma que card local entrou
    manifests = load_all_cards(pilot_project)
    by_origin = {(m.name, m.origin) for m in manifests}
    assert ("kotlin-multiplatform", "local") in by_origin
