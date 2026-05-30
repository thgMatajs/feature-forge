#!/usr/bin/env python3
# cards/firestore-security-rules/validators/check-firestore-rules-tests.py
# ──────────────────────────────────────────────────────────────────────────
# STUB — Phase 5
#
# Quando implementado, este validator vai:
#
# 1. Ler `firestore.rules` na raiz do repositório.
# 2. Extrair cada bloco `match /<path>/{...}` + lista de `allow <op>:` por bloco.
# 3. Ler suíte de testes (default: tests/firestore-rules/firestore-rules.test.ts;
#    aceita .test.kt ou .test.swift conforme convention do projeto).
# 4. Para cada `(path, op)` em rules:
#    a. Verificar que existe pelo menos 1 case `expected: allow` cobrindo.
#    b. Verificar que existe pelo menos 1 case `expected: deny` cobrindo
#       (cross-user OU anônimo OU threat declarado).
# 5. Verificar cobertura de threats:
#    - Cross-ler para cada threat em `security-and-threat-model.md`, batendo
#      com `cases[].threat-ref`.
# 6. Verificar que a suite roda contra emulator (start-script declarado em
#    `test-strategy.yaml > firestore-rules-tests.emulator`).
# 7. Exit 0 se cobertura completa; exit 1 com lista de rules sem teste OR
#    threats sem `deny` case.
#
# Flags previstas:
#   --rules-file <path>          override (default: firestore.rules)
#   --test-file <path>           override (default: do test-strategy.yaml)
#   --threat-model <path>        override (default: docs/specs/data/security-and-threat-model.md)
#   --min-cases-per-rule <int>   default 2 (1 allow + 1 deny)
#
# Severity: error (definido em card.yaml).
# Lifecycle: verify-task.
# ──────────────────────────────────────────────────────────────────────────

# TODO Phase 5: implementação completa.
# Por ora, exit 0 para não bloquear nada — apenas registrado como gate.

import sys

if __name__ == "__main__":
    print("[firestore-security-rules] check-firestore-rules-tests.py — stub Phase 5, no-op.")
    sys.exit(0)
