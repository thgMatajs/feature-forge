import json

from engine import cli


def test_help_json_emits_manifest(capsys, monkeypatch):
    monkeypatch.delenv("FORGE_OUTPUT", raising=False)
    code = cli.main(["--help", "--json"])
    out = capsys.readouterr().out
    manifest = json.loads(out)
    assert code == 0
    assert "forge_version" in manifest
    assert isinstance(manifest["commands"], list)
    names = {c["name"] for c in manifest["commands"]}
    # All visible commands present; hidden ingest absent.
    assert "status" in names and "plan" in names
    assert "ingest" not in names
    for cmd in manifest["commands"]:
        assert set(cmd) >= {"name", "summary", "interactive", "hidden", "flags", "args"}


def test_help_json_read_commands_advertise_json_flag(capsys, monkeypatch):
    monkeypatch.delenv("FORGE_OUTPUT", raising=False)
    cli.main(["--help", "--json"])
    manifest = json.loads(capsys.readouterr().out)
    by_name = {c["name"]: c for c in manifest["commands"]}
    assert "--json" in by_name["status"]["flags"]
    assert "--json" in by_name["doctor"]["flags"]
    assert by_name["plan"]["flags"] == []  # interactive → no meta-flags


def test_plain_help_still_prose(capsys, monkeypatch):
    monkeypatch.delenv("FORGE_OUTPUT", raising=False)
    cli.main(["--help"])  # no --json
    out = capsys.readouterr().out
    assert "Subcomandos" in out  # prose help unchanged


def test_command_meta_keys_match_visible_order():
    """W-001 drift guard: every visible command has hand-maintained metadata.

    ``_COMMAND_META`` is a parallel hand-written dict, NOT derived from
    ``COMMANDS``. The manifest iterates ``_VISIBLE_ORDER`` and looks each name
    up in ``_COMMAND_META``; a command added to ``_VISIBLE_ORDER``/``COMMANDS``
    without a metadata entry would silently emit ``summary=""``,
    ``interactive=True``, ``flags=[]``, ``args=[]`` — the manifest lying about
    the surface. This test fails the moment the two diverge.
    """
    assert set(cli._COMMAND_META) == set(cli._VISIBLE_ORDER)


def test_visible_order_subset_of_commands():
    """Every advertised command resolves to a real handler in COMMANDS."""
    assert set(cli._VISIBLE_ORDER) <= set(cli.COMMANDS)


def test_manifest_has_no_empty_summary():
    """No visible command ships an empty summary (would mean missing metadata)."""
    for name, meta in cli._COMMAND_META.items():
        assert meta.get("summary"), f"{name!r} has no summary in _COMMAND_META"
