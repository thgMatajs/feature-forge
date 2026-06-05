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
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


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


def parse_overrides(
    commit_body: str,
    *,
    prefix: str,
    key_pattern: str,
    value_converters: Optional[dict[str, Callable[[str], Any]]] = None,
    return_warnings: bool = False,
):
    """Parse `<PREFIX>: <key-pattern> — <razão>` lines do commit body.

    Generaliza `_parse_overrides` do CC gate. Caller fornece três
    ingredientes (o terceiro opcional):

    - ``prefix``: literal de início de linha (ex.: ``"CC-OVERRIDE"``,
      futuro ``"SECRETS-OVERRIDE"``, ``"DEPS-OVERRIDE"``). Aplica-se
      ``re.escape`` antes de compor o regex, então caracteres especiais
      no prefix não viram metacharacters acidentais.
    - ``key_pattern``: regex parcial com grupos nomeados (``(?P<nome>...)``)
      cobrindo o miolo entre ``<prefix>:`` e ``— <razão>``. Para o CC gate:
      ``r"(?P<file>\\S+):(?P<func>\\S+)\\s+cc=(?P<cc>\\d+)"``.
    - ``value_converters`` (opcional): map ``{group_name: callable}`` pra
      converter campos string → tipo doméstico (ex.: ``{"cc": int}``).
      Converter que raise ``(TypeError, ValueError)`` skipa a entrada
      inteira — preserva a guarda do CC original (``try: int(...) except:
      continue``). Campos não listados ficam como string.

    Disciplina (preservada byte-a-byte do CC original):

    1. **Strict pass** — exige o trailing ``— <razão concreta>`` (em-dash
       U+2014). Reason com whitespace puro (D-008) cai pro loose pass.
    2. **Loose pass** — qualquer linha que comece com ``<prefix>:`` (mesmo
       que strict não case) é candidata a warning. A linha é inspecionada
       até o ``\\n`` mais próximo; se contém ``" — "`` com tail não-vazio,
       o strict já aceitou, então skip. Caso contrário (sem em-dash, ou
       em-dash sem reason), warn ``"<prefix> sem razão concreta: ..."``.

    Returns:
        ``list[dict]`` (cada dict expõe os named groups do ``key_pattern``
        — convertidos via ``value_converters`` quando aplicável — mais
        ``"reason"`` stripado), ou tupla ``(overrides, warnings)`` quando
        ``return_warnings=True``.
    """
    strict_re = re.compile(
        rf"^{re.escape(prefix)}:\s+{key_pattern}\s+—\s+(?P<reason>.+)$",
        re.MULTILINE,
    )
    loose_re = re.compile(
        rf"^{re.escape(prefix)}:\s+.+",
        re.MULTILINE,
    )

    converters = value_converters or {}
    overrides: list[dict[str, Any]] = []
    warnings: list[str] = []
    valid_spans: set[tuple[int, int]] = set()

    # First pass: strict regex (must have a concrete reason).
    for m in strict_re.finditer(commit_body):
        reason = m.group("reason").strip()
        # D-008 — `.+` casa whitespace puro após `—`. Sem este guard,
        # `<prefix>: ... — ` viraria override válido com reason="". Skip
        # pro loose pass, que emite o warning canônico.
        if not reason:
            continue
        entry: dict[str, Any] = dict(m.groupdict())
        # Conversores domésticos (ex.: cc → int). Falha vira skip — mesmo
        # contrato do `try: int(cc) except (TypeError, ValueError): continue`
        # original do CC gate.
        skip = False
        for group_name, conv in converters.items():
            if group_name == "reason":
                continue
            try:
                entry[group_name] = conv(entry[group_name])
            except (TypeError, ValueError):
                skip = True
                break
        if skip:
            continue
        entry["reason"] = reason
        overrides.append(entry)
        valid_spans.add(m.span())

    # Second pass: loose match — linhas que LOOKAM override mas faltam o
    # `— <razão>` viram warning. Mantém o gate honesto.
    for m in loose_re.finditer(commit_body):
        if m.span() in valid_spans:
            continue
        nl = commit_body.find("\n", m.start())
        line_end = nl if nl != -1 else len(commit_body)
        line = commit_body[m.start():line_end]
        # Em-dash com tail concreto significa que o strict já aceitou
        # (linha possivelmente em outro span). Em-dash com tail vazio
        # ainda é D-008 — segue pro warn.
        if " — " in line:
            _, _, tail = line.partition(" — ")
            if tail.strip():
                continue
        warnings.append(
            f"{prefix} sem razão concreta: '{line.strip()}' — adicione texto após —"
        )

    if return_warnings:
        return overrides, warnings
    return overrides


def apply_overrides(
    fails: list,
    commit_body: str,
    *,
    prefix: str,
    key_pattern: str,
    fail_key_extractor: Callable[[Any], tuple],
    override_key_fields: list[str],
    value_converters: Optional[dict[str, Callable[[str], Any]]] = None,
) -> tuple[list, list, list[str]]:
    """Split ``fails`` em ``(silenced, surviving, warnings)`` via override lines.

    Generaliza ``_apply_overrides`` do CC gate. O caller decide a chave de
    cobertura passando duas funções alinhadas:

    - ``fail_key_extractor(fail) -> tuple`` — extrai a tupla identificadora
      do fail (CC gate: ``lambda f: (f.file, f.function)``; secrets vai
      passar ``lambda f: (f.file, f.line)``).
    - ``override_key_fields: list[str]`` — nomes dos named groups do
      ``key_pattern`` que compõem a cover tuple, **na mesma ordem** que o
      extractor produz (CC gate: ``["file", "func"]``, ignorando ``cc``
      porque ``cc`` documenta a linha mas não compõe identidade).

    Match cover:
        ``tuple(override[f] for f in override_key_fields) == fail_key_extractor(fail)``

    Warnings (linhas malformadas detectadas por ``parse_overrides``) são
    propagadas pro caller usar no result final — preserva o contrato H4
    do CC gate (warning emitido mesmo quando o gate passa).
    """
    overrides, warnings = parse_overrides(
        commit_body,
        prefix=prefix,
        key_pattern=key_pattern,
        value_converters=value_converters,
        return_warnings=True,
    )
    if not overrides:
        return [], list(fails), warnings

    cover: set[tuple] = {
        tuple(o[f] for f in override_key_fields) for o in overrides
    }
    silenced: list = []
    surviving: list = []
    for f in fails:
        if fail_key_extractor(f) in cover:
            silenced.append(f)
        else:
            surviving.append(f)
    return silenced, surviving, warnings
