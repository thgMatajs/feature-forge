"""Unit — content-check helper (Onda 2 — gates com dentes).

Reproduz os DOIS escapes do piloto MeoBonsai que passaram pelo gate
procedural de wave:

1. **tech-spec.md** renderizado-cru com §3-§7 ainda em stubs ``{{...}}``
   (placeholder-scan — forma de L2 do plan-auditor).
2. **task-breakdown.yaml** com ``dependency_graph.edges: []`` /
   ``critical_path: []`` / ``totals.tasks_count: 0`` enquanto ``tasks:`` tem
   ≥2 entradas reais (substance-coverage — forma de C2/M2 do plan-auditor).

Acks do plan-auditor cobertos aqui:
- **H-001:** a regra de placeholder NÃO é ``grep -v '^#'`` (deixaria o gate
  near-inert — 64/65 tokens do template vivem em linhas NÃO-comentadas). A
  regra correta remove o COMENTÁRIO TRAILING e checa ``{{...}}`` na parte
  não-comentada. Os dois casos são testados: stub-com-comentário-trailing é
  PEGO; linha puramente-ilustrativa (``# ex.: {{x}}``) é IGNORADA.
- **M-002:** YAML PRESENTE mas MALFORMADO degrada-soft (finding ``substance``
  amigável, NÃO crasha).
"""

from __future__ import annotations

from pathlib import Path

from engine.plan_content_check import (
    ContentFinding,
    check_artefacts,
    check_task_breakdown,
    scan_placeholders,
)


# ── scan_placeholders (forma de L2) ──────────────────────────────────────────


def test_scan_placeholders_catches_residual_tokens():
    """Stub ``{{...}}`` numa linha de código (não-comentada) é PEGO."""
    text = 'backend: "{{backend_provider}}"\nfoo: 1\n'
    hits = scan_placeholders(text)
    assert any("backend_provider" in h for h in hits), (
        f"placeholder substantivo deve ser detectado; got {hits!r}"
    )


def test_scan_placeholders_ignores_token_inside_trailing_comment():
    """H-001: ``# ex.: {{slug}}`` (token só no comentário trailing) é IGNORADO.

    Senão o gate auto-dispara nos exemplos legítimos dos próprios templates
    (lição C5 — gate near-inert ao contrário: aqui seria gate-histérico).
    """
    text = 'allowed_files: []                # ex.: ["src/{{slug}}/**"]\n'
    hits = scan_placeholders(text)
    assert hits == [], (
        f"token DENTRO do comentário trailing não é stub; got {hits!r}"
    )


def test_scan_placeholders_catches_stub_with_trailing_comment():
    """H-001 (par crítico): placeholder substantivo ANTES do ``# ex.:`` É pego.

    ``backend: "{{x}}"  # ex.: "firebase"`` — o ``{{x}}`` está na parte
    NÃO-comentada; o ``# ex.:`` é só ilustração. O gate DEVE pegar o stub
    real, não ser cegado pelo comentário na mesma linha.
    """
    text = 'backend: "{{backend_provider}}"  # ex.: "firebase" | "rest-api"\n'
    hits = scan_placeholders(text)
    assert any("backend_provider" in h for h in hits), (
        "placeholder substantivo antes do comentário trailing deve ser pego "
        f"— senão o gate fica near-inert (lição C5); got {hits!r}"
    )


def test_scan_placeholders_ignores_fully_commented_line():
    """Linha puramente comentada (``# Tech Spec — {{name}}``) é ignorada."""
    text = "# Tech Spec — {{feature_human_name}}\n"
    assert scan_placeholders(text) == []


def test_scan_placeholders_ignores_todo_tbd_fixme_in_prose():
    """M-01: ``TODO``/``TBD``/``FIXME`` em prosa legítima NÃO dispara o gate.

    Diferente do ``{{...}}`` (inequivocamente token de template), TBD/TODO/
    FIXME são palavras ambíguas em texto livre PT/EN. "A decisão está TBD" é
    prosa substantiva e honesta — flagá-la é gate-histérico. Confiamos no
    placeholder-scan (``{{...}}``) + substance-coverage, não em marcador-em-prosa.
    """
    for text in (
        "A decisão está TBD pendente de aprovação.\n",
        "Adicionar suporte FIXME no backend.\n",
        "## Seção 3\nTODO: preencher os ViewModels\n",
    ):
        assert scan_placeholders(text) == [], (
            f"marcador em prosa NÃO deve disparar (M-01); text={text!r}"
        )


def test_scan_placeholders_clean_text_has_no_hits():
    """Texto totalmente preenchido → 0 hits (happy-path / regressão)."""
    text = 'backend: "firebase-firestore"\nlayers: ["shared", "android"]\n'
    assert scan_placeholders(text) == []


# ── check_task_breakdown (forma de C2/M2) ────────────────────────────────────


def _write_breakdown(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_check_task_breakdown_empty_dag_with_multiple_tasks_is_caught(tmp_path: Path):
    """2º escape do piloto: DAG vazio com ≥2 tasks reais → finding substance."""
    body = (
        "tasks:\n"
        "  - id: TASK-0001\n"
        "    title: primeira\n"
        "  - id: TASK-0002\n"
        "    title: segunda\n"
        "dependency_graph:\n"
        "  edges: []\n"
        "  topological_order: []\n"
        "critical_path: []\n"
        "totals:\n"
        "  tasks_count: 0\n"
    )
    path = _write_breakdown(tmp_path / "task-breakdown.yaml", body)
    findings = check_task_breakdown(path)
    assert any(f.category == "substance" for f in findings), (
        f"DAG vazio com 2 tasks deve gerar finding substance; got {findings!r}"
    )


def test_check_task_breakdown_single_task_empty_dag_is_legit(tmp_path: Path):
    """Single-task feature: DAG vazio é LEGÍTIMO → 0 findings substance."""
    body = (
        "tasks:\n"
        "  - id: TASK-0001\n"
        "    title: única\n"
        "dependency_graph:\n"
        "  edges: []\n"
        "  topological_order: []\n"
        "critical_path: []\n"
        "totals:\n"
        "  tasks_count: 1\n"
    )
    path = _write_breakdown(tmp_path / "task-breakdown.yaml", body)
    findings = check_task_breakdown(path)
    assert not any(f.category == "substance" for f in findings), (
        f"single-task com DAG vazio é legítimo; got {findings!r}"
    )


def test_check_task_breakdown_populated_dag_has_no_substance_finding(tmp_path: Path):
    """DAG coerente com tasks → 0 findings substance (happy-path)."""
    body = (
        "tasks:\n"
        "  - id: TASK-0001\n"
        "    title: primeira\n"
        "  - id: TASK-0002\n"
        "    title: segunda\n"
        "dependency_graph:\n"
        "  edges:\n"
        "    - {from: TASK-0001, to: TASK-0002}\n"
        "  topological_order: [TASK-0001, TASK-0002]\n"
        "critical_path: [TASK-0001, TASK-0002]\n"
        "totals:\n"
        "  tasks_count: 2\n"
    )
    path = _write_breakdown(tmp_path / "task-breakdown.yaml", body)
    findings = check_task_breakdown(path)
    assert not any(f.category == "substance" for f in findings), (
        f"DAG populado não deve gerar finding substance; got {findings!r}"
    )


def test_check_task_breakdown_malformed_yaml_degrades_soft(tmp_path: Path):
    """M-002: YAML PRESENTE mas MALFORMADO degrada-soft (não crasha).

    Emite um finding ``substance`` amigável (tratado como incompleto-pausa
    no wiring), em vez de propagar YamlIOError pro pipeline.
    """
    body = "tasks:\n  - id: TASK-0001\n   bad-indent: : :\n"
    path = _write_breakdown(tmp_path / "task-breakdown.yaml", body)
    findings = check_task_breakdown(path)  # NÃO deve levantar
    assert findings, "YAML malformado deve gerar ≥1 finding (degrade-soft)"
    assert all(isinstance(f, ContentFinding) for f in findings)


def test_check_task_breakdown_missing_file_is_finding_not_crash(tmp_path: Path):
    """Artefato ausente no disco → finding missing (não crasha)."""
    path = tmp_path / "task-breakdown.yaml"  # nunca escrito
    findings = check_task_breakdown(path)
    assert any(f.category == "missing" for f in findings), (
        f"arquivo ausente deve gerar finding missing; got {findings!r}"
    )


# ── check_artefacts (dispatch por extensão/nome) ─────────────────────────────


def test_check_artefacts_partial_tech_spec_is_caught(tmp_path: Path):
    """1º escape do piloto: tech-spec.md cru (§3-§7 stub) é PEGO via .md scan."""
    spec = tmp_path / "tech-spec.md"
    spec.write_text(
        '## §3 ViewModels\nclass {{ConceptViewModel}}\n## §7 Riscos\n{{new_risk_1}}\n',
        encoding="utf-8",
    )
    findings = check_artefacts("C", [spec])
    assert any(f.category == "placeholder" for f in findings), (
        f"tech-spec parcial deve gerar finding placeholder; got {findings!r}"
    )


def test_check_artefacts_complete_tech_spec_is_clean(tmp_path: Path):
    """tech-spec.md totalmente preenchido → 0 findings (happy-path)."""
    spec = tmp_path / "tech-spec.md"
    spec.write_text(
        "## §3 ViewModels\nclass ConceptViewModel\n## §7 Riscos\nFirestore index ausente\n",
        encoding="utf-8",
    )
    assert check_artefacts("C", [spec]) == []


def test_check_artefacts_wave_a_is_exempt_from_dag_substance(tmp_path: Path):
    """Wave A (intake) é EXENTA do substance-check de DAG.

    Um task-breakdown.yaml com DAG vazio só dispara na wave que o produz
    (Wave D), não no intake.
    """
    bd = tmp_path / "task-breakdown.yaml"
    bd.write_text(
        "tasks:\n  - id: TASK-0001\n  - id: TASK-0002\n"
        "dependency_graph:\n  edges: []\ncritical_path: []\n",
        encoding="utf-8",
    )
    findings = check_artefacts("A", [bd])
    assert not any(f.category == "substance" for f in findings), (
        f"Wave A não roda substance-check de DAG; got {findings!r}"
    )


def test_check_artefacts_wave_a_intake_literal_placeholder_does_not_fire(tmp_path: Path):
    """H-01: Wave A (intake free-text) é EXENTA do placeholder-scan de ``.md``.

    O ``source-ref`` do feature-intake.md carrega o argv CRU do usuário; um
    ``{{...}}`` LITERAL ali (feature de templating/i18n) é texto legítimo, não
    stub residual. A Wave A é intake — os escapes do piloto foram em tech-spec
    (Wave C) e task-breakdown (Wave D), não no intake. O gate NÃO deve disparar.
    """
    intake = tmp_path / "feature-intake.md"
    intake.write_text(
        "# Intake bonsai\n- source-ref: add {{screenshots_count}} widget\n",
        encoding="utf-8",
    )
    findings = check_artefacts("A", [intake])
    assert findings == [], (
        f"intake com {{{{...}}}} literal no source-ref NÃO deve disparar o gate "
        f"(gate-histérico — inverso da lição C5); got {findings!r}"
    )


def test_check_artefacts_wave_c_literal_placeholder_still_fires(tmp_path: Path):
    """Contraprova de H-01: a isenção é SÓ da Wave A — Wave C ainda escaneia.

    O mesmo token literal numa tech-spec da Wave C É um stub residual real (o
    escape do piloto). A isenção não pode vazar pras waves estruturadas.
    """
    spec = tmp_path / "tech-spec.md"
    spec.write_text(
        "## §3 ViewModels\nbackend: {{screenshots_count}}\n", encoding="utf-8"
    )
    findings = check_artefacts("C", [spec])
    assert any(f.category == "placeholder" for f in findings), (
        f"Wave C (estruturada) ainda deve pegar o stub residual; got {findings!r}"
    )


def test_check_artefacts_dispatches_task_breakdown_substance_on_wave_d(tmp_path: Path):
    """Wave D: task-breakdown.yaml com DAG vazio (≥2 tasks) gera substance."""
    bd = tmp_path / "task-breakdown.yaml"
    bd.write_text(
        "tasks:\n  - id: TASK-0001\n  - id: TASK-0002\n"
        "dependency_graph:\n  edges: []\ntopological_order: []\ncritical_path: []\n",
        encoding="utf-8",
    )
    findings = check_artefacts("D", [bd])
    assert any(f.category == "substance" for f in findings), (
        f"Wave D deve rodar substance-check; got {findings!r}"
    )


def test_check_artefacts_missing_artefact_is_finding(tmp_path: Path):
    """Artefato listado mas ausente no disco → finding missing (não crasha)."""
    missing = tmp_path / "tech-spec.md"  # nunca escrito
    findings = check_artefacts("C", [missing])
    assert any(f.category == "missing" for f in findings)
