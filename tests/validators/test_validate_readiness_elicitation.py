"""needs-elicitation scan no validate_readiness (Wave 1 C5).

Block-severity quando `needs-elicitation: true` sobrevive não-promovido em
contract spec; warning em narrativa.

Cobre dois níveis:
- **Isolado:** `_scan_needs_elicitation` flagueia o MARKER ATIVO (campo/valor
  YAML estruturado) em `*-spec.yaml`, `task-breakdown.yaml` e `tasks/*.yaml`,
  ignora a prose instrucional dos templates (comentários YAML), e retorna `[]`
  quando o artefato não carrega o marker.
- **Integração (prova de wiring):** `validate()` retorna `result_fail` mesmo
  com verdict nominal `ready` quando há `needs-elicitation` não-promovido —
  provando que o scan preempta o parse do verdict — e o caso espelho
  (`ready` + sem marker → `result_pass`, sem regressão).

Refs: docs/superpowers/specs/2026-06-17-ai-first-interaction-layer-design.md §4 C5
"""

from __future__ import annotations

from pathlib import Path

from validators import validate_readiness


# ── Isolado — _scan_needs_elicitation ────────────────────────────────────────


def test_scan_flags_needs_elicitation_in_contract(tmp_path: Path) -> None:
    f_root = tmp_path
    spec = f_root / "data-contract-spec.yaml"
    spec.write_text(
        "fields:\n  - name: starred\n    persist: needs-elicitation\n",
        encoding="utf-8",
    )
    hits = validate_readiness._scan_needs_elicitation(f_root)
    assert any("data-contract-spec.yaml" in h for h in hits)


def test_scan_clean_when_no_marker(tmp_path: Path) -> None:
    f_root = tmp_path
    (f_root / "data-contract-spec.yaml").write_text(
        "fields:\n  - name: starred\n    persist: true\n",
        encoding="utf-8",
    )
    assert validate_readiness._scan_needs_elicitation(f_root) == []


def test_scan_flags_needs_elicitation_in_task_contract(tmp_path: Path) -> None:
    """BL-001 — o glob novo (`tasks/*.yaml`) pega task contracts.

    O task contract (`tasks/TASK-NNNN.yaml`) é o artefato mais propenso a
    carregar o campo não-promovido na cadeia story→task (spec C5). O glob
    antigo (`tasks/task-*.md`, lowercase + `.md`) casava NADA num FS
    case-sensitive — este teste prova que o novo glob fecha o ponto-cego.
    """
    f_root = tmp_path
    tasks = f_root / "tasks"
    tasks.mkdir()
    (tasks / "TASK-0001.yaml").write_text(
        "task_id: TASK-0001\nfields:\n  - name: reminder_time\n"
        "    default: needs-elicitation\n",
        encoding="utf-8",
    )
    hits = validate_readiness._scan_needs_elicitation(f_root)
    assert any("TASK-0001.yaml" in h for h in hits), (
        f"task contract deveria ser flagueado; hits={hits}"
    )


def test_scan_flags_needs_elicitation_in_breakdown(tmp_path: Path) -> None:
    """BL-001 — `task-breakdown.yaml` (root) entra no glob novo."""
    f_root = tmp_path
    (f_root / "task-breakdown.yaml").write_text(
        "tasks:\n  - id: TASK-0001\n    estimate: needs-elicitation\n",
        encoding="utf-8",
    )
    hits = validate_readiness._scan_needs_elicitation(f_root)
    assert any("task-breakdown.yaml" in h for h in hits), (
        f"breakdown deveria ser flagueado; hits={hits}"
    )


def test_scan_does_not_flag_template_prose_comment(tmp_path: Path) -> None:
    """BL-002 (regression guard) — comentário YAML instrucional NÃO flagueia.

    O `ui-state-spec.template.yaml` carrega a palavra `needs-elicitation` em
    comentários (prose de como usar o campo). Renderizado pra `ui-state-spec.yaml`,
    esses comentários casam o glob `*-spec.yaml`. Com substring puro (o bug),
    TODA feature real dispararia false-positive. O match estruturado +
    comment-strip deve ignorar a prose.

    A linha abaixo é a linha 11 REAL do template — fonte do bug.
    """
    f_root = tmp_path
    (f_root / "ui-state-spec.yaml").write_text(
        "schema_version: 1\n"
        "feature_slug: lembrete-rega\n"
        "# Regras absolutas:\n"
        "#   1. Toda screen declara TODOS os 7 base states. Estado sem evidência →\n"
        "#      confirmed: false + needs-elicitation: true + open-question id.\n"
        "#   3. Toda transition cita source. `inferred` SEMPRE pareado com needs-elicitation.\n"
        "screens: []\n",
        encoding="utf-8",
    )
    assert validate_readiness._scan_needs_elicitation(f_root) == [], (
        "comentário instrucional do template NÃO deveria disparar o scan"
    )


def test_scan_flags_both_active_forms(tmp_path: Path) -> None:
    """BL-002 — ambas as formas ATIVAS do marker flagueiam.

    Forma-valor (`campo: needs-elicitation`) e forma-chave
    (`needs-elicitation: true`) são markers reais; ambas devem ser pegas,
    enquanto a menção em prose (comentário) acima da chave não conta.
    """
    f_root = tmp_path
    (f_root / "navigation-spec.yaml").write_text(
        "transitions:\n"
        "  - from: idle\n"
        "    source: needs-elicitation\n"  # forma-valor
        "states:\n"
        "  # nota: estados sem source viram needs-elicitation\n"  # prose — ignora
        "  - name: error\n"
        "    needs-elicitation: true\n",  # forma-chave
        encoding="utf-8",
    )
    hits = validate_readiness._scan_needs_elicitation(f_root)
    # Exatamente 2 markers ativos (linhas 3 e 7); o comentário (linha 5) não conta.
    assert len(hits) == 2, f"esperado 2 markers ativos, got {hits}"
    linenos = sorted(int(h.rsplit(":", 1)[1]) for h in hits)
    assert linenos == [3, 7], f"markers nas linhas erradas: {hits}"


def test_scan_truthy_only_for_key_form(tmp_path: Path) -> None:
    """`needs-elicitation: false` (já resolvido) não flagueia na forma-chave.

    Quando o conductor resolve o campo, o marker vira `false` — não deve
    bloquear. A forma-chave só dispara em valores truthy (true/yes/1).
    """
    f_root = tmp_path
    (f_root / "analytics-spec.yaml").write_text(
        "events:\n  - name: open\n    needs-elicitation: false\n",
        encoding="utf-8",
    )
    assert validate_readiness._scan_needs_elicitation(f_root) == []


# ── Integração — scan preempta o parse do verdict em validate() ──────────────


def _write_ready_review(f_root: Path) -> None:
    """Escreve um implementation-readiness-review.md com verdict `ready`.

    Mirror de tests/unit/test_validators_readiness.py
    ::test_review_md_with_ready_verdict_passes — o caminho canônico que
    `validate()` parseia pra um result_pass.
    """
    (f_root / "implementation-readiness-review.md").write_text(
        "# Readiness review\n\n"
        "```yaml\n"
        "readiness_verdict:\n"
        "  status: ready\n"
        "  blockers: []\n"
        "  warnings: []\n"
        "```\n",
        encoding="utf-8",
    )


def test_validate_blocks_needs_elicitation_even_with_ready_verdict(
    tmp_forge_project: Path,
) -> None:
    """Verdict nominal `ready` NÃO mascara um contract spec não-elicitado.

    O scan roda no topo de validate(), antes do parse do verdict — então um
    needs-elicitation não-promovido força fail mesmo quando o verdict diz ready.
    """
    slug = "thin-but-complete"
    f_root = (
        tmp_forge_project
        / "docs"
        / "feature-implementation-workflow"
        / "features"
        / slug
    )
    f_root.mkdir(parents=True)
    _write_ready_review(f_root)
    # Contract spec com needs-elicitation não-promovido sobrevive até o readiness.
    (f_root / "data-contract-spec.yaml").write_text(
        "fields:\n  - name: starred\n    persist: needs-elicitation\n",
        encoding="utf-8",
    )

    result = validate_readiness.validate(tmp_forge_project, scope="feature", id=slug)
    assert result["status"] == "fail"
    assert len(result["paths"]) == 3
    assert "needs-elicitation" in result.get("what-failed", "")


def test_validate_blocks_needs_elicitation_in_task_contract(
    tmp_forge_project: Path,
) -> None:
    """Integração BL-001 — marker num task contract bloqueia mesmo com ready.

    Espelha o cenário central do C5: a cadeia story→task fecha nominalmente
    (verdict ready) mas o task contract carrega um campo não-elicitado.
    """
    slug = "task-leak"
    f_root = (
        tmp_forge_project
        / "docs"
        / "feature-implementation-workflow"
        / "features"
        / slug
    )
    (f_root / "tasks").mkdir(parents=True)
    _write_ready_review(f_root)
    (f_root / "tasks" / "TASK-0001.yaml").write_text(
        "task_id: TASK-0001\nfields:\n  - name: reminder_time\n"
        "    default: needs-elicitation\n",
        encoding="utf-8",
    )

    result = validate_readiness.validate(tmp_forge_project, scope="feature", id=slug)
    assert result["status"] == "fail"
    assert "needs-elicitation" in result.get("what-failed", "")
    assert "TASK-0001.yaml" in result.get("where", "")


def test_validate_ready_with_template_prose_passes(
    tmp_forge_project: Path,
) -> None:
    """Integração BL-002 — spec renderizado com prose de template NÃO bloqueia.

    Um `ui-state-spec.yaml` que herda os comentários instrucionais do template
    (a prose com a palavra `needs-elicitation`) mas sem marker ativo deve
    passar o readiness — senão TODA feature real falharia o gate.
    """
    slug = "prose-only-feature"
    f_root = (
        tmp_forge_project
        / "docs"
        / "feature-implementation-workflow"
        / "features"
        / slug
    )
    f_root.mkdir(parents=True)
    _write_ready_review(f_root)
    (f_root / "ui-state-spec.yaml").write_text(
        "schema_version: 1\n"
        "# Estado sem evidência → confirmed: false + needs-elicitation: true.\n"
        "screens: []\n",
        encoding="utf-8",
    )

    result = validate_readiness.validate(tmp_forge_project, scope="feature", id=slug)
    assert result["status"] == "pass"


def test_validate_ready_without_marker_still_passes(
    tmp_forge_project: Path,
) -> None:
    """Espelho: ready + sem needs-elicitation → result_pass (sem regressão)."""
    slug = "clean-ready-feature"
    f_root = (
        tmp_forge_project
        / "docs"
        / "feature-implementation-workflow"
        / "features"
        / slug
    )
    f_root.mkdir(parents=True)
    _write_ready_review(f_root)
    # Contract spec presente mas LIMPO (sem o marker).
    (f_root / "data-contract-spec.yaml").write_text(
        "fields:\n  - name: starred\n    persist: true\n",
        encoding="utf-8",
    )

    result = validate_readiness.validate(tmp_forge_project, scope="feature", id=slug)
    assert result["status"] == "pass"


def test_make_paths_canonical_taxonomy(tmp_forge_project: Path) -> None:
    """WR-003 — os 3 caminhos respeitam a taxonomia fix/revert/split.

    `make_paths` atribui `kind` por posição (fix→revert→split). O fix do
    needs-elicitation deve ter: fix=promover a blocking:true; revert=`forge undo`;
    split=resolver inline / escalar. Sem o swap que o REVIEW.md apontou.
    """
    slug = "paths-check"
    f_root = (
        tmp_forge_project
        / "docs"
        / "feature-implementation-workflow"
        / "features"
        / slug
    )
    f_root.mkdir(parents=True)
    _write_ready_review(f_root)
    (f_root / "data-contract-spec.yaml").write_text(
        "fields:\n  - name: starred\n    persist: needs-elicitation\n",
        encoding="utf-8",
    )

    result = validate_readiness.validate(tmp_forge_project, scope="feature", id=slug)
    paths = result["paths"]
    assert [p["kind"] for p in paths] == ["fix", "revert", "split"]
    # fix = promover a blocking:true (conductor elicita)
    assert "blocking" in paths[0]["label"].lower()
    # revert = forge undo (reverter pré-plan)
    assert "undo" in paths[1]["label"].lower()
    # split = resolver inline / escalar (valor já conhecido ou escala pro user)
    assert "inline" in paths[2]["label"].lower()


def test_validate_where_truncation_is_honest_with_many_hits(
    tmp_forge_project: Path,
) -> None:
    """IN-002 — com >5 hits, o `where` mostra 5 + sufixo `(+N more)` honesto.

    A contagem total já está no `message`; o sufixo evita que o operador
    pense que viu todos os locais quando há 6+.
    """
    slug = "many-hits-feature"
    f_root = (
        tmp_forge_project
        / "docs"
        / "feature-implementation-workflow"
        / "features"
        / slug
    )
    f_root.mkdir(parents=True)
    _write_ready_review(f_root)
    # 7 markers ativos numa única spec → 7 hits, where trunca em 5.
    fields = "".join(
        f"  - name: f{i}\n    persist: needs-elicitation\n" for i in range(7)
    )
    (f_root / "data-contract-spec.yaml").write_text(
        f"fields:\n{fields}", encoding="utf-8"
    )

    result = validate_readiness.validate(tmp_forge_project, scope="feature", id=slug)
    assert result["status"] == "fail"
    where = result["where"]
    assert where.count(":") >= 5  # 5 locais file:linha
    assert "(+2 more)" in where
