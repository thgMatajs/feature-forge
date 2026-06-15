"""H-02 regression: read_yaml must cap input size to prevent YAML bomb."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.utils.yaml_io import YamlIOError, read_yaml


def test_read_yaml_rejects_oversize_file(tmp_path: Path) -> None:
    """11MB YAML file → YamlIOError, no parse attempt."""
    big = tmp_path / "huge.yaml"
    # 11 MB of trivial YAML lines.
    payload = "k: v\n" * (11 * 1024 * 1024 // 5)
    big.write_text(payload, encoding="utf-8")

    with pytest.raises(YamlIOError, match="too large"):
        read_yaml(big)


def test_read_yaml_accepts_normal_file(tmp_path: Path) -> None:
    """Sanity: a small file still parses correctly post-cap."""
    small = tmp_path / "small.yaml"
    small.write_text("k: v\nlist:\n  - 1\n  - 2\n", encoding="utf-8")
    data = read_yaml(small)
    assert data == {"k": "v", "list": [1, 2]}
