import json

from engine.ui import output_mode as om
from engine import verify
from engine.memory.l1 import L1State, read_l1_status, write_l1_status


def _seed_config(project_root):
    forge_dir = project_root / ".claude" / "forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / "forge-config.yaml").write_text(
        "schema-version: 1\nidentity:\n  project-name: demo\n",
        encoding="utf-8",
    )
    return project_root


def _run_json(capsys, project_root, monkeypatch, argv=None):
    _seed_config(project_root)
    monkeypatch.chdir(project_root)
    token = om.set_output_mode(om.OutputMode.JSON)
    try:
        code = verify.run(argv or [])
    finally:
        om.reset_output_mode(token)
    out = capsys.readouterr().out
    return code, json.loads(out)


def test_verify_json_clean_project_emits_pass(tmp_forge_project, capsys, monkeypatch):
    # Clean project with nothing staged → built-in validators all pass → overall
    # pass, exit 0. (The fixture lives inside the forge repo, so the built-in
    # validators are discovered; with no staged files each one is a no-op pass.)
    code, payload = _run_json(capsys, tmp_forge_project, monkeypatch)
    assert code == 0
    assert payload["overall"] == "pass"
    assert isinstance(payload["validators"], list)
    assert all(v["status"] in ("pass", "skipped") for v in payload["validators"])
    assert "scope" in payload and "exit_code" in payload
    assert payload["exit_code"] == 0


def test_verify_json_stdout_pure(tmp_forge_project, capsys, monkeypatch):
    _, payload = _run_json(capsys, tmp_forge_project, monkeypatch)
    assert isinstance(payload, dict)


def _seed_active_feature(project_root, slug, status="implementing"):
    write_l1_status(
        L1State(
            feature_slug=slug,
            status=status,
            last_action_at="2026-06-18T00:00:00Z",
            last_action_kind="implement-started",
            raw={"sub-state": "apply-mode"} if status == "implementing" else {},
        ),
        project_root,
    )


def test_verify_json_task_scope_ambiguous_exits_1_no_mutation(
    tmp_forge_project, capsys, monkeypatch
):
    """C-34 (PR21-I2): `verify --json task TASK-N` com ≥2 features ativas →
    exit 1, stderr, ZERO mutação de L1 (não muta a feature errada).

    O guard C-001 cobria só o path de inferência de scope; o path `task`
    escapava e caía no fallback sorted(active)[0] dentro de run_scope, mutando
    a L1 da feature errada (status=verifying transiente).
    """
    _seed_config(tmp_forge_project)
    _seed_active_feature(tmp_forge_project, "alpha")
    _seed_active_feature(tmp_forge_project, "beta")
    monkeypatch.chdir(tmp_forge_project)

    token = om.set_output_mode(om.OutputMode.JSON)
    try:
        code = verify.run(["task", "TASK-0001"])
    finally:
        om.reset_output_mode(token)

    captured = capsys.readouterr()
    assert code == 1
    assert "ambíguo" in captured.err or "ambiguo" in captured.err
    assert captured.out == "", "stdout deve ficar puro (sem JSON parcial)"
    # Nenhuma feature foi marcada verifying — zero side-effect.
    for slug in ("alpha", "beta"):
        st = read_l1_status(slug, tmp_forge_project)
        assert st is not None
        assert st.status == "implementing", (
            f"{slug} não deveria ter sido mutada — status={st.status}"
        )


def test_verify_json_task_scope_single_active_resolves(
    tmp_forge_project, capsys, monkeypatch
):
    """C-34: com 1 feature ativa, `verify --json task TASK-N` resolve sem erro."""
    _seed_config(tmp_forge_project)
    _seed_active_feature(tmp_forge_project, "solo")
    monkeypatch.chdir(tmp_forge_project)

    token = om.set_output_mode(om.OutputMode.JSON)
    try:
        code = verify.run(["task", "TASK-0001"])
    finally:
        om.reset_output_mode(token)
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert code == 0
    assert payload["overall"] in ("pass", "warn")


def test_verify_json_project_root_missing_writes_stderr(tmp_path, capsys, monkeypatch):
    """H-001: ProjectRootNotFound in JSON mode emits the full message on stderr.

    `renderer.write` is a no-op in JSON mode, so the friendly text must go to
    stderr (mirroring status/doctor/memory) instead of vanishing. stdout stays
    pure (no JSON payload, no orphan text) and the exit code is 1.
    """
    # tmp_path has no .claude/forge marker → find_project_root raises.
    monkeypatch.chdir(tmp_path)
    token = om.set_output_mode(om.OutputMode.JSON)
    try:
        code = verify.run([])
    finally:
        om.reset_output_mode(token)
    captured = capsys.readouterr()
    assert code == 1
    assert "forge verify" in captured.err
    assert captured.out == ""
