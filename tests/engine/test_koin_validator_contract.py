"""BUG-VERIFY-1 (parte T2, Onda 1): o validator ``check-koin-modules.py`` do
card koin-annotations deve falar o contrato canônico de validator.

O ``forge verify`` invoca todo validator com::

    <script> --project-root <root> [--scope <kind>] [--id <target>]

(ver ``engine.verify._invoke_validator``). O koin só aceitava ``--root``;
invocado com os flags canônicos estourava argparse → exit 2 → (antes do fix
T1) era classificado ``fail`` e cegava a cascade.

Estes testes invocam o script COMO O VERIFY INVOCA (subprocess, flags
canônicos) e provam:
  - aceita ``--project-root``/``--scope``/``--id`` sem estourar argparse;
  - num projeto limpo (sem violação) sai 0;
  - num projeto com violação real (@Module sem @ComponentScan) sai != 0
    (comportamento de detecção preservado pela mudança de contrato).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_VALIDATOR = (
    Path(__file__).resolve().parents[2]
    / "cards"
    / "koin-annotations"
    / "validators"
    / "check-koin-modules.py"
)


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_VALIDATOR), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_koin_validator_accepts_canonical_contract(tmp_path: Path) -> None:
    """--project-root/--scope/--id não estouram argparse (exit != 2).

    Reproduz BUG-VERIFY-1 vermelho: com o contrato antigo (--root only) este
    invoke caía em "unrecognized arguments" → exit 2.
    """
    proc = _run(
        ["--project-root", str(tmp_path), "--scope", "feature", "--id", "demo"],
        cwd=tmp_path,
    )
    assert proc.returncode != 2, (
        "validator estourou argparse (exit 2) com os flags canônicos — "
        f"contrato off. stderr={proc.stderr!r}"
    )


def test_koin_validator_clean_project_exits_zero(tmp_path: Path) -> None:
    """Projeto sem .kt → nenhuma violação → exit 0 (pass pela exit-code contract)."""
    proc = _run(
        ["--project-root", str(tmp_path), "--scope", "feature", "--id", "demo"],
        cwd=tmp_path,
    )
    assert proc.returncode == 0, f"stderr={proc.stderr!r}"


def test_koin_validator_detects_module_without_componentscan(tmp_path: Path) -> None:
    """Comportamento de detecção preservado: @Module sem @ComponentScan → falha.

    Garante que a mudança de contrato (--root → --project-root) não esvaziou a
    checagem real do validator.
    """
    src = tmp_path / "src" / "commonMain" / "kotlin"
    src.mkdir(parents=True)
    (src / "AppModule.kt").write_text(
        "@Module\nclass AppModule\n", encoding="utf-8"
    )
    proc = _run(
        ["--project-root", str(tmp_path), "--scope", "feature", "--id", "demo"],
        cwd=tmp_path,
    )
    assert proc.returncode != 0, (
        "@Module sem @ComponentScan deveria reprovar — detecção esvaziada?"
    )
    assert proc.returncode != 2, (
        "deveria reprovar via veredito (não argparse error); "
        f"stderr={proc.stderr!r}"
    )


def test_koin_validator_dsl_check_still_available(tmp_path: Path) -> None:
    """O flag específico do card (--dsl-check) continua funcionando ao lado do
    contrato canônico (extra-arg, não conflita com --project-root/--scope/--id).
    """
    src = tmp_path / "src" / "commonMain" / "kotlin"
    src.mkdir(parents=True)
    (src / "BadModule.kt").write_text(
        "val x = module {\n}\n", encoding="utf-8"
    )
    proc = _run(
        [
            "--project-root",
            str(tmp_path),
            "--scope",
            "feature",
            "--id",
            "demo",
            "--dsl-check",
        ],
        cwd=tmp_path,
    )
    assert proc.returncode != 2, f"argparse error com --dsl-check: {proc.stderr!r}"
    assert proc.returncode != 0, (
        "DSL `module { }` em produção deveria reprovar com --dsl-check"
    )
