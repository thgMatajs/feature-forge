# Command surface — locked at 13 (após Revisita Decisão 9 em 2026-06-05)

This document is the formal mapping between **every lifecycle operation** the
engine performs and **which of the 13 canonical subcommands** hosts it. It
exists because two locked decisions are load-bearing and easy to drift from:

- **Decision 9** — the command surface is fixed at **13 subcomandos** (após
  Revisita Decisão 9 em 2026-06-05, que adicionou `forge qa` como 13º comando).
- **Decision 10** — interaction is **100% conversational, sem flags**. Every
  parameter is collected via interactive prompt or menu inside one of the 13
  entrypoints.

Anything that *feels* like it needs a new command (card lifecycle, inventory
refresh, schema migration, graph rebuild) **must route through one of the 13
as an interactive menu choice or a sub-prompt** — never as a new top-level
verb, never as a flag.

If a future need does not encaixar em nenhum dos 13, the response is **not** a
new command. The response is: revisit decisions 9 + 10 explicitly via a
dedicated PR. Silent expansion is forbidden.

---

## The 13 subcomandos (canonical purpose)

| # | Command | Canonical purpose |
|---|---|---|
| 1 | `forge init` | Greenfield / brownfield install: scan project, propose cards, write `.claude/workflow-config.yaml`, seed memory L2/L3, build initial graph. |
| 2 | `forge plan` | Conduct planning-conductor pipeline (Waves A–E) to produce a full feature package with `readiness=ready`. |
| 3 | `forge implement` | Conduct execution-conductor pipeline (Plan Mode → Apply Mode → review → commit) for one task at a time. |
| 4 | `forge verify` | Read-only verification gate (task-scope, feature-scope, or inferred-scope). Runs hard-gate validators. |
| 5 | `forge status` | Read-only board: in-flight features, current task, last verify, pending evolutions, doctor freshness. |
| 6 | `forge doctor` | Read-only health check across config, cards, inventory, memory, graph, hooks, MCPs, i18n, connectivity. Interactive choice of scope (full / quick). |
| 7 | `forge reconfigure` | **Single entrypoint for any post-init mutation**: cards, paths, conventions, backend, ticketing, workflow, persona, memory policy, external-docs, hooks, inventory re-extract, graph rebuild. Diff → confirm → apply → auto-doctor. |
| 8 | `forge graph` | Read graph queries Q1–Q17 (similar features, blast-radius, orphans, reusable-helpers, duplications, KMP-migration candidates, near-duplicates, redundant-platform). Rebuild lives inside `forge reconfigure`. |
| 9 | `forge memory` | Inspect and manage memory across L1–L5. Interactive menu: inspect, forget, promote-from-L1, view-L2. Distillation is **automatic** (não tem comando manual). |
| 10 | `forge evolve` | Review and apply / reject proposed evolutions queued by retrospective-agent. |
| 11 | `forge undo` | Revert the last state-mutating action (task commit, reconfigure apply, init). Interactive prompt picks target if ambiguous — `last` is not a CLI suffix, é a opção default no menu. |
| 12 | `forge raw` | Escape hatch. Direct invocation of internal scripts (`migrator-N-to-M`, `verify-card`, `edit-config`, `rebuild-templates`). Documented per-script. **NÃO** é uma porta pra inventar novos comandos via raw — é a porta pra operações pontuais sem UX. |
| 13 | `forge qa` | Adversarial red-team gate. Audita artefatos do lifecycle inventando cenários hostis (4 attack vectors: spec-vs-spec, chaos, coverage, validator-claim), executa fixtures sintéticos em sandbox isolado, emite findings actionable em proposed-evolutions. Scope: feature / screen / task / paranoid (cross-feature). Trigger: manual + opt-in auto via `qa.auto-run-on-feature-done`. Verdict (BLOCK/FLAG/PASS) NÃO bloqueia retrospective nem commit — alinha Decisão 5 (code review final out-of-scope). |

---

## Mapeamento formal: operação → entrypoint

| Operação | Onde mora | Como o usuário chega lá |
|---|---|---|
| **Card: add** | `forge reconfigure` → menu `[ ] cards` → opção "adicionar card" | Interactive multi-select dentro de reconfigure. |
| **Card: remove** | `forge reconfigure` → menu `[ ] cards` → opção "remover card" | Resolver bloqueia se outro card ativo depende. |
| **Card: upgrade (from canonical)** | `forge reconfigure` → menu `[ ] cards` → opção "atualizar card do canonical" | Mostra diff; usuário aceita ou pula. |
| **Card: lock (trust local edit)** | `forge reconfigure` → menu `[ ] cards` → opção "travar edição local" | Marca `pinned: true` na config. |
| **Card: inspect** | `forge memory` ou `forge reconfigure` → menu cards → opção "inspecionar" | Read-only; mostra sha256, conflicts, contributions. |
| **Inventory: refresh design-system** | `forge reconfigure` → menu `[ ] paths` (ou diretamente "re-extrair inventory") → escolhe quais | Auto também via post-commit hook quando DS muda no disco. |
| **Inventory: refresh i18n** | Mesmo. Geralmente roda automático via hooks `i18n-changes`. | |
| **Inventory: refresh conventions** | Mesmo. Roda automático no `feature-done` retrospective. | |
| **Schema migration v(n) → v(n+1)** | `forge raw migrator-N-to-M` | `raw` é o escape hatch por design — migrations não têm UX cinemática própria. |
| **Memory: distill L2 quando ultrapassa max-size** | (a) Automático no `feature-done` retrospective. (b) Manual via `forge memory` → menu "distill L2" — usado quando `forge evolve` apply é pausado por overflow (ver `docs/design/07-discipline.md` §6). | Não existe `forge memory distill` como CLI standalone; só opção de menu interativo. |
| **Memory: inspect L1/L2/L3** | `forge memory` (interactive menu) | "Inspect" é uma das opções do menu. |
| **Memory: forget / esquecer item** | `forge memory` (interactive menu) | "Forget" é opção; pede confirmação. |
| **Memory: promote L1 → L2** | `forge evolve` aplica propostas que vieram de retrospective-agent | Promoção nunca é manual via comando — é review-and-apply. |
| **Graph: rebuild full** | `forge reconfigure` → opção "rebuild graph" (também dentro de menu paths quando paths mudam) | Hooks normalmente mantêm o graph quente; rebuild manual é raro. |
| **Graph: query** | `forge graph` | Read-only sempre. Q1–Q10 estruturais, Q11 reusable-helpers, Q12–Q17 reuse-intelligence (duplications, KMP-migration, near-duplicates, redundant-platform, TS-helpers), `r` para combined view. |
| **Reuse intelligence: list findings** | `forge graph` → opções 12–17 ou `r` (combined); `forge doctor` mostra counts agregados | Read-only. Findings são populated automaticamente em `forge init` Step 11.5 + `forge reconfigure → rebuild graph`. Apply review fica em `forge evolve`. |
| **Reuse intelligence: apply finding** | `forge evolve` → escolher proposta de tipo `{consolidate-duplicate-helper, promote-to-shared-helper, remove-redundant-platform-helper, review-near-duplicate-helper, kmp-migration-candidate, consolidate-ts-helper}` → "aplicar" | Apply materializa `feature-intake.md` stub em `non-product/refactor-{slug}/` + L1 status.json com `subtype=refactor` → próximo passo é `forge plan refactor-{slug}`. |
| **Doctor: full** | `forge doctor` → escolhe "full" no prompt inicial | |
| **Doctor: quick (pre-plan reflex)** | `forge doctor` → escolhe "quick" no prompt inicial | Sem flag `--quick`. Reconfigure dispara o equivalente quick automaticamente pós-apply. |
| **Preset change** | **Não suportado por reconfigure.** Criar branch dedicada, apagar `.claude/`, rodar `forge init` do zero. | Preset é decisão de bootstrap, não de reconfig. |
| **Resume reconfigure draft** | `forge reconfigure` (sem argumento) — auto-detecta `.claude/.reconfigure-draft.yaml` | Sem flag `--resume`. Just call reconfigure again. |
| **Resume plan / implement** | `forge plan {slug}` / `forge implement {slug}` — auto-resume do checkpoint | Sem flag `--resume`. |
| **Amend plan (mid-implement)** | Abortar o plan corrente (digitar `para`), rodar `forge plan {slug}` de novo — auto-resume parte do checkpoint mais recente, usuário corrige onde precisa. | Sem flag `--amend`. |
| **Undo last action** | `forge undo` (sem sufixo) | `last` aparece como opção default do menu interativo dentro de `forge undo`, não como argumento CLI. |
| **QA: rodar audit adversarial** | `forge qa` (direto) | `forge qa` pergunta scope conversacionalmente (feature / screen / task / paranoid). Sem flag. |
| **QA: ativar/desativar comando + auto-run** | `forge reconfigure` → menu `[ ] qa` | Toggle interativo. Sem flag. |
| **QA: aplicar findings** | `forge evolve` → escolher proposta tipo `qa-finding-{vector-slug}` → "aplicar" | Reusa Decisão 26 single-by-single. QA não tem `--apply` próprio. |
| **Ship / open PR** | Out-of-scope para v1. | Não tem `forge ship`. |

---

## Migration table — invented commands/flags → conversational equivalent

A tabela completa de tudo que foi inventado nos roteiros e o que vira agora:

| Invented (forbidden) | Replacement (canonical) |
|---|---|
| `forge card add X` | `forge reconfigure` → menu cards → "adicionar card" |
| `forge card remove X` | `forge reconfigure` → menu cards → "remover card" |
| `forge card upgrade X` | `forge reconfigure` → menu cards → "atualizar card do canonical" |
| `forge card upgrade X --from-canonical` | Same as above — `--from-canonical` é o default; sem flag. |
| `forge card lock X` | `forge reconfigure` → menu cards → "travar edição local" |
| `forge card list` | `forge memory` → menu → "inspecionar cards", ou `forge status`. |
| `forge inventory refresh X` | `forge reconfigure` → opção "re-extrair inventory: X" |
| `forge migrate --from N --to M` | `forge raw migrator-N-to-M` |
| `forge memory distill` (CLI standalone) | `forge memory` → menu "distill L2" (opção interativa). Auto também no `feature-done` retrospective. |
| `forge memory promote` | `forge evolve` (review-and-apply de propostas do retrospective-agent) |
| `forge ship` | Out-of-scope v1. Removido das referências. |
| `forge feature-done` | Automático ao verificar a última task. Sem comando próprio. |
| `forge plan --amend X` | Abortar plan (`para`), rodar `forge plan {slug}` de novo. Auto-resume + correção interativa. |
| `forge plan --finalize X` | Diálogo interativo dentro de `forge plan` (não flag). |
| `forge doctor --quick` | `forge doctor` → responder "quick" no prompt de scope. |
| `forge reconfigure --resume` | `forge reconfigure` (auto-detecta draft em `.claude/.reconfigure-draft.yaml`). |
| `forge reconfigure --new-preset=X` | **Não suportado.** Branch dedicada + `.claude/` apagado + `forge init` do zero. |
| `forge reconfigure --rebuild-graph` | `forge reconfigure` → opção "rebuild graph". |
| `forge reconfigure --rebuild-templates` | `forge reconfigure` → opção "rebuild templates" (ou auto após card mutation). |
| `forge init --force` | Não suportado como flag. Para re-init real, apagar `.claude/` manualmente e rodar `forge init` — o init detecta greenfield. |
| `forge init --new-preset=X` | Mesmo. Sem flag. Init pergunta preset interativamente. |
| `forge verify --feature {slug}` | `forge verify` pergunta interativamente se não detectar feature ativa única; ou usuário responde o slug quando perguntado. |
| `forge verify --feature .` | Mesmo. Sem flag — feature corrente é o default quando há uma única ativa. |
| `forge ingest --event post-edit` | Hooks fazem isso automático. Para forçar: `forge reconfigure` → opção "rebuild graph". |
| `forge undo last` | `forge undo` (e responder "last" / aceitar o default no menu interativo). |
| `forge graph rebuild` | `forge reconfigure` → opção "rebuild graph". |

---

## Por que essa disciplina importa

1. **Decisão 9 é load-bearing.** Inventar comandos quebra a expectativa de que
   o usuário precisa lembrar apenas 13 verbos. Cada novo subcomando dobra a
   superfície cognitiva.
2. **Decisão 10 é load-bearing.** Flags geram explosão combinatória de UX.
   `forge X --foo --bar` aceita ordem qualquer, valores fora de enum, conflitos
   entre flags. Conversational é restrito por design: a engine pergunta, o
   usuário responde dentro do conjunto oferecido.
3. **Auditabilidade.** Toda mutação passa por um dos 13 entrypoints, então
   `history.jsonl` de cada entrypoint cobre 100% das mutações. Sem comandos
   "laterais" gerando estado opaco.
4. **Portabilidade.** O dispatcher bash em `bin/forge` resolve apenas 13 verbos.
   Se a tabela cresce, o dispatcher cresce, a documentação cresce, e a skill
   deixa de ser absorvível em um clone.

---

## Hidden internal entrypoints

Some operations need an event-driven funnel that hooks call on the user's
behalf. These **are not part of the 13 user-facing commands**, are **never
typed manually**, and are **not documented as something the user invokes**.
They exist so that a single Python entrypoint can route any hook signal into
the right handler (graph delta, memory append, inventory refresh, proposal
queue).

| Hidden entrypoint | Who calls it | What it does | Why it's not in the 13 |
|---|---|---|---|
| `forge ingest --event <type> [payload]` | Claude Code hooks, git hooks, CI hooks, forge native dispatchers | Routes the event into `engine/ingest.py` which fans out to graph updater, memory updater, inventory updater, or proposal queue | Pure plumbing. No UX. User never types this; if a user runs it manually that's a bug in the hook layer, not a feature. |
| `forge graph detect-incremental <file>...` | `.claude/hooks/post-edit-detect-duplications.sh` (Claude Code post-edit hook) | Re-parses edited files, refreshes graph row, runs reuse-intelligence detection, prints inline any finding touching the edited files. Exit 0 always — never breaks the developer's edit. | Subcomando POSICIONAL de `forge graph` (não flag — argv[0]=="detect-incremental"). É um modo non-interactive do verbo já existente, não um novo verbo. Decisão 9 preservada. |

Adding a new hidden entrypoint requires the same scrutiny as adding a
13th command: explicit PR, decision update, documentation. The current
hidden surface is **two** entrypoints (`forge ingest`, `forge graph
detect-incremental`) — keep it that way.

Hidden entrypoints **must not** be advertised in `--help`, in cinematic
roteiros, or in user-facing error messages. They appear in schema docs only
as "this is how the hook delivers the signal," with a callout to this
section.

---

## Regra operacional

Quando um futuro contributor (humano ou agente) escrever roteiro, schema, ou
agent prompt que mencione `forge {algo-novo}` ou `forge X --flag`:

1. Procura na **migration table** acima. Se está listado, usa o replacement.
2. Se não está listado mas a operação é nova: encaixa em um dos 13 como menu
   ou prompt interativo.
3. Se não encaixa em nenhum dos 13: **para** e abre PR pra revisar decisões 9
   e 10 explicitamente. Nunca expande silenciosamente.

Mentor calmo é firme aqui: o que protege a UX do forge é a estabilidade da
superfície. 13 verbos, zero flags, zero exceções.
