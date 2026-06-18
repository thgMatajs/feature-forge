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


# (b) Nenhum handler não-pausa retorna 2 -------------------------------------


def test_no_handler_source_returns_bare_two_outside_pause():
    """Varredura estática: fora de cli.py (onde EXIT_PAUSED=2 é legítimo) e de
    raw.py:111 (127), nenhum exit-site dos handlers deve usar `return 2`/`3`/
    `4`/`5`/`6`/`7`/`8` como código de erro. Eles devem usar fail_with_tag.
    """
    import re
    from pathlib import Path

    engine_root = Path(exit_codes.__file__).resolve().parent.parent
    handlers = [
        "plan.py", "implement.py", "verify.py", "upgrade.py", "evolve.py",
        "raw.py", "init.py", "qa/__init__.py",
    ]
    offenders: list[str] = []
    bad_return = re.compile(r"return\s+([2345678])\b")
    for rel in handlers:
        path = engine_root / rel
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            m = bad_return.search(stripped)
            if m:
                offenders.append(f"{rel}:{lineno}: {stripped}")
    assert not offenders, (
        "exit-sites legados de erro ainda usam return N numérico — devem usar "
        "fail_with_tag:\n" + "\n".join(offenders)
    )
