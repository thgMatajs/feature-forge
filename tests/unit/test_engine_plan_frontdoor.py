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

from engine import plan


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
    monkeypatch.setattr(plan, "_templates_dir", lambda: fake_templates)

    target = tmp_path / "out.md"
    created = plan._render_template("x.template.md", target, "lembrete-rega")
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
    monkeypatch.setattr(plan, "_templates_dir", lambda: fake_templates)

    target = tmp_path / "feature-intake.md"
    created = plan._render_template(
        "intake.template.md",
        target,
        "detalhe-do-bonsai",
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
    monkeypatch.setattr(plan, "_templates_dir", lambda: fake_templates)

    target = tmp_path / "tech-spec.md"
    created = plan._render_template(
        "tech.template.md",
        target,
        "x-feature",
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
    monkeypatch.setattr(plan, "_templates_dir", lambda: fake_templates)
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
    out = plan._source_tokens_for("adicionar detalhe do bonsai")
    assert out == {
        "{{source_type}}": "phrase",
        "{{source_ref_or_none}}": "adicionar detalhe do bonsai",
    }


def test_source_tokens_for_ticket() -> None:
    out = plan._source_tokens_for("IN-37234")
    assert out == {
        "{{source_type}}": "ticket",
        "{{source_ref_or_none}}": "IN-37234",
    }


def test_source_tokens_for_valid_slug() -> None:
    out = plan._source_tokens_for("lembrete-rega")
    assert out == {
        "{{source_type}}": "slug",
        "{{source_ref_or_none}}": "none",
    }


def test_source_tokens_for_interactive() -> None:
    out = plan._source_tokens_for(None)
    assert out == {
        "{{source_type}}": "interactive",
        "{{source_ref_or_none}}": "none",
    }
