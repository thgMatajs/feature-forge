"""Front-door + CASING-BUG + source-token fill tests para engine.plan (Wave 1 AI-first).

Cobre:
- slugify determinístico (`_derive_slug` / `engine.utils.slug.derive_slug`);
- CASING-BUG regression (`_render_template` substitui `{{feature_slug}}` lowercase);
- source-token fill (`extra_tokens` preenche `{{source_type}}` / `{{source_ref_or_none}}`
  no intake renderizado, sem deixar token cru);
- threading dos `extra_tokens` por `_run_static_wave` (Wave A) até `_render_template` —
  a falha que originou o vazamento do token cru;
- `_looks_like_ticket` reusando `_TICKET_PATTERN`.

Refs:
- docs/superpowers/specs/2026-06-17-ai-first-interaction-layer-design.md §4 C3
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from engine import plan

# Raiz do repo (tests/unit/<this> → parents[2]). Usado pra carregar o template
# de intake REAL nos testes de YAML-safety (não um stub) — assim a sanitização
# é exercida contra o scalar quotado que o conductor de fato consome.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_REAL_INTAKE_TEMPLATE = _REPO_ROOT / "templates" / "feature-intake.template.md"


# ── _derive_slug — slugify determinístico ────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("adicionar detalhe do bonsai", "adicionar-detalhe-do-bonsai"),
        ("IN-37234", "in-37234"),
        ("Lembrete de Rega", "lembrete-de-rega"),
        ("notificação às 8h", "notificacao-as-8h"),
        ("a   b    c", "a-b-c"),
        ("--leading-and-trailing--", "leading-and-trailing"),
        ("café com leite", "cafe-com-leite"),
    ],
)
def test_derive_slug_deterministic(text: str, expected: str) -> None:
    assert plan._derive_slug(text) == expected


def test_derive_slug_truncates_to_50() -> None:
    long = "palavra " * 20
    out = plan._derive_slug(long)
    assert len(out) <= 50
    assert plan._is_valid_slug(out), out


def test_derive_slug_starts_with_letter() -> None:
    # Começa com dígito → prefixa pra garantir início com letra.
    out = plan._derive_slug("123 fix")
    assert out[0].isalpha(), out
    assert plan._is_valid_slug(out), out


def test_derive_slug_empty_raises() -> None:
    with pytest.raises(ValueError):
        plan._derive_slug("")
    with pytest.raises(ValueError):
        plan._derive_slug("   !!!   ")


# ── CASING-BUG — _render_template substitui {{feature_slug}} lowercase ───────


def test_render_template_substitutes_lowercase_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Templates carregam {{feature_slug}} (lowercase, 74×). O engine renderizava
    {{FEATURE_SLUG}} (uppercase) — token sobrava cru. Asserir que some.
    """
    fake_templates = tmp_path / "templates"
    fake_templates.mkdir()
    (fake_templates / "x.template.md").write_text(
        "# Feature {{feature_slug}}\nslug: {{feature_slug}}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(plan, "_templates_dir", lambda _root: fake_templates)

    target = tmp_path / "out.md"
    created = plan._render_template("x.template.md", target, "lembrete-rega", tmp_path)
    assert created is True
    rendered = target.read_text(encoding="utf-8")
    assert "{{feature_slug}}" not in rendered, "lowercase token não substituído"
    assert "lembrete-rega" in rendered


# ── source-token fill — extra_tokens preenche source-type/source-ref ─────────

# As 3 linhas-token que os templates de intake carregam (lowercase + _or_none).
_INTAKE_TOKEN_BODY = (
    'feature-slug: "{{feature_slug}}"\n'
    'source-type: "{{source_type}}"\n'
    'source-ref: "{{source_ref_or_none}}"\n'
)


def test_render_template_fills_source_tokens(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`extra_tokens` preenche `{{source_type}}`/`{{source_ref_or_none}}` no
    intake renderizado — e NENHUM dos 3 tokens fica cru.
    """
    fake_templates = tmp_path / "templates"
    fake_templates.mkdir()
    (fake_templates / "intake.template.md").write_text(
        _INTAKE_TOKEN_BODY, encoding="utf-8"
    )
    monkeypatch.setattr(plan, "_templates_dir", lambda _root: fake_templates)

    target = tmp_path / "feature-intake.md"
    created = plan._render_template(
        "intake.template.md",
        target,
        "detalhe-do-bonsai",
        tmp_path,
        extra_tokens={
            "{{source_type}}": "phrase",
            "{{source_ref_or_none}}": "adicionar detalhe do bonsai",
        },
    )
    assert created is True
    rendered = target.read_text(encoding="utf-8")
    # Valores preenchidos.
    assert "detalhe-do-bonsai" in rendered
    assert "phrase" in rendered
    assert "adicionar detalhe do bonsai" in rendered
    # Nenhum dos 3 tokens vaza cru.
    for token in ("{{feature_slug}}", "{{source_type}}", "{{source_ref_or_none}}"):
        assert token not in rendered, f"{token} vazou cru no intake"


def test_render_template_extra_tokens_noop_on_other_templates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`extra_tokens` em template sem os tokens de source é inofensivo (no-op)."""
    fake_templates = tmp_path / "templates"
    fake_templates.mkdir()
    (fake_templates / "tech.template.md").write_text(
        "# Tech spec {{feature_slug}}\n", encoding="utf-8"
    )
    monkeypatch.setattr(plan, "_templates_dir", lambda _root: fake_templates)

    target = tmp_path / "tech-spec.md"
    created = plan._render_template(
        "tech.template.md",
        target,
        "x-feature",
        tmp_path,
        extra_tokens={
            "{{source_type}}": "phrase",
            "{{source_ref_or_none}}": "irrelevante",
        },
    )
    assert created is True
    rendered = target.read_text(encoding="utf-8")
    assert rendered == "# Tech spec x-feature\n"


# ── threading — _run_static_wave (Wave A) propaga extra_tokens p/ _render ─────


def test_run_static_wave_threads_source_tokens_to_intake(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifica que `extra_tokens` chega de `_run_static_wave` até
    `_render_template` (a falha que originou o vazamento do token cru — o
    plano original não cobria esse threading).
    """
    fake_templates = tmp_path / "templates"
    fake_templates.mkdir()
    (fake_templates / "intake.template.md").write_text(
        _INTAKE_TOKEN_BODY, encoding="utf-8"
    )
    monkeypatch.setattr(plan, "_templates_dir", lambda _root: fake_templates)
    # Não bloquear no prompt continuar/pausar.
    monkeypatch.setattr(plan, "_continue_or_pause", lambda slug, label: "continuar")

    feature_path = tmp_path / "feature"
    feature_path.mkdir()
    result = plan._run_static_wave(
        "A",
        (("intake.template.md", "feature-intake.md"),),
        "detalhe-do-bonsai",
        tmp_path,
        feature_path,
        extra_tokens={
            "{{source_type}}": "ticket",
            "{{source_ref_or_none}}": "IN-37234",
        },
    )
    assert result.deferred is False
    rendered = (feature_path / "feature-intake.md").read_text(encoding="utf-8")
    assert "ticket" in rendered
    assert "IN-37234" in rendered
    for token in ("{{feature_slug}}", "{{source_type}}", "{{source_ref_or_none}}"):
        assert token not in rendered, f"{token} vazou cru no intake"


# ── _looks_like_ticket — reusa _TICKET_PATTERN ───────────────────────────────


def test_looks_like_ticket_true_for_ticket_id() -> None:
    assert plan._looks_like_ticket("IN-37234") is True


def test_looks_like_ticket_false_for_phrase() -> None:
    assert plan._looks_like_ticket("frase livre") is False


# ── _source_tokens_for — dict de source pro intake (threadeado em run) ───────


def test_source_tokens_for_phrase() -> None:
    # M-001: frase livre mapeia pro enum do template → `text` (não `phrase`).
    out = plan._source_tokens_for("adicionar detalhe do bonsai")
    assert out == {
        "{{source_type}}": "text",
        "{{source_ref_or_none}}": "adicionar detalhe do bonsai",
    }


def test_source_tokens_for_ticket() -> None:
    out = plan._source_tokens_for("IN-37234")
    assert out == {
        "{{source_type}}": "ticket",
        "{{source_ref_or_none}}": "IN-37234",
    }


def test_source_tokens_for_valid_slug() -> None:
    # M-001: slug válido não vira `slug` (fora do enum) → `text`, ref `none`.
    out = plan._source_tokens_for("lembrete-rega")
    assert out == {
        "{{source_type}}": "text",
        "{{source_ref_or_none}}": "none",
    }


def test_source_tokens_for_interactive() -> None:
    # M-001: sem argv não vira `interactive` (fora do enum) → `text`, ref `none`.
    out = plan._source_tokens_for(None)
    assert out == {
        "{{source_type}}": "text",
        "{{source_ref_or_none}}": "none",
    }


# ── M-001 — source-type SEMPRE no enum do template (ticket | text) ───────────


@pytest.mark.parametrize(
    ("argv", "expected_type"),
    [
        ("IN-37234", "ticket"),  # ticket-id inteiro
        ("adicionar detalhe do bonsai", "text"),  # frase livre
        ("lembrete-rega", "text"),  # slug já válido
        (None, "text"),  # interativo (sem argv)
    ],
)
def test_source_tokens_for_type_in_template_enum(
    argv: str | None, expected_type: str
) -> None:
    """`source-type` casa o enum declarado em `feature-intake.template.md`
    (`ticket | text | screenshot | mixed`). Os 4 caminhos só emitem
    `ticket` ou `text` — nunca os valores fora-do-enum antigos
    (`phrase`/`slug`/`interactive`).
    """
    out = plan._source_tokens_for(argv)
    assert out["{{source_type}}"] == expected_type
    assert out["{{source_type}}"] in {"ticket", "text"}


# ── L-001 — _looks_like_ticket usa fullmatch (argv inteiro, não substring) ───


def test_looks_like_ticket_fullmatch_whole_id() -> None:
    assert plan._looks_like_ticket("IN-37234") is True
    # Espaço em volta é tolerado (strip antes do fullmatch).
    assert plan._looks_like_ticket("  IN-37234  ") is True


def test_looks_like_ticket_false_for_phrase_mentioning_ticket() -> None:
    # Frase que só MENCIONA um ticket não é ticket-id → vira text.
    assert plan._looks_like_ticket("fix IN-123 agora") is False
    assert plan._looks_like_ticket("ABC-12 e mais texto") is False
    # Consistência com _source_tokens_for: frase-com-ticket → source-type=text.
    out = plan._source_tokens_for("fix IN-123 agora")
    assert out["{{source_type}}"] == "text"


# ── H-001 — derive_slug SEMPRE passa _is_valid_slug (piso min-3) ─────────────


@pytest.mark.parametrize(
    "text",
    [
        "a",
        "ab",
        "aB",
        "ab--",
        "hi",
        "ok",
        "x",
        "1",
        "12",
        "a1",
        "1a",
        "à",  # NFKD → "a" isolado
        "a.b",
        "z9",
        "-a-",
    ],
)
def test_derive_slug_floor_always_valid(text: str) -> None:
    """Invariante H-001: pra qualquer input não-ValueError, `derive_slug`
    devolve slug que `_is_valid_slug` aceita. O piso era min-2 (off-by-one
    contra `_SLUG_PATTERN`, que exige min-3): `"ab"` escapava inválido e o
    `ask_text` recusava o próprio default derivado.
    """
    out = plan._derive_slug(text)
    assert plan._is_valid_slug(out), f"{text!r} → {out!r} reprovou _is_valid_slug"


def test_derive_slug_two_char_alnum_padded() -> None:
    # Caso canônico do finding: 2-char alnum não escapa mais inválido.
    assert plan._derive_slug("ab") == "ab-x"
    assert plan._is_valid_slug(plan._derive_slug("ab"))


# ── H-002 — source-ref YAML-safe: frontmatter REAL parseia sem injeção ───────


def _render_real_intake(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, argv: str
) -> tuple[dict, dict[str, str]]:
    """Renderiza o template de intake REAL com os tokens de `_source_tokens_for`
    e devolve `(frontmatter_parseado, tokens)`. Usa `yaml.safe_load` no
    frontmatter — o mesmo YAML que o conductor consome.
    """
    fake_templates = tmp_path / "templates"
    fake_templates.mkdir(exist_ok=True)
    (fake_templates / "feature-intake.template.md").write_text(
        _REAL_INTAKE_TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    monkeypatch.setattr(plan, "_templates_dir", lambda _root: fake_templates)

    tokens = plan._source_tokens_for(argv)
    target = tmp_path / "feature-intake.md"
    if target.exists():
        target.unlink()
    plan._render_template(
        "feature-intake.template.md", target, "my-slug", tmp_path, extra_tokens=tokens
    )
    rendered = target.read_text(encoding="utf-8")
    # Frontmatter = bloco entre o primeiro par de `---`.
    _, frontmatter, _ = rendered.split("---", 2)
    parsed = yaml.safe_load(frontmatter)
    return parsed, tokens


_ADVERSARIAL_ARGV = [
    'fix "login" button',  # aspas duplas no meio
    "IN-1: foo\n  extra-key: 99 #comment",  # newline + dois-pontos + tentativa de injeção
    "a: b: c",  # múltiplos dois-pontos
    '" \nextra-key: 99 #',  # aspa de abertura + newline + chave injetada
    "{{feature_slug}} pwned",  # token literal (não deve re-expandir)
]

# Chaves canônicas do frontmatter de feature-intake.template.md.
_INTAKE_FRONTMATTER_KEYS = {
    "feature-slug",
    "generated-by",
    "generated-at",
    "schema-version",
    "source-type",
    "source-ref",
}


@pytest.mark.parametrize("argv", _ADVERSARIAL_ARGV)
def test_intake_frontmatter_yaml_safe_no_injection(
    argv: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H-002: argv adversarial pelo `source-ref` não malforma o frontmatter
    nem injeta chave YAML. `yaml.safe_load` parseia como dict, e o conjunto
    de chaves é exatamente o canônico (nenhuma chave nova vinda do argv).
    """
    parsed, _tokens = _render_real_intake(tmp_path, monkeypatch, argv)
    assert isinstance(parsed, dict), f"frontmatter não parseou como dict: {parsed!r}"
    extra = set(parsed.keys()) - _INTAKE_FRONTMATTER_KEYS
    assert not extra, f"chave(s) YAML injetada(s) por {argv!r}: {extra}"


@pytest.mark.parametrize("argv", _ADVERSARIAL_ARGV)
def test_intake_source_ref_round_trips_sanitized(
    argv: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H-002: o `source-ref` no frontmatter parseado é o valor sanitizado
    (whitespace colapsado + strip). O escape (`\\` / `"`) é detalhe do scalar
    YAML: `yaml.safe_load` decodifica de volta pra forma lógica, que deve
    bater com o resultado de colapsar/strip o argv (sem o escape).
    """
    parsed, _tokens = _render_real_intake(tmp_path, monkeypatch, argv)
    # Forma lógica esperada: só colapsa whitespace + strip (sem escapar — o
    # escape é desfeito pelo parse). Espelha o `re.sub(r"\s+", " ", v).strip()`
    # de `_yaml_double_quote_safe`, antes do replace de escape.
    import re

    expected_logical = re.sub(r"\s+", " ", argv).strip()
    assert parsed["source-ref"] == expected_logical


def test_intake_frontmatter_yaml_safe_benign_phrase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sanity: frase benigna também round-trips limpo e classifica `text`."""
    parsed, tokens = _render_real_intake(
        tmp_path, monkeypatch, "adicionar detalhe do bonsai"
    )
    assert parsed["source-type"] == "text"
    assert parsed["source-ref"] == "adicionar detalhe do bonsai"
    assert tokens["{{source_type}}"] == "text"


# ── Colisão de slug — documenta o caminho EXISTENTE (sem comportamento novo) ─


def test_slug_collision_handled_by_existing_run_machinery() -> None:
    """Doc-test: a colisão com feature DONE é tratada por
    `_handle_done_feature_branch`; a colisão com feature ATIVA não-done por
    `_handle_active_slug_collision` (C-03). Ambos vivem em `run()`.
    """
    assert callable(plan._handle_done_feature_branch)
    assert callable(plan._handle_active_slug_collision)
    assert callable(plan.run)


def test_active_slug_collision_offers_three_paths(monkeypatch, tmp_path) -> None:
    """C-03 (PR18-R3): colisão com feature ativa não-done apresenta 3-caminhos.

    'nova' → devolve o slug sufixado; 'retomar' → devolve o slug existente;
    'abortar' → None.
    """
    from engine.memory.l1 import L1State

    state = L1State(
        feature_slug="lembrete-rega",
        status="planning",
        last_action_at="2026-06-18T00:00:00Z",
        last_action_kind="plan-started",
    )

    # 'nova' → sufixo (lembrete-rega-2, livre pois nada está em L1 no tmp).
    monkeypatch.setattr(plan.question, "ask", lambda *a, **k: "nova")
    assert (
        plan._handle_active_slug_collision("lembrete-rega", state, tmp_path)
        == "lembrete-rega-2"
    )

    # 'retomar' → o próprio slug.
    monkeypatch.setattr(plan.question, "ask", lambda *a, **k: "retomar")
    assert (
        plan._handle_active_slug_collision("lembrete-rega", state, tmp_path)
        == "lembrete-rega"
    )

    # 'abortar' → None.
    monkeypatch.setattr(plan.question, "ask", lambda *a, **k: "abortar")
    assert (
        plan._handle_active_slug_collision("lembrete-rega", state, tmp_path) is None
    )


def test_active_collision_states_cover_non_done_active() -> None:
    """C-03: planning/planned/deferred/blocked-on-external disparam o handler."""
    assert plan._ACTIVE_COLLISION_STATES == {
        "planning",
        "planned",
        "deferred",
        "blocked-on-external",
    }
