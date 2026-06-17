"""Codigos de saida canonicos — ``engine.ui.exit_codes`` (#27 PR #11).

O master-review do PR #11 (drift-1) marcou as constantes de exit code
como drift-prone. Este teste protege a fonte unica de verdade contra:

1. mudancas acidentais nos valores canonicos (0/1/2/130),
2. regressao no contrato exit-code do ``engine.cli.main`` (paused → 2,
   cancelled → 130) — confirmando que os caminhos drift-1 usam as
   constantes em vez de literais soltos.

O antigo ``engine.ui.tty_bridge`` (que duplicava ``_EXIT_PAUSED_FOR_INPUT``
/ ``_EXIT_USER_CANCELLED`` localmente) foi removido na Wave 2 — clean
break, superseded pelo TtyAdapter in-process que consome
``engine.ui.exit_codes`` diretamente. O teste que vigiava aquela
duplicacao saiu junto.

Refs:
- master-review PR #11 finding #27
- docs/superpowers/specs/drift-1-intent-protocol.md §8
"""
from __future__ import annotations

import engine.cli as cli_module
from engine.ui import exit_codes
from engine.ui.question import PausedForInputError, UserCancelledError


def _stub_handler(monkeypatch, handler):
    """Re-route ``cli._resolve`` so the test handler atende qualquer cmd."""
    monkeypatch.setattr(cli_module, "_resolve", lambda cmd: handler)


def test_exit_codes_values_canonical():
    """Os 4 codigos canonicos batem com o contrato SPEC §8.

    Mudar qualquer valor aqui exige revisita explicita do SPEC drift-1 +
    do bin/forge dispatcher, que mapeia o exit code do subprocess pra
    semantica visivel do usuario. Por isso o teste e literal — proteger
    contra "vou padronizar pra 64" tipo de drift silencioso.
    """
    assert exit_codes.EXIT_OK == 0
    assert exit_codes.EXIT_ERROR == 1
    assert exit_codes.EXIT_PAUSED == 2
    assert exit_codes.EXIT_CANCELLED == 130


def test_cli_main_uses_canonical_exit_paused(monkeypatch):
    """PausedForInputError no handler → ``main`` retorna ``EXIT_PAUSED``.

    Garante que o caminho drift-1 paused-for-input usa a constante
    canonica em vez de literal ``2`` — se alguem reintroduzir o literal
    e a constante mudar, este teste pega.
    """
    def handler(_argv):
        raise PausedForInputError(intent={"kind": "ask", "question": "stub"})

    _stub_handler(monkeypatch, handler)
    rc = cli_module.main(["plan"])
    assert rc == exit_codes.EXIT_PAUSED


def test_cli_main_uses_canonical_exit_cancelled(monkeypatch):
    """UserCancelledError no handler → ``main`` retorna ``EXIT_CANCELLED``.

    Idem ao paused: protege contra reintroducao de literal ``130`` solto.
    """
    def handler(_argv):
        raise UserCancelledError("cancelled")

    _stub_handler(monkeypatch, handler)
    rc = cli_module.main(["plan"])
    assert rc == exit_codes.EXIT_CANCELLED
