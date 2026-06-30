"""BUG-VERIFY-1 regression (Onda 1, T1): um validator QUEBRADO/OFF-CONTRACT
não pode cegar a cascade.

Invariante de detection (ACK H-001, Caminho A): quando um validator sai com
exit 2 — o sinal de argparse para *unrecognized arguments* / *invalid choice*,
i.e. o script está quebrado ou fora do contrato canônico (``--project-root`` /
``--scope`` / ``--id``) — isso é falha de INFRAESTRUTURA do validator, NÃO
código reprovado.

Logo:

  - O veredito é ``degraded`` (distinto de ``fail`` = código reprovado e de
    ``warn`` = código com ressalva). ``degraded`` NÃO conta pro overall e NÃO
    para a cascade fail-fast (Decisão 23 — fail-fast só morde em ``fail``).
  - É explicitamente NÃO ``warn``: ``warn`` conta no overall (vira
    ``overall="warn"``) e mascararia o problema de infra como ressalva de
    código. O anti-padrão exit-2→``warn`` está banido por este teste.

Este arquivo é a GUARDA EXECUTÁVEL dessa fronteira. O comentário-âncora
durável vive em ``engine/verify.py`` no ramo do fix.
"""

from __future__ import annotations

from pathlib import Path

from engine.verify import _invoke_validator, _run_cascade, _ValidatorSpec


def _write_script(tmp_path: Path, name: str, body: str) -> Path:
    script = tmp_path / name
    script.write_text(body, encoding="utf-8")
    return script


# ── exit 2 (broken / off-contract) → degraded, never fail, never warn ────────


def test_invoke_validator_exit2_argparse_error_is_degraded(tmp_path: Path) -> None:
    """Um validator que rejeita os flags canônicos (argparse → exit 2, sem JSON
    tail) é INFRA quebrada → ``degraded``, não ``fail`` nem ``warn``.

    Reproduz BUG-VERIFY-1: ``check-koin-modules.py`` só aceitava ``--root``;
    invocado pelo verify com ``--project-root``/``--scope``/``--id`` estourava
    argparse (exit 2) e era classificado como ``fail`` — cegando a cascade.
    """
    # argparse com allow_abbrev e sem os flags canônicos: ao receber
    # --project-root/--scope/--id estoura "unrecognized arguments" → exit 2.
    script = _write_script(
        tmp_path,
        "broken_validator.py",
        "import argparse, sys\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--root', default='.')\n"
        "p.parse_args()\n"
        "sys.exit(0)\n",
    )
    spec = _ValidatorSpec(name="broken", script_path=script)

    result = _invoke_validator(
        spec, project_root=tmp_path, scope_type="feature", scope_target="demo"
    )

    assert result.status == "degraded", (
        "validator off-contract (exit 2) deve ser degraded — infra quebrada, "
        f"não código reprovado; got {result.status!r}"
    )
    # Banir explicitamente o anti-padrão exit-2→warn (warn conta no overall).
    assert result.status != "warn"
    assert result.status != "fail"


def test_invoke_validator_genuine_fail_via_json_still_fails(tmp_path: Path) -> None:
    """Guard-rail: um validator que roda OK e emite ``{"status":"fail"}`` no JSON
    tail continua ``fail`` (código reprovado).

    Esse é o canal canônico de hard fail (``_common.emit_and_exit`` retorna
    exit 1 + JSON ``status=fail``). A correção do exit-2 não pode tocar nesse
    caminho — o veredito vem do JSON, não do exit code.
    """
    script = _write_script(
        tmp_path,
        "failing_validator.py",
        "import argparse, sys, json\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--project-root', default='.')\n"
        "p.add_argument('--scope', default=None)\n"
        "p.add_argument('--id', default=None)\n"
        "p.parse_args()\n"
        "print(json.dumps({'status': 'fail', 'message': 'boom'}))\n"
        "sys.exit(1)\n",
    )
    spec = _ValidatorSpec(name="failing", script_path=script)

    result = _invoke_validator(
        spec, project_root=tmp_path, scope_type="feature", scope_target="demo"
    )
    assert result.status == "fail"


# ── cascade não para num degraded — os validators a jusante rodam ────────────


def test_cascade_does_not_halt_on_degraded_validator(tmp_path: Path) -> None:
    """Cascade fail-fast NÃO para num validator ``degraded`` (exit 2).

    Reproduz o coração do BUG-VERIFY-1: o validator quebrado vinha primeiro,
    virava ``fail``, e os 5 validators iOS/KMP a jusante ficavam ``skipped``.
    Com o fix (``degraded``), os downstream rodam normalmente.
    """
    broken = _write_script(
        tmp_path,
        "broken_first.py",
        "import argparse, sys\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--root', default='.')\n"
        "p.parse_args()\n"
        "sys.exit(0)\n",
    )
    healthy = _write_script(
        tmp_path,
        "healthy_second.py",
        "import argparse, sys\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--project-root', default='.')\n"
        "p.add_argument('--scope', default=None)\n"
        "p.add_argument('--id', default=None)\n"
        "p.parse_args()\n"
        "sys.exit(0)\n",
    )
    specs = [
        _ValidatorSpec(name="broken-first", script_path=broken),
        _ValidatorSpec(name="healthy-second", script_path=healthy),
    ]

    results = _run_cascade(
        specs,
        fail_fast=True,
        project_root=tmp_path,
        interactive=False,
        scope_type="feature",
        scope_target="demo",
    )

    by_name = {r.name: r for r in results}
    assert by_name["broken-first"].status == "degraded"
    # O downstream NÃO pode estar skipped — a cascade seguiu apesar do degraded.
    assert by_name["healthy-second"].status != "skipped", (
        "validator a jusante foi cegado — cascade parou num degraded (BUG-VERIFY-1)"
    )
    assert by_name["healthy-second"].status == "pass"


def test_cascade_still_halts_on_genuine_fail(tmp_path: Path) -> None:
    """Guard-rail: a cascade AINDA para num ``fail`` genuíno (Decisão 23).

    O hard fail canônico vem do JSON tail ``{"status":"fail"}`` — é o que para
    a cascade; a correção do exit-2 não pode afrouxar isso.
    """
    failing = _write_script(
        tmp_path,
        "fail_first.py",
        "import argparse, sys, json\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--project-root', default='.')\n"
        "p.add_argument('--scope', default=None)\n"
        "p.add_argument('--id', default=None)\n"
        "p.parse_args()\n"
        "print(json.dumps({'status': 'fail', 'message': 'boom'}))\n"
        "sys.exit(1)\n",
    )
    downstream = _write_script(
        tmp_path,
        "down.py",
        "import argparse, sys\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--project-root', default='.')\n"
        "p.add_argument('--scope', default=None)\n"
        "p.add_argument('--id', default=None)\n"
        "p.parse_args()\n"
        "sys.exit(0)\n",
    )
    specs = [
        _ValidatorSpec(name="fail-first", script_path=failing),
        _ValidatorSpec(name="downstream", script_path=downstream),
    ]
    results = _run_cascade(
        specs,
        fail_fast=True,
        project_root=tmp_path,
        interactive=False,
        scope_type="feature",
        scope_target="demo",
    )
    by_name = {r.name: r for r in results}
    assert by_name["fail-first"].status == "fail"
    assert by_name["downstream"].status == "skipped", (
        "fail genuíno deve parar a cascade (fail-fast Decisão 23)"
    )
