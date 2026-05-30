# Schema — `.claude/workflow-config-history.jsonl`

The append-only audit log of every `forge reconfigure` apply (and of the
initial `forge init` write). One line per applied event. Committed to git so
the whole team can answer "who changed what, when, and why" without
diffing 17 commits.

This file is the source of truth for **historical** config state. The
**current** state lives in `workflow-config.yaml`.

## File header

This file has no header — it is pure JSONL. The schema-version of each
entry is embedded in the entry itself (`"schema-version": 1`).

```jsonl
{"schema-version":1,"timestamp":"2026-05-28T14:33:11Z","command":"forge init","action":"init","before-snapshot-sha":null,"after-snapshot-sha":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","user-confirmed":true,"notes":"initial install · preset=kmp-mobile-firebase"}
{"schema-version":1,"timestamp":"2026-05-28T16:12:44Z","command":"forge reconfigure","action":"reconfigure-applied","before-snapshot-sha":"e3b0c442...","after-snapshot-sha":"7a3b5e91...","user-confirmed":true,"notes":"8 changes · cards swap koin→hilt + firebase→rest"}
{"schema-version":1,"timestamp":"2026-05-29T09:05:11Z","command":"forge reconfigure","action":"add-card","before-snapshot-sha":"7a3b5e91...","after-snapshot-sha":"9f1ea4c0...","user-confirmed":true,"notes":"added card: analytics-mixpanel"}
```

## Per-line fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `schema-version` | int | yes | 1 in v1. Allows future migrators to detect mixed-version logs. |
| `timestamp` | ISO8601 UTC | yes | When the apply finished. Strictly increasing within the file. |
| `command` | string | yes | Which user-facing entrypoint produced this entry. Must be one of: `forge init`, `forge reconfigure`. (Future `forge raw migrator-...-to-...` entries would be added here.) |
| `action` | enum | yes | What the user did inside the command. See enum below. |
| `before-snapshot-sha` | hex string (64) or null | yes | sha256 of `workflow-config.yaml` immediately before this apply. `null` only when `action == "init"`. |
| `after-snapshot-sha` | hex string (64) | yes | sha256 of `workflow-config.yaml` immediately after this apply. |
| `user-confirmed` | bool | yes | Always `true` in v1 — every action goes through an explicit gate. Field exists so future flows (e.g., automated CI reconfigures) can be distinguished. |
| `notes` | string | yes | Free-form summary the apply step writes. Should be one short sentence. Long diffs live in git, not here. |

### `action` enum

| Value | Triggered by |
|---|---|
| `init` | `forge init` (greenfield install) — appears exactly once per project, on the first line of the file. |
| `reconfigure-applied` | `forge reconfigure` ran end-to-end with ≥ 1 mutation accepted at the gate. |
| `add-card` | `forge reconfigure` → menu "adicionar card" applied at least one new card. |
| `remove-card` | `forge reconfigure` → menu "remover card" applied at least one removal. |
| `upgrade-card` | `forge reconfigure` → menu "atualizar card do canonical" applied at least one upgrade. |
| `lock-card` | `forge reconfigure` → menu "travar edição local" toggled at least one card's `pinned`. |
| `rebuild-graph` | `forge reconfigure` → menu "rebuild do graph" ran successfully (config touched only in `doctor` block). |
| `rebuild-templates` | `forge reconfigure` → menu "rebuild templates" applied. |
| `refresh-inventory` | `forge reconfigure` → menu "re-extrair inventory X" applied. |
| `check-updates` | `forge reconfigure` → menu "verificar updates de cards do canonical" applied changes. |

Multiple `action` flavors can coalesce into a single `reconfigure-applied`
entry when the user runs one cinematic reconfigure that touches several
sub-flows; the more specific `action` values are used when only one sub-flow
ran. The roteiro determines which is emitted — see
`docs/ux/forge-reconfigure-roteiro.md`.

## Retention

```text
Retention: FOREVER. Committed to git.
Pruning:   None in v1. The file is JSONL of small lines; even a hundred
           reconfigures over a project's lifetime is < 50 KB.
Backup:    Git is the backup. There is no `.bak` of this file because it is
           append-only and crash-safe (see "Atomicity" below).
```

## Validation rules

```text
HIST-001  Every line must be valid JSON
HIST-002  Every line must contain all required fields per schema
HIST-003  schema-version must be in supported set (currently {1})
HIST-004  timestamps must be ISO8601 UTC and strictly increasing line-over-line
HIST-005  command must be in {"forge init", "forge reconfigure"} for v1
HIST-006  action must be in the enum
HIST-007  before-snapshot-sha must be null IFF action == "init"; otherwise must match regex ^[0-9a-f]{64}$
HIST-008  after-snapshot-sha must match regex ^[0-9a-f]{64}$
HIST-009  For every non-init line, the before-snapshot-sha must equal the
          previous line's after-snapshot-sha (continuous chain — no gaps)
HIST-010  user-confirmed must be true in v1
HIST-011  notes must be ≤ 280 chars (longer summaries live in git commit body)
HIST-012  The first line of the file must have action == "init"
```

HIST-009 is the integrity backbone: any tampering with the file breaks the
chain immediately. `forge doctor` runs this check. A broken chain is a
critical doctor failure.

## Atomicity

Writing to a JSONL file is naturally atomic at the line level if you write
one complete line in a single `write()` syscall and the line ends with `\n`.
The reconfigure apply step does exactly that:

```python
def append_history_entry(entry: dict) -> None:
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

Crash mid-line = next-startup truncation of any trailing partial line by
`forge doctor`. Crash between lines = nothing to recover.

## Concurrency

- **One writer at a time.** `flock` exclusive during write.
- **Many readers.** No coordination needed; readers must tolerate a
  partial last line if reading during a write (skip and re-read).
- **Multi-machine.** Git enforces the cross-machine ordering. If two
  developers reconfigure concurrently on different branches, the merge
  conflict is human-resolved (rare; documented in
  `docs/ux/forge-reconfigure-roteiro.md` edges).

## Reading patterns

| Use case | How |
|---|---|
| "What's the current sha?" | Last line's `after-snapshot-sha`. |
| "When did we switch to Hilt?" | grep for `action: reconfigure-applied` + notes containing "hilt". |
| "How many reconfigures this quarter?" | line-count filtered by timestamp range. |
| "Has anyone touched cards in the last week?" | grep `action: (add|remove|upgrade|lock)-card`. |
| "Rebuild the chain to verify integrity" | Replay HIST-009 from line 1 to EOF. |

## Out of scope for v1

- Querying via SQL (the file is small enough for `grep` + `jq`)
- Notification on append (PR review covers this — config changes ship in
  PRs, reviewers see the new history entry in the diff)
- Cross-project history aggregation
- Cryptographic signing of entries (git commit signing is the proxy)

## Related schemas

- `workflow-config.yaml` — the live state this file logs changes to —
  see `docs/schemas/workflow-config.md`
- `.claude/memory/history.jsonl` — a different append-only log that tracks
  per-feature lifecycle events (not config changes)
- `docs/ux/forge-reconfigure-roteiro.md` — the cinematic UX whose final
  scene appends to this file
