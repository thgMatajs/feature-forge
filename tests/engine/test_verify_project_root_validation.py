"""H-10 regression: verify must validate project_root.is_dir() before subprocess.

Se ``project_root`` aponta para um caminho que NAO eh diretorio (arquivo
regular, simlink quebrado, path inexistente), ``_invoke_validator`` deve
retornar ``status="degraded"`` em vez de tentar invocar ``subprocess.run``
com ``cwd`` invalido. Isso evita NotADirectoryError opaco no caller +
fecha vetor onde caller poderia controlar project_root pra apontar pra
caminho arbitrario.
"""

from __future__ import annotations

from pathlib import Path

from engine.verify import _invoke_validator, _ValidatorSpec


def _make_spec(tmp_path: Path) -> _ValidatorSpec:
    """Synthetic spec com script valido (validation deve disparar ANTES do subprocess)."""
    script = tmp_path / "validator.py"
    script.write_text("import sys; sys.exit(0)", encoding="utf-8")
    return _ValidatorSpec(name="probe", script_path=script)


def test_invoke_validator_degraded_when_project_root_is_file(tmp_path: Path) -> None:
    """project_root apontando pra arquivo regular → degraded."""
    not_a_dir = tmp_path / "file.txt"
    not_a_dir.write_text("x", encoding="utf-8")

    spec = _make_spec(tmp_path)

    result = _invoke_validator(spec, project_root=not_a_dir)
    assert result.status == "degraded"
    assert "project_root" in result.message.lower()


def test_invoke_validator_degraded_when_project_root_missing(tmp_path: Path) -> None:
    """project_root inexistente → degraded (sem chegar no subprocess)."""
    missing = tmp_path / "does-not-exist"

    spec = _make_spec(tmp_path)

    result = _invoke_validator(spec, project_root=missing)
    assert result.status == "degraded"
    assert "project_root" in result.message.lower()


def test_invoke_validator_passes_through_when_project_root_is_dir(tmp_path: Path) -> None:
    """project_root valido → check passa, subprocess executa normalmente."""
    spec = _make_spec(tmp_path)

    result = _invoke_validator(spec, project_root=tmp_path)
    # Script exits 0 e nao emite JSON tail → "pass" pela exit-code contract.
    assert result.status == "pass"
