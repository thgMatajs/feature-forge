"""M-02 regression: unknown task dep must raise SystemExit, not silently skip."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from engine import implement


def test_topo_sort_raises_on_unknown_dep() -> None:
    """A dep pointing at a task that doesn't exist is a config error.

    Prior behavior emitted a yellow warning and treated the missing dep as
    satisfied, which let `forge implement` proceed with a broken DAG.
    The fix raises SystemExit so the contract author fixes the reference.
    """
    task_a = SimpleNamespace(
        task_id="TASK-0001",
        dependencies=["TASK-9999"],
        path=Path("/tmp/contract-a.yaml"),
    )

    with pytest.raises(SystemExit, match="TASK-9999"):
        implement._topo_sort([task_a])
