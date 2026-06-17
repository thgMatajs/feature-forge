"""State-file I/O for the DRIFT-1 intent protocol.

Single chokepoint for ``.claude/forge/state/forge-pending.json`` and
``.claude/forge/state/forge-response.json``. Engine reads/writes go
through this module; ``question.py`` stays thin (sentinel + dispatch).
The host (Claude Code adapter) consumes the read-pending + write-response
half of the loop. The in-process ``TtyAdapter`` (Wave 2) does NOT touch
this module — it reads stdin directly and never writes state files; the
old ``tty_bridge`` subprocess-loop that used to land here was removed in
the same clean break.

State directory canonical (v1.3 clean break, spec §5):
The default ``state_dir`` resolves to ``forge_state_dir(project_root)``
— i.e., ``.claude/forge/state/`` — the v1.3 sub-namespace.  Callers
that supply ``state_dir`` explicitly still win (override semantics).
Pre-v1.3 default was ``.claude/state/``; that path is gone (no legacy
fallback) since the project is pre-production (no install to migrate).

Why a dedicated module:

- Keeps ``question.py`` focused on the API surface preserved for the
  125 callsites across 10 engine modules.
- Atomic write (via ``engine.utils.json_io.write_json``) is a hard
  contract — no caller may bypass it and write directly.
- Race detection has nuance (stale > 10min, recent = error, malformed
  = treat as stale) that lives best next to the writer.

Surface delivered in W1.T3 (foundation):

- ``write_pending(intent, project_root)`` — atomic emit
- ``read_response(project_root, intent_id)`` — None if absent, dict if
  match, raises ``IntentMismatchError`` on intent-id divergence
- ``clear_intent_files(project_root)`` — idempotent cleanup of both
- ``detect_race(project_root, new_intent_id)`` — returns None if free
  to write, sweeps stale pending (> 10min), raises
  ``RaceDetectedError`` if a recent pending with a different intent-id
  is still parked

Companion helpers added in W3 (caller-side of the loop, consumed by the
host adapter that fronts the engine — the Claude Code host):

- ``read_pending(project_root)`` — None if absent, dict otherwise.
  Counterpart to ``read_response`` from the host's perspective.
- ``write_response(project_root, response)`` — atomic emit using the
  same tempfile-rename strategy.

Re-entry idempotency (W7-fix consumed-log, 2026-06-12):

Multi-intent handlers (forge init brownfield/greenfield, reconfigure
backend submenu) emit 2+ intents sequentially. Without idempotency the
handler re-entry would refuse to progress: each subprocess re-invocation
restarts the handler from the top, hits the FIRST ``ask()`` with its
stable intent-id, but ``forge-response.json`` already holds the LATEST
intent's response — ``read_response`` would raise ``IntentMismatchError``
and exit 1.

Fix: persistent consumed-log at ``.claude/state/forge-intent-log.jsonl``.
``read_response`` consults the log first; if the intent-id was consumed
in a prior subprocess invocation, returns the cached response without
touching ``forge-response.json``. The log lives for the lifetime of a
single ``forge <cmd>`` invocation lifecycle and is cleared by
``clear_intent_files(also_log=True)`` from ``engine/cli.py::main()`` at
terminal exit (success or non-pause error). Exit 2 (paused) does NOT
clear — the next re-invocation needs the log to skip already-answered
intents.

Refs:
- ``docs/superpowers/specs/drift-1-intent-protocol.md`` §2, §3, §9
- ``docs/schemas/intent-protocol.md`` §4 (consumed-intent log)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.utils import json_io
from engine.utils.paths import forge_state_dir

# Pending older than this is considered orphaned and gets swept.
_STALE_THRESHOLD_SECONDS = 10 * 60  # 10 minutes

# Wire-format version of the pending/response payloads on disk. Bumped only on
# breaking changes to the schema (see `docs/schemas/intent-protocol.md`).
_SCHEMA_VERSION = 1

# Tolerance for clock skew when `created-at` lands in the future. NTP jitter
# in CI / VMs commonly drifts a few seconds; anything beyond a minute almost
# certainly means a clock that cannot be trusted, so we treat the pending as
# stale and sweep instead of holding the lane open indefinitely.
_FUTURE_SKEW_TOLERANCE_SECONDS = 60


class IntentMismatchError(RuntimeError):
    """Raised when a response file's intent-id does not match the caller's.

    Forensic by design: the file is preserved for inspection rather than
    silently discarded. Top-level handler maps this to exit code 1.
    """


class RaceDetectedError(RuntimeError):
    """Raised when a recent pending intent (≤ 10min) blocks a new one.

    The existing pending is NOT overwritten. Caller must wait or delete
    ``.claude/forge/state/forge-pending.json`` by hand. Top-level handler
    maps this to exit code 1 with the mentor-calmo phrasing carried in
    ``args[0]``.
    """


class SchemaVersionMismatchError(RuntimeError):
    """Raised when a pending/response file declares a ``schema-version`` the
    engine does not understand.

    Forensic by design (file is preserved). The message is mentor-calmo and
    tells the user which version landed on disk vs. which one this engine
    speaks, then suggests updating feature-forge so the two sides line up.
    Top-level handler maps this to exit code 1.
    """


# --- Path helpers ----------------------------------------------------------


def _state_dir(
    project_root: Path, state_dir_override: Path | None = None
) -> Path:
    """``.claude/forge/state/`` for this project (default), or the explicit
    override.

    Fix #3 / Path A (v1.3 pilot-ready, spec §5 clean break, 2026-06-16):
    The default resolves to ``forge_state_dir(project_root)`` — i.e.,
    ``.claude/forge/state/`` — the v1.3 canonical sub-namespace. The
    pre-v1.3 default (``claude_dir(project_root) / "state"``) is gone:
    no legacy fallback, no migration shim. Pre-production phase means
    there is no install to migrate, so the cleaner default wins.

    ``state_dir_override`` (Task 0.5 facade hook) preserves explicit-override
    semantics: callers that need a specific path still get it back unchanged.
    Used by ``engine/host/adapters/intent_file.py`` and by tests that need
    to pin paths under a ``tmp_path`` root.
    """
    if state_dir_override is not None:
        return state_dir_override
    return forge_state_dir(project_root)


def _pending_path(project_root: Path, *, state_dir: Path | None = None) -> Path:
    return _state_dir(project_root, state_dir) / "forge-pending.json"


def _response_path(project_root: Path, *, state_dir: Path | None = None) -> Path:
    return _state_dir(project_root, state_dir) / "forge-response.json"


def _log_path(project_root: Path, *, state_dir: Path | None = None) -> Path:
    """``.claude/forge/state/forge-intent-log.jsonl`` — consumed-intent log
    for re-entry idempotency in multi-intent handlers.

    Lifetime is bounded by a single ``forge <cmd>`` invocation cycle:
    written by ``read_response`` on consume, cleared by
    ``clear_intent_files(also_log=True)`` from the top-level handler at
    terminal exit.

    ``state_dir`` keyword (Task 0.5) overrides the default
    ``forge_state_dir(project_root)`` anchor when provided. When ``None``,
    falls back to the v1.3 canonical sub-namespace (spec §5).
    """
    return _state_dir(project_root, state_dir) / "forge-intent-log.jsonl"


# --- consumed-intent log (re-entry idempotency) ----------------------------

# Process-level cache pra `_read_intent_log` (PR #13 review #3405256063).
# Antes: cada chamada de `read_response` re-parseava o JSONL inteiro do
# disco, mesmo o log sendo append-only e nunca encolher dentro de uma
# invocação do forge. Em multi-intent handlers (init brownfield/greenfield,
# reconfigure backend submenu) isso era O(n) por prompt — n linhas × n
# prompts.
#
# Cache key é o `Path` do log (1 entry por project_root). Value é o dict
# parseado. Invalidação via `_append_intent_log` (atualiza incremental) e
# `clear_intent_files`/`clear_intent_log_only` (remove a entry).
#
# `_reset_log_cache` é exposto pra tests que precisam reset explícito —
# fixtures com `tmp_path` em geral usam paths únicos, mas se um test
# reusa o mesmo path entre invocações o cache pode contaminar.
_log_cache: dict[Path, dict[str, dict[str, Any]]] = {}


def _reset_log_cache() -> None:
    """Limpa o cache do log de intents (escape hatch pra testes).

    Em runtime de produção não precisa ser chamado — invalidação acontece
    no write path (`_append_intent_log`) e nos cleanups
    (`clear_intent_files`, `clear_intent_log_only`). Esta função existe
    pra testes que reusam Path entre invocações simuladas.
    """
    _log_cache.clear()


def _read_intent_log(
    project_root: Path, *, state_dir: Path | None = None
) -> dict[str, dict[str, Any]]:
    """Read consumed-intents log → ``{intent-id: response}``.

    Cached por `path` no module-level `_log_cache`. Hit retorna copy
    rasa do dict pra evitar mutação externa do cache.

    Log is append-only JSONL. Defensive parsing:

    - Missing file → returns ``{}``.
    - Empty / blank lines → skipped.
    - Malformed JSON lines → skipped silently (forensic forgiveness:
      a corrupt entry must not block reading the rest of the log; the
      cached read is best-effort by design).
    - Duplicate ``intent-id`` rows → latest entry wins (stable
      ``intent_id`` generation should make this impossible, but the
      latest-wins rule is the safest fallback if a duplicate ever
      slips in).

    Returns a flat dict keyed by ``intent-id`` so callers can do a
    single dict lookup per ``read_response`` call.
    """
    path = _log_path(project_root, state_dir=state_dir)
    if path in _log_cache:
        # Copy rasa — protege o cache contra mutação acidental por callers
        # que façam dict ops downstream. As values (response dicts) são
        # tratadas como read-only por convenção do `read_response`.
        return dict(_log_cache[path])
    if not path.exists():
        _log_cache[path] = {}
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        # Filesystem hiccup — treat as no cache, file is best-effort.
        # Não cacheia o hiccup: próxima chamada tenta de novo (transient).
        return {}
    result: dict[str, dict[str, Any]] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            entry = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        intent_id = entry.get("intent-id")
        if not isinstance(intent_id, str):
            continue
        response = entry.get("response")
        if isinstance(response, dict):
            result[intent_id] = response
    _log_cache[path] = result
    return dict(result)


def _append_intent_log(
    project_root: Path,
    *,
    intent_id: str,
    response: dict[str, Any],
    state_dir: Path | None = None,
) -> None:
    """Append a consumed-intent entry to the log.

    JSONL append + ``flush`` is the durability contract: a process crash
    after the write would leave at most a partial line, which
    ``_read_intent_log`` silently skips. No tempfile-rename gymnastics
    here because we are augmenting an existing file rather than
    replacing one — the JSONL format absorbs partial writes
    gracefully.

    Atualiza o cache (PR #13 review #3405256063) — append incremental
    em vez de invalidar tudo, mantém leituras subsequentes O(1).
    """
    path = _log_path(project_root, state_dir=state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "intent-id": intent_id,
        "response": response,
        "consumed-at": datetime.now(timezone.utc).isoformat(),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
        f.flush()
    # Cache update: garantia de coerência leitura-pós-escrita.
    cached = _log_cache.get(path)
    if cached is None:
        # Primeira vez que vemos esse path — popula cache com a entry nova.
        # Calls subsequentes pegam direto sem re-ler o arquivo inteiro.
        _log_cache[path] = {intent_id: response}
    else:
        cached[intent_id] = response


# --- write_pending ---------------------------------------------------------


def write_pending(
    intent: dict[str, Any],
    project_root: Path,
    *,
    state_dir: Path | None = None,
) -> None:
    """Emit the pending intent atomically.

    ``intent`` must already be a fully-formed dict matching
    ``docs/schemas/intent-protocol.md``. Validation of the shape lives
    with the caller (``question.py``); this module trusts its in-tree
    consumers.

    ``state_dir`` (Task 0.5 facade hook) overrides the default
    ``forge_state_dir(project_root)`` anchor. Default ``None`` resolves
    to ``.claude/forge/state/`` (v1.3 sub-namespace, spec §5 clean break).
    """
    json_io.write_json(_pending_path(project_root, state_dir=state_dir), intent)


# --- read_pending (W3 companion) -------------------------------------------


def read_pending(
    project_root: Path, *, state_dir: Path | None = None
) -> dict[str, Any] | None:
    """Read ``.claude/forge/state/forge-pending.json`` if present.

    Mirrors ``read_response`` but for the engine→caller direction: the
    host (Claude Code adapter) calls this whenever the engine exits with
    code 2, to discover what input the engine is asking for.

    Returns:
    - ``None`` when no pending file is on disk. The caller treats this
      as a clean exit-2 path (e.g. CR-003: user paused via response and
      the engine cleared state).
    - The decoded dict otherwise.

    Raises ``json_io.JsonIOError`` (propagated) on a malformed file —
    same contract as ``read_response``. Forensic preservation per SPEC §3
    is the caller's choice; this function does not touch the file.

    ``state_dir`` (Task 0.5) overrides the default anchor; ``None``
    resolves to ``forge_state_dir(project_root)`` (v1.3 canonical).
    """
    path = _pending_path(project_root, state_dir=state_dir)
    if not path.exists():
        return None
    return json_io.read_json(path)


# --- write_response (W3 companion) -----------------------------------------


def write_response(
    project_root: Path,
    response: dict[str, Any],
    *,
    state_dir: Path | None = None,
) -> None:
    """Emit the response payload atomically.

    Counterpart to ``write_pending``: same tempfile-rename strategy via
    ``engine.utils.json_io.write_json``, same trust contract (the caller
    formed a schema-compliant dict). Used by the host (Claude Code
    adapter) after the user supplies input; the engine then consumes it
    through ``read_response`` on the next invocation.

    ``state_dir`` (Task 0.5) overrides the default anchor.
    """
    json_io.write_json(_response_path(project_root, state_dir=state_dir), response)


# --- read_response ---------------------------------------------------------


def read_response(
    project_root: Path,
    intent_id: str,
    *,
    state_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Read the response file matching ``intent_id``.

    Lookup order (re-entry idempotency, W7-fix 2026-06-12):

    1. **Consumed-intent log** — if ``intent_id`` already appears in
       ``.claude/forge/state/forge-intent-log.jsonl``, return the cached
       response. The on-disk response file is not touched. This makes
       handler re-entry safe across subprocess invocations: the FIRST
       ``ask()`` in a multi-intent handler will always see its own
       response cached, regardless of which intent the host most
       recently answered.

    2. **Response file** — if ``forge-response.json`` exists and its
       ``intent-id`` matches, the response is recorded to the log and
       returned. Subsequent re-entries on the same ``intent_id`` hit
       branch 1 (cached read). The response file itself is preserved
       here; ``question.py`` clears it via ``clear_intent_files`` at
       the end of a successful ``ask*`` consume.

    Returns:
    - ``None`` if neither the log nor the response file holds an entry
      for ``intent_id`` (caller emits pending and exits 2).
    - The decoded dict on match (from the log on re-entry, from the
      file on first consume).

    Raises:
    - ``IntentMismatchError`` if the response file is on disk but its
      ``intent-id`` differs from ``intent_id`` AND the log lacks an
      entry for ``intent_id``. The file is preserved for forensic
      value. The "log lacks entry" guard is important: in a multi-
      intent re-entry, the log has the first intent's response and the
      file has the second intent's response — both legitimate, no
      mismatch.
    - ``json_io.JsonIOError`` (propagated) if the response file is
      malformed JSON.
    """
    # Branch 1: log lookup — re-entry idempotency.
    log = _read_intent_log(project_root, state_dir=state_dir)
    if intent_id in log:
        return log[intent_id]

    # Branch 2: file lookup — first consume in this lifecycle.
    path = _response_path(project_root, state_dir=state_dir)
    if not path.exists():
        return None

    response = json_io.read_json(path)
    _check_schema_version(response, path=path, kind="response")
    written_id = response.get("intent-id")
    if written_id != intent_id:
        raise IntentMismatchError(
            "response intent-id mismatch — "
            f"expected '{intent_id}', got '{written_id}'. "
            f"File preserved at {path} for inspection."
        )
    # Persist to log BEFORE returning — next re-entry skips straight to
    # branch 1 instead of fighting a stale response file.
    _append_intent_log(
        project_root,
        intent_id=intent_id,
        response=response,
        state_dir=state_dir,
    )
    return response


# --- schema-version guard --------------------------------------------------


def _check_schema_version(payload: dict[str, Any], *, path: Path, kind: str) -> None:
    """Raise ``SchemaVersionMismatchError`` if the payload speaks a different
    wire version than this engine.

    Why a strict check (vs. "lenient on read"): the protocol carries user input
    across process boundaries — a silent miscompat between v1 and v2 would
    consume the wrong field shape and surface as a confusing downstream
    failure. Refusing to read with a clear message is the kinder path.

    ``kind`` is "pending" or "response"; it only shapes the error wording.
    """
    written = payload.get("schema-version")
    if written == _SCHEMA_VERSION:
        return
    raise SchemaVersionMismatchError(
        f"{kind} file em {path} declara schema-version={written!r}, "
        f"mas esta versão do forge fala schema-version={_SCHEMA_VERSION}. "
        "Atualize feature-forge no host (ou no engine, se foi o host quem "
        "ficou pra trás) e tente de novo. "
        "O arquivo foi preservado pra inspeção."
    )


# --- clear_intent_files ----------------------------------------------------


def clear_intent_files(
    project_root: Path,
    *,
    also_log: bool = False,
    state_dir: Path | None = None,
) -> None:
    """Delete ``forge-pending.json`` and ``forge-response.json``.

    Idempotent: no-op when either file is already absent. Called by the
    engine after a successful response consume — keeps state clean
    between pauses (sub-Q **Sb** locked in the spec).

    By default the consumed-intent log
    (``forge-intent-log.jsonl``) is preserved: re-entry idempotency
    (W7-fix) requires the log to survive across the per-prompt
    cleanups inside ``question.py`` while a single ``forge <cmd>``
    invocation is mid-flight.

    Pass ``also_log=True`` when the call site is a successful per-
    prompt consume AND also wants the log gone. In normal operation
    callers do not need this — ``engine/cli.py::main()`` handles log
    lifecycle via ``clear_intent_log_only`` at terminal exit so it
    can wipe the log without touching pending/response (which SPEC §3
    preserves forensically on error paths).
    """
    json_io.delete_if_exists(_pending_path(project_root, state_dir=state_dir))
    json_io.delete_if_exists(_response_path(project_root, state_dir=state_dir))
    if also_log:
        log_path = _log_path(project_root, state_dir=state_dir)
        json_io.delete_if_exists(log_path)
        # Cache invalidation: próxima leitura re-lê do disco (que estará
        # ausente → {}). Sem isso, callers veriam entries fantasma.
        _log_cache.pop(log_path, None)


def clear_intent_log_only(
    project_root: Path, *, state_dir: Path | None = None
) -> None:
    """Delete only ``forge-intent-log.jsonl``, leaving pending/response
    intact.

    The top-level handler (``engine/cli.py::main()``) calls this in its
    ``finally`` block at every terminal exit (0 success, 1 error, 130
    cancel, or user-paused exit 2) EXCEPT the engine-paused exit 2
    (``PausedForInputError``). Wiping pending/response here would defeat
    SPEC §3's forensic-preservation rule on error paths — that work
    belongs to ``question.py``'s success branch via ``clear_intent_files``.

    Idempotent: no-op when the log file is absent.
    """
    log_path = _log_path(project_root, state_dir=state_dir)
    json_io.delete_if_exists(log_path)
    # Cache invalidation pareada com o delete on-disk.
    _log_cache.pop(log_path, None)


# --- detect_race -----------------------------------------------------------


def _parse_created_at(value: str) -> datetime | None:
    """Tolerant ISO-8601 parser. Returns None on malformed input."""
    if not isinstance(value, str):
        return None
    try:
        # Normalise the trailing "Z" (Python's fromisoformat accepted it
        # only from 3.11+, and we have a broader tolerance budget here).
        normalised = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalised)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def detect_race(
    project_root: Path,
    new_intent_id: str,
    *,
    state_dir: Path | None = None,
) -> None:
    """Check whether it is safe to write a new pending for ``new_intent_id``.

    Outcomes:

    - No existing pending → returns ``None`` (safe to proceed).
    - Existing pending has the same ``intent-id`` → returns ``None``
      (treated as a re-emission of the same intent, not a race).
    - Existing pending is stale (``created-at`` > 10 minutes old OR
      missing/malformed) → swept; returns ``None``.
    - Existing pending is recent with a different ``intent-id`` →
      raises ``RaceDetectedError`` with a mentor-calmo message pointing
      at the PID and the file path.

    Lock file via ``fcntl.flock`` is deferred — see the spec
    §"Anti-goals + Considerações futuras".
    """
    pending_path = _pending_path(project_root, state_dir=state_dir)
    if not pending_path.exists():
        return None

    try:
        existing = json_io.read_json(pending_path)
    except (json_io.JsonIOError, OSError):
        # Malformed pending OR filesystem hiccup — treat as stale and sweep.
        # Other exceptions (e.g. ValueError, TypeError) propagate: those are
        # programming errors the caller should see, not "race" noise.
        json_io.delete_if_exists(pending_path)
        return None

    existing_id = existing.get("intent-id")
    if existing_id == new_intent_id:
        return None

    created = _parse_created_at(existing.get("created-at", ""))
    now = datetime.now(timezone.utc)

    if created is None:
        # No usable timestamp — treat as orphaned.
        json_io.delete_if_exists(pending_path)
        return None

    age_seconds = (now - created).total_seconds()
    if age_seconds < 0:
        # `created-at` lives in the future relative to `now`. Two sub-cases:
        #   - small skew (NTP jitter in CI / containers): tolerate and treat
        #     as recent → continue to the race-detection branch below.
        #   - large skew: one of the clocks is clearly bad; sweep so the lane
        #     does not stay parked forever waiting on a phantom session.
        if -age_seconds > _FUTURE_SKEW_TOLERANCE_SECONDS:
            json_io.delete_if_exists(pending_path)
            return None
        # Fall through with the existing pending treated as recent.
    elif age_seconds > _STALE_THRESHOLD_SECONDS:
        json_io.delete_if_exists(pending_path)
        return None

    pid = existing.get("pid", "?")
    raise RaceDetectedError(
        "outra invocação do forge ainda está aguardando resposta "
        f"(PID {pid}, intent-id '{existing_id}').\n"
        "\n"
        "Três caminhos pra resolver:\n"
        "\n"
        "  1) Aguardar o outro processo terminar\n"
        "     A invocação anterior ainda está viva e vai limpar o state\n"
        "     ao receber a resposta do usuário.\n"
        "\n"
        f"  2) Se a sessão anterior travou: rm {pending_path}\n"
        "     Remove o pending órfão e deixa esta invocação seguir.\n"
        "\n"
        "  3) Se for feature paralela conflitante: forge undo\n"
        "     Encerra a outra invocação de forma controlada antes de\n"
        "     começar a nova.\n"
        "\n"
        "Sem auto-fix aqui — escolha humana."
    )
