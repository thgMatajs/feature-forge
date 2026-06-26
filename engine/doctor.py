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

import json
import os
import shutil
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import yaml  # B-003 (master review PR #15): write_yaml pode levantar yaml.YAMLError

from engine.cards import CardError  # B-002 (master review PR #15)
from engine.cards.snapshotter import compute_directory_sha256
from engine.memory.l1 import list_active_features, list_archived_features
from engine.memory.l2 import l2_size_bytes
from engine.ui import output_mode, question, renderer
from engine.ui.question import PromptAbortedError
from engine.integrations.mem import mem_call
from engine.utils.paths import (
    ProjectRootNotFoundError,
    active_config_path,
    cards_dir,
    claude_dir,
    ensure_dir,
    find_project_root,
    forge_home,
    graph_db_path,
    hooks_dir,
    inventory_dir,
    lifecycle_root,
    memory_dir,
    memory_l2_path,
    mem_asset_version_path,
    vendored_mem_path,
)
from engine.utils.yaml_io import (
    YamlIOError,
    bak_age_days,
    read_yaml,
    read_yaml_or_default,
    write_yaml,
)
from engine.utils.checkpoint_io import (
    clear_checkpoint as _clear_checkpoint_io,
    load_yaml_checkpoint as _load_yaml_checkpoint_io,
    save_yaml_checkpoint as _save_yaml_checkpoint_io,
)
from engine.utils.iso import utc_now_iso as _utc_now_iso_shared

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


# ── Checkpoint (DRIFT-1 W2.T3b — intent-resume, outcome C) ───────────────────
#
# Per the T3a audit (.planning/drift-1/checkpoint-audit.json,
# action="add-new", reuse_path="init-pattern"), doctor needs a minimal
# checkpoint so the host can pause at the ``scope`` ask and re-invoke
# cleanly. Mirrors ``_InitCheckpoint`` at ``engine/init.py:100-108`` —
# per-subcommand dataclass, no import from ``engine.qa.checkpoint``
# (Decision 22 + outcome C lock-in).
#
# Doctor has a single interactive prompt today (``scope`` full/quick),
# but intent-resume is the protocol universal: persisting handler state
# before any ``question.ask*`` call lets the host write a matching
# response and re-invoke without re-asking. ``intent_id`` keys the
# correlation with ``forge-response.json``.
#
# Refs:
#   - docs/superpowers/specs/drift-1-intent-protocol.md §3, §5, §8
#   - engine/init.py:100-108 (canonical template)


@dataclass
class _DoctorCheckpoint:
    """State serialized before each ``question.ask*`` call in ``doctor.run``.

    Re-invocation after exit-2 reads this back, picks up where the prompt
    left off, and either consumes the matching ``forge-response.json``
    (when present) or re-emits pending and exits 2 again.
    """

    step: str
    at: str
    project_root: str
    intent_id: str | None = None


def _doctor_checkpoint_path(project_root: Path) -> Path:
    return claude_dir(project_root) / ".doctor-checkpoint.yaml"


# Os 4 helpers abaixo são thin shims sobre ``engine.utils.checkpoint_io`` +
# ``engine.utils.iso`` — consolidação dos 30 duplicates + 10 cópias de
# ``_utc_now_iso_*`` apontada pelos findings #5 e #21 do master review do
# PR #11. Os nomes ``_save_doctor_checkpoint`` / ``_load_doctor_checkpoint``
# / ``_clear_doctor_checkpoint`` / ``_utc_now_iso_doctor`` permanecem como
# API privada do módulo para preservar os contracts dos testes em
# ``tests/unit/test_engine_doctor_resume.py`` (Mandamento #2 — verde).


def _save_doctor_checkpoint(cp: _DoctorCheckpoint) -> None:
    """Persist the doctor checkpoint atomically."""
    _save_yaml_checkpoint_io(
        _doctor_checkpoint_path(Path(cp.project_root)),
        {
            "schema-version": 1,
            "step": cp.step,
            "at": cp.at,
            "project-root": cp.project_root,
            "intent-id": cp.intent_id,
        },
    )


def _load_doctor_checkpoint(project_root: Path) -> dict[str, Any] | None:
    """Read the doctor checkpoint, returning ``None`` when absent."""
    return _load_yaml_checkpoint_io(_doctor_checkpoint_path(project_root))


def _clear_doctor_checkpoint(project_root: Path) -> None:
    """Remove the checkpoint — best-effort; silent on OSError (idempotent)."""
    _clear_checkpoint_io(_doctor_checkpoint_path(project_root))


def _utc_now_iso_doctor() -> str:
    """ISO-8601 UTC timestamp — thin shim sobre ``engine.utils.iso``."""
    return _utc_now_iso_shared()


def _doctor_scope_intent_id() -> str:
    """Deterministic intent-id for the canonical scope ask.

    Pre-computed so the handler can record it on the checkpoint BEFORE
    calling ``question.ask`` — preserves the invariant in
    ``docs/superpowers/specs/drift-1-intent-protocol.md §3`` that the
    pending intent points at state already on disk.
    """
    options = {
        "full": "checa tudo (~8s)",
        "quick": "só o crítico — config + cards + L2 size (~2s)",
    }
    return question.stable_intent_id(
        "ask",
        "Qual scope?",
        options,
        extra={
            "default": "full",
            "min-selected": None,
            "validator-hint": None,
        },
    )


# ── Public API ───────────────────────────────────────────────────────────────


def _all_categories(
    project_root: Path, config_path: Path, config: dict, *, scope: str
) -> list[_CategoryReport]:
    """Assemble the category reports for a given scope.

    Single source of truth for which ``_check_*`` run per scope — reused by
    both the interactive path and the JSON-mode path so the two never drift.
    """
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
                _check_forge_home_driver(project_root),
                _check_mcps(config),
                _check_i18n(project_root, config),
                _check_bak_overdue(project_root, config),
                _check_forge_version_lock(project_root),
                _check_cc_gate_tools(project_root),
                _check_secrets_tools(project_root),
                _check_qa_coherence(project_root, config),
                _check_gradle_catalogs(project_root),
                _check_mem(project_root),
            ]
        )
    return categories


def run(argv: list[str]) -> int:
    """Entry point. ``argv`` is ignored — scope is asked interactively."""
    try:
        project_root = find_project_root()
    except ProjectRootNotFoundError as exc:
        if output_mode.is_json_mode():
            sys.stderr.write(f"forge doctor: {exc}\n")
            return 1
        renderer.write(renderer.colored(str(exc), "red"))
        renderer.write("Próximo passo: forge init")
        return 1

    # A1 — JSON mode is non-interactive by nature: the ``scope`` ask cannot
    # pause for a machine consumer, so we assume ``full`` (a machine wants the
    # complete diagnosis). The ``doctor.last-run`` stamp (the one legitimate
    # read-only mutation) stays identical to the interactive path. ``_render_*``
    # writes inside ``_render_verdict`` are suppressed by the renderer no-op in
    # JSON mode, so calling it only yields ``(code, overall_status)``.
    if output_mode.is_json_mode():
        config_path = active_config_path(project_root)
        config = _safe_read_yaml(config_path) or {}
        categories = _all_categories(project_root, config_path, config, scope="full")
        code, overall_status = _render_verdict(categories, scope="full")
        _stamp_last_doctor_run(
            project_root,
            config_path,
            config,
            categories,
            exit_code=code,
            overall_status=overall_status,
        )
        payload = {
            "scope": "full",
            "overall_status": overall_status,
            "exit_code": code,
            "categories": [
                {
                    "title": cat.title,
                    "worst": cat.worst,
                    "checks": [asdict(c) for c in cat.checks],
                }
                for cat in categories
            ],
        }
        print(json.dumps(payload, indent=2, default=str))
        return code

    renderer.write("")
    renderer.write(renderer.bold("forge doctor — health check"))
    renderer.write(renderer.dim("Read-only. Nada vai ser modificado."))
    renderer.write("")

    # DRIFT-1 W2.T3b — intent-resume: persist checkpoint with the deterministic
    # intent-id for the scope ask BEFORE invoking ``question.ask``. If the
    # engine pauses (no response on disk), the chokepoint raises
    # ``PausedForInputError`` and ``cli.main`` exits 2; on re-invocation
    # ``question.ask`` finds the matching ``forge-response.json`` and returns
    # the value without re-prompting. Outcome C — per-subcommand dataclass,
    # no import from ``engine.qa.checkpoint``.
    _save_doctor_checkpoint(
        _DoctorCheckpoint(
            step="step-scope-ask",
            at=_utc_now_iso_doctor(),
            project_root=str(project_root),
            intent_id=_doctor_scope_intent_id(),
        )
    )

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

    config_path = active_config_path(project_root)
    config = _safe_read_yaml(config_path) or {}

    categories = _all_categories(project_root, config_path, config, scope=scope)

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

    # DRIFT-1 W2.T3b — clear the intent-resume checkpoint on clean completion.
    # Invalid response branches (ValueError raised by ``question.ask``) leave
    # the checkpoint in place per SPEC §3 forensic preservation; only the
    # happy path apaga, espelhando o contract de ``_clear_state`` em
    # ``engine.ui.question``.
    _clear_doctor_checkpoint(project_root)

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
    except (yaml.YAMLError, OSError):  # pragma: no cover - defensive
        # B-003 (master review PR #15): `write_yaml` NÃO levanta `YamlIOError`
        # (só `read_yaml` levanta). O tipo real escapando aqui é
        # `yaml.YAMLError` (de `safe_dump` em dados não-serializáveis) ou
        # `OSError` (write). Doctor must never crash by stamp write.
        # noqa: BLE001 — narrowed: stamp write is best-effort, observability-only.
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
    # RULE-001 (docs/schemas/forge-config.md): schema-version must be in
    # [1, 1.3]. `forge init` writes "1.3" (string), older configs may carry 1
    # (int) — accept both numeric and string forms of the documented set. An
    # unknown version warns (doctor can't migrate it) but is NOT a hard fail:
    # a valid current config must pass, and a config doctor merely doesn't
    # recognize shouldn't read as red.
    if schema_version in {1, "1", 1.3, "1.3"}:
        checks.append(_Check("schema-version", _STATUS_OK, f"= {schema_version}"))
    else:
        checks.append(
            _Check(
                "schema-version",
                _STATUS_WARN,
                f"= {schema_version!r} (forge suporta [1, 1.3])",
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
        except (OSError, ValueError, CardError) as exc:  # pragma: no cover - defensive
            # noqa: BLE001 — broad catch: defensive at category-check boundary —
            # filesystem walk + sha256 can raise OSError (permissions, race);
            # ValueError covers malformed paths.
            # B-002 (master review PR #15): `compute_directory_sha256` levanta
            # `CardError` quando o snapshot vira não-dir entre o guard `is_dir()`
            # e a chamada (race). Sem incluir CardError, race condition
            # escalava e crashava o doctor inteiro — o oposto do isolamento
            # por categoria que o comentário defende.
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
    l1_root = lifecycle_root(project_root)
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


def _check_forge_home_driver(project_root: Path) -> _CategoryReport:
    """FORGE_HOME-carries-skills (W-DEBT, follow-up Wave 1 DRIVER-001).

    Espelha a categoria de Hooks: assere a presença de um arquivo esperado no
    FORGE_HOME. Aqui o arquivo é o driver do host —
    ``skills/feature-forge/SKILL.md`` — que o Claude Code / opencode lê pra
    dirigir o lifecycle do forge. Um clone parcial/sparse de FORGE_HOME deixa o
    SKILL.md ausente e o driver fica dormente sem aviso; esta categoria pega
    isso cedo, no health-check.

    ``project_root`` não é usado (o driver vive no FORGE_HOME global, não no
    projeto) — recebido por uniformidade com as demais categorias.
    """
    checks: list[_Check] = []
    skill = forge_home() / "skills" / "feature-forge" / "SKILL.md"
    if skill.is_file():
        checks.append(
            _Check("driver SKILL.md", _STATUS_OK, f"presente em {skill}")
        )
    else:
        checks.append(
            _Check(
                "driver SKILL.md",
                _STATUS_FAIL,
                f"ausente: {skill}",
                "FORGE_HOME não carrega o driver do host — clone parcial/sparse "
                "deixa skills/feature-forge/SKILL.md de fora. Refaça o clone "
                "completo do feature-forge no FORGE_HOME (sem sparse-checkout).",
            )
        )
    return _CategoryReport("FORGE_HOME driver", checks)


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


def _check_secrets_tools(project_root: Path) -> _CategoryReport:
    """Reporta availability das 2 tools nativas usadas por check_secrets.

    Tools NÃO são instaladas pelo forge (Decision 22 + spec §3
    trust-but-verify). Doctor surfaca status + install hint por tool.
    Missing tool → WARN, nunca FAIL — workflows que não rodam o
    secrets-gate (ex.: dev local sem ``forge implement``) não precisam
    dessas ferramentas. Quem efetivamente precisa descobre via gate em
    ``forge verify`` / ``forge implement`` (warn surface).

    Lookup é PATH-only (``shutil.which``). Versão da ferramenta NÃO é
    capturada aqui — esta categoria é availability, não compatibilidade.
    Versão entra em escopo apenas se algum bug ligar a release específica.

    Stage mapping (per spec §2):
      - gitleaks  → per-task hook (``forge implement``, stage="per_task")
      - trufflehog → cascade (``forge verify``, stage="cascade",
                     ``--only-verified``)
    """
    del project_root  # not needed — tool lookup is PATH-only
    tools = [
        (
            "gitleaks",
            "brew install gitleaks    # or: go install github.com/gitleaks/gitleaks/v8@latest",
        ),
        ("trufflehog", "brew install trufflehog"),
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
    return _CategoryReport("secrets-tools", checks)


def _check_qa_coherence(project_root: Path, config: dict) -> _CategoryReport:
    """13ª categoria (Wave 7 / spec §16) — coerência da config qa.

    4 checks (warning/info only — nunca FAIL):
        1. qa.enabled=false + auto-run=true → config inconsistente
        2. qa.enabled=true mas `.planning/qa/` sem write perm → warning
        3. Runs em `.planning/qa/<slug>/<run-id>/` com timestamp >
           retention-days dias → warning com lista (top 5) de paths
        4. Cards declaram qa-extensions referenciando auditor em
           extensions.disabled → info ("declarado mas desativado")

    Read-only. Nada bloqueia commit/verify — verdict é informativo.
    """
    checks: list[_Check] = []
    qa_cfg = (config.get("qa") or {}) if isinstance(config, dict) else {}
    if not isinstance(qa_cfg, dict):
        checks.append(
            _Check(
                "qa block",
                _STATUS_WARN,
                f"not a mapping (got {type(qa_cfg).__name__})",
                "rode `forge reconfigure` → menu qa",
            )
        )
        return _CategoryReport("QA coherence", checks)

    if not qa_cfg:
        # Ausente é OK — significa instalação pré-Wave 7 que ainda não
        # rodou `forge reconfigure -> qa`. Defaults conservadores
        # (enabled=true implícito; auto-run=false) já garantem
        # comportamento sensato.
        checks.append(
            _Check(
                "qa block",
                _STATUS_SKIP,
                "ausente (defaults: enabled=true, auto-run=false)",
            )
        )
        return _CategoryReport("QA coherence", checks)

    # Check 1 — config inconsistência
    enabled = bool(qa_cfg.get("enabled", True))
    auto_run = bool(qa_cfg.get("auto-run-on-feature-done", False))
    if not enabled and auto_run:
        checks.append(
            _Check(
                "enabled vs auto-run",
                _STATUS_WARN,
                "qa.enabled=false + auto-run=true (auto-run nunca dispara)",
                "rode `forge reconfigure` → menu qa → opção 1 ou 2",
            )
        )
    else:
        checks.append(
            _Check(
                "enabled vs auto-run",
                _STATUS_OK,
                f"enabled={enabled}, auto-run={auto_run}",
            )
        )

    # Check 2 — `.planning/qa/` write permission (só quando enabled).
    qa_root = project_root / ".planning" / "qa"
    if enabled:
        if not qa_root.exists():
            checks.append(
                _Check(
                    ".planning/qa/",
                    _STATUS_OK,
                    "ainda não criado (será criado na primeira run)",
                )
            )
        elif not os.access(qa_root, os.W_OK):
            checks.append(
                _Check(
                    ".planning/qa/",
                    _STATUS_WARN,
                    "sem permissão de escrita",
                    "chmod +w .planning/qa/ (ou ajuste owner)",
                )
            )
        else:
            checks.append(
                _Check(
                    ".planning/qa/", _STATUS_OK, "writable"
                )
            )
    else:
        checks.append(
            _Check(".planning/qa/", _STATUS_SKIP, "qa desabilitado")
        )

    # Check 3 — runs em retention overdue
    retention_days = qa_cfg.get("retention-days", 14)
    try:
        retention_days = float(retention_days)
    except (TypeError, ValueError):
        retention_days = 14.0

    overdue_paths: list[tuple[Path, float]] = []
    if enabled and qa_root.is_dir():
        now = datetime.now(timezone.utc).timestamp()
        for slug_dir in qa_root.iterdir():
            if not slug_dir.is_dir() or slug_dir.name.startswith("."):
                continue
            for run_dir in slug_dir.iterdir():
                if not run_dir.is_dir():
                    continue
                try:
                    mtime = run_dir.stat().st_mtime
                except OSError:
                    continue
                age_days = (now - mtime) / 86400.0
                if age_days > retention_days:
                    overdue_paths.append((run_dir, age_days))

    if not overdue_paths:
        checks.append(
            _Check(
                "runs retention",
                _STATUS_OK,
                f"0 overdue (retention {retention_days}d)",
            )
        )
    else:
        for path, age in overdue_paths[:5]:
            try:
                rel = path.relative_to(project_root)
            except ValueError:
                rel = path
            checks.append(
                _Check(
                    str(rel),
                    _STATUS_WARN,
                    f"{age:.1f}d > {retention_days}d",
                    "rode `forge reconfigure` → menu qa → opção 5 ou remova manualmente",
                )
            )
        if len(overdue_paths) > 5:
            checks.append(
                _Check(
                    "…",
                    _STATUS_WARN,
                    f"+{len(overdue_paths) - 5} runs overdue não listadas",
                )
            )

    # Check 4 — cards declaram qa-extensions referenciando auditor em
    # extensions.disabled. Severity info — não é erro, é audit visibility.
    extensions = qa_cfg.get("extensions") or {}
    disabled_auditors: set[str] = set()
    if isinstance(extensions, dict):
        raw_disabled = extensions.get("disabled") or []
        if isinstance(raw_disabled, list):
            disabled_auditors = {str(n) for n in raw_disabled if isinstance(n, str)}

    if disabled_auditors:
        declared_disabled = _scan_disabled_auditors_in_cards(
            project_root, disabled_auditors
        )
        if declared_disabled:
            for auditor_name, card_names in sorted(declared_disabled.items()):
                checks.append(
                    _Check(
                        auditor_name,
                        _STATUS_SKIP,  # info — usamos SKIP glyph "·"
                        f"declarado em {', '.join(card_names)} mas desativado",
                    )
                )
        else:
            checks.append(
                _Check(
                    "extensions.disabled",
                    _STATUS_OK,
                    f"{len(disabled_auditors)} auditor(es) desativado(s); "
                    "nenhum card declara",
                )
            )
    else:
        checks.append(
            _Check("extensions.disabled", _STATUS_OK, "vazio")
        )

    return _CategoryReport("QA coherence", checks)


def _scan_disabled_auditors_in_cards(
    project_root: Path, disabled: set[str]
) -> dict[str, list[str]]:
    """Walk cards (canon snapshot + local) procurando qa-extensions.auditors[].

    Retorna mapping `{auditor_name: [card_names]}` quando o auditor declarado
    no card está em `extensions.disabled` da workflow-config. Best-effort —
    falhas de parse silenciam (read-only audit, não bloqueia doctor).
    """
    found: dict[str, list[str]] = {}
    if not disabled:
        return found

    cards_root = cards_dir(project_root)
    local_root = cards_root / "local"
    candidates: list[Path] = []
    if cards_root.is_dir():
        for d in cards_root.iterdir():
            if d.is_dir() and not d.name.startswith(".") and d.name != "local":
                if (d / "card.yaml").is_file():
                    candidates.append(d)
    if local_root.is_dir():
        for d in local_root.iterdir():
            if d.is_dir() and not d.name.startswith("."):
                if (d / "card.yaml").is_file():
                    candidates.append(d)

    for card_dir in candidates:
        try:
            data = read_yaml(card_dir / "card.yaml")
        except (YamlIOError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        qa_ext = data.get("qa-extensions")
        if not isinstance(qa_ext, dict):
            continue
        auditors = qa_ext.get("auditors") or []
        if not isinstance(auditors, list):
            continue
        identity = data.get("identity") or {}
        card_name = (
            str(identity.get("name") or card_dir.name)
            if isinstance(identity, dict)
            else card_dir.name
        )
        for aud in auditors:
            if not isinstance(aud, dict):
                continue
            aud_name = aud.get("name")
            if not isinstance(aud_name, str):
                continue
            if aud_name in disabled:
                found.setdefault(aud_name, []).append(card_name)
    return found


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


def _check_mem(project_root: Path) -> _CategoryReport:
    """Categoria 'mem': vendorização + saúde (mem doctor) + drift do pin.

    Reusa a fronteira mem_call — nunca replica lógica do mem em Python.

    H-001: `mem doctor` (cmd_doctor) retorna exit 0 SEMPRE — exit_code não é
    sinal de saúde. A saúde é derivada do PIOR check do JSON `--json`, não do
    exit code. Trata 3 modos de falha sem crash: binário não encontrado, JSON
    inválido, lista vazia.
    """
    vendored = vendored_mem_path(project_root)
    if not vendored.is_file():
        return _CategoryReport("mem", [_Check(
            name="vendored",
            status=_STATUS_FAIL,
            message="mem não vendorizado em .claude/bin/mem",
            remediation="rode `forge init` pra vendorizar o mem",
        )])

    checks: list[_Check] = [_Check("vendored", _STATUS_OK, "mem vendorizado em .claude/bin/mem")]

    # H-001: `mem doctor` retorna exit 0 SEMPRE — derivar saúde do JSON, não do exit_code.
    res = mem_call(project_root, ["doctor"])  # json=True por default
    if not res.found:
        checks.append(_Check("health", _STATUS_WARN, "mem doctor não executou"))
    else:
        try:
            report = json.loads(res.stdout or "[]")
            # mem doctor --json → lista de {"check","status","detail"};
            # status do mem ∈ {"ok", e não-ok (ex.: "fail"/"error"/"stale")}.
            bad = [c for c in report if isinstance(c, dict) and c.get("status") != "ok"]
            if bad:
                names = ", ".join(str(c.get("check")) for c in bad)
                checks.append(_Check(
                    "health",
                    _STATUS_WARN,
                    f"mem doctor reportou checks não-ok: {names}",
                ))
            else:
                checks.append(_Check("health", _STATUS_OK, "mem doctor: todos os checks ok"))
        except (ValueError, TypeError):
            checks.append(_Check(
                "health",
                _STATUS_WARN,
                f"mem doctor saída ininteligível: {(res.stderr or res.stdout or '')[:120]}",
            ))

    # Drift do pin: VERSION vendorizada vs asset embutido neste forge.
    pin = vendored.parent / "mem.version"
    asset_v = mem_asset_version_path()
    if pin.is_file() and asset_v.is_file():
        vp = pin.read_text().strip()
        va = asset_v.read_text().strip()
        if vp != va:
            # M-001: `forge reconfigure` NÃO re-vendoriza nesta onda;
            # `forge init` é idempotente e re-vendoriza. Remediation honesta.
            checks.append(_Check(
                "pin",
                _STATUS_WARN,
                f"drift: vendorizado {vp} vs asset {va}",
                remediation="rode `forge init` pra re-vendorizar o asset mais novo",
            ))
        else:
            checks.append(_Check("pin", _STATUS_OK, f"pin alinhado ({vp})"))

    return _CategoryReport("mem", checks)


# ── Gradle catalog scope (DET-3 M-4) ─────────────────────────────────────────


# Diretórios que nunca devem disparar o warning de catálogo fora do path
# canônico. Mantém a lista pragmática — fixtures de teste, build outputs,
# caches de package managers e VCS interno. Em projetos KMP grandes, evita
# ruído de catálogos transientes ou de terceiros (ex.: dependency clones).
_GRADLE_CATALOG_EXCLUDED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".gradle",
        ".idea",
        "build",
        "node_modules",
        "tests",  # cobre tests/fixtures/** sem precisar matchar profundidade
        ".venv",
        "venv",
        "__pycache__",
    }
)


def _check_gradle_catalogs(project_root: Path) -> _CategoryReport:
    """Warn quando `libs.versions.toml` existe fora de `<project>/gradle/`.

    DET-3 v1 (spec det-3-gradle-dep-signal §Non-Goals) só inspeciona
    catálogos no path canônico `<project>/gradle/*.versions.toml`. Composite
    builds (`subprojects/*/gradle/`) ou catálogos em `buildSrc/` ficam fora
    de escopo deliberadamente — mas o usuário verá `(cards matched: 0/N)`
    sem indicação do porquê. Esta categoria surfaca esses catálogos como
    warning não-bloqueante pra ajudar diagnóstico no campo.

    Read-only. Caminhada limitada por `_GRADLE_CATALOG_EXCLUDED_DIRS` pra
    evitar ruído de fixtures, builds e caches.
    """
    checks: list[_Check] = []
    canonical_dir = (project_root / "gradle").resolve()
    out_of_scope: list[Path] = []

    # Walk manual em vez de rglob() pra cortar diretórios cedo — em monorepos
    # grandes, descer em node_modules/.gradle/build é caro e inútil.
    stack: list[Path] = [project_root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir() and not entry.is_symlink():
                if entry.name in _GRADLE_CATALOG_EXCLUDED_DIRS:
                    continue
                if entry.name.startswith("."):
                    # Pula dot-dirs em geral (`.claude/`, `.pytest_cache/`,
                    # etc.). Catálogos legítimos nunca vivem em dot-dirs.
                    continue
                stack.append(entry)
            elif entry.is_file() and entry.name == "libs.versions.toml":
                try:
                    parent_resolved = entry.parent.resolve()
                except OSError:
                    continue
                if parent_resolved != canonical_dir:
                    out_of_scope.append(entry)

    if not out_of_scope:
        checks.append(
            _Check(
                "libs.versions.toml scope",
                _STATUS_OK,
                "nenhum catálogo fora de gradle/",
            )
        )
        return _CategoryReport("Gradle catalog scope", checks)

    for path in out_of_scope[:5]:
        try:
            rel = path.relative_to(project_root)
        except ValueError:
            rel = path
        checks.append(
            _Check(
                str(rel),
                _STATUS_WARN,
                "fora de gradle/ — DET-3 v1 não inspeciona",
                "out-of-scope v1; ver docs/superpowers/specs/"
                "det-3-gradle-dep-signal.md §Non-Goals",
            )
        )
    if len(out_of_scope) > 5:
        checks.append(
            _Check(
                "…",
                _STATUS_WARN,
                f"+{len(out_of_scope) - 5} catálogo(s) fora de gradle/ não listado(s)",
            )
        )
    return _CategoryReport("Gradle catalog scope", checks)


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


# forge_home agora é consumido por _check_forge_home_driver (W-DEBT
# FORGE_HOME-carries-skills); o shim antigo `_ = forge_home` saiu.
_safe_read_yaml_ref: Callable = _safe_read_yaml  # noqa: F841 — keep reference
