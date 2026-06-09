"""Tests for the position of check_secrets in the verify cascade.

Cobre Sub-Task 5A do check_secrets plan: o validador `check_secrets` fica
registrado como engine-default — imediatamente APÓS
`check_cyclomatic_complexity` (anti-pattern de gates agrupados) — e a
cascade respeita fail-fast (Decision 23): quando o anterior falha hard,
secrets nem roda.
"""

from __future__ import annotations

from pathlib import Path

from engine import verify


def test_secrets_validator_registered() -> None:
    """Cascade default registry contém `check_secrets`."""
    assert hasattr(verify, "_DEFAULT_VALIDATORS")
    names = [entry["name"] for entry in verify._DEFAULT_VALIDATORS]
    assert "check_secrets" in names, (
        f"check_secrets ausente em _DEFAULT_VALIDATORS; got {names}"
    )


def test_secrets_position_after_cc() -> None:
    """`check_secrets` aparece IMEDIATAMENTE após `check_cyclomatic_complexity`.

    Anti-pattern de "gates agrupados" — gates correm juntos pra fail-fast
    surfacing previsível. Ordem load-bearing: NIB → CC → secrets.
    """
    names = [entry["name"] for entry in verify._DEFAULT_VALIDATORS]
    idx_cc = names.index("check_cyclomatic_complexity")
    idx_secrets = names.index("check_secrets")
    assert idx_secrets == idx_cc + 1, (
        f"check_secrets must immediately follow check_cyclomatic_complexity; "
        f"got {names}"
    )


def test_secrets_fail_fast_respected(monkeypatch, tmp_path: Path) -> None:
    """Se um validador anterior falha hard, check_secrets nem roda."""
    captured: list[str] = []

    def fake_invoke(spec, root):
        captured.append(spec.name)
        if spec.name == "check_cyclomatic_complexity":
            return verify._ValidatorResult(
                name=spec.name, status="fail", duration_ms=1
            )
        return verify._ValidatorResult(
            name=spec.name, status="pass", duration_ms=1
        )

    monkeypatch.setattr(verify, "_invoke_validator", fake_invoke)
    specs = [
        verify._ValidatorSpec(
            name="check_cyclomatic_complexity", script_path=Path("cc.py")
        ),
        verify._ValidatorSpec(
            name="check_secrets", script_path=Path("secrets.py")
        ),
    ]
    results = verify._run_cascade(
        specs, fail_fast=True, project_root=tmp_path, interactive=False
    )
    secrets_result = next(
        (r for r in results if r.name == "check_secrets"), None
    )
    assert secrets_result is not None, "Result for check_secrets not found"
    assert secrets_result.status == "skipped"
    # check_secrets nem foi invocado — fail-fast respeitado
    assert "check_secrets" not in captured


def test_default_validator_specs_includes_check_secrets(tmp_path: Path) -> None:
    """`_default_validator_specs` inclui check_secrets quando o script existe no disco."""
    out = verify._default_validator_specs(tmp_path)
    names = [spec.name for spec in out]
    assert "check_secrets" in names, (
        f"check_secrets ausente em default specs; got {names}"
    )


def test_check_secrets_validate_defaults_to_cascade() -> None:
    """Cascade roda via subprocess sem ``--stage`` → o default DEVE ser
    ``"cascade"`` (trufflehog), nunca ``"per_task"`` (gitleaks).

    Simétrico ao ``test_run_secrets_gate_calls_validator_with_per_task_stage``
    (per-task hook). O split per-stage é a decisão central do design: regredir
    o default pra ``"per_task"`` faria a cascade rodar gitleaks silenciosamente,
    sem nenhum sinal. Esta é a rede de segurança barata contra esse anti-padrão
    (plano §Task 4). Ancoramos no default da assinatura porque
    ``engine/verify.py`` invoca o validator como subprocess sem injetar stage —
    o default implícito É o contrato da cascade.
    """
    import inspect

    from validators import check_secrets

    sig = inspect.signature(check_secrets.validate)
    assert sig.parameters["stage"].default == "cascade", (
        "default de check_secrets.validate(stage=...) regrediu; a cascade "
        "depende de 'cascade' (trufflehog) e não passa --stage explicitamente"
    )
