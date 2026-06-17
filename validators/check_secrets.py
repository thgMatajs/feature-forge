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

from typing import Any

from _common import make_paths, result_fail, result_pass, result_warn, run_cli
from _diff import git_staged_files, read_commit_body
from _gate_infra import (
    DispatchResult,
    apply_overrides as _gate_apply_overrides,
    check_tool_available,
    dispatch_native_tool,
)

# Sobe ao engine root pra importar yaml_io — mesmo pattern do CC gate
# (validators/ é package raso; engine/ é sibling com utilities).
import sys as _sys

_ENGINE_ROOT = Path(__file__).parent.parent
if str(_ENGINE_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ENGINE_ROOT))

from engine.utils.paths import forge_config_path  # noqa: E402
from engine.utils.yaml_io import read_yaml_or_default  # noqa: E402


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
                # A-005 (master review PR #15): regex inválida é skip
                # silencioso aqui; `_collect_invalid_patterns` abaixo é
                # quem coleta + reporta ao caller de alto nível
                # (`validate()`) para warning fail-loud.
                continue
        if not dropped:
            out.append(f)
    return out


def _collect_invalid_patterns(patterns: list[str]) -> list[str]:
    """A-005 (master review PR #15): retorna patterns que `re.compile` rejeita.

    `_filter_ignored` engole `re.error` por design (best-effort match),
    mas a config inválida do usuário NÃO pode ser silenciosa em `validate()`
    — sem feedback, a entrada malformada some sem rastro.
    """
    invalid: list[str] = []
    for pat in patterns:
        try:
            re.compile(pat)
        except re.error:
            invalid.append(pat)
    return invalid


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


# ── Override-justify (Task 4) ────────────────────────────────────────────────
#
# Override declarado em linha única no commit body — segue a mesma disciplina
# do CC gate (CC-OVERRIDE), apenas com prefix e cover key adaptados pro
# domínio. Parser + apply são genéricos em ``_gate_infra``; aqui ficamos só
# com a especialização (prefix, key_pattern, cover fields).
#
# Cover-key é ``(file, line, kind)`` — triple exato. Um override silencia
# APENAS o finding cuja tupla bate; outras ocorrências (mesmo kind, outro
# file/linha) seguem ativas. Auditoria via ``git log --grep='SECRETS-OVERRIDE'``.

_SECRETS_OVERRIDE_PREFIX = "SECRETS-OVERRIDE"
_SECRETS_OVERRIDE_KEY_PATTERN = r"(?P<file>\S+):(?P<line>\d+)\s+kind=(?P<kind>\S+)"
_SECRETS_OVERRIDE_KEY_FIELDS = ["file", "line", "kind"]
_SECRETS_OVERRIDE_VALUE_CONVERTERS = {"line": int}


def _secrets_fail_key_extractor(f: SecretFinding) -> tuple[str, int, str]:
    """Cover key do gate: ``(file, line, kind)`` — triple exigente.

    Match parcial (mesmo kind, outro arquivo) NÃO silencia — preserva a
    auditoria por ocorrência específica.
    """
    return (f.file, f.line, f.kind)


def apply_overrides(
    fails: list[SecretFinding],
    commit_body: str,
) -> tuple[list[SecretFinding], list[SecretFinding], list[str]]:
    """Thin wrapper sobre ``_gate_infra.apply_overrides`` com params do gate.

    Retorna ``(silenced, surviving, warnings)``:

    - ``silenced``: findings cobertos por algum override válido.
    - ``surviving``: findings que vão pro ``result_fail`` + render.
    - ``warnings``: linhas começando com ``SECRETS-OVERRIDE:`` que faltam o
      ``— <razão>`` (D-008 do CC gate, mesmo contrato).

    Generalização vive em ``_gate_infra`` — aqui só fixamos o prefix,
    key_pattern e cover fields pra manter os callsites enxutos.
    """
    return _gate_apply_overrides(
        fails,
        commit_body,
        prefix=_SECRETS_OVERRIDE_PREFIX,
        key_pattern=_SECRETS_OVERRIDE_KEY_PATTERN,
        fail_key_extractor=_secrets_fail_key_extractor,
        override_key_fields=_SECRETS_OVERRIDE_KEY_FIELDS,
        value_converters=_SECRETS_OVERRIDE_VALUE_CONVERTERS,
    )


# ── 3-caminhos render (canônico — snapshot test) ─────────────────────────────
#
# Vocabulário load-bearing — testes de orchestrator + integration validam
# substrings críticas (header, marcadores de stage, instrução literal do
# override). Copy edits cosméticos OK; remover header / paths / footer NÃO.
#
# Por que não generalizar em ``format_three_paths_message`` (CC gate)? O
# vocabulário é diferente o suficiente — secrets fala de "rotação" e
# "fixture", CC fala de "refatoração" e "split-task". Tentar fundir os dois
# rendeu prose genérica que perdeu o ponto. Princípio Phase 0: extrai só
# quando o 3º consumer documentado pede. Spec §3 deixa explícito.


def _render_secrets_three_paths(
    findings: list[SecretFinding], *, stage: str
) -> str:
    """Render literal do bloco 3-caminhos pro fail surviving.

    Args:
        findings: findings sobreviventes (após apply_overrides). Lista vazia
            é programming error — caller só chama quando tem o que mostrar.
        stage: ``per_task`` (gitleaks, regex-only) ou ``cascade`` (trufflehog,
            verificação ativa). Muda o marcador no ``Onde:`` e no ``Por que
            importa:`` — o resto do bloco é literal.

    Returns:
        Texto pronto pra ser anexado ao result dict no campo ``render`` e
        consumido por ``engine.implement._render_secrets_gate_block``
        (Task 5 — wave seguinte).
    """
    if not findings:
        raise ValueError(
            "_render_secrets_three_paths requires ≥1 finding "
            "(caller só deve invocar com surviving não-vazio)"
        )

    sorted_findings = sorted(findings, key=lambda f: (f.file, f.line))
    lines: list[str] = []
    lines.append("🛑 Check Secrets gate")
    lines.append("")
    lines.append("O que falhou:")
    if stage == "cascade":
        verified_count = sum(1 for f in sorted_findings if f.verified)
        lines.append(
            f"  {verified_count} secrets verificados detectados em arquivos staged."
        )
    else:
        lines.append(
            f"  {len(sorted_findings)} candidatos a secret (regex-match) "
            "detectados em arquivos staged."
        )
    lines.append("")
    lines.append("Onde:")
    for f in sorted_findings:
        flag = "(verified)" if f.verified else "(unverified — gitleaks)"
        lines.append(f"  · {f.file}:{f.line} — kind={f.kind} {flag}")
    lines.append("")
    lines.append("Por que importa:")
    lines.append(
        "  · Tokens commitados ficam no histórico mesmo após delete — "
        "rotação imediata é única mitigação."
    )
    if stage == "cascade":
        lines.append(
            "  · trufflehog confirmou ATIVA na origem (--only-verified). "
            "Não é falso positivo."
        )
    else:
        lines.append(
            "  · gitleaks marcou regex-match no per-task hook. Verificação "
            "ativa acontece na cascade (trufflehog) — bloqueio aqui é preventivo."
        )
    lines.append("  · Decision 23 — cascade fail-fast; check_secrets é gate hard.")
    lines.append("")
    lines.append("Três caminhos pra resolver:")
    lines.append("")
    lines.append("  1) Remover e rotacionar")
    lines.append(
        "     Apague a linha do arquivo, ROTACIONE o token na origem "
        "(revogue + emita novo),"
    )
    lines.append(
        "     e use variável de ambiente / secret manager pro novo valor."
    )
    lines.append(
        "     Token já commitado vive no git history — assume comprometido."
    )
    lines.append("")
    lines.append("  2) Override-justify (commit body) — apenas pra test fixtures")
    lines.append(
        "     Se a string é deliberadamente um fixture (test, doc exemplo), "
        "adicione ao commit body"
    )
    lines.append("     — EXATAMENTE este formato:")
    lines.append("")
    lines.append(
        "         SECRETS-OVERRIDE: <file>:<line> kind=<token-type> — <razão concreta>"
    )
    lines.append("")
    lines.append(
        "     Validator detecta a linha no commit body e libera APENAS este commit."
    )
    lines.append(
        "     Auditável via `git log --grep='SECRETS-OVERRIDE'`. NÃO é "
        "whitelist persistente."
    )
    lines.append("")
    lines.append("  3) Marcar como fixture")
    lines.append(
        "     Mova o arquivo pra `tests/fixtures/secrets/` (já no `ignore-paths` "
        "default)."
    )
    lines.append(
        "     Use chars deliberadamente inválidos no token (ex: "
        "`AKIA00000000FAKE`) pra"
    )
    lines.append("     trufflehog --only-verified não bater.")
    lines.append("")
    lines.append("Sem auto-fix aqui — escolha humana.")
    return "\n".join(lines)


# ── Orchestrator (Task 4) ────────────────────────────────────────────────────
#
# ``validate(project_root, stage=...)`` é o entry-point chamado tanto pelo
# cascade (``forge verify`` → stage="cascade") quanto pelo per-task hook
# (``forge implement`` → stage="per_task"). Wiring final segue spec §2:
#
#   1. Lê workflow-config; short-circuit warn se ``enabled=false``.
#   2. ``git_staged_files`` (sem filtro de extensão — secrets em qualquer file).
#   3. Aplica ``ignore-paths`` (defaults + config-extra).
#   4. ``check_tool_available(tool)`` — missing → result_warn (cascade alive).
#   5. ``_dispatch_for_stage`` (benign_nonzero=(1,) já injetado lá dentro).
#   6. Parse via ``_parse_gitleaks_json`` (per_task) ou ``_parse_trufflehog_json``
#      (cascade).
#   7. ``apply_overrides`` lê ``read_commit_body`` e silencia matches exatos.
#   8. result_fail com ``render`` populated se surviving; senão result_pass /
#      result_warn (se houve override malformed).
#
# Sem behavior-change comparado ao CC gate — compõe Phase 0 inteira.


_SECRETS_TOOL_INSTALL_HINTS: dict[str, str] = {
    "gitleaks": (
        "brew install gitleaks    # or: "
        "go install github.com/gitleaks/gitleaks/v8@latest"
    ),
    "trufflehog": "brew install trufflehog",
}

# Defaults: fixture dir pra evitar false positives quando o próprio
# repo testa o gate. Ordem é literal — repo dev pode prepender em
# ``secrets-gate.ignore-paths`` mas não substitui.
# M-12: anchor pattern to start-of-path. Prevents false-positive ignores
# like `src/tests/fixtures/secrets/x.py` which is NOT the project's tests
# root. The default ignore is exclusively the repo's tests/ root; consumers
# who need additional ignore paths must opt-in via
# ``secrets-gate.ignore-paths`` in workflow-config.
_DEFAULT_IGNORE_PATTERNS: list[str] = [r"^tests/fixtures/secrets/"]


def _load_workflow_config(project_root: Path) -> dict[str, Any]:
    """Lê ``.claude/forge/forge-config.yaml`` ou devolve ``{}`` se ausente/inválido.

    Paralelo direto do helper do CC gate — mesmo pattern, sem reuso porque
    cada validator tem o próprio import e função one-liner não justifica
    extração ainda (princípio Phase 0: 2-3 consumers documentados antes).

    Task 0.8 (v1.3 pilot-ready): callsite migrado pra ``forge_config_path``
    helper — config canônico agora vive sob o sub-namespace
    ``.claude/forge/`` (spec §2).
    """
    cfg_path = forge_config_path(project_root)
    return read_yaml_or_default(cfg_path, {}) or {}


def validate(
    project_root: Path,
    *,
    stage: str = "cascade",
    **kwargs: Any,
) -> dict[str, Any]:
    """Main entry-point — orquestra o pipeline de secrets gate completo.

    Args:
        project_root: Raiz do projeto consumidor (contém ``.claude/``).
        stage: ``"per_task"`` (gitleaks, hook de ``forge implement``) ou
            ``"cascade"`` (trufflehog ``--only-verified``, ``forge verify``).
            Default ``"cascade"`` é decisão consciente — ``forge verify`` é
            o consumer mais comum pra invocação direta.
        **kwargs: Reservado pra args extras vindos do ``run_cli`` (scope, id).

    Returns:
        Result dict ``{status, message, ...}`` produzido por
        ``result_pass`` / ``result_warn`` / ``result_fail``. Quando fail,
        ``paths`` carrega o 3-paths block obrigatório (disciplina §1) e
        ``render`` o texto canônico pra surfacing UX.

    Pipeline detalhado: vide bloco de cabeçalho desta seção + spec §2.
    """
    config = _load_workflow_config(project_root)
    sec_block = config.get("secrets-gate") if isinstance(config, dict) else None
    if isinstance(sec_block, dict) and sec_block.get("enabled") is False:
        return result_warn(
            "secrets-gate desligado em workflow-config (secrets-gate.enabled=false)"
        )

    staged = git_staged_files(project_root)
    if not staged:
        return result_pass("nenhum staged file pra scanear")

    ignore_patterns = list(_DEFAULT_IGNORE_PATTERNS)
    extra_ignore = (
        sec_block.get("ignore-paths") if isinstance(sec_block, dict) else None
    )
    if isinstance(extra_ignore, list):
        ignore_patterns.extend(str(p) for p in extra_ignore)

    # A-005 (master review PR #15): fail-loud em regex inválida na config
    # `secrets-gate.ignore-paths`. Antes, `_filter_ignored` engolia silentemente,
    # entrada quebrada do usuário sumia sem rastro. Agora coletamos via
    # `re.compile` e devolvemos `result_warn` para o validator cascade.
    _invalid_patterns = _collect_invalid_patterns(ignore_patterns)
    if _invalid_patterns:
        return result_warn(
            "secrets-gate: ignore-paths contém regex inválida — entradas ignoradas",
            what_failed="invalid-regex-in-config",
            where="forge-config.yaml::secrets-gate.ignore-paths",
            why=[f"regex inválida: {pat!r}" for pat in _invalid_patterns],
        )

    # M-12: match patterns against paths RELATIVE to project_root so that
    # the anchored default ``^tests/fixtures/secrets/`` correctly targets
    # only the repo's tests root (not nested ``src/tests/...`` or absolute
    # path prefixes). Preserve original Path objects for downstream tools.
    #
    # A-004 (master review PR #15): chave do `_rel_map` precisa ser o Path
    # original (não a string relativa), porque em projetos com symlinks dois
    # staged paths distintos podem reduzir pra mesma string relativa e o
    # último vencer descartava silenciosamente o primeiro. Detectamos colisão
    # e caímos em modo conservador (skip relativization, deixa o `_filter_ignored`
    # rodar direto sobre os Path originais).
    _rel_pairs: list[tuple[Path, Path]] = []  # (relativized, original)
    _seen_rel: dict[str, Path] = {}
    _collision = False
    for _p in staged:
        try:
            _rel = _p.relative_to(project_root)
        except ValueError:
            _rel = _p
        _rel_str = str(_rel)
        prior = _seen_rel.get(_rel_str)
        if prior is not None and prior != _p:
            _collision = True
            break
        _seen_rel[_rel_str] = _p
        _rel_pairs.append((_rel, _p))

    if _collision:
        # Modo conservador: filtra com paths originais (string absoluta).
        # Patterns anchored em rel-path podem falhar — aceito frente a perder
        # arquivo do scan silenciosamente. M-12 é otimização de match accuracy,
        # não pode regredir cobertura.
        staged = _filter_ignored(staged, ignore_patterns)
    else:
        _rel_kept = _filter_ignored([rel for rel, _ in _rel_pairs], ignore_patterns)
        _rel_kept_set = {str(r) for r in _rel_kept}
        staged = [orig for rel, orig in _rel_pairs if str(rel) in _rel_kept_set]
    if not staged:
        return result_pass(
            "ignore-paths filtrou todos os staged files — nada a scanear"
        )

    if stage not in _SECRETS_TOOL_BIN:
        return result_warn(
            f"stage desconhecido: {stage!r} (esperado 'per_task' ou 'cascade')"
        )
    tool_bin = _SECRETS_TOOL_BIN[stage]
    if not check_tool_available(tool_bin):
        hint = _SECRETS_TOOL_INSTALL_HINTS.get(tool_bin, "(no hint)")
        return result_warn(
            f"{tool_bin} não instalado — skip {stage} secrets scan. "
            f"install: {hint}"
        )

    dispatch_res = _dispatch_for_stage(stage, staged, project_root=project_root)
    if dispatch_res.crashed:
        return result_warn(
            f"{tool_bin} crashed: {dispatch_res.error_message or '(no stderr)'}"
        )

    parser = (
        _parse_gitleaks_json if stage == "per_task" else _parse_trufflehog_json
    )
    findings = parser(dispatch_res.raw_stdout)
    if not findings:
        return result_pass("zero secrets detectados")

    commit_body = read_commit_body(project_root)
    silenced, surviving, override_warnings = apply_overrides(findings, commit_body)

    if not surviving:
        msg = (
            f"check_secrets ok ({len(silenced)} silenciado(s) via SECRETS-OVERRIDE)"
        )
        if override_warnings:
            res = result_warn(
                msg + "; tentativas malformed: " + "; ".join(override_warnings)
            )
            res["warnings"] = override_warnings
            return res
        return result_pass(msg)

    render = _render_secrets_three_paths(surviving, stage=stage)
    sample = ", ".join(
        f"{f.file}:{f.line} kind={f.kind}" for f in surviving[:3]
    )
    res = result_fail(
        f"Check Secrets gate: {len(surviving)} secret(s) detectado(s)",
        what_failed=sample,
        where="staged files",
        why=[
            (
                "Tokens commitados vivem no histórico — rotação é única "
                "mitigação."
            ),
            (
                "trufflehog confirmou ATIVA (--only-verified)."
                if stage == "cascade"
                else "gitleaks regex-match (per-task — verificação ativa na cascade)."
            ),
            "Decision 23 — cascade fail-fast; check_secrets é gate hard.",
        ],
        paths=make_paths(
            "Remover e rotacionar",
            (
                "Apague + revogue na origem + emita novo + use env / secret "
                "manager."
            ),
            "Override-justify no commit body",
            (
                "SECRETS-OVERRIDE: <file>:<line> kind=<type> — <razão>. "
                "Use APENAS pra test fixtures genuínos."
            ),
            "Marcar como fixture",
            (
                "Mova pra tests/fixtures/secrets/ e use chars FAKE no token "
                "(ex: AKIA00000000FAKE)."
            ),
        ),
    )
    res["render"] = render
    if override_warnings:
        res["warnings"] = override_warnings
    return res


if __name__ == "__main__":
    _sys.exit(run_cli(__doc__ or "", validate))
