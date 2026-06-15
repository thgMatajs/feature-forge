"""engine.detection — composer + helpers para detecção multi-axis (DET-6).

W5.1 entrega skeleton: `compose_backend_axes()` agrega signals por
(axis, platform) e emite `Cell | Conflict | None`. Reusa
`_eval_detection_signals` + `_eval_gradle_dep` de `engine.init`.
"""

from engine.detection.composer import (
    Cell,
    ComposerCell,
    Conflict,
    DEFAULT_THRESHOLD,
    compose_backend_axes,
)

__all__ = [
    "Cell",
    "ComposerCell",
    "Conflict",
    "DEFAULT_THRESHOLD",
    "compose_backend_axes",
]
