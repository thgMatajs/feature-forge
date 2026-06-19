"""C-43 (PR22-R-001) — regressão: o cascade de verify threada scope/target
até os validators como `--scope`/`--id`.

Antes do fix, `_invoke_validator` invocava cada validator só com
`--project-root`, então `check_unfilled_placeholders._resolve_slug` recebia
kwargs vazios e SEMPRE retornava `None` → gate inteiro vacuous (shipped-but-
inert). Estes testes provam que:

1. `_invoke_validator` inclui `--scope`/`--id` no argv do subprocess.
2. `_run_cascade` propaga scope_type/scope_target recebidos.
3. Um artefato de feature UNSTAGED com `{{token}}` cru hard-faila em
   `run_scope('feature', slug)` — i.e. o gate detecta pré-staging (filesystem
   scan, não git-staged).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from engine import verify
from engine.utils.paths import feature_path


def test_invoke_validator_threads_scope_and_id(monkeypatch, tmp_path: Path) -> None:
    """O argv do subprocess carrega --scope <kind> --id <target>."""
    captured: dict[str, list[str]] = {}

    class _FakeProc:
        returncode = 0
        stdout = '{"status": "pass", "message": "ok"}'
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        return _FakeProc()

    monkeypatch.setattr(verify.subprocess, "run", fake_run)
    script = tmp_path / "v.py"
    script.write_text("# noop\n", encoding="utf-8")
    spec = verify._ValidatorSpec(name="v", script_path=script)
    verify._invoke_validator(
        spec, tmp_path, scope_type="feature", scope_target="demo"
    )
    cmd = captured["cmd"]
    assert "--scope" in cmd, cmd
    assert "feature" in cmd, cmd
    assert "--id" in cmd, cmd
    assert "demo" in cmd, cmd


def test_run_cascade_propagates_scope(monkeypatch, tmp_path: Path) -> None:
    seen: list[tuple[str | None, str | None]] = []

    def fake_invoke(spec, root, *, scope_type=None, scope_target=None):
        seen.append((scope_type, scope_target))
        return verify._ValidatorResult(name=spec.name, status="pass")

    monkeypatch.setattr(verify, "_invoke_validator", fake_invoke)
    specs = [verify._ValidatorSpec(name="v", script_path=Path("v.py"))]
    verify._run_cascade(
        specs,
        fail_fast=True,
        project_root=tmp_path,
        interactive=False,
        scope_type="feature",
        scope_target="demo",
    )
    assert seen == [("feature", "demo")]


def _git_init(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)


def test_placeholder_gate_catches_unstaged_artifact(tmp_path: Path) -> None:
    """run_scope('feature', slug) hard-faila em artefato UNSTAGED com {{token}}.

    Reproduz o defeito do C-43: o gate precisa varrer o filesystem do dir da
    feature, não os arquivos staged (que estão vazios pré-staging num hook
    pre-commit que roda ANTES do `git add`).
    """
    _git_init(tmp_path)
    # Estrutura mínima de projeto forge.
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "forge").mkdir()
    f_root = feature_path(tmp_path, "demo", subtype="product")
    f_root.mkdir(parents=True, exist_ok=True)
    artifact = f_root / "prd.md"
    artifact.write_text("# PRD\nObjetivo: {{objective}}\n", encoding="utf-8")
    # NÃO faz git add — fica unstaged de propósito.
    rc = verify.run_scope("feature", "demo", tmp_path, interactive=False)
    assert rc == 1, "gate deveria hard-failar em placeholder cru unstaged"
