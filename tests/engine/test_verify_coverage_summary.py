"""BUG-VERIFY-2 (Onda 1, T3): sumário honesto de cobertura.

O ``forge verify`` reportava só "Pass: N" — mas nem todo pass é igual. Um
validator pode:

  - examinar artefatos reais e aprová-los          → ``substantive``
  - ser um stub/no-op que sempre passa             → ``stub``
  - passar porque NADA estava no escopo pra checar  → ``staged-blind`` (vacuous)
  - passar só pela exit-code contract (sem JSON)    → ``opaque`` (não-declarado)

Sem distinguir, "verde" mente: 10 passes podem ser 6 stub + 4 staged-blind e
zero substância. T3 faz o verify reportar a cobertura — observável no --json.

ACK M-001: este teste cobre AS TRÊS categorias que o sumário distingue —
``substantive``, ``stub`` E ``staged-blind`` — porque sem cobrir staged-blind
o gate fica near-inert (lição C5). ``opaque`` (legado, sem JSON) também é
coberto pra travar a inferência default.
"""

from __future__ import annotations

import json
from pathlib import Path

from engine.ui import output_mode as om
from engine import verify
from engine.verify import (
    _coverage_breakdown,
    _invoke_validator,
    _ValidatorResult,
    _ValidatorSpec,
)


def _write_script(tmp_path: Path, name: str, body: str) -> Path:
    script = tmp_path / name
    script.write_text(body, encoding="utf-8")
    return script


def _emit_script(tmp_path: Path, name: str, payload: dict) -> Path:
    return _write_script(
        tmp_path,
        name,
        "import argparse, sys, json\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--project-root', default='.')\n"
        "p.add_argument('--scope', default=None)\n"
        "p.add_argument('--id', default=None)\n"
        "p.parse_args()\n"
        f"print(json.dumps({payload!r}))\n"
        "sys.exit(0)\n",
    )


# ── plumbing: coverage flui do JSON payload pro _ValidatorResult ─────────────


def test_invoke_validator_threads_coverage_substantive(tmp_path: Path) -> None:
    script = _emit_script(
        tmp_path, "subst.py", {"status": "pass", "coverage": "substantive"}
    )
    res = _invoke_validator(
        _ValidatorSpec(name="subst", script_path=script),
        project_root=tmp_path,
        scope_type="feature",
        scope_target="demo",
    )
    assert res.status == "pass"
    assert res.coverage == "substantive"


def test_invoke_validator_threads_coverage_stub(tmp_path: Path) -> None:
    script = _emit_script(tmp_path, "stub.py", {"status": "pass", "coverage": "stub"})
    res = _invoke_validator(
        _ValidatorSpec(name="stub", script_path=script),
        project_root=tmp_path,
        scope_type="feature",
        scope_target="demo",
    )
    assert res.coverage == "stub"


def test_invoke_validator_threads_coverage_staged_blind(tmp_path: Path) -> None:
    """staged-blind: validator passou porque não havia nada no escopo (vacuous)."""
    script = _emit_script(
        tmp_path, "blind.py", {"status": "pass", "coverage": "staged-blind"}
    )
    res = _invoke_validator(
        _ValidatorSpec(name="blind", script_path=script),
        project_root=tmp_path,
        scope_type="feature",
        scope_target="demo",
    )
    assert res.coverage == "staged-blind"


def test_invoke_validator_exit_code_pass_is_opaque(tmp_path: Path) -> None:
    """Pass via exit-code (sem JSON tail) → coverage ``opaque``: o verify não
    consegue afirmar substância. Default honesto pra validators legados.
    """
    script = _write_script(
        tmp_path,
        "legacy.py",
        "import argparse, sys\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--project-root', default='.')\n"
        "p.add_argument('--scope', default=None)\n"
        "p.add_argument('--id', default=None)\n"
        "p.parse_args()\n"
        "sys.exit(0)\n",
    )
    res = _invoke_validator(
        _ValidatorSpec(name="legacy", script_path=script),
        project_root=tmp_path,
        scope_type="feature",
        scope_target="demo",
    )
    assert res.status == "pass"
    assert res.coverage == "opaque"


def test_non_pass_results_have_no_coverage(tmp_path: Path) -> None:
    """warn/fail/degraded não recebem classe de cobertura (N/A)."""
    script = _emit_script(
        tmp_path, "warned.py", {"status": "warn", "message": "ressalva"}
    )
    res = _invoke_validator(
        _ValidatorSpec(name="warned", script_path=script),
        project_root=tmp_path,
        scope_type="feature",
        scope_target="demo",
    )
    assert res.status == "warn"
    assert res.coverage == ""


# ── breakdown agrega os passes por categoria ─────────────────────────────────


def test_coverage_breakdown_counts_all_three_categories() -> None:
    """ACK M-001: o breakdown distingue substantive / stub / staged-blind.

    Sem cobrir staged-blind o gate ficaria near-inert (C5). Aqui as três
    categorias nomeadas + opaque estão presentes e contadas separadamente.
    """
    results = [
        _ValidatorResult(name="a", status="pass", coverage="substantive"),
        _ValidatorResult(name="b", status="pass", coverage="substantive"),
        _ValidatorResult(name="c", status="pass", coverage="stub"),
        _ValidatorResult(name="d", status="pass", coverage="staged-blind"),
        _ValidatorResult(name="e", status="pass", coverage="opaque"),
        _ValidatorResult(name="f", status="warn"),
        _ValidatorResult(name="g", status="fail"),
    ]
    breakdown = _coverage_breakdown(results)
    assert breakdown["substantive"] == 2
    assert breakdown["stub"] == 1
    assert breakdown["staged-blind"] == 1
    assert breakdown["opaque"] == 1
    # warn/fail não entram em nenhuma categoria de pass-coverage.
    assert sum(breakdown.values()) == 5  # só os 5 passes


# ── observável no --json (gate de aceite, spec linha 106) ────────────────────


def _seed_config(project_root: Path) -> Path:
    forge_dir = project_root / ".claude" / "forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / "forge-config.yaml").write_text(
        "schema-version: 1\nidentity:\n  project-name: demo\n",
        encoding="utf-8",
    )
    return project_root


def test_json_output_exposes_coverage_summary(
    tmp_forge_project, capsys, monkeypatch
) -> None:
    """O --json expõe coverage por-validator E um coverage_summary agregado.

    Reproduz BUG-VERIFY-2 vermelho ANTES: sem o campo, um host (IA-first) não
    tem como distinguir pass-substantivo de stub/staged-blind no payload.
    """
    _seed_config(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)
    token = om.set_output_mode(om.OutputMode.JSON)
    try:
        code = verify.run([])
    finally:
        om.reset_output_mode(token)
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert "coverage_summary" in payload, "payload deve expor coverage_summary agregado"
    cs = payload["coverage_summary"]
    # As três categorias nomeadas + opaque são chaves estáveis do summary.
    for key in ("substantive", "stub", "staged-blind", "opaque"):
        assert key in cs, f"coverage_summary deve ter a chave {key!r}"
    # Cada validator individual carrega seu campo coverage.
    for v in payload["validators"]:
        assert "coverage" in v, "cada validator deve carregar o campo coverage"
