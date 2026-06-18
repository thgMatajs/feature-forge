import json

from engine.ui import output_mode as om
from engine import memory_cli


def _seed_config(project_root):
    forge_dir = project_root / ".claude" / "forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / "forge-config.yaml").write_text(
        "schema-version: 1\nidentity:\n  project-name: demo\n",
        encoding="utf-8",
    )
    return project_root


def _run_json(capsys, project_root, monkeypatch):
    _seed_config(project_root)
    monkeypatch.chdir(project_root)
    token = om.set_output_mode(om.OutputMode.JSON)
    try:
        code = memory_cli.run([])
    finally:
        om.reset_output_mode(token)
    out = capsys.readouterr().out
    return code, json.loads(out)


def test_memory_json_emits_three_layers(tmp_forge_project, capsys, monkeypatch):
    code, payload = _run_json(capsys, tmp_forge_project, monkeypatch)
    assert code == 0
    assert "l2" in payload and "l1" in payload and "l3" in payload
    assert "entries" in payload["l2"] and "size_bytes" in payload["l2"]
    assert "active" in payload["l1"] and "archived" in payload["l1"]
    assert isinstance(payload["l3"], list)


def test_memory_json_does_not_enter_menu(tmp_forge_project, capsys, monkeypatch):
    # JSON mode must NOT call question.ask — a pure-JSON stdout proves it.
    _, payload = _run_json(capsys, tmp_forge_project, monkeypatch)
    assert isinstance(payload, dict)
