---
name: mem-resume
description: Resume interrupted or prior work. Reads the local session checkpoint first (deterministic), then optionally narrates the previous session via a subagent. Use when starting work, asked "where were we", or after an interrupted session.
---

# Resuming work with `mem`

The SessionStart hook already injects a deterministic resume banner when the prior session
was interrupted (its checkpoint was left `open`). That banner carries the branch, last prompt,
uncommitted-file count and head — so the basic "where was I" is already in context. Use this
skill to go deeper.

1. Read the deterministic checkpoint (one call, no extra digging):
   `.claude/bin/mem checkpoint` → session_id, branch, head, last_prompt, status, updated_at.
   Cross-check the on-disk state with `git status --porcelain` and `git log -1`.
2. For a narrated reconstruction (objective / progress / blocker / single best next step),
   dispatch a subagent (Haiku-class, e.g. claude-haiku-4-5) under this contract:
   - SCOPE: read the most recent prior transcript for this cwd
     (`~/.claude/projects/<cwd-with-/-as->-->/`, newest file ≠ the current session).
     Read-only. **Never invent** — if the transcript is thin, say so plainly.
   - OUTPUT: a short on-screen briefing. Nothing is written to the mem acervo.
3. Also surface durable handoffs, if any: `.claude/bin/mem find "" --type session --since 14d`
   then `.claude/bin/mem get <id>` (prefer those whose `git_meta.branch` matches the branch).

Record a durable handoff at the end of significant work:
`.claude/bin/mem session "<objective; what changed; handoff pending>"`

<!-- mem-managed sha256:35a1aa17485c3f9031c1cd6756351d158b6ab8662585abd8fe89e49549dfa1eb -->
