"""Schema bump 1 → "1.3" + module/class rename — Task 0.9 of v1.3 pilot-ready plan.

v1.3 (Decision 18 / spec §5 clean-break, pre-production) renamed the
artifact ``workflow-config.yaml`` → ``forge-config.yaml`` (sub-namespace
``.claude/forge/``). The validator module was renamed accordingly and
gained a ``ValidateForgeConfig`` class exposing the canonical schema
version constant for callers/tests/registry lookups.

This test pins the public surface so a future regression (accidental
revert, partial migration) is detected at import time.
"""

from __future__ import annotations

from validate_forge_config import ValidateForgeConfig


def test_expected_schema_version_is_1_3() -> None:
    """v1.3 introduces schema-version bump for forge-config.yaml."""
    assert ValidateForgeConfig.EXPECTED_SCHEMA_VERSION == "1.3"


def test_validator_class_name_is_forge_config() -> None:
    """Class renamed from ValidateWorkflowConfig (v1.2-) to ValidateForgeConfig (v1.3+)."""
    assert ValidateForgeConfig.__name__ == "ValidateForgeConfig"


def test_validator_module_path_is_forge_config() -> None:
    """Module renamed from validate_workflow_config.py to validate_forge_config.py.

    Validators are imported top-level via ``sys.path`` (see ``tests/conftest.py``
    insertion of ``validators/``), so ``__module__`` is the bare module name
    rather than the dotted package path.
    """
    assert ValidateForgeConfig.__module__ == "validate_forge_config"
