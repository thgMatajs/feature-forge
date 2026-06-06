"""`forge doctor` — health check across every moving piece.

Read-only inspection cascade per `docs/ux/forge-doctor-roteiro.md`. Categories
match the doctor roteiro §Cena 3 (config / cards / inventory / memory L2 /
memory L1 / graph / hooks / MCPs / i18n / bak overdue / forge version lock).

Mutation exception (legitimate): at the end of every run, doctor stamps
`doctor.last-run` + `doctor.last-status` on `workflow-config.yaml` (aligned
with the path consumed by `forge status`). This is the only write doctor
performs — it never mutates cards, inventory, memory, or the graph.

Severity follows discipline §2 — hard fails stop nothing here (each category
runs independently), but they DO control the return code:

    return 0  →  everything green (default — warnings do not fail CI)
    return 0  →  warnings only (POSIX-friendly default)
    return 1  →  at least one hard fail
    return 1  →  warnings only when `FORGE_DOCTOR_STRICT=1`

Strict mode (env `FORGE_DOCTOR_STRICT=1`) escalates warn-only runs to
exit 1 — opt-in para times que querem treat warn como red em CI.

`quick` mode runs only the critical block (config + cards + L2 size) and is
chosen conversationally at the prompt (decision 10: no flags).
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from engine.cards.snapshotter import compute_directory_sha256
from engine.memory.l1 import list_active_features, list_archived_features
from engine.memory.l2 import l2_size_bytes
from engine.ui import question, renderer
from engine.ui.question import PromptAbortedError
from engine.utils.paths import (
    ProjectRootNotFoundError,
    cards_dir,
    claude_dir,
    find_project_root,
    forge_home,
    graph_db_path,
    hooks_dir,
    inventory_dir,
    memory_dir,
    memory_l2_path,
    workflow_config_path,
)
from engine.utils.yaml_io import YamlIOError, bak_age_days, read_yaml, write_yaml

from engine import __version__ as FORGE_VERSION

_STATUS_OK = "ok"
_STATUS_WARN = "warn"
_STATUS_FAIL = "fail"
_STATUS_SKIP = "skip"

_GLYPH = {
    _STATUS_OK: "✓",
    _STATUS_WARN: "⚠",
    _STATUS_FAIL: "🛑",
    _STATUS_SKIP: "·",
}


@dataclass
class _Check:
    name: str
    status: str
    message: str = ""
    remediation: str = ""


@dataclass
class _CategoryReport:
    title: str
    checks: list[_Check]

    @property
    def worst(self) -> str:
        for s in (_STATUS_FAIL, _STATUS_WARN):
            if any(c.status == s for c in self.checks):
                return s
        return _STATUS_OK


# ── Public API ───────────────────────────────────────────────────────────────


def run(argv: list[str]) -> int:
    """Entry point. ``argv`` is ignored — scope is asked interactively."""
    try:
        project_root = find_project_root()
    except ProjectRootNotFoundError as exc:
        renderer.write(renderer.colored(str(exc), "red"))
        renderer.write("Próximo passo: forge init")
        return 1

    renderer.write("")
    renderer.write(renderer.bold("forge doctor — health check"))
    renderer.write(renderer.dim("Read-only. Nada vai ser modificado."))
    renderer.write("")

    try:
        scope = question.ask(
            "Qual scope?",
            {
                "full": "checa tudo (~8s)",
                "quick": "só o crítico — config + cards + L2 size (~2s)",
            },
            default="full",
        )
    except PromptAbortedError:
        return 130

    config_path = workflow_config_path(project_root)
    config = _safe_read_yaml(config_path) or {}

    categories: list[_CategoryReport] = [
        _check_config(project_root, config_path, config),
        _check_cards(project_root, config),
        _check_memory_l2(project_root, config),
    ]
    if scope == "full":
        categories.extend(
            [
                _check_inventory(project_root),
                _check_memory_l1(project_root),
                _check_graph(project_root),
                _check_reuse_findings(project_root),
                _check_hooks(project_root, config),
                _check_mcps(config),
                _check_i18n(project_root, config),
                _check_bak_overdue(project_root, config),
                _check_forge_version_lock(project_root),
                _check_cc_gate_tools(project_root),
            ]
        )

    for cat in categories:
        _render_category(cat)

    code, overall_status = _render_verdict(categories, scope=scope)

    # Mutation exception (read-only principle): doctor stamps its own run no
    # bloco canônico `doctor.last-run` (mesmo path lido por `forge status`).
    _stamp_last_doctor_run(
        project_root,
        config_path,
        config,
        categories,
        exit_code=code,
        overall_status=overall_status,
    )

    return code


def _stamp_last_doctor_run(
    project_root: Path,
    config_path: Path,
    config: dict,
    categories: list[_CategoryReport],
    *,
    exit_code: int,
    overall_status: str,
) -> None:
    """Persist `doctor.last-run` + `doctor.last-status` on the config.

    Path canônico alinhado com `engine/status.py` (lê `config.doctor.last-run`).
    Doctor é read-only por contrato exceto por este stamp — atualiza o dict
    em memória e grava atomicamente. Falha silenciosa quando o config está
    ausente ou inválido (nada seguro pra escrever).

    `overall_status` é o resultado do veredito (ok/warn/fail), não derivado
    do exit code — em strict mode, warn pode virar exit 1 sem que o status
    deixe de ser warn.

    Observabilidade best-effort apenas — invocações concorrentes (ex.: matrix
    de CI rodando `forge doctor` em jobs paralelos) competem nesta escrita e
    o último writer vence. Aceitável porque o stamp é informacional e o
    doctor em si é read-only contra o estado do projeto. Se auditoria
    precisa por execução virar load-bearing, trocar pra JSONL append log.
    """
    if not config_path.is_file() or not isinstance(config, dict):
        return
    doctor_block = config.get("doctor")
    if not isinstance(doctor_block, dict):
        doctor_block = {}
        config["doctor"] = doctor_block
    doctor_block["last-run"] = datetime.now(timezone.utc).isoformat()
    doctor_block["last-status"] = overall_status
    try:
        write_yaml(config_path, config, atomic=True)
    except Exception:  # pragma: no cover - defensive
        # Doctor must never crash the user's session because of a stamp write.
        pass


# ── Category checks ──────────────────────────────────────────────────────────


def _check_config(project_root: Path, config_path: Path, config: dict) -> _CategoryReport:
    checks: list[_Check] = []
    if not config_path.is_file():
        checks.append(
            _Check(
                "workflow-config.yaml",
                _STATUS_FAIL,
                "not found",
                "rode `forge init`",
            )
        )
        return _CategoryReport("Config integrity", checks)

    if not isinstance(config, dict):
        checks.append(_Check("yaml-parse", _STATUS_FAIL, "not a mapping"))
        return _CategoryReport("Config integrity", checks)

    checks.append(_Check("workflow-config.yaml", _STATUS_OK, "parses cleanly"))
    schema_version = config.get("schema-version")
    if schema_version == 1:
        checks.append(_Check("schema-version", _STATUS_OK, "= 1"))
    else:
        checks.append(
            _Check(
                "schema-version",
                _STATUS_FAIL,
                f"= {schema_version!r} (forge supports 1)",
                "atualize o forge ou regenere o config",
            )
        )

    identity = config.get("identity") or {}
    project_slug = identity.get("project-slug")
    if isinstance(project_slug, str) and project_slug:
        checks.append(_Check("project-slug", _STATUS_OK, project_slug))
    else:
        checks.append(_Check("project-slug", _STATUS_WARN, "missing"))

    preset = identity.get("preset")
    checks.append(
        _Check("preset", _STATUS_OK if preset else _STATUS_WARN, str(preset or "(unset)"))
    )

    return _CategoryReport("Config integrity", checks)


def _check_cards(project_root: Path, config: dict) -> _CategoryReport:
    checks: list[_Check] = []
    cards_block = (config.get("cards") or {}) if isinstance(config, dict) else {}
    active = cards_block.get("active") or []
    cards_root = cards_dir(project_root)

    if not active:
        checks.append(
            _Check(
                "active cards",
                _STATUS_WARN,
                "nenhum card ativo",
                "rode `forge reconfigure` pra adicionar",
            )
        )
        return _CategoryReport("Cards integrity", checks)

    for entry in active:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "")
        if not name:
            continue
        snapshot = cards_root / name
        expected = str(entry.get("sha256") or "")
        if not snapshot.is_dir():
            checks.append(
                _Check(
                    name,
                    _STATUS_FAIL,
                    "snapshot ausente",
                    "rode `forge reconfigure`",
                )
            )
            continue
        if not expected:
            checks.append(
                _Check(name, _STATUS_WARN, "sha256 não registrado no config")
            )
            continue
        try:
            actual = compute_directory_sha256(snapshot)
        except Exception as exc:  # pragma: no cover - defensive
            checks.append(_Check(name, _STATUS_FAIL, f"hash error: {exc}"))
            continue
        if actual == expected:
            checks.append(_Check(name, _STATUS_OK, "sha256 ok"))
        else:
            checks.append(
                _Check(
                    name,
                    _STATUS_FAIL,
                    "sha256 mismatch (edição local ou upgrade parcial)",
                    "forge reconfigure → menu cards",
                )
            )
    return _CategoryReport(f"Cards integrity · {len(active)} active", checks)


def _check_inventory(project_root: Path) -> _CategoryReport:
    checks: list[_Check] = []
    root = inventory_dir(project_root)
    for name in ("design-system.yaml", "i18n.yaml", "conventions.yaml"):
        path = root / name
        if not path.is_file():
            checks.append(
                _Check(name, _STATUS_WARN, "ausente — rode forge reconfigure")
            )
            continue
        try:
            data = read_yaml(path)
        except YamlIOError as exc:
            checks.append(_Check(name, _STATUS_FAIL, f"parse error: {exc}"))
            continue
        if not isinstance(data, dict):
            checks.append(_Check(name, _STATUS_FAIL, "top-level não é mapping"))
            continue
        checks.append(_Check(name, _STATUS_OK, "parseable"))
    return _CategoryReport("Inventory freshness", checks)


def _check_memory_l2(project_root: Path, config: dict) -> _CategoryReport:
    checks: list[_Check] = []
    path = memory_l2_path(project_root)
    if not path.exists():
        checks.append(
            _Check("L2-project.yaml", _STATUS_WARN, "ainda não existe (ok pra projetos novos)")
        )
        return _CategoryReport("Memory L2", checks)
    try:
        data = read_yaml(path)
        if not isinstance(data, dict):
            raise YamlIOError("not a mapping")
    except YamlIOError as exc:
        checks.append(_Check("L2-project.yaml", _STATUS_FAIL, f"parse error: {exc}"))
        return _CategoryReport("Memory L2", checks)
    checks.append(_Check("L2-project.yaml", _STATUS_OK, "parseable"))

    size_bytes = l2_size_bytes(project_root)
    max_mb = _config_get_path(config, ["memory", "l2", "max-size-mb"], None)
    if max_mb is None:
        max_mb = _config_get_path(config, ["memory", "L2-project", "max-size-mb"], 0.5)
    try:
        max_bytes = float(max_mb) * 1024 * 1024
    except (TypeError, ValueError):
        max_bytes = 0.5 * 1024 * 1024
    pct = (size_bytes / max_bytes * 100) if max_bytes else 0
    size_kb = size_bytes / 1024
    status = _STATUS_OK if size_bytes <= max_bytes else _STATUS_WARN
    checks.append(
        _Check(
            "L2 size",
            status,
            f"{size_kb:.1f} KB / {max_mb} MB ({pct:.0f}%)",
            "memory-distiller roda automático no próximo verify",
        )
    )
    return _CategoryReport("Memory L2", checks)


def _check_memory_l1(project_root: Path) -> _CategoryReport:
    checks: list[_Check] = []
    l1_root = memory_dir(project_root) / "L1"
    if not l1_root.exists():
        checks.append(_Check("L1 root", _STATUS_OK, "ainda não criado"))
        return _CategoryReport("Memory L1", checks)
    active = list_active_features(project_root)
    archived = list_archived_features(project_root)
    checks.append(_Check("L1 active features", _STATUS_OK, f"{len(active)}"))
    checks.append(_Check("L1 archived", _STATUS_OK, f"{len(archived)}"))
    return _CategoryReport("Memory L1", checks)


def _check_graph(project_root: Path) -> _CategoryReport:
    checks: list[_Check] = []
    path = graph_db_path(project_root)
    if not path.exists():
        checks.append(
            _Check(
                "graph.db",
                _STATUS_WARN,
                "ainda não construído",
                "rode `forge reconfigure` → rebuild graph",
            )
        )
        return _CategoryReport("Graph health", checks)
    checks.append(_Check("graph.db", _STATUS_OK, "presente"))
    try:
        conn = sqlite3.connect(str(path))
        row = conn.execute("PRAGMA journal_mode").fetchone()
        conn.close()
        mode = (row[0] if row else "").lower()
        if mode == "wal":
            checks.append(_Check("journal_mode", _STATUS_OK, "WAL"))
        else:
            checks.append(
                _Check(
                    "journal_mode",
                    _STATUS_WARN,
                    f"= {mode!r}",
                    "espera-se WAL — forge reconfigure resolve",
                )
            )
    except sqlite3.Error as exc:
        checks.append(_Check("sqlite open", _STATUS_FAIL, str(exc)))
    return _CategoryReport("Graph health", checks)


def _check_reuse_findings(project_root: Path) -> _CategoryReport:
    """Surface reuse-intelligence findings queued for `forge evolve`.

    Aggregated by proposal kind. WARN when anything pending, OK otherwise.
    Graph-missing → SKIP (the graph check already covered that).
    """
    checks: list[_Check] = []
    path = graph_db_path(project_root)
    if not path.exists():
        checks.append(
            _Check(
                "reuse findings",
                _STATUS_SKIP,
                "graph não construído",
            )
        )
        return _CategoryReport("Reuse intelligence", checks)
    # R3.6 fix: use closing() so the connection is unconditionally
    # closed on every exit path — including non-sqlite3 exceptions
    # (MemoryError, KeyboardInterrupt, etc.) that the outer except
    # wouldn't intercept. The previous try/finally was correct for the
    # happy path but `closing()` is the idiomatic, defensive shape.
    from contextlib import closing

    try:
        with closing(sqlite3.connect(str(path))) as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(reuse_findings)").fetchall()}
            if not cols:
                checks.append(
                    _Check(
                        "reuse_findings",
                        _STATUS_SKIP,
                        "tabela ausente — schema antigo",
                        "rode `forge reconfigure` → rebuild graph",
                    )
                )
                return _CategoryReport("Reuse intelligence", checks)
            rows = conn.execute(
                "SELECT category, COUNT(*) AS n FROM reuse_findings GROUP BY category"
            ).fetchall()
    except sqlite3.Error as exc:
        checks.append(_Check("sqlite open", _STATUS_FAIL, str(exc)))
        return _CategoryReport("Reuse intelligence", checks)

    by_category: dict[str, int] = {row[0]: row[1] for row in rows if row[0]}
    total = sum(by_category.values())
    if total == 0:
        checks.append(_Check("findings", _STATUS_OK, "nenhuma duplicação pendente"))
        return _CategoryReport("Reuse intelligence", checks)
    summary = ", ".join(f"{cat}={n}" for cat, n in sorted(by_category.items()))
    checks.append(
        _Check(
            "findings",
            _STATUS_WARN,
            f"{total} pendente(s): {summary}",
            "rode `forge evolve` para revisar",
        )
    )
    return _CategoryReport("Reuse intelligence", checks)


def _check_hooks(project_root: Path, config: dict) -> _CategoryReport:
    checks: list[_Check] = []
    root = hooks_dir(project_root)
    if not root.exists():
        checks.append(
            _Check("hooks dir", _STATUS_SKIP, "Phase 5+ — não esperamos isso ainda")
        )
        return _CategoryReport("Hooks", checks)

    declared = (config.get("hooks") or {}).get("active") or []
    if not declared:
        checks.append(_Check("declared hooks", _STATUS_SKIP, "nenhum no config"))
        return _CategoryReport("Hooks", checks)

    for hook in declared:
        if not isinstance(hook, dict):
            continue
        name = str(hook.get("name") or "")
        file_rel = str(hook.get("file") or "")
        if not file_rel:
            checks.append(_Check(name or "(unnamed)", _STATUS_WARN, "sem file:"))
            continue
        path = project_root / file_rel
        if not path.is_file():
            checks.append(_Check(name, _STATUS_FAIL, f"missing: {file_rel}"))
            continue
        if not os.access(path, os.X_OK):
            checks.append(
                _Check(
                    name,
                    _STATUS_WARN,
                    "not executable",
                    f"chmod +x {file_rel}",
                )
            )
            continue
        checks.append(_Check(name, _STATUS_OK, "executável"))
    return _CategoryReport("Hooks", checks)


def _check_mcps(config: dict) -> _CategoryReport:
    checks: list[_Check] = []
    ticketing = (config.get("ticketing") or {}) if isinstance(config, dict) else {}
    provider = ticketing.get("provider")
    if provider and provider != "none":
        checks.append(
            _Check(
                f"ticketing.{provider}",
                _STATUS_SKIP,
                "reachability probe NotImplemented em v1",
            )
        )
    else:
        checks.append(_Check("ticketing", _STATUS_OK, "provider=none"))
    docs = (config.get("external-docs") or {}) if isinstance(config, dict) else {}
    primary = docs.get("primary-provider") or "none"
    checks.append(
        _Check(
            f"external-docs.{primary}",
            _STATUS_SKIP,
            "reachability probe NotImplemented em v1",
        )
    )
    return _CategoryReport("MCPs", checks)


def _check_i18n(project_root: Path, config: dict) -> _CategoryReport:
    checks: list[_Check] = []
    i18n = ((config.get("conventions") or {}).get("i18n") or {}) if isinstance(config, dict) else {}
    src_rel = i18n.get("source-path")
    if not src_rel:
        checks.append(_Check("i18n source-of-truth", _STATUS_SKIP, "não declarado no config"))
        return _CategoryReport("i18n", checks)
    src_path = project_root / str(src_rel)
    if src_path.is_dir():
        checks.append(_Check("source-of-truth dir", _STATUS_OK, str(src_rel)))
    else:
        checks.append(
            _Check(
                "source-of-truth dir",
                _STATUS_FAIL,
                f"não existe: {src_rel}",
                "ajuste conventions.i18n.source-path",
            )
        )
    return _CategoryReport("i18n", checks)


def _check_bak_overdue(project_root: Path, config: dict) -> _CategoryReport:
    """Walk `.claude/` for `.bak` files older than the configured retention."""
    checks: list[_Check] = []
    retention_days = _config_get_path(config, ["cleanup", "bak-retention-days"], 7)
    try:
        retention_days = float(retention_days)
    except (TypeError, ValueError):
        retention_days = 7.0

    claude = claude_dir(project_root)
    if not claude.exists():
        checks.append(_Check("bak scan", _STATUS_SKIP, ".claude/ ausente"))
        return _CategoryReport("Backups (.bak)", checks)

    now = datetime.now(timezone.utc)
    overdue: list[tuple[Path, float]] = []
    for path in claude.rglob("*.bak"):
        if not path.is_file():
            continue
        try:
            age = bak_age_days(path, now=now)
        except OSError:
            continue
        if age > retention_days:
            overdue.append((path, age))

    if not overdue:
        checks.append(_Check("overdue baks", _STATUS_OK, f"0 (retention {retention_days}d)"))
    else:
        for path, age in overdue[:5]:
            rel = path.relative_to(project_root)
            checks.append(
                _Check(
                    str(rel),
                    _STATUS_WARN,
                    f"{age:.1f}d > {retention_days}d",
                    "forge reconfigure → limpar bak antigos",
                )
            )
        if len(overdue) > 5:
            checks.append(
                _Check(
                    "…",
                    _STATUS_WARN,
                    f"+{len(overdue) - 5} arquivos overdue não listados",
                )
            )
    return _CategoryReport("Backups (.bak)", checks)


def _check_forge_version_lock(project_root: Path) -> _CategoryReport:
    checks: list[_Check] = []
    lock_path = claude_dir(project_root) / "forge-version-lock.yaml"
    if not lock_path.exists():
        checks.append(
            _Check(
                "forge-version-lock.yaml",
                _STATUS_SKIP,
                "não criado ainda (gerenciado por forge init)",
            )
        )
        return _CategoryReport("Forge version lock", checks)
    try:
        data = read_yaml(lock_path)
    except YamlIOError as exc:
        checks.append(_Check("yaml parse", _STATUS_FAIL, str(exc)))
        return _CategoryReport("Forge version lock", checks)
    locked = (data or {}).get("forge-version") if isinstance(data, dict) else None
    if locked == FORGE_VERSION:
        checks.append(_Check("forge-version", _STATUS_OK, f"= {locked}"))
    else:
        checks.append(
            _Check(
                "forge-version",
                _STATUS_FAIL,
                f"lock={locked!r}, binary={FORGE_VERSION!r}",
                "atualize o forge ou regere o lock via reconfigure",
            )
        )
    return _CategoryReport("Forge version lock", checks)


def _check_cc_gate_tools(project_root: Path) -> _CategoryReport:
    """Report availability of the 4 native CC tools used by check_cyclomatic_complexity.

    Tools are NOT installed by forge (Decision 22 + spec §3 trust-but-verify).
    Doctor surfaces status + install hint per tool. Missing tool → WARN, never
    FAIL — dev workflows que não tocam toda linguagem não precisam de todas
    as ferramentas. Quem realmente precisa descobre via cc-gate em
    `forge verify`.

    Lookup é PATH-only (`shutil.which`). Versão da ferramenta NÃO é capturada
    aqui — chamadas a `<tool> --version` variam por binário e o objetivo desta
    categoria é availability, não compatibilidade. Versão entra em escopo só
    se algum bug específico ligar a determinada release.
    """
    del project_root  # not needed — tool lookup is PATH-only
    tools = [
        ("detekt", "brew install detekt    # or: sdk install detekt"),
        ("swiftlint", "brew install swiftlint"),
        ("eslint", "npm install -g eslint    # or per-project: npm i -D eslint"),
        ("radon", "pip install radon"),
    ]
    checks: list[_Check] = []
    for name, install_hint in tools:
        path = shutil.which(name)
        if path:
            checks.append(_Check(name, _STATUS_OK, f"found at {path}"))
        else:
            checks.append(
                _Check(
                    name,
                    _STATUS_WARN,
                    "não encontrado no PATH",
                    f"install: {install_hint}",
                )
            )
    return _CategoryReport("cc-gate-tools", checks)


# ── Rendering ────────────────────────────────────────────────────────────────


def _render_category(cat: _CategoryReport) -> None:
    renderer.write("")
    renderer.write(renderer.section_header(cat.title))
    for idx, check in enumerate(cat.checks):
        connector = "└" if idx == len(cat.checks) - 1 else "├"
        glyph = _GLYPH.get(check.status, "?")
        line = f"{connector} {check.name:<32} {glyph} {check.message}"
        renderer.write(line)
        if check.status in (_STATUS_WARN, _STATUS_FAIL) and check.remediation:
            renderer.write(renderer.dim(f"     ↳ {check.remediation}"))


def _render_verdict(
    categories: list[_CategoryReport], *, scope: str
) -> tuple[int, str]:
    """Render veredito e retorna (exit_code, status_canonico).

    POSIX-friendly: warn-only → exit 0 por padrão (não falha CI).
    Para escalar warn → exit 1, exporte `FORGE_DOCTOR_STRICT=1`.
    Hard fail sempre retorna exit 1.

    `status_canonico` ∈ {"ok", "warn", "fail"} — escrito em `doctor.last-status`.
    """
    passed = sum(1 for c in categories if c.worst == _STATUS_OK)
    warns = sum(1 for c in categories if c.worst == _STATUS_WARN)
    fails = sum(1 for c in categories if c.worst == _STATUS_FAIL)
    total = len(categories)

    strict = os.environ.get("FORGE_DOCTOR_STRICT", "").strip() in {"1", "true", "yes"}

    if fails:
        overall = "🔴 broken"
        status = "fail"
        code = 1
    elif warns:
        overall = "🟡 healthy with warnings"
        status = "warn"
        code = 1 if strict else 0
    else:
        overall = "🟢 healthy"
        status = "ok"
        code = 0

    body = [
        f"Overall:    {overall}",
        f"Categorias: {passed} ok · {warns} warn · {fails} fail · {total} total",
        f"Mode:       {scope}",
    ]
    if strict and warns and not fails:
        body.append("Strict:     FORGE_DOCTOR_STRICT=1 → warn escalou para exit 1")
    renderer.write("")
    renderer.write(renderer.box("doctor verdict", body))
    return code, status


# ── Helpers ──────────────────────────────────────────────────────────────────


def _safe_read_yaml(path: Path) -> Optional[dict]:
    if not path.is_file():
        return None
    try:
        data = read_yaml(path)
    except YamlIOError:
        return None
    return data if isinstance(data, dict) else None


def _config_get_path(config: dict, keys: list[str], default):
    cursor = config
    for key in keys:
        if not isinstance(cursor, dict):
            return default
        cursor = cursor.get(key)
        if cursor is None:
            return default
    return cursor


# Keep imports referenced (forge_home is reserved for future absolute-path
# remediation hints; do not drop the import).
_ = forge_home
_: Callable = _safe_read_yaml  # type: ignore[assignment]
