#!/usr/bin/env python3
# ──────────────────────────────────────────────────────────────────────────
# Validator: check-no-swiftlint-disable
# Card:      swiftui-screens v1.0.0
# Runs-on:   pre-commit, verify-task
# Severity:  error
#
# Verifica que nenhum arquivo .swift sob `iosApp/iosApp/` contém diretivas
# `// swiftlint:disable` ou `// swiftformat:disable` em qualquer escopo
# (linha, próxima, arquivo). Política do card é absoluta: suprimir o
# linter é proibido — corrigir a violação na raiz (extrair para
# `{Screen}Components.swift`, dividir struct, mover lógica para ViewModel).
#
# Saída:
#   exit 0  → nenhuma diretiva encontrada
#   exit 1  → ao menos uma diretiva encontrada (lista por arquivo:linha)
#
# Referência viva: ~/Documents/MeoBonsai/.claude/rules/swift-style.md §2
# ──────────────────────────────────────────────────────────────────────────

# TODO Phase 5 — implementar:
#   1. Resolver diretório raiz do projeto (git rev-parse --show-toplevel).
#   2. Glob `iosApp/iosApp/**/*.swift` (excluir `**/build/`, `**/DerivedData/`,
#      `**/Pods/`, `**/.bak/`).
#   3. Para cada arquivo, ler em UTF-8 (errors='replace') e buscar regex:
#        r'//\s*swift(lint|format):disable(\s|:|$)'
#      em qualquer linha.
#   4. Acumular ocorrências em lista `(path, lineno, snippet)`.
#   5. Se vazia → print resumo + exit 0.
#   6. Se não vazia → print uma linha por ocorrência no formato
#      `{path}:{lineno}: forbidden directive "{snippet}"` e exit 1.
#   7. Aceitar env var `SWIFTUI_SCREENS_VALIDATOR_PATHS` (CSV de paths)
#      para override em testes.
#
# Casos a considerar:
#   - Arquivos só de comentário em mass header (Apache/MIT) — irrelevante,
#     a busca é por `swiftlint:disable` / `swiftformat:disable` exato.
#   - Linhas dentro de string literal contendo a diretiva — raríssimo;
#     aceitar falso positivo (corrigir manualmente no caso real).
#   - Symlinks → seguir apenas se dentro do mesmo repo.
#
# Dependências externas: nenhuma (stdlib only — re, pathlib, sys, os).

import sys


def main() -> int:
    print("[swiftui-screens] check-no-swiftlint-disable: stub (Phase 5)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
