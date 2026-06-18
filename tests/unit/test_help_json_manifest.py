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
