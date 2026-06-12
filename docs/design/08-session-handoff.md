# Session Handoff

> Use este doc se você está **retomando feature-forge numa sessão nova** ou se
> é um agente cold-start sem contexto da conversa de design original.

**Última atualização:** 2026-06-12 (REVIEW.md remediation — Bloco 1: security quick wins)
**Wave A (PR #13 review, 2026-06-12):** 6 fixes contidos remediados em 5 commits sobre `96a0896` (cli paused_exc refactor + intent-state flush + validate_presets imports + RULE-020 cascade guard + doc-sync). Fix 4 (clear_intent_log_only delegation) skipped — semantics divergem, anotado pra Wave B. Rapid lane verde (1306 passing, 6 falhas pré-existentes inalteradas em test_cards_resolver/test_commands_init/test_validators_card_yaml). +2 regression tests.
**Wave B (PR #13 review, 2026-06-12):** 5 fixes cross-module remediados em 5 commits sobre `b8731f7` (commits `37084c0` → `4b6eada`): (1) ciclo composer↔init quebrado via `engine/detection/_eval.py` novo + shape guard no composer; (2) `isinstance(Cell/Conflict)` em vez de `hasattr` em 5 sites de init.py; (3) `BACKEND_AXES` shared em `engine/detection/_axes.py` (init + reconfigure consomem); (4) cache process-level pra `_read_intent_log` (O(1) cache hit vs O(n) re-parse); (5) `VALID_BACKEND_AXES`/`VALID_BUNDLE_PLATFORM_KEYS`/`VALID_PROJECT_PLATFORMS` consolidados em `validators/_common.py`. Rapid lane sobe pra 1321 passed (+15 vs Wave A baseline). Mesmas 6 falhas pré-existentes herdadas, não tocadas (out of scope).
**Estado:** v1.2-dev Phase B DET-6 ✅ COMPLETO + REVIEWED. W1-W8 + W7 cluster review fix + E2E coverage + 2 follow-up fixes (_SKIP_DIRS + Phase A pitfall) + DET-6 W2 fixture cleanup tardio. AC-1..AC-10 cobertos. Rapid lane 1310 passing; integration 133 passing (1 deferred: bootstrap.sh worktree edge case); validators 245+8 passing; e2e 21 passing (RUN_E2E=1). Mandamento 0 loop fechado (impl → review → fix → verify) com 2 reviews formais (W5 + W7 cluster). Branch ainda LOCAL — push + PR depois desta sessão. Fechamento absorve B1/B2/DET-5 naturalmente conforme spec. Phase 0 DET-3 ✅ shipped em `main`. Phase A (DRIFT-1) PR #11 master-review remediado integralmente; PR #12 carrega os 14 follow-ups pós-PR #11 (16 commits: `a7d0947..d1b95c5`) — A-1/A-2/M-2/M-3/M-4/M-5/B-1/B-2/B-3 + S-1 edge-case coverage + M-1 assimetria documentada + S-2/S-3 follow-ups capturados; +41 novos tests; rapid lane ~1054 passing, suite total ~1178 collected. v1.2.0 feito + Gap 9 cumulativo + CC gate v1 (PR #4) + PRD docs/product/ (PR #5) + plan-auditor (PR #6) tudo em `main`. `forge qa` shipado (PR #8). QA-11 sandbox env hardening fechado (impl + final review + closeout post-review remediação + post-ultra-review remediation 16 findings); pré-piloto restrito a QA-13 (paranoid state filter — `aborted`/`archived` corretamente excluídos do cross-feature scope). Ultra-review do PR #9 fechou deep-001 (crítico: PYTHONPATH não herda mais do parent), endureceu pattern regex contra false-positive (AUTHOR/CO_AUTHOR), adicionou defense-in-depth no `build_safe_env` (allow_sensitive opt-in), corrigiu UX do grant flow (EOF + re-prompt 3x), mascarou nomes em log (anti-disclosure), guardiou isinstance de shape em sensitive-env-grants e ampliou catch do alert layer pra RuntimeError. 5 findings deferidos a PRs separados (deep-010 warning channel cross-cutting; deep-011/012 scope.py refinements fora da whitelist; deep-014 verify.py plumbing; deep-021 loader.py warning). Branch `worktree-feat+gate-infra-extract` agora consolida (após merge de origin/main) Phase 0 do roadmap de quality-gates expansion — refactor estrito (no-behavior-change) extrai infra reusável do CC gate em `validators/_gate_infra.py` + `validators/_diff.py` + rename de helpers em `validators/_common.py`. CC validator caiu de ~1127 LOC para ~840 LOC compondo helpers públicos. Phase 0 suite verde (baseline 751 - 1 justificado em T4: removed test do lookup `_TOOL_BIN[lang]` interno que não existe pós-refactor). Wave R1.1 `check_secrets` shipping na mesma branch — primeiro consumer real do helper extraído valida a generalização e fechou Gap GATE-INFRA-1 (parametrização de `gate_threshold_lookup` + `format_three_paths_message`); Gap GATE-INFRA-2 (kw-only `cmd_builder` API) registrado pra próximo consumer.

Linha paralela `feat/drift-1-intent-protocol` (worktree `.claude/worktrees/drift-1-w2`): Phase A SHIPPING-READY. 21 commits sobre `1b1d289` cobrindo W1 (foundation — `engine/utils/json_io.py` + `engine/ui/intent_state.py` + schema canônico `docs/schemas/intent-protocol.md`), W2 (chokepoint refactor + 10/10 intent-resume — T0 outcome C locked, T1 question.py emitter+sentinel, T2 cli.py exit 2/130, T1+T2 fix de 10 findings CR/HI/MD/LO, T3a checkpoint-audit.json, T3b PART A/B/C integração nos 10 subcommands), W3 (tty_bridge subprocess loop fallback), W4 (bin/forge dispatcher detectando TTY + env `CLAUDECODE`; hooks audit sem patches), W5 (15 integration + 3 e2e pty tests cobrindo AC-1..AC-9) e W6 (doc-sync — este commit). Rapid lane preservada: 1151 passed / 11 skipped (1162 collected pós-W5). Integration lane: 119. E2E lane: 17. Total coletado: 1298. Engine intent-only protocol + tty_bridge fallback + bin/forge dispatcher migration + 10/10 subcommand intent-resume; aguardando push + abertura de PR. Phase B DRIFT-1 (DET-6) W1 ✅ entregue em outro worktree (`det-6-w1`, também aguardando push). Phase 0b ainda aguarda merge do PR #10.

**Update 2026-06-11 — master-review PR #11 remediado:** os 28 findings do
master-review (`/tmp/master-review-pr-11-drift1-REVIEW.md`) endereçados em
10 commits Wave 1+2 sobre `e992e01` (range `ad49c40..626a4f0`) — todos
3 Críticos + 7 Altos + 10 Médios + 5 Baixos + 3 Sugestões. Rapid lane
sobe de 1151 → 1199 passed / 11 skipped (+32 testes novos cobrindo
race-detection threading, schema-version mismatch, EOFError no
tty_bridge, dir fsync POSIX, chmod 0600, intent-id stability sob mesmo
prompt em comandos distintos). Cinco follow-ups novos registrados em
`04-pending.md §Follow-ups pós-master-review PR #11`:
FU-DRIFT-1-LOCK (P3, fcntl.flock real), FU-DRIFT-1-DEPRECATE-INTENT-ID-ALIAS
(P2, v1.3), FU-DRIFT-1-CHECKPOINT-CONSOLIDATE (P3, deletar shims
pós-DRIFT-2), FU-DRIFT-1-OBS (P3, log infrastructure), FU-DRIFT-1-VERIFY-ISO
(P3, microseconds vs seconds). PR #11 ready for merge.

**Follow-up 2026-06-11 (commit `6dd40af`):** `engine/init.py::_load_checkpoint`
ganhou guarda `isinstance(data, dict)` retornando `None` em YAML corrompido
(threads master-review #3396896063 + #3396903793, `[Critico]`). Alinha com
o pattern dos 9 outros checkpoint-loaders já refatorados via
`engine/utils/checkpoint_io.py`. Sem mudança de behavior pra cases válidos;
elimina crash silencioso em payload mal-formado.

**Nota rebase Phase B (2026-06-11):** a entrada de doc-sync W1 deste
commit foi colapsada no rebase contra `origin/main` — a versão mais
nova do header (acima) já existe em `main`, e o conteúdo factual da
Phase B W1 está preservado na "Linha paralela" logo abaixo. W8
reescreverá a seção quando Phase B fechar.

Linha paralela (2026-06-10): branch `feat/det-6-multi-axis-backend` (worktree `det-6-w1`) consolida **Phase B W1 — DET-6 multi-axis backend foundation**: novo schema doc `docs/schemas/backend-axes.md` formaliza o modelo platform-keyed (8 axes × N plataformas → cell-object com `provider`/`status`/`notes?`); `docs/schemas/card.md` atualiza CARD-004 enum (+analytics/notifications/flags; −backend/network) + adiciona campo opcional `identity.platforms` + CARD-020 + seção "Backend axes"; `docs/schemas/workflow-config.md` reescreve bloco `backend:` para shape multi-axis, remove `backend.provider` monolítico, canoniza RULE-019..024 como referenciados (autoridade em `backend-axes.md`). Sub-IDs alfanuméricos eliminados; RULE-010/011 ficam como audit-trail dos campos legacy. Doc-only — sem touch em engine/validators/cards/presets. Phase B é multi-wave (W1-W8): W1 done; W2-W6 paralelizáveis com Phase A pendentes; W7-W8 ainda blocked em Phase A merge. PR final só ao fim de W8. Refs commits `c60eeb1` (schema foundation) + `26c0822` (review-fix canonicalizando RULE-019..024). Findings deferidos do REVIEW registrados como W1-L-002 e W1-L-003 em `docs/design/04-pending.md`. Suite rapid lane na branch: **1015 passed** (baseline mantido).

Linha paralela `worktree-forge-qa` (PR #8) consolidou pós-rebase contra
`main`: CONF-001..008 entregues, Gap QA-12 fechado (pause/resume via
checkpoint.json), 4 fixes pós-review CONF-004 aplicados (H-1, M-2, M-4,
M-5), Revisita Decisão 30 (sandbox guard via sitecustomize.py em vez de
PYTHONSTARTUP — comportamento idêntico, mecanismo nomeado corrigido).
Suite: 933 passed + 19 skipped + 1 falha pré-existente bootstrap
(BOOTSTRAP-1). Próximo: merge PR #8 → main + estabilização.

Linha paralela: branch `worktree-forge-qa` (PR #8, in-flight contra
`main` pós-rebase) carrega `forge qa` como 13º comando (red-team
adversarial gate). 4 attack vectors (spec-vs-spec, chaos, coverage,
validator-claim) × 4 scope targets (feature / screen / task / paranoid).
Sandbox isolado em `.planning/qa/<run-id>/fixtures/` (Decisão 30).
Verdict informativo (BLOCK / FLAG / PASS) — não bloqueia
retrospective/commit (Decisão 5 preservada via discipline §11 nova).
Findings desaguam em `forge evolve` como `proposal-kind: qa-finding`.
Spec: `docs/superpowers/specs/2026-06-05-forge-qa-design.md`. Plano
executado: `docs/superpowers/plans/2026-06-05-forge-qa.md`.

Próximo passo: PR #7 mergeable + Wave R1.1 verde + considerar Gap 14 (preset coverage) + itens deferred v1.2.x. Várias linhas de trabalho convivem no Unreleased:

- Phase B aguarda push da branch `feat/det-6-multi-axis-backend` (29 commits
  acumulados em worktree `det-6-w1`) + abertura de PR. W8 doc-sync neste
  commit é a última wave; review da PR + merge fecham DET-6 em main.


- **Phase 0 (gate-infra-extract) — esta branch** — refactor estrito: 7 commits de
  extração + 1 doc-sync + 4 robustness fixes pós-power-review (render_config,
  parse/apply_overrides, diff worktree-safe, dead re-exports). Sem behavior
  change, sem decisão locked tocada, sem novo validator. Apenas reorganização
  que destrava Wave R1+ (gates pendentes compõem do shared em vez de copiar).

- **Wave R1.1 (check_secrets) — esta branch, in-flight** — primeiro consumer
  real de `_gate_infra` + `_diff`. Valida generalização do refactor Phase 0.

- **(1) CC gate v1 — em main** (PR #4 merged 2026-06-05) — `check_cyclomatic_complexity`
  multi-language (Kotlin/Swift/TS/Python) dispatcha pra Detekt/SwiftLint/
  eslint/Radon, roda em duas posições: cascade de `forge verify` (após
  `check_no_invented_behavior`) e per-task em `forge implement` (entre
  review e commit). Threshold via precedência card `cc-gate-override` >
  workflow-config `cc-gate` > defaults built-in (kotlin=10, swift=10,
  ts=15, python=10). Regra de fail: função nova `cc > N` OU função
  modificada `cc_after > cc_before`. Override-justify via linha
  `CC-OVERRIDE: <file>:<func> cc=<N> — <razão>` no commit body,
  auditável via `git log --grep='CC-OVERRIDE'`. Bypass emergencial via
  env `NO_CC_GATE=1`, logado em `.claude/state/cc-gate-bypass.jsonl`.
  `forge doctor` ganha 13ª categoria `cc-gate-tools` (status + instruções
  de install). Refinamentos pré-merge endereçados em final review: (H1)
  threshold dinâmico chega às tools nativas via tempfile-render
  (Detekt/SwiftLint não aceitam threshold via CLI flag — placeholder
  `__CC_THRESHOLD__` substituído em tempo de execução); (H2) Radon trocado
  de `-n F` (mascarava CC ∈ [11..40]) pra `-n A` com filtragem em Python;
  (H3) `cc_format_three_paths` render canônico chega ao usuário via
  `result["render"]` consumido em `_render_cc_gate_block`; (H4) warnings
  de overrides malformados propagam via 3-tupla `(silenced, surviving,
  warnings)` até o result dict. Suite cumulativa pós-merge: ~688 passed
  + 17 skipped. Sem revisitar decisões locked — Decisions 10/19/22/23
  preservadas.

- **(2) PRD docs/product/ entregue** (PR #5) — 4 docs (~2205 LOC):
  `00-prd.md` (583 LOC, 13 seções: Por-quê / Vision / Princípios /
  Escopo IN-OUT / Personas-resumo / Scenarios-resumo / Roadmap-resumo /
  Success criteria / Anti-personas / Cross-refs docs técnicos / Glossary
  15 termos / FAQ 9 perguntas / Risks 6 + Open questions 4) +
  `01-personas.md` (555 LOC, 8 personas em 3 camadas: Marina primária +
  Bruno + Sub-agente Claude dedicadas; Carlos/Lucas/Carolina variantes
  Marina; Patricia/Diego downstream read-only) + `02-scenarios.md`
  (679 LOC, 6 user journeys end-to-end — C1 Brownfield init / C2 Feature
  product / C3 Bugfix IN-37234 / C4 Retomar pausado / C5 Extension Gap 9 /
  C6 Reuse intelligence) + `03-roadmap.md` (388 LOC, 3 ondas Autopilot
  v1.3-1.4 / Catálogo evolutivo v1.5-2.0 / Inteligência adaptativa v2.x +
  Matriz Eisenhower + anti-roadmap 8 items + cross-ref bidirecional pro
  `docs/design/ROADMAP.md` técnico). Lente produto que coexiste paralelo
  com `docs/design/` (lente arquitetura) e `docs/ux/` (roteiros) — sem
  mexer em `docs/design/00-vision.md` nem `docs/design/ROADMAP.md`
  (load-bearing). Spec: `docs/superpowers/specs/2026-06-04-prd-design.md`
  (commit `2e1a266`). Plan: `docs/superpowers/plans/2026-06-04-product-docs.md`
  (commit `4134744`).

- **(3) Plan auditor entregue** (PR #6, merged em main) — `.claude/rules/plan-auditor.md` define prompt determinístico + 12 checks com severity (2 Critical / 4 High / 3 Medium / 3 Low) pra auditoria pós-`superpowers:writing-plans`. Orquestrador dispatcha `gsd-code-reviewer` com este prompt antes do "Execution Handoff"; Critical findings bloqueiam até fix-dispatch. Output em `.planning/plan-reviews/<plan-slug>-review-r<N>.md` (gitignored). Re-audit cap em 3 rodadas; override inline via `<!-- audit-override: C-XXX — razão -->` no topo do plano. Integração documentada em `CLAUDE.md` §Workflow por verbo, `.claude/rules/superpowers.md`, `.claude/rules/subagent-workflow.md`, `.claude/rules/README.md`. Sync r3 (2026-06-05) fecha 4 findings do power-review externo (PR-001 high + PR-002/PR-003 medium + PR-004 low): verbatim Task 1 ≡ rule vivo, spec back-portada pós refinements, override dash flex (`-`/`–`/`—`/`--`), meta-finding §"snapshot-vs-vivo" ganha case-1 factual. Spec: `docs/superpowers/specs/2026-06-04-plan-auditor-design.md`. Plan: `docs/superpowers/plans/2026-06-04-plan-auditor.md`.

- **(4) Phase 0 gate-infra-extract + Wave R1.1 check_secrets — branch `worktree-feat+gate-infra-extract` (PR #7)** — descrita em detalhe no header desta nota (refactor estrito + primeiro consumer). Após Phase 0, suite cumulativa na branch fica em **750 collected** (baseline 751 - 1 justificado em T4). Wave R1.1 adiciona testes pra `check_secrets` (fixtures em `tests/fixtures/secrets/` + integration em `tests/integration/test_secrets_gate_end_to_end.py`). Gap GATE-INFRA-1 fechado (parametrização habilitada); Gap GATE-INFRA-2 (kw-only `cmd_builder` API) registrado pra 2º consumer downstream.

Anterior (Gap 9 + /resolve-pr-comments cleanup): extends-feature mechanic
shipado em `feat/gap9-extends-feature` (PR #3 merged 2026-06-05). Pattern
leve product-derived: feature done pode ser estendida via novo slug
derivado com `extends-feature: {parent-slug}` aditivo no status.json +
intake — sem cards canon novos, sem mudança no enum platforms, sem
upgrade de inventory schema. Cena 1 do `forge plan` ganha 4º caminho
"Estender" (conditional state=done); validator novo EXT-001..004
(cross-cutting); discipline §10 formaliza semantics. **Multi-target
retroativo (watchOS / Wear OS / tvOS) movido pra out-of-scope permanente**
— feature-forge cobre mobile (Android + iOS + KMP); plataforma exótica
futura entra via Gap 5 overlay local, não via canon expansion. Suite Gap 9
baseline: **637 passing + 12 skipped** (+42 desde v1.2.0: 37 Gap 9 + 5
fix loop).

Próximo: PR #7 merged + considerar Gap 14 (preset coverage) e itens
deferred v1.2.x em `04-pending.md` (lenient local loader C1, re-detection
inline no Step 7.5 N2-a, ADR-suspension audit log N13, catalog_overlay
refactor N17, Gap GATE-INFRA-2 parametrização quando 2º consumer chegar,
Gap BOOTSTRAP-1 worktree-aware bootstrap).

### Histórico — v1.2.0 (2026-06-03)

v1.2.0 entregue. Gap 5 + power-review PR #2 R1 + schema_version fix
merged em `main`; tags `v1.2.0` (HEAD doc-sync) e `v1.1.0` (retro em
`859d528`) criadas. Loader cascade canon ∪ local com hard-fail em colisão;
`validate_card_yaml` + `validate_capability_labels` overlay-aware (CARD-008
conformity: conflicts-with aceita label OR card-name); reconfigure ganha
submenu `card-local`; init ganha Step 7.5 com 3-caminhos pra signals órfãos
(orphans agrupados por capability, `_count_needle_hits` respeita
`_SKIP_DIRS` — sem mais hang em monorepos). Cards canon: 20 → 22
(`retrofit-client` + `shared-preferences-prefs` com `legacy-marker: true`).
Nova decisão locked 28 (ADR append-only — não revisita prévia). Suite total
v1.2.0: 607 tests passing (rapid lane + integration/e2e). Itens deferred
v1.2.x anotados em `04-pending.md`: lenient local loader (C1),
re-detection inline no Step 7.5 (N2-a), ADR-suspension audit log (N13),
catalog_overlay refactor (N17). Histórico prévio (PR #1 R3) preservado
abaixo na timeline.

---

## TL;DR pra nova sessão

Cole este prompt no início da sessão nova:

```
Estou retomando feature-forge em ~/Documents/feature-forge/.
Leia, nesta ordem:
  1. docs/design/08-session-handoff.md (este doc)
  2. docs/design/01-decisions.md
  3. docs/design/06-command-surface.md
  4. docs/design/07-discipline.md
  5. docs/design/04-pending.md
Depois siga as instruções. Estou na Fase {N}.
```

---

## Estado atual (anchors)

```
~400 arquivos · ~52,500 linhas · 27 decisões locked + 7 direcionais (Fase 3.5) + 2 ADR append-only (Decisão 28, Gap 5; Decisão 31, Revisita 30 sandbox guard via sitecustomize.py)
v1.2-dev cumulativo (PR #4 CC gate + Phase 0 + R1.1 secrets + PR #8 forge qa CONF + pause/resume): **1113 passed** em main (pós PR #9) (baseline pré-PR #8: 847; +86 tests da CONF wave + pause/resume + review fixes); branch gate-infra-extract registra Gap 9 baseline 637 + CC gate +~63 + Phase 0 -1 justificado + secrets gate +~30 · 17 graph queries · 16 proposal kinds · 20 validators (inclui check_cyclomatic_complexity + check_secrets + validate_extension_feature) · 22 cards canon (+ overlay local)
```

| Categoria | Status |
|---|---|
| Phase 1 — schemas + filesystem | ✅ 100% |
| Phase 2 — UX roteiros + agent prompts | ✅ 100% |
| Phase 3 — templates + cards canônicos + preset | ✅ 100% |
| Phase 3.5 — refactor backend-agnostic + REST coverage | ✅ 100% |
| Phase 4 Wave 1 — foundation (bin + cli + utils + ui + persona) | ✅ 100% (16 arquivos, ~1440 LOC) |
| Phase 4 Wave 2 — state + integration (cards + memory + graph + inventory + mcp + vision) | ✅ 100% (28 arquivos, ~5400 LOC) |
| Phase 4 Wave 3 — commands handlers (13 módulos) | ✅ 100% (13 arquivos, ~6040 LOC). **Nota:** `forge implement` é stub manual em v1 — Apply Mode automatizado fica pra v2/Phase 6. |
| **Phase 4 total** | ✅ **57 arquivos, ~12880 LOC** |
| Phase 5 Wave A — hooks (8 .sh + 1 CI yml) | ✅ ~277 LOC |
| Phase 5 Wave B — validators Python (13 + 2 helpers) | ✅ 2622 LOC |
| Phase 5 Wave C — pytest suite (unit + integration + e2e) | ✅ ~3460 LOC, 258 passing |
| Phase 5 Cleanup — hooks install no init + 3 handlers ingest + validator tests | ✅ +838 LOC |
| **Phase 5 total** | ✅ **72 arquivos, ~6600 LOC, 258 tests passing** |
| **🎉 feature-forge v1.0 completa** | ✅ **~370 arquivos, ~28K LOC, 5 fases + cleanup** (2026-05-29) |
| v1.1 — Gap 1 (bugfix subtype) | ✅ shipped 2026-05-30 — `_VALID_SUBTYPES + ['bugfix']`, ticket-pattern detection, Wave B conditional, template intake-bugfix |
| v1.1 — Gap 2 (refactor subtype + non-product track) | ✅ shipped 2026-05-30 — `_VALID_SUBTYPES + ['refactor', 'spike', 'chore']` (refactor only completo), `non-product/{slug}/`, `check_no_behavior_change` validator, template intake-refactor |
| v1.1 — Gap 8 (blocked-on-external state) | ✅ shipped 2026-05-30 — L1 status enum, manual unblock via reconfigure |
| v1.1 — Gap 18 (reuse intelligence expansion) | ✅ shipped 2026-06-01 — 6 detection categories, schema v2, parser overhaul, gradle modules+deps, init Step 11.5+11.6, evolve dispatch, doctor check, incremental hook, forge plan integration. **+12.360 LOC, 55 arquivos, 20 unit tests novos.** |
| **🎉 feature-forge v1.1.0 completa** | ✅ **~379 arquivos, ~50.7K LOC, 458 tests passing (rapid lane)** (2026-06-01) |
| v1.1.0 — PR #1 bloqueadores resolvidos | ✅ shipped 2026-06-01 — 14 commits cobrindo C1–C4 (phase lock atomic O_EXCL, implement try/finally, `_reset_domain_tables` atomic, version bump 1.1.0) + A1/A2/A5/A6/A9/A12 (Swift `"""` brace counter, Groovy DSL parens, tie-breaker determinístico, root-level `test/` recognition, `forge plan` rc=130 em deferred) + review fixes (CR-01/CR-02/MD-01/HG-01/HG-02/HG-03). **+38 regression tests, total 458 (baseline 367 + 53)**. Detalhe em `CHANGELOG.md`. |
| v1.2 — Gap 5 (card local overlay) | ✅ shipped 2026-06-02 — Approach A: cascade canon ∪ local com hard-fail em colisão; validators overlay-aware; reconfigure submenu `card-local`; init Step 7.5 com 3-caminhos pra signals órfãos; cards canon 20 → 22 (`retrofit-client` + `shared-preferences-prefs` com `legacy-marker`). Decisão locked 28 nova (ADR append-only). Suite: 595 passing + 12 skipped. |
| v1.2 — Gap 9 (extends-feature mechanic) | ✅ shipped 2026-06-03 — re-escopado: extends-feature pattern leve product-derived (sem cards canon novos, sem mudança em platforms enum, sem upgrade de inventory schema); 4º caminho "Estender" em `forge plan` Cena 1; validator EXT-001..004; discipline §10 formaliza semantics; `shipped-at` writer em transição state=done. Multi-target watchOS/Wear/TV movido pra out-of-scope permanente. **+42 tests cumulativo (37 Gap 9 + 5 fix loop); total 637 passing + 12 skipped**. Detalhe em `CHANGELOG.md`. |
| forge qa (13º comando) | ✓ — entregue v1.2, 4 attack vectors + 4 scope targets + sandbox isolado |
| v1.2-dev — PR #8 forge qa hardening (2026-06-08) | ✅ merged main (PR #8) — CONF-001 (qa-report.json skeleton + finalize), CONF-002 (snapshot via hardlink/copy), CONF-003 (sandbox-breach + timeout → findings determinísticos), CONF-004 (pause/resume via checkpoint.json — fecha Gap QA-12), CONF-007 (e2e valida estrutura on-disk), CONF-008 (Revisita Decisão 30 — sitecustomize.py em vez de PYTHONSTARTUP). Novos módulos: `engine/qa/checkpoint.py`, `engine/qa/_common.py`. Conductor agora escreve `sandbox-results.json` após Phase 3 (ativa CONF-003 em produção). Suite: **847 → 933 passing** (+86 tests). Gaps novos: QA-14 (conductor contract), QA-15 (review findings deferidos M-1/M-3/L-1/L-2/L-4), QA-16 (utc_iso_z cross-engine sweep). |
| v1.2-dev — CC gate (PR #4) | ✅ merged main 2026-06-05 — `check_cyclomatic_complexity` multi-language (Kotlin/Swift/TS/Python via Detekt/SwiftLint/eslint/Radon); threshold per card override > workflow-config > defaults; 3-caminhos on-fail (refactor / override-justify / split-task); doctor categoria 13ª `cc-gate-tools`. 13 commits + ~63 tests novos (suite 630 → 693 collected pré-merge; 682 passed + 17 skipped pós-refinements; 688 passed + 17 skipped pós PR #4 review fixes D-006/D-008/D-009/F-006). |
| v1.2-dev — Phase 0 (gate-infra-extract) | ✅ extracted (`_gate_infra.py` + `_diff.py`) 2026-06-05 — refactor estrito sem behavior change: 7 commits extraem `DispatchResult`/`check_tool_available`/`dispatch_native_tool`/`render_config_with_placeholders`/`parse_overrides`/`apply_overrides` em `_gate_infra.py` + `DiffHunk`/`classify_range_against_hunks`/`extract_diff_hunks`/`git_staged_files`/`read_commit_body` em `_diff.py`; rename `cc_threshold_lookup` → `gate_threshold_lookup` e `cc_format_three_paths` → `format_three_paths_message` em `_common.py` (DEFAULTS_CC preservado). CC validator ~1127 → ~840 LOC compondo helpers. Suite 750 (baseline 751 - 1 justificado em T4). Destrava Wave R1+ (check_secrets/check_deps_cve/check_duplication/check_cognitive_complexity/check_dead_code/check_arch_rules/check_function_length_and_nesting). |
| v1.2-dev — Secrets gate (R1.1) | ✅ merged main 2026-06-05 — `check_secrets` per-stage split: gitleaks no per-task hook de `forge implement`, trufflehog `--only-verified` na cascade de `forge verify`. Posicionado após `check_cyclomatic_complexity` (fail-fast Decision 23 preservado). Override via `SECRETS-OVERRIDE: <file>:<line> kind=<token-type> — <razão>` no commit body. Hard-fail sempre; tool missing → warn; bypass `NO_SECRETS_GATE=1` logado em `.claude/state/secrets-gate-bypass.jsonl`. Composto inteiro da infra Phase 0 (2º consumer, prova que a extração paga). Validators 15→16, doctor 13→14 categorias (`secrets-tools`). 6 commits + ~30 tests novos. |
| v1.2-dev — Phase A DRIFT-1 intent protocol (branch `feat/drift-1-intent-protocol`) | ✅ shipping-ready 2026-06-10 — 21 commits sobre `1b1d289`. Engine deixa de ler stdin: emite intent em `.claude/state/forge-pending.json`, consome `.claude/state/forge-response.json`, exit code 2 = paused-for-input. Novos módulos: `engine/utils/json_io.py`, `engine/ui/intent_state.py`, `engine/ui/tty_bridge.py`. `bin/forge` dispatcher detecta TTY + `CLAUDECODE` env. 3 sentinels exportadas de `engine/ui/question.py` (`PausedForInputError` / `UserCancelledError` / `UserPausedError`); 10 per-subcommand checkpoint dataclasses (outcome C de W2.T0). Schema canônico em `docs/schemas/intent-protocol.md`. AC-1..AC-9 verificados em 15 integration + 3 e2e pty tests. Rapid lane 1151 passed / 11 skipped preservada. Aguardando push + PR. |

## REVIEW.md remediation — baseline (2026-06-12)

- **Branch:** `fix/review-md-remediation`
- **Spec:** `docs/superpowers/specs/2026-06-12-review-md-remediation-design.md`
- **Plan:** `docs/superpowers/plans/2026-06-12-review-md-remediation.md`
- **Pytest baseline:** `1500` tests collected (capturado via `pytest --collect-only -q`)
- **Lanes pra esta sessão:**
  - Bloco 1, 2, 3, 5: rapid lane (`pytest -m "not integration and not e2e"`) verde
  - Bloco 4: full lane (`pytest`) verde ao fim do bloco (cruza módulos críticos)

## Conhecidos limites v1.1 (atualizado)

A v1.1 entregue inclui o pipeline completo de planning + verify + memory + graph
+ reuse-intelligence + non-product feature track (refactor/bugfix). Limites
restantes ficam pra v1.2+ ou v2/Phase 6:

**v1.0 herdados (ainda válidos):**

- **`forge implement` não automatiza Apply Mode** — em v1 é um **stub manual**:
  `forge implement` renderiza Plan Mode (contract + allowed_files + gates) e
  emite handoff em texto. A edição dos arquivos é responsabilidade do usuário
  (ou da sessão Claude Code que está rodando o forge). Pre-commit Review
  automatizado, Atomic Commit com mensagem canônica, e detecção out-of-scope
  via hook real chegam em v2.
- **`forge init` Cena 7 (Jira/ticketing auth) não é prompted** — a configuração
  de provider de ticketing (Jira, Linear, GitHub Issues) sai com `provider=none`
  no `workflow-config.yaml` por default. Para configurar pós-init, use
  `forge reconfigure → ticketing`.
- **3 kinds de `apply_proposal_to_l2` ainda em fall-through** — `engine/memory/distiller.py`
  resolveu 6 kinds reuse-intelligence em v1.1, mas `tooling-update`,
  `card-version-bump` e `template-update` (entre outros retrospective kinds)
  continuam raise NotImplementedError até emergirem de uso real.
- **LLM/sub-agent hookup real** — `plan.py`/`implement.py` narram fluxo +
  renderam templates. Integração real com Anthropic API dentro do `forge`
  requer hooks + Claude integration (já documentado em §Out-of-scope abaixo).

**DET-3 master-review PR #11 (2026-06-10) — surfaced, não bloqueia merge:**

- **Assimetria TOML-exact vs build.gradle-substring** (consequência de M-1 do
  master-review, decisão deliberada Caminho A): signal `gradle-dep` compara
  `module == coordinate` por igualdade no passo TOML (`gradle/libs.versions.toml`)
  e usa substring no passo build.gradle (`**/build.gradle*`). Cards com
  coordenada base (ex.: `com.google.firebase:firebase-storage`) NÃO detectam
  variantes sufixadas (ex.: `-ktx`) em projetos TOML-only puros. Declare
  coordenadas explícitas por variante quando relevante. Documentado em
  `docs/schemas/card.md` §Signal types; FU-MR-1 (P3) em `04-pending.md`
  captura trigger pro schema-version bump quando demanda de `match: prefix`
  opcional emergir.
- **BOM em `libs.versions.toml` silenciosamente ignorado** (consequência
  observada em S-1.1 do master-review): `tomllib` stdlib rejeita BOM por
  aderir à TOML 1.0; helper `_load_toml_catalog` engole `TOMLDecodeError`,
  catálogo com BOM vira invisível ao scanner. Editores Windows às vezes
  salvam `.toml` com BOM. Sugestão futura: `forge doctor` warn pra catálogo
  com BOM. Anotado em `04-pending.md` FU-MR-3 (P3). Test de regressão
  `test_s1_toml_with_utf8_bom_silently_skipped` trava se helper algum dia
  strippar BOM — forçando revisita consciente.
- **retrofit-client family-match preservado**: `retrofit-client` continua com
  `file-content` substring `io.squareup.retrofit2:retrofit-` (captura
  `-converters-gson`, `-converter-moshi`, `-mock`). TOML-only puro ainda não
  detecta retrofit-client. Decisão deferida em FU-MR-2 (P3) — aceitar
  tradeoff vs adicionar wildcard sufixado quando 2+ cards de família-multipla
  pedirem.

**v1.1 novos (decisões deliberadas, não bugs):**

- **`kmp-migration-candidate` confidence é shallow** — token Jaccard sintático,
  não AST semântico. Pode flagar Swift function com nome igual a Kotlin shared
  mas semântica diferente. Mitigação: confidence 0.50–0.75 (manual review
  obrigatório), apply NUNCA auto-runs, rejection veto persiste.
- **Incremental detection hook wiring é manual** — `forge init` Step 11.6
  escreve `.claude/hooks/post-edit-detect-duplications.sh`, mas a referência
  em `.claude/settings.local.json` é **opt-in por design** — não modificamos
  settings.local.json automaticamente pra não surpreender o usuário.
- **Gradle dependency parsing** cobre `implementation(project(...))` e
  variantes comuns (`api`, `compileOnly`, `testImplementation`, etc.).
  `includeBuild`, DSL Kotlin avançado, ou versionCatalogs podem precisar
  extensão futura. Fallback: heurística estática (`:shared:core` como
  ancestor padrão pra cross-shared dups).
- **Spike + chore subtypes stubbed** — `_VALID_SUBTYPES` aceita `spike` e
  `chore`, mas só `refactor` tem flow completo (Gap 2 ship). Spike + chore
  caem no fluxo product por default; será implementado quando emergir.
- **MCP polling para external-dep resolution (Gap 8)** stubbed — v1.1 ship
  manual unblock via `forge reconfigure → external-deps`. Auto-polling via
  Jira/Linear webhook fica pra v1.2+.

**Rules system v1 (2026-06-01) — limites reconhecidos:**

- Per-tool-use Mandamento 0 detection é manual (depende de orchestrator obedecer regra textual). Hook bloqueante de main-vs-subagent depende de Claude Code expor distinção no hook protocol — anotado em `04-pending.md`.
- `forge audit-rules` (comando futuro pra verificar conformidade em git log) ainda não existe — anotado em `04-pending.md` pra v1.2+.
- Bloqueios opt-in (test-count regression, validator-cascade fail) estão documentados em `.claude/rules/doc-sync.md` mas comentados no script; ativar quando emergir necessidade real.

**Pré-existente em v1.1.0 (não bloqueia ship, fix agendado pra v1.1.1):**

- **`tests/integration/test_graph_build_meobonsai.py::test_build_full_creates_meta_schema_version`** assertava `meta.schema_version == "1"`, mas `engine/utils/sqlite_io.py:20` declara `SCHEMA_VERSION = "2"` desde o bump da reuse-intelligence schema (v1.1.0 Gap 18). Falha **não bloqueia** rapid lane (458 passing), `forge verify`, nem o ship v1.1.0 — só atinge a integration lane. Surfaced 2026-06-01 durante verification final do PR #1. Fix pequeno: ler `sqlite_io.SCHEMA_VERSION` em vez de hardcoded `"1"`. Gap completo em `docs/design/04-pending.md § Gaps pós-rules-system`.

**Round 2 surfaced (2026-06-02) — não bloqueiam merge do PR #1, agendados pra v1.1.1+:**

- **plan.py `phase_lock_held` CM migration deferred** — R2.7 (MD-03) migrou só `engine/implement.py` para `with phase_lock_held(...)`. `engine/plan.py` tem múltiplos deferred paths via `_persist_deferred` que precisam de brainstorm focado antes de migrar; happy path em `plan.py` (linha ~1108, `final_state`) seta `phase_lock=None` via `write_l1_status` mas **NÃO chama `release_phase_lock`**, deixando sentinel `.phase-lock` órfão no disco. Recovery manual: `rm .planning/<slug>/.phase-lock`. Fix proposto: chamar `release_phase_lock` no happy path antes da migração CM. Target v1.1.1.
- **A13 `IN`-clause >999 findings ceiling** (review IN-01) — `list_reuse_findings` agora usa `WHERE finding_id IN ({placeholders})` que falha com SQLite default `SQLITE_MAX_VARIABLE_NUMBER=999` se `findings > 999`. Chunking em batches de 500 quando relevante. Não atinge nenhum projeto conhecido hoje; target v1.1.2+.
- **`forge undo` coverage para reconfigure-external-deps** (review WR-01) — `_undo_reconfigure` em `engine/undo.py` não enumera per-task `.bak` files criados pelo loop de external-deps em `engine/reconfigure.py:754`. Recovery atualmente manual via `.bak` direto. Target v1.1.1.

**Gap 5 (card local overlay) surfaced (2026-06-02) — não bloqueia merge, target v1.2:**

- **Card local re-prompt** — fluxo `_card_local_add` em colisão de nome
  oferece 3-caminhos (rename / abort / listar) mas o "rename" não reabre
  o prompt do nome — encerra a operação. Gap pra v1.2; documentado em
  `docs/design/04-pending.md`.

**CC gate v1.2-dev surfaced (2026-06-04) — não bloqueia merge, target v1.2.1+:**

- **CC gate delta rule é structural-only (F-001)** — `CCResult.cc_before`
  existe como campo, mas todos os parsers seteam `cc_before=None`. A regra
  `cc_after > cc_before` nunca dispara. Implementar exige `git show
  <parent>:<file>` + re-run das 4 tools nativas sobre o estado anterior.
  Pré-requisito F-006 (rename detection `-M80%`) já está aplicado nesta
  Unreleased. Gap em `docs/design/04-pending.md § Gap CC-6`.
- **CC validator LOC bloat (F-003)** —
  `validators/check_cyclomatic_complexity.py` em 1067 LOC contra spec
  target 350-450 (≈2.4x). Refactor cross-cutting (extrair `_parsers/`,
  `_dispatch.py`, `_override.py`, `_classifier.py`) deferido pra
  piggyback na próxima feature substantial do validator. Gap em
  `docs/design/04-pending.md § Gap CC-7`.

**PR #8 forge qa v1.2-dev surfaced (2026-06-08) — não bloqueia merge, target v1.x+:**

- **Gap QA-14 — sandbox-results.json contract no qa-conductor.md**: CONF-003
  ativo mas dormente em produção sem conductor cooperante. Wave 4 já
  endereçou no `agents/qa-conductor.md`; restam runs reais pra validar
  serialização concreta no campo. Gap em `04-pending.md § Gap QA-14`.
- **Gap QA-15 — Findings deferidos do review CONF-004**: M-1 (SIGINT em
  Phase 0 deixa run_dir órfão), M-3 (find_resumable_run ignora scope_type
  → colisão `feature/login` vs `screen/login`), L-1/L-2/L-4 (style only).
  Cross-cutting; brainstorm separado. Gap em `04-pending.md § Gap QA-15`.
- **Gap QA-16 — `_utc_iso_z` duplicado em 10+ call-sites cross-engine**:
  M-4 do review CONF-004 consolidou apenas em `engine/qa/_common.py`.
  Sweep cross-engine (promover pra `engine/utils/timestamps.py` ou
  similar) é refactor dedicado. Gap em `04-pending.md § Gap QA-16`.
- **BOOTSTRAP-1**: `test_bootstrap_is_idempotent` falha em worktree (1
  test count drop em 933→932 quando rodado em worktree). Pré-existente;
  não introduzido por PR #8.

**feature-forge cobre mobile (Android + iOS + KMP) — scope-out
permanente (Gap 9 revisita 2026-06-03):**

- **watchOS, Wear OS, tvOS e multi-target retroativo são explicitamente
  out-of-scope permanente.** Não é "v1.x+" — é decisão arquitetural
  consciente, não TODO residual. Cards canon `watchos-screens`,
  `watchos-navigation`, `wear-os-screens`, `tv-screens` não virão; enum
  `workflow-config.platforms.active` permanece `[android, ios, kmp, web]`;
  `inventory.design-system.components.platforms` field não agrega valor
  sem multi-target; labels `watchos-*` / `wear-os-*` / `tv-*` não entram
  no catálogo nem como Reservada; `forge extend-feature {slug}` como
  verbo novo não vem (Decision 9 preservada — "estender" vive dentro de
  `forge plan` via 4º caminho conditional em Cena 1). Quando demanda
  improvável surgir, o caminho oficial é via **Gap 5 (card local
  overlay)** — não expansão prescritiva do canon. Demanda real teria
  que reabrir a revisita Gap 9 inteira. Documentado em
  `docs/design/04-pending.md §Gap 9 §OUT-OF-SCOPE explícito`.

**forge qa (13º comando) surfaced (2026-06-05) — não bloqueia ship,
target v1.2.x+:**

- **Auditores LLM dependem de Claude Code dispatch** — Phase 2 (generative
  auditors: spec-vs-spec, chaos, coverage, validator-claim) é invocada via
  Agent tool em contexto Claude Code. Engine standalone fora desse contexto
  não roda os 4 auditores LLM — só os auditores estáticos (Phase 1).
  Decisão arquitetural alinhada a "LLM hookup real é Phase 6" (v1.0 herdado),
  não bug. Documentado em `docs/superpowers/specs/2026-06-05-forge-qa-design.md`
  §6.2.
- **Greenfield retorna mensagem honesta sem 3-caminhos** — `forge qa` em
  projeto sem features planejadas retorna `state=greenfield, verdict=n/a`
  e explica que QA requer scope auditável (feature / screen / task /
  paranoid sobre algo concreto). Não oferece 3-caminhos porque "rodar QA
  vazio" não é caminho legítimo — é estado inicial honesto.

**Gap 9 (extends-feature mechanic) surfaced (2026-06-03) — não bloqueia
merge, target v1.2.x:**

- **`validate_extension_feature` wiring na cascade `forge verify`** —
  validator existe + roda standalone + 19 testes verdes, mas não está
  cadastrado em `engine/verify.py` cascade explícita. Decisão consciente
  no ship: cross-cutting validator com apenas 1 caso até hoje; cascade
  automatic em `forge verify` é refinamento que entra em v1.2.x quando
  o pattern "cross-cutting validator" tiver 2+ casos. Workaround atual:
  invocação manual ou smoke test. Documentado em
  `docs/design/04-pending.md §Gap 9 §TODO residual`.
- **Wave A skipping logic completo no conductor** — agent prompt da
  `planning-conductor` foi patchado (Phase 1 step 5 extension context
  import), mas execução real do skip de elicit no conductor (não
  re-perguntar user value / business outcome / persona herdados da pai)
  só é exercitada com piloto E2E real. Refinamento de prompt esperado
  pós-piloto.
- **Smoke test E2E real** — Mandamento "verde antes de pronto" cumprido
  via unit + integration (637 passing). E2E real (dummy parent feature
  done + `forge plan` + escolher Estender + verificar L1 + intake +
  validator) seria refinamento de fixture pra v1.2.x. Smoke manual
  documentado em `04-pending.md §Gap 9 §Validation pendente`.

**QA-11 sandbox hardening surfaced (2026-06-08) — não bloqueia ship, gap opt-in v1.2+:**

- **Grant revoke automático:** quando card com `qa-extensions.env-needs`
  é desinstalado, grant permanece em `workflow-config.qa.sensitive-env-grants`.
  Revoke é manual (editar config) ou via gap opt-in
  `forge reconfigure --revoke-grants` (não implementado v1.2).

**DRIFT-1 Phase A pós-master-review (2026-06-11) — não bloqueia merge, follow-ups registrados:**

- **Race detection sem hard lock** — protocolo é single-writer por
  design hoje; concurrency test em
  `tests/integration/test_intent_state_concurrency.py` documenta a
  TOCTOU window declarada no SPEC §9. Lock real via `fcntl.flock`
  deferido em FU-DRIFT-1-LOCK até race genuíno surgir em produção.
- **`_stable_intent_id` alias deprecated** — alias preserva 4 test
  files referenciando o nome antigo; remoção em v1.3 via
  FU-DRIFT-1-DEPRECATE-INTENT-ID-ALIAS.
- **Checkpoint shims de 1-linha** — 10 module handlers ainda têm
  wrappers preservando API pública dos tests. Deleção pós-DRIFT-2 OU
  v1.3 via FU-DRIFT-1-CHECKPOINT-CONSOLIDATE.
- **`engine/verify.py::_utc_now_iso()` microseconds** — não migrado
  para o shared `engine.utils.iso.utc_now_iso` (seconds-truncated)
  porque mudaria shape de checkpoint files do `forge verify`.
  FU-DRIFT-1-VERIFY-ISO mantém o gap aberto.

## Fase 4 — completa (resumo)

```
57 arquivos · ~12.880 LOC · 13 commands handlers + hidden ingest
Smoke-tests verdes: ./bin/forge --version, all handlers resolve via cli._resolve
```

Wave 3 entregue (13 arquivos):
- `engine/init.py` (953 LOC) — greenfield/brownfield install, backend-candidates, snapshot, merge, inventory, graph build, workflow-config writer
- `engine/plan.py` (604 LOC) — planning-conductor waves A-E com auto-resume + phase_lock
- `engine/implement.py` (625 LOC) — execution-conductor task-by-task, topo-sort, plan mode + apply stub
- `engine/verify.py` (432 LOC) — validator cascade fail-fast com 3-caminhos
- `engine/doctor.py` (593 LOC) — 11 health checks (full) / 3 (quick), .bak overdue, MCP probes
- `engine/status.py` (285 LOC) — read-only board 6 sections
- `engine/reconfigure.py` (~600 LOC) — single mutation entrypoint, 10 submenus, history.jsonl
- `engine/ingest.py` (~210 LOC) — hidden hook entry, key-value parse, exit 0 always
- `engine/raw.py` (~210 LOC) — escape hatch (verify-card, edit-config, rebuild-templates, forge-debug, migrator-N-to-M stub)
- `engine/evolve.py` (455 LOC) — single-by-single apply, L2 overflow pause, fingerprint veto
- `engine/undo.py` (497 LOC) — 7 targets menu, last default
- `engine/graph_cli.py` (203 LOC) — Q1-Q10 read-only menu
- `engine/memory_cli.py` (373 LOC) — inspect L1/L2/L3 + search + forget + distill + export

### Cleanup final Fase 4 (29 FOLLOWUPs fechados em 2026-05-29)

Todos os FOLLOWUPs das Waves 1-3 foram fechados em uma rodada final de 4 sub-agents paralelos.

**Wave 3 commands (10 itens):**
1. ✅ `init.py` cria `.claude/forge-version-lock.yaml` (Step 12.5)
2. ✅ `init.py` cria `.claude/.gitignore` auto-managed (Step 12.6)
3. ✅ `init.py` append primeira entry em `workflow-config-history.jsonl` (schema HIST-001..012)
4. ✅ `doctor.py` escreve `metadata.last-doctor-run` + `last-doctor-status` (única mutação documentada)
5. ✅ `verify.py` atualiza L1 status.json + grava `verify-log.jsonl` (schema MEM-L1-VL-001..005)
6. ✅ `verify.py` expõe `run_scope(scope_type, scope_id, project_root, *, interactive=False)` API
7. ✅ `ingest.py` `pre-commit` event invoca `verify.run_scope` real
8. ✅ `raw.py rebuild-templates` re-renderiza templates reais com merger
9. ✅ `undo.py` schema canônico `commit-sha` (40-hex) + fallback graceful pra legacy
10. ✅ `memory_cli.distill` handler real com single-by-single apply

**Wave 2a cards (5 itens):**
11. ✅ Parser real do `capability-labels.md` (40 labels carregadas dinamicamente, 16 singular, 3 latent) com cache lazy
12. ✅ CARD-011/012 cross-check com frontmatter dos agents — detectou e corrigiu 3 bugs reais (auth-jwt-bearer, ktor-client, swiftui-navigation)
13. ✅ Categorias canônicas reconciliadas (`card.md` ↔ cards reais)
14. ✅ `firebase-auth/card.yaml` confidence sum 2.1 → 1.5 (CARD-016 compliant)
15. ✅ `merger.render_merged_template` suporta setext headings (`===` / `---`)

**Wave 2b memory (4 itens):**
16. ✅ Filelock cross-platform Windows (`msvcrt.locking` LK_LOCK/LK_UNLCK)
17. ✅ `record_rejection` schema canônico completo conforme `rejected-evolutions.md`
18. ✅ `append_verify_log` com validação MEM-L1-VL-001..005
19. ✅ L2 buckets auxiliares tipados (`naming-extras`, `contradictions-resolved`, `promotion-candidates`)

**Wave 2c graph (4 itens):**
20. ✅ `.gitignore` parser real (wildcards, negação, nested) em `discover_source_files`
21. ✅ Populate 6 tabelas faltantes: `di_graph`, `ds_usage`, `i18n_usage`, `screens`, `routes`, `tests`
22. ✅ Concurrency lock com `busy_timeout = 5s` + `GraphError` em deadlock
23. ✅ `to_file_id` resolution em `imports` (ALTER TABLE + post-pass; 39% resolved no MeoBonsai)

**Wave 2d inventory (5 itens):**
24. ✅ JUnit5 detection (`org.junit.jupiter` / `useJUnitPlatform`)
25. ✅ `tailwind.config.{js,ts}` parser regex (colors, spacing, borderRadius, fontFamily)
26. ✅ Component level fallback heurística (LOC + imports → atom/molecule/organism)
27. ✅ AndroidManifest.xml parser (package, label, main_activity, permissions)
28. ✅ `features-analyzed` counter real (union de paths convencionais)

**Wave 2e mcp/vision (1 item):**
29. ✅ `engine/mcp/types.py` — dataclass `Ticket`, `TicketComment`, `normalize_status` cross-provider

### Out-of-scope (decisões arquiteturais, não FOLLOWUPs)

Itens explicitamente fora de Fase 4 (esperados pra Fase 5/6 ou v1.1+):

- **LLM/sub-agent hookup real** — `plan.py`/`implement.py` v1 narram fluxo + renderam templates. Integração real com sub-agents Anthropic dentro do `forge` requer hooks + Claude API integration → Phase 5/6 escopo
- **Tree-sitter / AST parsing real** — regex parsers v1 por design (decisão de simplicidade); upgrade só se false positives críticos aparecerem em campo
- **MCP real connections** (Jira/Linear/GitHub/Context7 com credentials reais) — Phase 5 escopo; tipos `Ticket`/`TicketComment` prontos pra consumo
- **iOS pbxproj proper parser** — regex pragmático suficiente; tratar como bug quando aparecer
- **Marketplace de cards user-contributed** — v1 só canonical cards; v2+ escopo

Detalhamento granular em `docs/design/04-pending.md`.

---

## Ordem canônica de leitura (cold-start mandatory)

1. **README.md** — overview e índice
2. **THIS handoff** — você está aqui
3. **docs/design/01-decisions.md** — 27 decisões locked (NÃO REVISAR sem explícito pedido do usuário)
4. **docs/design/06-command-surface.md** — 12 comandos canônicos, zero flags
5. **docs/design/07-discipline.md** — 7 disciplines universais
6. **docs/design/00-vision.md** — filosofia (6 layers, capability cards)
7. **agents/planning-conductor.md** — orchestrator template
8. **docs/design/04-pending.md** — o que falta fazer

Para trabalhar em um schema/agent específico, leia também o file correspondente em `docs/schemas/` ou `agents/`.

---

## Persona e voz (carrega isso antes de qualquer ação)

- **mentor calmo**: warm em exploração, firme em gates, didático, nunca apressado
- **100% conversacional, NUNCA flags** — toda parametrização via menu interativo
- **3-caminhos em todo gate violation** — sempre 3 opções, nunca 2, nunca 4
- **Never invent** — se não há fonte (ticket, screenshot, memory, card default, codebase), marca `needs-elicitation`
- **PT-BR primário** — espelhar idioma do usuário quando ele usa outro

---

## Contexto crítico que NÃO está nos docs

Coisas decididas em auto-mode durante a sessão de design (já refletidas nos docs, mas que poderiam parecer revisáveis):

| Decisão | Por quê não revisar |
|---|---|
| 13 comandos LOCKED | Decision 9 revisitada 2026-06-05 (Revisita Decisão 9 — `forge qa` adicionado como 13º). Adicionar um 14º ainda quebra tudo. Roteie por entrypoints existentes via menu. |
| `forge ingest` = hidden machine-only | Chamado só por hooks. Não conta nos 12. Não é typed pelo usuário. |
| Card management = `forge reconfigure` interactive | Não existe `forge card add/remove/upgrade`. Tudo via menu. |
| Migrations = `forge raw migrator-N-to-M` | `raw` é o escape hatch oficial. |
| L2 distill = automático OU menu de `forge memory` | Não existe `forge memory distill` standalone. |
| Auto-resume em `forge plan {slug}` / `forge implement {slug}` | Sem flag `--resume`. Detecta state e segue. |
| Sub-agents usam `model: sonnet` | Só planning-conductor usa opus. |
| `phase_lock` dual: agent-scoped (intake, prd, etc.) ou task-scoped (TASK-NNNN) | Documentado em memory.md §phase_lock canonical form. |
| Strictness matrix 14/10/5 enumerada | Documentada em workflow-config.md §strictness-matrix. |
| Extension-points formalizados nos frontmatters dos agentes | Não tem doc separado de registry — agente declara seu próprio. |

---

## Padrão de operação do usuário (importante)

| Aspecto | Preferência |
|---|---|
| Comandos curtos | "mete marcha", "continue de onde parou", "vai" — quer ação, não dúvida |
| Auto-mode | Quando ativo, fazer call razoável sem perguntar; redirect explícito vem do usuário |
| Sub-agents em paralelo | Dispatchar múltiplos quando os escopos não conflitam |
| Tipo de sub-agent | `general-purpose` (não usar os especializados a menos que perfeitamente alinhado) |
| Idioma | PT-BR no chat; mix EN+PT em docs OK |
| GitHub user | `thgMatajs` |
| Project home | `~/Documents/feature-forge/` (não `~/Code/`) |
| Outro projeto-alvo | Também KMP Android+iOS (modularizando agora) |
| TaskCreate | Geralmente skip — o usuário não pede tracking detalhado |

---

## Polish TODOs deferidos (não-bloqueantes, podem ser feitos junto com Fase 3)

1. **Bidirectional cross-links em 07-discipline §"Referenced from"** — cada doc alvo (roteiros, schemas, agents) deveria ter backlink → §X de 07-discipline
2. **Worked example multi-feature em retrospective-agent.md** — mostrar mesmo proposal evoluindo em 3 features com fingerprint mudando
3. **ASCII state-transition diagram em 07-discipline §7** — atualmente texto; diagrama clarifica pause vs deferred vs aborted
4. **`forge status`, `forge graph`, `forge memory`, `forge undo`, `forge raw` roteiros** — não escritos individualmente (são mais CLI-utility-style). Decidir: roteiros próprios ou 1 doc consolidado "CLI utility commands"?

---

## Anti-patterns conhecidos (não repetir)

| Anti-pattern | Por quê foi rejeitado |
|---|---|
| Adicionar 13º comando "pra conveniência" | Quebra decision 9. Use menu interativo em entrypoint existente. |
| Adicionar flag "só pra esse caso" | Quebra decision 10. Substitute por prompt interativo. |
| Inventar paths de arquivo | Pull de `inventory/conventions.yaml` + `paths.feature-roots`. |
| Auto-apply em memory L2 | Decision 26: review-and-apply via `forge evolve`. Nunca silencioso. |
| Skip 3-caminhos em gate violations | Universal discipline §1 de 07-discipline. Sempre 3 paths. |
| Sub-agent "decidir" produto/arquitetura | Sub-agents só executam decisões do conductor + user. |
| Stub artifact quando input é thin | Falhar com 3-caminhos é melhor que stub. |
| Drill-down infinito em pergunta vaga | Cap em 2 rounds. Decision 27 + planning-conductor §drill-down. |
| Mudança de preset via `reconfigure` | Decision 06-command-surface.md: preset change exige fresh `forge init` em branch dedicada. |

---

## Fase 3 + 3.5 — concluídas (resumo)

**Entregue Fase 3 (sessão 2026-05-29 manhã):**

```
Templates × 16  →  ~/Documents/feature-forge/templates/   ✅
Cards × 12      →  ~/Documents/feature-forge/cards/{name}/ ✅
Preset (inicial) → presets/kmp-mobile-firebase/           ✅ (depois arquivado em 3.5)
```

**Entregue Fase 3.5 — refactor backend-agnostic (sessão 2026-05-29 tarde):**

Motivação: v1 não pode assumir Firebase como o backend canônico — projetos reais usam REST mais frequentemente. Sem MVP, esta é a versão final.

```
Capability labels catalog → docs/schemas/capability-labels.md ✅ (35 labels, 9 famílias)
Cards Firestore split (3) → firestore-persistence/realtime/security-rules ✅
Cards Firebase patched (3) → firebase-auth (capabilities) + spot-check storage/crashlytics ✅
Cards REST novos (6)    →  ktor-client, rest-api-contract, kotlinx-serialization-json,
                            room-database, datastore-prefs, auth-jwt-bearer ✅
Templates refatorados (3) → data-contract-spec, tech-spec, test-strategy (agnósticos) ✅
Agents patchados (3)    → contract-planner, tech-spec, task-contract-writer ✅
Preset refactor          → kmp-mobile-firebase arquivado; kmp-mobile criado (só stack) ✅
docs/design patches      → 04-pending (Fase 3.5 entry), 05-filesystem-layout (cards/presets),
                            08-handoff (este doc) ✅
```

**7 decisões direcionais da Fase 3.5 (locked):**

| # | Decisão | Onde mora |
|---|---|---|
| D1 | Cobrir REST completo na v1 (não v1.1) | 6 cards REST novos |
| D2 | Refatorar Firebase em cards menores | split de firebase-firestore em 3 |
| D3 | Sem preset híbrido; cards livres em cima de kmp-mobile | preset kmp-mobile-firebase deletado |
| D4 | Split `firebase-firestore` em 3: persistence + realtime + security-rules | cards/ |
| D5 | Persistence local: Room (2.7+ KMP-stable) + DataStore | room-database + datastore-prefs |
| D6 | Preset `kmp-mobile-firebase` arquivado; só `kmp-mobile` base | presets/.archived/ |
| D7 | `realtime-stream` como capability formal | capability-labels.md |

## Fase 3 — fluxo de entrega (resumo histórico)

**Entregue na Fase 3 inicial (substituído/refinado pela Fase 3.5):**

```
Templates × 16  →  ~/Documents/feature-forge/templates/   ✅
Cards × 12      →  ~/Documents/feature-forge/cards/{name}/ ✅ (102 arquivos)
Preset manifest →  ~/Documents/feature-forge/presets/kmp-mobile-firebase/preset.yaml ✅ (arquivado em 3.5)
```

**Estratégia usada:**
- Templates: 3 batches sequenciais (Wave A+B narrativos / Wave B contract YAMLs / Wave C+D+E execution). Overlap de schema base resolvido inline (cross-references entre templates implementadas).
- Cards: 12 sub-agents `general-purpose` em paralelo. Cada um briefed com (a) catálogo canônico de capability labels inline, (b) referência viva ao MeoBonsai, (c) extension-points conforme frontmatters reais dos agents.

**Convenção canônica estabelecida em Fase 3:**
- **snake_case** em todos os YAML/JSON dos templates (`schema_version`, `feature_slug`, `generated_by`, `generated_at`)
- IDs: `SC-{NNN}` (BDD), `TASK-{NNNN}`, `Q-CP-{NN}` (open questions), `BE2E-{NNN}` (backend e2e)
- Cross-references: `screen_id`, `route_key`, `entity_name`, `event_name`, `test_id` conectam artefatos
- Fingerprints sha256 canonical-form per `07-discipline.md §4`

**FOLLOWUPs deferidos (não-bloqueantes p/ Fase 4):**

Lista completa em `04-pending.md § Fase 3 — FOLLOWUPs herdados`. Highlights:

- snake_case vs kebab-case mismatch entre agent prompts e templates — alinhar agent prompts
- `contract-planner-agent` sem extension-points no frontmatter (só tabela em §5) — padronizar
- `screen-analysis-agent` sem extension-points formais — definir
- Capability label catalog inline-only — criar `docs/schemas/capability-labels.md` em v1.1
- Labels úteis fora do v1 (`hilt-di`, `android-xml-views`, `ios-ui-uikit`, `navigation2-android`, `material3`) — decidir v1.1
- `card.md` schema cita extension-point exemplo (`section:Language Conventions`) que não existe no agent real — atualizar exemplo
- `evals.template.json` vs `evals/evals.json` — alinhar convenção de path

---

## Estrutura física do repo

```
~/Documents/feature-forge/
├── README.md
├── INFLUENCES.md
├── .git/                              (inicializado, sem commit ainda)
├── docs/
│   ├── design/      (8 docs: 00-vision, 01-decisions, ..., 08-handoff)
│   ├── schemas/     (8 docs: workflow-config, card, memory, graph, ...)
│   ├── ux/          (7 roteiros: init, plan, implement, ..., evolve)
│   └── lifecycle/   (1 doc: memory-and-graph)
├── agents/          (10 prompts: planning-conductor + 9 sub-agents)
└── presets/
    └── kmp-mobile-firebase/README.md  (placeholder)
```

Criado em Fase 3 + 3.5:
```
├── templates/                          ✅ (16 templates, 3 refatorados em 3.5)
├── cards/                              ✅ (17 cards canônicos ativos + 1 arquivado)
│   ├── kotlin-language/
│   ├── kmp-shared/
│   ├── compose-screens/
│   ├── swiftui-screens/
│   ├── koin-annotations/
│   ├── skie-bridge/
│   ├── nav3/
│   ├── swiftui-navigation/
│   ├── firebase-auth/                  (capabilities atualizadas em 3.5)
│   ├── firestore-persistence/          (NOVO 3.5)
│   ├── firestore-realtime/             (NOVO 3.5)
│   ├── firestore-security-rules/       (NOVO 3.5)
│   ├── firebase-storage/
│   ├── crashlytics/
│   ├── ktor-client/                    (NOVO 3.5)
│   ├── rest-api-contract/              (NOVO 3.5)
│   ├── kotlinx-serialization-json/     (NOVO 3.5)
│   ├── room-database/                  (NOVO 3.5)
│   ├── datastore-prefs/                (NOVO 3.5)
│   ├── auth-jwt-bearer/                (NOVO 3.5)
│   └── .archived/firebase-firestore-monolithic/
├── docs/schemas/capability-labels.md   (NOVO 3.5 — 35 labels v1)
└── presets/
    ├── kmp-mobile/                     (NOVO 3.5 — só stack, backend livre)
    └── .archived/kmp-mobile-firebase-pre-3.5/
```

Pendente criar (Fase 4+):
```
├── bin/forge        (Phase 4 — Bash dispatcher)
├── engine/          (Phase 4 — Python engine)
├── hooks/           (Phase 5 — hook scripts)
├── validators/      (Phase 5 — Python validators)
└── tests/           (Phase 5 — E2E)
```

---

## Como retomar limpo

1. Abra sessão nova
2. Cole o TL;DR prompt do topo deste doc
3. O agent novo lê os 5 docs canônicos (handoff + decisions + command-surface + discipline + pending)
4. Diz onde você quer continuar
5. Auto-mode dispatch dos sub-agents da fase escolhida

---

## Como atualizar este handoff

Toda vez que terminar uma fase ou tomar decisão arquitetural em auto-mode, **atualize este doc**:

- Mover phase de pendente → concluída na tabela de estado
- Adicionar novas decisões em "Contexto crítico que NÃO está nos docs"
- Atualizar Polish TODOs (riscar feitos, adicionar novos)
- Atualizar Anti-patterns se um novo foi tentado e rejeitado
- Anotar nova preferência do usuário se surgir

**Não duplicar conteúdo dos outros docs aqui** — este é um índice + nuances de sessão, não substituto de leitura.

---

## Última coisa: o que NÃO é este projeto

- Não é PRD/product. Não estima tempo. Não decide produto.
- Não é code review final. Detecta violações; veredito final é humano.
- Não é IDE plugin. É CLI-first.
- Não é skill auto-installer pra outros projetos (ainda). Snapshot copy manual via `forge init`.
- Não é hosted service. Tudo local; só MCPs externos (Jira, Context7) quando configurados.
