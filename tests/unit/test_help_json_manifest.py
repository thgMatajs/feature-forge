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


def test_manifest_prompts_by_default_is_truthful(capsys, monkeypatch):
    """C-37 (PR21-I4): `prompts_by_default` reflete o comportamento REAL.

    O campo `interactive` antigo mentia — dizia False pra verify/doctor/graph/
    memory, que de fato promptam no caminho default (≥2 features / sem query /
    submenu). Só `status` é genuinamente non-prompting. `machine_readable` é o
    eixo ORTOGONAL (aceita --json).
    """
    monkeypatch.delenv("FORGE_OUTPUT", raising=False)
    cli.main(["--help", "--json"])
    manifest = json.loads(capsys.readouterr().out)
    by_name = {c["name"]: c for c in manifest["commands"]}

    # Campos canônicos presentes.
    for cmd in manifest["commands"]:
        assert "prompts_by_default" in cmd
        assert "machine_readable" in cmd

    # Os 4 read-cmds que promptam no default: prompts_by_default=True E --json.
    for name in ("verify", "doctor", "graph", "memory"):
        assert by_name[name]["prompts_by_default"] is True, name
        assert by_name[name]["machine_readable"] is True, name

    # status: único genuinamente non-prompting, mas machine_readable.
    assert by_name["status"]["prompts_by_default"] is False
    assert by_name["status"]["machine_readable"] is True

    # `interactive` é alias de prompts_by_default (não mais mentira).
    for cmd in manifest["commands"]:
        assert cmd["interactive"] == cmd["prompts_by_default"]


def test_verify_in_bootstrap_skip(capsys, monkeypatch):
    """C-38 (PR21-I7): verify entra no skip-set (simétrico aos read-cmds)."""
    assert "verify" in cli._BOOTSTRAP_SKIP_COMMANDS


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
