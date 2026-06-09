"""Robustness tests for `_gate_infra` helpers (PR #7 review fixes B1-B4).

Cobre 4 ajustes endereçando comentários do review do gate-infra-extract:

  B1 — render_config_with_placeholders ordena placeholders por len desc
       (evita prefix-collision: substituir `__CC__` antes de `__CC_THRESHOLD__`).
  B2 — render_config_with_placeholders limpa tempfile se write/close raise
       (evita leak silencioso).
  B3 — apply_overrides valida `override_key_fields` contra named groups do
       `key_pattern` up-front (raise ValueError em vez de KeyError tardio).
  B4 — parse_overrides skipa entrada quando conversor levanta KeyError
       (match the docstring promise: skip silencioso pra falhas de
       conversor).
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest

import _gate_infra


# ── B1 — placeholder ordering ────────────────────────────────────────────────


def test_render_config_orders_placeholders_by_length_desc(tmp_path: Path) -> None:
    """Chave curta que é prefixo da longa não pode corromper a longa.

    Passa o dict com a chave curta PRIMEIRO — sem o sort, Python 3.7+
    preserva insertion order e `__CC` substitui o prefixo de
    `__CC_THRESHOLD__`, produzindo `X_THRESHOLD__` corrompido.
    """
    template = tmp_path / "tpl.yml"
    template.write_text("threshold: __CC_THRESHOLD__\nbase: __CC\n", encoding="utf-8")
    rendered_path = _gate_infra.render_config_with_placeholders(
        template,
        # Curto PRIMEIRO de propósito — força regressão sem sort
        {"__CC": "X", "__CC_THRESHOLD__": "10"},
    )
    try:
        content = Path(rendered_path).read_text(encoding="utf-8")
    finally:
        os.unlink(rendered_path)
    assert "threshold: 10" in content, f"got: {content!r}"
    assert "base: X" in content, f"got: {content!r}"
    # Crucial: o curto NÃO pode ter corrompido o longo
    assert "X_THRESHOLD__" not in content, f"corruption: {content!r}"


# ── B2 — tempfile cleanup on write failure ───────────────────────────────────


def test_render_config_cleans_tempfile_when_write_fails(tmp_path: Path) -> None:
    """Se `tmp.write` raise, tempfile não pode ficar órfão no disco."""
    import tempfile as real_tempfile

    template = tmp_path / "tpl.yml"
    template.write_text("hello\n", encoding="utf-8")

    captured: dict[str, str] = {}
    real_ntf = real_tempfile.NamedTemporaryFile  # captura antes do patch

    class _ExplodingTempfile:
        def __init__(self, *args, **kwargs):
            self._inner = real_ntf(*args, **kwargs)
            self.name = self._inner.name
            captured["name"] = self.name

        def write(self, *_a, **_kw):
            raise OSError("disk full simulation")

        def close(self):
            self._inner.close()

    with mock.patch.object(
        _gate_infra.tempfile, "NamedTemporaryFile", side_effect=_ExplodingTempfile
    ):
        with pytest.raises(OSError, match="disk full"):
            _gate_infra.render_config_with_placeholders(template, {})

    # Cleanup happened: arquivo NÃO existe mais
    assert captured.get("name")
    assert not Path(captured["name"]).exists(), \
        f"tempfile {captured['name']} ficou órfão após write failure (leak)"


# ── B3 — apply_overrides validates override_key_fields up-front ──────────────


def test_apply_overrides_raises_when_override_key_fields_missing_from_pattern() -> None:
    """`override_key_fields` que não existem em `key_pattern` viram ValueError."""
    fails: list[tuple[str, str]] = [("a.py", "f")]
    with pytest.raises(ValueError, match="override_key_fields"):
        _gate_infra.apply_overrides(
            fails,
            commit_body="",
            prefix="X-OVERRIDE",
            key_pattern=r"(?P<file>\S+)",  # tem só `file`
            fail_key_extractor=lambda f: (f[0], f[1]),
            override_key_fields=["file", "nope"],  # `nope` não existe
        )


def test_apply_overrides_error_message_lists_actual_named_groups() -> None:
    """Mensagem de erro mostra os grupos disponíveis pra debugger ver."""
    with pytest.raises(ValueError) as exc_info:
        _gate_infra.apply_overrides(
            fails=[],
            commit_body="",
            prefix="X",
            key_pattern=r"(?P<file>\S+):(?P<func>\S+)",
            fail_key_extractor=lambda f: (f,),
            override_key_fields=["bogus"],
        )
    msg = str(exc_info.value)
    assert "file" in msg
    assert "func" in msg


def test_apply_overrides_passes_through_when_fields_valid() -> None:
    """Validação up-front não regrede comportamento legítimo."""
    fails = [("a.py", "f")]
    silenced, surviving, warnings = _gate_infra.apply_overrides(
        fails,
        commit_body="X-OVERRIDE: a.py:f — fix concreto\n",
        prefix="X-OVERRIDE",
        key_pattern=r"(?P<file>\S+):(?P<func>\S+)",
        fail_key_extractor=lambda f: (f[0], f[1]),
        override_key_fields=["file", "func"],
    )
    assert len(silenced) == 1
    assert surviving == []
    assert warnings == []


# ── B4 — parse_overrides catches KeyError in converter ───────────────────────


def test_parse_overrides_skips_entry_when_converter_raises_keyerror() -> None:
    """Conversor que tenta acessar group ausente do regex skipa entrada."""
    # Cenário: converter pede `entry["missing_field"]` que não existe.
    def buggy_conv(_val: str) -> int:
        # Simula erro de acesso a campo ausente. parse_overrides itera por
        # converters.items() — se conv levanta KeyError por algum motivo,
        # antes do fix B4 isso crashava o parser inteiro.
        raise KeyError("missing_field")

    overrides = _gate_infra.parse_overrides(
        commit_body="X-OVERRIDE: a.py:f cc=12 — concrete reason\n",
        prefix="X-OVERRIDE",
        key_pattern=r"(?P<file>\S+):(?P<func>\S+)\s+cc=(?P<cc>\d+)",
        value_converters={"cc": buggy_conv},
    )
    # Skip silencioso (KeyError tratado igual TypeError/ValueError)
    assert overrides == []
