"""BUG-STATUS-1/2 (T1): status reflete commits do git + expõe qa verdict.

Regressão:
- BUG-STATUS-1: numa feature commitada, `forge status` reportava
  `implementing` com os commits do git INVISÍVEIS.
- BUG-STATUS-2: o qa verdict (persistido em
  ``.planning/qa/<target>/<run-id>/qa-report.json``) não aparecia no payload
  — um BLOCK ficava sem rastro.

Status permanece pure-read: nenhum dos novos campos muta git/estado.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from engine import status
from engine.memory import l1
from engine.memory.l1 import L1State
from engine.ui import output_mode as om


def _seed_config(project_root: Path) -> None:
    forge_dir = project_root / ".claude" / "forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / "forge-config.yaml").write_text(
        "identity:\n  project-name: demo\n  project-slug: demo\n",
        encoding="utf-8",
    )


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _init_git_repo(root: Path) -> None:
    _git(["init", "-q"], root)
    _git(["config", "user.email", "t@t.co"], root)
    _git(["config", "user.name", "t"], root)


def _run_json(capsys, project_root: Path, monkeypatch):
    monkeypatch.chdir(project_root)
    token = om.set_output_mode(om.OutputMode.JSON)
    try:
        code = status.run([])
    finally:
        om.reset_output_mode(token)
    out = capsys.readouterr().out
    return code, json.loads(out)


def _feature_payload(payload: dict, slug: str) -> dict:
    for f in payload["active_features"]:
        if f["slug"] == slug:
            return f
    raise AssertionError(f"feature {slug!r} ausente no payload")


def test_status_json_reflects_git_commits(tmp_path: Path, capsys, monkeypatch) -> None:
    slug = "lembrete-rega"
    _seed_config(tmp_path)
    _init_git_repo(tmp_path)

    # Feature em estado implementing + 2 commits que tocam o dir da feature.
    l1.write_l1_status(
        L1State(
            feature_slug=slug,
            status="implementing",
            last_action_at="2026-06-29T10:00:00Z",
            last_action_kind="implement-started",
        ),
        tmp_path,
    )
    feat_dir = tmp_path / "src" / slug
    feat_dir.mkdir(parents=True)
    for i in range(2):
        (feat_dir / f"f{i}.kt").write_text(f"// {i}\n", encoding="utf-8")
        _git(["add", "-A"], tmp_path)
        _git(["commit", "-qm", f"feat({slug}): commit {i}"], tmp_path)

    code, payload = _run_json(capsys, tmp_path, monkeypatch)
    assert code == 0
    fp = _feature_payload(payload, slug)
    assert "git" in fp, "payload da feature não tem bloco git (BUG-STATUS-1)"
    assert fp["git"]["feature_commits"] >= 2, (
        f"esperava >=2 commits da feature, vi {fp['git']!r}"
    )


def test_status_json_exposes_qa_verdict(tmp_path: Path, capsys, monkeypatch) -> None:
    slug = "lembrete-rega"
    _seed_config(tmp_path)
    _init_git_repo(tmp_path)
    l1.write_l1_status(
        L1State(
            feature_slug=slug,
            status="verifying",
            last_action_at="2026-06-29T10:00:00Z",
            last_action_kind="qa-run",
        ),
        tmp_path,
    )

    # Persiste um qa verdict BLOCK no path canônico (H-001).
    run_dir = tmp_path / ".planning" / "qa" / slug / "2026-06-29T11-00-00Z-aaaa"
    run_dir.mkdir(parents=True)
    (run_dir / "qa-report.json").write_text(
        json.dumps({"schema_version": 1, "verdict": "BLOCK", "findings": []}),
        encoding="utf-8",
    )

    code, payload = _run_json(capsys, tmp_path, monkeypatch)
    assert code == 0
    fp = _feature_payload(payload, slug)
    assert fp.get("qa_verdict") == "BLOCK", (
        f"qa verdict não exposto/errado: {fp.get('qa_verdict')!r} (BUG-STATUS-2)"
    )


def test_status_qa_verdict_picks_most_recent_run(tmp_path: Path, capsys, monkeypatch) -> None:
    slug = "lembrete-rega"
    _seed_config(tmp_path)
    _init_git_repo(tmp_path)
    l1.write_l1_status(
        L1State(
            feature_slug=slug,
            status="verifying",
            last_action_at="2026-06-29T10:00:00Z",
            last_action_kind="qa-run",
        ),
        tmp_path,
    )
    qa_dir = tmp_path / ".planning" / "qa" / slug
    older = qa_dir / "2026-06-28T10-00-00Z-aaaa"
    newer = qa_dir / "2026-06-29T10-00-00Z-bbbb"
    for d, verdict in ((older, "BLOCK"), (newer, "PASS")):
        d.mkdir(parents=True)
        (d / "qa-report.json").write_text(
            json.dumps({"verdict": verdict}), encoding="utf-8"
        )

    _, payload = _run_json(capsys, tmp_path, monkeypatch)
    fp = _feature_payload(payload, slug)
    assert fp.get("qa_verdict") == "PASS", "deveria ler o verdict da run mais recente"


def test_git_commits_not_double_counted_across_src_and_qa(tmp_path: Path) -> None:
    """MED-01: o pathspec ``*<slug>*`` casava src E .planning/qa do mesmo slug,
    double-contando. Um commit que toca só planning/qa NÃO é commit de código
    da feature — deve ser excluído da contagem.

    Cenário: 1 commit de código (src/<slug>) + 1 commit só de planning/qa do
    mesmo slug. A contagem de commits de CÓDIGO deve ser 1, não 2.
    """
    slug = "lembrete-rega"
    _init_git_repo(tmp_path)

    # Commit 1: código real da feature.
    feat_dir = tmp_path / "src" / slug
    feat_dir.mkdir(parents=True)
    (feat_dir / "Screen.kt").write_text("// code\n", encoding="utf-8")
    _git(["add", "-A"], tmp_path)
    _git(["commit", "-qm", f"feat({slug}): code"], tmp_path)

    # Commit 2: só artefatos de planning/qa do mesmo slug (NÃO é código).
    qa_dir = tmp_path / ".planning" / "qa" / slug
    qa_dir.mkdir(parents=True)
    (qa_dir / "qa-report.json").write_text("{}\n", encoding="utf-8")
    _git(["add", "-A"], tmp_path)
    _git(["commit", "-qm", f"qa({slug}): report"], tmp_path)

    n = status._git_feature_commits(tmp_path, slug)
    assert n == 1, (
        f"esperava 1 commit de código (não double-contar planning/qa), vi {n}"
    )


def test_qa_verdict_most_recent_run_without_verdict_reports_none(
    tmp_path: Path,
) -> None:
    """LOW-01: se a run mais recente existe mas não tem verdict (run em voo /
    report parcial), NÃO cair pro verdict de uma run anterior — devolver None
    (= "ainda sem veredito"), não um PASS/BLOCK estale rotulado como atual.
    """
    slug = "lembrete-rega"
    qa_dir = tmp_path / ".planning" / "qa" / slug
    older = qa_dir / "2026-06-28T10-00-00Z-aaaa"
    newer = qa_dir / "2026-06-29T10-00-00Z-bbbb"  # mais recente, sem verdict
    older.mkdir(parents=True)
    newer.mkdir(parents=True)
    (older / "qa-report.json").write_text(
        json.dumps({"verdict": "PASS"}), encoding="utf-8"
    )
    # run mais recente: report sem campo verdict (run em voo)
    (newer / "qa-report.json").write_text(
        json.dumps({"schema_version": 1, "findings": []}), encoding="utf-8"
    )

    verdict = status._read_qa_verdict(tmp_path, slug)
    assert verdict is None, (
        f"run mais recente sem verdict deveria reportar None, não o verdict velho "
        f"({verdict!r})"
    )


def test_status_does_not_mutate_git(tmp_path: Path, capsys, monkeypatch) -> None:
    """Pure-read: rodar status não muda o HEAD nem cria/altera commits."""
    slug = "lembrete-rega"
    _seed_config(tmp_path)
    _init_git_repo(tmp_path)
    (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
    _git(["add", "-A"], tmp_path)
    _git(["commit", "-qm", f"feat({slug}): base"], tmp_path)
    l1.write_l1_status(
        L1State(
            feature_slug=slug,
            status="implementing",
            last_action_at="2026-06-29T10:00:00Z",
            last_action_kind="implement-started",
        ),
        tmp_path,
    )
    sha_before = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True
    ).strip()

    _run_json(capsys, tmp_path, monkeypatch)

    sha_after = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True
    ).strip()
    assert sha_before == sha_after, "status mutou o git (quebra contrato pure-read)"
