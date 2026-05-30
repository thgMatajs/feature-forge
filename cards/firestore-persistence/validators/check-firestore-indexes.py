#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────
# Validator: check-firestore-indexes
# Card:      firestore-persistence
# Runs-on:   verify-task
# Severity:  warn
#
# Objetivo:
#   Avisa quando há query custom one-shot (compound where, orderBy + where)
#   sem índice declarado em firestore.indexes.json.
#
# Escopo:
#   Este validator cobre queries declaradas pelo card firestore-persistence
#   (one-shot CRUD/queries). Queries realtime (snapshot listeners) são
#   responsabilidade do card firestore-realtime e podem ter validator
#   próprio. Single-field indexes implícitos do Firestore NÃO precisam
#   declaração.
#
# Inputs esperados (Phase 5):
#   - data-contract-spec.yaml § firestore-collections[].queries[]
#     (cada query referencia um index-ref)
#   - firestore.indexes.json (path resolvido via workflow-config)
#
# Saída esperada (Phase 5):
#   - exit code 0:  todas as queries custom têm índice declarado
#   - exit code 1:  warn — lista de queries sem índice no stderr
#   - exit code 2:  erro de parse / arquivo ausente
#
# Importante:
#   NUNCA aceitar como "ok" um índice criado via Firebase console — o índice
#   precisa estar declarado no arquivo committado para garantir paridade
#   entre ambientes (dev/stg/prod) e reprodutibilidade entre devs.
#
# TODO Phase 5: implementar diff entre queries declaradas
# (data-contract-spec.yaml) e índices listados em firestore.indexes.json.
# Considerar single-field implicit indexes (Firestore cria automaticamente
# para todos os campos top-level — só compound where/orderBy precisam
# declaração explícita).
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
