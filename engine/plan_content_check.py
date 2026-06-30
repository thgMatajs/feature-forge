"""Content-check determinístico das waves do `forge plan` (Onda 2 — dentes).

Hoje cada wave do `forge plan` renderiza templates e pergunta
"continuar/pausar" SEM olhar o conteúdo. O piloto MeoBonsai pegou DUAS
substâncias parciais escapando pelo gate procedural:

- **tech-spec.md** com §3-§7 ainda em stubs ``{{...}}``.
- **task-breakdown.yaml** com ``dependency_graph.edges: []`` /
  ``critical_path: []`` / ``totals.tasks_count: 0`` no default (DAG vazio).

Este módulo porta a **FORMA** de dois dos 12 checks do plan-auditor
(``.claude/rules/plan-auditor.md`` + prompt do ``gsd-code-reviewer``) como
um helper Python leve e determinístico:

- categoria ``placeholder`` ── tradução de **L2** (placeholder-scan).
- categoria ``substance``  ── tradução de **C2/M2** (substance-coverage).

NÃO é uma reimplementação dos 12 checks como prompt, e NÃO importa nada de
skill/superpowers/gsd (Decisão 22 — engine não acopla a artefato de skill).
O helper é PURO: sem I/O de prompt, sem subprocess no caminho crítico (o
bloco 3-caminhos e a ramificação vivem em ``engine/plan.py``).

Ack do plan-auditor (H-001 — premissa CORRIGIDA): a regra de placeholder
NÃO é ``grep -v '^#'`` (deixaria o gate near-inert — 64/65 tokens dos
templates vivem em linhas NÃO-comentadas, ex.: ``backend: "{{x}}"``). A
regra correta remove o COMENTÁRIO TRAILING de cada linha e checa ``{{...}}``
na parte NÃO-comentada. Assim ``backend: "{{x}}"  # ex.:`` (placeholder
substantivo) É pego, e ``allowed: []  # ex.: ["{{slug}}"]`` (token só na
ilustração) é IGNORADO.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from engine.utils.yaml_io import YamlIOError, read_yaml

# Placeholder residual: ``{{...}}`` (token de template não preenchido).
_PLACEHOLDER_RE = re.compile(r"\{\{.*?\}\}")
# M-01 (gate-histérico): a detecção de TODO/TBD/FIXME em prosa foi REMOVIDA.
# Diferente do ``{{...}}`` (inequivocamente token de template residual), as
# palavras TODO/TBD/FIXME aparecem legitimamente em texto livre PT/EN ("a
# decisão está TBD", "suporte FIXME no backend") — flagá-las disparava o gate
# em prosa honesta. Confiamos no placeholder-scan (``{{...}}``) +
# substance-coverage (DAG/totais) pra pegar incompletude REAL.

# Severity mínimo HIGH — alinhado à calibração do auditor: detection
# findings (gate enforcement) recebem severity mínimo HIGH, o reviewer não
# improvisa "é cosmético".
_DEFAULT_SEVERITY = "high"

_BREAKDOWN_NAME = "task-breakdown.yaml"


@dataclass(frozen=True)
class ContentFinding:
    """Um achado determinístico de conteúdo incompleto numa wave.

    - ``category`` ── ``placeholder`` (L2) | ``substance`` (C2/M2) | ``missing``.
    - ``severity`` ── default ``high`` (detection finding, calibração do auditor).
    """

    artefact: Path
    category: str
    detail: str
    severity: str = _DEFAULT_SEVERITY


def _strip_trailing_comment(line: str) -> str:
    """Remove o comentário trailing (``#`` até EOL) FORA de aspas.

    Respeita aspas simples/duplas pra não cortar um ``#`` legítimo dentro de
    string (ex.: ``color: "#fff"``). Linhas YAML/MD usam ``#`` como início de
    comentário; tudo após o primeiro ``#`` não-citado é ilustração.
    """
    in_single = in_double = False
    for idx, ch in enumerate(line):
        if ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "'" and not in_double:
            in_single = not in_single
        elif ch == "#" and not in_single and not in_double:
            return line[:idx]
    return line


def scan_placeholders(text: str) -> list[str]:
    """Devolve a lista de stubs residuais (``{{...}}`` não preenchidos).

    Tradução determinística de **L2** (placeholder-scan). Por linha:

    1. Linha PURAMENTE comentada (``^\\s*#``) → ignorada (ilustração).
    2. Demais linhas → remove o comentário TRAILING (H-001) e escaneia só a
       parte NÃO-comentada. Assim ``backend: "{{x}}"  # ex.:`` é pego (stub
       substantivo) e ``allowed: []  # ex.: ["{{slug}}"]`` é ignorado (token
       só na ilustração).

    M-01: NÃO escaneia TODO/TBD/FIXME — são palavras ambíguas em prosa livre
    (ver ``_PLACEHOLDER_RE``/comentário acima). Só ``{{...}}``, que é
    inequivocamente token de template residual.
    """
    hits: list[str] = []
    for raw in text.splitlines():
        stripped = raw.lstrip()
        if stripped.startswith("#"):
            continue  # linha puramente comentada — ilustração legítima
        code = _strip_trailing_comment(raw)
        for match in _PLACEHOLDER_RE.findall(code):
            hits.append(match)
    return hits


def _scan_file_placeholders(path: Path) -> list[ContentFinding]:
    """Placeholder-scan de um arquivo texto. Ausente → finding ``missing``."""
    if not path.exists():
        return [
            ContentFinding(
                artefact=path,
                category="missing",
                detail=f"artefato esperado não existe no disco: {path.name}",
            )
        ]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:  # degrade-soft: não crasha o gate
        return [
            ContentFinding(
                artefact=path,
                category="missing",
                detail=f"não foi possível ler {path.name}: {exc}",
            )
        ]
    hits = scan_placeholders(text)
    if not hits:
        return []
    # Dedup preservando ordem, pra a mensagem não repetir o mesmo token.
    seen: set[str] = set()
    unique: list[str] = []
    for hit in hits:
        if hit not in seen:
            seen.add(hit)
            unique.append(hit)
    sample = ", ".join(unique[:5])
    more = "" if len(unique) <= 5 else f" (+{len(unique) - 5})"
    return [
        ContentFinding(
            artefact=path,
            category="placeholder",
            detail=f"{len(unique)} stub(s) residual(is) em {path.name}: {sample}{more}",
        )
    ]


def check_task_breakdown(path: Path) -> list[ContentFinding]:
    """Substance-check do task-breakdown.yaml (forma de **C2/M2**).

    Dispara um finding ``substance`` quando ``tasks`` tem ≥2 entradas reais
    MAS o grafo de dependência está no default vazio
    (``dependency_graph.edges == []`` E ``critical_path == []``), ou quando
    ``totals.tasks_count == 0`` com ``tasks`` não-vazio. Single-task features
    (``len(tasks) <= 1``) NÃO disparam — DAG vazio é legítimo.

    Degrade-soft (M-002): arquivo ausente → finding ``missing``; YAML
    PRESENTE mas MALFORMADO → finding ``substance`` amigável (NÃO crasha; o
    wiring trata como incompleto-pausa).
    """
    if not path.exists():
        return [
            ContentFinding(
                artefact=path,
                category="missing",
                detail=f"task-breakdown esperado não existe: {path.name}",
            )
        ]
    try:
        data = read_yaml(path)
    except YamlIOError:
        # M-002: malformado degrada-soft — trata como incompleto, não crasha.
        return [
            ContentFinding(
                artefact=path,
                category="substance",
                detail=(
                    f"{path.name} está presente mas malformado (YAML não parseável) "
                    "— preencha/corrija o conteúdo antes de avançar a wave"
                ),
            )
        ]
    if not isinstance(data, dict):
        return [
            ContentFinding(
                artefact=path,
                category="substance",
                detail=f"{path.name} não é um mapa YAML válido (esperado dict no topo)",
            )
        ]

    tasks = data.get("tasks") or []
    if not isinstance(tasks, list):
        tasks = []
    findings: list[ContentFinding] = []

    if len(tasks) >= 2:
        dep_graph = data.get("dependency_graph") or {}
        if not isinstance(dep_graph, dict):
            dep_graph = {}
        edges = dep_graph.get("edges") or []
        # ``critical_path`` pode viver no topo (template) ou sob dependency_graph.
        critical_path = data.get("critical_path")
        if critical_path is None:
            critical_path = dep_graph.get("critical_path")
        critical_path = critical_path or []
        if not edges and not critical_path:
            findings.append(
                ContentFinding(
                    artefact=path,
                    category="substance",
                    detail=(
                        f"DAG vazio com {len(tasks)} tasks — dependency_graph.edges "
                        "e critical_path estão no default vazio; preencha as "
                        "dependências entre as tasks"
                    ),
                )
            )

        totals = data.get("totals") or {}
        if isinstance(totals, dict):
            tasks_count = totals.get("tasks_count")
            if tasks_count == 0:
                findings.append(
                    ContentFinding(
                        artefact=path,
                        category="substance",
                        detail=(
                            f"totals.tasks_count=0 enquanto tasks tem {len(tasks)} "
                            "entradas — atualize os totais"
                        ),
                    )
                )

    return findings


def check_artefacts(wave_label: str, artefacts: list[Path]) -> list[ContentFinding]:
    """Despacha o content-check por artefato (extensão/nome).

    - ``.md`` → placeholder-scan (L2), EXCETO na Wave A (intake free-text).
    - ``task-breakdown.yaml`` (por nome) → ``check_task_breakdown`` (C2/M2) +
      placeholder-scan, EXCETO na Wave A (intake), que é exenta do
      substance-check de DAG.
    - demais ``.yaml``/``.json`` → placeholder-scan só.

    H-01 (gate-histérico) — a Wave A renderiza o ``feature-intake.md``, cujo
    ``source-ref`` carrega o **argv CRU do usuário** (texto livre, não
    sanitizado de placeholder). Um ``{{...}}`` LITERAL na frase do usuário
    (feature de templating/i18n/qualquer texto com chaves duplas) NÃO é stub
    residual de template — é conteúdo legítimo. Por isso o placeholder-scan de
    ``.md`` é ISENTADO na Wave A. Os dois escapes reais do piloto foram em
    tech-spec (Wave C) e task-breakdown (Wave D) — artefatos ESTRUTURADOS de
    engenharia, não o intake. Isentar só o ``.md`` da Wave A fecha o
    false-positive sem perder cobertura dos escapes reais.

    Determinístico, puro, sem prompt nem subprocess.
    """
    findings: list[ContentFinding] = []
    wave_a = wave_label.strip().upper() == "A"

    for artefact in artefacts:
        name = artefact.name
        suffix = artefact.suffix.lower()

        if name == _BREAKDOWN_NAME:
            if not wave_a:
                findings.extend(check_task_breakdown(artefact))
                # placeholder-scan do breakdown só fora da Wave A (estruturado).
                if artefact.exists():
                    findings.extend(_scan_file_placeholders(artefact))
            # Na Wave A o breakdown é intake-adjacente / pode nem existir —
            # isento do scan (mesma política de free-text do intake).
            continue

        if suffix == ".md":
            # H-01: intake free-text da Wave A é isento do placeholder-scan.
            if wave_a:
                continue
            findings.extend(_scan_file_placeholders(artefact))
        elif suffix in (".yaml", ".yml", ".json"):
            findings.extend(_scan_file_placeholders(artefact))

    return findings
