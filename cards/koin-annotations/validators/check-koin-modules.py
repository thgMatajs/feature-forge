#!/usr/bin/env python3
# ──────────────────────────────────────────────────────────────────────────
# check-koin-modules.py — validator stub do card koin-annotations
#
# Executa duas checagens determinísticas:
#
#   (1) Toda classe anotada com @Module deve ter @ComponentScan no mesmo
#       arquivo. Falha com severity=error caso contrário.
#
#   (2) DSL `module { ... }` é proibida em código de produção (qualquer
#       source set que NÃO seja commonTest / androidUnitTest / iosTest).
#       Acionada com flag --dsl-check.
#
# TODO Phase 5:
#   - Substituir busca textual por parse via tree-sitter ou kotlinc -Xfir
#   - Permitir allowlist explícita para casos legados (com aprovação)
#   - Reportar JSON estruturado consumido pelo forge verify
#   - Cobrir @ComponentScan sem string literal (deve apontar para pacote real)
#   - Detectar @KoinViewModel em commonMain (atualmente fora do escopo)
# ──────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

MODULE_ANNOTATION = re.compile(r"^\s*@Module\b", re.MULTILINE)
COMPONENT_SCAN_ANNOTATION = re.compile(r"^\s*@ComponentScan\b", re.MULTILINE)
MODULE_DSL_CALL = re.compile(r"\bmodule\s*\{")

PRODUCTION_SOURCE_SETS = (
    "/src/commonMain/",
    "/src/androidMain/",
    "/src/iosMain/",
    "/src/iosArm64Main/",
    "/src/iosSimulatorArm64Main/",
    "/src/iosX64Main/",
    "/src/jvmMain/",
    "/src/jsMain/",
    "/src/main/",
)

TEST_SOURCE_SETS = (
    "/src/commonTest/",
    "/src/androidUnitTest/",
    "/src/androidInstrumentedTest/",
    "/src/iosTest/",
    "/src/jvmTest/",
    "/src/test/",
)


def is_production_path(path: Path) -> bool:
    p = path.as_posix()
    if any(seg in p for seg in TEST_SOURCE_SETS):
        return False
    return any(seg in p for seg in PRODUCTION_SOURCE_SETS)


def check_module_componentscan_pair(root: Path) -> list[str]:
    failures: list[str] = []
    for kt in root.rglob("*.kt"):
        try:
            text = kt.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not MODULE_ANNOTATION.search(text):
            continue
        if not COMPONENT_SCAN_ANNOTATION.search(text):
            failures.append(
                f"{kt}: @Module sem @ComponentScan no mesmo arquivo "
                f"(card koin-annotations exige pareamento explicito)."
            )
    return failures


def check_dsl_banned_in_production(root: Path) -> list[str]:
    failures: list[str] = []
    for kt in root.rglob("*.kt"):
        if not is_production_path(kt):
            continue
        try:
            text = kt.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if MODULE_DSL_CALL.search(text):
            failures.append(
                f"{kt}: DSL `module {{ ... }}` em codigo de producao e proibida "
                f"pelo card koin-annotations. Use Koin Annotations "
                f"(@Module/@ComponentScan/@Single/@Factory/@KoinViewModel)."
            )
    return failures


def main() -> int:
    # Contrato canônico de validator (BUG-VERIFY-1, T2): o `forge verify`
    # invoca todo validator com `--project-root <root> [--scope <kind>]
    # [--id <target>]` (ver engine.verify._invoke_validator). Antes este
    # script só aceitava `--root` → argparse estourava em "unrecognized
    # arguments" (exit 2) → cegava a cascade. Scripts de card são subprocess
    # isolados (sem módulo compartilhado), então o argparser é local — espelha
    # cards/compose-screens/validators/check-screen-layout.py.
    parser = argparse.ArgumentParser(description="Validator stub for koin-annotations card.")
    parser.add_argument("--dsl-check", action="store_true", help="Run only the module { } DSL ban check.")
    parser.add_argument(
        "--project-root",
        default=".",
        help="Project root to scan (default: cwd). Canonical verify contract.",
    )
    parser.add_argument("--scope", default=None, help="Tolerado (parse-only).")
    parser.add_argument("--id", default=None, help="Tolerado (parse-only).")
    parser.add_argument(
        "--root",
        default=None,
        help="Alias legado de --project-root (deprecado). Use --project-root.",
    )
    args = parser.parse_args()

    # --project-root é canônico; --root permanece como alias legado tolerado.
    root = Path(args.root if args.root is not None else args.project_root).resolve()

    failures: list[str] = []
    if args.dsl_check:
        failures = check_dsl_banned_in_production(root)
    else:
        failures = check_module_componentscan_pair(root)

    if failures:
        for f in failures:
            print(f"[koin-annotations] {f}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
