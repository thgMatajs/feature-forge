"""WR-02 (Onda 1, fix-forward): um run com ``degraded`` não pode reportar
``overall: pass`` silencioso — é o gêmeo "cega o overall" do bug que a Onda 1
combate ("cega a cascade").

Contexto: se TODOS (ou alguns) validators saem ``degraded`` (infra off-contract),
o cálculo antigo ``overall = "fail" if hard_fail else ("warn" if warns else
"pass")`` resultava em ``overall="pass"`` + ``exit_code=0`` + ``coverage_summary``
todo-zero. Um host IA-first ingênuo lê "verde" sem varrer ``validators[]`` —
falso-verde, exatamente o que a T1/T3 existem pra matar.

Invariante PRESERVADA (H-001 + Decisão 23): ``degraded`` continua NÃO sendo
``fail``, NÃO halta a cascade, e NÃO vira hard-fail de exit-code. Infra quebrada
≠ código reprovado. O fix torna a presença de degraded SALIENTE (overall distinto
+ flag no payload + coverage honesta), sem inventar exit-code novo.

Estes testes batem direto em ``run_scope`` via o caminho ``--json`` real (cruza
o cálculo de overall + montagem do payload), e em ``_coverage_breakdown`` pro
contrato de coverage honesta.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.ui import output_mode as om
from engine import verify
from engine.memory.l1 import append_verify_log, MemoryError as L1MemoryError
from engine.verify import _coverage_breakdown, _ValidatorResult, _ValidatorSpec


def _seed_config(project_root: Path) -> Path:
    forge_dir = project_root / ".claude" / "forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / "forge-config.yaml").write_text(
        "schema-version: 1\nidentity:\n  project-name: demo\n",
        encoding="utf-8",
    )
    return project_root


def _run_json_with_results(monkeypatch, project_root, results):
    """Roda ``run_scope`` no caminho --json forçando o resultado da cascade,
    pra exercitar exatamente o cálculo de overall + payload sem precisar de
    validators reais quebrados no disco."""
    _seed_config(project_root)
    monkeypatch.chdir(project_root)

    # Curto-circuita a descoberta+execução da cascade: o que importa pro WR-02
    # é o que run_scope faz com a LISTA de resultados (overall, coverage, payload).
    # Os specs precisam carregar .name (consumido por _write_verify_log_entry).
    specs = [_ValidatorSpec(name=r.name, script_path=Path("/nonexistent")) for r in results]
    monkeypatch.setattr(
        verify,
        "_discover_validators",
        lambda *a, **k: specs,  # não-vazio: evita o early-return all-pass
    )
    monkeypatch.setattr(verify, "_run_cascade", lambda *a, **k: results)

    token = om.set_output_mode(om.OutputMode.JSON)
    try:
        code = verify.run([])
    finally:
        om.reset_output_mode(token)
    return code, results


def _capture_payload(capsys):
    return json.loads(capsys.readouterr().out)


# ── run 100% degraded → overall != pass-limpo, exit 0, coverage honesta ──────


def test_all_degraded_run_overall_is_not_clean_pass(
    tmp_forge_project, capsys, monkeypatch
) -> None:
    """Run all-degraded: ``overall`` NÃO é ``pass`` silencioso.

    Reproduz WR-02 vermelho: antes, dois degradeds (sem fail/warn) caíam em
    ``overall="pass"`` — host lê verde mas ZERO checagem substantiva correu.
    """
    results = [
        _ValidatorResult(name="koin", status="degraded", message="unrecognized arguments"),
        _ValidatorResult(name="ios", status="degraded", message="invalid choice: --scope"),
    ]
    code, _ = _run_json_with_results(monkeypatch, tmp_forge_project, results)
    payload = _capture_payload(capsys)

    assert payload["overall"] != "pass", (
        "run all-degraded não pode reportar overall=pass limpo — cega o overall (WR-02)"
    )
    # WR-03: o veredito AGREGADO do caso infra é `incomplete` — token DISTINTO
    # do `degraded` do contrato L1 (que tem semântica código-com-ressalva +
    # block-implement + warnings>=1). `incomplete` = "verify não pôde avaliar
    # tudo; não-bloqueante; não dispara block-forge-implement".
    assert payload["overall"] == "incomplete"
    # H-001 / Decisão 23: degraded ≠ fail → exit-code NÃO vira hard-fail.
    assert code == 0
    assert payload["exit_code"] == 0


def test_all_degraded_payload_exposes_infra_degraded_flag(
    tmp_forge_project, capsys, monkeypatch
) -> None:
    """O host deve poder branchar SEM varrer ``validators[]``: o payload expõe
    uma flag/contagem de degraded saliente no topo."""
    results = [
        _ValidatorResult(name="koin", status="degraded", message="off-contract"),
        _ValidatorResult(name="ios", status="degraded", message="off-contract"),
    ]
    _run_json_with_results(monkeypatch, tmp_forge_project, results)
    payload = _capture_payload(capsys)

    assert payload.get("infra_degraded") == 2, (
        "payload deve expor infra_degraded saliente no topo (WR-02)"
    )


def test_all_degraded_coverage_summary_is_honest(
    tmp_forge_project, capsys, monkeypatch
) -> None:
    """coverage_summary num run all-degraded: ``0 substantivos / N degradados``,
    não um zero mudo que parece "nada a verificar = ok"."""
    results = [
        _ValidatorResult(name="koin", status="degraded", message="off-contract"),
        _ValidatorResult(name="ios", status="degraded", message="off-contract"),
    ]
    _run_json_with_results(monkeypatch, tmp_forge_project, results)
    payload = _capture_payload(capsys)

    cs = payload["coverage_summary"]
    assert cs["substantive"] == 0
    # A degradação tem que aparecer no summary — não só nos validators[].
    assert cs.get("degraded") == 2, (
        "coverage_summary deve contar os degradados (0 substantivos / N degradados)"
    )


# ── run misto (alguns pass substantivos + alguns degraded) ───────────────────


def test_mixed_substantive_and_degraded_overall_signals_not_all_verified(
    tmp_forge_project, capsys, monkeypatch
) -> None:
    """Run misto: alguns pass-substantivos + alguns degraded. O overall (ou uma
    flag saliente) reflete que NEM TUDO foi verificado."""
    results = [
        _ValidatorResult(name="ok-a", status="pass", coverage="substantive"),
        _ValidatorResult(name="ok-b", status="pass", coverage="substantive"),
        _ValidatorResult(name="koin", status="degraded", message="off-contract"),
    ]
    code, _ = _run_json_with_results(monkeypatch, tmp_forge_project, results)
    payload = _capture_payload(capsys)

    # overall não é pass-limpo: há infra que não foi verificada (WR-03: incomplete).
    assert payload["overall"] != "pass"
    assert payload["overall"] == "incomplete"
    # E a saliência no topo permite o host branchar sem varrer o array.
    assert payload.get("infra_degraded") == 1
    assert payload["coverage_summary"]["substantive"] == 2
    assert payload["coverage_summary"].get("degraded") == 1
    # Ainda não é fail (código não reprovou) → exit 0.
    assert code == 0


def test_clean_substantive_run_stays_plain_pass(
    tmp_forge_project, capsys, monkeypatch
) -> None:
    """Guard-rail: sem degraded, o overall continua ``pass`` e infra_degraded=0
    — o fix não pode introduzir falso-degradado num run limpo."""
    results = [
        _ValidatorResult(name="ok-a", status="pass", coverage="substantive"),
        _ValidatorResult(name="ok-b", status="pass", coverage="substantive"),
    ]
    code, _ = _run_json_with_results(monkeypatch, tmp_forge_project, results)
    payload = _capture_payload(capsys)

    assert payload["overall"] == "pass"
    assert payload.get("infra_degraded") == 0
    assert code == 0


# ── breakdown carrega a contagem de degraded ─────────────────────────────────


def test_coverage_breakdown_counts_degraded() -> None:
    """``_coverage_breakdown`` passa a contar degradados (chave estável), sem
    misturá-los com as classes de pass-coverage."""
    results = [
        _ValidatorResult(name="a", status="pass", coverage="substantive"),
        _ValidatorResult(name="b", status="degraded"),
        _ValidatorResult(name="c", status="degraded"),
        _ValidatorResult(name="d", status="warn"),
    ]
    breakdown = _coverage_breakdown(results)
    assert breakdown["substantive"] == 1
    assert breakdown["degraded"] == 2
    # degraded não polui as classes de pass-coverage.
    assert breakdown["stub"] == 0
    assert breakdown["staged-blind"] == 0
    assert breakdown["opaque"] == 0


# ── WR-03: `incomplete` é um result válido distinto de `degraded` no L1 ───────


def _seed_l1_feature(project_root: Path, slug: str) -> None:
    """Cria o diretório L1 mínimo da feature pra append_verify_log escrever."""
    from engine.memory.l1 import L1State, write_l1_status

    write_l1_status(
        L1State(
            feature_slug=slug,
            status="verifying",
            last_action_at="2026-06-29T00:00:00Z",
            last_action_kind="verify-started",
        ),
        project_root,
    )


def test_append_verify_log_accepts_incomplete_with_zero_warnings(
    tmp_forge_project,
) -> None:
    """WR-03: o contrato L1 ACEITA result==`incomplete` mesmo com warnings==0.

    `incomplete` (infra/off-contract, não-bloqueante) é DISTINTO de `degraded`
    (código-com-ressalva, exige warnings>=1, block-implement). Um run all-infra-
    degradado emite overall=`incomplete` com warnings=0 — append_verify_log NÃO
    pode levantar MemoryError nesse caso.
    """
    slug = "demo-feature"
    _seed_l1_feature(tmp_forge_project, slug)
    entry = {
        "schema-version": 1,
        "verify-id": "verify-20260629T000000Z",
        "at": "2026-06-29T00:00:00Z",
        "scope": "task",
        "validators-run": ["koin", "ios"],
        "result": "incomplete",
        "warnings": 0,
    }
    # Não deve levantar — `incomplete` é result válido (MEM-L1-VL-004 estendido).
    append_verify_log(slug, tmp_forge_project, entry)


def test_append_verify_log_degraded_still_requires_warnings(
    tmp_forge_project,
) -> None:
    """WR-03 guard: o `degraded` do L1 NÃO mudou — segue exigindo warnings>=1
    (MEM-L1-VL-005). O novo `incomplete` não relaxa essa regra."""
    slug = "demo-feature"
    _seed_l1_feature(tmp_forge_project, slug)
    entry = {
        "schema-version": 1,
        "verify-id": "verify-20260629T000001Z",
        "at": "2026-06-29T00:00:01Z",
        "scope": "task",
        "validators-run": ["x"],
        "result": "degraded",
        "warnings": 0,
    }
    with pytest.raises(L1MemoryError):
        append_verify_log(slug, tmp_forge_project, entry)
