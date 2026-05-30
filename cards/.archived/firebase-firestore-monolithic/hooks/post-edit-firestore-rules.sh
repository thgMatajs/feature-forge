#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────
# Hook: post-edit-firestore-rules
# Card: firebase-firestore
# Event: post-edit
# Glob: **/firestore.rules
#
# Disparado depois de qualquer edição em firestore.rules. Responsável por
# reexecutar a suite de rules-unit-tests contra o emulator Firestore para
# garantir que a regra alterada ainda cobre todas as operações declaradas
# em data-contract-spec.yaml § firestore-collections[].operations.
#
# TODO Phase 5:
#   1. Subir emulator firestore (se não estiver up)
#   2. Rodar a runner @firebase/rules-unit-testing apontando para
#      firestore.rules editado
#   3. Falhar com exit != 0 se alguma op listada no contrato deixou de ser
#      coberta pela rule
#   4. Sugerir reabrir o tech-spec quando muda escopo da regra
# ─────────────────────────────────────────────────────────────────────────

set -euo pipefail

echo "post-edit-firestore-rules: stub (Phase 5) — nenhum check executado ainda." >&2
exit 0
