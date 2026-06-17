"""E2E — pytest wrapper para a bats suite de install.sh.

Invoca ``bats tests/e2e/test_install_sh.bats`` como subprocesso e
afirma returncode 0.

Skipped por default (requer ``RUN_E2E=1``). Se bats não estiver
instalado, também skipa graciosamente — o wrapper nunca falha por
ausência de bats.

Voz mentor calmo: o cenário aqui é "bats disponível → suite passa".
Ausência de bats é informada como skip, não como falha de configuração.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_RUN_E2E = os.environ.get("RUN_E2E") == "1"
_BATS_BIN = shutil.which("bats")

_BATS_SUITE = Path(__file__).parent / "test_install_sh.bats"


@pytest.mark.e2e
@pytest.mark.skipif(not _RUN_E2E, reason="set RUN_E2E=1 to run e2e tests")
@pytest.mark.skipif(_BATS_BIN is None, reason="bats não instalado — instale com 'brew install bats-core'")
def test_install_sh_bats_suite() -> None:
    """Executa a bats suite de install.sh e verifica que todos os testes passam.

    Cenários cobertos pela suite (veja test_install_sh.bats):
    - python3 < 3.11 aborta com mensagem de erro
    - python3 >= 3.11 passa verificação de pré-requisito
    - PATH detection zsh: adiciona linha no .zshrc quando ausente
    - PATH detection zsh: idempotência — re-run não duplica entrada
    - PATH já setado: pula edição do rc file
    - alias conflict: opção C aborta com exit 130
    - fish shell: _forge_setup_path usa fish_add_path
    """
    assert _BATS_BIN is not None  # já garantido pelo skipif acima
    assert _BATS_SUITE.is_file(), f"bats suite não encontrada: {_BATS_SUITE}"

    result = subprocess.run(
        [_BATS_BIN, str(_BATS_SUITE)],
        capture_output=False,  # exibe output diretamente para diagnóstico
        text=True,
    )

    assert result.returncode == 0, (
        f"bats suite falhou com exit {result.returncode}. "
        f"Rode manualmente para diagnóstico: bats {_BATS_SUITE}"
    )
