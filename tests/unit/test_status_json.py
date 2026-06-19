import json

from engine.ui import output_mode as om
from engine import status


def _seed_config(project_root):
    """Write the minimal forge project marker so find_project_root resolves."""
    forge_dir = project_root / ".claude" / "forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / "forge-config.yaml").write_text(
        "identity:\n  project-name: demo\n  project-slug: demo\n",
        encoding="utf-8",
    )
    return project_root


def _run_json(capsys, project_root, monkeypatch):
    _seed_config(project_root)
    monkeypatch.chdir(project_root)
    token = om.set_output_mode(om.OutputMode.JSON)
    try:
        code = status.run([])
    finally:
        om.reset_output_mode(token)
    out = capsys.readouterr().out
    return code, json.loads(out)


def test_status_json_emits_valid_json_with_required_keys(tmp_forge_project, capsys, monkeypatch):
    code, payload = _run_json(capsys, tmp_forge_project, monkeypatch)
    assert code == 0
    for key in (
        "project",
        "active_features",
        "memory",
        "pending_evolutions",
        "doctor",
        "suggested_next_command",
    ):
        assert key in payload


def test_status_json_suggests_plan_when_no_active_features(tmp_forge_project, capsys, monkeypatch):
    code, payload = _run_json(capsys, tmp_forge_project, monkeypatch)
    assert payload["suggested_next_command"] == "plan"


def test_status_json_stdout_is_pure_json(tmp_forge_project, capsys, monkeypatch):
    _, payload = _run_json(capsys, tmp_forge_project, monkeypatch)
    # json.loads succeeded above; assert no cinematic prose leaked.
    assert isinstance(payload, dict)
