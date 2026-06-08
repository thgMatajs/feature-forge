"""Safe env builder pra subprocess. Allowlist core + extras declarados.

Internal API (underscore prefix). Consumidores autorizados:
- engine.qa.sandbox
- engine.verify
- engine.qa.__init__   (alert layer)
- engine.cards.loader  (parse env-needs)
- engine.cards.grant   (decisão sensitive)

Externos NÃO devem importar.

Spec: docs/superpowers/specs/2026-06-08-qa-sandbox-env-hardening-design.md (QA-11).
"""

from __future__ import annotations

import re


CORE_ALLOWLIST: frozenset[str] = frozenset({
    "PATH",                              # binary lookup defensivo
    "HOME",                              # ~ expansion + cache
    "USER", "LOGNAME",                   # subprocess identity
    "LANG", "LC_ALL", "LC_CTYPE",        # unicode em pytest output
    "TZ",                                # timestamps determinísticos
    "TMPDIR", "TEMP", "TMP",             # temp file creation
    "PYTHONHASHSEED",                    # determinismo dict ordering
})


SENSITIVE_PATTERN: re.Pattern = re.compile(
    r"(?i).*(TOKEN|SECRET|PASSWORD|AUTH|CREDENTIAL|API[_-]?KEY|PRIVATE[_-]?KEY).*"
)


def is_sensitive(name: str) -> bool:
    """Testa nome contra SENSITIVE_PATTERN (case-insensitive)."""
    return SENSITIVE_PATTERN.match(name) is not None
