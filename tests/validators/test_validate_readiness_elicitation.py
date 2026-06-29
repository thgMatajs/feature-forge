"""needs_elicitation scan no validate_readiness (Wave 1 C5).

Block-severity quando `needs_elicitation` ATIVO sobrevive não-promovido em
contract spec; warning em narrativa.

Convenção REAL (WR-01 holistic review): o marker estruturado usa **underscore**
(`needs_elicitation`) na DATA — a forma hyphen só vive em PROSE/comentário. As
formas ativas reais nos artefatos:
  - `needs_elicitation: true` (boolean per-state em ui-state-spec; default false)
  - `"needs_elicitation": true` (bdd.json, JSON)
  - `needs_elicitation: [<item>]` ou bloco YAML (lista top-level; default `[]`)
Inativo (NÃO bloqueia): `false`, `[]`, `null`, ausente, comentário de template.

Cobre dois níveis:
- **Isolado:** `_scan_needs_elicitation` parseia o artefato (YAML/JSON) e flagueia
  a chave `needs_elicitation` ATIVA (truthy OU lista não-vazia) em `*-spec.yaml`,
  `task-breakdown.yaml`, `tasks/*.yaml`, `test-strategy.yaml` e `bdd.json`,
  ignora prose/template-comment (não é DATA), e retorna `[]` sem marker ativo.
- **Integração (prova de wiring):** `validate()` retorna `result_fail` mesmo com
  verdict nominal `ready` quando há `needs_elicitation` ativo — provando que o
  scan preempta o parse do verdict — e o caso espelho (`ready` + sem marker →
  `result_pass`, sem regressão).

Refs: docs/superpowers/specs/2026-06-17-ai-first-interaction-layer-design.md §4 C5
      .planning/wave1-full/REVIEW.md WR-01
"""

from __future__ import annotations

from pathlib import Path

from validators import validate_readiness


# ── Isolado — _scan_needs_elicitation (formas REAIS underscore) ───────────────


def test_scan_flags_key_truthy_yaml(tmp_path: Path) -> None:
    """Forma-chave truthy YAML (`needs_elicitation: true`) → flagueada.

    A forma boolean per-state mais comum (ui-state-spec): um estado sem
    evidência vira `confirmed: false` + `needs_elicitation: true`.
    """
    f_root = tmp_path
    spec = f_root / "ui-state-spec.yaml"
    spec.write_text(
        "screens:\n"
        "  - name: home\n"
        "    states:\n"
        "      - id: empty\n"
        "        confirmed: false\n"
        "        needs_elicitation: true\n",
        encoding="utf-8",
    )
    hits = validate_readiness._scan_needs_elicitation(f_root)
    assert any("ui-state-spec.yaml" in h for h in hits), (
        f"needs_elicitation: true deveria ser flagueado; hits={hits}"
    )


def test_scan_flags_non_empty_list_yaml(tmp_path: Path) -> None:
    """Forma-lista não-vazia YAML (top-level `needs_elicitation: [item]`)."""
    f_root = tmp_path
    spec = f_root / "task-contract-spec.yaml"
    spec.write_text(
        "task_id: TASK-0001\n"
        "needs_elicitation:\n"
        "  - reminder_time default desconhecido\n",
        encoding="utf-8",
    )
    hits = validate_readiness._scan_needs_elicitation(f_root)
    assert any("task-contract-spec.yaml" in h for h in hits), (
        f"lista não-vazia deveria ser flagueada; hits={hits}"
    )


def test_scan_flags_inline_non_empty_list_yaml(tmp_path: Path) -> None:
    """Forma-lista inline não-vazia (`needs_elicitation: [item]`)."""
    f_root = tmp_path
    (f_root / "analytics-spec.yaml").write_text(
        "events: []\nneeds_elicitation: [open-event sem schema]\n",
        encoding="utf-8",
    )
    hits = validate_readiness._scan_needs_elicitation(f_root)
    assert any("analytics-spec.yaml" in h for h in hits), (
        f"lista inline não-vazia deveria ser flagueada; hits={hits}"
    )


def test_scan_flags_needs_elicitation_in_bdd_json(tmp_path: Path) -> None:
    """Forma JSON underscore truthy (`"needs_elicitation": true`) em bdd.json.

    Quando o contract-planner acha um cenário sem assertion comprovável, o
    campo real do schema bdd.json é `needs_elicitation` (underscore). O glob
    novo (`bdd.json`) + parse JSON pega esse gap (antes era cego — WR-01).
    """
    f_root = tmp_path
    (f_root / "bdd.json").write_text(
        '{\n'
        '  "scenarios": [\n'
        '    {"name": "abrir tela", "needs_elicitation": true}\n'
        '  ]\n'
        '}\n',
        encoding="utf-8",
    )
    hits = validate_readiness._scan_needs_elicitation(f_root)
    assert any("bdd.json" in h for h in hits), (
        f"bdd.json deveria ser flagueado; hits={hits}"
    )


def test_scan_flags_top_level_list_in_bdd_json(tmp_path: Path) -> None:
    """Lista top-level não-vazia em bdd.json (`"needs_elicitation": [...]`)."""
    f_root = tmp_path
    (f_root / "bdd.json").write_text(
        '{\n'
        '  "scenarios": [],\n'
        '  "needs_elicitation": ["cenário sem given concreto"]\n'
        '}\n',
        encoding="utf-8",
    )
    hits = validate_readiness._scan_needs_elicitation(f_root)
    assert any("bdd.json" in h for h in hits), (
        f"lista top-level em bdd.json deveria ser flagueada; hits={hits}"
    )


def test_scan_flags_needs_elicitation_in_test_strategy(tmp_path: Path) -> None:
    """`test-strategy.yaml` (NÃO casava `*-spec.yaml`) entra no glob novo.

    `test-strategy.yaml` usa `needs_elicitation: []` default; populado com
    items vira lista não-vazia. Antes do WR-01 escapava DUPLAMENTE (underscore
    + sem sufixo `-spec`).
    """
    f_root = tmp_path
    (f_root / "test-strategy.yaml").write_text(
        "lanes:\n  - rapid\nneeds_elicitation:\n"
        "  - per-state test de error não decidido\n",
        encoding="utf-8",
    )
    hits = validate_readiness._scan_needs_elicitation(f_root)
    assert any("test-strategy.yaml" in h for h in hits), (
        f"test-strategy.yaml deveria ser flagueado; hits={hits}"
    )


def test_scan_flags_needs_elicitation_in_task_contract(tmp_path: Path) -> None:
    """BL-001 — o glob `tasks/*.yaml` pega task contracts (forma underscore).

    O task contract (`tasks/TASK-NNNN.yaml`) é o artefato mais propenso a
    carregar o campo não-promovido na cadeia story→task (spec C5).
    """
    f_root = tmp_path
    tasks = f_root / "tasks"
    tasks.mkdir()
    (tasks / "TASK-0001.yaml").write_text(
        "task_id: TASK-0001\n"
        "needs_elicitation:\n"
        "  - reminder_time default desconhecido\n",
        encoding="utf-8",
    )
    hits = validate_readiness._scan_needs_elicitation(f_root)
    assert any("TASK-0001.yaml" in h for h in hits), (
        f"task contract deveria ser flagueado; hits={hits}"
    )


def test_scan_flags_needs_elicitation_in_breakdown(tmp_path: Path) -> None:
    """BL-001 — `task-breakdown.yaml` (root) no glob, forma underscore."""
    f_root = tmp_path
    (f_root / "task-breakdown.yaml").write_text(
        "tasks:\n  - id: TASK-0001\n    needs_elicitation: true\n",
        encoding="utf-8",
    )
    hits = validate_readiness._scan_needs_elicitation(f_root)
    assert any("task-breakdown.yaml" in h for h in hits), (
        f"breakdown deveria ser flagueado; hits={hits}"
    )


# ── Inativo — default/resolvido NÃO flagueia ─────────────────────────────────


def test_scan_clean_when_no_marker(tmp_path: Path) -> None:
    f_root = tmp_path
    (f_root / "data-contract-spec.yaml").write_text(
        "fields:\n  - name: starred\n    persist: true\n",
        encoding="utf-8",
    )
    assert validate_readiness._scan_needs_elicitation(f_root) == []


def test_scan_key_false_does_not_flag(tmp_path: Path) -> None:
    """`needs_elicitation: false` (já resolvido) NÃO flagueia na forma-chave."""
    f_root = tmp_path
    (f_root / "analytics-spec.yaml").write_text(
        "events:\n  - name: open\n    needs_elicitation: false\n",
        encoding="utf-8",
    )
    assert validate_readiness._scan_needs_elicitation(f_root) == []


def test_is_active_marker_descriptive_string_is_active() -> None:
    """C-05 (PR18-B5): string descritiva ('pending') é ATIVA (bloqueia).

    Antes do fix o ramo string só ativava em true/yes/1 — cego a qualquer
    string descritiva que o conductor deixasse ('pending', 'aguardando user',
    'TODO'), que são exatamente os sinais de elicitation não-resolvida.
    """
    assert validate_readiness._is_active_marker("pending") is True
    assert validate_readiness._is_active_marker("aguardando user") is True
    assert validate_readiness._is_active_marker("TODO") is True


def test_is_active_marker_explicit_negatives_are_inactive() -> None:
    """C-05: negativos explícitos + string vazia NÃO bloqueiam."""
    for neg in ("false", "False", "no", "NO", "0", "none", "null", "", "  "):
        assert validate_readiness._is_active_marker(neg) is False, neg


def test_scan_flags_descriptive_string_marker(tmp_path: Path) -> None:
    """C-05 end-to-end: `needs_elicitation: pending` flagueia."""
    f_root = tmp_path
    (f_root / "analytics-spec.yaml").write_text(
        "events:\n  - name: open\n    needs_elicitation: pending\n",
        encoding="utf-8",
    )
    hits = validate_readiness._scan_needs_elicitation(f_root)
    assert hits, "string descritiva deveria flaguear"


def test_scan_empty_list_does_not_flag(tmp_path: Path) -> None:
    """`needs_elicitation: []` (default vazio = inativo) NÃO flagueia."""
    f_root = tmp_path
    (f_root / "test-strategy.yaml").write_text(
        "lanes:\n  - rapid\nneeds_elicitation: []\n",
        encoding="utf-8",
    )
    assert validate_readiness._scan_needs_elicitation(f_root) == []


def test_scan_empty_list_json_does_not_flag(tmp_path: Path) -> None:
    """`"needs_elicitation": []` em bdd.json (default vazio) NÃO flagueia."""
    f_root = tmp_path
    (f_root / "bdd.json").write_text(
        '{"scenarios": [], "needs_elicitation": []}\n',
        encoding="utf-8",
    )
    assert validate_readiness._scan_needs_elicitation(f_root) == []


def test_scan_key_false_json_does_not_flag(tmp_path: Path) -> None:
    """`"needs_elicitation": false` per-scenario em bdd.json NÃO flagueia."""
    f_root = tmp_path
    (f_root / "bdd.json").write_text(
        '{"scenarios": [{"name": "x", "needs_elicitation": false}]}\n',
        encoding="utf-8",
    )
    assert validate_readiness._scan_needs_elicitation(f_root) == []


def test_scan_does_not_flag_template_prose_comment(tmp_path: Path) -> None:
    """Regression guard — comentário YAML instrucional NÃO flagueia.

    O `ui-state-spec.template.yaml` carrega a palavra `needs-elicitation`
    (hyphen, prose) E `needs_elicitation` (underscore, prose) em comentários.
    Comentário não é DATA — o parse estrutural ignora `#` naturalmente, então
    nem a forma hyphen nem a underscore em prose disparam.

    A linha abaixo replica a prose real do template — fonte do risco de
    false-positive se o scan fosse substring.
    """
    f_root = tmp_path
    (f_root / "ui-state-spec.yaml").write_text(
        "schema_version: 1\n"
        "feature_slug: lembrete-rega\n"
        "# Regras absolutas:\n"
        "#   1. Toda screen declara TODOS os 7 base states. Estado sem evidência →\n"
        "#      confirmed: false + needs_elicitation: true + open-question id.\n"
        "#   3. `inferred` SEMPRE pareado com needs-elicitation.\n"
        "screens: []\n",
        encoding="utf-8",
    )
    assert validate_readiness._scan_needs_elicitation(f_root) == [], (
        "comentário instrucional do template NÃO deveria disparar o scan"
    )


def test_scan_ignores_unparseable_yaml_gracefully(tmp_path: Path) -> None:
    """YAML inválido → ignore gracioso (o schema gate pega isso noutro lugar)."""
    f_root = tmp_path
    (f_root / "data-contract-spec.yaml").write_text(
        "fields: [unbalanced\n  bad: : :\n",
        encoding="utf-8",
    )
    # Não deve crashar; sem marker parseável, retorna [].
    assert validate_readiness._scan_needs_elicitation(f_root) == []


def test_scan_ignores_unparseable_json_gracefully(tmp_path: Path) -> None:
    """JSON inválido → ignore gracioso (não crasha)."""
    f_root = tmp_path
    (f_root / "bdd.json").write_text(
        '{"scenarios": [ {"name": "x"  ,, ] }',
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
    needs_elicitation não-promovido força fail mesmo quando o verdict diz ready.
    """
    slug = "thin-but-complete"
    f_root = (
        tmp_forge_project
        / "docs"
        / "forge-specs"
        / "features"
        / slug
    )
    f_root.mkdir(parents=True)
    _write_ready_review(f_root)
    # Contract spec com needs_elicitation ativo sobrevive até o readiness.
    (f_root / "ui-state-spec.yaml").write_text(
        "screens:\n  - name: home\n    states:\n"
        "      - id: empty\n        needs_elicitation: true\n",
        encoding="utf-8",
    )

    result = validate_readiness.validate(tmp_forge_project, scope="feature", id=slug)
    assert result["status"] == "fail"
    assert len(result["paths"]) == 3
    assert "needs_elicitation" in result.get("what-failed", "")


def test_validate_blocks_needs_elicitation_in_bdd_json(
    tmp_forge_project: Path,
) -> None:
    """Integração WR-01 — marker em bdd.json bloqueia mesmo com ready.

    O hole central do WR-01: um gap de elicitação que vive só em bdd.json
    (convenção underscore + JSON) escapava do scan. Agora bloqueia.
    """
    slug = "bdd-leak"
    f_root = (
        tmp_forge_project
        / "docs"
        / "forge-specs"
        / "features"
        / slug
    )
    f_root.mkdir(parents=True)
    _write_ready_review(f_root)
    (f_root / "bdd.json").write_text(
        '{"scenarios": [{"name": "x", "needs_elicitation": true}]}\n',
        encoding="utf-8",
    )

    result = validate_readiness.validate(tmp_forge_project, scope="feature", id=slug)
    assert result["status"] == "fail"
    assert "needs_elicitation" in result.get("what-failed", "")
    assert "bdd.json" in result.get("where", "")


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
        / "forge-specs"
        / "features"
        / slug
    )
    (f_root / "tasks").mkdir(parents=True)
    _write_ready_review(f_root)
    (f_root / "tasks" / "TASK-0001.yaml").write_text(
        "task_id: TASK-0001\nneeds_elicitation:\n  - reminder_time default\n",
        encoding="utf-8",
    )

    result = validate_readiness.validate(tmp_forge_project, scope="feature", id=slug)
    assert result["status"] == "fail"
    assert "needs_elicitation" in result.get("what-failed", "")
    assert "TASK-0001.yaml" in result.get("where", "")


def test_validate_ready_with_template_prose_passes(
    tmp_forge_project: Path,
) -> None:
    """Integração — spec renderizado com prose de template NÃO bloqueia.

    Um `ui-state-spec.yaml` que herda os comentários instrucionais do template
    (a prose com a palavra `needs_elicitation`) mas sem marker ativo deve
    passar o readiness — senão TODA feature real falharia o gate.
    """
    slug = "prose-only-feature"
    f_root = (
        tmp_forge_project
        / "docs"
        / "forge-specs"
        / "features"
        / slug
    )
    f_root.mkdir(parents=True)
    _write_ready_review(f_root)
    (f_root / "ui-state-spec.yaml").write_text(
        "schema_version: 1\n"
        "# Estado sem evidência → confirmed: false + needs_elicitation: true.\n"
        "screens: []\n",
        encoding="utf-8",
    )

    result = validate_readiness.validate(tmp_forge_project, scope="feature", id=slug)
    assert result["status"] == "pass"


def test_validate_ready_with_resolved_marker_passes(
    tmp_forge_project: Path,
) -> None:
    """Integração — `needs_elicitation: false`/`[]` (resolvido) NÃO bloqueia."""
    slug = "resolved-feature"
    f_root = (
        tmp_forge_project
        / "docs"
        / "forge-specs"
        / "features"
        / slug
    )
    f_root.mkdir(parents=True)
    _write_ready_review(f_root)
    (f_root / "ui-state-spec.yaml").write_text(
        "screens:\n  - name: home\n    states:\n"
        "      - id: empty\n        needs_elicitation: false\n",
        encoding="utf-8",
    )
    (f_root / "test-strategy.yaml").write_text(
        "lanes:\n  - rapid\nneeds_elicitation: []\n",
        encoding="utf-8",
    )

    result = validate_readiness.validate(tmp_forge_project, scope="feature", id=slug)
    assert result["status"] == "pass"


def test_validate_ready_without_marker_still_passes(
    tmp_forge_project: Path,
) -> None:
    """Espelho: ready + sem needs_elicitation → result_pass (sem regressão)."""
    slug = "clean-ready-feature"
    f_root = (
        tmp_forge_project
        / "docs"
        / "forge-specs"
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
    needs_elicitation deve ter: fix=promover a blocking:true; revert=`forge undo`;
    split=resolver inline / escalar. Sem o swap que o REVIEW.md apontou.
    """
    slug = "paths-check"
    f_root = (
        tmp_forge_project
        / "docs"
        / "forge-specs"
        / "features"
        / slug
    )
    f_root.mkdir(parents=True)
    _write_ready_review(f_root)
    (f_root / "ui-state-spec.yaml").write_text(
        "screens:\n  - name: home\n    states:\n"
        "      - id: empty\n        needs_elicitation: true\n",
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
        / "forge-specs"
        / "features"
        / slug
    )
    f_root.mkdir(parents=True)
    _write_ready_review(f_root)
    # 7 specs distintos, cada um com 1 marker ativo → 7 hits, where trunca em 5.
    for i in range(7):
        (f_root / f"screen{i}-spec.yaml").write_text(
            "states:\n  - id: empty\n    needs_elicitation: true\n",
            encoding="utf-8",
        )

    result = validate_readiness.validate(tmp_forge_project, scope="feature", id=slug)
    assert result["status"] == "fail"
    where = result["where"]
    assert "(+2 more)" in where
