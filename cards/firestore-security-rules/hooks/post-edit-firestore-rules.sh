#!/usr/bin/env bash
# cards/firestore-security-rules/hooks/post-edit-firestore-rules.sh
# ──────────────────────────────────────────────────────────────────────────
# STUB — Phase 5
#
# Trigger: post-edit em **/firestore.rules
#
# Quando implementado, este hook vai:
#
# 1. Detectar que firestore.rules foi editado (FILE="$1").
# 2. Garantir que o emulator Firestore está rodando (porta 8080):
#    - Se não, iniciar via `scripts/firebase-emulator.sh` em background.
# 3. Rodar a suíte firebase-rules-unit-testing:
#    - Default: `npx -y firebase-tools@latest emulators:exec --only firestore \
#               'npm test -- firestore-rules'`
#    - Override via `conventions.security.rules-test-framework` se projeto
#      preferir kotlin-test (`./gradlew :tests:firestoreRulesTest`) ou
#      XCTest (`xcodebuild test ...`).
# 4. Capturar exit code:
#    - 0  → log success, permitir commit.
#    - !0 → emitir erro detalhado (qual teste quebrou, qual rule afetada)
#           e bloquear commit (exit 1).
# 5. Opcional: rodar diff de rules vs versão deploy em bonsai-meo-dev
#    (smoke check de drift entre local vs remote).
#
# Variáveis de ambiente disponíveis:
#   FILE — path do arquivo editado (vem do events-mapping no card.yaml)
#
# Lifecycle: post-edit. Não-bloqueante por default; vira gate em pre-commit
# se a feature declara `firestore-rules-tests` em test-strategy.yaml.
# ──────────────────────────────────────────────────────────────────────────

# TODO Phase 5: implementação completa.
# Por ora, log + exit 0 — registrar evento mas não rodar nada.

echo "[firestore-security-rules] post-edit-firestore-rules.sh — stub Phase 5."
echo "  File edited: ${FILE:-<unknown>}"
echo "  Next steps (Phase 5): start emulator, run firebase-rules-unit-testing, block on failure."

exit 0
