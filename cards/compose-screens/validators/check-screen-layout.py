#!/usr/bin/env python3
"""
check-screen-layout.py
======================

Validator do card `compose-screens`.

Objetivo
--------
Falhar quando um diretório de tela Compose não segue o pareamento obrigatório:

    .../ui/{screen}/
    ├── {Screen}Screen.kt        # obrigatório (stateful host)
    ├── {Screen}Content.kt       # obrigatório (stateless content)
    ├── {Screen}Components.kt    # opcional (subcomponentes)
    └── {Screen}Mappers.kt       # opcional (mappers domain→UI)

Regra de detecção (precisa)
---------------------------
- "Diretório de tela" = qualquer dir sob escopo Compose
  (`/androidApp/` ou `/composeApp/src/`) que contenha ≥1 arquivo casando
  `{Screen}Screen.kt` (PascalCase).
- Pra cada `{Screen}Screen.kt`, o MESMO dir DEVE conter `{Screen}Content.kt`
  → ausência: `{dir}: missing {Screen}Content.kt`.
- Inverso: `{Screen}Content.kt` sem `{Screen}Screen.kt` no mesmo dir
  → `{dir}: missing {Screen}Screen.kt`.
- `{Screen}Components.kt` e `{Screen}Mappers.kt` são OPCIONAIS.
- Detecção por nome de arquivo no dir, agnóstica ao source set KMP, desde
  que o dir esteja dentro do escopo Compose.

Contrato de invocação (autoritativo, `engine/verify.py::_invoke_validator`)
---------------------------------------------------------------------------
    python3 check-screen-layout.py --project-root <path> [--scope <kind> --id <target>]
com `cwd=project_root`. `--scope`/`--id` são tolerados (parse-only).

Saída
-----
- exit 0 → todo dir de tela tem o par {Screen}Screen.kt + {Screen}Content.kt.
- exit 1 → pareamento quebrado; imprime `{dir}: missing {...}.kt` em stderr.

Severity
--------
`error` em `card.yaml`.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Iterator

# Escopo Compose por segmentos de path. Scripts de card são subprocess
# isolados (sem módulo compartilhado), então a constante é local — espelha
# check-no-suppress.py do mesmo card.
COMPOSE_PATH_SEGMENTS = ("/androidApp/", "/composeApp/src/")

# Dirs ignorados na varredura: gerados, VCS, deps. Espelha check-no-suppress.py
# do mesmo card (subprocess isolado, sem módulo compartilhado) (M1).
EXCLUDED_DIR_NAMES = frozenset(
    {"build", ".gradle", "node_modules", ".git", ".idea"}
)

SCREEN_RE = re.compile(r"^(?P<screen>[A-Z][A-Za-z0-9]*)Screen\.kt$")
CONTENT_RE = re.compile(r"^(?P<screen>[A-Z][A-Za-z0-9]*)Content\.kt$")


def in_compose_scope(path: Path) -> bool:
    """True se o arquivo .kt está em código Compose UI."""
    p = path.as_posix()
    return any(seg in p for seg in COMPOSE_PATH_SEGMENTS)


def iter_kt_files(root: Path) -> Iterator[Path]:
    """Itera arquivos `.kt` sob `root`, pulando dirs gerados/VCS/deps e SEM
    descer em dirs symlinkados (M1 — evita varredura de build/ e loop/hang).
    """
    stack: list[Path] = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
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
                    continue
                stack.append(Path(entry.path))
                continue
            if name.endswith(".kt"):
                yield Path(entry.path)


def scan_dir(directory: Path) -> list[str]:
    """Retorna failures de pareamento {Screen}Screen.kt ↔ {Screen}Content.kt."""
    screens: set[str] = set()
    contents: set[str] = set()
    try:
        entries = list(directory.iterdir())
    except OSError as exc:
        # B3: dir inacessível (permissão/IO) — pula em vez de estourar.
        print(
            f"[compose-screens/check-screen-layout] não consegui listar "
            f"{directory} ({exc.__class__.__name__}: {exc}) — pulando.",
            file=sys.stderr,
        )
        return []
    for f in entries:
        if not f.is_file():
            continue
        m = SCREEN_RE.match(f.name)
        if m:
            screens.add(m["screen"])
            continue
        m = CONTENT_RE.match(f.name)
        if m:
            contents.add(m["screen"])

    failures: list[str] = []
    for s in sorted(screens - contents):
        failures.append(f"{directory}: missing {s}Content.kt")
    for s in sorted(contents - screens):
        failures.append(f"{directory}: missing {s}Screen.kt")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="compose-screens: valida o par {Screen}Screen.kt + {Screen}Content.kt."
    )
    parser.add_argument("--project-root", default=".", help="Raiz do projeto a varrer.")
    parser.add_argument("--scope", default=None, help="Tolerado (parse-only).")
    parser.add_argument("--id", default=None, help="Tolerado (parse-only).")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()

    # Dirs candidatos: parents de arquivos .kt sob escopo Compose.
    candidate_dirs = {kt.parent for kt in iter_kt_files(root) if in_compose_scope(kt)}

    failures: list[str] = []
    for d in sorted(candidate_dirs):
        failures.extend(scan_dir(d))

    if failures:
        for f in failures:
            print(f"[compose-screens/check-screen-layout] {f}", file=sys.stderr)
        print(
            "[compose-screens/check-screen-layout] Cada tela Compose precisa do "
            "par {Screen}Screen.kt (host stateful) + {Screen}Content.kt "
            "(conteúdo stateless). Crie o arquivo faltante pra completar o par.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
