#!/usr/bin/env python3
"""
check-auth-test-ids-canonical.py — STUB (Phase 5 placeholder)

Validator do card firebase-auth.

Falha quando código de auth (Android Compose ou iOS SwiftUI) contém test_id
hardcoded em vez de consumir o contrato canônico em
shared:core/observability/AuthTestIds.kt.

Regra base (espelha .claude/rules/observability.md e o script
scripts/observability/check-no-hardcoded-auth-ids.sh do projeto MeoBonsai):

  - Android:  Modifier.testTag("<string>")  com string que case
              ^(register_|login_|legal_|snackbar_).*  → fail.
              Deve ser: Modifier.testTag(AuthTestIds.<Group>.<KEY>).

  - iOS:      .accessibilityIdentifier("<string>")  com mesmo padrão → fail.
              Deve ser: .accessibilityIdentifier(AuthTestIds.<Group>.shared.<KEY>).

  - Permitidos: apenas o arquivo canônico em
                shared/core/.../observability/AuthTestIds.kt pode declarar
                as constantes string.

Runs-on:   [pre-commit, verify-task]
Severity:  error
"""

from __future__ import annotations

import sys


# TODO Phase 5 — Implementação completa:
#   1. Resolver scope de arquivos via --paths (pre-commit passa file list).
#   2. Grep regex:
#        Android: testTag\(\s*"(register_|login_|legal_|snackbar_)[a-z_]+"\s*\)
#        iOS:     accessibilityIdentifier\(\s*"(register_|login_|legal_|snackbar_)[a-z_]+"\s*\)
#   3. Permitir apenas declarações dentro do arquivo canônico.
#   4. Suportar --staged (pre-commit) e --branch <ref> (verify-task) modes.
#   5. Sair com:
#        0 — sem violações
#        1 — violações encontradas (printar arquivo:linha + sugestão de fix)
#        2 — erro interno (config inválida, paths não encontrados)
#   6. Honrar workflow-config.yaml > conventions.observability.auth-contracts-location.
#   7. Emitir JSON summary em --report-json para o forge agregar com outros validators.


def main() -> int:
    print(
        "[firebase-auth] check-auth-test-ids-canonical.py — STUB Phase 5",
        file=sys.stderr,
    )
    print(
        "[firebase-auth] Implementação completa pendente. Retornando sucesso (no-op).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
