"""Progress bars and spinners.

Both use carriage returns (`\\r`) to overwrite the current line, so they
require a TTY. On non-TTY (piped output, CI logs), we degrade to:
- Progress: one-shot start + end lines, no in-place updates.
- Spinner: silent during run, just shows the label once.

Mentor calmo tone: progress is informative, never anxious — no exclamation
marks, no fake "almost there" messages.
"""

from __future__ import annotations

import itertools
import sys
import threading
import time
from contextlib import contextmanager
from typing import Iterator, TextIO

from . import renderer

_SPINNER_FRAMES = "⣾⣽⣻⢿⡿⣟⣯⣷"
_PROGRESS_FILLED = "█"
_PROGRESS_EMPTY = "░"


@contextmanager
def progress(
    total: int,
    label: str,
    *,
    width: int = 30,
    stream: TextIO | None = None,
) -> Iterator["Progress"]:
    """Context manager wrapping `Progress`. Always closes the line cleanly."""
    stream = stream or sys.stdout
    p = Progress(total=total, label=label, width=width, stream=stream)
    try:
        yield p
    finally:
        p.close()


class Progress:
    """Determinate progress bar. Caller drives via `update()`.

    Renders `label [████░░░░░░] 4/10` and overwrites the line each tick.
    On non-TTY, only the initial label and the final summary are printed.
    """

    def __init__(
        self,
        total: int,
        label: str,
        *,
        width: int = 30,
        stream: TextIO | None = None,
    ) -> None:
        self.total = max(1, total)
        self.label = label
        self.width = width
        self.stream = stream or sys.stdout
        self.value = 0
        self._tty = renderer._is_tty(self.stream)
        self._closed = False
        if not self._tty:
            # Non-TTY: write a one-shot start line so logs aren't silent.
            self.stream.write(f"{label}…\n")
            self.stream.flush()
        else:
            self._render()

    def update(self, n: int = 1) -> None:
        if self._closed:
            return
        self.value = min(self.total, self.value + n)
        if self._tty:
            self._render()

    def set(self, value: int) -> None:
        if self._closed:
            return
        self.value = max(0, min(self.total, value))
        if self._tty:
            self._render()

    def _render(self) -> None:
        filled = int((self.value / self.total) * self.width)
        bar = _PROGRESS_FILLED * filled + _PROGRESS_EMPTY * (self.width - filled)
        line = f"\r{self.label} [{bar}] {self.value}/{self.total}"
        self.stream.write(line)
        self.stream.flush()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._tty:
            # Finalize line with newline so subsequent output doesn't overwrite.
            self._render()
            self.stream.write("\n")
            self.stream.flush()
        else:
            self.stream.write(f"{self.label}: {self.value}/{self.total}\n")
            self.stream.flush()


@contextmanager
def spinner(label: str, *, stream: TextIO | None = None) -> Iterator["Spinner"]:
    """Context manager spinner. Always stops the worker thread on exit."""
    stream = stream or sys.stdout
    sp = Spinner(label=label, stream=stream)
    sp.start()
    try:
        yield sp
    finally:
        sp.stop()


class Spinner:
    """Indeterminate spinner driven by a background thread.

    Renders `⣾ label` cycling through braille frames at ~10 fps. Non-TTY
    callers see only the label once; no animation, no hidden state changes.
    """

    def __init__(
        self,
        label: str,
        *,
        interval: float = 0.1,
        stream: TextIO | None = None,
    ) -> None:
        self.label = label
        self.interval = interval
        self.stream = stream or sys.stdout
        self._tty = renderer._is_tty(self.stream)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if not self._tty:
            self.stream.write(f"{self.label}…\n")
            self.stream.flush()
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        frames = itertools.cycle(_SPINNER_FRAMES)
        while not self._stop.is_set():
            frame = next(frames)
            self.stream.write(f"\r{frame} {self.label}")
            self.stream.flush()
            time.sleep(self.interval)

    def stop(self, final_label: str | None = None) -> None:
        if not self._tty:
            return
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        # F4: usar display_width para calcular largura visual (emoji/CJK
        # contam como 2 colunas — `len` deixa resíduo no terminal).
        clear_width = renderer.display_width(self.label) + 4
        self.stream.write("\r" + " " * clear_width + "\r")
        if final_label:
            self.stream.write(final_label + "\n")
        self.stream.flush()
