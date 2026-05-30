#!/usr/bin/env python3
# cards/firebase-storage/validators/check-storage-rules-coverage.py
# ──────────────────────────────────────────────────────────────────────────
# STUB — Phase 5
#
# Quando implementado, este validator vai:
#
# 1. Ler `data-contract-spec.yaml` da feature ativa, coletar a lista de
#    `storage-paths.assets[].path-template`.
# 2. Ler `storage.rules` na raiz do repositório.
# 3. Para cada `path-template`, verificar:
#    a. Existe um bloco `match /{path-shape}/{allPaths=**}` que cobre o path.
#    b. O bloco contém as required-constraints declaradas
#       (`request.auth.uid == userId`, `request.resource.size < N`,
#       `request.resource.contentType.matches('...')`).
# 4. Adicionalmente, fazer scan estático em `shared/feature/*/src/commonMain`
#    e `iosApp/**/*.swift` por chamadas literais a Storage (`.reference(...)`,
#    `StorageReference("...")`) e bater contra `assets[].path-template`.
#    Qualquer literal de path que não esteja na lista é violação.
# 5. Exit 0 se tudo coberto; exit 1 com mensagem por path não-coberto.
#
# Flags previstas:
#   --feature <slug>      restringe a um feature dir
#   --rules-file <path>   override do path de storage.rules
#   --strict              falha também se rules cobrirem path não declarado
#
# Severity: error (definido em card.yaml). Lifecycle: verify-task + forge-doctor.
# ──────────────────────────────────────────────────────────────────────────

# TODO Phase 5: implementação completa.
# Por ora, exit 0 para não bloquear nada — apenas registrado como gate.

import sys

if __name__ == "__main__":
    print("[firebase-storage] check-storage-rules-coverage.py — stub Phase 5, no-op.")
    sys.exit(0)
