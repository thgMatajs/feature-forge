"""Unit tests — engine.utils.json_io.

Validates atomic JSON write semantics, read-or-default, and the
delete-if-exists helper. Models its shape on test_utils_yaml_io.py
because json_io mirrors the same atomic-write contract.

DRIFT-1 W1.T2 — foundation for the intent protocol state files
(forge-pending.json + forge-response.json).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.utils import json_io


def test_write_json_atomic_roundtrip(tmp_path):
    p = tmp_path / "out.json"
    json_io.write_json(p, {"a": 1, "b": [2, 3]})
    assert p.is_file()
    assert json.loads(p.read_text(encoding="utf-8")) == {"a": 1, "b": [2, 3]}
    # No leftover .tmp file.
    assert not (tmp_path / "out.json.tmp").exists()


def test_write_json_creates_parent_dirs(tmp_path):
    nested = tmp_path / "deep" / "nested" / "file.json"
    json_io.write_json(nested, {"k": "v"})
    assert nested.is_file()
    assert json.loads(nested.read_text(encoding="utf-8")) == {"k": "v"}


def test_write_json_preserves_insertion_order(tmp_path):
    p = tmp_path / "ordered.json"
    json_io.write_json(p, {"z": 1, "a": 2, "m": 3})
    text = p.read_text(encoding="utf-8")
    # Lines should appear in insertion order (sort_keys=False).
    assert text.index('"z"') < text.index('"a"') < text.index('"m"')


def test_write_json_unicode(tmp_path):
    """Non-ASCII content must round-trip without escaping (UTF-8 native)."""
    p = tmp_path / "u.json"
    payload = {"q": "Qual preset usar pra este projeto?", "v": "não"}
    json_io.write_json(p, payload)
    assert json.loads(p.read_text(encoding="utf-8")) == payload
    # Make sure ensure_ascii=False so PT chars survive readable on disk.
    raw = p.read_text(encoding="utf-8")
    assert "não" in raw


def test_write_json_atomic_writes_no_partial_on_failure(tmp_path, monkeypatch):
    """If os.replace fails mid-write, no .tmp residue should be left behind."""
    p = tmp_path / "atomic.json"
    p.write_text(json.dumps({"original": True}), encoding="utf-8")

    original_replace = json_io.os.replace

    def boom(src, dst):
        # Simulate a rename failure after the temp file has been written.
        raise OSError("simulated rename failure")

    monkeypatch.setattr(json_io.os, "replace", boom)
    with pytest.raises(OSError):
        json_io.write_json(p, {"new": True})

    # Original survives untouched.
    assert json.loads(p.read_text(encoding="utf-8")) == {"original": True}
    # No dangling .tmp.
    assert not (tmp_path / "atomic.json.tmp").exists()

    monkeypatch.setattr(json_io.os, "replace", original_replace)


def test_read_json_happy_path(tmp_path):
    p = tmp_path / "a.json"
    p.write_text('{"foo": "bar", "list": [1, 2]}', encoding="utf-8")
    data = json_io.read_json(p)
    assert data == {"foo": "bar", "list": [1, 2]}


def test_read_json_surfaces_error_with_path(tmp_path):
    p = tmp_path / "broken.json"
    p.write_text("{ not valid json", encoding="utf-8")
    with pytest.raises(json_io.JsonIOError) as exc:
        json_io.read_json(p)
    # Error message must include the path for forensic value.
    assert str(p) in str(exc.value)


def test_read_json_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        json_io.read_json(tmp_path / "nope.json")


def test_read_json_or_default_missing(tmp_path):
    sentinel = {"defaulted": True}
    result = json_io.read_json_or_default(tmp_path / "nope.json", sentinel)
    assert result is sentinel


def test_read_json_or_default_present(tmp_path):
    p = tmp_path / "present.json"
    p.write_text('{"k": "v"}', encoding="utf-8")
    sentinel = {"defaulted": True}
    assert json_io.read_json_or_default(p, sentinel) == {"k": "v"}


def test_delete_if_exists_removes(tmp_path):
    p = tmp_path / "doomed.json"
    p.write_text("{}", encoding="utf-8")
    assert json_io.delete_if_exists(p) is True
    assert not p.exists()


def test_delete_if_exists_silent_on_missing(tmp_path):
    p = tmp_path / "never.json"
    # Idempotent — no FileNotFoundError, just False.
    assert json_io.delete_if_exists(p) is False


def test_write_json_non_atomic(tmp_path):
    """atomic=False writes directly without the tempfile dance."""
    p = tmp_path / "direct.json"
    json_io.write_json(p, {"k": "v"}, atomic=False)
    assert json.loads(p.read_text(encoding="utf-8")) == {"k": "v"}
    assert not (tmp_path / "direct.json.tmp").exists()
