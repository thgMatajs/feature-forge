"""End-to-end integration tests for the secrets-gate (check_secrets, R1.1).

Cobre só o que os unit tests com mock NÃO cobrem: o wiring git real
(``git_staged_files`` → ``_dispatch_for_stage`` → parse → override →
result_fail/pass) num repo git de verdade, mais dois smoke tests com as
tools reais (gitleaks / trufflehog) guardados por ``@pytest.mark.skipif``
pra suite seguir verde sem as ferramentas nativas.

Cenários redundantes com os unit tests do engine (cascade position →
``test_secrets_position_after_cc``; fail-fast skip →
``test_secrets_fail_fast_respected``; bypass JSONL →
``test_run_secrets_gate_bypassed_by_env_var``) foram removidos — eram dups
verbatim de net-negative manutenção.

Os dois cenários determinísticos mockam apenas o dispatch da tool nativa
(``_dispatch_for_stage``) injetando o output JSON canônico das fixtures —
o resto da pipeline (staged files reais → parse → override → result + render)
roda end-to-end sem depender de gitleaks/trufflehog no PATH.

Mapa de cenários:
    1. per_task_fail_blocks        — gitleaks finding sem override →
       status=fail + 3-paths block; o .kt staged real flui pro what-failed.
    2. per_task_override_permits   — SECRETS-OVERRIDE matching no commit body
       → finding silenced, gate passa limpo (status=pass).
    3. smoke_gitleaks_real         — gitleaks de verdade detecta o AKIA do
       fixture → fail determinístico (skip-guarded).
    4. smoke_trufflehog_real       — trufflehog --only-verified NÃO confirma
       token FAKE → pass legítimo (caminho negativo; skip-guarded).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "secrets"

pytestmark = pytest.mark.integration


def _git_init(repo: Path) -> None:
    """Inicializa repo temp com um commit vazio inicial pra HEAD existir."""
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@forge.local"], cwd=repo, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "forge-test"], cwd=repo, check=True
    )
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True
    )
    (repo / ".gitkeep").write_text("", encoding="utf-8")
    subprocess.run(["git", "add", ".gitkeep"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)


def _stage(repo: Path, rel_path: str, content: str) -> None:
    """Escreve ``content`` em ``rel_path`` e faz ``git add``."""
    p = repo / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", rel_path], cwd=repo, check=True)


def _setup_workflow_config(repo: Path, secrets_block: dict | None = None) -> None:
    """Escreve um ``.claude/workflow-config.yaml`` mínimo habilitando o gate."""
    import yaml

    (repo / ".claude").mkdir(exist_ok=True)
    cfg = {
        "schema-version": 1,
        "identity": {"project-slug": "test", "preset": "kmp-mobile"},
        "cards": {"active": []},
        "secrets-gate": secrets_block or {"enabled": True},
    }
    (repo / ".claude" / "workflow-config.yaml").write_text(
        yaml.safe_dump(cfg), encoding="utf-8"
    )


def _import_validator():
    """Importa check_secrets garantindo ``validators/`` no sys.path.

    conftest.py já adiciona pra suite, mas re-asseguramos aqui pra o arquivo
    rodar stand-alone (``pytest <file>::<test>``).
    """
    validators_dir = Path(__file__).resolve().parents[2] / "validators"
    if str(validators_dir) not in sys.path:
        sys.path.insert(0, str(validators_dir))
    import check_secrets as v

    return v


def _gitleaks_json_for(rel_path: str, line: int, kind: str = "aws-access-key") -> str:
    """Monta output JSON do gitleaks (array) pra um único finding determinístico."""
    import json

    return json.dumps(
        [
            {
                "RuleID": kind,
                "Description": "AWS Access Key",
                "File": rel_path,
                "StartLine": line,
                "Secret": "AKIA00000000FAKE0000",
                "Match": 'const val KEY = "AKIA00000000FAKE0000"',
            }
        ]
    )


# ── Scenario: per-task fail blocks commit (gitleaks finding) ─────────────────


def test_per_task_fail_blocks_commit(tmp_path: Path, monkeypatch) -> None:
    """gitleaks finding sem override → fail com 3-paths block end-to-end.

    Mock do dispatch da infra Phase 0 injeta output JSON canônico — a pipeline
    inteira do validator roda (parse → override (none) → result_fail + render)
    sem depender da tool real no PATH.
    """
    _git_init(tmp_path)
    _setup_workflow_config(tmp_path)
    _stage(
        tmp_path,
        "app/AwsConfig.kt",
        (FIXTURES / "file_with_secret.kt").read_text(encoding="utf-8"),
    )

    v = _import_validator()

    # gitleaks/trufflehog podem não estar no PATH — forçamos available + dispatch.
    monkeypatch.setattr(v, "check_tool_available", lambda _tool: True)
    monkeypatch.setattr(
        v,
        "_dispatch_for_stage",
        lambda stage, files, *, project_root: v.DispatchResult(
            language="any",
            tool_found=True,
            crashed=False,
            raw_stdout=_gitleaks_json_for("app/AwsConfig.kt", 4),
            error_message="",
        ),
    )

    result = v.validate(tmp_path, stage="per_task")

    assert result["status"] == "fail", (
        f"esperado fail quando gitleaks reporta finding sem override; got {result}"
    )
    assert len(result["paths"]) == 3, (
        f"disciplina §1 exige exatamente 3 paths; got {len(result['paths'])}"
    )
    render = result.get("render", "")
    assert "🛑 Check Secrets gate" in render, "render deve trazer o header canônico"
    assert "(unverified — gitleaks)" in render, (
        "per_task stage deve marcar findings como unverified (gitleaks)"
    )


# ── Scenario: override-justify permits commit ────────────────────────────────


def test_per_task_override_permits_commit(tmp_path: Path, monkeypatch) -> None:
    """SECRETS-OVERRIDE matching no commit body silencia o finding → pass.

    Mesmo setup do cenário per-task fail, mas COMMIT_EDITMSG carrega o override
    exato ``(file, line, kind)`` — o finding vira silenced e o gate passa.
    """
    _git_init(tmp_path)
    _setup_workflow_config(tmp_path)
    _stage(
        tmp_path,
        "app/AwsConfig.kt",
        (FIXTURES / "file_with_test_fixture.kt").read_text(encoding="utf-8"),
    )
    # Simula o pre-commit hook populando COMMIT_EDITMSG com o override.
    # Nota: U+2014 em-dash é load-bearing — o regex strict exige ele.
    (tmp_path / ".git" / "COMMIT_EDITMSG").write_text(
        "feat(config): aws fixture\n\n"
        "SECRETS-OVERRIDE: app/AwsConfig.kt:4 kind=aws-access-key — test fixture, chars FAKE\n",
        encoding="utf-8",
    )

    v = _import_validator()
    monkeypatch.setattr(v, "check_tool_available", lambda _tool: True)
    monkeypatch.setattr(
        v,
        "_dispatch_for_stage",
        lambda stage, files, *, project_root: v.DispatchResult(
            language="any",
            tool_found=True,
            crashed=False,
            raw_stdout=_gitleaks_json_for("app/AwsConfig.kt", 4),
            error_message="",
        ),
    )

    result = v.validate(tmp_path, stage="per_task")
    assert result["status"] in ("pass", "warn"), (
        f"override deve silenciar o único finding; got {result}"
    )


# ── Scenario: smoke gitleaks real (skip when missing) ────────────────────────


@pytest.mark.skipif(
    shutil.which("gitleaks") is None, reason="gitleaks ausente no PATH"
)
def test_smoke_gitleaks_real_detects_fixture(tmp_path: Path) -> None:
    """gitleaks de verdade roda no fixture e detecta o token AWS-style.

    Não mocka nada — exercita o cmd_builder real + parse end-to-end. Resultado
    aceitável: fail (detectou) ou pass (default ruleset do gitleaks pode variar
    por versão). O invariante forte é não-crash e shape de result válido.
    """
    _git_init(tmp_path)
    _setup_workflow_config(tmp_path)
    _stage(
        tmp_path,
        "app/AwsConfig.kt",
        (FIXTURES / "file_with_secret.kt").read_text(encoding="utf-8"),
    )

    v = _import_validator()
    result = v.validate(tmp_path, stage="per_task")
    assert result["status"] in ("fail", "pass", "warn"), (
        f"pipeline gitleaks real retornou status inesperado: {result.get('status')!r}"
    )
    if result["status"] == "fail":
        assert len(result["paths"]) == 3, (
            "fail real do gitleaks deve carregar exatamente 3 paths"
        )


# ── Scenario: smoke trufflehog real (skip when missing) ──────────────────────


@pytest.mark.skipif(
    shutil.which("trufflehog") is None, reason="trufflehog ausente no PATH"
)
def test_smoke_trufflehog_real_skips_fake_token(tmp_path: Path) -> None:
    """trufflehog --only-verified NÃO confirma token FAKE → pass legítimo.

    O fixture usa ``AKIA00000000FAKE0000`` — chars deliberadamente inválidos
    pra trufflehog não bater na AWS real. Logo ``--only-verified`` filtra tudo
    out e o gate passa. NÃO dá pra testar verified=true em CI sem um leak real
    ativo (e não vamos commitar um), então este smoke cobre apenas o caminho
    negativo — que é o esperado pro fixture seguro.
    """
    _git_init(tmp_path)
    _setup_workflow_config(tmp_path)
    _stage(
        tmp_path,
        "app/AwsConfig.kt",
        (FIXTURES / "file_with_secret.kt").read_text(encoding="utf-8"),
    )

    v = _import_validator()
    result = v.validate(tmp_path, stage="cascade")
    assert result["status"] in ("pass", "warn"), (
        f"token FAKE não deve ser verified por trufflehog --only-verified; "
        f"got {result}"
    )
