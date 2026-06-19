"""C3 EXIT-2-COLLISION — contrato estrito de exit codes.

Contrato final:
  0   sucesso
  1   erro (com tag machine-readable [FORGE-ERR:<TAG>] em stderr)
  2   pausa aguardando input (SÓ PausedForInputError + UserPausedError)
  130 cancelamento (KeyboardInterrupt + UserCancelledError)
  127 editor-not-found (exceção POSIX documentada, só forge raw edit-config)

Este módulo prova que a escada legada (3/4/5/6/7/8 + not-a-project=2) colapsou
em 1 + tag, e que exit 2 ficou reservado pra pausa.
"""
from __future__ import annotations

import io

import pytest

from engine.ui import exit_codes


# (a) Helper fail_with_tag emite tag + retorna 1 -----------------------------


def test_fail_with_tag_writes_tag_and_returns_one():
    buf = io.StringIO()
    rc = exit_codes.fail_with_tag("LOCKED", "feature travada", stream=buf)
    assert rc == exit_codes.EXIT_ERROR == 1
    out = buf.getvalue()
    assert "[FORGE-ERR:LOCKED]" in out
    assert "feature travada" in out


def test_fail_with_tag_message_optional():
    buf = io.StringIO()
    rc = exit_codes.fail_with_tag("PROJECT-NOT-FOUND", stream=buf)
    assert rc == 1
    assert "[FORGE-ERR:PROJECT-NOT-FOUND]" in buf.getvalue()


@pytest.mark.parametrize(
    "tag",
    [
        "PROJECT-NOT-FOUND", "LOCKED", "FEATURE-MISSING", "NOT-READY",
        "WAVE-INCOMPLETE", "BLOCKED-EXTERNAL", "QA-BLOCK", "UPGRADE-FAILED",
        "USAGE", "ABORTED",
    ],
)
def test_all_canonical_tags_emit_consistently(tag):
    buf = io.StringIO()
    rc = exit_codes.fail_with_tag(tag, stream=buf)
    assert rc == 1
    assert f"[FORGE-ERR:{tag}]" in buf.getvalue()


# (b) Nenhum handler não-pausa retorna 2 (nem 3-8) ---------------------------


def _discover_handler_modules():
    """Descobre TODOS os handlers despachados a partir de ``engine.cli.COMMANDS``.

    Em vez de uma lista hardcoded (que escondeu o escape de ``undo.py`` —
    BL-01 do review W2), varremos o registry de dispatch real. Assim nenhum
    handler atual OU futuro escapa do contrato: registrou em ``COMMANDS`` →
    entra na varredura automaticamente.

    ``engine.cli`` é excluído do conjunto de varredura porque é o ÚNICO lugar
    onde ``return EXIT_PAUSED`` (== 2) é legítimo — é o chokepoint que ramifica
    o exit-code da pausa (``PausedForInputError`` / ``UserPausedError``). O
    wrapper ``qa`` aponta pra ``engine.cli:_qa_run``, então essa entrada também
    resolve pra ``cli.py`` e é deduplicada junto.

    Retorna lista de ``(rel_path, abs_path)`` ordenada e deduplicada por módulo.
    """
    import importlib
    from pathlib import Path

    from engine.cli import COMMANDS

    engine_root = Path(exit_codes.__file__).resolve().parent.parent
    cli_path = (engine_root / "cli.py").resolve()

    seen: set[Path] = set()
    discovered: list[tuple[str, Path]] = []
    for _cmd, (mod_path, _fn_name) in sorted(COMMANDS.items()):
        mod = importlib.import_module(mod_path)
        src = Path(mod.__file__).resolve()
        if src == cli_path:
            # engine.cli — pause-branch chokepoint, EXIT_PAUSED legítimo.
            continue
        if src in seen:
            continue
        seen.add(src)
        rel = src.relative_to(engine_root).as_posix()
        discovered.append((rel, src))
    return discovered


def test_no_handler_source_returns_bare_two_outside_pause():
    """Varredura estática AUTO-DESCOBERTA: nenhum handler despachado deve usar
    ``return 2`` / ``3`` / ... / ``8`` (nem ``sys.exit(N)`` / ``exit(N)`` no
    mesmo range) como código de erro. Erros colapsam em ``fail_with_tag`` (1 +
    tag). Exit 2 é reservado SÓ pra pausa, que vive em ``cli.py`` (excluído da
    varredura). Exit 127 (``raw edit-config``, editor-not-found) é exceção
    POSIX documentada e fica fora do range 2-8.

    A descoberta vem de ``engine.cli.COMMANDS`` (registry real de dispatch), de
    modo que qualquer handler NOVO entra no contrato sem editar este teste —
    fechando o buraco do BL-01 (lista hardcoded escondia ``undo.py``).
    """
    import re

    handlers = _discover_handler_modules()
    assert handlers, "auto-discovery não encontrou nenhum handler em COMMANDS"

    offenders: list[str] = []
    # ``return 2`` … ``return 8`` (numérico cru) OU ``sys.exit(2..8)`` /
    # ``exit(2..8)``. ``return EXIT_PAUSED`` simbólico nunca casa — só vive em
    # cli.py de qualquer forma. Linhas de comentário são puladas.
    bad_return = re.compile(r"\breturn\s+([2-8])\b")
    bad_exit = re.compile(r"\b(?:sys\.)?exit\(\s*([2-8])\s*\)")
    for rel, path in handlers:
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if bad_return.search(stripped) or bad_exit.search(stripped):
                offenders.append(f"{rel}:{lineno}: {stripped}")
    assert not offenders, (
        "exit-sites legados de erro ainda usam código numérico fora do "
        "contrato (return/exit 2-8) — devem usar fail_with_tag (1 + tag); "
        "exit 2 é reservado só pra pausa em cli.py:\n" + "\n".join(offenders)
    )


def test_error_handlers_have_no_bare_return_one():
    """C-23 (PR20-R2): nos handlers onde TODO error-path foi tagueado
    (raw/reconfigure/upgrade), nenhum ``return 1`` bare pode reaparecer —
    error sem tag é cego pro host/driver.

    Escopo restrito a esses 3 módulos (em vez de todos os handlers) porque
    outros têm ``return 1`` legítimos NÃO-erro (exit code de verify hard-fail,
    doctor unhealthy, etc.) que não carregam tag por design — o 1 ali É o
    veredito, não um erro de plumbing. Nos 3 módulos cobertos, todo ``return 1``
    era erro de plumbing e foi roteado via ``fail_with_tag``.
    """
    import re
    from pathlib import Path

    engine_root = Path(exit_codes.__file__).resolve().parent.parent
    bare_one = re.compile(r"^\s*return\s+1\s*$")
    offenders: list[str] = []
    for name in ("raw.py", "reconfigure.py", "upgrade.py"):
        path = engine_root / name
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            if bare_one.match(line):
                offenders.append(f"{name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "error-path com `return 1` bare (sem tag) reintroduzido — use "
        "fail_with_tag(ERR_*):\n" + "\n".join(offenders)
    )
