"""Detection + schema tests for the ``posthog-analytics`` card (DET-6 W4.2).

Espelho do test do ``firebase-analytics`` (W4.1) — mesmas convenções:
fixture em ``tmp_path`` para evitar o ``.claude`` em ``_SKIP_DIRS`` quando
testes rodam dentro de uma worktree.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from engine.cards.loader import validate_card_yaml
from engine.init import _eval_detection_signals


REPO_ROOT = Path(__file__).resolve().parents[2]
CARD_DIR = REPO_ROOT / "cards" / "posthog-analytics"
CARD_YAML = CARD_DIR / "card.yaml"


def _load_card() -> dict:
    return yaml.safe_load(CARD_YAML.read_text(encoding="utf-8"))


def _make_fixture(root: Path) -> Path:
    (root / "build.gradle").write_text(
        "dependencies {\n"
        "    implementation 'com.posthog:posthog-android:3.4.0'\n"
        "}\n",
        encoding="utf-8",
    )
    src = root / "app" / "src" / "main" / "java"
    src.mkdir(parents=True)
    (src / "AnalyticsBootstrap.kt").write_text(
        "package fixture.posthog\n"
        "import com.posthog.android.PostHog\n"
        "object AnalyticsBootstrap { fun init() = PostHog.with(/* ctx */) }\n",
        encoding="utf-8",
    )
    return root


def test_posthog_analytics_card_yaml_passes_schema_validation() -> None:
    data = _load_card()
    violations = validate_card_yaml(data, CARD_DIR)
    assert violations == [], (
        "Esperado zero violations em posthog-analytics/card.yaml, "
        f"mas surgiram: {violations}"
    )


def test_posthog_analytics_detection_reaches_threshold_on_positive_fixture(
    tmp_path: Path,
) -> None:
    fixture = _make_fixture(tmp_path)
    data = _load_card()
    detection = data.get("detection") or {}
    score, matched = _eval_detection_signals(fixture, detection)
    threshold = float(detection.get("threshold") or 0.5)
    assert score >= threshold, (
        f"score {score} < threshold {threshold} no fixture posthog-analytics. "
        f"matched={matched}"
    )
    assert matched
