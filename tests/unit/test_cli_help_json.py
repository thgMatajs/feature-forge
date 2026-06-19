"""test_cli_help_json.py — per-subcommand `--help --json` (P-05, pilot R1).

`forge <subcmd> --help --json` deve emitir o manifest JSON do subcomando
(slice de `_COMMAND_META`), NÃO a prosa do handler. Subcomando sem meta →
erro explícito em stderr + exit≠0, nunca silêncio.
"""

from __future__ import annotations

import contextlib
import io
import json

from engine.cli import main


def test_subcommand_help_json_emits_json() -> None:
    """forge init --help --json deve emitir JSON (não prosa) — P-05."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(["init", "--help", "--json"])
    out = buf.getvalue().strip()
    assert rc == 0
    parsed = json.loads(out)  # FALHA se for prosa (não-JSON)
    assert parsed.get("name") == "init"
    assert "summary" in parsed


def test_subcommand_help_json_unknown_meta_errors() -> None:
    """Subcomando sem meta + --help --json → erro explícito, não silêncio."""
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        rc = main(["nao-existe-este-comando", "--help", "--json"])
    assert rc != 0
    assert err_buf.getvalue().strip() != ""
