"""BUG-B (T6): round-trip init→doctor lê o version-lock no MESMO path.

Regressão: o init grava o lock em ``.claude/forge/forge-version-lock.yaml``
(``forge_dir``) mas o doctor lia em ``.claude/forge-version-lock.yaml``
(``claude_dir``) — o check caía sempre no SKIP falso "não criado ainda" e a
detecção lock-vs-binário ficava morta.
"""

from __future__ import annotations

from pathlib import Path

from engine import __version__ as FORGE_VERSION
from engine.doctor import _check_forge_version_lock, _STATUS_OK, _STATUS_FAIL, _STATUS_SKIP
from engine.utils.paths import forge_dir
from engine.utils.yaml_io import write_yaml


def _write_lock(project_root: Path, version: str) -> None:
    """Escreve o version-lock no path canônico do init (``forge_dir``)."""
    lock_path = forge_dir(project_root) / "forge-version-lock.yaml"
    write_yaml(
        lock_path,
        {
            "schema-version": 1,
            "forge-version": version,
            "locked-at": "2026-06-29T00:00:00Z",
            "project": project_root.name,
        },
        atomic=True,
    )


def test_init_doctor_version_lock_roundtrip(tmp_project_root: Path) -> None:
    """Lock gravado pelo init é LIDO pelo doctor (check vivo = OK quando casam)."""
    _write_lock(tmp_project_root, FORGE_VERSION)

    report = _check_forge_version_lock(tmp_project_root)
    statuses = {c.status for c in report.checks}

    assert _STATUS_SKIP not in statuses, (
        "doctor reportou SKIP falso 'não criado ainda' com o lock existindo no "
        "path do init — path mismatch (BUG-B) não corrigido"
    )
    assert _STATUS_OK in statuses, "lock casando com o binário deveria reportar OK"


def test_doctor_version_lock_detects_drift(tmp_project_root: Path) -> None:
    """Lock com versão divergente do binário → FAIL (check vivo, não SKIP)."""
    _write_lock(tmp_project_root, "0.0.0-drift")

    report = _check_forge_version_lock(tmp_project_root)
    statuses = {c.status for c in report.checks}

    assert _STATUS_SKIP not in statuses
    assert _STATUS_FAIL in statuses, "drift lock-vs-binário deveria reportar FAIL"
