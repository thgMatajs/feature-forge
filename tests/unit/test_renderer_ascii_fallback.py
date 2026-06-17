"""ASCII fallback for box-drawing chars in non-TTY output — bug U3.

Verifies that `engine.ui.renderer.write()` degrades Unicode box-drawing
chars (┌┐└┘─│├┤┬┴┼) to plain ASCII when the output stream is not a TTY,
while preserving them when it is a TTY.

Covers:
- non-TTY: box/divider/section_header output contains only ASCII (+/-/|)
  and no Unicode box-drawing chars.
- TTY: Unicode box-drawing chars are preserved.
- `to_ascii_box()` helper: maps every char in the set correctly.
- `NO_COLOR` env var forces non-TTY (ASCII degradation active).
- `FORGE_FORCE_COLOR` env var forces TTY (Unicode preserved).

Refs:
- spec bug U3 (§"Bugs usabilidade")
- engine/ui/renderer.py `write()` / `to_ascii_box()` / `_BOX_TO_ASCII`
"""

from __future__ import annotations

import io
import os
from unittest.mock import patch

import pytest

from engine.ui import renderer

# All Unicode box-drawing chars used by this module.
_BOX_CHARS = set("┌┐└┘─│├┤┬┴┼")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_stream(*, is_tty: bool) -> io.StringIO:
    """Return a StringIO whose ``isatty()`` answers `is_tty`."""
    stream = io.StringIO()
    stream.isatty = lambda: is_tty  # type: ignore[method-assign]
    return stream


def _collected(fn, *args, **kwargs) -> str:
    """Call a void `fn` that writes to a stream, return collected output."""
    stream = kwargs.pop("stream")
    fn(*args, stream=stream, **kwargs)
    return stream.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# to_ascii_box — helper isolation
# ─────────────────────────────────────────────────────────────────────────────


class TestToAsciiBox:
    """Unit tests for the `to_ascii_box()` helper in isolation."""

    def test_corners_become_plus(self):
        for ch in "┌┐└┘":
            assert renderer.to_ascii_box(ch) == "+", (
                f"corner {ch!r} should map to '+'"
            )

    def test_junctions_become_plus(self):
        for ch in "├┤┬┴┼":
            assert renderer.to_ascii_box(ch) == "+", (
                f"junction {ch!r} should map to '+'"
            )

    def test_horizontal_bar_becomes_dash(self):
        assert renderer.to_ascii_box("─") == "-"

    def test_vertical_bar_becomes_pipe(self):
        assert renderer.to_ascii_box("│") == "|"

    def test_full_box_chars_converted(self):
        input_text = "┌─┐\n│x│\n└─┘"
        output = renderer.to_ascii_box(input_text)
        assert output == "+-+\n|x|\n+-+"

    def test_plain_ascii_passthrough(self):
        text = "hello world 123 !@#"
        assert renderer.to_ascii_box(text) == text

    def test_non_box_unicode_passthrough(self):
        text = "Olá — mentor calmo"
        assert renderer.to_ascii_box(text) == text

    def test_ansi_sequences_passthrough(self):
        """to_ascii_box does NOT strip ANSI — that is strip_ansi's job."""
        ansi = "\033[38;5;78mhello\033[0m"
        assert renderer.to_ascii_box(ansi) == ansi

    def test_all_box_chars_covered(self):
        """Every char in _BOX_CHARS maps to a plain ASCII char."""
        for ch in _BOX_CHARS:
            result = renderer.to_ascii_box(ch)
            assert len(result) == 1, f"{ch!r} maps to multi-char {result!r}"
            assert result.isascii(), f"{ch!r} maps to non-ASCII {result!r}"
            assert result in "+-|", f"{ch!r} maps to unexpected char {result!r}"

    def test_idempotent(self):
        """Applying to_ascii_box twice gives the same result as once."""
        text = "┌─ header ──────┐"
        once = renderer.to_ascii_box(text)
        twice = renderer.to_ascii_box(once)
        assert once == twice


# ─────────────────────────────────────────────────────────────────────────────
# write() — non-TTY: box-drawing must be degraded
# ─────────────────────────────────────────────────────────────────────────────


class TestWriteNonTTY:
    """write() on a non-TTY stream must degrade box-drawing to ASCII."""

    def _write_box(self) -> str:
        stream = _make_stream(is_tty=False)
        text = renderer.box("titulo", ["linha 1", "linha 2"])
        renderer.write(text, stream=stream)
        return stream.getvalue()

    def _write_divider(self) -> str:
        stream = _make_stream(is_tty=False)
        text = renderer.divider(40)
        renderer.write(text, stream=stream)
        return stream.getvalue()

    def _write_section_header(self) -> str:
        stream = _make_stream(is_tty=False)
        text = renderer.section_header("minha section", width=40)
        renderer.write(text, stream=stream)
        return stream.getvalue()

    def test_box_no_unicode_box_chars(self):
        output = self._write_box()
        for ch in _BOX_CHARS:
            assert ch not in output, (
                f"box char {ch!r} leaked into non-TTY output"
            )

    def test_box_contains_ascii_plus(self):
        output = self._write_box()
        assert "+" in output

    def test_box_contains_ascii_dash(self):
        output = self._write_box()
        assert "-" in output

    def test_box_contains_ascii_pipe(self):
        output = self._write_box()
        assert "|" in output

    def test_divider_no_unicode_box_chars(self):
        output = self._write_divider()
        for ch in _BOX_CHARS:
            assert ch not in output, (
                f"box char {ch!r} leaked in divider non-TTY output"
            )

    def test_divider_contains_ascii_dash(self):
        output = self._write_divider()
        assert "-" in output

    def test_section_header_no_unicode_box_chars(self):
        output = self._write_section_header()
        for ch in _BOX_CHARS:
            assert ch not in output, (
                f"box char {ch!r} leaked in section_header non-TTY output"
            )

    def test_section_header_contains_ascii_dash(self):
        output = self._write_section_header()
        assert "-" in output

    def test_ansi_also_stripped_non_tty(self):
        """Non-TTY: SGR escapes are stripped (pre-existing behaviour preserved)."""
        stream = _make_stream(is_tty=False)
        text = "\033[38;5;78mcoloured┌┐\033[0m"
        renderer.write(text, stream=stream)
        output = stream.getvalue()
        assert "\033" not in output
        assert "┌" not in output
        assert "┐" not in output

    def test_plain_content_preserved(self):
        """Non-box, non-ANSI text survives non-TTY write unchanged."""
        stream = _make_stream(is_tty=False)
        renderer.write("hello world", stream=stream)
        assert "hello world" in stream.getvalue()

    def test_newline_appended_by_default(self):
        stream = _make_stream(is_tty=False)
        renderer.write("text", stream=stream)
        assert stream.getvalue().endswith("\n")

    def test_newline_suppressed(self):
        stream = _make_stream(is_tty=False)
        renderer.write("text", stream=stream, newline=False)
        assert not stream.getvalue().endswith("\n")


# ─────────────────────────────────────────────────────────────────────────────
# write() — TTY: Unicode box-drawing must be preserved
# ─────────────────────────────────────────────────────────────────────────────


class TestWriteTTY:
    """write() on a TTY stream must preserve Unicode box-drawing chars."""

    def test_box_preserves_unicode(self):
        stream = _make_stream(is_tty=True)
        text = renderer.box("titulo", ["linha"])
        renderer.write(text, stream=stream)
        output = stream.getvalue()
        assert "┌" in output, "TL corner missing in TTY output"

    def test_box_no_ascii_corner_replacement(self):
        """On a TTY the '+' corner replacement must NOT appear in place of ┌."""
        stream = _make_stream(is_tty=True)
        text = renderer.box("titulo", ["linha"])
        renderer.write(text, stream=stream)
        output = stream.getvalue()
        # The box chars should be present; ASCII '+' may appear in content
        # but the corners specifically rendered by renderer.box use Unicode.
        assert "┌" in output
        assert "┘" in output

    def test_divider_preserves_unicode(self):
        stream = _make_stream(is_tty=True)
        text = renderer.divider(20)
        renderer.write(text, stream=stream)
        assert "─" in stream.getvalue()

    def test_section_header_preserves_unicode(self):
        stream = _make_stream(is_tty=True)
        text = renderer.section_header("sec", width=30)
        renderer.write(text, stream=stream)
        assert "─" in stream.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# Environment-variable overrides
# ─────────────────────────────────────────────────────────────────────────────


class TestEnvVarOverrides:
    """NO_COLOR and FORGE_FORCE_COLOR interact correctly with ASCII fallback."""

    def test_no_color_forces_ascii(self, monkeypatch):
        """NO_COLOR set → treated as non-TTY → ASCII degradation active."""
        monkeypatch.setenv("NO_COLOR", "1")
        monkeypatch.delenv("FORGE_FORCE_COLOR", raising=False)
        # Even a stream that claims to be a TTY must be treated as non-TTY.
        stream = _make_stream(is_tty=True)
        text = renderer.box("x", ["y"])
        renderer.write(text, stream=stream)
        output = stream.getvalue()
        for ch in _BOX_CHARS:
            assert ch not in output, (
                f"NO_COLOR set but {ch!r} leaked into output"
            )
        assert "+" in output

    def test_forge_force_color_preserves_unicode(self, monkeypatch):
        """FORGE_FORCE_COLOR set → treated as TTY → Unicode preserved."""
        monkeypatch.setenv("FORGE_FORCE_COLOR", "1")
        monkeypatch.delenv("NO_COLOR", raising=False)
        # Even a stream that claims not to be a TTY must be treated as TTY.
        stream = _make_stream(is_tty=False)
        text = renderer.box("x", ["y"])
        renderer.write(text, stream=stream)
        output = stream.getvalue()
        assert "┌" in output, (
            "FORGE_FORCE_COLOR set but Unicode box chars were degraded"
        )

    def test_no_color_unset_uses_isatty(self, monkeypatch):
        """Without NO_COLOR/FORGE_FORCE_COLOR, isatty() drives the decision."""
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("FORGE_FORCE_COLOR", raising=False)

        non_tty = _make_stream(is_tty=False)
        text = renderer.box("x", ["y"])
        renderer.write(text, stream=non_tty)
        assert "┌" not in non_tty.getvalue()

        tty = _make_stream(is_tty=True)
        renderer.write(text, stream=tty)
        assert "┌" in tty.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# display_width regression: ASCII replacements are single-column
# ─────────────────────────────────────────────────────────────────────────────


class TestDisplayWidthRegression:
    """ASCII replacement chars have the same display width as box-drawing chars.

    Box-drawing chars are BMP U+25xx, East-Asian-Width category "Na" (narrow)
    — they count as 1 column wide.  ASCII '+', '-', '|' are also 1 column.
    Replacing one with the other must not disturb padding calculations.
    """

    @pytest.mark.parametrize("box_ch,ascii_ch", [
        ("┌", "+"), ("┐", "+"), ("└", "+"), ("┘", "+"),
        ("├", "+"), ("┤", "+"), ("┬", "+"), ("┴", "+"), ("┼", "+"),
        ("─", "-"),
        ("│", "|"),
    ])
    def test_same_display_width(self, box_ch, ascii_ch):
        w_box = renderer.display_width(box_ch)
        w_ascii = renderer.display_width(ascii_ch)
        assert w_box == w_ascii == 1, (
            f"Width mismatch: {box_ch!r}={w_box}, {ascii_ch!r}={w_ascii}"
        )
