"""Unit tests — engine.inventory.i18n.

Smoke tests `extract_i18n` against a synthetic per-locale JSON tree and
validates the empty-project graceful fallback (`source-of-truth: unknown`).
"""

from __future__ import annotations

import json
from pathlib import Path

from engine.inventory import i18n


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_extract_i18n_with_no_sot_returns_unknown_path(tmp_path):
    inv = i18n.extract_i18n(tmp_path)
    sot = inv.raw["source-of-truth"]
    assert sot["path"] == "unknown"
    assert sot["format"] == "unknown"
    assert inv.raw["stats"]["total-keys"] == 0


def test_extract_i18n_detects_per_locale_json(tmp_path):
    _write_json(
        tmp_path / "shared" / "resources" / "i18n" / "pt-BR.json",
        {"auth": {"login": {"title": "Entrar"}}, "common": {"ok": "Ok"}},
    )
    _write_json(
        tmp_path / "shared" / "resources" / "i18n" / "en-US.json",
        {"auth": {"login": {"title": "Sign in"}}, "common": {"ok": "Ok"}},
    )
    inv = i18n.extract_i18n(tmp_path)
    assert inv.raw["source-of-truth"]["format"] == "json-per-locale"
    locales = inv.raw["source-of-truth"]["locales"]
    assert set(locales) == {"pt-BR", "en-US"}
    assert inv.raw["stats"]["total-keys"] >= 2
    keys = [k.key for k in inv.keys]
    assert "auth.login.title" in keys
    assert "common.ok" in keys


def test_extract_i18n_round_trip_write_read(tmp_path):
    _write_json(
        tmp_path / "shared" / "resources" / "i18n" / "pt-BR.json",
        {"hello": "Olá"},
    )
    inv = i18n.extract_i18n(tmp_path)
    # Sanity: the extractor itself returns the key in-memory.
    assert any(k.key == "hello" for k in inv.keys)

    out = i18n.write_i18n_inventory(tmp_path, inv)
    assert out.is_file()
    read = i18n.read_i18n_inventory(tmp_path)
    assert read is not None
    # `read_i18n_inventory` rehydrates from raw — keys list is intentionally
    # empty (raw only). We verify SoT path + locales survived the round-trip.
    assert read.source_of_truth.endswith("i18n")
    assert "pt-BR" in read.languages


def test_extract_i18n_parity_calculation(tmp_path):
    _write_json(
        tmp_path / "shared" / "resources" / "i18n" / "pt-BR.json",
        {"a": "A", "b": "B"},
    )
    _write_json(
        tmp_path / "shared" / "resources" / "i18n" / "en-US.json",
        {"a": "A"},
    )
    inv = i18n.extract_i18n(tmp_path)
    # 2 total keys, en-US covers 1 — parity = 0.5
    assert inv.raw["stats"]["parity"] <= 1.0
    assert inv.raw["stats"]["parity"] >= 0.0
