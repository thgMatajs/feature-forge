#!/usr/bin/env python3
"""
check-screen-layout.py
======================

Validator stub do card `compose-screens`.

Objetivo
--------
Falhar quando um diretório de tela Compose não segue o layout obrigatório:

    androidApp/feature/{feature}/ui/{screen}/
    ├── {Screen}Screen.kt        # obrigatório (stateful host)
    ├── {Screen}Content.kt       # obrigatório (stateless content)
    ├── {Screen}Components.kt    # opcional (subcomponentes)
    └── {Screen}Mappers.kt       # opcional (mappers domain→UI)

Regras
------
- Se existe `{Screen}Screen.kt` mas falta `{Screen}Content.kt` → erro.
- Se existe `{Screen}Content.kt` mas falta `{Screen}Screen.kt` → erro.
- Arquivos `Screen.kt` / `Content.kt` devem usar PascalCase no prefixo.
- Arquivos genéricos sem o prefixo (ex.: `View.kt`, `Page.kt`) → erro.
- Composable com `@Suppress` é responsabilidade do outro validator
  (`check-no-suppress.py`) — este foca em estrutura de arquivos.

Saída esperada (Phase 5 — não implementado ainda)
-------------------------------------------------
- exit code 0 → layout válido em todos os diretórios escaneados.
- exit code 1 → ao menos um diretório viola o layout; imprime
  `{path}: missing {Screen}Content.kt` etc.

Severity
--------
Configurado como `error` em `card.yaml`.

# TODO Phase 5: enumerar diretórios `androidApp/feature/*/ui/*/`, listar
# arquivos `*Screen.kt` e validar par `*Content.kt` correspondente. Suportar
# argumento `--feature {slug}` para restringir o escopo durante verify-task.
"""

from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    # TODO Phase 5: implementar varredura real conforme regras acima. Stub
    # atual sempre retorna 0 para não bloquear o pipeline antes da Phase 5.
    print(
        "[compose-screens/check-screen-layout] stub — validator não "
        "implementado (Phase 5). Sem bloqueio.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
