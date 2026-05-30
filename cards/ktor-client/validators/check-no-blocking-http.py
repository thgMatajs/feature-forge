#!/usr/bin/env python3
# ──────────────────────────────────────────────────────────────────────────
# Validator: check-no-blocking-http
# Card:      ktor-client v1.0.0
# Runs-on:   [pre-commit, verify-task]
# Severity:  error
#
# Detecta `runBlocking { ... httpClient... ... }` envolvendo chamadas Ktor.
# `runBlocking` em código de produção bloqueia a thread chamadora — quase
# sempre a Main thread em mobile, causando jank/ANR. Toda chamada HTTP deve
# rodar dentro de `withContext(ioDispatcher) { httpClient.X(...) }` com o
# dispatcher injetado.
#
# TODO Phase 5 — implementação completa:
#   - Walk recursivamente em src/commonMain/kotlin, androidMain, iosMain.
#   - Parse cada *.kt buscando blocos `runBlocking { ... }`.
#   - Dentro de cada bloco, procurar referência a `HttpClient`, `httpClient`,
#     `.get(`, `.post(`, `.put(`, `.patch(`, `.delete(`, `.body()` (Ktor APIs).
#   - Tolerar arquivos de teste (`src/commonTest/`, `src/androidTest/`,
#     `src/iosTest/`) — runBlocking em test é aceitável.
#   - Reportar arquivo + linha + snippet.
#   - Exit code 0 (pass) ou 1 (fail).
#   - Considerar parser AST leve via `kotlinx.ast` ou regex multi-linha
#     com balance de chaves. Regex single-line não é suficiente.
#
# Stub atual: imprime aviso e sai com 0 (não bloqueia). Substituir antes
# de habilitar `severity: error` em CI.
# ──────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import sys


def main() -> int:
    sys.stderr.write(
        "[ktor-client/check-no-blocking-http] stub — Phase 5 pendente. "
        "Validator real ainda não implementado; nenhuma análise executada.\n"
    )
    # TODO Phase 5: implementar varredura real e retornar 1 em violação.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
