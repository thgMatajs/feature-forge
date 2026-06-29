---
name: mem-report
description: File a bug or feature request against the mem tool itself when you hit a problem in mem (bad injection, crash, missing capability) instead of silently working around it. Use when mem misbehaves and the friction is worth reporting upstream.
---

# Reporting a bug or rough edge in `mem` itself

When `mem` itself gets in your way (a bad/oversized injection, a crash, a missing
capability) — don't just work around it. File it upstream so `mem` improves.
You orchestrate; a subagent drafts the report under a tight contract.

1. Dispatch a subagent (Haiku-class model, e.g. claude-haiku-4-5) with this contract:
   - SCOPE: read the context of the mem problem you just hit. Draft a **title** (short,
     specific) and a **body**. **Never invent** facts.
   - The `--body` is injected verbatim as the **"O que aconteceu"** section only. Do **NOT**
     put `##` section headers (`## O que aconteceu`, `## Comportamento esperado`, etc.) in the
     body — the CLI template supplies all headers, and adding your own duplicates them. Write a
     self-contained account in plain prose/markdown: what happened, what you expected, and the
     minimal repro, woven into that one section. The CLI auto-fills **Ambiente** and leaves
     "Comportamento esperado" / "Como reproduzir" as placeholders for the human to refine.
   - OUTPUT: run `.claude/bin/mem issue --title "<title>" --body "<body>" --kind bug`
     (use `--kind feature` or `--kind rough-edge` when it fits). Run it with `--dry-run`
     first to review the composed report, then drop `--dry-run` to create the issue.
2. Report the issue URL (or, if `gh` is offline, the ready-made title+body printed for
   manual filing).

The `mem issue` CLI is fully deterministic and LLM-free (R4): it composes a template,
auto-collects the environment, applies the secret filter (R6), and calls `gh`. The model
lives only here in this skill, never in the CLI.

<!-- mem-managed sha256:2e2c1342c53596d516e52d67ce218c73257c8578ca510155cbd75badad23cda2 -->
