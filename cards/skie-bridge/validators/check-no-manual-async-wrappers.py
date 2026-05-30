#!/usr/bin/env python3
# ──────────────────────────────────────────────────────────────────────────
# check-no-manual-async-wrappers.py
#
# STUB — Phase 5 implementation.
#
# Validator do card `skie-bridge`. Severity: warn.
#
# Objetivo: detectar uso de `withCheckedContinuation` /
# `withCheckedThrowingContinuation` em arquivos `.swift` quando o callback
# envolve uma chamada a uma API do framework compartilhado (Shared/
# KMP framework). SKIE já gera `async throws` automaticamente — wrappers
# manuais são anti-padrão (ver `architecture_ios.md` § SKIE).
#
# Heurística futura:
#   1. Listar imports do arquivo `.swift`; identificar import do framework
#      compartilhado (ex.: `import Shared`).
#   2. Se presente, varrer por `withCheckedContinuation` /
#      `withCheckedThrowingContinuation` no corpo.
#   3. Para cada match, inspecionar a closure: se chama método de um
#      símbolo importado do framework Shared, emitir warn com path:line.
#   4. Sair com código 0 sempre (severity warn não bloqueia).
#
# Critérios de "skip":
#   - Arquivo fora de `iosApp/iosApp/**/*.swift` → ignora.
#   - Comentário `// skie-bridge:allow-manual-wrapper` na mesma linha do
#     `withCheckedContinuation` → ignora com aviso de revisão.
#
# Output esperado (formato):
#   WARN [skie-bridge] iosApp/iosApp/Features/Foo/FooView.swift:42
#     manual async wrapper around Shared API; SKIE gera async throws
#     automaticamente — remova o withCheckedContinuation.
#
# Exit code:
#   0 → sempre (warn never blocks).
# ──────────────────────────────────────────────────────────────────────────

import sys


def main() -> int:
    # TODO Phase 5: implementar heurística descrita no header.
    # Por enquanto este stub apenas reporta que o check está pendente.
    print(
        "[skie-bridge] check-no-manual-async-wrappers.py: STUB — "
        "Phase 5 pending. No checks executed.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
