# Schemas — `.claude/memory/`

Memory is the **accumulated learning** of the engine across time. Not config
(decisions), not inventory (facts) — but patterns, contradictions resolved,
FNDs, and project-specific intuitions that survive between sessions.

Five layers; three implemented in v1.

## Layer overview

```
┌────────────────────────────────────────────────────────┐
│ L1 — Per-feature                                       │
│   location: .claude/memory/L1/{feature-slug}/          │
│   scope:    one feature lifecycle                      │
│   write:    yes (during forge plan / implement)        │
│   git:      ❌ (work-in-progress, archived on done)    │
├────────────────────────────────────────────────────────┤
│ L2 — Project                                           │
│   location: .claude/memory/L2-project.yaml             │
│   scope:    this repo, across features                 │
│   write:    yes (via retrospective + user approval)    │
│   git:      ✅ (team shares learning)                  │
├────────────────────────────────────────────────────────┤
│ L3 — User-global                                       │
│   location: ~/.claude/projects/{hash}/memory/          │
│   scope:    this user across all projects              │
│   write:    NO (forge is read-only here)               │
│   git:      managed by Claude auto-memory              │
├────────────────────────────────────────────────────────┤
│ L4 — Skill-global (not in v1)                          │
│   location: ~/.feature-forge/skill-memory.yaml         │
│   scope:    feature-forge across all projects          │
│   write:    yes (opt-in)                               │
│   git:      ❌                                          │
├────────────────────────────────────────────────────────┤
│ L5 — Per-card (not in v1)                              │
│   location: ~/.feature-forge/cards/{name}/memory.yaml  │
│   scope:    card-specific patterns across projects     │
│   write:    yes (opt-in)                               │
│   git:      ❌                                          │
└────────────────────────────────────────────────────────┘
```

Read order during planning-conductor entry: L1 → L2 → L3 → (L4) → (L5).
More specific wins on conflict.

---

## L1 — Per-feature memory

The feature logbook. Created by `forge plan`, updated throughout
`forge implement`, archived on `feature-done`.

### Files in L1

L1 owns **8 files**, all under `.claude/memory/L1/{feature-slug}/`. This is
the full scope — no subdirectories, no sibling artifacts.

```
.claude/memory/L1/{feature-slug}/
├── hypothesis.yaml          working hypothesis from Phase 1 of planning-conductor
├── ambiguity-map.yaml       decision tree with resolution sources
├── elicitation.yaml         user-answered questions
├── rationale-trace.yaml     decisions log
├── dispatch-log.jsonl       sub-agent invocations
├── history.jsonl            event log (append-only)
├── verify-log.jsonl         every forge verify run (pass / fail / degraded) — append-only
└── status.json              feature lifecycle state (lock signal)
```

> **What is NOT L1.** The following directories belong to the **feature
> package**, not to memory L1, and live under
> `docs/forge-specs/features/{slug}/` per
> `docs/design/05-filesystem-layout.md`:
>
> - `findings/` — FNDs raised during planning / implementation
> - `completion-evidence/` — proofs that each task's contract was met
> - `checkpoints/` — Plan Mode plans and post-apply snapshots
> - `reviews/` — code review notes and decisions
> - `screenshots/` — visual references attached to the feature
>
> They are version-controlled in git as part of the feature package; L1
> memory (this directory) is gitignored work-in-progress that compresses to
> a `summary.yaml` on feature-done.

### `verify-log.jsonl`

Append-only log of every `forge verify` invocation against this feature.
One line per run.

```jsonl
{"timestamp":"2026-05-28T15:42:11Z","scope":"task","task-id":"TASK-0001","result":"pass","warnings":0,"duration-ms":1842}
{"timestamp":"2026-05-28T16:11:03Z","scope":"task","task-id":"TASK-0002","result":"degraded","warnings":2,"duration-ms":2104,"notes":"observability contract added entry; not blocking"}
{"timestamp":"2026-05-28T18:01:55Z","scope":"feature","task-id":null,"result":"pass","warnings":0,"duration-ms":7531}
```

Validation:

```text
MEM-L1-VL-001  every line must be valid JSON
MEM-L1-VL-002  timestamp must be ISO8601 UTC
MEM-L1-VL-003  scope must be in {"task", "feature", "inferred"}
MEM-L1-VL-004  result must be in {"pass", "warn", "degraded", "fail"}
               (warn = validators executados, alguns warnings não-bloqueantes)
MEM-L1-VL-005  if result == "degraded", warnings must be ≥ 1
```

Behavior: when the last entry's `result == "degraded"`, the next
`forge implement` advancement is blocked until the user acknowledges (the
roteiro shows the warnings and asks "ok to continue?"). When `result == "fail"`,
the feature's `status.json.state` is left at `verifying` and the conductor
explains the failure.

### `hypothesis.yaml`

```yaml
schema-version: 1
feature-slug: lembrete-rega
created-at: 2026-05-28T14:23:11Z

hypothesis:
  shape: list+detail              # list | list+detail | form | flow | dashboard | settings | custom
  screens: [list, detail, edit]
  persistence: firestore          # local-only | server-only | both | none
  realtime: false
  auth-required: true
  similar-features:               # found via graph query
    - bonsai-list
    - water-tracker
  identified-components:          # match against design-system inventory
    - MeoCard
    - MeoFab
    - MeoTopBar
  new-components-needed:
    - ReminderBadge
    - WaterDropletIcon
  confidence: 0.78
  rationale: |
    Ticket mentions "lembrete" (reminder) which structurally matches
    list+detail. Screenshots show 3 mockups. Persistence inferred from
    project's Firestore-default pattern (L2 confirms).
```

#### `extension-scope` (Gap 9 — opcional)

Quando o feature em questão tem `status.json.extends-feature != null`
(extension de uma feature done — discipline §10), `hypothesis.yaml`
ganha o campo `extension-scope`:

```yaml
schema-version: 1
feature-slug: lembrete-rega-push
extends-feature: lembrete-rega
parent-feature: lembrete-rega
extension-scope: push-notification    # opcional — string livre
shape: extension
subtype: product
```

| Campo | Tipo | Quando | Quem escreve | Quem lê |
|---|---|---|---|---|
| `extension-scope` | string \| null | Apenas em features extension | `feature-intake-agent` na Cena 2 (source inquiry) | `validators/validate_extension_feature.py` (EXT-004 dedupe) |

**Semantics:** chave de dedupe pra EXT-004. Múltiplas extensions do mesmo
parent são OK quando `extension-scope` é distinto (`android-widget` vs
`ios-watch`); colisão de scope é bloqueada. Ausência do campo (ou null) é
tratada como string vazia — duas extensions empty-scope do mesmo parent
trippam EXT-004 e o validator nudga o user a declarar scope explícito em
vez de shipping ambíguo.

Forward-compat: ausência do campo em features standalone (sem
`extends-feature`) é silenciosa — validator faz no-op nesses casos. Em
features extension legacy sem scope, o user precisa adicionar manualmente
na próxima edição do `hypothesis.yaml`.

### `ambiguity-map.yaml`

```yaml
schema-version: 1
feature-slug: lembrete-rega
computed-at: 2026-05-28T14:24:00Z

decisions:
  - id: D-entry-point
    description: "Where does user enter this feature from?"
    value: "bottom-bar tab + push notification deep link"
    source: ticket-acceptance-criteria
    confidence: 1.0
  
  - id: D-empty-state
    description: "What shows when no reminders exist?"
    value: null                   # unresolved
    source: null
    confidence: 0.0
    needs-elicitation: true
    candidates:
      - "MeoFeedbackState with CTA to create first"
      - "Inline form to create first reminder"
  
  - id: D-realtime-updates
    description: "If another device edits, does list update live?"
    value: false
    source: l2-pattern             # L2 shows project uses one-shot reads default
    confidence: 0.85

unresolved-count: 4
total-decisions: 27
```

### `elicitation.yaml`

```yaml
schema-version: 1
feature-slug: lembrete-rega

rounds:
  - round: 1
    timestamp: 2026-05-28T14:30:00Z
    questions-asked: 4
    answers:
      - question-id: Q-empty-state
        answer: "MeoFeedbackState with CTA"
        drill-down-needed: false
      - question-id: Q-backup-strategy
        answer: "Outbox queue with retry"
        drill-down-needed: false
        rationale: "Para criação offline funcionar"
      - question-id: Q-conflict-resolution
        answer: "last-write-wins"
        drill-down-needed: false
      - question-id: Q-push-permission-flow
        answer: "vague (depende)"
        drill-down-needed: true
        drill-down-answer: "Pede no primeiro lembrete criado"
        drill-down-rounds: 1

remaining-ambiguity: 0
```

### `phase_lock` canonical form

Open questions written by sub-agents tag themselves with `phase_lock` so the
conductor knows which agent (or task) owns the resolution. Two forms:

1. **Agent-scoped** — used in Waves A–C (before tasks exist):
   `phase_lock: intake | prd | screen-analysis | contract-planner | tech-spec`

2. **Task-scoped** — used in Wave D+ (after task-contract-writer produces TASK ids):
   `phase_lock: TASK-{NNNN}` (e.g., `TASK-0003`)

Pre-Wave-D agents that anticipate UI-detail questions tied to a future task may
use `TASK-{slug}-{purpose}` as a placeholder (e.g., `TASK-lembrete-rega-ui`).
task-contract-writer will resolve placeholders to concrete `TASK-NNNN` ids
when it produces the breakdown.

**Blocking behavior:**
- Agent-scoped `phase_lock` blocks the feature globally (readiness=blocked) until resolved
- Task-scoped `phase_lock` blocks only the matching task (other tasks proceed)

### `rationale-trace.yaml`

```yaml
schema-version: 1
feature-slug: lembrete-rega

decisions:
  - id: D-001
    timestamp: 2026-05-28T14:31:00Z
    decision: "Persistence: Firestore with outbox queue for offline writes"
    source: user-elicitation        # user-elicitation | user-paste | memory-L2 | codebase-graph | card-default | inference
    rationale: |
      User confirmed offline-create + online-sync (Q-backup-strategy round 1).
      L2 pattern shows project uses outbox in 2/3 features with offline-write.
    confidence: 1.0
    influences-artifacts:
      - data-contract-spec.yaml
      - tech-spec.md
      - test-strategy.yaml
  
  - id: D-002
    timestamp: 2026-05-28T14:31:00Z
    decision: "Conflict resolution: last-write-wins"
    source: l2-pattern
    rationale: |
      L2 shows 3/3 features use last-write-wins.
      User confirmed in Q-conflict-resolution.
    confidence: 1.0
    influences-artifacts:
      - data-contract-spec.yaml
      - tech-spec.md
```

> **`user-paste` fallback.** When `ticketing.provider != none` but the Jira/Linear
> MCP is offline/unreachable, planning-conductor asks the user to paste the
> ticket content inline. Decisions resolved from that pasted content use
> `source: user-paste` (not `user-elicitation`) so the trace records that the
> ground truth came from the ticket — just via a degraded transport.

### `dispatch-log.jsonl`

```jsonl
{"timestamp":"2026-05-28T14:35:00Z","wave":"A","agent":"feature-intake-agent","status":"dispatched","context-pack-size-kb":12}
{"timestamp":"2026-05-28T14:35:18Z","wave":"A","agent":"feature-intake-agent","status":"returned","output-file":"feature-intake.md","validation":"pass"}
{"timestamp":"2026-05-28T14:35:18Z","wave":"A","agent":"feature-prd-agent","status":"dispatched","context-pack-size-kb":14}
{"timestamp":"2026-05-28T14:35:30Z","wave":"A","agent":"feature-prd-agent","status":"returned","output-file":"feature-prd.md","validation":"pass"}
```

### `history.jsonl`

```jsonl
{"timestamp":"2026-05-28T14:23:11Z","event":"plan-started","feature":"lembrete-rega","actor":"user"}
{"timestamp":"2026-05-28T14:24:00Z","event":"hypothesis-formed","confidence":0.78}
{"timestamp":"2026-05-28T14:30:00Z","event":"elicitation-completed","rounds":1}
{"timestamp":"2026-05-28T14:36:00Z","event":"readiness-ready","artifacts":16}
```

### `status.json`

```json
{
  "schema-version": 1,
  "feature-slug": "lembrete-rega",
  "state": "planning",
  "state-since": "2026-05-28T14:23:11Z",
  "sub-state": null,
  "subtype": "product",
  "extends-feature": null,
  "parent-feature": null,
  "last-action": "elicitation-completed",
  "last-action-at": "2026-05-28T14:30:00Z",
  "current-task": null,
  "checkpoint-ref": null,
  "verify-degraded": false,
  "graph-stale": false,
  "aborted": false,
  "abort-reason": null
}
```

#### New fields (additive in v1)

| Field | Purpose | Allowed values | Who sets it | Who reads it |
|---|---|---|---|---|
| `sub-state` | Disambiguates the phase a feature is in while `state == implementing`. Without this, the execution-conductor cannot resume cleanly mid-task. | `"plan-mode"` (writing Plan Mode plan), `"apply-mode"` (executing the plan), `"fix-loop"` (post-review iteration), or `null` when `state != implementing`. | execution-conductor on every Plan/Apply transition; `forge implement` resume logic. | `forge status` (shows alongside state); `forge implement` to pick correct resume point; `forge verify` to refuse if fix-loop is mid-flight. |
| `subtype` | Classifies the feature track for wave dispatch — see `docs/design/07-discipline.md §8`. Default `"product"` preserves the legacy pipeline (Waves A–E); `"refactor"` skips Wave B + §11 of tech-spec and requires `check_no_behavior_change` in Wave E; `"bugfix"` runs a compact intake with Wave B **conditional** (UI/behavioral bug → run; logic-only → skip) and a focused tech-spec; `"spike"` and `"chore"` are stubs in v1.0 (conductor surfaces 3-caminhos when chosen). | `"product"` \| `"refactor"` \| `"bugfix"` \| `"spike"` \| `"chore"`. Defaults `"product"` when field absent (forward compat for status.json written by pre-Gap-2 engines). | planning-conductor on Cena 2.5 subtype detection (or on resume from `hypothesis.yaml.subtype`); `engine.plan._initialize_status`. | planning-conductor (wave dispatch branching); tech-spec-agent (conditional section render); `forge status` (badge); `check_no_behavior_change` validator (gates only when `subtype == "refactor"`). |
| `verify-degraded` | Last `forge verify` passed but emitted warnings (e.g., observability contract grew an entry but didn't break). Distinguishes "all green" from "green with caveats" for downstream commands. | `true` \| `false`. Defaults `false`. | `forge verify` sets at the end of a verify run. | `forge status` (badge in board); `forge implement` (refuses to advance if the previous task ended degraded and the user hasn't acknowledged). |
| `graph-stale` | Indicates the graph DB needs rebuild before the next verify can trust queries. Set when paths or DS components mutate without an incremental graph update (rare — usually after a recovery from a corrupted graph). | `true` \| `false`. Defaults `false`. | `forge reconfigure` (sets true if config mutation invalidates graph rows); recovery scripts. | `forge verify` (refuses to run, asks user to pick "rebuild do graph" no menu de `forge reconfigure`); `forge doctor` (warns). |
| `extends-feature` | Marks this feature as a derived extension of a shipped parent (Gap 9 — `extends-feature` mechanic). When non-null, identifies the parent slug whose context (allowed_files baseline, hypothesis.platforms, design-system snapshot) the planning-conductor inherits. Null for standalone features — the default. Pattern preserves "1 feature = 1 ship moment" while giving extensions an official path that doesn't pollute the parent's L1. | slug string (`"{parent-slug}"`) \| `null`. Defaults `null` (forward compat for status.json files written by pre-Gap-9 engines). | planning-conductor on Cena 1 when the user picks the "Estender" path on an existing done feature; `engine.plan._initialize_status` when intake declares `extends-feature`. | planning-conductor (Phase 1 step 5 — extension context import); `validate_extension_feature` validator (EXT-001..004); `forge status` (groups extensions under parent); retrospective-agent (extension-focused retro). |
| `parent-feature` | Reverse pointer mirror of `extends-feature` — same parent slug, repeated for clarity in reverse-lookup queries that walk L1 looking for "who extends me?". Always agrees with `extends-feature` (validator enforces) or both are `null`. The redundancy is deliberate: keeps query code from having to decide which field to read. | slug string (`"{parent-slug}"`) \| `null`. Defaults `null`. Must equal `extends-feature` when non-null. | Same writers as `extends-feature` — set together, in lockstep. | `list_extensions_of(parent)` reverse-lookup helper in `engine/memory/l1.py`; `forge status` extension grouping. |
| `shipped-at` | Carimbo ISO 8601 do momento em que a feature transitou para `state="done"`. Aditivo: ausente em features pre-done (planning / implementing / verifying / deferred / blocked-on-external) e em features `done` pre-Gap-9 (forward-compat). Idempotente: a engine só carimba quando o campo está absent ou null — re-execução de `forge implement` em feature já `done` preserva o timestamp original. | ISO 8601 string (`"YYYY-MM-DDTHH:MM:SSZ"`) \| `null`. Defaults `null` (pre-done states e forward-compat). | `engine.implement` na transição `state="done"` (Gap 9 W-002 fix). | `engine.plan._import_parent_context` (lê pra renderizar `Parent shipped: <ISO>` no bloco §Extension context do intake); retrospective-agent (extension variant section "Parent feature ... (shipped {parent.shipped-at})"). |

All seven fields são **additive**: missing the field em um arquivo escrito
por um engine mais antigo é tratado como `null` / `false` / `"product"` pra
forward-compat. Sem migração necessária. `extends-feature`, `parent-feature`
e `shipped-at` defaultam pra `null` — status.json pre-Gap-9 parse sem
mudança.

**Exemplo done com `shipped-at`** (estado terminal — extension reads daqui):

```json
{
  "schema-version": 1,
  "feature-slug": "lembrete-rega",
  "state": "done",
  "subtype": "product",
  "extends-feature": null,
  "parent-feature": null,
  "shipped-at": "2026-05-28T18:00:00Z",
  "last-action": "implement-completed",
  "last-action-at": "2026-05-28T18:00:00Z",
  "phase-lock": null
}
```

##### `blocked-on-external` state semantics (discipline §9)

The `state` enum gains a new value `"blocked-on-external"` — orthogonal to
`subtype` (what the feature is) and a sibling of `deferred` (which is a
human-driven pause). `blocked-on-external` is engine-driven: it triggers
when any task in the feature declares an unresolved
`depends-on-external` entry with `blocking: true` (see
`docs/schemas/task-contract.md §depends-on-external`).

Transitions:

```
implementing ──┬─→ blocked-on-external   (first unresolved blocking dep detected)
               │
               └─← blocked-on-external   (all blocking deps marked resolved via
                                          `forge reconfigure` → "marcar dep
                                          externa como resolvida")
```

Read semantics:

- `forge status` renders blocked features in their own section (not in
  "in-flight", not in "deferred" — a third group).
- `forge implement` refuses to start a task that itself has unresolved
  blocking deps, surfacing the canonical 3-caminhos block.
- `forge plan` accepts an explicit `depends-on-external` entry from the
  user during Phase 2 elicitation (planning-conductor) and persists it
  into the task-contract for tasks that need it.

Write semantics:

- Only `engine.implement` and `engine.reconfigure` toggle this state.
  `forge plan` never writes `blocked-on-external` directly; it writes the
  field to the task-contract and lets `engine.implement` infer the
  feature-level state on first refusal.
- Going back to `implementing` happens via `forge reconfigure` menu when
  the user marks a ticket id as resolved. The engine re-scans
  task-contracts for remaining blocking deps; if none, it flips state back.
- `forge undo` can revert a "mark resolved" mutation by reading the
  audit trail in `history.jsonl` (`kind: "external-dep-marked-resolved"`).

The state is **additive**: status.json files written by pre-Gap-8 engines
never carry `blocked-on-external` and parse without modification.
`MEM-L1-008` accepts the new value as part of the enum.

##### `subtype` semantics by value

| Value | Waves that run | Artifacts emitted | Validators gated on Wave E |
|---|---|---|---|
| `product` (default) | A · B · C · D · E | Full 16-artifact package | `validate_feature_package`, `validate_readiness`, plus standard cascade |
| `refactor` | A · C · D · E (Wave B **skipped**) | `feature-intake.md` (refactor variant) · `tech-spec.md` (§§ 2, 3-7 modified-layers, 14 only) · `task-breakdown.yaml` · `tasks/TASK-NNNN.yaml` · `implementation-readiness-review.md` · `plan-feature-handoff.json`. No `screen-analysis.md`, `bdd.*`, `ui-state-spec.yaml`, `navigation-spec.yaml`, `data-contract-spec.yaml`, `analytics-spec.yaml`, `test-strategy.yaml` | Standard cascade **plus** `check_no_behavior_change` |
| `bugfix` | A · (B conditional) · C · D · E. Conductor asks once whether the bug touches UI/observable behavior — when "yes", the full Wave B runs (the fix must respect contracts); when "no" (logic-only / data-only), Wave B is skipped exactly like `refactor`. Wave D defaults to 1 task; dev can split. Wave E readiness relaxed when Wave B was skipped (`check_no_behavior_change` does **not** apply — bugfix changes behavior by definition: from broken to correct). | `feature-intake.md` (bugfix variant) · `tech-spec.md` (§§ 1 · 2 · 3-7 touched-layers · 13 · 14; §11 only when new analytics added) · Wave B artifacts iff UI/behavioral · `task-breakdown.yaml` · `tasks/TASK-NNNN.yaml` · `implementation-readiness-review.md` · `plan-feature-handoff.json` | Standard cascade (no extra gate; the fix legitimately changes behavior) |
| `spike` | Stub in v1.0 — conductor surfaces 3-caminhos and asks user how to proceed | n/a (stub) | n/a (stub) |
| `chore` | Stub in v1.0 — conductor surfaces 3-caminhos and asks user how to proceed | n/a (stub) | n/a (stub) |

When `subtype != "product"`, feature artifacts live under
`docs/forge-specs/non-product/{slug}/` instead of
`features/{slug}/` — see `docs/design/05-filesystem-layout.md`. This
applies to `refactor`, `bugfix`, and the (stubbed) `spike`/`chore` —
all share the non-product subtree so the product feature folder stays
clean of "restore correct behavior" / "architecture-only" / "explore"
work that has different shapes.

`state` enum:

| Value | Meaning |
|---|---|
| `not-started` | Feature folder exists but no `forge plan` run yet |
| `planning` | `forge plan` is in progress |
| `planned` | Plan complete; awaiting `forge implement` |
| `implementing` | `forge implement` is in progress on at least one task |
| `verifying` | `forge verify-task` / `forge verify-feature` is running |
| `done` | Feature shipped; L1 will be archived to `summary.yaml` |
| `deferred` | User stopped mid-flow (Ctrl+C / `para`); safe auto-resume. This is where a pause lands — there is no separate `paused` state (Decision 27). |
| `aborted` | `forge plan/implement` aborted; `abort-reason` populated |
| `blocked-on-external` | An unresolved external dependency (`depends-on-external.blocking: true` in a task-contract) prevents the next task from starting. Engine-driven, sibling of `deferred` (which is human-driven). See `docs/design/07-discipline.md §9`. |

`status.json` is the canonical lock signal: other commands read `state` to
detect whether a feature is currently active (see "L1 as a lock mechanism"
below).

### L1 lifecycle

- **Created** on `forge plan` start
- **Updated** throughout plan and implement
- **Archived** on feature-done → compressed to `summary.yaml` (1 file)
- **Retention** until feature is archived (then becomes summary)

### L1 validation

```text
MEM-L1-001  feature-slug must match a directory under docs/.../features/
MEM-L1-002  hypothesis.confidence must be in [0, 1]
MEM-L1-003  ambiguity-map decisions ids must be unique
MEM-L1-004  elicitation rounds must be sequential (1, 2, 3...)
MEM-L1-005  rationale-trace decisions must reference real artifact files
MEM-L1-006  dispatch-log + history must be valid JSONL
MEM-L1-007  elicitation.remaining-ambiguity == 0 required for readiness=ready
MEM-L1-008  status.json must exist and:
              · state must be in {not-started, planning, planned,
                implementing, verifying, done, deferred, aborted,
                blocked-on-external}
              · sub-state must be in {null, "plan-mode", "apply-mode", "fix-loop"};
                must be non-null IFF state == "implementing"
              · subtype must be in {"product", "refactor", "bugfix", "spike", "chore"}
                (default "product" when absent — forward compat for pre-Gap-2
                files; "bugfix" added Gap 1)
              · verify-degraded must be a boolean (default false if absent)
              · graph-stale must be a boolean (default false if absent)
              · when state == "blocked-on-external", at least one task in
                tasks/TASK-*.yaml must declare `depends-on-external` with
                `blocking: true` and `resolved-at: null` (discipline §9 —
                external dependencies)
              · extends-feature must be a slug string or null (default null
                when absent — forward compat for pre-Gap-9 files); when non-
                null, parent slug must exist as a sibling L1 directory
                `.claude/memory/L1/{parent-slug}/` AND parent.state == "done"
                (Gap 9 — extends-feature mechanic; enforced by
                `validate_extension_feature`)
              · parent-feature must be a slug string or null and must equal
                extends-feature when non-null (reverse pointer mirror; set in
                lockstep)
```

---

## L1 as a lock mechanism

`status.json` doubles as the per-feature lock signal. Any L1 with
`state ∈ {planning, implementing, verifying}` constitutes an **active feature
lock**: at least one forge command is currently mutating that feature's
package or memory, and concurrent mutation of shared state would corrupt the
workspace.

Operations that mutate shared state (cards, workflow-config, inventory) MUST
scan `.claude/memory/L1/*/status.json` and refuse to run if any feature is
active. The current scope:

| Command | Why it must check |
|---|---|
| `forge reconfigure` | Rewrites workflow-config — could invalidate in-progress sub-agent context packs |
| `forge reconfigure` → menu "adicionar card" | Card may inject new agent-contributions that conflict with active plan |
| `forge reconfigure` → menu "remover card" | In-progress feature may depend on the card's defaults |
| `forge reconfigure` → menu "atualizar card do canonical" | sha256 + agent-contributions change beneath a running plan |

> All card mutations are subcommands of `forge reconfigure`. There is no
> `forge card` top-level verb — see `docs/design/06-command-surface.md`.

Refusal message contract:

```text
✋ Refusing: feature '{slug}' is currently {state} (since {state-since}).
   Resolve before running this command:
     • Finish naturally — continue with `forge implement {slug}` or
       `forge verify {slug}` per the current state
     • Pause the active session — type "para" inside the running command;
       state transitions to `deferred` and shared-state mutation unlocks
     • Resume later — run `forge plan {slug}` (auto-resume) once deferred
```

Terminal/safe states (`done`, `aborted`, `deferred`) do NOT lock. `deferred`
is the user-driven safe state designed exactly for this (Decision 27 — a
pause lands in `deferred`, auto-resumable): it lets a developer pause
mid-feature to run `forge reconfigure` (which is where card add/remove/
upgrade live as menu options) between sessions without losing progress.

`blocked-on-external` is **also safe** for shared-state mutation: the
feature is paused by an engine-driven gate, no sub-agent is mutating
artifacts, and `forge reconfigure` is explicitly the entrypoint where
the user marks the external ticket as resolved (sub-menu "marcar dep
externa como resolvida"). Treating it as a lock would deadlock the only
exit path.

There is no separate `forge pause` or `forge abort` command — pause is
triggered by typing "para" inside an active forge command (handled by
planning-conductor / execution-conductor); transition to `aborted` happens
only when retry budgets exhaust or the user explicitly cancels via
`forge undo`.

---

## L2 — Project memory

Patterns established across features. The "what we've learned about this
project" file. Survives between sessions and is committed in git.

### Schema

```yaml
schema-version: 1
project-slug: meobonsai
last-updated: 2026-05-28T16:00:00Z
last-distillation: null

# Patterns detected across features (≥ 3 features use the same approach)
patterns:
  - id: P-001
    name: "loading-guard in viewmodels"
    detected-in: [auth.login, bonsai.list, register]
    description: |
      ViewModels check `state.value is StateUI.Processing` before launching
      new operation, to prevent duplicate dispatches.
    confidence: 0.95
    promoted-to-rule: false       # if true, lives in .claude/rules/ also
  
  - id: P-002
    name: "split host/content/components/mappers"
    detected-in: [auth.login, auth.register, bonsai.list, bonsai.detail]
    description: |
      Android screens split into 4 files: {Screen}Screen.kt (host),
      {Screen}Content.kt (stateless), {Screen}Components.kt (helpers),
      {Screen}Mappers.kt (domain→UI mappers).
    confidence: 1.0
    promoted-to-rule: true
  
  - id: P-003
    name: "outbox queue for offline-write features"
    detected-in: [bonsai.create, register]
    description: |
      Features that allow creating data offline use outbox queue with retry,
      not optimistic-with-rollback.
    confidence: 0.85

# Cross-feature findings (FNDs)
findings:
  - id: FND-001
    title: "Auto-complete components need clearFocus after onSelect"
    severity: medium                # low | medium | high | critical
    detected-in: [auth.register]
    description: |
      Focus tracking alone doesn't dismiss the autocomplete dropdown.
      Must call clearFocus() in onSelect callback explicitly.
    fix-pattern: |
      `MeoAutocompleteField(onSelect = { focusManager.clearFocus(); ... })`
    applies-to-cards: [compose-screens]

# Decisions frozen at project level (do not re-ask in any feature)
decisions-frozen:
  - id: DF-001
    decision: "Use Firebase project bonsai-meo-dev for development"
    locked-since: 2026-05-28
    by: user-elicitation-during-init
  
  - id: DF-002
    decision: "All ViewModels return StateFlow<StateUI<T>>"
    locked-since: 2026-05-28
    by: rule-extraction

# Naming conventions encountered
naming-extras:
  - context: "feature module names"
    pattern: "feature/{slug}"
    examples: [auth, bonsai, bonsai-form, register]
  - context: "screen file names"
    pattern: "{Screen}Screen.kt"
    examples: [LoginScreen.kt, RegisterScreen.kt]

# Contradictions resolved (kept for future reference)
contradictions-resolved:
  - id: CR-001
    feature: register
    context: "offline-first vs real-time strategy"
    resolution: "offline-first prevails; real-time deferred to v2"
    timestamp: 2026-05-15

# Promotion candidates (proposed for evolve, not yet approved)
promotion-candidates:
  - source: L1/lembrete-rega/rationale-trace.yaml
    candidate-pattern: "deep link from push notification entering specific tab"
    proposed-name: "push-deep-link-to-tab"
    confidence: 0.6
    appears-in-features: 2          # if reaches 3, gets promoted to patterns
```

### L2 lifecycle

- **Created** on `forge init` (seeded from inventory + L3 if any)
- **Updated** automatically on `feature-done` (triggered after the last task's
  verify succeeds — there is no `forge feature-done` command) via
  retrospective-agent (proposes changes; user approves via `forge evolve`)
- **Distilled** when file exceeds `max-size-mb` (default 0.5MB)
- **Retention** forever; lives in git

### L2 size management

```
max-size-mb: 0.5

When exceeded:
  memory-distiller agent runs
  ↓
  Reads full L2
  ↓
  For each pattern/finding:
    - If superseded by newer entry → mark for removal
    - If never referenced in last 6 months → mark for compression
    - If still active and used → keep
  ↓
  Rewrites L2 with backup at L2-project.yaml.bak
```

### L2 validation

```text
MEM-L2-001  schema-version must be 1
MEM-L2-002  every pattern.detected-in must reference real features
MEM-L2-003  pattern.confidence must be in [0, 1]
MEM-L2-004  if pattern.promoted-to-rule == true, the rule slug must exist in .claude/rules/
MEM-L2-005  findings.severity must be in {low, medium, high, critical}
MEM-L2-006  decisions-frozen.id must be unique
MEM-L2-007  promotion-candidates with confidence > 0.85 should be auto-promoted on next evolve cycle (warn if not)
```

---

## L3 — User-global memory (read-only)

L3 is **not owned by feature-forge**. It is the existing Claude auto-memory
system at:

```
~/.claude/projects/{project-hash}/memory/MEMORY.md
~/.claude/projects/{project-hash}/memory/*.md
```

forge reads this to understand user preferences (language, feedback patterns,
guidance). forge **never writes** here.

### What forge reads from L3

When planning-conductor enters:

1. Open `~/.claude/projects/{hash}/memory/MEMORY.md`
2. Parse the bullet list of pointers
3. Open relevant pointers (those tagged `feedback` or `user` per auto-memory schema)
4. Use as context for tone, language preference, feedback to avoid violating

### What forge does NOT do with L3

- Never writes
- Never edits
- Never re-organizes
- Never deletes entries

If forge identifies a pattern that would be a great L3 addition, it
**suggests verbally** to the user — never persists.

---

## L4 — Skill-global (deferred to post-v1)

Cross-project patterns. Lives at `~/.feature-forge/skill-memory.yaml`.

Not in v1 because requires >1 project to surface value. Promotion path: when
L2 patterns appear in 3+ projects, candidate for L4.

---

## L5 — Per-card (deferred to post-v1)

Card-specific patterns observed across projects. Lives at
`~/.feature-forge/cards/{name}/memory.yaml`.

Example: card `firebase-firestore` learns that 4 of 5 projects using it have
the same FND about index rules. Promotes finding to its agent-prompts
contribution on next install.

---

## Read order in planning-conductor

```
1. Load L1 (if feature-slug exists)
2. Load L2 (always)
3. Load L3 (read MEMORY.md + tagged entries)
4. Load L4 (post-v1)
5. Load L5 (post-v1)

Merge precedence:
- Specific overrides generic
- Newer overrides older
- User-confirmed overrides auto-detected
```

## Write discipline

| Layer | Who writes | When | Approval needed |
|---|---|---|---|
| L1 | planning-conductor + sub-agents | Throughout plan/implement | No (own scope) |
| L2 | retrospective-agent | feature-done | Yes (via `forge evolve`) |
| L3 | Claude auto-memory only | Per-conversation | N/A (not forge) |
| L4 | retrospective-agent | After N projects | Yes |
| L5 | retrospective-agent | After N projects | Yes |

## Out of scope for v1

- Encrypted memory layers (for confidential repos)
- Memory diff visualization tool
- Cross-user memory sharing (team-level L4)
- Memory garbage collection beyond size-based distillation
- Memory query language (cards reference memory verbatim; no DSL)
