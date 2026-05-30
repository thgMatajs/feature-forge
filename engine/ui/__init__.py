"""Terminal UI helpers — box drawing, prompts, progress, tree.

All cinematic output (boxes, dividers, progress bars, prompts) lives here.
Engine modules must never call `print()` directly — they route through
`renderer`, `progress`, `tree`, or `question` so:

1. Non-TTY pipelines automatically strip ANSI / animations.
2. The persona voice (mentor calmo) is centralised, not sprinkled.
3. Future redirection (logging, JSON for CI) is a one-file change.
"""
