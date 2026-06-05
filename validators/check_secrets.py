#!/usr/bin/env python3
"""check_secrets.py — multi-tool secrets scanning gate (R1.1).

Detecta tokens vazados em staged files via 2 tools nativas, escolhidas por
estágio de invocação (per spec §0 brainstorm):

- ``stage="per_task"`` → ``gitleaks`` (regex-based, ~100ms, sem network
  roundtrip — usado no hook de `forge implement`).
- ``stage="cascade"``  → ``trufflehog --only-verified`` (mais lento mas
  valida ativamente cada candidato contra a origem — usado em
  `forge verify`).

Composição: este validator é fino porque toda a mecânica de dispatch +
override + render 3-caminhos vive na infra Phase 0 — ``validators._gate_infra``
(``dispatch_native_tool``, ``check_tool_available``, ``apply_overrides``),
``validators._diff`` (``git_staged_files``, ``read_commit_body``), e
``validators._common`` (``result_pass`` / ``_fail`` / ``_warn``,
``make_paths``, ``run_cli``). O específico do gate é stage selection,
``cmd_builder`` per-tool, parser do JSON, e vocabulário do render.

Override-justify vive no commit body via prefix exato::

    SECRETS-OVERRIDE: <file>:<line> kind=<token-type> — <razão concreta>

Sem allowlist persistente — auditabilidade via ``git log --grep='SECRETS-OVERRIDE'``.
Hard-fail sempre quando secret sobrevive (decisão locked do brainstorm).
Tool missing → ``result_warn`` (cascade segue alive, igual contrato do CC gate).

Forge NÃO instala as tools (Decision 22 + filosofia trust-but-verify) — o gate
emite hint de install ao detectar ausência.

Doc canônica: ``docs/superpowers/specs/2026-06-05-check-secrets-design.md``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from _gate_infra import (
    DispatchResult,
    dispatch_native_tool,
)


@dataclass(frozen=True)
class SecretFinding:
    """Resultado normalizado de um scan de secret (tool-agnóstico).

    Emitido pelos parsers per-tool (``_parse_gitleaks_json`` /
    ``_parse_trufflehog_json`` — chegam nas Tasks 2+) e consumido por
    ``apply_overrides`` + render 3-caminhos.

    Campos:
        file:     path relativo à raiz do repo (string p/ casar com regex
                  de override sem conversão).
        line:     1-indexed; ``0`` quando a tool não reporta linha.
        kind:     ``RuleID`` do gitleaks ou ``DetectorName`` do trufflehog
                  (normalizado pelo parser).
        snippet:  primeiros ~80 chars do match — propositalmente truncado
                  pra evitar vazar o token completo em logs (defesa-em-
                  profundidade — render redige de novo antes de exibir).
        verified: ``True`` apenas quando ``trufflehog --only-verified`` confirmou
                  origem ativa. gitleaks sempre ``False`` (regex puro, sem
                  verificação ativa).
    """

    file: str
    line: int
    kind: str
    snippet: str
    verified: bool


def _filter_ignored(files: list[Path], patterns: list[str]) -> list[Path]:
    """Filtra ``files`` removendo paths que casem com QUALQUER regex em ``patterns``.

    Paralelo de ``_path_matches_ignore`` do CC gate (regra: belt-and-
    suspenders, pre-validation acontece no caller de alto nível em tasks
    seguintes). Contrato literal:

    - ``patterns`` vazio → devolve cópia dos files íntegra (sem filtragem).
    - Pattern casa via ``re.search(pat, str(path))`` → path é dropado.
    - Regex inválida em ``patterns`` é skip silencioso (``re.error``
      ignorado) — o motivo de a entrada da config ter sido ignorada vira
      warning no caller de alto nível (Task 4 cobre).

    Mantemos a busca simples (``re.search`` toda iteração) — o número de
    patterns é tipicamente baixo (≤10 entries na config) e o ganho de
    pre-compile é marginal aqui.
    """
    if not patterns:
        return list(files)
    out: list[Path] = []
    for f in files:
        rel = str(f)
        dropped = False
        for pat in patterns:
            try:
                if re.search(pat, rel):
                    dropped = True
                    break
            except re.error:
                # Regex inválida — ignora esta entry, segue avaliando o
                # resto. Caller de alto nível (Task 4) emite warning.
                continue
        if not dropped:
            out.append(f)
    return out


# ── Parsers per-tool (Task 2) ────────────────────────────────────────────────
#
# Cada parser normaliza o output nativo da tool em ``list[SecretFinding]`` —
# o shape comum consumido por ``apply_overrides`` (Task 4) e pelo render
# 3-caminhos (Task 4). Robustness contract (paralelo dos parsers do CC gate
# em ``check_cyclomatic_complexity.py``): JSON inválido / não-shape esperado
# / vazio → ``[]`` (não levanta). Spec §3 trust-but-verify — cascade segue
# alive mesmo quando a tool emite garbage.


def _parse_gitleaks_json(raw: str) -> list[SecretFinding]:
    """Parse ``gitleaks detect --report-format json`` output em SecretFindings.

    Shape: JSON array de findings. Cada entry tem ``RuleID``, ``File``,
    ``StartLine``, ``Secret``, ``Description``. ``verified`` é sempre
    ``False`` — gitleaks é regex-based, não verifica origem (filosofia do
    split per-stage: gitleaks no per_task hook = fast, sem network
    roundtrip).

    Robustness: JSON inválido / não-array / vazio → ``[]``. Entry sem
    campos opcionais ganha defaults sensatos (``file=""``, ``line=0``,
    ``kind="unknown"``). Snippet truncado em 80 chars (defesa-em-profundidade
    contra vazar token completo em logs).
    """
    try:
        data = json.loads(raw) if raw.strip() else []
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[SecretFinding] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        try:
            line_value = int(entry.get("StartLine", 0) or 0)
        except (TypeError, ValueError):
            line_value = 0
        out.append(
            SecretFinding(
                file=str(entry.get("File", "")),
                line=line_value,
                kind=str(entry.get("RuleID", "unknown")),
                snippet=str(entry.get("Secret", ""))[:80],
                verified=False,
            )
        )
    return out


def _parse_trufflehog_json(raw: str) -> list[SecretFinding]:
    """Parse ``trufflehog filesystem --json`` output em SecretFindings.

    Shape: NDJSON — 1 JSON object por linha. Cada object tem
    ``DetectorName``, ``Verified``, ``Raw``, e
    ``SourceMetadata.Data.Filesystem.{file,line}``.

    ``Verified=False`` ainda entra na lista — o filtro ``--only-verified``
    é responsabilidade da CLI flag (caller injeta no cmd_builder), não do
    parser. Parser é honesto pra debug (rodar sem o flag pra ver tudo).
    A cascade dispatch (Task 3) garante o flag.

    Robustness: linha vazia → ignorada; linha malformada → skip
    silencioso; entry sem ``SourceMetadata`` → ``file=""``, ``line=0``
    sem crash; raw vazio → ``[]``. Snippet truncado em 80 chars.
    """
    findings: list[SecretFinding] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        source_metadata = entry.get("SourceMetadata")
        if isinstance(source_metadata, dict):
            metadata = (
                source_metadata.get("Data", {}).get("Filesystem", {})
                if isinstance(source_metadata.get("Data"), dict)
                else {}
            )
            if not isinstance(metadata, dict):
                metadata = {}
        else:
            metadata = {}
        try:
            line_value = int(metadata.get("line", 0) or 0)
        except (TypeError, ValueError):
            line_value = 0
        findings.append(
            SecretFinding(
                file=str(metadata.get("file", "")),
                line=line_value,
                kind=str(entry.get("DetectorName", "unknown")),
                snippet=str(entry.get("Raw", ""))[:80],
                verified=bool(entry.get("Verified", False)),
            )
        )
    return findings


# ── Tool dispatch (Task 3) ───────────────────────────────────────────────────
#
# Stage selection (per spec §3 brainstorm 2026-06-05):
#
#   per_task → gitleaks (regex-fast, ~100ms, sem network roundtrip — usado no
#              hook entre review e commit em `forge implement`).
#   cascade  → trufflehog --only-verified (mais lento mas valida ativamente
#              cada candidato contra a origem — usado em `forge verify`).
#
# `benign_nonzero_codes=(1,)` é load-bearing: ambas as tools usam exit=1 pra
# sinalizar "encontrei findings" (não crash). É o mesmo trick do eslint que a
# infra Phase 0 já cobre — gate herda sem reinventar.
#
# Os cmd_builders ficam aqui (secrets-específicos pelas tools nativas) enquanto
# o dispatch canônico vive em `_gate_infra.dispatch_native_tool`. Os próximos
# gates (deps-cve, duplication, dead-code, arch-rules, function-length) seguem
# o mesmo padrão — cada um define seus builders, todos compartilham a infra.


def _build_gitleaks_cmd(
    tool_bin: str,
    files: list[str],
    rendered_config: Optional[str],
) -> list[str]:
    """``gitleaks detect`` com staged files via ``--source`` repetível.

    Composição literal::

        gitleaks detect --no-git --report-format=json --report-path=- \\
          --source <f1> --source <f2> ...

    Notas:
        ``--no-git`` evita scan do history inteiro — gate é diff-mode, apenas
        staged interessa. ``--report-path=-`` emite JSON no stdout pra parsear
        via ``_parse_gitleaks_json``. ``--source <path>`` é repetível em
        gitleaks v8+ pra restringir scan a paths explícitos.

        ``rendered_config`` ignorado em v1.2-dev — default rules cobrem o
        baseline (AWS, GCP, Stripe, GitHub PATs, etc.); custom rules ficam pra
        v1.3+ (gap SECRETS-1 documenta).
    """
    cmd = [
        tool_bin,
        "detect",
        "--no-git",
        "--report-format=json",
        "--report-path=-",
    ]
    for f in files:
        cmd.extend(["--source", str(f)])
    return cmd


def _build_trufflehog_cmd(
    tool_bin: str,
    files: list[str],
    rendered_config: Optional[str],
) -> list[str]:
    """``trufflehog filesystem --only-verified --json`` com files no tail.

    Composição literal::

        trufflehog filesystem --only-verified --json <f1> <f2> ...

    Notas:
        ``--only-verified`` é decisão locked do brainstorm 2026-06-05 — reporta
        apenas tokens validados ativamente contra a API de origem. Zero falsos
        positivos ao custo de perder unverifiable secrets (chaves customizadas
        sem detector). Trade-off aceito porque a cascade precisa ser confiável
        o suficiente pra hard-fail sem ruído.

        ``--json`` emite NDJSON (uma linha JSON por finding) — parser splits
        por ``\\n`` em ``_parse_trufflehog_json``.

        ``rendered_config`` ignorado em v1.2-dev (gap SECRETS-1).
    """
    cmd = [tool_bin, "filesystem", "--only-verified", "--json"]
    cmd.extend(str(f) for f in files)
    return cmd


# Stage → (tool_bin, cmd_builder). Tabela explícita pra fail-fast em stage
# desconhecido — dict lookup levanta ``KeyError`` natural, sem fallback
# silencioso que esconderia bug de wiring no caller.
_SECRETS_TOOL_BIN: dict[str, str] = {
    "per_task": "gitleaks",
    "cascade": "trufflehog",
}

_SECRETS_CMD_BUILDERS: dict[
    str, Callable[[str, list[str], Optional[str]], list[str]]
] = {
    "per_task": _build_gitleaks_cmd,
    "cascade": _build_trufflehog_cmd,
}


def _dispatch_for_stage(
    stage: str,
    files: list[Path],
    *,
    project_root: Path,
) -> DispatchResult:
    """Dispatch a tool correspondente ao ``stage`` via infra Phase 0.

    Contrato:
        ``stage="per_task"``  → gitleaks (regex-fast).
        ``stage="cascade"``   → trufflehog --only-verified (active verify).
        outro stage           → ``KeyError`` (fail-fast).

    ``files`` chega como ``list[Path]`` porque vem do alto-nível
    (``git_staged_files`` devolve Paths); convertemos pra ``list[str]`` aqui
    porque ``dispatch_native_tool`` espera strings pra repassar ao
    ``subprocess.run``. A conversão acontece em um ponto único — caller não
    precisa pensar sobre isso.

    ``language="any"`` é descritivo (secrets atravessam Kotlin, Swift, TS,
    YAML, Dockerfile, ``.env``...) — o campo existe no ``DispatchResult`` por
    contrato da infra, mas não é load-bearing aqui.

    ``benign_nonzero_codes=(1,)`` cobre o "found findings → exit=1" das duas
    tools. Sem este kwarg, o dispatch trataria findings como crash e o gate
    quebraria silenciosamente toda vez que houvesse o que reportar.
    """
    tool_bin = _SECRETS_TOOL_BIN[stage]
    cmd_builder = _SECRETS_CMD_BUILDERS[stage]
    return dispatch_native_tool(
        language="any",
        files=[str(f) for f in files],
        cmd_builder=cmd_builder,
        project_root=project_root,
        tool_bin=tool_bin,
        benign_nonzero_codes=(1,),
    )
