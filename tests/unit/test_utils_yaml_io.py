"""Unit tests — engine.utils.yaml_io.

Validates read/write roundtrip, error context on bad YAML, atomic write
semantics, and the backup_file helper.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from engine.utils import yaml_io


def test_read_yaml_happy_path(tmp_path):
    p = tmp_path / "a.yaml"
    p.write_text("foo: bar\nlist:\n  - 1\n  - 2\n", encoding="utf-8")
    data = yaml_io.read_yaml(p)
    assert data == {"foo": "bar", "list": [1, 2]}


def test_read_yaml_surfaces_error_with_path(tmp_path):
    p = tmp_path / "broken.yaml"
    p.write_text("foo: : bar\n  bad: [unclosed\n", encoding="utf-8")
    with pytest.raises(yaml_io.YamlIOError) as exc:
        yaml_io.read_yaml(p)
    assert str(p) in str(exc.value)


def test_read_yaml_or_default(tmp_path):
    missing = tmp_path / "nope.yaml"
    sentinel = {"defaulted": True}
    assert yaml_io.read_yaml_or_default(missing, sentinel) is sentinel

    p = tmp_path / "present.yaml"
    p.write_text("k: v\n", encoding="utf-8")
    assert yaml_io.read_yaml_or_default(p, sentinel) == {"k": "v"}


def test_write_yaml_atomic_roundtrip(tmp_path):
    p = tmp_path / "out.yaml"
    yaml_io.write_yaml(p, {"a": 1, "b": [2, 3]})
    assert p.is_file()
    assert yaml.safe_load(p.read_text(encoding="utf-8")) == {"a": 1, "b": [2, 3]}
    # No leftover .tmp file.
    assert not (tmp_path / "out.yaml.tmp").exists()


def test_write_yaml_creates_parent_dirs(tmp_path):
    nested = tmp_path / "deep" / "nested" / "file.yaml"
    yaml_io.write_yaml(nested, {"k": "v"})
    assert nested.is_file()


def test_write_yaml_preserves_insertion_order(tmp_path):
    p = tmp_path / "ordered.yaml"
    yaml_io.write_yaml(p, {"z": 1, "a": 2, "m": 3})
    text = p.read_text(encoding="utf-8")
    # Lines should appear in insertion order (sort_keys=False).
    assert text.index("z:") < text.index("a:") < text.index("m:")


def test_backup_file_creates_bak_sibling(tmp_path):
    src = tmp_path / "src.yaml"
    src.write_text("k: v\n", encoding="utf-8")
    bak = yaml_io.backup_file(src)
    assert bak == src.with_suffix(".yaml.bak")
    assert bak.is_file()
    assert bak.read_text(encoding="utf-8") == "k: v\n"


def test_backup_file_no_source_returns_none(tmp_path):
    assert yaml_io.backup_file(tmp_path / "nope.yaml") is None


def test_write_yaml_with_backup_makes_bak(tmp_path):
    p = tmp_path / "doc.yaml"
    p.write_text("v: 1\n", encoding="utf-8")
    yaml_io.write_yaml(p, {"v": 2}, backup=True)
    assert (tmp_path / "doc.yaml.bak").is_file()
    bak_text = (tmp_path / "doc.yaml.bak").read_text(encoding="utf-8")
    assert "v: 1" in bak_text
    assert yaml.safe_load(p.read_text(encoding="utf-8")) == {"v": 2}


def test_bak_age_days_returns_float(tmp_path):
    bak = tmp_path / "f.yaml.bak"
    bak.write_text("x", encoding="utf-8")
    age = yaml_io.bak_age_days(bak)
    assert isinstance(age, float)
    assert age >= 0.0
