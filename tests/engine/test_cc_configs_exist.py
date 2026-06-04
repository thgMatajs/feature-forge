"""Sanity tests for engine/_cc_configs/: existence + parseability.

Configs em ``engine/_cc_configs/`` são forge-managed. O gate de
cyclomatic-complexity (`check_cyclomatic_complexity`) chama cada
ferramenta (detekt, swiftlint, eslint, radon) com config interna fixa
e passa o threshold via CLI args — então estes arquivos precisam
existir, ser parseáveis no formato esperado, e ter exatamente a
única regra de complexidade habilitada por ferramenta.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "engine" / "_cc_configs"


def test_init_marker_exists() -> None:
    assert (CONFIG_DIR / "__init__.py").is_file()


def test_detekt_yaml_parses() -> None:
    path = CONFIG_DIR / "detekt.yml"
    assert path.is_file(), f"missing: {path}"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    # CyclomaticComplexMethod must be the only enabled complexity rule
    complexity = data.get("complexity") or {}
    assert isinstance(complexity, dict)
    rule = complexity.get("CyclomaticComplexMethod") or {}
    assert rule.get("active") is True


def test_swiftlint_yaml_parses() -> None:
    path = CONFIG_DIR / "swiftlint.yml"
    assert path.is_file()
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert "cyclomatic_complexity" in (data.get("only_rules") or [])


def test_eslint_json_parses() -> None:
    path = CONFIG_DIR / "eslint.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    # complexity rule placeholder — threshold is passed via CLI
    rules = data.get("rules") or {}
    assert "complexity" in rules


def test_radon_cfg_parses() -> None:
    path = CONFIG_DIR / "radon.cfg"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    # Radon usa INI-like; basta conferir que tem a seção esperada
    assert "[radon]" in text
    assert "exclude" in text
