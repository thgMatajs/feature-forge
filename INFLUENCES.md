# Influences

> Padrões absorbed em 2026-05-29 durante v1; nenhuma dep runtime nas skills de origem (Decision 22 locked).
> Versão expandida com rationale e exemplos: [`docs/design/03-influences.md`](docs/design/03-influences.md).

feature-forge absorbs patterns from existing skills but has no runtime
dependency on them. The essence is re-implemented under feature-forge's own
namespace.

| Pattern | Origin | Where it lives in feature-forge |
|---|---|---|
| State machine file-driven (status, history, checkpoints) | gsd-* | engine state model |
| Phase pipeline with artifacts and gates | gsd-* | docs/schemas + planning-conductor strategy |
| Goal-backward verification | gsd-verifier | readiness-reviewer + verify-task gates |
| Codebase knowledge graph | gsd-graphify | engine/graph (SQLite) |
| Parallel sub-agent dispatch with context-pack | gsd + superpowers | planning-conductor Phase 4 |
| Brainstorming Socratic elicitation | superpowers:brainstorming | embedded in planning-conductor |
| TDD-first discipline | superpowers:tdd | opt-in card `tdd-discipline` |
| Systematic debugging | superpowers:debugging | future `forge debug` mode |
| Verification before completion | superpowers | hard gate in verify-task |
| Plan-as-document | superpowers:writing-plans | feature package artifacts |
| Worktree isolation | superpowers + git | future opt-in card `worktree-per-task` |
| Retrospective + extract-learnings | gsd | workflow-retrospective on feature done |
| Cross-AI peer review | gsd-review | future opt-in card `peer-review-external` |

These are inspirations and patterns, not dependencies. No `requires:` in any
manifest references the above skills. See `docs/design/03-influences.md` for
the deeper rationale.
