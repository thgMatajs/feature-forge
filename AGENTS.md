<!-- >>> mem >>> -->
## Project memory (`mem`)

Persistent, searchable memory shared by all devs. Vendored at `.claude/bin/mem` (zero deps).

CONSULT (read) — before acting:
- starting a task/feature -> `mem find "<area/tech>"` for conventions & past gotchas
- hit an error / unexpected behavior -> `mem find "<symptom>"` before debugging from scratch
- a choice that smells like "we decided this before" -> `mem find "<topic>" --type decision`

CAPTURE (write) — when it happens:
- the user corrects you ("not that" / "redo" / "wrong") -> `add --type feedback`
- you fix the SAME thing twice, or a fix is a reusable rule -> `add --type feedback`
- a decision is made with a rationale (chose A over B; accept/defer) -> `add --type decision`
- a non-obvious bug is solved (hidden root cause) -> `add --type episode`
- significant work ends -> `mem session "<summary>"` + run the `mem-consolidate` skill to propose inbox candidates
- unsure / mid-task? queue it: `mem inbox add ...` then triage later via `mem evolve`

REPORT (the mem tool itself) — hit a bug or rough edge IN mem (bad injection, crash, missing capability)?
Don't silently work around it: `mem issue --title "<short>" --kind bug` (use the `mem-report` skill to draft a full report). mem only improves if friction is filed.

Cut rule: would a future session or another dev rediscover this and waste time? -> record it.
Only matters to finishing the current task? -> skip it.

- `.claude/bin/mem find "<terms>"`  -> ranked search, titles only
- `.claude/bin/mem get <id>`        -> full body of one memory
- `.claude/bin/mem add --type <t> -i <1-5> -t "<title>" --tags a,b "<body>"`
- `.claude/bin/mem session "<summary>"` -> record a session at the end of work

Types: feedback / decision / episode / reference. If `find` is weak, retry with synonyms.
Never paste secrets; `add` blocks them. Resume past work with the `mem-resume` skill.
Recipes: standup `mem find "" --type session --since 7d`; forensics `mem find "<symptom>" --type session --all`.
<!-- <<< mem <<< -->
