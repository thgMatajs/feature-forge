#!/usr/bin/env python3
# ──────────────────────────────────────────────────────────────────────────
# nav3 — check-no-nav-dsl.py
# Card: nav3
# Runs-on: [pre-commit, verify-task]
# Severity: error
#
# Falha o build se um arquivo Kotlin de produção contiver a DSL proibida
#   module {
#       activityRetainedScope {
#           navigation<T> { ... }
#       }
#   }
# OU APIs de Navigation 2 (NavHost, composable("..."), rememberNavController).
#
# TODO Phase 5: executor real do validator framework feature-forge. Esta
# versão é um stub que documenta o contrato (entradas, saídas, exit codes)
# para o engine resolver. Não exercitar em CI ainda.
# ──────────────────────────────────────────────────────────────────────────

"""nav3 / check-no-nav-dsl — Phase 5 stub.

Contrato esperado do validator quando implementado:

Inputs (via env, populados pelo engine):
    FORGE_REPO_ROOT          repositório alvo
    FORGE_CHANGED_FILES      lista space-separated dos arquivos do diff
                             (em pre-commit) — empty em verify-task

Output:
    exit 0   — nenhum padrão proibido encontrado
    exit 1   — pelo menos um padrão proibido encontrado; stdout lista
               file:line:snippet em formato compatível com 'reviewdog'
    exit 2   — erro interno (Python exception, arquivo inacessível, etc.)

Forbidden patterns (regex Python, multi-linha quando aplicável):
    r"\\bmodule\\s*\\{[^}]*\\bnavigation\\s*<"          # Koin DSL scoped
    r"\\bNavHost\\s*\\("                                # Navigation 2 host
    r"\\bcomposable\\s*\\(\\s*\"[^\"]+\""               # Navigation 2 string route
    r"\\brememberNavController\\s*\\("                  # Navigation 2 controller

Allowed false-positive escapes:
    - arquivos sob 'src/test/' ou 'commonTest/' (DSL permitida em test fixtures)
    - arquivos com comentário no topo "// nav3-allow-dsl: <ticket-id>"
      (gerencia exceções com rastreio)

Scope de varredura:
    - **/*.kt em FORGE_CHANGED_FILES quando rodando pre-commit
    - composeApp/**/*.kt, androidApp/**/*.kt em verify-task

Quando este stub é executado, ele apenas:
    1. imprime status="not-implemented"
    2. devolve exit 0 (não bloqueia merge)
    3. orienta a equipe a abrir issue Phase 5 para o executor.
"""

import sys

NOT_IMPLEMENTED_MSG = (
    "[nav3/check-no-nav-dsl] stub Phase 5 — validator real ainda não foi "
    "implementado. Contrato declarado em validators/check-no-nav-dsl.py.\n"
    "Quando implementado, vai grep por: navigation<T> { } (Koin DSL), "
    "NavHost(, composable(\"...\"), rememberNavController(."
)


def main() -> int:
    print(NOT_IMPLEMENTED_MSG)
    return 0


if __name__ == "__main__":
    sys.exit(main())
