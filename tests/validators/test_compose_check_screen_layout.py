"""Tests for the `compose-screens` card validator `check-screen-layout.py` (P-24).

Script subprocess isolado, invocado como
`python3 <script> --project-root <path> [--scope <kind> --id <target>]`
com cwd=project_root.

Regra de detecção:
- "Diretório de tela" = dir sob escopo Compose (/androidApp/, /composeApp/src/)
  com ≥1 arquivo `{Screen}Screen.kt` (PascalCase).
- Cada `{Screen}Screen.kt` exige `{Screen}Content.kt` no MESMO dir, e vice-versa.
- `{Screen}Components.kt` / `{Screen}Mappers.kt` são opcionais.
- Agnóstico ao source set KMP, desde que dentro do escopo Compose.

Plan: docs/superpowers/plans/2026-06-19-pilot-r6-aifirst-blockers.md §C2
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "cards"
    / "compose-screens"
    / "validators"
    / "check-screen-layout.py"
)


def _run(project_root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--project-root", str(project_root), *extra],
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )


def _touch(path: Path, content: str = "// stub\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ── happy path ───────────────────────────────────────────────────────────────


def test_paired_screen_content_passes(tmp_path: Path) -> None:
    base = tmp_path / "androidApp/feature/home/ui/home"
    _touch(base / "HomeScreen.kt")
    _touch(base / "HomeContent.kt")
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr


# ── broken pairing ───────────────────────────────────────────────────────────


def test_screen_without_content_fails(tmp_path: Path) -> None:
    base = tmp_path / "androidApp/feature/home/ui/home"
    _touch(base / "HomeScreen.kt")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "missing HomeContent.kt" in result.stderr


def test_content_without_screen_fails(tmp_path: Path) -> None:
    base = tmp_path / "androidApp/feature/home/ui/home"
    _touch(base / "HomeContent.kt")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "missing HomeScreen.kt" in result.stderr


# ── optional siblings ────────────────────────────────────────────────────────


def test_optional_components_mappers_dont_break(tmp_path: Path) -> None:
    base = tmp_path / "androidApp/feature/home/ui/home"
    _touch(base / "HomeScreen.kt")
    _touch(base / "HomeContent.kt")
    _touch(base / "HomeComponents.kt")
    _touch(base / "HomeMappers.kt")
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr


# ── source-set agnostic ───────────────────────────────────────────────────────


def test_composeapp_source_set_scope(tmp_path: Path) -> None:
    base = tmp_path / "composeApp/src/commonMain/kotlin/feature/detail/detail"
    _touch(base / "DetailScreen.kt")
    _touch(base / "DetailContent.kt")
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr


# ── scope exclusion ──────────────────────────────────────────────────────────


def test_non_compose_dir_ignored(tmp_path: Path) -> None:
    _touch(tmp_path / "shared/domain/UseCase.kt")
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr


# ── invocation contract ──────────────────────────────────────────────────────


def test_tolerates_scope_and_id_flags(tmp_path: Path) -> None:
    base = tmp_path / "androidApp/feature/home/ui/home"
    _touch(base / "HomeScreen.kt")
    _touch(base / "HomeContent.kt")
    result = _run(tmp_path, "--scope", "feature", "--id", "home")
    assert result.returncode == 0, result.stderr


def test_empty_project_passes(tmp_path: Path) -> None:
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
