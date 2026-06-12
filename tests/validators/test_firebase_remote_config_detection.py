"""Detection + schema tests for the ``firebase-remote-config`` card (DET-6 W4.5)."""

from __future__ import annotations

from pathlib import Path

import yaml

from engine.cards.loader import validate_card_yaml
from engine.detection._eval import _eval_detection_signals


REPO_ROOT = Path(__file__).resolve().parents[2]
CARD_DIR = REPO_ROOT / "cards" / "firebase-remote-config"
CARD_YAML = CARD_DIR / "card.yaml"


def _load_card() -> dict:
    return yaml.safe_load(CARD_YAML.read_text(encoding="utf-8"))


def _make_fixture(root: Path) -> Path:
    (root / "google-services.json").write_text(
        '{"project_info":{"project_id":"fixture-remote-config"}}\n', encoding="utf-8"
    )
    (root / "build.gradle").write_text(
        "dependencies {\n"
        "    implementation 'com.google.firebase:firebase-config:21.6.0'\n"
        "}\n",
        encoding="utf-8",
    )
    src = root / "app" / "src" / "main" / "java"
    src.mkdir(parents=True)
    (src / "FlagsBootstrap.kt").write_text(
        "package fixture.remoteconfig\n"
        "import com.google.firebase.remoteconfig.FirebaseRemoteConfig\n"
        "object FlagsBootstrap { fun init(rc: FirebaseRemoteConfig) = rc.fetchAndActivate() }\n",
        encoding="utf-8",
    )
    return root


def test_firebase_remote_config_card_yaml_passes_schema_validation() -> None:
    data = _load_card()
    violations = validate_card_yaml(data, CARD_DIR)
    assert violations == [], (
        "Esperado zero violations em firebase-remote-config/card.yaml, "
        f"mas surgiram: {violations}"
    )


def test_firebase_remote_config_detection_reaches_threshold_on_positive_fixture(
    tmp_path: Path,
) -> None:
    fixture = _make_fixture(tmp_path)
    data = _load_card()
    detection = data.get("detection") or {}
    score, matched = _eval_detection_signals(fixture, detection)
    threshold = float(detection.get("threshold") or 0.5)
    assert score >= threshold, (
        f"score {score} < threshold {threshold} no fixture remote-config. "
        f"matched={matched}"
    )
    assert matched
