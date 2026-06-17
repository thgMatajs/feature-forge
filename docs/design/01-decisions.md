# Locked decisions

All decisions crystallized during design conversations (May 2026). This is the
source of truth for "what was decided and why." Changes require explicit
revisit, not silent drift.

## Decisions table

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | Skill name | feature-forge (alias `forge`) | Verb of crafting/shaping. Memorable, short. |
| 2 | Persona | Mentor calmo | Warm, explanatory, didactic. Firm at gates. |
| 3 | Magic moment | Init reveals project map | Investment goes into init UX. |
| 4 | Vocabulary | "forge" só como verbo, resto neutro | No metaphor overload. |
| 5 | Out-of-scope set | arch macro, produto, code review final, time tracking | Scope discipline. |
| 6 | Init map format | Cinemático passo-a-passo | "Skill discovering with me" feeling. |
| 7 | Gate violation reaction | Bloqueia firme + cita regra | Mentor calmo is firm at gates. |
| 8 | Out-of-scope reply | Redireciona + valor adjacente | Helpful without overstepping. |
| 9 | Command surface | 12 subcomandos (versão final) | init, plan, implement, verify, status, doctor, reconfigure, graph, memory, evolve, undo, raw. Note: retrospective on feature completion runs **automatically** when the last task is verified — no separate `feature-done` command. Card management, inventory refresh, schema migration, and graph rebuild are routed through interactive menus inside the 12 entrypoints (see `docs/design/06-command-surface.md` for the formal mapping). No card/inventory/migrate sub-commands exist. |
| 10 | Interaction mode | 100% conversacional, sem flags | Human-first. CI mode not in v1. |
| 11 | Feature completion | Retrospectiva expandida | Learn-out-loud. |
| 12 | Resume behavior | Auto-resume com sumário | Low friction return. |
| 13 | Skill downstream pattern | Split por preset | Each preset has its own simple skills. |
| 14 | Config scope (monorepo) | Um por sub-projeto | Multi-stack monorepos supported. |
| 15 | Versioning model | Snapshot copy local | Fork-and-forget. No runtime dep on upstream. |
| 16 | Reconfigure UX | Comando `reconfigure` com diff | Incremental update. |
| 17 | Greenfield vs brownfield | Mesmo fluxo, auto-detect opcional | One code path. |
| 18 | Skill location | Standalone repo at `~/Documents/feature-forge/` | Canonical home + per-project install. (superseded by row 18-v2 — 2026-06-17) |
| 18-v2 | Skill location | Standalone repo at `~/.local/share/feature-forge/` (XDG default; respects $XDG_DATA_HOME) | Revisita v1.3 2026-06-17 — XDG is the universal convention for script-installed tools; ~/Documents/ conflates with the user's docs directory. |
| 19 | Language | Python core + Bash dispatcher + YAML/MD specs | Pragmatic mix. |
| 20 | Persistence | SQLite (graph) + arquivos (config, memory, docs) | Best of both. |
| 21 | First implementation artifact | Forge init roteiro end-to-end | UX before code. |
| 22 | Dependencies on other skills | None at runtime; absorb patterns only | Portability + independence. |
| 23 | Validator cascade behavior | Halt on first hard error; continue past warnings; override via `validators.fail-fast: false` in workflow-config | Fast feedback no caso comum; batch-collect quando refactor grande ou CI precisa do panorama. Sem flag (decisão 10). |
| 24 | `.bak` retention | 7 dias default (configurável em `cleanup.bak-retention-days`); doctor reporta overdue; nunca auto-deleta — limpeza via menu interativo em `forge reconfigure` | Reversibilidade (princípio do 00-vision) exige que backups durem o suficiente pra undo, mas sem virar lixo eterno. |
| 25 | Rejected proposal fingerprint | `sha256` sobre canonical-form `{type, name, normalized-description, sorted-provenance-set}` | Estável contra timestamps e edits cosméticos; muda quando conteúdo ou evidência mudam — permite re-apresentar quando há padrão novo. |
| 26 | Batch-apply em `forge evolve` | Proibido. Aplicação é single-by-single sempre; alta confidence apenas acelera apresentação, não pula confirmação | Engine nunca decide sem usuário (00-vision). O valor de `evolve` É o gate humano — batch-apply tira o valor. |
| 27 | Pause vs abort semantics | Ctrl+C / `para` = pause (state `deferred`, auto-resumable); abort terminal só via `forge undo` interativo escolhendo "abort feature entirely" | Loops longos (plan/implement/evolve) precisam pausa segura como default. Abort destrutivo requer dois passos explícitos. |
| 28 | Card local overlay (Approach A — added 2026-06-02) | `.claude/cards/local/<name>/` versionado no projeto consumidor. Cascade canon ∪ local com hard-fail em colisão de nome. Sem merge silencioso, sem override. `legacy-marker: bool` é campo aditivo opcional (schema-version permanece 1). Capability labels overlay vive em `.claude/inventory/capability-labels.local.yaml` com guards: sem `overrides`, sem `reserved-promotions`, sem colisão com canon ativo. | Destrava portabilidade real (Gaps 5, 9, 14) sem violar Decision 22 (zero runtime deps) nem Decision 15 (snapshot copy local). Hard-fail explícito > merge silencioso; promoção formal exige ADR. |
| 29 | Revisita Decisão 9 (2026-06-05) — command surface | 13 subcomandos | Adiciona `forge qa` como 13º. Justificativa: QA red-team é semanticamente distinto de verify (cascade determinístico) / doctor (health check) / evolve (review-and-apply). Encaixar como menu interno de qualquer um dilui semântica e quebra discoverability. Linha 9 histórica preservada (locked at 12); a partir desta data, locked at 13. Veja `docs/superpowers/specs/2026-06-05-forge-qa-design.md` pra design completo. |
| 30 | Sandbox isolation (forge qa Phase 3) (superseded by row 31 — 2026-06-08) | Subprocess CWD = `.planning/qa/<run-id>/fixtures/`; writes fora do sandbox raise SandboxBreachError; os.chdir guard via PYTHONSTARTUP preload; budget global default 60s + per-validator 15s configurável em workflow-config | Isolation guarantee contra contaminação de produção. Auditores chaos/validator-claim geram fixtures hostis que rodam validators em subprocess — sem hardening, validator malicioso ou bugado poderia escrever em paths de produção. Decisão pareada com Decisão 22 (no runtime deps em outras skills): sandbox protege a forge AGAINST cards de terceiros via qa-extensions. |
| 31 | Revisita Decisão 30 (2026-06-08) — sandbox isolation guard | Subprocess CWD = `.planning/qa/<run-id>/fixtures/`; writes fora do sandbox raise SandboxBreachError; **os.chdir guard via `sitecustomize.py` preload por PYTHONPATH** (não PYTHONSTARTUP — esse só dispara em REPL interativo, não em `python script.py`); budget global default 60s + per-validator 15s configurável em workflow-config | Decisão 30 original documentou PYTHONSTARTUP mas implementação em `engine/qa/sandbox.py:19-24` usa sitecustomize.py via PYTHONPATH. Texto atualizado pra refletir mecanismo real, pareando spec com código. Rationale técnico: PYTHONSTARTUP é executado APENAS quando Python entra em REPL interativo (testado: subprocess.run com script não dispara); sitecustomize.py é executado em TODA invocação do interpretador. Comportamento de isolamento idêntico ao da Decisão 30 original — só o mecanismo nomeado mudou. |

## User-provided constraints (verbatim notes)

> "**completo pois isso ja sera a versao final**" — re: command surface.
> v1 is the final daily-driver, not an MVP that evolves.

> "**quero no final ter algo já pronto para uso**" — practical end-to-end
> shipping orientation.

> "**estou modularizando outro projeto** que também é Android + iOS + KMP" —
> portability is a real near-term need.

> "**não quero ficar dependente de outros pacotes de skill**" — absorb
> essences, no runtime dependencies on gsd-*, superpowers, etc.

## Decisions deferred to later phases

- Card schema details (Phase 1, item 2)
- Sub-agent prompt format (Phase 2)
- Template structure (Phase 3)
- CI hook strategy specifics (Phase 5)
- Marketplace of cards (post-v1)

## Decisions that could be revisited

These are not load-bearing on the architecture and could be revisited without
major refactor:

- Cinemático init UX vs other formats — affects only init.py
- Voice "mentor calmo" vs other personas — affects prompts, not structure
- Command names — refactor at any time before users invoke them

## Decisions that are LOAD-BEARING (don't revisit lightly)

- Card composition model (changes ripple through every preset)
- File-driven state (changes break resume / inspectability)
- Snapshot copy versioning (changes break per-project isolation)
- SQLite for graph (changes break hooks and queries)
- Python core (changes break all scripts)
