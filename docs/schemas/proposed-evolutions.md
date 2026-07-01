# Schema — `.claude/proposed-evolutions.yaml`

The queue of self-evolution proposals waiting for the user to review. Written
by `retrospective-agent` after each `feature-done`, consumed by `forge evolve`,
drained as user accepts / rejects / defers each proposal.

This is the engine's **suggestion box**, not its decision log. Nothing in here
takes effect until the user explicitly applies it through `forge evolve`.

## File header

```yaml
# feature-forge / proposed-evolutions.yaml
# ──────────────────────────────────────────────────────────────────────────
# Schema version: 1
# Location:       .claude/proposed-evolutions.yaml
# Owner:          retrospective-agent (writes proposals) ·
#                 forge evolve (drains the queue) ·
#                 doctor (reads count for status board)
# Git policy:     COMMIT this file. Proposals are durable across sessions.
# ──────────────────────────────────────────────────────────────────────────

schema-version: 1
last-updated:   2026-05-28T16:40:00Z
last-source:    retrospective-agent           # who wrote the most recent entry
```

## Top-level layout

```yaml
schema-version: 1
last-updated:   2026-05-28T16:40:00Z
last-source:    retrospective-agent

proposals:
  - id: P-001
    type: l1-to-l2-promotion
    confidence: 0.95
    created-at: 2026-05-28T16:38:11Z
    source:
      features:
        - bonsai-form
        - register
        - lembrete-rega
        - water-tracker
      trigger: retrospective
    rationale: |
      Quatro features consecutivas implementaram outbox-queue para escrita
      offline. Confiança alta de que vira regra padrão do projeto.
    proposed-change:
      target-file: .claude/memory/L2-project.yaml
      operation: append
      payload:
        patterns:
          - id: P-007
            name: "outbox queue for offline-write features"
            detected-in: [bonsai-form, register, lembrete-rega, water-tracker]
            description: |
              Features que permitem criação offline usam outbox queue com
              retry, não optimistic-with-rollback.
            confidence: 0.95
            promoted-to-rule: false
    provenance:
      count: 4
      feature-slugs: [bonsai-form, register, lembrete-rega, water-tracker]
    impact:
      - "planning-conductor passa a usar este padrão como L2 default"
      - "próximas features similares pulam ≈ 1 rodada de elicitation"
```

## Proposal types (enum)

`type` must be one of:

| Value | Meaning |
|---|---|
| `l1-to-l2-promotion` | Pattern detected ≥ 3 features; promote a feature-local insight to project-wide L2. |
| `template-patch` | Template under `templates/*.template.*` should gain or lose a section based on observed gaps. |
| `agent-prompt-addition` | Sub-agent prompt should add a reminder / contract clause / example. |
| `new-card-suggestion` | Repeated need for capability not covered by any active card — suggests installing or authoring a new card. |
| `question-elimination` | A question asked in elicitation across N features always got the same answer → freeze as `decisions-frozen` in L2 (or drop from template). |
| `convention-refinement` | A convention in `inventory/conventions.yaml` should be tightened or relaxed based on how features actually used it. |

Adding a new `type` requires updating `retrospective-agent` + `forge evolve`
roteiros simultaneously. Don't introduce a value the apply path can't honor.

## Per-proposal fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string `P-NNN` | yes | Unique within the file at write time. **Note:** retrospective-agent re-IDs proposals each run — fingerprint (in `rejected-evolutions.yaml`) is the durable identity, not the ID. |
| `type` | enum (above) | yes | |
| `confidence` | float `[0, 1]` | yes | retrospective-agent's confidence the proposal is correct + valuable. Below 0.5 is rare. |
| `created-at` | ISO8601 UTC | yes | When retrospective-agent wrote this entry. |
| `source` | object | yes | See below. |
| `source.features` | list of feature slugs | yes | Which features triggered the proposal. Empty list is invalid. |
| `source.trigger` | enum | yes | `retrospective` (after feature-done) \| `distillation` (during L2 compaction) \| `doctor` (during health check) \| `manual` (user added entry via editor — rare). |
| `rationale` | multi-line string | yes | One paragraph the user can read inside `forge evolve` to understand why this matters. |
| `proposed-change` | object | yes | The actual mutation, structured so apply can be transactional. |
| `proposed-change.target-file` | path | yes | What file gets modified. |
| `proposed-change.operation` | enum | yes | `append` \| `replace-key` \| `merge` \| `insert-block` \| `delete-block`. |
| `proposed-change.payload` | object \| string | yes | The data to merge/append. Shape depends on `operation`. |
| `provenance` | object | yes | Audit context. |
| `provenance.count` | int ≥ 1 | yes | How many features support this proposal. **3+** is the natural promotion threshold for `l1-to-l2-promotion`. |
| `provenance.feature-slugs` | list | yes | Same content as `source.features`, kept separately so fingerprint can be computed without coupling to `source`. |
| `impact` | list of strings | no | Bullets shown in the apply diff so the user sees consequences before confirming. |

### Provenance vs source — why both?

- `source` is **the trigger of this writeback session** (when + how the
  proposal entered the queue).
- `provenance` is **the durable evidence set** used to compute the
  fingerprint that blocks re-proposal after a rejection. Keeping them
  separate means re-numbering the proposal (P-001 → P-008 after a partial
  rollback) doesn't change the fingerprint.

## Validation rules

```text
PROP-001  schema-version must be 1
PROP-002  every proposals[].id must match regex ^P-\d{3,}$
PROP-003  every proposals[].type must be in the enum
PROP-004  every proposals[].confidence must be in [0, 1]
PROP-005  every proposals[].source.features must be non-empty
PROP-006  every proposals[].source.features[] must reference a real feature directory
PROP-007  every proposals[].provenance.count must equal len(proposals[].provenance.feature-slugs)
PROP-008  every proposals[].proposed-change.target-file must resolve to a path inside the repo
PROP-009  proposals[].proposed-change.operation must be in {append, replace-key, merge, insert-block, delete-block}
PROP-010  forge evolve refuses to apply a proposal whose fingerprint (sha256 over the canonical form per rejected-evolutions schema) is present in rejected-evolutions.yaml
PROP-011  proposals[].created-at must be ISO8601 UTC
PROP-012  proposals[].id must be unique within the file at write time (collisions resolved by re-numbering before write)
PROP-013  last-updated must be ≥ max(proposals[].created-at)
```

Each rule has a stable identifier so `forge doctor` and `forge evolve`
can reference failures consistently. Apply blockers are PROP-001 to PROP-009
plus PROP-010 (fingerprint guard). PROP-011 / PROP-013 are warn-level
because clock skew is real.

## Lifecycle

```
       ┌─────────────────────────────┐
       │ retrospective-agent runs    │
       │ after feature-done          │
       └──────────────┬──────────────┘
                      ▼
       ┌─────────────────────────────┐
       │ For each candidate pattern: │
       │  1. Compute fingerprint     │
       │  2. Check                   │
       │     rejected-evolutions     │
       │  3. If not rejected, append │
       │     to proposed-evolutions  │
       └──────────────┬──────────────┘
                      ▼
       ┌─────────────────────────────┐
       │  User runs `forge evolve`   │
       │  Loop: apply / reject /     │
       │  defer / edit-and-apply     │
       └──────────────┬──────────────┘
                      ▼
       ┌─────────────────────────────┐
       │ Outcomes:                   │
       │  apply  → drains entry +    │
       │           mutates target    │
       │  reject → drains entry +    │
       │           writes fingerprint│
       │           to rejected-evol. │
       │  defer  → entry stays       │
       │  edit-and-apply → user      │
       │           amends payload,   │
       │           then apply path   │
       └─────────────────────────────┘
```

## Concurrency

- **One writer at a time.** retrospective-agent and `forge evolve` both hold
  an OS-level lock on the file (`flock`) during writes.
- **Atomic writes.** Mutations go through `.proposed-evolutions.yaml.tmp` +
  `mv` to avoid partial files if the process crashes mid-write.
- **Backup before drain.** `forge evolve` snapshots the file to
  `.proposed-evolutions.yaml.bak` before its loop starts, so a mid-loop
  Ctrl-C cannot corrupt the queue.

## Out of scope for v1

- Cross-project proposal sharing (would need L4 memory)
- Priority/ranking signals beyond `confidence` and `provenance.count`
- Automatic time-based aging (deferring forever ≠ rejection — the user has
  to make the call explicitly)
- Webhook notifications when new proposals arrive

## Related schemas

- `.claude/rejected-evolutions.yaml` (this file's pair) — see
  `docs/schemas/rejected-evolutions.md`
- `.claude/memory/L2-project.yaml` — common apply target — see
  `docs/schemas/memory.md`
- `.claude/memory/history.jsonl` — every apply / reject / defer appends a
  line here for audit

---

## Reuse Intelligence proposal types (schema v2)

Six new `type` values queued automatically by `engine/graph/duplicates.py`
during `forge init` Step 11.5 and on graph rebuild via `forge reconfigure`.

| `type`                                  | Triggered when                                                                 | Confidence | Apply path                                                  |
|-----------------------------------------|--------------------------------------------------------------------------------|------------|-------------------------------------------------------------|
| `consolidate-duplicate-helper`          | Same Kotlin extension in ≥2 files of one Gradle module                         | 0.95       | Refactor intake stub in `non-product/refactor-{slug}/`     |
| `promote-to-shared-helper`              | Same Kotlin extension across ≥2 sibling modules                                | 0.85       | idem; target = smallest-common-ancestor module             |
| `remove-redundant-platform-helper`      | Android Kotlin identical to shared `commonMain` Kotlin                         | 0.90       | idem; suggested target = keep shared, drop Android         |
| `review-near-duplicate-helper`          | Same signature, different `body_hash` (drift)                                  | 0.40       | idem; manual review demanded — never auto-apply             |
| `kmp-migration-candidate`               | Swift extension `(receiver, name)` matches Kotlin shared with token similarity ≥0.4 | 0.50–0.75  | idem; suggested target = SKIE call into shared              |
| `consolidate-ts-helper`                 | Same TypeScript top-level helper duplicated in one module                      | 0.95       | idem; target = `util/` of the module                       |

All six share these conventions:

- `source.trigger = "init-scan"` (or `"reconfigure"` during a rebuild).
- `proposed-change.operation = "refactor-plan"` — apply writes a feature-intake
  stub at `docs/forge-specs/non-product/refactor-{slug}/`
  using `templates/feature-intake-refactor.template.md` and writes the L1
  `status.json` with `subtype=refactor`.
- `proposed-change.payload` carries the full detection payload (category,
  receiver_type, symbol_name, canonical_signature, body_hash, modifiers,
  similarity_score, locations, suggested_target).
- `fingerprint` is a 64-char SHA-256 over category-specific fields. Stable
  across rebuilds — same logical group keeps the same proposal entry
  (idempotent re-queue).
- `provenance.feature-slugs = ["__init-scan__"]` — sentinel slug indicating
  the proposal came from a graph scan rather than a feature retrospective.

### Apply / reject mechanics

`route_proposal_to_inbox` dispatches the six kinds to
`engine.graph.reuse_apply.apply_reuse_intelligence_proposal(project_root, proposal)`
which:
1. Computes the kebab-case slug `refactor-{receiver}-{name}`.
2. Renders `templates/feature-intake-refactor.template.md` with the payload.
3. Writes the intake at the non-product directory.
4. Writes the L1 status via `engine.memory.l1.write_l1_status` with
   `subtype="refactor"` — `forge plan {slug}` recognises this and skips Wave A
   discovery.

Reject path uses the standard rejected-evolutions veto — the SHA-256
fingerprint goes into `.claude/rejected-evolutions.yaml` and the proposal
never resurfaces.
