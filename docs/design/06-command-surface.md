# Command surface — locked at 14 (após Revisita Decisão 9 em 2026-06-17)

This document is the formal mapping between **every lifecycle operation** the
engine performs and **which of the 14 canonical subcommands** hosts it. It
exists because two locked decisions are load-bearing and easy to drift from:

- **Decision 9** — the command surface is fixed at **14 subcomandos** (após
  Revisita Decisão 9 em 2026-06-17, que adicionou `forge upgrade` como 14º comando;
  Revisita anterior em 2026-06-05 adicionou `forge qa` como 13º comando).
- **Decision 10 (revisitada em 2026-06-18 — row 32)** — interaction is
  **conversational human-first by default**. Cada parâmetro de domínio é
  coletado via prompt/menu interativo dentro de um dos 14 entrypoints. **Carve-out
  machine-readable opt-in:** os read-commands (`status`/`doctor`/`verify`/`memory`/`graph`)
  aceitam as meta-flags `--json` (e `forge --help --json`) e honram a env
  `FORGE_OUTPUT=json` — emitem JSON puro em stdout pra consumo por máquina (CI,
  hosts agentic). Esse carve-out é **meta-flags only**: flags de comportamento de
  domínio continuam proibidas. Comandos interativos (`plan`/`implement`/`init`/
  `reconfigure`/`evolve`/`qa`/`undo`/`raw`) IGNORAM `--json`/`FORGE_OUTPUT=json` —
  o intent protocol (marker `<FORGE_INTENT/>` + exit-2) e a UX cinematográfica
  ficam intactos. Ver §"Manifesto + meta-flags (Decisão 10 revisitada)" abaixo.

Anything that *feels* like it needs a new command (card lifecycle, inventory
refresh, schema migration, graph rebuild) **must route through one of the 14
as an interactive menu choice or a sub-prompt** — never as a new top-level
verb, never as a domain-behaviour flag (meta-flags `--json`/`--help --json`
pros read-commands são o único carve-out — Decisão 10 revisitada).

If a future need does not encaixar em nenhum dos 14, the response is **not** a
new command. The response is: revisit decisions 9 + 10 explicitly via a
dedicated PR. Silent expansion is forbidden.

---

## The 14 subcomandos (canonical purpose)

| # | Command | Canonical purpose |
|---|---|---|
| 1 | `forge init` | Greenfield / brownfield install: scan project, propose cards, write `.claude/workflow-config.yaml`, seed memory L2/L3, build initial graph. Após o vendoring do mem, executa `_reduce_rules`: lê `.claude/rules/` + `CLAUDE.md`, classifica cada fragmento em Tier-0 (invariante always-on) vs Tier-1 (detalhe recuperável) via intent `classify` fulfillado pelo host-LLM, exibe proposta em 3-caminhos (G1 aceitar / G2 ajustar / G3 pular), e ao aceitar move Tier-1 pro mem (com `.bak`, apply ordenado). Greenfield sem rules ou sentinel `.rules-reduced` presente pulam o passo. `TtyAdapter` (host sem LLM) pula com aviso. |
| 2 | `forge plan` | Conduct planning-conductor pipeline (Waves A–E) to produce a full feature package with `readiness=ready`. Aceita `<ticket\|frase\|slug>` como argv **posicional** (Decisão 10 preservada — argv, não flag): slug válido entra direto; ticket-id (ex.: `IN-37234`) ou frase livre são derivados pra slug kebab-case determinístico, confirmados conversacionalmente, e o texto cru é semeado no `feature-intake.md`. Screenshot/mockup entra conversacionalmente na source-inquiry (sem flag). Subtype-aware (product / refactor / bugfix / spike / chore): no bugfix detecta o ticket (ex: IN-37234) e exige regression-test-first; no refactor entra com contrato no-behavior-change. W-ROUTE 6c: antes de redigir os artefatos da Wave A, consulta `mem find` por gotchas/convenções relevantes ao slug da feature. O resultado é injetado no context-pack do subagente de planejamento via token `{{mem_context_hint}}`. Degrade soft: mem ausente → token vazio, sem crash. |
| 3 | `forge implement` | Conduct execution-conductor pipeline (Plan Mode → Apply Mode → review → commit) for one task at a time. W-ROUTE 6c: em Plan Mode, exibe memória relevante ao tema da task antes do prompt de confirmação. O host vê o hint educacional antes de aprovar o plano. Degrade soft: mem ausente → hint omitido. |
| 4 | `forge verify` | Verification gate (task-scope, feature-scope, or inferred-scope). Não muta código nem artefatos, mas é um **observador com side-effects de L1** (C-34d): transita o status pra `verifying` enquanto roda + dá append no `verify-log.jsonl`. Runs hard-gate validators numa cascade fail-fast (para no primeiro erro duro). Inclui os gates fortes: `check_cyclomatic_complexity` (multi-lang), `check_secrets` (gitleaks/trufflehog), `check_no_behavior_change` (refactor) — cada gate forte com override-justify auditável no commit body + bypass de emergência logado em `.claude/state/`. W-ROUTE 6c: antes do cascade de validators, exibe hint educacional com memória relevante ao scope. Só em modo interativo (omitido em --json). O hint NÃO é passado pra validators — determinismo preservado. **Gates de execução externa (Decisão 33, Tema 6, Fase 1 Track A):** o `verify` agora roda gates nativos junto da cascade de validators. No Nível 1: **ktlint** via `./gradlew ktlintCheck` (modo check, read-only; só em stacks `android`/`kmp`) e **build-only** via `./gradlew assembleDebug` (android/kmp) ou `xcodebuild build` (ios), conforme `platforms.active`; web sem build-only no Nível 1. Violação é informativa (`warn`, exit 0) por default; opt-in `fail-on-violation: true` por gate sobe pra `fail`. Tool ausente → `skipped`; timeout → `degraded`. Config em `docs/schemas/forge-config.md §native-gates`. O build escreve artefatos (esperado — o forge não versiona/limpa). |
| 5 | `forge status` | Read-only board: in-flight features, current task, last verify, pending evolutions, doctor freshness. |
| 6 | `forge doctor` | Read-only health check across config, cards, inventory, memory, graph, hooks, MCPs, i18n, connectivity, mem. Categoria `mem` (scope `full`): verifica vendorização em `.claude/bin/mem`, saúde via `mem doctor` e drift do pin vendorizado vs asset. Interactive choice of scope (full / quick). |
| 7 | `forge reconfigure` | **Single entrypoint for any post-init mutation**: cards, paths, conventions, backend, ticketing, workflow, persona, memory policy, external-docs, hooks, inventory re-extract, graph rebuild. Diff → confirm → apply → auto-doctor. |
| 8 | `forge graph` | Read graph queries Q1–Q17 (similar features, blast-radius, orphans, reusable-helpers, duplications, KMP-migration candidates, near-duplicates, redundant-platform). Rebuild lives inside `forge reconfigure`. |
| 9 | `forge memory <ação>` | Wrapper fino sobre o `mem` vendorizado (stateless): `search <query>` (busca ranqueada — `mem find`), `inspect [id]` (corpo de uma nota ou stats do acervo — `mem get`/`mem stats`), `export [--budget N]` (índice de alto valor pro context-pack — `mem brief`), `distill [--apply]` (curadoria do acervo — `mem evolve`). Inspeção de lifecycle vive em `forge status`; L3/forget removidos (W-ROUTE 6a). |
| 10 | `forge evolve` | Review and apply / reject proposed evolutions queued by retrospective-agent. Knowledge proposals (`promote-to-l2` / `l1-to-l2-promotion` / `consolidate-l2`): ao aprovar ("a"), emite `mem inbox add` (candidato curado) em vez de escrever direto no L2. O conhecimento entra na fila de inbox do mem e fica disponível via `mem evolve` / `mem inbox promote` (W-ROUTE 6b). Reuse-intelligence e `forget-l1` não são afetados. |
| 11 | `forge undo` | Revert the last state-mutating action (task commit, reconfigure apply, init). Interactive prompt picks target if ambiguous — `last` is not a CLI suffix, é a opção default no menu. |
| 12 | `forge raw` | Escape hatch. Direct invocation of internal scripts (`migrator-N-to-M`, `verify-card`, `edit-config`, `rebuild-templates`). Documented per-script. **NÃO** é uma porta pra inventar novos comandos via raw — é a porta pra operações pontuais sem UX. |
| 13 | `forge qa` | Adversarial red-team gate. Audita artefatos do lifecycle inventando cenários hostis (4 attack vectors: spec-vs-spec, chaos, coverage, validator-claim), executa fixtures sintéticos em sandbox isolado, emite findings actionable em proposed-evolutions. Scope: feature / screen / task / paranoid (cross-feature). Trigger: manual + opt-in auto via `qa.auto-run-on-feature-done`. Verdict (BLOCK/FLAG/PASS) NÃO bloqueia retrospective nem commit — alinha Decisão 5 (code review final out-of-scope). W-ROUTE 6c: antes de escrever o conductor-handoff.json, consulta `mem find` com o scope target. O resultado é injetado em `handoff["mem_context"]` pro conductor auditor. Degrade soft: campo `None` no handoff, sem crash. |
| 14 | `forge upgrade` | Self-updater do forge (v1.3+). Opera no FORGE_HOME (`~/.local/share/feature-forge/` ou FORGE_HOME env). Fluxo: git fetch → check HEAD vs origin → git pull → pip install --upgrade → smoke (`./bin/forge --version`). Se smoke falhar: git reset --hard ao commit anterior (rollback automático). Não interativo: sem prompts, sem menus. Idempotente: "já no latest" → exit 0 sem mutação. Exit codes: 0 = atualizado com sucesso / já no latest; 1 = falha (carrega tag `[FORGE-ERR:UPGRADE-FAILED]` em stderr no caso de smoke/pip falho + rollback executado — recontratado em W2, C3 EXIT-2-COLLISION; antes era exit 4). Não toca `.claude/forge/` do projeto — só atualiza o canonical repo. |

---

## Mapeamento formal: operação → entrypoint

| Operação | Onde mora | Como o usuário chega lá |
|---|---|---|
| **Card: add** | `forge reconfigure` → menu `[ ] cards` → opção "adicionar card" | Interactive multi-select dentro de reconfigure. |
| **Card: remove** | `forge reconfigure` → menu `[ ] cards` → opção "remover card" | Resolver bloqueia se outro card ativo depende. |
| **Card: upgrade (from canonical)** | `forge reconfigure` → menu `[ ] cards` → opção "atualizar card do canonical" | Mostra diff; usuário aceita ou pula. |
| **Card: lock (trust local edit)** | `forge reconfigure` → menu `[ ] cards` → opção "travar edição local" | Marca `pinned: true` na config. |
| **Card: inspect** | `forge reconfigure` → menu cards → opção "inspecionar" | Read-only; mostra sha256, conflicts, contributions. |
| **Inventory: refresh design-system** | `forge reconfigure` → menu `[ ] paths` (ou diretamente "re-extrair inventory") → escolhe quais | Auto também via post-commit hook quando DS muda no disco. |
| **Inventory: refresh i18n** | Mesmo. Geralmente roda automático via hooks `i18n-changes`. | |
| **Inventory: refresh conventions** | Mesmo. Roda automático no `feature-done` retrospective. | |
| **Schema migration v(n) → v(n+1)** | `forge raw migrator-N-to-M` | `raw` é o escape hatch por design — migrations não têm UX cinemática própria. |
| **Memory: distill quando acervo precisa curadoria** | (a) Manual via `forge memory distill [--apply]` — usado quando `forge evolve` apply é pausado por overflow de L2 (ver `docs/design/07-discipline.md` §6). (b) Interativo via `mem evolve`. | `forge memory distill` é CLI standalone arg-driven (W-ROUTE 6a). |
| **Memory: buscar no acervo** | `forge memory search "<query>"` | Busca ranqueada; equivalente a `mem find`. |
| **Memory: inspecionar nota ou stats** | `forge memory inspect [id]` | Sem id: stats do acervo (`mem stats`). Com id: corpo da nota (`mem get`). |
| **Memory: exportar context-pack** | `forge memory export [--budget N]` | Índice de alto valor (`mem brief`). |
| **Memory: knowledge → mem inbox** | `forge evolve` aplica propostas que vieram de retrospective-agent | Aprovação de proposal de conhecimento emite `mem inbox add`; curadoria final via `mem evolve` / `mem inbox promote`. |
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
| `forge card list` | `forge status` (cards ativos listados). |
| `forge inventory refresh X` | `forge reconfigure` → opção "re-extrair inventory: X" |
| `forge migrate --from N --to M` | `forge raw migrator-N-to-M` |
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
   o usuário precisa lembrar apenas 14 verbos. Cada novo subcomando dobra a
   superfície cognitiva.
2. **Decisão 10 é load-bearing.** Flags geram explosão combinatória de UX.
   `forge X --foo --bar` aceita ordem qualquer, valores fora de enum, conflitos
   entre flags. Conversational é restrito por design: a engine pergunta, o
   usuário responde dentro do conjunto oferecido.
3. **Auditabilidade.** Toda mutação passa por um dos 14 entrypoints, então
   `history.jsonl` de cada entrypoint cobre 100% das mutações. Sem comandos
   "laterais" gerando estado opaco.
4. **Portabilidade.** O dispatcher bash em `bin/forge` resolve apenas 14 verbos.
   Se a tabela cresce, o dispatcher cresce, a documentação cresce, e a skill
   deixa de ser absorvível em um clone.

---

## Hidden internal entrypoints

Some operations need an event-driven funnel that hooks call on the user's
behalf. These **are not part of the 14 user-facing commands**, are **never
typed manually**, and are **not documented as something the user invokes**.
They exist so that a single Python entrypoint can route any hook signal into
the right handler (graph delta, memory append, inventory refresh, proposal
queue).

| Hidden entrypoint | Who calls it | What it does | Why it's not in the 14 |
|---|---|---|---|
| `forge ingest --event <type> [payload]` | Claude Code hooks, git hooks, CI hooks, forge native dispatchers | Routes the event into `engine/ingest.py` which fans out to graph updater, memory updater, inventory updater, or proposal queue | Pure plumbing. No UX. User never types this; if a user runs it manually that's a bug in the hook layer, not a feature. |
| `forge graph detect-incremental <file>...` | `.claude/hooks/post-edit-detect-duplications.sh` (Claude Code post-edit hook) | Re-parses edited files, refreshes graph row, runs reuse-intelligence detection, prints inline any finding touching the edited files. Exit 0 always — never breaks the developer's edit. | Subcomando POSICIONAL de `forge graph` (não flag — argv[0]=="detect-incremental"). É um modo non-interactive do verbo já existente, não um novo verbo. Decisão 9 preservada. |

Adding a new hidden entrypoint requires the same scrutiny as adding a
14th command: explicit PR, decision update, documentation. The current
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
2. Se não está listado mas a operação é nova: encaixa em um dos 14 como menu
   ou prompt interativo.
3. Se não encaixa em nenhum dos 14: **para** e abre PR pra revisar decisões 9
   e 10 explicitamente. Nunca expande silenciosamente.

Mentor calmo é firme aqui: o que protege a UX do forge é a estabilidade da
superfície. 14 verbos, zero flags, zero exceções.

---

## Exit codes

Contrato canônico do dispatcher (`bin/forge` → `engine/cli.py::main()`).
Recontratado em W2 (protocol robustness, 2026-06-17, finding C3
EXIT-2-COLLISION): exit 2 é reservado ESTRITAMENTE pra pausa; a escada legada
(3/4/5/6/7/8 + not-a-project=2) colapsou em `exit 1` + tag machine-readable em
stderr.

| Code | Significado | Origem |
|---|---|---|
| 0 | comando completou com sucesso | handler retornou normalmente |
| 1 | erro (carrega tag `[FORGE-ERR:<TAG>]` em stderr) | todo erro de handler via `fail_with_tag` + exceções não-listadas |
| 2 | paused for input (needs response) | SÓ `PausedForInputError` (engine emitiu pending) + `UserPausedError` (response `paused: true`) |
| 127 | editor não encontrado | exceção POSIX documentada — só `forge raw edit-config` |
| 130 | user cancelou | `KeyboardInterrupt` (TTY) + `UserCancelledError` (response `cancelled: true`) |

**Tags machine-readable (exit 1).** Toda saída de erro de handler emite uma tag
estável em stderr no formato `[FORGE-ERR:<TAG>]`. O host/driver ramifica por ela
sem depender de código numérico ambíguo. Tags canônicas (fonte única:
`engine/ui/exit_codes.py`):

| TAG | Quando | Comandos |
|---|---|---|
| `PROJECT-NOT-FOUND` | fora de um projeto forge | plan, implement, verify, evolve, undo |
| `LOCKED` | feature phase-locked por outro comando | plan, implement |
| `FEATURE-MISSING` | feature não existe (rode `forge plan` antes) | implement |
| `NOT-READY` | readiness != 'ready' (finalize Wave E) | implement |
| `WAVE-INCOMPLETE` | sem tasks (Wave D do plano incompleta) | implement |
| `BLOCKED-EXTERNAL` | task bloqueada por ticket externo | implement |
| `QA-BLOCK` | verdict do `forge qa` = BLOCK | qa |
| `UPGRADE-FAILED` | rollback após checkout/smoke falho | upgrade |
| `USAGE` | uso inválido / sem projeto / arquivo ausente / migrator stub | raw, init |
| `ABORTED` | usuário abortou um gate (subtype-stub, resume de init, config-presente) | plan, init |
| `INIT-FAILED` | pipeline de `forge init` levantou InitError | init |

O host (Claude Code OR adapter intent-file) loop-reads exit code 2 + state files
(`.claude/forge/state/forge-pending.json` / `forge-response.json`) pra
continuação. Subagent invocando `forge` que receba exit 2 NÃO deve responder
sozinho — ver `.claude/rules/subagent-workflow.md §Quando subagent invoca \`forge\``.

**Exit 130 — duas rotas convergentes:**
- (a) `KeyboardInterrupt` (Ctrl+C / SIGINT) em modo TTY.
- (b) Host response `cancelled: true` (`UserCancelledError`) em modo intent.

Callers tratam identicamente — usuário desistiu (Decisão 27 cobre a rota TTY;
CR-001 do W2 review cobre a rota intent).

Schema dos state files: `docs/schemas/intent-protocol.md`.
Spec canônico: `docs/superpowers/specs/drift-1-intent-protocol.md` §4.

POSIX nota: exit 2 às vezes é usado por shells pra "misuse of shell builtins";
`forge` não é shell builtin, então o conflito é nominal.

---

## Manifesto + meta-flags (Decisão 10 revisitada — 2026-06-18)

W3 (token economy / machine-legibility) destrava consumo por máquina sem quebrar
a UX conversacional human-first. O carve-out é **meta-flags only** e GATED num
allowlist de read-commands (`engine/ui/output_mode.py::_JSON_CAPABLE_COMMANDS =
{status, doctor, verify, memory, graph}`).

**Ativadores do modo JSON (só pros read-commands no allowlist):**

- `--json` em argv (ex.: `forge status --json`).
- env `FORGE_OUTPUT=json` (ativa o modo pros read-commands; valor desconhecido
  é ignorado e cai pra TTY/PLAIN).
- `forge --help --json` (manifesto — emitido direto, independente do output-mode).

**Enforcement estrutural (H-001).** O modo JSON é resolvido UMA vez no startup
do `cli.main` via `detect_output_mode(argv, command=cmd)` e publicado num context
var lido pelo chokepoint único `renderer.write`. Comandos interativos
(`plan`/`implement`/`init`/`reconfigure`/`evolve`/`qa`/`undo`/`raw`) NUNCA resolvem
JSON — mesmo sob `FORGE_OUTPUT=json` ou um `--json` espúrio resolvem TTY/PLAIN.
Isso impede que o no-op global de `renderer.write` (em JSON mode) degrade
silenciosamente a UX cinematográfica deles. O marker `<FORGE_INTENT/>` é emitido
via `sys.stdout.write` direto (não via `renderer.write`), então o intent protocol
sobrevive ao modo independentemente.

**Modelo de saída JSON** (idêntico ao `forge graph --json`): stdout SÓ JSON
(`json.dumps(payload, indent=2, default=str)`), erros → stderr, exit 0 sucesso /
1 falha. `status`/`memory` são read-only puros. `doctor` mantém o stamp
`doctor.last-run` idêntico ao caminho interativo. `verify` é um **observador com
side-effects de L1** (C-34d): mesmo em JSON mode ele transita o status da feature
pra `verifying` enquanto roda (restaurando ao status anterior no pass; anotando
`verify-failed` no `raw.notes` no fail) e dá append num registro por invocação em
`.claude/forge/state/lifecycle/{slug}/verify-log.jsonl`. NÃO muta código nem artefatos — daí
"observador" — mas a observabilidade de L1 é idêntica entre os modos
interativo e JSON. Em scope `task` ambíguo (≥2 features ativas, sem
`--feature-slug`) o JSON mode emite erro determinístico + exit 1 ANTES de
qualquer escrita de L1 (C-34) — nunca muta a feature errada por fallback.

**JSON mode NUNCA pausa (C-001).** Os read-commands com caminho de prompt
(`verify` quando ≥2 features ativas e nenhum scope explícito; `graph` quando
invocado sem query) NÃO entram no `question.ask` sob JSON mode — fazê-lo
dispararia exit-2 + marker `<FORGE_INTENT/>`, reservado ESTRITO pro intent
protocol. Em vez disso emitem erro determinístico em stderr + exit 1: `verify`
exige `feature <slug>`/`task TASK-NNNN`; `graph` exige `forge graph --json
<query>`. Exit-2 jamais ocorre num consumo machine-readable.

**Payloads:**

- `forge status --json` → `{project, active_features, memory, pending_evolutions,
  doctor, suggested_next_command}`. O bloco `memory` inclui `memory.mem`
  (total/by_type/live/stale — resumo de `mem stats`) + `memory.l1`
  (active/archived). Degrade soft se mem indisponível: `memory.mem` ausente
  ou `null` (W-ROUTE 6b). `suggested_next_command` é o workflow router
  (A2): mapeia o estado da feature mais recente pro próximo verbo, cobrindo TODOS
  os 9 estados de `_VALID_STATES` (H-002): not-started→plan, planning/planned→
  implement, implementing/verifying→verify, done→status, deferred→status,
  aborted→plan, blocked-on-external→reconfigure; nenhuma feature→plan; estado
  fora-do-enum→doctor. (PHANTOM-STATES resolvido em W-DEBT: `verified`/`paused`
  removidos do enum — nunca foram escritos; pausa é `deferred` por Decisão 27.)
  Tie-break de recência é estável (timestamp, depois slug) pra ser
  determinístico quando `last_action_at` empata (W-003).
- `forge doctor --json` → `{scope: "full", overall_status, exit_code, categories:
  [{title, worst, checks: [{name, status, message, remediation}]}]}`. JSON mode é
  non-interactive: assume scope `full` (o ask de scope não pode pausar pra máquina).
- `forge verify --json` → `{scope: {type, target}, overall, exit_code,
  infra_degraded, coverage_summary, validators: [{name, status, duration_ms,
  message, paths, what_failed, where, why, coverage}]}`.
  - `overall` ∈ `{pass, warn, incomplete, degraded, fail}`. Precedência do
    agregado: `fail > warn > incomplete > pass`. `incomplete` = houve validator
    `degraded` (infra off-contract / quebrado) e nenhum `fail`/`warn` — "verify
    não pôde avaliar tudo"; é NÃO-bloqueante (não dispara block-forge-implement)
    e distinto do `degraded` do contrato L1 verify-log (Onda 1, BUG-VERIFY-1).
  - `infra_degraded` (int) = contagem de validators `degraded`, saliente no topo
    do payload pro host branchar sem varrer `validators[]` — loud mesmo num run
    warn/fail-misto onde `overall` carrega o veredito dominante.
  - `coverage_summary` (BUG-VERIFY-2) = quebra honesta dos passes por classe de
    cobertura: `{substantive, stub, staged-blind, opaque, degraded}` (contagens
    inteiras; `degraded` é gêmeo separado, não classe de pass-coverage). Cada
    validator carrega `coverage` (só preenchido em `status==pass`) — pro host não
    tratar "verde" como garantia uniforme.
- `forge memory <ação> --json` → cada subcomando repassa `--json` ao `mem`; o schema de
  saída casa com o do `mem` correspondente: `search <query>` → hits de `mem find`,
  `inspect [id]` → nota/stats de `mem get`/`mem stats`, `export [--budget N]` → briefing
  de `mem brief`, `distill [--apply]` → resultado de `mem evolve`. Não há mais snapshot
  `{l1, l2, l3}` nem menu REPL — a superfície é arg-driven stateless.
- `forge --help --json` → manifesto: `{forge_version, commands: [{name, summary,
  interactive, hidden, flags, args}]}`. Itera `_VISIBLE_ORDER` (ingest oculto
  omitido) e busca cada nome em `_COMMAND_META` — metadata hand-maintained em
  lockstep com `COMMANDS`, NÃO auto-derivada (drift-guard de teste assegura
  `set(_COMMAND_META) == set(_VISIBLE_ORDER)`; W-001). Read-commands anunciam
  `flags: ["--json"]`; interativos `flags: []`.
