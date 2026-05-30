#!/usr/bin/env python3
# ──────────────────────────────────────────────────────────────────────────
# Validator: check-screen-layout-ios
# Card:      swiftui-screens v1.0.0
# Runs-on:   verify-task
# Severity:  warn
#
# Verifica que cada subdiretório de `iosApp/iosApp/Features/{Feature}/{Screen}/`
# segue o layout canônico de quatro arquivos:
#
#   - {Screen}ScreenView.swift
#   - {Screen}ScreenContentView.swift
#   - {Screen}Components.swift
#   - {Screen}Strings.swift
#
# Arquivos auxiliares aceitáveis (sem warning):
#   - {Feature}ViewModelAdapter.swift
#   - {Feature}UIFactory.swift
#   - {Screen}ScreenContentCallbacks.swift
#
# Política: warning (severity=warn). Telas legadas têm grace period —
# regressões em telas novas devem virar `error` em release futura
# (FOLLOWUP: trocar severity quando MeoBonsai estiver 100% adaptado).
#
# Saída:
#   exit 0  → todos os Features/Screens conformes (com possíveis warns logados)
#   exit 1  → erro irrecuperável (path inválido, IO)
#
# Referência viva: ~/Documents/MeoBonsai/.claude/rules/architecture_ios.md
#   §"Organização de Arquivos UI (obrigatório)"
# ──────────────────────────────────────────────────────────────────────────

# TODO Phase 5 — implementar:
#   1. Resolver raiz do projeto (git rev-parse --show-toplevel).
#   2. Listar imediatamente `iosApp/iosApp/Features/*/` (depth 1) → Features.
#   3. Para cada Feature:
#        a. Se contém arquivos .swift no nível raiz (não em subpasta) →
#           verificar se são `{Feature}ViewModelAdapter.swift` ou
#           `{Feature}UIFactory.swift`. Outros nomes → warn.
#        b. Para cada subpasta Screen:
#             - Extrair `{Screen}` do nome do diretório (CamelCase).
#             - Verificar presença obrigatória dos quatro arquivos canônicos.
#             - Listar arquivos `.swift` extras: aceitar
#               `{Screen}ScreenContentCallbacks.swift`; qualquer outro nome
#               → warn "non-canonical file in screen folder".
#             - Bloquear hard se encontrar `*Previews.swift` → conflita com
#               regra de preview-in-same-file (severidade lógica error mesmo
#               sob runner=warn — log explícito).
#   4. Permitir overrides via arquivo `.claude/cards/swiftui-screens/exemptions.yaml`
#      (lista de paths em grace period).
#   5. Print resumo:
#        - N Features escaneadas
#        - N Screens conformes
#        - N warnings
#
# Dependências externas: nenhuma (stdlib — pathlib, os, sys, re).

import sys


def main() -> int:
    print("[swiftui-screens] check-screen-layout-ios: stub (Phase 5)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
