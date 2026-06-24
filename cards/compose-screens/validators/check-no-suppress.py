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
import os
import re
import sys
from pathlib import Path
from typing import Iterator, NamedTuple

# Dirs ignorados na varredura: gerados, VCS, deps. Evita falsos positivos em
# código não-fonte e gasto de tempo em árvores grandes (M1).
EXCLUDED_DIR_NAMES = frozenset(
    {"build", ".gradle", "node_modules", ".git", ".idea"}
)

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


def in_compose_scope(path: Path) -> bool:
    """True se o arquivo .kt está em código Compose UI (não em test source set)."""
    p = path.as_posix()
    if any(seg in p for seg in TEST_SOURCE_SETS):
        return False
    return any(seg in p for seg in COMPOSE_PATH_SEGMENTS)


class _ScanState(NamedTuple):
    """Estado multi-linha do scanner de `_strip_noise`.

    - `block_depth`: profundidade de aninhamento de block comments `/* ... */`.
      Kotlin permite aninhamento (`/* /* */ */`), então contamos abre/fecha em
      vez de fechar no primeiro `*/` (WR-03).
    - `in_raw_string`: dentro de uma raw-string triple-quote `\"\"\"...\"\"\"`,
      que pode atravessar várias linhas (WR-02). Conteúdo é tratado como noise.
    """

    block_depth: int = 0
    in_raw_string: bool = False


def _strip_noise(line: str, *, state: _ScanState) -> tuple[str, _ScanState]:
    """Remove conteúdo de comentário/KDoc/string da linha antes da regex.

    Faz uma varredura char-a-char numa única passada, rastreando: block
    comments aninhados (`/* ... */`, com profundidade), raw-strings
    triple-quote (`\"\"\"`), strings de aspas simples (`"..."`) e comentário
    de linha (`//`). Crucialmente, `//` e `/*` DENTRO de uma string não
    iniciam comentário (WR-01) — a string é neutralizada inline.

    Retorna a linha "viva" (só código fora de comentário/string) e o novo
    estado multi-linha.
    """
    block_depth = state.block_depth
    in_raw_string = state.in_raw_string

    out: list[str] = []
    i = 0
    n = len(line)
    while i < n:
        # Dentro de raw-string multi-linha: tudo é noise até o `"""` de fecho.
        if in_raw_string:
            if line[i : i + 3] == '"""':
                in_raw_string = False
                i += 3
                continue
            i += 1
            continue

        # Dentro de block comment: tudo é noise; rastreia aninhamento.
        if block_depth > 0:
            two = line[i : i + 2]
            if two == "/*":
                block_depth += 1
                i += 2
                continue
            if two == "*/":
                block_depth -= 1
                i += 2
                continue
            i += 1
            continue

        # Código vivo: detecta início de comentários, raw-strings e strings.
        if line[i : i + 3] == '"""':
            in_raw_string = True
            i += 3
            continue

        two = line[i : i + 2]
        if two == "//":
            break  # resto da linha é comentário de linha; descarta
        if two == "/*":
            block_depth += 1
            i += 2
            continue
        if line[i] == "'":
            # Char literal Kotlin: `'x'`, `'\''`, `'\n'`, `'"'`. Consome até o
            # `'` de fecho respeitando escapes. Um `"` DENTRO do char literal
            # NÃO pode fazer o scanner entrar em modo string e engolir um
            # `@Suppress` posterior (A1). Emite placeholder neutro.
            j = i + 1
            while j < n:
                if line[j] == "\\":
                    j += 2
                    continue
                if line[j] == "'":
                    j += 1
                    break
                j += 1
            out.append("''")  # placeholder neutro (não casa SUPPRESS_RE)
            i = j
            continue
        if line[i] == '"':
            # String de aspas simples: consome até o fecho (respeita escapes),
            # neutralizando o conteúdo. `//` aqui dentro NÃO trunca (WR-01).
            j = i + 1
            while j < n:
                if line[j] == "\\":
                    j += 2
                    continue
                if line[j] == '"':
                    j += 1
                    break
                j += 1
            out.append('""')  # placeholder neutro (não casa SUPPRESS_RE)
            i = j
            continue

        out.append(line[i])
        i += 1

    return "".join(out), _ScanState(block_depth=block_depth, in_raw_string=in_raw_string)


def scan_file(path: Path) -> list[str]:
    """Retorna failures `arquivo:linha: <trecho>` para cada @Suppress real.

    Fail-CLOSED (A2): se um arquivo em escopo não puder ser lido, NÃO o
    tratamos como limpo — emitimos aviso no stderr e devolvemos uma falha
    sintética, de modo que o gate bloqueie em vez de deixar passar um arquivo
    que não conseguimos auditar.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        print(
            f"[compose-screens/check-no-suppress] não consegui ler {path} "
            f"({exc.__class__.__name__}: {exc}). Trato como falha — não dá pra "
            "auditar @Suppress num arquivo ilegível.",
            file=sys.stderr,
        )
        return [f"{path}:0: <arquivo ilegível — gate falha fechado>"]

    failures: list[str] = []
    state = _ScanState()
    for lineno, raw in enumerate(text.splitlines(), start=1):
        cleaned, state = _strip_noise(raw, state=state)
        if SUPPRESS_RE.search(cleaned):
            failures.append(f"{path}:{lineno}: {raw.strip()}")
    return failures


def iter_kt_files(root: Path) -> Iterator[Path]:
    """Itera arquivos `.kt` sob `root`, pulando dirs gerados/VCS/deps e SEM
    descer em dirs symlinkados (M1 — evita loop/hang e varredura de build/).

    Replica `root.rglob("*.kt")` para fontes reais, mas com poda explícita.
    """
    stack: list[Path] = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue  # dir ilegível: pula (arquivos individuais são fail-closed)
        for entry in entries:
            name = entry.name
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if is_dir:
                if name in EXCLUDED_DIR_NAMES or name.startswith("."):
                    continue
                if entry.is_symlink():
                    continue  # não desce em symlink de dir
                stack.append(Path(entry.path))
                continue
            if name.endswith(".kt"):
                yield Path(entry.path)


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
    for kt in iter_kt_files(root):
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
