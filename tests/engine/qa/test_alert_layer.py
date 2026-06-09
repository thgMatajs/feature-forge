"""Tests for engine.qa alert layer — sensitive-env-drop masking + isinstance guard.

Cobertura dos findings deep-005, deep-006, deep-022 do ultra-review:

  - deep-005: _alert_sensitive_drops mascara nomes (não vaza em log de CI)
  - deep-006: _compute_allowed_extras tolera shape malformado de
    sensitive-env-grants (dict, string, None) sem corrupção silenciosa
  - deep-022: _maybe_alert_sensitive_drops captura RuntimeError
    (corrupção de catalog) sem deixar escapar
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.qa import (
    _alert_sensitive_drops,
    _compute_allowed_extras,
    _mask_var_name,
    _maybe_alert_sensitive_drops,
)


# ---------------------------------------------------------------------------
# deep-005 — _mask_var_name
# ---------------------------------------------------------------------------


def test_mask_var_name_preserves_prefix_masks_rest():
    """Nome longo retorna 2 chars + asteriscos do tamanho restante."""
    assert _mask_var_name("GITHUB_TOKEN") == "GI" + "*" * 10
    assert _mask_var_name("AWS_SECRET_ACCESS_KEY") == "AW" + "*" * 19


def test_mask_var_name_short_input_returns_as_is():
    """Nome ≤2 chars não tem o que mascarar — retorna íntegro."""
    assert _mask_var_name("X") == "X"
    assert _mask_var_name("AB") == "AB"
    assert _mask_var_name("") == ""


def test_alert_does_not_disclose_full_names(monkeypatch, capsys):
    """deep-005: o alert deve emitir nomes mascarados, não os reais."""
    monkeypatch.setenv("STRIPE_LIVE_API_KEY", "sk_live_xxx")
    _alert_sensitive_drops(card_extras=[])
    err = capsys.readouterr().err
    # Nome completo nunca vaza
    assert "STRIPE_LIVE_API_KEY" not in err
    # Máscara presente
    assert "ST" + "*" * (len("STRIPE_LIVE_API_KEY") - 2) in err


# ---------------------------------------------------------------------------
# deep-006 — _compute_allowed_extras tolera shape malformado de grants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_shape", [
    "GITHUB_TOKEN",         # string solta — set() viraria {chars}
    {"GITHUB_TOKEN": True}, # dict — set() viraria {chaves}
    42,                     # int — set() levanta TypeError
    None,                   # None — `or []` cobre, mas testamos pra ter certeza
])
def test_compute_allowed_extras_tolerates_malformed_grants_shape(
    bad_shape, tmp_path, capsys
):
    """deep-006: shape malformado vira [] com warning em stderr — não corrupção."""
    project_root = tmp_path / "proj"
    project_root.mkdir()
    cfg = {"qa": {"sensitive-env-grants": bad_shape}}

    # Não deve raise. Resultado é seguro (extras vazios — load_all_cards
    # provavelmente retorna lista vazia num project_root sem cards).
    result = _compute_allowed_extras(project_root, cfg)

    assert isinstance(result, tuple)
    # Validações silenciosas anteriores virariam set({'G','I','T',...}) ou
    # set({'GITHUB_TOKEN': True}); aqui só não corrompe.
    for v in result:
        assert isinstance(v, str)
        assert len(v) > 1, (
            f"Char solto em result indica que set(string) leakou: {result!r}"
        )


def test_compute_allowed_extras_emits_warning_on_malformed_shape(
    tmp_path, capsys
):
    """deep-006: warning visível em stderr quando shape é não-lista."""
    project_root = tmp_path / "proj"
    project_root.mkdir()
    cfg = {"qa": {"sensitive-env-grants": "GITHUB_TOKEN"}}

    _compute_allowed_extras(project_root, cfg)

    err = capsys.readouterr().err
    assert "shape" in err.lower() or "str" in err.lower(), (
        f"esperado warning de shape em stderr; obtido: {err!r}"
    )


# ---------------------------------------------------------------------------
# deep-022 — _maybe_alert_sensitive_drops captura RuntimeError
# ---------------------------------------------------------------------------


def test_maybe_alert_catches_runtime_error(monkeypatch, tmp_path, capsys):
    """deep-022: RuntimeError de catalog corruption não deve escapar."""

    def boom(*_args, **_kwargs):
        raise RuntimeError("catalog corrompido")

    monkeypatch.setattr("engine.qa._compute_allowed_extras", boom)

    # Não deve raise — alert layer NUNCA bloqueia QA run.
    _maybe_alert_sensitive_drops(tmp_path, {})

    err = capsys.readouterr().err
    assert "Alert layer QA-11 falhou" in err
    assert "RuntimeError" in err
