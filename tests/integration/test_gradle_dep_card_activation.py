"""Integration: ativação real de cards via gradle-dep + file-content signals.

Carrega os cards REAIS do diretório `cards/` (via `engine.cards.loader.load_card`)
e roda `_eval_detection_signals` contra as fixtures REAIS em `tests/fixtures/`,
cobrindo AC-1..AC-6 do SPEC `docs/superpowers/specs/det-3-gradle-dep-signal.md`.

Justificativa (review master PR #11 finding A-2): a suite unit em
`tests/unit/test_eval_gradle_dep.py` exercita apenas o helper isolado
(_eval_gradle_dep / _eval_detection_signals com detection inline). O card
real — incluindo o threshold canônico e o conjunto completo de signals — só
é exercitado end-to-end aqui. Sem este nível, fix em A-1 (promoção do
gradle-dep a confidence 0.5 em ktor-client) ficaria sem regression test
permanente.
"""

from pathlib import Path

import pytest

from engine.cards.loader import load_card
from engine.init import _eval_detection_signals

REPO_ROOT = Path(__file__).resolve().parents[2]
CARDS_DIR = REPO_ROOT / "cards"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"


def _activate(card_name: str, fixture_name: str) -> tuple[float, float, list[str]]:
    """Carrega card real, roda detection real, retorna (score, threshold, matched).

    Devolve threshold pra o teste asserir ativação relativa ao próprio card —
    nunca hard-coda 0.5 (cards podem mudar threshold no futuro sem invalidar
    a semântica do AC).
    """
    card = load_card(CARDS_DIR / card_name)
    detection = card.detection or {}
    threshold = float(detection.get("threshold") or 0.0)
    score, matched = _eval_detection_signals(FIXTURES_DIR / fixture_name, detection)
    return score, threshold, matched


# ── AC-1 ────────────────────────────────────────────────────────────────────
@pytest.mark.integration
def test_ac1_ktor_client_activates_in_toml_only_fixture() -> None:
    """AC-1: TOML-only puro (libs.versions.toml com `module = ...`) ativa ktor-client.

    Regression de A-1 do master review PR #11: antes do fix, gradle-dep
    estava em confidence 0.2 e o score (0.2) não atingia threshold 0.5 —
    o card ficava abaixo do threshold mesmo com a coordenada declarada.
    """
    score, threshold, matched = _activate("ktor-client", "gradle-dep-toml-only")
    assert score >= threshold, (
        f"ktor-client should activate in toml-only fixture: "
        f"got score={score:.3f}, threshold={threshold:.3f}, matched={matched}"
    )
    assert any("gradle-dep" in m for m in matched), (
        f"expected gradle-dep signal match, got matched={matched}"
    )


# ── AC-2 ────────────────────────────────────────────────────────────────────
@pytest.mark.integration
def test_ac2_ktor_client_activates_in_toml_split_fixture() -> None:
    """AC-2: TOML com `group + name` separados (em vez de `module = ...`) ativa.

    Cobre a outra sintaxe TOML canônica do Gradle Version Catalog. O parser
    de gradle-dep precisa entender ambos os formatos pra prometer cobertura
    completa do ecossistema Gradle moderno.
    """
    score, threshold, matched = _activate("ktor-client", "gradle-dep-toml-split")
    assert score >= threshold, (
        f"ktor-client should activate in toml-split fixture: "
        f"got score={score:.3f}, threshold={threshold:.3f}, matched={matched}"
    )
    assert any("gradle-dep" in m for m in matched), (
        f"expected gradle-dep signal match (group+name form), got matched={matched}"
    )


# ── AC-3 ────────────────────────────────────────────────────────────────────
@pytest.mark.integration
def test_ac3_ktor_client_activates_in_legacy_fixture() -> None:
    """AC-3: build.gradle.kts legacy (sem TOML) ativa via literal Maven string.

    Setups antigos sem Version Catalog declaram `implementation("group:name:ver")`
    direto no build script. O signal gradle-dep precisa parsear isso também.
    """
    score, threshold, matched = _activate("ktor-client", "gradle-dep-legacy")
    assert score >= threshold, (
        f"ktor-client should activate in legacy fixture: "
        f"got score={score:.3f}, threshold={threshold:.3f}, matched={matched}"
    )
    assert any("gradle-dep" in m for m in matched), (
        f"expected gradle-dep signal match (build.gradle.kts literal), got matched={matched}"
    )


# ── AC-4 ────────────────────────────────────────────────────────────────────
@pytest.mark.integration
def test_ac4_ktor_client_no_double_counting_in_hybrid_fixture() -> None:
    """AC-4: hybrid (TOML + build.gradle.kts declaram a MESMA dep) sem double-count.

    Critical: o signal gradle-dep deve casar a coordenada uma única vez,
    mesmo quando aparece em ambas as fontes. Soma teórica das confidences
    do card ktor-client > 1.0; verificamos que o score real respeita
    score ≤ 1.0 (sanity CARD-016; fixture-specific ceiling, CARD-016 hard ceiling is 2.0) — confirma que gradle-dep curto-circuita
    quando já casou.
    """
    score, threshold, matched = _activate("ktor-client", "gradle-dep-hybrid")
    assert score >= threshold, (
        f"ktor-client should activate in hybrid fixture: "
        f"got score={score:.3f}, threshold={threshold:.3f}, matched={matched}"
    )
    # Conta quantas vezes gradle-dep aparece em matched (deve ser 1, nunca 2).
    gradle_dep_hits = sum(1 for m in matched if m.startswith("gradle-dep"))
    assert gradle_dep_hits == 1, (
        f"gradle-dep signal should match exactly once even when coordinate "
        f"exists in both TOML and build.gradle (no double count): "
        f"got gradle_dep_hits={gradle_dep_hits}, matched={matched}"
    )
    assert score <= 1.0, (
        f"score should not exceed sanity ceiling 1.0 in hybrid fixture: "
        f"got score={score:.3f}, matched={matched}"
    )


# ── AC-5 ────────────────────────────────────────────────────────────────────
@pytest.mark.integration
def test_ac5_ktor_client_does_not_activate_in_negative_fixture() -> None:
    """AC-5: fixture sem nenhuma dep ktor não ativa o card (negative case).

    Garante que a detecção é específica — só ativa quando a coordenada
    canônica está realmente declarada.
    """
    score, threshold, matched = _activate("ktor-client", "gradle-dep-negative")
    assert score < threshold, (
        f"ktor-client should NOT activate in negative fixture: "
        f"got score={score:.3f}, threshold={threshold:.3f}, matched={matched}"
    )
    assert not matched, (
        f"no signals should match in negative fixture, got matched={matched}"
    )


# ── AC-6 ────────────────────────────────────────────────────────────────────
@pytest.mark.integration
def test_ac6_file_content_signal_still_active_alongside_gradle_dep() -> None:
    """AC-6: file-content signals continuam funcionando após introdução do gradle-dep.

    Card ktor-client preserva 3 signals file-content (build.gradle*, HttpClient(,
    io.ktor.client) ao lado do gradle-dep novo. Fixture
    `gradle-dep-file-content-preserved` contém apenas um arquivo .kt — o card
    deve ativar exclusivamente via os signals file-content preservados,
    provando que a migração para gradle-dep não regrediu o caminho legacy.
    """
    score, threshold, matched = _activate(
        "ktor-client", "gradle-dep-file-content-preserved"
    )
    assert score >= threshold, (
        f"ktor-client should activate via preserved file-content signals: "
        f"got score={score:.3f}, threshold={threshold:.3f}, matched={matched}"
    )
    # Match deve vir de file-content, não de gradle-dep (não há build files).
    assert any("file-content" in m for m in matched), (
        f"expected file-content signal match in this fixture, got matched={matched}"
    )
    assert not any(m.startswith("gradle-dep") for m in matched), (
        f"gradle-dep should NOT match (no build files in fixture): "
        f"got matched={matched}"
    )
