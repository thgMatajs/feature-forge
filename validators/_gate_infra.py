"""Reusable gate infrastructure — extracted from CC gate (PR #4) per Phase 0
of quality-gates expansion. See docs/superpowers/specs/2026-06-04-gate-infra-
extract-design.md.

Helpers here são gate-agnósticos: despacham tools nativas via subprocess,
parseiam linhas de override-justify no commit body, renderizam templates de
config com placeholders. Usados por `check_cyclomatic_complexity` hoje e
(planejado) por `check_secrets`, `check_deps_cve`, `check_duplication`,
`check_cognitive_complexity`, `check_dead_code`, `check_arch_rules`,
`check_function_length_and_nesting`.

Convenção de voz: mentor calmo. Helpers públicos não levam underscore —
sinalizam intenção de reuso pelos próximos gates. Em conflito, a spec vence.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DispatchResult:
    """Resultado de uma invocação a uma CLI tool nativa (gate-agnóstico).

    Contrato (preserva o do `_DispatchResult` original do CC gate — rename
    apenas remove o underscore, campos idênticos):

        tool_found=False  → tool ausente do PATH; caller emite result_warn com
                            install hint. `raw_stdout` / `crashed` irrelevantes.
        crashed=True      → exit não-zero (exceto `benign_nonzero_codes`),
                            timeout, ou OSError. `error_message` traz stderr
                            snippet ou descrição. `raw_stdout` pode ter parcial.
        caso contrário    → `raw_stdout` vai pro parser específico do gate
                            (ex.: `_parse_detekt`, `_parse_swiftlint`, etc.).
    """

    language: str
    tool_found: bool
    crashed: bool
    raw_stdout: str
    error_message: str


def check_tool_available(tool: str) -> bool:
    """Return True iff `tool` is on PATH (uses shutil.which).

    Não tenta executar — apenas PATH lookup. Suficiente porque tool crash
    em runtime é tratado separadamente em `dispatch_native_tool` (próxima
    extração). Gate-agnóstico: caller passa o binário esperado, sem
    referência à linguagem.
    """
    return shutil.which(tool) is not None


def render_config_with_placeholders(
    template_path: Path,
    placeholders: dict[str, str],
) -> str:
    """Render config template to a tempfile substituindo placeholders.

    Generaliza `_render_config_for_threshold` do CC gate. Caller passa dict
    tipo `{"__CC_THRESHOLD__": "10"}` (futuros: `{"__COG_THRESHOLD__": ...}`,
    `{"__LEN_LIMIT__": ...}`); função aplica `raw.replace(k, v)` para cada
    par e escreve o resultado num tempfile, devolvendo o path.

    Tempfile usa o mesmo `suffix` do template original — Detekt/SwiftLint
    e companhia parseiam config baseado na extensão (`.yml`, `.yaml`,
    `.json`), então preservar o suffix mantém o contrato sem hard-code.

    Caller é responsável pelo cleanup do tempfile (padrão try/finally com
    `os.unlink`). A função não registra atexit nem mantém referência —
    leak silencioso seria minor, mas o gate atual já cuida disso bem.
    """
    raw = template_path.read_text(encoding="utf-8")
    for placeholder, value in placeholders.items():
        raw = raw.replace(placeholder, value)
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=template_path.suffix,
        delete=False,
        encoding="utf-8",
    )
    tmp.write(raw)
    tmp.close()
    return tmp.name
