"""Mentor calmo persona — phrase library + drill-down rules.

The persona's voice is centralised here so every command sounds like the
same person. Anywhere else that hardcodes a greeting, an acknowledgement,
or a gate-violation header is a bug.

Voice rules (from `docs/design/01-decisions.md` #2 + roteiros):
- Warm, explanatory, didactic.
- Firm at gates — never improvise a 4th path; never auto-fix.
- No exclamation marks; no "yay!"; no "let's go!".
- Portuguese (Brazil) by default.
"""

from .mentor_calmo import (  # noqa: F401  re-export public surface
    acknowledgment,
    abort_warning,
    drilldown_question,
    gate_violation_header,
    greeting,
    pause_message,
    progress_phrase,
    three_paths_block,
)
