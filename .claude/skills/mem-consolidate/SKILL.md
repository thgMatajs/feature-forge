---
name: mem-consolidate
description: At the end of significant work, propose durable memory candidates for the project's mem inbox by delegating extraction to a subagent. Use when work wrapped up (commit/PR/decision) or when the Stop hook asks for consolidation.
---

# Consolidating a session into mem inbox candidates

Run this at the end of significant work (or when nudged by the mem Stop hook).
You orchestrate; a subagent does the extraction under a tight contract.

1. Dispatch a subagent (Haiku-class model, e.g. claude-haiku-4-5) with this contract:
   - SCOPE: read the recent session/transcript. Extract **0-5** durable memory
     candidates (types: feedback / decision / episode / reference). **Never invent** —
     a trivial session yields **0**. Skip anything only relevant to the finished task.
   - OUTPUT: for each candidate, run
     `.claude/bin/mem inbox add --origin haiku --type <t> -i <1-5> -t "<title>" --tags a,b "<body>"`.
     Nothing goes straight to the store — the inbox is the only sink; triage (`mem evolve`)
     promotes to a real memory via PR (anti-poisoning gate).
2. Report the count of candidates queued. Do not promote them yourself.

This keeps `mem` LLM-free: the model lives in the subagent, never in the CLI.

<!-- mem-managed sha256:fd767026c6927b8ccb4dbb26d013eec0f2b3a7e3e3b5c598decb4c7ce4a2c42d -->
