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


def test_status_json_memory_has_mem_block(tmp_forge_project, capsys, monkeypatch):
    """O payload JSON deve ter memory.mem com total/by_type/live/stale."""
    import json
    from engine.integrations.mem import MemQuery

    import engine.status as _status
    monkeypatch.setattr(
        _status, "mem_stats",
        lambda root: MemQuery(
            ok=True,
            data={"total": 2, "live": 2, "stale": 0, "by_type": {"decision": 1, "feedback": 1},
                  "by_status": {}, "inbox_pending": 0, "inbox_promoted": 0, "inbox_rejected": 0,
                  "top_accessed": []},
        ),
    )
    code, payload = _run_json(capsys, tmp_forge_project, monkeypatch)
    assert code == 0
    mem_block = payload.get("memory", {}).get("mem")
    assert mem_block is not None, "campo 'mem' ausente no bloco 'memory'"
    assert "total" in mem_block
    assert "by_type" in mem_block
    assert "live" in mem_block
    assert "stale" in mem_block


def test_status_json_memory_mem_block_absent_when_degraded(tmp_forge_project, capsys, monkeypatch):
    """Se mem_stats degrada, o bloco 'mem' pode ser None ou ausente — sem crash."""
    import json
    from engine.integrations.mem import MemQuery

    import engine.status as _status
    monkeypatch.setattr(
        _status, "mem_stats",
        lambda root: MemQuery(ok=False, data=None, message="mem indisponível"),
    )
    code, payload = _run_json(capsys, tmp_forge_project, monkeypatch)
    assert code == 0
    # memory block ainda existe com L1 counts
    assert "memory" in payload
    # mem pode ser None ou estar ausente — não é erro
    mem_block = payload.get("memory", {}).get("mem")
    assert mem_block is None or isinstance(mem_block, dict)
