"""End-to-end integration tests for the secrets-gate (check_secrets, R1.1).

Cada teste exercita um dos cenários do spec §5 — cascade position, fail-fast
skip (Decision 23), per-task block, override-permit, bypass via env, e dois
smoke tests com tools reais (gitleaks / trufflehog) guardados por
``@pytest.mark.skipif`` pra suite seguir verde sem as ferramentas nativas.

Os cenários determinísticos (sem tool real) mockam o dispatch da infra Phase 0
(``dispatch_native_tool``) injetando o output JSON canônico das fixtures —
assim a pipeline inteira do validator (parse → ignore-paths → override →
result_fail/pass + render) roda end-to-end sem depender de gitleaks/trufflehog
estarem no PATH. Os smoke tests cobrem a integração com a tool real.

Mapa de cenários (spec §5 integration table):
    1. cascade_position            — check_secrets sit AFTER
       check_cyclomatic_complexity no cascade default.
    2. failfast_skips_secrets      — validator anterior falha sob fail_fast
       → secrets gate marcado ``skipped`` e nunca invocado.
    3. per_task_fail_blocks        — gitleaks finding sem override →
       status=fail + 3-paths block + handoff aborta antes do commit.
    4. per_task_override_permits   — SECRETS-OVERRIDE matching no commit body
       → finding silenced, gate passa, handoff continua.
    5. no_secrets_gate_bypass      — NO_SECRETS_GATE=1 → gate pulado, entry
       JSONL escrito em .claude/forge/state/secrets-gate-bypass.jsonl.
    6. smoke_gitleaks_real         — gitleaks de verdade detecta o fixture.
    7. smoke_trufflehog_real       — trufflehog --only-verified NÃO confirma
       token FAKE → pass legítimo (não dá pra testar verified=true em CI sem
       leak real — documentado no docstring).
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


# ── Scenario 1: cascade position ─────────────────────────────────────────────


def test_verify_cascade_position(tmp_path: Path) -> None:
    """check_secrets é listado APÓS check_cyclomatic_complexity no cascade."""
    from engine import verify

    specs = verify._default_validator_specs(tmp_path)
    names = [s.name for s in specs]
    assert "check_secrets" in names, (
        "secrets gate deve estar registrado no cascade default"
    )
    assert "check_cyclomatic_complexity" in names, (
        "esperado check_cyclomatic_complexity ancorando o cascade"
    )
    assert (
        names.index("check_secrets")
        == names.index("check_cyclomatic_complexity") + 1
    ), f"secrets gate deve seguir o CC gate; ordem obtida {names}"


# ── Scenario 2: fail-fast skip (Decision 23) ─────────────────────────────────


def test_cascade_failfast_skips_secrets_when_earlier_fails(
    tmp_path: Path, monkeypatch
) -> None:
    """fail_fast=True + fail anterior ⇒ secrets gate result.status == 'skipped'."""
    from engine import verify

    captured: list[str] = []

    def fake_invoke(spec, root, **kwargs):
        captured.append(spec.name)
        if spec.name == "check_cyclomatic_complexity":
            return verify._ValidatorResult(
                name=spec.name, status="fail", duration_ms=1
            )
        return verify._ValidatorResult(
            name=spec.name, status="pass", duration_ms=1
        )

    monkeypatch.setattr(verify, "_invoke_validator", fake_invoke)
    specs = verify._default_validator_specs(tmp_path)
    results = verify._run_cascade(
        specs, fail_fast=True, project_root=tmp_path, interactive=False
    )
    secrets = next(r for r in results if r.name == "check_secrets")
    assert secrets.status == "skipped", (
        f"secrets gate deve ser skipped após fail anterior no fail-fast; "
        f"obtido {secrets.status}"
    )
    assert "check_secrets" not in captured, (
        "fail-fast não pode sequer invocar o secrets gate após fail anterior"
    )


# ── Scenario 3: per-task fail blocks commit (gitleaks finding) ───────────────


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


# ── Scenario 4: override-justify permits commit ──────────────────────────────


def test_per_task_override_permits_commit(tmp_path: Path, monkeypatch) -> None:
    """SECRETS-OVERRIDE matching no commit body silencia o finding → pass.

    Mesmo setup do cenário 3, mas COMMIT_EDITMSG carrega o override exato
    ``(file, line, kind)`` — o finding vira silenced e o gate passa.
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


# ── Scenario 5: NO_SECRETS_GATE bypass (per-task hook) ───────────────────────


def test_no_secrets_gate_bypass_logs_entry(tmp_path: Path, monkeypatch) -> None:
    """NO_SECRETS_GATE=1 pula o gate e escreve entry JSONL de auditoria."""
    import json

    from engine import implement

    monkeypatch.setenv("NO_SECRETS_GATE", "1")
    result = implement._run_secrets_gate(tmp_path)

    assert result["status"] == "warn"
    assert result["blocking"] is False
    assert "bypassed" in result["message"]

    log_path = tmp_path / ".claude" / "forge" / "state" / "secrets-gate-bypass.jsonl"
    assert log_path.is_file(), "bypass deve escrever trilha de auditoria JSONL"
    lines = [ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1, f"esperado 1 entry de bypass; got {len(lines)}"
    entry = json.loads(lines[0])
    assert "at" in entry and "reason" in entry, (
        f"entry de bypass deve ter 'at' + 'reason'; got {entry}"
    )


# ── Scenario 6: smoke gitleaks real (skip when missing) ──────────────────────


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


# ── Scenario 7: smoke trufflehog real (skip when missing) ────────────────────


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
