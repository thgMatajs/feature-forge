"""Box-drawing and ANSI text formatting.

Single source of truth for cinematic output: every box, divider, header, or
coloured token in the engine must go through this module so non-TTY callers
get clean text automatically.

Unicode chars used (BMP only — safe on every modern terminal):
    ┌ ┐ └ ┘ ─ │ ├ ┤ ┬ ┴ ┼

Colour palette is 256-color SGR — falls back to no-colour when stdout is
not a TTY or when `NO_COLOR` env var is set (https://no-color.org).

Non-TTY output (pipes, CI, redirects):
    SGR sequences are stripped AND box-drawing Unicode chars are degraded to
    plain ASCII via `to_ascii_box()`.  The degradation table lives in
    `_BOX_TO_ASCII` and is applied inside `write()` — the single canonical
    write path — so every caller is covered automatically.
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

# Translation table: box-drawing Unicode → plain ASCII.
# Used by `to_ascii_box()` for non-TTY output (pipes, CI, redirects).
# Corner/junction chars → '+'; horizontal → '-'; vertical → '|'.
# ASCII replacements are all single-column wide (same as the originals in
# BMP), so `display_width()` calculations remain correct after translation.
_BOX_TO_ASCII: dict[int, str] = str.maketrans(
    "┌┐└┘├┤┬┴┼",  # corners + junctions  → +
    "+++++++++",
) | {
    ord("─"): "-",  # horizontal bar
    ord("│"): "|",  # vertical bar
}

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


def to_ascii_box(text: str) -> str:
    """Degrade box-drawing Unicode chars to plain ASCII equivalents.

    Converts the full set of box-drawing chars used by this module:
        corners and junctions (┌┐└┘├┤┬┴┼) → '+'
        horizontal bar (─)                 → '-'
        vertical bar (│)                   → '|'

    All replacements are single display-column wide (same as the originals),
    so padding and width calculations are unaffected.

    Called by `write()` for non-TTY streams.  Exposed as a public helper so
    callers that build strings outside `write()` can also apply the
    degradation, and so tests can exercise the mapping in isolation.
    """
    return text.translate(_BOX_TO_ASCII)


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
    """Single canonical write path.

    For TTY streams: writes `text` as-is (Unicode box-drawing + SGR colours
    preserved).

    For non-TTY streams (pipes, CI, redirects): strips SGR escape sequences
    via `strip_ansi()` AND degrades box-drawing Unicode to plain ASCII via
    `to_ascii_box()`.  Both transformations are applied here — the single
    chokepoint — so every caller is covered without per-callsite changes.

    TTY detection respects `NO_COLOR` (force off) and `FORGE_FORCE_COLOR`
    (force on) via `_is_tty()`.
    """
    stream = stream or sys.stdout
    if _is_tty(stream):
        payload = text
    else:
        payload = to_ascii_box(strip_ansi(text))
    stream.write(payload)
    if newline:
        stream.write("\n")
    stream.flush()
