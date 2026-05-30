#!/usr/bin/env python3
# cards/firestore-security-rules/validators/check-firestore-rules-coverage.py
# ──────────────────────────────────────────────────────────────────────────
# STUB — Phase 5
#
# Quando implementado, este validator vai:
#
# 1. Ler `data-contract-spec.yaml` da feature ativa, coletar:
#    - `firestore-collections[].path` (collections mexidas pela feature)
#    - `firestore-collections[].operations` (get/list/create/update/delete)
# 2. Ler `firestore.rules` na raiz do repositório.
# 3. Para cada `collection.path`, verificar:
#    a. Existe bloco `match /<path-shape>/{...}` que cobre o path.
#    b. Cada operation declarada em data-contract tem `allow <op>:` no bloco.
#    c. Rule de update preserva `ownerUid` (se padrão field-based).
# 4. Verificar consistência com `docs/specs/data/access-matrix.md`:
#    - Toda collection da feature aparece como linha na matrix.
#    - Operations no data-contract batem com as autorizadas no matrix.
# 5. Verificar `docs/specs/data/security-and-threat-model.md`:
#    - Cada `deny` esperado tem entrada de threat correspondente.
# 6. Exit 0 se tudo coberto; exit 1 com mensagem detalhada por gap.
#
# Flags previstas:
#   --feature <slug>        restringe a um feature dir
#   --rules-file <path>     override do path de firestore.rules
#   --access-matrix <path>  override (default: docs/specs/data/access-matrix.md)
#   --strict                falha também se rules cobrirem path não declarado
#
# Severity: error (definido em card.yaml).
# Lifecycle: verify-task + forge-doctor.
# ──────────────────────────────────────────────────────────────────────────

# TODO Phase 5: implementação completa.
# Por ora, exit 0 para não bloquear nada — apenas registrado como gate.

import sys

if __name__ == "__main__":
    print("[firestore-security-rules] check-firestore-rules-coverage.py — stub Phase 5, no-op.")
    sys.exit(0)
