"""Unit tests — engine.ui.renderer.

Covers ANSI stripping, no-color env handling, box drawing, and display
width calculation (including wide CJK characters).
"""

from __future__ import annotations

import io

import pytest

from engine.ui import renderer


def test_strip_ansi_removes_sgr():
    raw = "\033[38;5;196mred\033[0m and plain"
    assert renderer.strip_ansi(raw) == "red and plain"


def test_display_width_ignores_ansi():
    assert renderer.display_width("\033[1mhello\033[0m") == 5


def test_display_width_handles_wide_chars():
    # 全 is a CJK wide char (width 2).
    assert renderer.display_width("全") == 2
    assert renderer.display_width("ab全") == 4


def test_no_color_env_disables_color(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("FORGE_FORCE_COLOR", raising=False)
    out = renderer.colored("hi", "red")
    assert out == "hi"


def test_force_color_enables_color(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("FORGE_FORCE_COLOR", "1")
    out = renderer.colored("hi", "red")
    assert "\033[38;5;196m" in out
    assert out.endswith("\033[0m")


def test_colored_unknown_color_passthrough(monkeypatch):
    monkeypatch.setenv("FORGE_FORCE_COLOR", "1")
    assert renderer.colored("hi", "no-such-color") == "hi"


def test_divider_default_width():
    d = renderer.divider()
    assert len(d) == 80
    assert set(d) == {renderer.H}


def test_section_header_contains_label():
    out = renderer.section_header("Init", width=30)
    assert "Init" in out
    assert renderer.display_width(out) == 30


def test_box_contains_title_and_lines():
    out = renderer.box("title", ["line one", "line two"], width=30)
    assert "title" in out
    assert "line one" in out
    assert "line two" in out
    # Top/bottom borders present.
    assert renderer.TL in out
    assert renderer.BR in out


def test_box_no_title():
    out = renderer.box(None, ["only"], width=20)
    assert "only" in out
    assert renderer.TL in out


def test_write_strips_ansi_for_non_tty(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    buf = io.StringIO()
    renderer.write("\033[1mhi\033[0m", stream=buf)
    assert buf.getvalue() == "hi\n"


def test_write_no_newline(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    buf = io.StringIO()
    renderer.write("x", stream=buf, newline=False)
    assert buf.getvalue() == "x"
