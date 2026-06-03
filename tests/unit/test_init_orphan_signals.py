"""Unit tests — init Step 7.5: orphan signals detection + 3-caminhos.

Parte 1 (Task 10): _check_orphan_signals detection
Parte 2 (Task 11): _surface_three_paths UX
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from engine.init import (
    InitDecision,
    OrphanSignal,
    _check_orphan_signals,
    _count_needle_hits,
    _surface_three_paths,
)


@pytest.fixture
def project_with_hilt(tmp_path: Path) -> Path:
    """Project root com 3 arquivos .kt mencionando Hilt — orphan target."""
    proj = tmp_path / "proj"
    (proj / "app" / "src" / "main" / "kotlin" / "com" / "x").mkdir(parents=True)
    src = proj / "app" / "src" / "main" / "kotlin" / "com" / "x"
    (src / "App.kt").write_text(
        "package com.x\n\nimport dagger.hilt.android.HiltAndroidApp\n\n@HiltAndroidApp\nclass App\n",
        encoding="utf-8",
    )
    (src / "Module.kt").write_text(
        "package com.x\n\nimport dagger.hilt.android.AndroidEntryPoint\n",
        encoding="utf-8",
    )
    (src / "Helper.kt").write_text(
        "package com.x\n\nimport dagger.hilt.android.qualifiers.ApplicationContext\n",
        encoding="utf-8",
    )
    return proj


class _FakeCatalog:
    def __init__(self, reserved: set[str]) -> None:
        self.reserved = frozenset(reserved)


def test_count_needle_hits_finds_three_files(project_with_hilt):
    count = _count_needle_hits(project_with_hilt, "dagger.hilt.android")
    assert count == 3


def test_count_needle_hits_zero_for_absent_pattern(project_with_hilt):
    count = _count_needle_hits(project_with_hilt, "this-string-does-not-exist")
    assert count == 0


def test_check_orphan_signals_detects_hilt_when_no_card_covers_it(project_with_hilt):
    """Hilt detected, hilt-di label is reserved (canon roadmap) → is_reserved=True."""
    catalog = _FakeCatalog(reserved={"hilt-di"})
    orphans = _check_orphan_signals(project_with_hilt, canonical_cards=[], catalog=catalog)
    hilt_orphans = [o for o in orphans if o.suggested_capability == "hilt-di"]
    assert hilt_orphans, "Hilt orphan deveria ter sido detectado"
    o = hilt_orphans[0]
    assert o.is_reserved is True
    assert o.hit_count >= 1


def test_check_orphan_signals_returns_empty_when_card_covers_needle(project_with_hilt):
    """Card existente cobre `dagger.hilt.android` no detection.signals → não vira orphan."""
    from engine.cards.loader import CardManifest

    fake_card = CardManifest(
        name="hilt-di",
        version="1.0.0",
        schema_version=1,
        description="",
        category="dependency-injection",
        maturity="stable",
        provides=["hilt-di"],
        detection={
            "signals": [
                {"type": "file-content", "glob": "**/*.kt", "contains": "dagger.hilt.android", "confidence": 0.5}
            ],
            "threshold": 0.5,
        },
    )
    catalog = _FakeCatalog(reserved=set())
    orphans = _check_orphan_signals(
        project_with_hilt, canonical_cards=[fake_card], catalog=catalog
    )
    # `dagger.hilt.android` é o needle exato cobrendo — não vira orphan.
    # `@HiltAndroidApp` ainda é outro needle distinto na heurística; depende
    # se está coberto. Aqui só queremos confirmar que o needle coberto sai.
    needles_in_orphans = {o.signal_id for o in orphans}
    assert "orphan:dagger.hilt.android" not in needles_in_orphans


def test_check_orphan_signals_marks_non_reserved_when_not_in_catalog(tmp_path):
    """Suggested capability fora de reserved → is_reserved=False."""
    proj = tmp_path / "p"
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "X.kt").write_text("import io.reactivex.rxjava3.core.Observable\n", encoding="utf-8")

    catalog = _FakeCatalog(reserved=set())  # vazio — nada é reservado
    orphans = _check_orphan_signals(proj, canonical_cards=[], catalog=catalog)
    rx = [o for o in orphans if o.suggested_capability == "rxjava3-streams"]
    assert rx and rx[0].is_reserved is False


def test_check_orphan_signals_empty_project_returns_no_orphans(tmp_path):
    proj = tmp_path / "empty"
    proj.mkdir()
    catalog = _FakeCatalog(reserved={"hilt-di"})
    orphans = _check_orphan_signals(proj, canonical_cards=[], catalog=catalog)
    assert orphans == []


# ── Parte 2 — _surface_three_paths UX ───────────────────────────────────────


@pytest.fixture
def hilt_orphan() -> OrphanSignal:
    return OrphanSignal(
        signal_id="orphan:@HiltAndroidApp",
        source="detected in 3 file(s)",
        suggested_capability="hilt-di",
        is_reserved=True,
        hit_count=3,
    )


@pytest.fixture
def rx_orphan() -> OrphanSignal:
    return OrphanSignal(
        signal_id="orphan:io.reactivex.rxjava3",
        source="detected in 12 file(s)",
        suggested_capability="async-streams",
        is_reserved=False,
        hit_count=12,
    )


def test_three_paths_caminho_1_creates_local_for_non_reserved(rx_orphan, tmp_path):
    """Caminho 1 (não-reservada): chama reconfigure card-local add inline."""
    proj = tmp_path / "p"
    (proj / ".claude").mkdir(parents=True)
    with patch("engine.init.question.ask") as ask_mock, patch(
        "engine.init._card_local_add_inline"
    ) as add_mock:
        ask_mock.return_value = "1"
        decision = _surface_three_paths([rx_orphan], project_root=proj)
    assert decision.choice == "create-local"
    add_mock.assert_called_once()


def test_three_paths_caminho_1_groups_multiple_orphans_by_capability(tmp_path):
    """Múltiplos orphans com mesma suggested_capability viram UMA chamada.

    C14+C15: cada capability deve gerar um único `_card_local_add_inline`
    com a lista consolidada — sem isso, o segundo write sobrescreve o
    primeiro (mesmo diretório local/<capability>/).
    """
    proj = tmp_path / "p"
    (proj / ".claude").mkdir(parents=True)
    orphan_a = OrphanSignal(
        signal_id="orphan:foo-needle-a",
        source="detected in 1 file(s)",
        suggested_capability="shared-cap",
        is_reserved=False,
        hit_count=1,
    )
    orphan_b = OrphanSignal(
        signal_id="orphan:foo-needle-b",
        source="detected in 2 file(s)",
        suggested_capability="shared-cap",
        is_reserved=False,
        hit_count=2,
    )
    with patch("engine.init.question.ask") as ask_mock, patch(
        "engine.init._card_local_add_inline"
    ) as add_mock:
        ask_mock.return_value = "1"
        decision = _surface_three_paths([orphan_a, orphan_b], project_root=proj)
    assert decision.choice == "create-local"
    # Uma única chamada — agrupada por capability.
    add_mock.assert_called_once()
    args, _kwargs = add_mock.call_args
    # Segundo argumento deve ser lista com os dois orphans (signal aceita
    # OrphanSignal | list[OrphanSignal]).
    passed = args[1]
    assert isinstance(passed, list)
    assert {o.signal_id for o in passed} == {
        "orphan:foo-needle-a",
        "orphan:foo-needle-b",
    }


def test_card_local_add_inline_consolidates_signals_from_list(tmp_path):
    """C15: chamada com lista de orphans grava TODOS os signals no card.yaml."""
    from engine.init import _card_local_add_inline

    proj = tmp_path / "p"
    (proj / ".claude").mkdir(parents=True)

    orphans = [
        OrphanSignal(
            signal_id=f"orphan:needle-{i}",
            source=f"detected in {i} file(s)",
            suggested_capability="shared-cap",
            is_reserved=False,
            hit_count=i,
        )
        for i in (1, 2, 3)
    ]
    _card_local_add_inline(proj, orphans)

    card_yaml = proj / ".claude" / "cards" / "local" / "shared-cap" / "card.yaml"
    assert card_yaml.is_file()
    parsed = yaml.safe_load(card_yaml.read_text(encoding="utf-8"))
    signals = (parsed.get("detection") or {}).get("signals") or []
    contains_set = {s.get("contains") for s in signals}
    assert contains_set == {"needle-1", "needle-2", "needle-3"}


def test_card_local_add_inline_accepts_single_orphan_backward_compat(tmp_path):
    """C15: single OrphanSignal continua sendo aceito (backward compat)."""
    from engine.init import _card_local_add_inline

    proj = tmp_path / "p"
    (proj / ".claude").mkdir(parents=True)

    orphan = OrphanSignal(
        signal_id="orphan:single-needle",
        source="detected in 1 file(s)",
        suggested_capability="kotlin-multiplatform",
        is_reserved=False,
        hit_count=1,
    )
    _card_local_add_inline(proj, orphan)

    card_yaml = (
        proj / ".claude" / "cards" / "local" / "kotlin-multiplatform" / "card.yaml"
    )
    assert card_yaml.is_file()


def test_three_paths_caminho_1_reserved_routes_to_adr(hilt_orphan, tmp_path):
    """Caminho 1 com reservada: NÃO cria local, oferece abrir ADR."""
    proj = tmp_path / "p"
    (proj / ".claude").mkdir(parents=True)
    with patch("engine.init.question.ask") as ask_mock:
        ask_mock.return_value = "1"
        decision = _surface_three_paths([hilt_orphan], project_root=proj)
    assert decision.choice == "adr-required"
    assert "hilt-di" in decision.note


def test_three_paths_caminho_2_writes_ignored_signals_yaml(rx_orphan, tmp_path):
    proj = tmp_path / "p"
    (proj / ".claude" / "inventory").mkdir(parents=True)
    with patch("engine.init.question.ask") as ask_mock:
        ask_mock.return_value = "2"
        decision = _surface_three_paths([rx_orphan], project_root=proj)
    assert decision.choice == "ignore"
    ignored_path = proj / ".claude" / "inventory" / "ignored-signals.yaml"
    assert ignored_path.is_file()
    parsed = yaml.safe_load(ignored_path.read_text(encoding="utf-8"))
    assert parsed.get("schema-version") == 1
    entries = parsed.get("ignored") or []
    assert any(e.get("signal_id") == "orphan:io.reactivex.rxjava3" for e in entries)


def test_three_paths_caminho_3_aborts_with_exit_8(rx_orphan, tmp_path):
    proj = tmp_path / "p"
    (proj / ".claude").mkdir(parents=True)
    with patch("engine.init.question.ask") as ask_mock:
        ask_mock.return_value = "3"
        decision = _surface_three_paths([rx_orphan], project_root=proj)
    assert decision.choice == "abort"
    assert decision.exit_code == 8


def test_three_paths_invalid_choice_reprompts_then_resolves(rx_orphan, tmp_path):
    proj = tmp_path / "p"
    (proj / ".claude" / "inventory").mkdir(parents=True)
    with patch("engine.init.question.ask") as ask_mock:
        # primeiro retorna escolha inválida, depois "2"
        ask_mock.side_effect = ["bogus", "2"]
        decision = _surface_three_paths([rx_orphan], project_root=proj)
    assert decision.choice == "ignore"
    assert ask_mock.call_count == 2


def test_three_paths_empty_orphan_list_is_no_op(tmp_path):
    proj = tmp_path / "p"
    (proj / ".claude").mkdir(parents=True)
    decision = _surface_three_paths([], project_root=proj)
    assert decision.choice == "noop"
