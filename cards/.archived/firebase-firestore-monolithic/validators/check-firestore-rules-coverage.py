#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────
# Validator: check-firestore-rules-coverage
# Card:      firebase-firestore
# Runs-on:   verify-task, forge-doctor
# Severity:  error  (blocks-merge)
#
# Objetivo:
#   Falha se uma coleção mexida pela feature não tem rule em firestore.rules
#   cobrindo cada operação declarada em
#   data-contract-spec.yaml § firestore-collections[].operations.
#
# Inputs esperados (Phase 5):
#   - feature dir (passed pelo conductor)
#   - workflow-config.yaml (para path canônico de firestore.rules)
#   - data-contract-spec.yaml (lista de collections + operations +
#     security-rules-ref)
#
# Saída esperada (Phase 5):
#   - exit code 0:  todas as ops têm rule cobrindo
#   - exit code 1:  faltou rule para alguma op (lista no stderr com
#                   collection + op + ref ausente)
#   - exit code 2:  erro de parse / arquivo ausente
#
# TODO Phase 5: implementar parser de firestore.rules (regex + tokenizer
# simples) e cruzar com `security-rules-ref` do data-contract-spec.
# ─────────────────────────────────────────────────────────────────────────

import sys


def main() -> int:
    # TODO Phase 5
    print(
        "check-firestore-rules-coverage: stub (Phase 5) — "
        "nenhum check executado ainda.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
