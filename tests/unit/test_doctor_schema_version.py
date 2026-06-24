"""Doctor `schema-version` acceptance — RULE-001 `[1, 1.3]`.

Regression: piloting `forge qa` against the MeoBonsai-qa consumer surfaced
that `_check_config` only accepted `schema-version == 1`, hard-failing every
freshly-init'd consumer (init writes `schema-version: "1.3"`). RULE-001 in
`docs/schemas/forge-config.md` documents the accepted set as `[1, 1.3]`;
doctor must mirror it. A valid current config MUST pass; only a genuinely
unknown version warns (doctor can't migrate, but doesn't hard-fail a config
it merely doesn't recognize).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import doctor
from engine.doctor import _STATUS_FAIL, _STATUS_OK, _STATUS_WARN, _check_config


def _config_path(tmp_path: Path) -> Path:
    # _check_config only requires the path to be an existing file; the parsed
    # `config` dict is passed separately.
    p = tmp_path / "forge-config.yaml"
    p.write_text("schema-version: 1\n", encoding="utf-8")
    return p


def _schema_check(report) -> doctor._Check:
    for check in report.checks:
        if check.name == "schema-version":
            return check
    raise AssertionError("schema-version check not emitted")


@pytest.mark.parametrize("value", [1, "1", 1.3, "1.3"])
def test_documented_schema_versions_pass(tmp_path: Path, value) -> None:
    """RULE-001 `[1, 1.3]` — every documented form is OK, not a fail."""
    cfg_path = _config_path(tmp_path)
    config = {"schema-version": value, "identity": {"project-slug": "demo"}}
    report = _check_config(tmp_path, cfg_path, config)
    check = _schema_check(report)
    assert check.status == _STATUS_OK, f"{value!r} should pass RULE-001"


@pytest.mark.parametrize("value", [2, "9.9", 0, "abc", None])
def test_unknown_schema_version_warns_not_fails(tmp_path: Path, value) -> None:
    """Unknown version → WARN (doctor can't migrate), never a hard FAIL."""
    cfg_path = _config_path(tmp_path)
    config = {"schema-version": value, "identity": {"project-slug": "demo"}}
    report = _check_config(tmp_path, cfg_path, config)
    check = _schema_check(report)
    assert check.status == _STATUS_WARN, f"{value!r} should warn, got {check.status}"
    assert check.status != _STATUS_FAIL
