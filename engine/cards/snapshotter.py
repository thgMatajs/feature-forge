"""Card snapshotting — copy canonical cards into per-project `.claude/cards/`.

Each snapshot is a frozen copy of `~/Documents/feature-forge/cards/<name>/`
inside the project. `workflow-config.yaml cards.active.<name>.sha256` records
the integrity hash so `forge doctor` can detect tampering.

The directory hash is computed deterministically: every file under the
snapshot is hashed individually and the tuples `(rel_path, file_sha256)` are
sorted before being combined into one final sha256. This makes the hash
stable across runs and OSes regardless of `os.walk` order.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from ..utils.sha256 import file_sha256, string_sha256
from . import CardError


def snapshot_card(canonical_dir: Path, project_dir: Path) -> str:
    """Copy `canonical_dir` to `project_dir`. Returns the snapshot sha256.

    Atomic: se `copytree` falhar, o backup é restaurado e a exceção propagada.

    Behaviour:
    - Quando `project_dir` existe, ele é movido pra um backup timestamped
      (`<parent>/.<name>.bak.<epoch>`) antes do novo copy.
    - Em caso de falha do `copytree`, o backup é restaurado no lugar original e
      um `CardError` é levantado — o sistema NUNCA fica com diretório parcial.
    - Em sucesso, o backup é REMOVIDO (caller que quiser keep history usa
      `forge undo`/`forge doctor`).
    """
    if not canonical_dir.is_dir():
        raise CardError(f"canonical card directory not found: {canonical_dir}")

    project_dir.parent.mkdir(parents=True, exist_ok=True)

    backup_dir: Path | None = None
    if project_dir.exists():
        backup_dir = project_dir.parent / f".{project_dir.name}.bak.{int(time.time() * 1000)}"
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        shutil.move(str(project_dir), str(backup_dir))

    try:
        shutil.copytree(canonical_dir, project_dir, dirs_exist_ok=False)
    except Exception as exc:
        # Rollback: restaura o backup pra preservar atomicidade.
        if project_dir.exists():
            shutil.rmtree(project_dir, ignore_errors=True)
        if backup_dir is not None and backup_dir.exists():
            shutil.move(str(backup_dir), str(project_dir))
        raise CardError(
            f"snapshot falhou pra {canonical_dir.name}, estado original restaurado: {exc}"
        ) from exc

    # Sucesso: limpa backup (compat com semântica antiga de não acumular).
    if backup_dir is not None and backup_dir.exists():
        shutil.rmtree(backup_dir, ignore_errors=True)

    return compute_directory_sha256(project_dir)


def verify_snapshot_integrity(snapshot_dir: Path, expected_sha256: str) -> bool:
    """Re-hash `snapshot_dir` and compare to `expected_sha256`.

    Returns True if they match, False otherwise. Caller decides whether a
    mismatch is a warn or block (typically `forge doctor` decides).
    """
    if not snapshot_dir.is_dir():
        return False
    actual = compute_directory_sha256(snapshot_dir)
    return actual == expected_sha256


def compute_directory_sha256(directory: Path) -> str:
    """Deterministic sha256 of every file under `directory`.

    Algorithm:
        for each file (POSIX-relative path, sorted):
            entries.append(f"{rel_path}\\0{file_sha256}\\n")
        sha256("".join(entries))

    Symlinks, sockets, fifos are ignored — only regular files contribute.
    """
    if not directory.is_dir():
        raise CardError(f"not a directory: {directory}")

    entries: list[str] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(directory).as_posix()
        entries.append(f"{rel}\0{file_sha256(path)}\n")

    return string_sha256("".join(entries))


def remove_snapshot(snapshot_dir: Path) -> None:
    """Delete `snapshot_dir`. If it does not exist, this is a no-op.

    The caller is responsible for backing up first if needed; this function
    deliberately does NOT move to `.bak/` to keep `forge reconfigure remove`
    semantics clean. (Reconfigure's "remove card" flow does its own backup
    via `forge undo`.)
    """
    if not snapshot_dir.exists():
        return
    if not snapshot_dir.is_dir():
        raise CardError(f"refusing to remove non-directory snapshot: {snapshot_dir}")
    shutil.rmtree(snapshot_dir)
