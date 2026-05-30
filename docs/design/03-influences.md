# Influences and pattern absorption

> Padrões absorbed em 2026-05-29 durante v1; nenhuma dep runtime nas skills de origem (Decision 22 locked).

feature-forge has zero runtime dependencies on other skills, but absorbs
proven patterns. This document explains what we took, from where, and how.

See also: `INFLUENCES.md` (root) for the short attribution.

## The full table

| Pattern | Origin | Where it lives in feature-forge | Adaptation |
|---|---|---|---|
| State machine file-driven | gsd-* | engine state model | Feature-scoped instead of phase-scoped |
| Phase pipeline with gates | gsd-* | planning-conductor strategy | 6 fixed phases instead of free phases |
| Goal-backward verification | gsd-verifier | readiness-reviewer + verify-task | Built into readiness review, not separate skill |
| Codebase knowledge graph | gsd-graphify | engine/graph (SQLite) | SQLite v1 (Kuzu deferred) |
| Parallel sub-agent dispatch | gsd + superpowers | planning-conductor Phase 4 | Waves A–E with declared dependencies |
| Brainstorming Socratic | superpowers:brainstorming | embedded in planning-conductor | Mentor calmo voice, not socratic challenge |
| TDD-first discipline | superpowers:tdd | opt-in card `tdd-discipline` | Opt-in, not default |
| Systematic debugging | superpowers:debugging | future `forge debug` mode | Not in v1 |
| Verification before completion | superpowers | hard gate in verify-task | Enforced by validator + hook |
| Plan-as-document | superpowers:writing-plans | feature package artifacts | 14–16 specific docs |
| Worktree isolation | superpowers + git | future opt-in card `worktree-per-task` | Not in v1 |
| Retrospective + extract-learnings | gsd | retrospective-agent on feature done | Triggered automatically at done |
| Cross-AI peer review | gsd-review | future opt-in card `peer-review-external` | Not in v1 |

## Why no dependency at runtime

1. **Different lifecycle.** feature-forge will install in many projects;
   pulling transitive dependencies multiplies install footprint and risk.

2. **Different evolution speeds.** Upstream skills change on their cadence;
   feature-forge needs frozen behavior per project (snapshot model).

3. **Different scope.** feature-forge is mobile-specific; some upstream
   skills are general-purpose.

4. **Different distribution.** feature-forge lives in `~/Documents/`, gets
   snapshot-copied to projects. No package manager interaction.

## What "absorb" means concretely

For each pattern absorbed:

1. Read the original implementation.
2. Extract the principle (not the code).
3. Re-implement under feature-forge's namespace, in our chosen language and
   format.
4. Document the influence in this file.
5. No `requires:` reference upstream.

## Three examples

### State machine file-driven (gsd-*)

**Upstream:** `status.json`, `history.jsonl`, `checkpoints/` per phase.

**Absorbed:** same structure under `docs/.../features/{slug}/`.

**Adaptation:** feature-scoped instead of phase-scoped; simpler schema; no
phase-level coordination since features are the unit.

### Brainstorming Socratic (superpowers:brainstorming)

**Upstream:** a dedicated skill that explores intent → requirements → design.

**Absorbed:** the same elicitation pattern, embedded as Phase 2 (Ambiguity
Map) + Phase 3 (Elicit) of planning-conductor. Not a separate skill.

**Adaptation:** mentor-calmo voice instead of socratic challenge. The agent
asks "you said X — could that mean A or B?" rather than "what do you really
mean by X?"

### Verification before completion (superpowers)

**Upstream:** a discipline of "must run cmd, must see output, then claim."

**Absorbed:** hardcoded as a gate in verify-task phase. Cannot be skipped.

**Adaptation:** enforced by validator + hook, not by agent self-discipline.
The hook actually checks; the agent doesn't merely promise.

## Patterns intentionally not absorbed

| Skipped pattern | Why |
|---|---|
| superpowers:using-git-worktrees as default | Adds complexity; opt-in card for power users |
| gsd-debug session-manager checkpoint loop | Different mental model (debug vs build); future skill |
| superpowers:dispatching-parallel-agents as a separate skill | We do parallelism, but inside planning-conductor |
| gsd-thread persistent context | Memory layers replace this with finer scopes |
| gsd-graphify as a separate skill | Graph is core, not auxiliary; built in |

## Re-attribution policy

If a future contributor adds a pattern from another skill or system, they
must:

1. Add a row to the table above
2. Add the rationale to "What absorb means" if novel
3. Reference the source in `INFLUENCES.md`
4. Not add `requires:` to any manifest
