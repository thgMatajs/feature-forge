#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────
# Validator: check-firestore-indexes
# Card:      firebase-firestore
# Runs-on:   verify-task
# Severity:  warn
#
# Objetivo:
#   Avisa quando há query custom (compound where, orderBy + where, listener
#   com filtro composto) sem índice declarado em firestore.indexes.json.
#
# Inputs esperados (Phase 5):
#   - data-contract-spec.yaml § firestore-collections[].queries[]
#     (cada query referencia um index-ref)
#   - firestore.indexes.json (path resolvido via workflow-config)
#
# Saída esperada (Phase 5):
#   - exit code 0:  todas as queries custom têm índice
#   - exit code 1:  warn — lista de queries sem índice no stderr
#   - exit code 2:  erro de parse / arquivo ausente
#
# Importante:
#   NUNCA aceitar como "ok" um índice criado via Firebase console — o índice
#   precisa estar declarado no arquivo committado.
#
# TODO Phase 5: implementar diff entre queries declaradas e índices listados
# em firestore.indexes.json. Levar em conta single-field implicit indexes
# (Firestore cria automaticamente).
# ─────────────────────────────────────────────────────────────────────────

import sys


def main() -> int:
    # TODO Phase 5
    print(
        "check-firestore-indexes: stub (Phase 5) — "
        "nenhum check executado ainda.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
