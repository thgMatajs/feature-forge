"""Detection + schema tests for the ``firebase-analytics`` card (DET-6 W4.1).

Cobre:
  - ``card.yaml`` passa o validator CARD-001..019 (zero violations).
  - Um fixture project sintético construído via ``tmp_path`` casa pelo
    menos um sinal do bloco ``detection.signals`` e a confidence acumulada
    atinge o threshold do card.

Notas:
  - O sinal ``gradle-dep`` foi adicionado em W3 mas o evaluator runtime
    (``engine.init._eval_detection_signals``) ainda não o consome — chega
    em W5 (composer). Por enquanto a soma do score depende dos sinais
    ``file-content`` / ``file-exists`` cobertos pelo evaluator atual.
  - O card é ``category: analytics`` (backend-axis), então ``provides: []``
    é aceito por CARD-006 relax (W3).
  - O fixture é construído em ``tmp_path`` (não em ``tests/fixtures/``)
    para evitar que o ``_SKIP_DIRS`` do engine (que inclui ``.claude``)
    filtre arquivos quando os testes rodam dentro de uma worktree sob
    ``.claude/worktrees/``.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from engine.cards.loader import validate_card_yaml
from engine.detection._eval import _eval_detection_signals


REPO_ROOT = Path(__file__).resolve().parents[2]
CARD_DIR = REPO_ROOT / "cards" / "firebase-analytics"
CARD_YAML = CARD_DIR / "card.yaml"


def _load_card() -> dict:
    return yaml.safe_load(CARD_YAML.read_text(encoding="utf-8"))


def _make_fixture(root: Path) -> Path:
    """Construct a minimal Android-shaped project that triggers the card signals."""
    (root / "google-services.json").write_text(
        '{"project_info":{"project_id":"fixture-firebase-analytics"}}\n',
        encoding="utf-8",
    )
    (root / "build.gradle").write_text(
        "dependencies {\n"
        "    implementation 'com.google.firebase:firebase-analytics:21.5.0'\n"
        "}\n",
        encoding="utf-8",
    )
    src = root / "app" / "src" / "main" / "java"
    src.mkdir(parents=True)
    (src / "MainActivity.kt").write_text(
        "package fixture.firebaseanalytics\n"
        "import com.google.firebase.analytics.FirebaseAnalytics\n"
        "class MainActivity { private lateinit var a: FirebaseAnalytics }\n",
        encoding="utf-8",
    )
    return root


def test_firebase_analytics_card_yaml_passes_schema_validation() -> None:
    """CARD-001..019 limpo no card.yaml (zero violations)."""
    data = _load_card()
    violations = validate_card_yaml(data, CARD_DIR)
    assert violations == [], (
        "Esperado zero violations CARD-001..019 em firebase-analytics/card.yaml, "
        f"mas surgiram: {violations}"
    )


def test_firebase_analytics_detection_reaches_threshold_on_positive_fixture(
    tmp_path: Path,
) -> None:
    """Detection signals casam contra o fixture sintético e somam ≥ threshold."""
    fixture = _make_fixture(tmp_path)
    data = _load_card()
    detection = data.get("detection") or {}
    score, matched = _eval_detection_signals(fixture, detection)
    threshold = float(detection.get("threshold") or 0.5)
    assert score >= threshold, (
        f"Confidence acumulada {score} < threshold {threshold} no fixture "
        f"firebase-analytics-positive. Signals que casaram: {matched}"
    )
    assert matched, "Esperado pelo menos um signal casando no fixture."
