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


def test_memory_json_partial_snapshot_on_corrupt_l3(
    tmp_forge_project, capsys, monkeypatch
):
    """C-40 (PR21-I9): L3 corrompido → snapshot PARCIAL coerente (l3=[] + flag
    `degraded`), não traceback — as outras camadas seguem."""
    _seed_config(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    def _boom_l3():
        raise OSError("L3 corrompido")

    monkeypatch.setattr(memory_cli, "read_l3_index", _boom_l3)
    token = om.set_output_mode(om.OutputMode.JSON)
    try:
        code = memory_cli.run([])
    finally:
        om.reset_output_mode(token)
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert code == 0
    assert payload["l3"] == []
    assert "l3" in payload.get("degraded", [])
    # As outras camadas continuam presentes.
    assert "l2" in payload and "l1" in payload


def test_memory_json_outer_guard_clean_error(
    tmp_forge_project, capsys, monkeypatch
):
    """C-36 (PR21-I6): erro residual no snapshot → stderr clean + exit 1, stdout
    puro (sem traceback cru, sem JSON parcial)."""
    _seed_config(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    def _boom(_root):
        raise OSError("snapshot explodiu")

    monkeypatch.setattr(memory_cli, "_memory_snapshot", _boom)
    token = om.set_output_mode(om.OutputMode.JSON)
    try:
        code = memory_cli.run([])
    finally:
        om.reset_output_mode(token)
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == "", "stdout deve ficar puro (sem JSON/traceback)"
    assert "forge memory" in captured.err
