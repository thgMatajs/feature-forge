# {{auditor_name}} — qa auditor (card extension)

> **Inherits qa-conductor overlay** (mentor calmo + staff QA red-team).
> Definido em `agents/qa-conductor.md`.

## Phase

{{phase}}   <!-- static | generative -->

## Provided by card

`{{card_name}}`

## What it audits

{{audit_focus}}

## Inputs lidos

- {{input_paths}}

## Outputs

- `findings/{{auditor_slug}}.json` — findings draft (Decisão 25 fingerprint)
- (opcional) `fixtures/{{auditor_slug}}-*.yaml` se phase=generative

## Heurísticas adversariais

{{heuristics}}

## Schema do finding emitido

Mesmo `qa-finding` canônico — `vector: "{{auditor_name}}"`.

## Cross-refs

- Conductor: `agents/qa-conductor.md`
- Schema: `docs/schemas/qa-finding.md`
- Card extension policy: `docs/schemas/qa-extensions.md`
