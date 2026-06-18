"""Atomic JSON read/write helpers.

Mirrors `engine.utils.yaml_io` for the JSON case used by the intent
protocol (`.claude/state/forge-pending.json` and
`.claude/state/forge-response.json`). Why a separate module:

- JSON and YAML use distinct serializers; one wrapper over both would
  obscure error context and force callers to think about format flags.
- Atomicity is a hard requirement of the intent protocol — no reader
  may ever observe a partial file mid-flush.
- ``json.dumps`` with ``ensure_ascii=False`` preserves the persona's
  Portuguese phrasing on disk (mentor-calmo voice survives the wire).

Atomic-write contract (same as ``yaml_io.write_yaml(atomic=True)``):
write to ``path.tmp`` then ``os.replace()`` it onto the target. This is
atomic on POSIX and Windows for same-filesystem renames. If the rename
raises, the temp file is unlinked so no dangling residue stays behind.

DRIFT-1 W1.T2 — foundation only. ``intent_state.py`` (W1.T3) and
``question.py`` (W2) consume this.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any


class JsonIOError(RuntimeError):
    """Raised when a JSON file cannot be parsed, with file context attached."""


def read_json(path: Path) -> Any:
    """Parse a JSON file. Returns the decoded object (dict/list/scalar).

    Raises ``FileNotFoundError`` when the file is missing (callers that
    want a soft check should use ``read_json_or_default``).

    Raises ``JsonIOError`` with the file path attached on parse failure
    so callers don't have to wrap.
    """
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as exc:
        raise JsonIOError(f"failed to parse JSON at {path}: {exc}") from exc


def read_json_or_default(path: Path, default: Any) -> Any:
    """Like ``read_json`` but returns ``default`` when the file is absent."""
    if not path.exists():
        return default
    return read_json(path)


def write_json(
    path: Path,
    data: Any,
    *,
    atomic: bool = True,
    indent: int = 2,
    mode: int = 0o600,
) -> None:
    """Write ``data`` to ``path`` as JSON.

    - ``atomic=True`` (default) writes to ``path.tmp`` then ``os.replace``
      onto the target. The replace is the atomic boundary.
    - ``indent=2`` (default) makes the file human-readable on disk; the
      intent protocol files are inspected by humans during debugging.
    - ``mode=0o600`` (default) restringe o arquivo a owner-read/write
      apenas. Os arquivos do intent protocol carregam input do usuário
      (potenciais paths e segredos) — o default conservador protege em
      ambientes multi-usuário. Em Windows ``os.chmod`` só ajusta o bit
      read-only; aceitamos o no-op silencioso (não é regressão).

    JSON style: ``ensure_ascii=False`` so Portuguese characters survive
    readable (no ``\\uXXXX`` escapes), ``sort_keys=False`` so the engine
    can preserve the canonical key order from the spec.

    Durabilidade: após ``os.replace`` o diretório pai é fsync-ado em
    POSIX para garantir que a entrada do novo inode chegue ao disco.
    Em filesystems exóticos (procfs, tmpfs de container) onde dir fsync
    não é suportado, engolimos o ``OSError`` em silêncio — o ``os.fsync``
    do próprio arquivo já feito acima cobre o caso comum.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    serialized = json.dumps(
        data,
        indent=indent,
        ensure_ascii=False,
        sort_keys=False,
    )

    if not atomic:
        with path.open("w", encoding="utf-8") as fh:
            fh.write(serialized)
        _apply_mode(path, mode)
        return

    # C4 CONC-1: tempfile por-processo. O nome fixo (path + ".tmp") fazia dois
    # processos forge no mesmo root colidirem no mesmo arquivo intermediário —
    # torn write OU FileNotFoundError no os.replace do escritor tardio. O sufixo
    # {pid}.{uuid} garante que cada escritor tenha seu próprio tmp; o os.replace
    # final continua sendo a fronteira atômica (last-writer-wins por syscall,
    # nunca conteúdo corrompido).
    tmp = path.with_suffix(f"{path.suffix}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(serialized)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        # Após o replace bem-sucedido: restringe permissões e fsync
        # do diretório pai para durar o rename atômico em POSIX.
        _apply_mode(path, mode)
        _fsync_parent_dir(path)
    finally:
        # Defensive: if rename failed, leave no dangling .tmp.
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _apply_mode(path: Path, mode: int) -> None:
    """Aplica ``mode`` em ``path``. Erros são re-empacotados como ``JsonIOError``.

    Em Windows ``os.chmod`` tem semântica limitada (só read-only bit),
    mas não levanta — o no-op silencioso é aceitável e documentado em
    ``write_json``.
    """
    try:
        os.chmod(path, mode)
    except OSError as exc:
        raise JsonIOError(
            f"could not restrict permissions on {path}: {exc}"
        ) from exc


def _fsync_parent_dir(path: Path) -> None:
    """Fsync no diretório pai para garantir durabilidade do rename atômico.

    POSIX-only: em Windows não há fd de diretório utilizável. Em
    filesystems exóticos onde o fsync de diretório não é suportado,
    engolimos ``OSError`` silenciosamente — o fsync do arquivo em si já
    foi feito antes do replace.
    """
    if sys.platform == "win32":
        return
    try:
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        # Filesystems sem suporte a dir fsync (procfs, alguns tmpfs):
        # tratamos como best-effort.
        pass
    finally:
        os.close(dir_fd)


def delete_if_exists(path: Path) -> bool:
    """Delete ``path`` if it exists. Idempotent.

    Returns True when the file was deleted, False when it was already
    absent. Never raises ``FileNotFoundError``.
    """
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
