"""Unit tests pro modulo engine.qa.checkpoint (CONF-004).

Cobre write/read happy path, ausencia de arquivo, JSON malformado, shape
errado, e find_resumable_run com ordenacao e filtragem por verdict.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.qa.checkpoint import (
    Checkpoint,
    CheckpointCorruptError,
    find_resumable_run,
    read_checkpoint,
    write_checkpoint,
)


# ---------------------------------------------------------------------------
# write_checkpoint + read_checkpoint — happy path + atomicidade
# ---------------------------------------------------------------------------


def test_write_and_read_roundtrip(tmp_path: Path) -> None:
    """write_checkpoint -> read_checkpoint retorna Checkpoint equivalente."""
    run_root = tmp_path / "run-1"
    path = write_checkpoint(
        run_root,
        run_id="2026-06-08T10-00-00Z-abcd",
        scope_type="feature",
        scope_target="my-feature",
        last_phase_completed=3,
        findings_partial_count=2,
    )
    assert path == run_root / "checkpoint.json"
    assert path.exists()

    cp = read_checkpoint(run_root)
    assert cp is not None
    assert cp.run_id == "2026-06-08T10-00-00Z-abcd"
    assert cp.scope_type == "feature"
    assert cp.scope_target == "my-feature"
    assert cp.last_phase_completed == 3
    assert cp.findings_partial_count == 2
    # interrupted_at e gerado pelo write_checkpoint em UTC ISO-Z
    assert cp.interrupted_at.endswith("Z")


def test_write_checkpoint_creates_parent_dir(tmp_path: Path) -> None:
    """write_checkpoint cria dir pai se nao existe."""
    nested = tmp_path / "a" / "b" / "c"
    write_checkpoint(
        nested,
        run_id="r-1",
        scope_type="task",
        scope_target="TASK-0001",
        last_phase_completed=0,
    )
    assert (nested / "checkpoint.json").exists()


def test_write_checkpoint_does_not_leave_tmp(tmp_path: Path) -> None:
    """Apos write, nao existe .tmp dangling."""
    write_checkpoint(
        tmp_path,
        run_id="r-1",
        scope_type="screen",
        scope_target="home",
        last_phase_completed=4,
    )
    assert not (tmp_path / "checkpoint.json.tmp").exists()


def test_write_checkpoint_is_atomic_overwrite(tmp_path: Path) -> None:
    """Sobrescrever checkpoint nao corrompe (atomic os.replace)."""
    write_checkpoint(
        tmp_path,
        run_id="r-1",
        scope_type="feature",
        scope_target="f1",
        last_phase_completed=0,
    )
    write_checkpoint(
        tmp_path,
        run_id="r-1",
        scope_type="feature",
        scope_target="f1",
        last_phase_completed=4,
        findings_partial_count=5,
    )
    cp = read_checkpoint(tmp_path)
    assert cp is not None
    assert cp.last_phase_completed == 4
    assert cp.findings_partial_count == 5


# ---------------------------------------------------------------------------
# read_checkpoint — ausencia + corruption paths
# ---------------------------------------------------------------------------


def test_read_returns_none_when_absent(tmp_path: Path) -> None:
    """Sem arquivo -> retorna None silenciosamente."""
    assert read_checkpoint(tmp_path) is None


def test_read_raises_on_malformed_json(tmp_path: Path) -> None:
    """JSON quebrado -> CheckpointCorruptError com path + reason."""
    (tmp_path / "checkpoint.json").write_text("{ not valid", encoding="utf-8")
    with pytest.raises(CheckpointCorruptError) as exc_info:
        read_checkpoint(tmp_path)
    assert exc_info.value.path == tmp_path / "checkpoint.json"
    assert "JSON malformado" in exc_info.value.reason


def test_read_raises_when_top_level_not_dict(tmp_path: Path) -> None:
    """Top-level lista/scalar -> erro de shape."""
    (tmp_path / "checkpoint.json").write_text("[]", encoding="utf-8")
    with pytest.raises(CheckpointCorruptError) as exc_info:
        read_checkpoint(tmp_path)
    assert "dict" in exc_info.value.reason


def test_read_raises_when_required_field_missing(tmp_path: Path) -> None:
    """Campo obrigatorio faltando -> erro nomeando o campo."""
    payload = {
        "run_id": "r-1",
        "scope_type": "feature",
        # scope_target ausente
        "last_phase_completed": 0,
        "interrupted_at": "2026-06-08T10:00:00Z",
    }
    (tmp_path / "checkpoint.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    with pytest.raises(CheckpointCorruptError) as exc_info:
        read_checkpoint(tmp_path)
    assert "scope_target" in exc_info.value.reason


def test_read_raises_when_field_wrong_type(tmp_path: Path) -> None:
    """Campo com tipo errado -> erro nomeando tipo recebido."""
    payload = {
        "run_id": "r-1",
        "scope_type": "feature",
        "scope_target": "f1",
        "last_phase_completed": "three",  # str em vez de int
        "interrupted_at": "2026-06-08T10:00:00Z",
    }
    (tmp_path / "checkpoint.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    with pytest.raises(CheckpointCorruptError) as exc_info:
        read_checkpoint(tmp_path)
    assert "last_phase_completed" in exc_info.value.reason


def test_read_rejects_bool_as_int(tmp_path: Path) -> None:
    """bool (subclass de int) NAO conta como int valido."""
    payload = {
        "run_id": "r-1",
        "scope_type": "feature",
        "scope_target": "f1",
        "last_phase_completed": True,  # bool nao deve passar como int
        "interrupted_at": "2026-06-08T10:00:00Z",
    }
    (tmp_path / "checkpoint.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    with pytest.raises(CheckpointCorruptError):
        read_checkpoint(tmp_path)


def test_read_accepts_missing_findings_partial_count(tmp_path: Path) -> None:
    """findings_partial_count e opcional — default 0."""
    payload = {
        "run_id": "r-1",
        "scope_type": "feature",
        "scope_target": "f1",
        "last_phase_completed": 3,
        "interrupted_at": "2026-06-08T10:00:00Z",
        # findings_partial_count omitido
    }
    (tmp_path / "checkpoint.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    cp = read_checkpoint(tmp_path)
    assert cp is not None
    assert cp.findings_partial_count == 0


# ---------------------------------------------------------------------------
# find_resumable_run — discovery + filtragem
# ---------------------------------------------------------------------------


def _seed_run(
    project_root: Path,
    target: str,
    run_id: str,
    *,
    verdict: str = "pending",
    with_checkpoint: bool = True,
) -> Path:
    """Helper: cria .planning/qa/<target>/<run_id>/ com qa-report + opcional checkpoint."""
    run_dir = project_root / ".planning" / "qa" / target / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "qa-report.json").write_text(
        json.dumps({"verdict": verdict}), encoding="utf-8"
    )
    if with_checkpoint:
        (run_dir / "checkpoint.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "scope_type": "feature",
                    "scope_target": target,
                    "last_phase_completed": 3,
                    "interrupted_at": "2026-06-08T10:00:00Z",
                }
            ),
            encoding="utf-8",
        )
    return run_dir


def test_find_resumable_returns_none_when_no_dir(tmp_path: Path) -> None:
    """Sem .planning/qa/<target>/ -> None."""
    assert find_resumable_run(tmp_path, "feature", "missing") is None


def test_find_resumable_returns_none_when_no_checkpoint(tmp_path: Path) -> None:
    """Run dir sem checkpoint.json -> None."""
    _seed_run(tmp_path, "f1", "r-1", with_checkpoint=False)
    assert find_resumable_run(tmp_path, "feature", "f1") is None


def test_find_resumable_skips_completed_runs(tmp_path: Path) -> None:
    """Run com verdict != pending -> ignorada."""
    _seed_run(tmp_path, "f1", "r-1", verdict="PASS")
    _seed_run(tmp_path, "f1", "r-2", verdict="BLOCK")
    assert find_resumable_run(tmp_path, "feature", "f1") is None


def test_find_resumable_picks_most_recent(tmp_path: Path) -> None:
    """Multiplos pendings -> retorna o mais recente (sort lexicografico)."""
    _seed_run(tmp_path, "f1", "2026-06-07T10-00-00Z-aaaa")
    _seed_run(tmp_path, "f1", "2026-06-08T10-00-00Z-bbbb")
    _seed_run(tmp_path, "f1", "2026-06-08T09-00-00Z-cccc")
    result = find_resumable_run(tmp_path, "feature", "f1")
    assert result is not None
    assert result.name == "2026-06-08T10-00-00Z-bbbb"


def test_find_resumable_sanitizes_target(tmp_path: Path) -> None:
    """scope_target com chars invalidos sanitizado pra casar com dir real."""
    _seed_run(tmp_path, "weird_target", "r-1")
    # User passa target com chars que sao sanitizados pra "_"
    result = find_resumable_run(tmp_path, "feature", "weird/target")
    assert result is not None
    assert result.parent.name == "weird_target"


def test_find_resumable_handles_corrupt_qa_report(tmp_path: Path) -> None:
    """qa-report.json invalido -> dir nao considerado resumivel."""
    run_dir = tmp_path / ".planning" / "qa" / "f1" / "r-1"
    run_dir.mkdir(parents=True)
    (run_dir / "qa-report.json").write_text("{ broken", encoding="utf-8")
    (run_dir / "checkpoint.json").write_text("{}", encoding="utf-8")
    assert find_resumable_run(tmp_path, "feature", "f1") is None


def test_checkpoint_dataclass_is_frozen() -> None:
    """Checkpoint e dataclass frozen — assignment apos init explode."""
    cp = Checkpoint(
        run_id="r-1",
        scope_type="feature",
        scope_target="f1",
        last_phase_completed=0,
        interrupted_at="2026-06-08T10:00:00Z",
    )
    with pytest.raises((AttributeError, Exception)):
        cp.last_phase_completed = 3  # type: ignore[misc]
