import json

from engine.ui import output_mode as om
from engine import doctor


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
        code = doctor.run([])
    finally:
        om.reset_output_mode(token)
    out = capsys.readouterr().out
    return code, json.loads(out)


def test_doctor_json_emits_categories(tmp_forge_project, capsys, monkeypatch):
    code, payload = _run_json(capsys, tmp_forge_project, monkeypatch)
    assert "categories" in payload
    assert "overall_status" in payload
    assert payload["exit_code"] == code
    for cat in payload["categories"]:
        assert "title" in cat and "checks" in cat
        for chk in cat["checks"]:
            assert set(chk) >= {"name", "status", "message", "remediation"}


def test_doctor_json_scope_is_full(tmp_forge_project, capsys, monkeypatch):
    _, payload = _run_json(capsys, tmp_forge_project, monkeypatch)
    assert payload["scope"] == "full"
