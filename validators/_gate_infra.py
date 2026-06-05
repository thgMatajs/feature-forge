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

import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


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


def dispatch_native_tool(
    *,
    language: str,
    files: list[str],
    cmd_builder: Callable[[str, list[str], Optional[str]], list[str]],
    project_root: Path,
    tool_bin: str,
    config_template: Optional[Path] = None,
    placeholders: Optional[dict[str, str]] = None,
    timeout: int = 60,
    benign_nonzero_codes: tuple[int, ...] = (),
) -> DispatchResult:
    """Dispatcher genérico de tool nativa CLI (gate-agnóstico).

    Cobre o padrão "1 validator dispatcha tool nativa via subprocess" que o
    CC gate codificou em PR #4 e que os próximos gates (`check_secrets`,
    `check_deps_cve`, `check_duplication`, `check_cognitive_complexity`,
    `check_dead_code`, `check_arch_rules`, `check_function_length_and_nesting`)
    vão reusar. Tools previstas: gitleaks, trufflehog, osv-scanner, jscpd,
    além de Detekt / SwiftLint / eslint / radon já em uso.

    Pipeline:
      1. `check_tool_available(tool_bin)` — se falso, devolve tool_found=False
         (caller emite result_warn, cascade segue alive per spec §3).
      2. Se `config_template` foi passado, renderiza via
         `render_config_with_placeholders` para um tempfile e injeta o path
         no `cmd_builder`. Sem template, passa `None` no terceiro arg.
      3. `cmd_builder(tool_bin, files, rendered_config)` devolve o cmd final.
      4. `subprocess.run` com timeout + capture_output; OSError e
         TimeoutExpired viram crashed=True com error_message descritivo.
      5. Exit não-zero (exceto `benign_nonzero_codes`) → crashed=True com
         stderr snippet (cap 400 chars). `benign_nonzero_codes=(1,)` cobre
         eslint exit=1 sem hard-code de linguagem aqui.
      6. Cleanup do tempfile no finally — best-effort, nunca shadow do erro.

    Contrato preservado byte-a-byte do `_dispatch_tool` original do CC gate:
    mesmos error_message prefixes, mesmo stderr cap, mesmo timeout default,
    mesma ordem de checks. Cmd construction é o ÚNICO ponto que muda — vira
    callback parametrizado em vez de switch hard-coded por linguagem.
    """
    if not check_tool_available(tool_bin):
        return DispatchResult(
            language=language,
            tool_found=False,
            crashed=False,
            raw_stdout="",
            error_message=f"{tool_bin} not installed (PATH lookup failed)",
        )

    rendered_config: Optional[str] = None
    try:
        if config_template is not None:
            rendered_config = render_config_with_placeholders(
                config_template, placeholders or {}
            )

        cmd = cmd_builder(tool_bin, files, rendered_config)

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return DispatchResult(
                language=language,
                tool_found=True,
                crashed=True,
                raw_stdout="",
                error_message=f"{tool_bin} timeout (>{timeout}s)",
            )
        except OSError as exc:
            return DispatchResult(
                language=language,
                tool_found=True,
                crashed=True,
                raw_stdout="",
                error_message=f"{tool_bin} OS error: {exc}",
            )

        benign = proc.returncode in benign_nonzero_codes
        if proc.returncode != 0 and not benign:
            return DispatchResult(
                language=language,
                tool_found=True,
                crashed=True,
                raw_stdout=proc.stdout or "",
                error_message=(proc.stderr or "").strip()[:400]
                or f"{tool_bin} exit={proc.returncode}",
            )

        return DispatchResult(
            language=language,
            tool_found=True,
            crashed=False,
            raw_stdout=proc.stdout or "",
            error_message="",
        )
    finally:
        if rendered_config:
            try:
                os.unlink(rendered_config)
            except OSError:
                # Best-effort cleanup — tempfile leak é minor leak, nunca
                # behavior bug. Não shadow a exceção real.
                pass
