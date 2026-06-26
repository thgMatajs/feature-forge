# Memory and graph lifecycle

How memory layers and the codebase graph stay fresh over time without manual
intervention.

> **`forge ingest` is the internal event-router invoked by hooks.** It is not
> part of the 12 user-facing commands and is not typed manually. Every
> reference below to `forge ingest --event ...` describes what a hook calls
> on the user's behalf, not something the user runs. See
> `docs/design/06-command-surface.md` § "Hidden internal entrypoints".

## Principle

Memory and graph **are never updated by hand**. Each update has an **event
trigger**, a **handler**, and a **clear destination**. The system is
event-driven, not polling-based.

```
[event] ──→ [handler]: forge ingest --event=X --payload=Y ──→ [destination]
```

Hooks are **thin shims** that fire `forge ingest`. All logic lives in `forge`.
This means: changing behavior = changing forge, not the hooks.

## The 4 hook surfaces

| Surface | Lives at | Fires when | Acceptable latency |
|---|---|---|---|
| **Claude Code hooks** | `.claude/settings.json` + `.claude/hooks/*.sh` | During Claude session (post-edit, post-tool, session-start) | < 200ms |
| **Git hooks** | `.git/hooks/` (or `lefthook`/`husky`) | Locally (pre-commit, post-commit, pre-push) | < 2s |
| **CI hooks** | `.github/workflows/feature-forge-ingest.yml` | Remotely (PR opened/merged, push to main) | < 30s |
| **forge native** | inside forge commands themselves | When user invokes `forge plan`, `forge implement`, etc. | immediate |

All 4 enter the same funnel:

```
hook (any surface)
        │
        ▼
forge ingest --event <type> --<payload>
        │
        ▼
event router (engine/ingest.py)
        │
        ├──→ graph updater   (SQLite writes)
        ├──→ memory updater  (YAML/JSONL writes)
        ├──→ inventory updater (re-scan if needed)
        └──→ proposal queue (self-evolution candidates)
```

## Canonical table: trigger → artifact → strategy

### Frequent events (file/commit)

| Event | Hook surface | Updates | Strategy |
|---|---|---|---|
| File saved | Claude Code `post-edit` | `graph.db` (incremental) | Reindex only the file + its reverse-deps |
| Feature artifact saved | Claude Code `post-edit` | `forge/state/lifecycle/{slug}/` | Update timestamp + summary |
| Pre-commit | Git `pre-commit` | nothing (read-only) | Validates gates, doesn't write |
| Local commit | Git `post-commit` | `graph.db` (feature↔commit edge) + `forge/state/lifecycle/{slug}/history.jsonl` | Append-only log |
| Push to remote | Git `pre-push` | nothing (read-only) | Final validation gate |

### Feature lifecycle events

| Event | Hook surface | Updates | Strategy |
|---|---|---|---|
| `forge plan` starts | forge native | `forge/state/lifecycle/{slug}/hypothesis.yaml`, `ambiguity-map.yaml` | Create dir, write initial state |
| Sub-agent dispatch | forge native | `forge/state/lifecycle/{slug}/dispatch-log.jsonl` | Append-only |
| Sub-agent returns | forge native | `forge/state/lifecycle/{slug}/dispatch-log.jsonl` + validates output | Append + validation result |
| Question answered | forge native | `forge/state/lifecycle/{slug}/elicitation.yaml` + `rationale-trace.yaml` | Update with confidence |
| Readiness=ready | forge native | `status.json`, proposes L1→L2 candidates | Writes `proposed-evolutions.yaml` |
| Task complete | forge native | `forge/state/lifecycle/{slug}/history.jsonl`, `graph.db` (task→commits edge) | Append + edges |
| Feature done | forge native | Triggers retrospective | Spawn retrospective-agent |
| Retrospective complete | forge native | `proposed-evolutions.yaml` + L2 candidates | Queue for `forge evolve` |

### Remote events (PR/CI)

| Event | Hook surface | Updates | Strategy |
|---|---|---|---|
| PR opened | GitHub Action | Comment on PR with plan summary + status | Read-only of `L1` + post |
| PR review with changes requested | GitHub Action | `L4` (cross-project pattern: "this reviewer asked X") | Anonymized, opt-in |
| PR merged to main | GitHub Action | Promote `L1` → `L2` candidates + close feature | Trigger remote retrospective |
| Push to main (no PR) | GitHub Action | Graph rebuild dirty flag | Next local `forge` runs incremental rebuild |

### Periodic events (cron/manual)

| Event | Trigger | Updates | Strategy |
|---|---|---|---|
| `forge doctor` | manual / weekly cron | `workflow-config.yaml.doctor` | Health checks + status |
| L2 distillation | when `L2` > max-size | `L2-project.yaml` | `memory-distiller` agent compresses |
| Stale external docs cache | TTL expired | `inventory/external-docs-cache/` | Re-fetch via Context7 |
| Cards snapshot drift | weekly | compare sha256 | Suggest rodar `forge reconfigure` e escolher "verificar updates de cards do canonical" no menu |

## Dataflow per artifact

### `graph.db` (SQLite)

```
Trigger: post-edit file foo.kt
   │
   ▼
hook calls: forge ingest --event post-edit --file foo.kt
   │
   ▼
forge engine/graph/incremental.py
   │
   ├──→ DELETE FROM symbols WHERE file_id = (foo.kt)
   ├──→ DELETE FROM imports WHERE from_file = (foo.kt)
   ├──→ Parse foo.kt → extract symbols, imports
   ├──→ INSERT new rows
   └──→ UPDATE files.last_modified
   
Latency: 50-200ms per file
Concurrency: SQLite WAL mode + write lock
```

**Principle:** never rebuild fully in a hook. Always delta.

There is no `forge graph rebuild` subcommand — full rebuild lives only inside
`forge init` ou via menu de `forge reconfigure` → "rebuild do graph".

### `forge/state/lifecycle/{slug}/`

```
Trigger: planning-conductor writes a decision
   │
   ▼
forge native (doesn't come from hook, comes from inside agent)
   │
   ├──→ rationale-trace.yaml: append to `decisions:` list
   ├──→ elicitation.yaml: update ambiguity counter
   └──→ history.jsonl: append event line
   
Concurrency: each feature has its own lifecycle dir, no collision
Disposal: when feature.status == archived, compresses lifecycle dir → 1 summary file
```

L1 is the **feature logbook**. Everything that happened is recorded. Never
edited, only appended.

### `memory/L2-project.yaml`

```
Trigger 1: forge feature done
   │
   ▼
Retrospective agent compares L1 of just-finished feature with current L2
   │
   ├──→ Detects repeated patterns (≥ 3 features do X)
   ├──→ Detects consolidated new convention
   ├──→ Detects relevant FND (cross-feature finding)
   │
   └──→ Proposes entries in proposed-evolutions.yaml
            ↓
        User runs `forge evolve` when ready
            ↓
        Approve → merge into L2-project.yaml
        Reject → marked rejected (won't ask again)

Trigger 2: distillation (when L2 > max-size)
   │
   ▼
memory-distiller agent
   │
   ├──→ Reads full L2
   ├──→ Identifies redundant / superseded entries
   ├──→ Compresses keeping what killed real ambiguity
   └──→ Rewrites L2 (with backup at .claude/memory/L2-project.yaml.bak)
```

**Principle:** L2 is never edited by automatic hook. Always passes through
queue + approval. Otherwise becomes garbage dump.

### `memory/L3-user-global/`

```
Trigger: none internal
Permission: forge is READ-ONLY here
   │
   ▼
L3 is maintained by ~/.claude/memory/ (existing auto-memory system)
   │
   └──→ forge READS to use as context, NEVER writes
```

**Principle:** forge respects separation. Who writes to L3 is Claude's
auto-memory. Forge only consumes.

### `inventory/*.yaml`

```
Trigger 1: forge init
   │
   ▼
Full scan for the first time

Trigger 2: forge reconfigure
   │
   ▼
Re-scan with diff before applying

Trigger 3: hook detected significant structural change
   │
   ▼
e.g., new Meo* component committed
   │
   ▼
forge ingest --event post-commit detects this
   │
   ▼
Updates inventory/design-system.yaml incremental + suggests git commit
```

**Principle:** inventory is fact about the repo. Reflects the repo.
Change in repo → change in inventory. But only structures that enter the
formal graph trigger updates — not every edit.

## The "common language" — `forge ingest`

All memory/graph writes go through:

```bash
forge ingest --event <EVENT_TYPE> [payload args...]
```

Events supported in v1:

```text
post-edit         --file <path>
post-write        --file <path> --feature <slug>
pre-commit        --files <paths>           (read-only check)
post-commit       --sha <hash>
pre-push          --branch <name>           (read-only check)
pr-opened         --pr <num> --branch <name>
pr-reviewed       --pr <num> --decision <approve|changes|comment>
pr-merged         --pr <num> --sha <hash>
forge-plan-start  --feature <slug>
forge-plan-done   --feature <slug>
task-start        --feature <slug> --task <id>
task-done         --feature <slug> --task <id>
feature-done      --feature <slug>
retrospective     --feature <slug>
doctor-run        (no payload)
distill-l2        (no payload)
```

Adding new event = add handler in `engine/ingest.py`. Hooks remain trivial:

```bash
#!/usr/bin/env bash
# .claude/hooks/post-edit-codebase-graph.sh
exec forge ingest --event post-edit --file "$1"
```

## Concurrency and integrity

Points where things go wrong without care:

| Risk | Mitigation |
|---|---|
| Two agents writing forge/state/lifecycle/{slug}/history.jsonl concurrently | append-only + OS-level flock per file |
| Graph incremental rebuild fails mid-flight | SQLite transaction with BEGIN/COMMIT/ROLLBACK |
| Memory L2 corrupted by partial scribble | write to `.tmp` + atomic `mv` |
| Hook locks up Claude Code (latency) | 5s timeout + silent failure (log warn, continue session) |
| CI hook takes too long | CI hook is informational, not blocking |
| Schema-version drift across machines | doctor checks at session entry |
| Graph desynchronized after pull of old branch | session-start hook detects divergence + suggests rebuild |

## Privacy

Some updates **may leak context externally**. Map:

| Update | Leaks externally? | Controlled by |
|---|---|---|
| Local graph (SQLite) | No | — |
| Local L1/L2/L3 | No | — |
| Jira post-back (comment on PR) | Yes (plan summary) | `ticketing.post-back.require-confirmation: true` |
| Context7 query | Yes (lib/framework names, NOT the feature) | `external-docs.privacy-mode: true` disables |
| GitHub Action posting comment | Yes (summary) | opt-in feature in CI workflow |
| L4 cross-project distill | Yes (anonymized) | explicit opt-in in user-global config |

`privacy-mode: true` in `workflow-config.yaml` disables ALL flows that leak
something. Useful for confidential repos.

## Performance — each hook's budget

| Hook | Budget | Strategy if exceeded |
|---|---|---|
| post-edit (Claude Code) | 200ms | Skip + log warning, schedule re-sync |
| pre-commit (git) | 2s | Block commit with clear message |
| post-commit (git) | sync 500ms / async 5s | Async background, doesn't block |
| pre-push | 5s | Block push |
| CI on PR open | 60s | Fails check, but not blocking for merge |
| Periodic distill | 5min | Runs in background, in idle hours |

Heavy hooks (large graph rebuild, distillation) **never run synchronously**
in interactive actions. Go to background or to next session.

## Concretely — v1 hook list

```
.claude/hooks/                              (Claude Code)
  post-edit-codebase-graph.sh             ──► forge ingest --event post-edit
  post-write-feature-artifact.sh          ──► forge ingest --event post-write
  pre-commit-feature-forge.sh             ──► forge ingest --event pre-commit
  post-subagent-validate.sh               ──► forge ingest --event subagent-done
  session-start-drift-check.sh            ──► forge ingest --event doctor-quick-check (internal event-router runs the quick checks without surfacing a prompt; the cinematic `forge doctor` command remains the only user-facing entrypoint for the full health check)

.git/hooks/  (or lefthook.yml)             (git)
  pre-commit                              ──► forge ingest --event pre-commit
  post-commit                             ──► forge ingest --event post-commit
  pre-push                                ──► forge ingest --event pre-push

.github/workflows/                          (CI)
  feature-forge-pr-ingest.yml             ──► forge ingest --event pr-opened
                                              forge ingest --event pr-merged
```

Total: **9 thin hooks**. All logic in `engine/ingest.py`.

## Complete feedback cycle (visual)

```
                     ┌──────────────────────────┐
                     │   USER ACTIVITY          │
                     │   (edit, commit, PR)     │
                     └──────────────┬───────────┘
                                    │
                ┌───────────────────┼───────────────────┐
                ▼                   ▼                   ▼
        ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
        │  Claude hook │   │   git hook   │   │   CI hook    │
        └──────┬───────┘   └──────┬───────┘   └──────┬───────┘
                └──────────┬──────┴──────────┬──────┘
                           ▼                 ▼
                  ┌────────────────────────────────┐
                  │  forge ingest --event X        │
                  │  (single entry point)          │
                  └────────────────┬───────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
      ┌──────────────┐   ┌──────────────────┐   ┌──────────────────┐
      │  graph.db    │   │  forge/state/    │   │ proposed-        │
      │  (SQLite)    │   │  lifecycle + L2  │   │ evolutions.yaml  │
      └──────┬───────┘   └──────────┬───────┘   └──────────┬───────┘
             │                      │                      │
             │                      │                      ▼
             │                      │              ┌───────────────┐
             │                      │              │ forge evolve  │
             │                      │              │ (user review) │
             │                      │              └───────┬───────┘
             │                      │                      │
             ▼                      ▼                      ▼
   ┌─────────────────────────────────────────────────────────────┐
   │            CONTEXT FOR NEXT FORGE RUN                       │
   │   graph queries + memory layers + approved evolutions       │
   └─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                  ┌───────────────────────┐
                  │  forge plan / forge   │ ◀── user runs
                  │  implement (next)     │     with more context
                  └───────────────────────┘
```

## Out of scope for v1

Deferred to keep v1 lean:

| Deferred | Why |
|---|---|
| Real-time multi-user sync of memory | Single-user assumed in v1 |
| Slack/Teams notifications of events | Adjacent, not core |
| User-customizable webhooks | Power-user feature for later |
| Memory L4 cross-project automation | Needs >1 project to test |
| Time-series analytics over history | Useful but not blocking |
| **MCP polling for external-dep resolution** (Gap 8 / discipline §9) | v1.0 ships manual unblock via `forge reconfigure`. v1.1+ will add `forge ingest --event external-dep-resolved` (hidden entrypoint) hooked into Jira/Linear webhooks. v1.0 keeps human-in-the-loop for the trust gate — a misfired webhook would lie to `forge implement` about safety to proceed. |

## Direct answer to "how is memory and graph fed?"

> "será criado um hook para o claude quando tiver commit ou abertura de pr
> roda uma análise e alimenta onde tem que ser?"

**Yes, exactly that — but on 3 levels:**

1. **Claude hook** (`.claude/hooks/post-edit-codebase-graph.sh`) — each edit
   updates the graph incrementally. Fast (< 200ms).

2. **Git hook** (`.git/hooks/post-commit`) — each local commit updates
   history + feature↔commit edges. Medium (< 2s).

3. **CI hook** (`.github/workflows/feature-forge-pr-ingest.yml`) — each PR
   opened/merged updates feature state + posts summary. Slow but
   non-blocking (< 30s).

---

## Reuse intelligence dataflow (Gap 18 expandido)

`reuse_findings` é o 5º artifact materializado dessa pipeline. Diferente
dos outros, ele é **derived state** — não recebe input direto do hook,
é re-computado a partir do graph (`symbols`, `files`, `module_deps`) toda
vez que o graph muda.

```
source files  ──build_full──>  symbols + files +  ──detect_all_*──>  reuse_findings
(.kt/.swift/                   module_deps           (6 queries)      + locations
 .ts/.tsx)
                                                                            │
                                                                            │ queue_proposals
                                                                            ▼
                                                              proposed-evolutions.yaml
                                                                            │
                                                                            │ forge evolve apply
                                                                            ▼
                                              non-product/refactor-{slug}/feature-intake.md
                                                + L1 status.json subtype=refactor
                                                                            │
                                                                            │ forge plan refactor-{slug}
                                                                            ▼
                                                       refactor Wave A→E (Gap 2 flow)
```

**6 trigger points alimentam essa pipeline:**

| Trigger | O quê alimenta | Latency |
|---|---|---|
| `forge init` Step 11.5 | Inicial — todo o backlog do projeto vira findings | depende do tamanho (~10s em MeoBonsai 8k LOC) |
| `forge reconfigure` → graph rebuild | Refresh — qualquer mudança no codebase reflete | mesma do rebuild |
| Post-edit hook (`.claude/hooks/post-edit-detect-duplications.sh`) | Incremental — só pra arquivo editado, surface inline | < 200ms |
| `apply_proposal_to_l2(reuse-kind)` | Out — escreve intake + L1 status (NÃO mexe em código) | < 50ms |
| `apply_proposal_to_l2(reject)` | Out — fingerprint vai pra rejected-evolutions; futuros scans skipam | < 50ms |
| `forge plan refactor-{slug}` | Out — lê L1 status subtype=refactor, dispatcha Gap 2 flow | Wave A skipada |

**Idempotência por fingerprint SHA-256:**

```
fingerprint = sha256(category | receiver_type | name | signature | body_hash | <category-specific extras>)
```

Mesmo grupo (e.g., 3 duplicações de `FirebaseAnalytics.logEventSafely` em
3 módulos) tem fingerprint estável across rebuilds. Adicionar 4ª duplicação
NÃO muda fingerprint — payload da proposta refresca, entry NÃO duplica.

Categorias e suas regras de fingerprint estão em
`docs/schemas/graph.md § Reuse Intelligence (schema v2)`.

**Disciplina §4 (deterministic context) preservada:** apply nunca toca em
código. Materializa intake stub + L1 status, e delega refactor real para o
fluxo Gap 2 (`forge plan refactor-{slug}` → Wave A→E refactor track).

**Disciplina §5 (rejection veto) preservada:** rejeitar uma proposta
persiste o fingerprint em `rejected-evolutions.yaml`. Re-rodar `forge init`
ou `forge reconfigure` NÃO re-propõe o mesmo grupo.

---

All call the same entry point `forge ingest --event <X>`. Changing what each
event does = changing 1 Python file, not 9 hooks.
