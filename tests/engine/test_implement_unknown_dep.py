"""M-02 + A-008 regression: unknown task dep must raise TaskGraphError.

A-008 (master review PR #15): originalmente erro era `SystemExit` —
`BaseException`, não pegava em `except Exception` de chamadores defensivos.
Agora é `TaskGraphError(RuntimeError)`, domain exception mapeada para exit
code 1 pelo CLI `run()`.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from engine import implement


def test_topo_sort_raises_on_unknown_dep() -> None:
    """A dep pointing at a task that doesn't exist is a config error.

    Prior behavior emitted a yellow warning and treated the missing dep as
    satisfied, which let `forge implement` proceed with a broken DAG.
    The fix raises TaskGraphError so the contract author fixes the reference.
    """
    task_a = SimpleNamespace(
        task_id="TASK-0001",
        dependencies=["TASK-9999"],
        path=Path("/tmp/contract-a.yaml"),
    )

    with pytest.raises(implement.TaskGraphError, match="TASK-9999"):
        implement._topo_sort([task_a])
