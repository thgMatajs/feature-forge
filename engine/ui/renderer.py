"""Box-drawing and ANSI text formatting.

Single source of truth for cinematic output: every box, divider, header, or
coloured token in the engine must go through this module so non-TTY callers
get clean text automatically.

Unicode chars used (BMP only — safe on every modern terminal):
    ┌ ┐ └ ┘ ─ │ ├ ┤ ┬ ┴ ┼

Colour palette is 256-color SGR — falls back to no-colour when stdout is
not a TTY or when `NO_COLOR` env var is set (https://no-color.org).
"""

from __future__ import annotations

import os
import sys
import unicodedata
from typing import Iterable, TextIO

# Box-drawing constants.
TL, TR, BL, BR = "┌", "┐", "└", "┘"
H, V = "─", "│"
T_DOWN, T_UP, T_LEFT, T_RIGHT, CROSS = "┬", "┴", "┤", "├", "┼"

# A minimal named palette. We map names → 256-color codes.
_PALETTE: dict[str, int] = {
    "red": 196,
    "green": 78,
    "yellow": 220,
    "blue": 75,
    "magenta": 177,
    "cyan": 80,
    "white": 255,
    "grey": 244,
    "dim_grey": 240,
}

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"


def _is_tty(stream: TextIO | None = None) -> bool:
    stream = stream or sys.stdout
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORGE_FORCE_COLOR"):
        return True
    return bool(getattr(stream, "isatty", lambda: False)())


def _wcwidth(ch: str) -> int:
    """Approximate East-Asian wide width (1 for ASCII, 2 for wide CJK)."""
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    if unicodedata.category(ch).startswith("M"):
        return 0  # combining marks add nothing
    return 1


def display_width(text: str) -> int:
    """Visible width of a string (handles wide chars + ignores ANSI)."""
    # Strip ANSI escapes for width calculation.
    stripped: list[str] = []
    skip = False
    for ch in text:
        if ch == "\033":
            skip = True
            continue
        if skip:
            if ch == "m":
                skip = False
            continue
        stripped.append(ch)
    return sum(_wcwidth(c) for c in stripped)


def colored(text: str, color: str, *, stream: TextIO | None = None) -> str:
    """Wrap `text` in a 256-colour SGR. No-op when not a TTY."""
    if not _is_tty(stream) or color not in _PALETTE:
        return text
    return f"\033[38;5;{_PALETTE[color]}m{text}{_RESET}"


def bold(text: str, *, stream: TextIO | None = None) -> str:
    if not _is_tty(stream):
        return text
    return f"{_BOLD}{text}{_RESET}"


def dim(text: str, *, stream: TextIO | None = None) -> str:
    if not _is_tty(stream):
        return text
    return f"{_DIM}{text}{_RESET}"


def strip_ansi(text: str) -> str:
    """Remove SGR escape sequences — for logs / non-TTY mirrors."""
    out: list[str] = []
    skip = False
    for ch in text:
        if ch == "\033":
            skip = True
            continue
        if skip:
            if ch == "m":
                skip = False
            continue
        out.append(ch)
    return "".join(out)


def divider(width: int = 80, *, char: str = H) -> str:
    """Horizontal rule using box-drawing dash."""
    return char * width


def section_header(text: str, *, width: int = 80) -> str:
    """`── text ──────────────` — section divider with inline label."""
    label = f" {text} "
    label_w = display_width(label)
    if label_w >= width - 2:
        return label.strip()
    fill = width - label_w - 2
    left = H * 2
    right = H * fill
    return f"{left}{label}{right}"


def box(title: str | None, lines: Iterable[str], *, width: int = 80) -> str:
    """Render a Unicode box. `title` goes inside the top border.

    Lines longer than `width - 4` are NOT auto-wrapped — caller is
    responsible. We pad to the box's inner width with spaces.
    """
    inner_w = width - 2
    out: list[str] = []

    if title:
        title_label = f" {title} "
        title_w = display_width(title_label)
        if title_w < inner_w:
            fill = inner_w - title_w
            out.append(f"{TL}{H * 1}{title_label}{H * (fill - 1)}{TR}")
        else:
            out.append(f"{TL}{H * inner_w}{TR}")
            out.append(f"{V} {title} {' ' * (inner_w - 2 - display_width(title))}{V}")
    else:
        out.append(f"{TL}{H * inner_w}{TR}")

    for line in lines:
        line_w = display_width(line)
        pad = max(0, inner_w - 2 - line_w)
        out.append(f"{V} {line}{' ' * pad} {V}")

    out.append(f"{BL}{H * inner_w}{BR}")
    return "\n".join(out)


def write(text: str, *, stream: TextIO | None = None, newline: bool = True) -> None:
    """Single canonical write path. Strips ANSI for non-TTY streams."""
    stream = stream or sys.stdout
    payload = text if _is_tty(stream) else strip_ansi(text)
    stream.write(payload)
    if newline:
        stream.write("\n")
    stream.flush()
