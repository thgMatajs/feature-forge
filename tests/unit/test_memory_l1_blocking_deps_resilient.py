"""Regression test for ``blocking_deps`` resilience to corrupt TASK YAMLs.

One malformed TASK-*.yaml in a feature's tasks/ directory must not kill
the whole scan — the function should log a warning and skip the bad
file, returning blocking deps from every other task that parsed fine.
See R2.3.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from engine.memory.l1 import blocking_deps


def _seed_feature(project_root: Path, slug: str) -> Path:
    """Create the feature layout that ``_feature_tasks_dir`` looks up.

    Mirrors the product-subtype path: ``docs/forge-specs/
    features/{slug}/tasks/``.
    """
    tasks = (
        project_root
        / "docs"
        / "forge-specs"
        / "features"
        / slug
        / "tasks"
    )
    tasks.mkdir(parents=True, exist_ok=True)
    return tasks


def _write_task(tasks_dir: Path, name: str, payload: dict) -> None:
    (tasks_dir / name).write_text(
        yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
    )


def test_blocking_deps_survives_corrupt_yaml(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One corrupt TASK-*.yaml should not abort the whole walk."""
    tasks = _seed_feature(tmp_path, "feature-x")

    # Healthy task with one blocking dep.
    _write_task(
        tasks,
        "TASK-0001.yaml",
        {
            "task_id": "TASK-0001",
            "depends_on_external": [
                {
                    "ticket": "JIRA-1",
                    "integration": "jira",
                    "description": "needs backend",
                    "blocking": True,
                }
            ],
        },
    )

    # Corrupt YAML — unclosed flow sequence, unbalanced indent.
    (tasks / "TASK-0002.yaml").write_text(
        "task_id: TASK-0002\ndepends_on_external:\n  - [JIRA-2: bad: [indent\n",
        encoding="utf-8",
    )

    # Another healthy task with one blocking dep.
    _write_task(
        tasks,
        "TASK-0003.yaml",
        {
            "task_id": "TASK-0003",
            "depends_on_external": [
                {
                    "ticket": "JIRA-3",
                    "integration": "jira",
                    "description": "needs design",
                    "blocking": True,
                }
            ],
        },
    )

    result = blocking_deps("feature-x", tmp_path)

    tickets = sorted(item["ticket"] for item in result)
    assert tickets == ["JIRA-1", "JIRA-3"], (
        f"corrupt task TASK-0002 should be skipped silently; got tickets={tickets}"
    )

    # R3.9: warning must mention the bad file AND convey a meaningful
    # "corrupt YAML" signal — not just an opaque mention of the task id.
    # Operators (and downstream tooling) need to know WHY the file was
    # skipped, otherwise the warning is just noise.
    captured = capsys.readouterr()
    combined = (captured.err or "") + (captured.out or "")
    assert re.search(
        r"TASK-0002.*(corrupt|failed|error|invalid|parse|unreadable)",
        combined,
        re.IGNORECASE | re.DOTALL,
    ), (
        "expected a meaningful corrupt-YAML warning mentioning TASK-0002 + "
        "a corruption keyword (corrupt/failed/error/invalid/parse/unreadable); "
        f"got err={captured.err!r}, out={captured.out!r}"
    )
