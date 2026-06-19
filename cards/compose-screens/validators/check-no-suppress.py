#!/usr/bin/env python3
"""
check-no-suppress.py
====================

Validator do card `compose-screens`.

Objetivo
--------
Falhar quando arquivos Compose UI contiverem `@Suppress(...)` ou
`@file:Suppress(...)`. A regra do projeto é: nunca silenciar detekt/ktlint
em código Compose — corrigir a violação na raiz (ex.: extrair função para
`{Screen}Components.kt` ou `{Screen}Mappers.kt`).

Escopo
------
Arquivos `.kt` cujo path (posix) contenha um segmento Compose
(`/androidApp/` ou `/composeApp/src/`), excluindo os test source sets KMP.
Ocorrências de `@Suppress` dentro de comentário de linha (`//`), KDoc
(`/** ... */`) ou string literal são ignoradas — não são silenciamento real.

Contrato de invocação (autoritativo, `engine/verify.py::_invoke_validator`)
---------------------------------------------------------------------------
    python3 check-no-suppress.py --project-root <path> [--scope <kind> --id <target>]
com `cwd=project_root`. `--scope`/`--id` são tolerados (parse-only).

Saída
-----
- exit 0  → nenhum @Suppress encontrado em escopo Compose.
- exit 1  → ao menos um @Suppress; imprime `arquivo:linha: <trecho>` em stderr.

Severity
--------
`error` em `card.yaml` — bloqueia hard gate em pre-commit / verify-task.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Escopo Compose por segmentos de path. Scripts de card são subprocess
# isolados (sem módulo compartilhado), então a constante é local — espelha
# check-screen-layout.py do mesmo card.
COMPOSE_PATH_SEGMENTS = ("/androidApp/", "/composeApp/src/")

TEST_SOURCE_SETS = (
    "/src/commonTest/",
    "/src/androidUnitTest/",
    "/src/androidInstrumentedTest/",
    "/src/iosTest/",
    "/src/jvmTest/",
    "/src/test/",
)

SUPPRESS_RE = re.compile(r"@(?:file:)?Suppress\b")
_STRING_LITERAL_RE = re.compile(r'"(?:[^"\\]|\\.)*"')


def in_compose_scope(path: Path) -> bool:
    """True se o arquivo .kt está em código Compose UI (não em test source set)."""
    p = path.as_posix()
    if any(seg in p for seg in TEST_SOURCE_SETS):
        return False
    return any(seg in p for seg in COMPOSE_PATH_SEGMENTS)


def _strip_noise(line: str, *, in_kdoc: bool) -> tuple[str, bool]:
    """Remove conteúdo de comentário/KDoc/string da linha antes de aplicar a regex.

    Rastreia estado multi-linha de blocos KDoc (`/** ... */`). Retorna a linha
    limpa (só código "vivo") e o novo estado `in_kdoc`.
    """
    if in_kdoc:
        end = line.find("*/")
        if end == -1:
            return "", True  # linha inteira ainda dentro do bloco KDoc
        line = line[end + 2 :]
        in_kdoc = False

    # Consumir blocos `/* ... */` (e `/** ... */`) abertos nesta linha e
    # cortar comentário de linha `//`. Acumula só o código "vivo" em `out`.
    out: list[str] = []
    i = 0
    n = len(line)
    while i < n:
        two = line[i : i + 2]
        if two == "//":
            break  # resto da linha é comentário; descarta
        if two == "/*":
            end = line.find("*/", i + 2)
            if end == -1:
                in_kdoc = True
                break
            i = end + 2
            continue
        out.append(line[i])
        i += 1
    line = "".join(out)

    # Neutralizar string literais simples.
    line = _STRING_LITERAL_RE.sub('""', line)
    return line, in_kdoc


def scan_file(path: Path) -> list[str]:
    """Retorna failures `arquivo:linha: <trecho>` para cada @Suppress real."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    failures: list[str] = []
    in_kdoc = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        cleaned, in_kdoc = _strip_noise(raw, in_kdoc=in_kdoc)
        if SUPPRESS_RE.search(cleaned):
            failures.append(f"{path}:{lineno}: {raw.strip()}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="compose-screens: bloqueia @Suppress em código Compose UI."
    )
    parser.add_argument("--project-root", default=".", help="Raiz do projeto a varrer.")
    parser.add_argument("--scope", default=None, help="Tolerado (parse-only).")
    parser.add_argument("--id", default=None, help="Tolerado (parse-only).")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()

    failures: list[str] = []
    for kt in root.rglob("*.kt"):
        if not in_compose_scope(kt):
            continue
        failures.extend(scan_file(kt))

    if failures:
        for f in failures:
            print(f"[compose-screens/check-no-suppress] {f}", file=sys.stderr)
        print(
            "[compose-screens/check-no-suppress] Em Compose não silenciamos o "
            "linter. Extraia a função para {Screen}Components.kt / "
            "{Screen}Mappers.kt ou corrija a violação na raiz.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
