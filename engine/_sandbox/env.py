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

import os
import re
from typing import Iterable


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


def build_safe_env(*, extras: Iterable[str] = ()) -> dict[str, str]:
    """Constrói env reduzido pra subprocess.

    Retorna dict com (CORE_ALLOWLIST ∪ extras) ∩ os.environ. Vars
    listadas em ``extras`` mas ausentes em ``os.environ`` são filtradas
    silenciosamente (subprocess naturalmente não as vê).

    Raises
    ------
    TypeError
        Se algum elemento de ``extras`` não for ``str``.
    """
    allowed = CORE_ALLOWLIST | _validate_extras(extras)
    return {k: v for k, v in os.environ.items() if k in allowed}


def _validate_extras(extras: Iterable[str]) -> frozenset[str]:
    """Type-check + freeze. TypeError se houver não-string."""
    out: set[str] = set()
    for v in extras:
        if not isinstance(v, str):
            raise TypeError(
                f"build_safe_env extras: expected str, got {type(v).__name__} ({v!r})"
            )
        out.add(v)
    return frozenset(out)


def inspect_dropped(*, extras: Iterable[str] = ()) -> list[str]:
    """Retorna lista ordenada de vars em os.environ que seriam dropadas.

    Útil pra alert layer pré Phase 3: caller filtra por ``is_sensitive``
    pra decidir se dispara prompt.
    """
    allowed = CORE_ALLOWLIST | _validate_extras(extras)
    return sorted(k for k in os.environ if k not in allowed)
