# Schema — `.claude/rejected-evolutions.yaml`

The durable veto list. When the user picks "rejeitar permanente" inside
`forge evolve`, the rejected proposal is fingerprinted and recorded here so
the engine **never re-proposes the same idea** — even if retrospective-agent
generates a brand-new `P-NNN` ID on a future run.

This file is the answer to the question "the user already said no to this —
why are you asking again?" In v1 it is the only mechanism that turns a
single rejection into a permanent answer.

## File header

```yaml
# feature-forge / rejected-evolutions.yaml
# ──────────────────────────────────────────────────────────────────────────
# Schema version: 1
# Location:       .claude/rejected-evolutions.yaml
# Owner:          forge evolve (writes on user permanent-reject) ·
#                 retrospective-agent (reads to filter candidates before queuing)
# Git policy:     COMMIT this file. Rejection is a team-level decision.
# ──────────────────────────────────────────────────────────────────────────

schema-version: 1
last-updated:   2026-05-28T16:42:00Z
```

## Top-level layout

```yaml
schema-version: 1
last-updated:   2026-05-28T16:42:00Z

rejections:
  - id: R-001
    fingerprint: "a3f4c8b1d2e6f7901b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8901a2b3c4d5e6"
    rejected-at: 2026-05-28T16:42:00Z
    reason: "user permanent rejection"
    original-proposal-snapshot:
      id-at-rejection-time: P-001
      type: l1-to-l2-promotion
      name: "outbox queue for offline-write features"
      provenance:
        count: 4
        feature-slugs: [bonsai-form, register, lembrete-rega, water-tracker]
      rationale: |
        Quatro features consecutivas implementaram outbox-queue para escrita
        offline. Confiança alta de que vira regra padrão do projeto.
```

## Per-entry fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string `R-NNN` | yes | Sequential within this file. Independent of the proposal's `P-NNN` (which is ephemeral). |
| `fingerprint` | hex string (64 chars) | yes | sha256 — see algorithm below. The **durable identity** of the rejected proposal. |
| `rejected-at` | ISO8601 UTC | yes | When the user picked "rejeitar permanente" in `forge evolve`. |
| `reason` | string | yes | Free-form, short. Default `"user permanent rejection"`. Optionally extended with user's stated reason if the roteiro captured one. |
| `original-proposal-snapshot` | object | yes | Frozen copy of the proposal at the moment of rejection. Audit + future debugging. |
| `original-proposal-snapshot.id-at-rejection-time` | string | yes | The `P-NNN` the proposal had when rejected. Useful only for history.jsonl correlation. |
| `original-proposal-snapshot.type` | enum (per proposed-evolutions) | yes | |
| `original-proposal-snapshot.name` | string | yes | The proposal's `name` / `pattern name` / `template patch name`. Part of the fingerprint input. |
| `original-proposal-snapshot.provenance` | object | yes | Same shape as in proposed-evolutions. Part of the fingerprint input. |
| `original-proposal-snapshot.rationale` | string | no | Helpful for human audit; not part of fingerprint. |

## Fingerprint algorithm

The fingerprint must be deterministic so two retrospective-agent runs over
the same evidence produce the same hash.

### Canonical form

Given a proposal `P`, the canonical form `canonical(P)` is built as follows:

1. Build an object with exactly four keys, in this order:
   ```text
   {
     "type":        <P.type>,
     "name":        <P.name | P.proposed-change.payload.patterns[0].name | P.proposed-change.payload.name>,
     "description": <P.rationale OR P.proposed-change.payload.patterns[0].description, trimmed>,
     "provenance":  sorted(unique(P.provenance.feature-slugs))
   }
   ```
2. Lower-case every string value (`name`, `description`, each entry in
   `provenance`) using Unicode-aware lower-case (NFC normalized first, then
   `str.casefold()` semantics).
3. Trim leading/trailing whitespace on every string. Collapse internal
   runs of whitespace into single spaces inside `description` (so paragraph
   reformatting doesn't change the fingerprint).
4. Sort `provenance` lexicographically (case-insensitive after step 2). It is
   already deduplicated.
5. Serialize the object to JSON using **canonical JSON** rules:
   - UTF-8
   - Keys in the literal order above (NOT alphabetical — the four-key order is
     fixed by step 1)
   - No insignificant whitespace
   - Strings escaped per RFC 8259
6. Compute `sha256(<canonical JSON bytes>)`.
7. Encode the digest as lowercase hex (64 chars).

### Worked example

Source proposal:

```yaml
type: l1-to-l2-promotion
proposed-change:
  payload:
    patterns:
      - name: "Outbox queue for offline-write features"
        description: |
          Features que permitem criação offline usam outbox queue com
          retry, não optimistic-with-rollback.
provenance:
  feature-slugs: [Water-Tracker, register, bonsai-form, lembrete-rega]
```

Canonical form (pretty-printed for clarity — the actual hash input has no
extra whitespace):

```json
{
  "type": "l1-to-l2-promotion",
  "name": "outbox queue for offline-write features",
  "description": "features que permitem criação offline usam outbox queue com retry, não optimistic-with-rollback.",
  "provenance": ["bonsai-form", "lembrete-rega", "register", "water-tracker"]
}
```

`sha256` of those bytes = the fingerprint persisted in `rejections[].fingerprint`.

### Why these four keys

- `type` + `name` capture the **intent** of the proposal.
- `description` captures the **substance** so two superficially renamed
  proposals about the same idea still collide.
- `provenance` set captures the **evidence base**; a different set of
  features hitting the same intent is a genuinely new proposal and deserves
  a fresh look.

Rationale + impact + confidence + IDs are deliberately **excluded** — they
shift between runs without changing the underlying proposal.

## Auto-skip rule

```text
Before retrospective-agent queues a new proposal into
proposed-evolutions.yaml:
  1. Compute canonical(candidate) → fingerprint
  2. If fingerprint ∈ rejected-evolutions.yaml.rejections[].fingerprint:
       SKIP (log to history.jsonl as `proposal-skipped-fingerprint-rejected`)
  3. Else: append to proposed-evolutions.yaml
```

Same guard runs in `forge evolve` at apply time (last-ditch race-condition
defense) — see PROP-010 in `proposed-evolutions.md`.

## Validation rules

```text
REJ-001  schema-version must be 1
REJ-002  every rejections[].id must match regex ^R-\d{3,}$
REJ-003  every rejections[].id must be unique
REJ-004  every rejections[].fingerprint must match regex ^[0-9a-f]{64}$
REJ-005  fingerprints must be unique across rejections[] (collisions = corruption)
REJ-006  rejections[].rejected-at must be ISO8601 UTC
REJ-007  rejections[].original-proposal-snapshot.type must be in the proposed-evolutions type enum
REJ-008  rejections[].original-proposal-snapshot.provenance.count must equal len(provenance.feature-slugs)
REJ-009  forge evolve must compute the fingerprint at write time and refuse if it does not match REJ-004 regex
REJ-010  retrospective-agent must check fingerprints before queuing — bypassing this is a bug, not an edge case
REJ-011  last-updated must be ≥ max(rejections[].rejected-at)
```

REJ-005 — collision of two distinct rejections under one fingerprint means
either sha256 had a real-world collision (functionally impossible) or the
file was hand-edited incorrectly. `forge doctor` flags as critical.

## Recovery from corruption

If `rejected-evolutions.yaml` becomes unreadable:

1. `forge evolve` refuses to run with the canonical lock-style message and
   suggests `forge raw restore-rejected-evolutions`.
2. The escape hatch offers two paths: restore from `.bak` (last apply
   snapshot) or seed an empty file (loses history — explicit confirmation).
3. There is **no** auto-recover. Permanent rejections are too important to
   silently lose.

## Concurrency

- **Append-only writer.** `forge evolve` is the only writer; retrospective
  agent only reads.
- **OS-level lock.** `flock` on the file during write.
- **Atomic write.** `.tmp` + `mv`.
- **Git is the backup.** The file is committed, so `git checkout` is the
  ultimate recovery.

## Out of scope for v1

- "Un-reject" UX. If the user changes their mind, they delete the entry
  manually with an editor + commit. This is rare and intentional friction.
- Time-based rejection expiry. A rejection is forever until manually removed.
- Cross-project rejection sharing (would need L4).
- Encrypted rejection log for confidential repos.

## Related schemas

- `.claude/proposed-evolutions.yaml` — the queue this file vetoes from —
  see `docs/schemas/proposed-evolutions.md`
- `.claude/memory/history.jsonl` — every rejection appends a line for audit
- `docs/ux/forge-evolve-roteiro.md` — the cinematic UX where rejections
  are produced
