#!/usr/bin/env python3
"""
check-no-suppress.py
====================

Validator stub do card `compose-screens`.

Objetivo
--------
Falhar quando arquivos Compose UI contiverem `@Suppress(...)` ou
`@file:Suppress(...)`. A regra do projeto é: nunca silenciar detekt/ktlint
em código Compose — corrigir a violação na raiz (ex.: extrair função para
`{Screen}Components.kt` ou `{Screen}Mappers.kt`).

Escopo padrão
-------------
- Arquivos sob `androidApp/feature/*/ui/**/*.kt`.
- Caminhos `composeApp/src/main/kotlin/**/*.kt` quando o repo coloca telas no
  módulo `composeApp`.

Saída esperada (Phase 5 — não implementado ainda)
-------------------------------------------------
- exit code 0  → nenhum @Suppress encontrado.
- exit code 1  → ao menos um @Suppress encontrado; imprime arquivo:linha:trecho.

Severity
--------
Configurado como `error` em `card.yaml` (bloqueia hard gate em pre-commit /
verify-task).

# TODO Phase 5: implementar leitura dos arquivos, regex robusta (ignorar
# @Suppress dentro de strings/KDoc), suporte a `--paths` para rodar só em
# arquivos modificados e integração com pre-commit hook do projeto.
"""

from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    # TODO Phase 5: validar argumentos, varrer arquivos alvo, retornar exit
    # code apropriado conforme regra acima. Por ora, stub sempre retorna 0
    # para não bloquear o pipeline antes da implementação real.
    print(
        "[compose-screens/check-no-suppress] stub — validator não implementado "
        "(Phase 5). Sem bloqueio.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
