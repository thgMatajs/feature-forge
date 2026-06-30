"""Safe env builder pra subprocess. Allowlist core + extras declarados.

Internal API (underscore prefix). Consumidores autorizados:
- engine.qa.sandbox
- engine.verify
- engine.qa.__init__   (alert layer)
- engine.cards.loader  (parse env-needs)
- engine.cards.grant   (decisão sensitive)
- engine.external_exec  (fronteira de execução externa, Decisão 33)

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


# deep-002: pattern com boundary explícito (^/$ ou [_-]) pra evitar
# false-positive em nomes que apenas CONTÊM substring sensível
# (ex.: AUTHOR, CO_AUTHOR, BASE_PATHTOKEN). A versão anterior usava
# `.*(AUTH|TOKEN|...).*` que matava nome legítimo `AUTHOR_NAME` e o
# escondia silenciosamente do subprocess.
#
# Cobertura:
#   - SUFIXOS sensíveis: TOKEN, SECRET, PASSWORD, CREDENTIAL,
#     API[_-]?KEY, PRIVATE[_-]?KEY, AUTHORIZATION
#   - AUTH como palavra autônoma (não dentro de AUTHOR/AUTHORIZATION)
#
# Negativos garantidos: AUTHOR, AUTHOR_NAME, CO_AUTHOR.
# Positivos canônicos: GITHUB_TOKEN, AWS_SECRET_ACCESS_KEY, DB_PASSWORD,
# AUTHORIZATION_HEADER, AUTH_USER, MY_API_KEY, RSA_PRIVATE_KEY, OAUTH_TOKEN.
SENSITIVE_PATTERN: re.Pattern[str] = re.compile(
    r"(?ix)"
    r"(?:^|[_-])"
    r"(?:"
    r"  TOKEN | SECRET | PASSWORD | CREDENTIAL"
    r"  | API[_-]?KEY | PRIVATE[_-]?KEY"
    r"  | AUTHORIZATION"
    r"  | AUTH(?=$|[_-])"
    r")"
    r"(?:$|[_-])"
)


def is_sensitive(name: object) -> bool:
    """True iff ``name`` é string e bate ``SENSITIVE_PATTERN``.

    deep-008: aceita ``object`` para fail-open defensivo. Non-str retorna
    ``False`` (não TypeError) — chamadores em código de segurança que
    queiram fail-closed devem filtrar via ``isinstance`` antes.
    """
    if not isinstance(name, str):
        return False
    return SENSITIVE_PATTERN.search(name) is not None


def build_safe_env(
    *,
    extras: Iterable[str] = (),
    allow_sensitive: bool = False,
) -> dict[str, str]:
    """Constrói env reduzido pra subprocess.

    Retorna dict com (CORE_ALLOWLIST ∪ extras) ∩ os.environ. Vars
    listadas em ``extras`` mas ausentes em ``os.environ`` são filtradas
    silenciosamente (subprocess naturalmente não as vê).

    deep-003 (defense-in-depth): por padrão, se ``extras`` contém vars
    sensitive (que batem ``SENSITIVE_PATTERN``), levanta ``ValueError``.
    Callers que JÁ passaram pelo grant flow (workflow-config.qa.
    sensitive-env-grants) devem passar ``allow_sensitive=True``. Sem esse
    guard, qualquer caller futuro que esqueça de filtrar extras
    re-introduz o leak que QA-11 fechou.

    deep-016: ``extras`` é materializado em tupla na entrada pra
    permitir re-iteração segura (defensivo contra generators).

    Raises
    ------
    TypeError
        Se algum elemento de ``extras`` não for ``str``.
    ValueError
        Se ``extras`` contém vars sensitive e ``allow_sensitive`` é False.
    """
    extras_tuple = tuple(extras)
    extras_set = _validate_extras(extras_tuple)
    if not allow_sensitive:
        bad = sorted(v for v in extras_set if is_sensitive(v))
        if bad:
            raise ValueError(
                f"build_safe_env: extras contém vars sensitive sem "
                f"allow_sensitive=True: {bad}. Passe pelo grant flow "
                f"(workflow-config.qa.sensitive-env-grants) antes."
            )
    allowed = CORE_ALLOWLIST | extras_set
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

    deep-016: ``extras`` materializado em tupla pra re-iteração segura.
    """
    extras_tuple = tuple(extras)
    allowed = CORE_ALLOWLIST | _validate_extras(extras_tuple)
    return sorted(k for k in os.environ if k not in allowed)
