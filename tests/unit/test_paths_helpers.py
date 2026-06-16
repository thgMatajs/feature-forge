from pathlib import Path
from engine.utils.paths import (
    forge_dir, forge_config_path, forge_state_dir,
    forge_cards_local_dir, forge_hooks_dir,
)


def test_forge_dir(tmp_path):
    assert forge_dir(tmp_path) == tmp_path / ".claude" / "forge"


def test_forge_config_path(tmp_path):
    assert forge_config_path(tmp_path) == tmp_path / ".claude" / "forge" / "forge-config.yaml"


def test_forge_state_dir(tmp_path):
    assert forge_state_dir(tmp_path) == tmp_path / ".claude" / "forge" / "state"


def test_forge_cards_local_dir(tmp_path):
    assert forge_cards_local_dir(tmp_path) == tmp_path / ".claude" / "forge" / "cards" / "local"


def test_forge_hooks_dir(tmp_path):
    assert forge_hooks_dir(tmp_path) == tmp_path / ".claude" / "forge" / "hooks"
