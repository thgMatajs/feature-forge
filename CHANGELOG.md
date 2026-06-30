# Changelog

Todas as mudanças notáveis no feature-forge.

Formato baseado em [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versionamento: [SemVer](https://semver.org/lang/pt-BR/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `forge upgrade` avisa (não-fatal, stderr) em flag desconhecida em vez de ignorá-la em silêncio (Fase 1 Track B, B1).

### Added

- feedback de progresso (spinner) nos steps longos do `forge init` — backend (~86s) e orphan-scan (~75s); GATEADO por `_is_tty` (no-op puro fora de TTY, sem poluir o transcript IA-first) (Fase 1 Track D, D1; fecha item P2 16).

### Changed

- discovery cache do `forge init` ganha content-fingerprint top-level (invalida fora do replay mecânico) — hardening cinto-e-suspensório sobre o lifecycle de checkpoint (Fase 1 Track B, B2; fecha BUG-2 follow-on).
- `forge init` brownfield computa `compose_backend_axes` uma única vez (era 2× por fase no hot-path) — `_handle_backend_multi_axis_brownfield` aceita `composer_result` pré-computado; no-behavior-change confirmado; docstring de `_handle_backend_multi_axis_brownfield` corrigido (estava stale: "só pelo integration test" — a função está no hot-path ativo via `_run_pipeline`) (Fase 1 Track B, B3; fecha BUG-1b — CAMINHO A confirmado empiricamente).

### Changed (load-bearing)

- Nova decisão 33: o engine pode executar binários externos do projeto
  consumidor (linters, build tools) via uma fronteira de execução dedicada,
  distinta do sandbox de validators da Decisão 30. Garantias: modo check
  read-only onde aplicável; env reduzido (build_safe_env); timeout por gate com
  estouro → degraded; skip-se-ausente; sem auto-fix; sem instalar toolchain. A
  Decisão 30 segue valendo integralmente pro sandbox de validators — a 33 é
  fronteira separada, não afrouxa a 30.
- Hook `.claude/hooks/pre-commit-feature-forge.sh` e check **C1** do plan-auditor
  (`.claude/rules/plan-auditor.md` + nota `mem`) agora reconhecem "Nova decisão N"
  (decisão nova) como cerimônia de primeira classe, além de "Revisita decisão N"
  (decisão existente). Espelha o hook estendido pela Decisão 33; evita
  falso-positivo Critical em auditorias de decisões novas.

### Changed

- `docs/design/04-pending.md`: o follow-on "impl de gates-nativos (Tema 6, face 2)"
  deixa de dizer "pode exigir Decisão 33" — a Decisão 33 foi tomada nesta fase,
  destravando a impl da Fase 1.

### Fixed

- `engine/memory/l1.py::append_verify_log`: guard VL-003a — `scope` não-str
  (ex.: dict) agora levanta `MemoryError` canônico com mensagem VL-003 antes do
  membership test no set `_VERIFY_SCOPES`, evitando `TypeError: unhashable type`
  cru. Cobre o caminho de drift documentado em `test_verify_log_write_paths.py`
  (Fase 0 cleanup, Fix #6).

- `engine/verify.py::_write_verify_log_entry` agora roteia pela fronteira
  validada `engine/memory/l1.py::append_verify_log` (Fase 0c, campanha AI-first).
  Antes serializava JSON DIRETO, bypassando a validação MEM-L1-VL-001..005:
  gravava `scope` como dict `{"type","id"}` e `warnings` como list — formas que
  `append_verify_log` rejeita (o dict chega a estourar `TypeError` no membership
  test do set `_VERIFY_SCOPES`). A investigação (`superpowers:systematic-debugging`)
  confirmou que os DOIS write-paths escreviam no MESMO arquivo
  (`lifecycle_root/slug/verify-log.jsonl`), então a assimetria era drift real. A
  consolidação mapeia `scope` → string validável + `scope-id` preservado, e
  `warnings` → contagem int (VL-005) com a lista humana sob `warnings-list`.
  Guardas: `tests/engine/test_verify_log_write_paths.py` (investigação) +
  `tests/engine/test_verify_log_consolidation.py` (regressão).

### Added

- Native gate ktlint no `forge verify` (Tema 6, Decisão 33, Fase 1 Track A1):
  `./gradlew ktlintCheck` em modo check read-only, guard de stack FR-02 (só roda
  em projetos com `platforms.active` contendo `android` ou `kmp`). Violação é
  informativa (`warn`, exit 0) por default; opt-in `fail-on-violation: true` sobe
  `warn→fail`; tool ausente → `skipped`; timeout → `degraded`. Config em
  `native-gates.ktlint`. Implementado em `engine/verify.py::_run_ktlint_gate`;
  guarda `tests/engine/test_verify_native_gates.py` (8 testes, inclui FR-04
  early-return).

- Build-only no `forge verify` (Tema 6, Nível 1, Decisão 33, Fase 1 Track A2):
  `./gradlew assembleDebug` (android/kmp) / `xcodebuild build` (ios) conforme
  `platforms.active`; web sem build-only no Nível 1. Reusa o step de gates externos
  de A1 (`_run_native_gates` / `_map_external_result` / `resolve_invocation`).
  Informativo por default, opt-in `fail-on-violation`, skip-se-ausente, timeout →
  `degraded`. O build escreve artefatos no working tree (esperado; forge não
  versiona/limpa). Config em `native-gates.build`.
  Implementado em `engine/verify.py::_run_build_gates` / `_build_candidates`;
  guarda `tests/engine/test_verify_build_only.py` (13 testes, inclui FR-01/02/03).

- FR-01 fix em `_map_external_result`: mensagem agora é condicional a
  `fail_on_violation` — quando `true`, diz "fail-on-violation: true — feature
  reprova" (antes dizia "informativo; não reprova por default" mesmo ao reprovar).

- FR-02 guard de stack compartilhado (`_ktlint_applies`): ktlint só roda quando
  `platforms.active` tem `android`/`kmp`; stack desconhecida (active vazio ou
  ausente) → tenta (conservador). Evita verde inerte em repos não-Kotlin com
  ktlint no PATH.

- FR-03 removido import `os` morto de `tests/engine/test_verify_native_gates.py`.

- FR-04 adicionado teste `test_run_scope_early_return_skips_native_gates`:
  validators=[] aciona early-return sem chamar gates nativos (comportamento Nível 1
  documentado — gates acompanham cascade).

- `engine/external_exec.py` — fronteira de execução externa genérica (Decisão
  33): `run_external_tool(argv, project_root, *, timeout)` roda binário do
  consumidor com env reduzido (`build_safe_env`), `check=False`, timeout com
  estouro → `degraded`; `resolve_invocation(candidates, project_root)` descobre
  o binário (wrapper `./...` → path de config → `which`) com skip-se-ausente
  (`None`). Base reusada pela Fase 1 (Tema 6 — gates nativos + build-only). Nada
  tool-específico mora aqui.

- Novo 5º vetor core `impl-vs-spec` no `forge qa` (Onda 1b da remediação do
  piloto MeoBonsai — fecha o gap do Tema 6 "qa red-teia contratos, não a
  impl"): o vetor snapshota a implementação real via os `allowed_files` dos
  task contracts e roda um auditor Phase-1 static que confronta a impl contra a
  spec (`agents/qa-auditor-impl-vs-spec.md`). Antes, o `qa` red-teava só os
  contratos/plano; agora cobre também o código produzido. Helper de snapshot em
  `engine/utils/task_contract.py`; ingest/synthesis do qa estendidos; schemas
  e templates `qa-finding`/`qa-report` atualizados.
- Duas specs de design adicionadas (implementação DEFERIDA pras suas próprias
  ondas/decisões): `docs/superpowers/specs/2026-06-30-native-quality-gates-design.md`
  (gates de qualidade nativos — pode exigir Decisão 33) e
  `docs/superpowers/specs/2026-06-30-runtime-visual-verification-design.md`
  (verificação runtime/visual). Só a spec; a impl é follow-on registrado em
  `docs/design/04-pending.md`.

- `engine/integrations/mem.py::mem_inbox_reject` — wrapper degrade-soft sobre
  `mem inbox reject <id>`.

- `mem_inbox_add` — wrapper sobre `mem inbox add` na camada de integração
  (`engine/integrations/mem.py`). Argv: `inbox add --type mem_type -t title
  [opcionais] --origin origin -- body`. Separador `--` antes do body é
  obrigatório (lição W-RULES). Degrade soft via `_run_or_degrade` (W-ROUTE 6b).

- `forge init` vendoriza o mem no consumidor: copia o asset embutido pra
  `.claude/bin/mem` (executável), roda o scaffold do mem (gitignore `mem.db*`,
  índice no `AGENTS.md`) via a fronteira `mem_call`. `forge doctor` ganha a
  categoria `mem` (saúde via `mem doctor` + drift do pin vendorizado vs asset).

- Relatório-mãe do piloto end-to-end do forge contra o MeoBonsai (KMP) persistido em `docs/reports/2026-06-25-piloto-meobonsai-gaps.md` — gaps IA-first priorizados P0/P1/P2, scorecard dos 14 comandos, 8 temas cross-cutting, registro completo de bugs e fixes já aplicados. Síntese durável dos 11 relatórios por-comando que eram efêmeros (scratchpad da sessão do piloto).
- mem vendorizado em `.claude/bin/mem` (asset pinado v0.8.1) + scaffold `.claude/memory/` + skills do mem (`mem-resume`/`mem-consolidate`/`mem-report`) — substrato de memória do dogfood da Fase 0. O `mem init` também adicionou `.claude/memory/mem.db*` ao `.gitignore` (índice SQLite derivado, não versionado) e criou um bloco rule-índice delimitado em `AGENTS.md` na raiz. Nenhuma migração de conhecimento aqui — só o substrato vazio (`mem stats` → `total: 0`); a curadoria Tier-0/Tier-1 vem nas tasks seguintes.
- Decisões/disciplinas/pending/handoff/learnings espelhados no acervo mem (aditivo; os canônicos `docs/design/*` preservados intactos) — Fase 0 dogfood (T5). As 33 decisões de `01-decisions.md` (rows 1-32 + 18-v2, com `tag:superseded` nas supersedidas e `importance 4-5` nas 8 load-bearing), as 10 disciplinas de `07-discipline.md` (as 6 universais com `tag:universal`), os 7 gaps abertos de `04-pending.md`, o estado curado v1.6.1 de `08-session-handoff.md` (via `mem session`) e os 27 learnings duráveis da auto-memory (24 feedback + 3 reference, preservando Why/How-to-apply + links cruzados). Migração só por `mem add`/`mem session` (acervo `total: 45 → 123`, zero near-dup). Os `docs/design/*` permanecem como fonte de verdade load-bearing com enforcement acoplado; o mem é o espelho recuperável que destrava o enxugue do núcleo injetado na T6.
- Hooks do mem instalados no `.claude/settings.json` via `mem install-hooks --apply` (Fase 0.5 — P2): `Stop`/`UserPromptSubmit` (eventos novos pro repo) + `SessionStart`/`PostToolUse` somados aos do forge. Merge aditivo verificado (gate de coexistência): os hooks do forge — `session-start-orientation`, `pre-tool-use-load-bearing`, `post-edit-doc-drift` — continuam registrados e funcionais; `PreToolUse` fica só do forge (mem não o registra). Continuidade via `checkpoint` (singleton mantido pelos hooks do mem) + consolidação via skill `mem-consolidate` passam a ser a prática canônica.

- Novo intent-kind `classify` (Fase 1 W-RULES, ADITIVO): o engine emite um
  pending `kind:"classify"` com `fragments` (fragmentos de text das rules do
  consumidor) + `classification-schema`; o host-LLM fulfilla escrevendo
  `forge-response.json` com `classification:[{fragment_id, tier:int, rationale,
  mem_note?}]`. `tier 0` = invariante always-on (gates, enforcement,
  "NUNCA/sempre"); `tier 1` = detalhe recuperável → mem. `TtyAdapter` retorna
  `None` (host sem LLM) — `_reduce_rules` pula com aviso (fallback honesto
  H-101). Schema: `docs/schemas/intent-protocol.md §classify`. Driver:
  `skills/feature-forge/SKILL.md §Fulfillment do intent classify`.

- `forge init` ganha passo de redução de rules do consumidor (`_reduce_rules`,
  Fase 1 W-RULES): após o vendoring do mem, o init lê `.claude/rules/` +
  `CLAUDE.md`, fatia por heading, emite um `classify` intent e exibe proposta
  em 3-caminhos (G1 aceitar / G2 ajustar / G3 pular). Ao aceitar: `mem add`
  de todos os tier-1 (verificado — sem `.bak` nem trim se algum falhar), depois
  `.bak` imediato de cada arquivo tocado (Decisão 24), depois trim — substituindo
  o conteúdo tier-1 por ponteiro `mem find`. Revisão (M-202): caminho G2 re-emite
  `classify` com `revise:true` + `prior`, novo `intent-id` (sem colidir com o
  anterior); máximo 3 rodadas. Greenfield sem rules e consumidor com sentinel
  `.rules-reduced` (sem `--force`) pulam sem efeito.

- `mem_context_hint(project_root, query, *, limit) -> str | None` — helper
  compartilhado em `engine/integrations/mem.py`. Compõe sobre `mem_find` de 6a;
  retorna bloco de texto compacto com hits ou `None` em degrade (W-ROUTE 6c).

- `forge plan` / `implement` / `verify` / `qa`: leem `mem_context_hint` antes
  de agir; resultado alimenta context-pack/handoff/hint educacional por handler
  (D1 do design 6c). Handler-only: validators nunca recebem contexto de mem.
  Degrade soft em todos os handlers: mem ausente → sem crash, sem "forge init" nag.

- Placeholder `{{mem_context_hint}}` nos 3 templates de Wave A
  (`feature-intake.template.md`, `feature-intake-bugfix.template.md`,
  `feature-intake-refactor.template.md`) + input `memory-mem-hint` documentado em
  `agents/feature-intake-agent.md` — consumidor real do read de `forge plan` (sem
  o placeholder o token seria descartado no `re.sub`) (W-ROUTE 6c).

- `tests/unit/test_validators_determinism.py`: teste estático parametrizado que
  garante que nenhum módulo em `validators/` importa ou chama funções de
  `engine.integrations.mem` (W-ROUTE 6c — invariante de determinismo).

- `tests/unit/test_engine_plan_mem_hint.py`: prova que o hint chega ao artefato
  RENDERIZADO da Wave A (não só ao dict de tokens) (W-ROUTE 6c).

### Docs

- Gaps do piloto MeoBonsai (2026-06-25) catalogados em `docs/design/04-pending.md`
  (seção nova "Piloto MeoBonsai 2026-06-25 — gaps", status verificado pós-merge
  Fase 1). Os ~37 bugs do report viviam só no relatório e nunca tinham entrado no
  backlog ativo; agora estão agrupados em Fechados / Parciais / Abertos (P0/P1/P2)
  com file:line e direção de fix. Verificação empírica fechou BUG-A, Tema 7
  (implement DAG), BUG-MEM-1/2 e BUG-1 — que o report tratava como abertos.
- Apêndice de status no fim do report
  `docs/reports/2026-06-25-piloto-meobonsai-gaps.md` (append-only; corpo histórico
  intacto): registra o que mudou desde o piloto, verificado contra o código de
  main pós-PR#32, e corrige explicitamente os itens que o report tratava como
  abertos e hoje estão fechados.
- Nova spec de remediação `docs/superpowers/specs/2026-06-29-pilot-remediation-design.md`:
  organiza os gaps ABERTOS em 5 ondas (correctness → gates com dentes → P0s
  estruturais → hardening P1 → mem Fase 2), lideradas pelo loop de correctness,
  cada onda com gate de aceite testável.

### Removed

- `agents/memory-distiller.md` — agente órfão; a compressão de L2 perdeu sentido
  pós-mem (o `mem evolve` gere o tamanho do acervo) e nada o despachava. Desvio
  consciente da spec §Re-roteamento (que previa repurpose pra gerador de inbox —
  descartado por duplicar o retrospective-agent + a skill mem-consolidate)
  (Onda 7 / W-AGENTS).

- `engine/memory/distiller._apply_consolidate_l2` — dead code após 6b (branch
  `consolidate-l2` roteado via `_KNOWLEDGE_KINDS → mem_inbox_add`). Removido
  em 6c após grep-confirm de zero caller (W-ROUTE 6c orphan-cleanup).

- `engine/memory/l2.add_entry` — write-path órfão de conhecimento após 6b.
  Nenhum engine code chamava a função após o re-roteamento dos 3 branches de
  L2-knowledge pro mem inbox. Removida de `l2.py` e de `__all__` (W-ROUTE 6c).

- Imports órfãos de `add_entry` e `L2Entry` em `engine/memory/distiller.py` —
  `add_entry` perdeu o call-site em 6b; `L2Entry` era usado apenas em
  `_apply_consolidate_l2` (deletada). Ambos removidos (W-ROUTE 6c).

### Changed

- Conductor prompts (feature-prd-agent, planning-conductor, contract-planner-agent,
  retrospective-agent) consultam o acervo via `mem find` em vez do `L2-project.yaml`
  abandonado (Onda 7 / W-AGENTS). Write-path inalterado — proposals seguem via
  `proposed-evolutions.yaml` → `forge evolve` → `mem inbox add` (knowledge kinds).

- `forge evolve` (knowledge proposals): aprovação de `promote-to-l2` /
  `l1-to-l2-promotion` / `consolidate-l2` agora emite `mem inbox add` em vez
  de escrever direto no L2 (anti-envenenamento G11). O conhecimento entra na
  fila de inbox do mem e fica disponível via `mem evolve` / `mem inbox promote`
  (W-ROUTE 6b).

- `forge status` (seção memory): linha de L2-size substituída por resumo de
  `mem stats` (total/live/stale/by_type). Payload JSON ganha bloco
  `memory.mem`. Degrade soft se mem indisponível (W-ROUTE 6b).

- `forge memory` reescrito como wrapper fino arg-driven sobre o `mem`
  vendorizado (`search`/`inspect`/`export`/`distill`), stateless — elimina
  o checkpoint-resume do DRIFT-1 (BUG-M1). Inspeção de lifecycle move pra
  `forge status`; L3 e `forget` por-id removidos (W-ROUTE 6a).

- ADR-note Decisão 22 (sem dep runtime de outras skills): o mem é vendorizado
  como snapshot pinado fork-and-forget (Decisão 15), não import runtime — o
  espírito da 22 se mantém. Sem revisita formal (não contradiz a decisão locked).

- State-machine de lifecycle migrada de `.claude/memory/L1/` →
  `.claude/forge/state/lifecycle/` (Decisão #1 da integração mem). Consolidada
  numa fonte única `paths.lifecycle_root`. `.claude/memory/` deixa de hospedar
  lifecycle (caminho pra ser 100% do mem). ADR-note Decisão 20 (persistence):
  o espírito se mantém — lifecycle continua arquivos + SQLite; só muda o
  sub-namespace de `memory/` pra `forge/state/`. Sem revisita formal (não
  contradiz a decisão locked).

- Renomeado o path de artefatos de feature `docs/feature-implementation-workflow`
  → `docs/forge-specs` (clean break, sem alias). Consolidados os 11 literais
  hardcoded numa fonte única `paths.FEATURE_WORKFLOW_DIRNAME`. `docs/superpowers/specs/`
  (specs do forge) NÃO muda.

- CLAUDE.md + `.claude/rules/**` enxugados pra Tier-0 lean + índice mem (Fase 0 dogfood, T6). O núcleo injetado sempre-on — Mandamento 0 (regra absoluta + whitelist de ferramentas + override do usuário), os 6 mandamentos e o fluxo único do orquestrador — permanece verbatim em `CLAUDE.md`; o resto (workflow por verbo, superpowers map, anatomia, comandos, graph howto, não-procrastinação) virou ponteiro `mem find` por tema. As 13 rules de `.claude/rules/` foram reduzidas a cabeçalho + ponteiro + invariante de enforcement que um hook lê (ex.: o ritual "Revisita decisão N" em `decisions.md`; os 5 títulos de smoke em `SMOKE-CHECKLIST.md`) — nenhuma apagada. O detalhe migrou pro acervo mem (recuperável via `.claude/bin/mem find "<tema>"`), comprovadamente coberto antes do enxugue. Canônicos `docs/design/*` preservados intactos. Os hooks (`session-start-orientation`, `pre-tool-use-load-bearing`, `pre-commit-feature-forge`) não leem texto de rule pra enforçar — a whitelist load-bearing e o hard-block de decisões vivem nos próprios `.sh` —, então o enxugue não afrouxa nenhum gate.

  ADR-note (sem revisita formal — consistente com decisões locked):
  - Decisão 20 (Persistence = SQLite + arquivos) é HONRADA: o `mem` É esse modelo — JSONL commitado (arquivos) como fonte + `mem.db` (SQLite) como índice derivado. O graph segue como a outra metade SQLite.
  - Decisão 22 (zero runtime dep em skills; absorb patterns only) é HONRADA: o `mem` entra como TOOL vendorizada via shell, não import de skill. `engine/` nunca faz `import mem`. Snapshot local pinado alinha com Decisão 15.
  Nenhuma das duas é revisitada — a substituição opera dentro do que ambas já endossam.

- Design spec da substituição da camada de memória-de-conhecimento pelo `mem` (CLI vendorizada via shell) — `docs/superpowers/specs/2026-06-25-mem-integration-design.md`. O forge deixará de manter L1-distilável/L2/L3 caseiros em `engine/memory/`; o `mem` (vendorizado em `.claude/bin/mem`, pinado por versão, invocado por subprocess — mesmo padrão de `dispatch_native_tool` pra detekt/gradle) passa a ser o dono único de learnings, decisões, episodes, sessões e convenções curadas. O code graph (`graph.db`) e o L1 state-machine de lifecycle permanecem no forge (este migra de `.claude/memory/L1/` → `.claude/forge/state/`, deixando `.claude/memory/` 100% do mem). O spec também detalha o rename clean-break `docs/feature-implementation-workflow/` → `docs/forge-specs/` (sem back-compat; resolve colisão de namespace — NÃO confundir com `docs/superpowers/specs/`, que é spec do próprio forge).

  Spec revisado pelo autor e consolidado: as 5 questões abertas viraram decisões (corte do L1 pra `.claude/forge/state/`; fronteira via helper enxuto `engine/integrations/mem.py:mem_call`; mem embarcado como asset pinado em `engine/assets/mem/mem`; bug multi-passo do `forge memory` exige TDD — reproduzir antes, não assumir cura; `forge evolve` vs `mem evolve` ortogonais). Rollout em 3 fases: **Fase 0** dogfood (o próprio forge usa mem, com gate de aceite explícito — sessão de manutenção fresca DEVE manter o Mandamento 0 enforçado), **Fase 1** produto (todos os fluxos re-roteiam; inclui a REDUÇÃO de rules no init — fix do gap de assimilação de convenção do piloto), **Fase 2** enriquecimento de rules (só referenciada).

  ADR-note (sem revisita formal — consistente com decisões locked):
  - Decisão 20 (Persistence = SQLite + arquivos) é HONRADA: o `mem` É esse modelo — JSONL commitado (arquivos) como fonte + `mem.db` (SQLite) como índice derivado. O graph segue como a outra metade SQLite.
  - Decisão 22 (zero runtime dep em skills; absorb patterns only) é HONRADA: o `mem` entra como TOOL vendorizada via shell, não import de skill. `engine/` nunca faz `import mem`. Snapshot local pinado alinha com Decisão 15.
  Nenhuma das duas é revisitada — a substituição opera dentro do que ambas já endossam. (Por não editar `docs/design/01-decisions.md`, o hard-block do Mandamento #1 não dispara; ADR-note aqui é a documentação correta de "honra, não revisita".)

- Handoff de sessão re-roteado pro `mem` (Fase 0.5 — dogfood). O `session-start-orientation.sh` passa a injetar o corpo do último `mem session` (dois passos: `mem --json find "" --type session -k 1` → `mem --json get <id>` → `.body`), com fallback gracioso pro grep dos dois campos do `08-session-handoff.md` quando o mem está vazio/ausente/falhando — o bloco hardcoded de Mandamento 0 + fluxo e o contrato exit-0 permanecem intactos em todos os caminhos. O `post-edit-doc-drift.sh` e o SOFT WARNING do `pre-commit-feature-forge.sh` deixam de exigir o handoff-arquivo no gate per-commit (fica `CHANGELOG`/`README`) e passam a apontar `mem session` como o trilho de fim-de-sessão; o HARD BLOCK do Mandamento #1 (`01-decisions.md`) não foi tocado. `CLAUDE.md` §6 e `.claude/rules/doc-sync.md` refletem o novo modelo (per-commit = CHANGELOG/README; handoff = `mem session`); as duas notas mem de doc-sync (matriz código→docs + checklist pré-commit) foram re-classificadas via `mem add` + `mem supersede` (antigas preservadas como superseded). O `docs/design/08-session-handoff.md` congelou — snapshot histórico + fallback de bootstrap do SessionStart, não mais editado a cada sessão (estado-final hybrid: não deletado). Nenhuma mudança de código Python.

### Fixed

- `forge verify` ganha dentes contra validator off-contract/quebrado (Onda 1 da
  remediação do piloto MeoBonsai — fecha BUG-VERIFY-1 e BUG-VERIFY-2):
  - **BUG-VERIFY-1** — validator que estoura exit ≥2 sem JSON tail (script
    quebrado ou fora do contrato canônico `--project-root/--scope/--id`) agora é
    classificado como `degraded`, NÃO `fail`. `degraded` não conta no overall nem
    cega a cascade fail-fast (Decisão 23): um validator off-contract não pode
    mais parar os validators a jusante (foi exatamente o caso do koin no piloto,
    que só aceitava `--root`, estourava exit 2 e parava tudo). Exit 1 sem JSON
    permanece `warn`; hard fail de código vem só pelo JSON tail `{"status":"fail"}`.
  - Novo veredito AGREGADO `incomplete` (distinto de `degraded`/`warn`): quando
    há `degraded` e nenhum `fail`/`warn`, o `overall` vira `incomplete` — "verify
    não pôde avaliar tudo (infra off-contract); NÃO-bloqueante, NÃO dispara
    block-forge-implement". `incomplete` é deliberadamente distinto do `degraded`
    do contrato L1 verify-log (que exige warnings≥1 e atrela block-implement).
    Precedência do overall: `fail > warn > incomplete > pass`.
  - **BUG-VERIFY-2 (T3)** — sumário honesto de cobertura: os passes são quebrados
    por classe (`substantive`/`stub`/`staged-blind`/`opaque`) pro host IA-first
    não tratar "verde" como garantia uniforme. Novo campo `infra_degraded` e
    `coverage_summary` no `forge verify --json`; valores possíveis de `overall`:
    `{pass, warn, incomplete, degraded, fail}`.
  - Glyph próprio (`⛒`) pra `degraded` na linha-a-linha (distinto do `⚠` do warn)
    + o motivo da degradação impresso na linha; título do box-sumário deriva do
    veredito agregado (run all-degraded titula "Verify incomplete", não "clean").
  - Validator do koin (`cards/koin-annotations/validators/check-koin-modules.py`)
    migrado pro contrato canônico (`--project-root/--scope/--id`).

- Gates de wave do `forge plan` ganham dentes (Onda 2 da remediação do piloto
  MeoBonsai — fecha o Tema 1: gates procedurais → substantivos): `forge plan`
  passa a rodar um content-check determinístico nas waves (A/B/C/D/E) antes de
  liberar o avanço. Helper `engine/plan_content_check.py` faz placeholder-scan
  quote-aware (não acusa marcador citado dentro de exemplo/prosa) +
  substance-coverage do DAG (cada nó precisa de conteúdo real, não só o
  esqueleto). A Wave A (intake free-text) é isenta do scan — texto livre não
  carrega marcador procedural. Substância apenas parcial → pausa deferred
  (exit 130), não falso-verde. Antes, os gates eram procedurais (existência de
  arquivo/marcador) e deixavam passar wave com placeholder não-resolvido.

- Hardening P1 (Onda 4 da remediação do piloto MeoBonsai):
  - `forge status` reconcilia git + expõe `qa_verdict` (**BUG-STATUS-1/2**): o
    pathspec não double-conta commits (qa + src separados) e o run mais recente
    sem verdict reporta `None`, não o veredito velho de um run anterior.
  - O marker `FORGE_INTENT` anuncia `response-schema-version` (**BUG-G2**) — o
    host-LLM sabe qual shape de `forge-response.json` o engine espera.
  - `forge upgrade` ganha `--dry-run` + guard de branch nomeada antes do
    checkout (**BUG-UPGRADE-1**) — não troca de branch às cegas.
  - `.gitignore` do `forge init` cobre derivados irmãos de `forge/`, incluindo o
    sidecar SQLite WAL `graph.db-shm` (**BUG-4/MEM-5**).
  - Build commands dos cards são project-derived pelo agente, não hardcoded
    literal cego no `agent-contributions` (**BUG-IMPL-2**).
  - `forge doctor` lê o version-lock no path canônico do `forge_dir` (**BUG-B**).
  - `skills/feature-forge/SKILL.md` mapeia todos os verbos dirigíveis
    (**BUG-QA-4**).
  - Polish P2 (bundle T8): `forge undo` no-op → exit 0 consistente; `evolve`
    help + SIGPIPE; escopo do `raw`; dashboard do `reconfigure`; help do
    `implement`.

- P0s estruturais (Onda 3 da remediação do piloto MeoBonsai):
  - **BUG-5** — `_walk_recursive_pruned`/`_lazy`: a poda de diretórios acontece
    na descida da árvore (não mais `rglob` cru no hot-path de discovery), o que
    elimina a varredura de subárvores ignoradas. Em árvores pesadas o ganho
    medido foi ~345x. `_glob_any` short-circuita no primeiro hit — a detecção
    fica independente de ordem de iteração e de cap.
  - **BUG-2** — o discovery passa a ser cacheado em disco no replay mecânico:
    o init não re-paga o custo de varredura (~220s no piloto) a cada replay.
  - **BUG-PLAN-1** — o gate de readiness do `forge plan` re-renderiza e pausa
    (exit 130) sem recursar; antes recursava no próprio gate ao re-checar
    prontidão.

- `test_rule_file_linked_in_claude_md` alinhado ao modelo de índice da Fase 0
  (rules indexadas em `.claude/rules/README.md`, `CLAUDE.md` só Tier-0). O
  teste codificava o invariante antigo (link literal de cada rule na
  `CLAUDE.md`) e quebrava em 10 rules depois que a `CLAUDE.md` foi enxugada
  pro ponteiro na campanha mem (cef24d5). Agora o invariante é: cada rule é
  referenciada na `CLAUDE.md` (path-anchored / link — sem match por
  substring) OU genuinamente indexada na tabela Map do README (parse
  estrutural por LINHA, não substring solta). Elimina o falso-positivo do
  `decisions.md` (passava por acidente via `01-decisions.md`) — agora passa
  legitimamente via índice. Adicionados guarda anti-near-inert (rule fictício
  DEVE falhar), consistência EXPECTED_RULES↔disco↔README, e `plan-auditor.md`
  (que faltava em EXPECTED_RULES). Só-teste — sem mudança de comportamento.

- Hook SessionStart (`.claude/hooks/session-start-orientation.sh`) resiliente
  a `created_at` malformado no JSONL do mem (cross-AI bot PR #32): a seleção
  da sessão mais recente agora valida que `created_at` é uma string ISO
  parseável antes de usá-la como chave; entradas ausentes OU corrompidas (não
  derivam de date válida) caem pra um sentinela que as ordena pro fim — nunca
  são mis-selecionadas como "mais recente" (caminho de continuidade entre
  sessões). Caso feliz (datas ISO válidas) preserva o comportamento atual.

- `forge undo` de evolve-apply de conhecimento agora reverte de fato via
  `mem inbox reject` (W-ROUTE 6d) — antes era no-op silencioso pós-6b (o
  candidato persistia no inbox do mem). O id é capturado no apply e gravado
  no evento `evolve-apply`; report honesto quando o candidato já virou nota
  ativa ou o mem está indisponível.

- Hardening do recovery-path 6d (cross-AI review PR #32):
  - **P2** (`engine/memory/distiller.py`): `apply_proposal_to_l2` valida o
    `mem-inbox-id` (`result.data["id"]`, não-vazio) ANTES de drenar a fila.
    Se o mem mudar o shape do `inbox add --json` (sem `id`, ou `id`
    vazio/null), levanta `MemoryError` sem drenar (raise-não-drena, espelhando
    o guard de `result.ok`). Antes, um shape mudado retornava `inbox_id=None`
    silencioso com a proposta já drenada → o evento `evolve-apply` virava
    L2-style, o guard L-02 de `undo.py` não disparava, e o `forge undo`
    reportava falso sucesso sobre um candidato órfão.
  - **P4** (`engine/evolve.py`): o preflight de overflow no topo de `run()` só
    roda quando há proposta pendente que de fato toca L2. Uma fila só-knowledge
    (que roteia pro mem-inbox) com L2 legada cheia não bloqueia mais applies
    válidos — espelha o skip per-proposta de `_apply_proposal`.
  - **P6** (`engine/evolve.py`): `_record_history_event` estreita o
    `except Exception: pass` para `(OSError, ValueError)` e emite aviso visível
    (`renderer.dim`) em vez de swallow silencioso — alinhado com
    `undo.py::_append_undo_log`. O evento `evolve-apply` carrega o
    `mem-inbox-id` load-bearing pro recovery; um append-fail silencioso
    orfanaria o candidato (undo nunca acharia o id).

- `mem_call` degrada soft em `OSError`/`PermissionError`, não só em
  `TimeoutExpired` (cross-AI PR #32, P1). Um binário mem resolvido por
  `is_file()` mas não-executável (bit de exec ausente / shebang ruim /
  delete em corrida) levantava `OSError` cru que escapava a fronteira e
  crashava o caller, furando o contrato de degrade-soft de plan/implement/
  verify/qa. Agora mapeia pro mesmo `MemResult` degradado (`found=True`,
  exit `_BINARY_NOT_FOUND`).

- `forge doctor` não crasha mais no check de pin do mem (cross-AI PR #32,
  P3). `pin.read_text()`/`asset_v.read_text()` rodavam fora de try/except
  logo após `is_file()` — um EACCES ou delete-em-corrida (TOCTOU) propagava
  traceback cru do comando de health-check que nunca deve crashar. Agora
  degrada pra um check WARN ("não consegui ler o pin/asset").

- `mem_find` protege a `query` posicional com o separador `--` (cross-AI
  PR #32, P5). Uma busca cujo tema começa por `-` (derivada de slug/
  `scope.target`/descrição de task) era parseada como flag pelo argparse do
  mem → exit≠0 → falha silenciosa do hint. Argv corrigido com a ordem
  verificada empiricamente: flags ANTES, `--` separa, query por ÚLTIMO
  (`find -k N [--type T] -- query`).

### Changed

- `MEM_PINNED_VERSION` (`engine/integrations/mem.py`) deixou de ser dead
  constant (cross-AI PR #32, P7): o pin-check de `forge doctor` agora valida
  o asset embutido contra a constante (fonte-da-verdade do pin do forge em
  código), pegando drift silencioso entre a constante Python e o asset
  `engine/assets/mem/VERSION`.

- Limpeza de qualidade do power-review do PR #32 (Q-01..Q-06, sem mudança de
  comportamento): docstring de `mentor_calmo` tira `pause_message` da lista
  "bare" (exige `project_root`); categoria `Memory L2` do `forge doctor`
  renomeada pra `Memory L2 (legacy)` com linguagem size-only (a curadoria do
  conhecimento vive no `mem`, não no L2); novo helper
  `paths.vendored_mem_version_path` centraliza o nome do pin do consumidor
  (`mem.version`) — escrita (`_vendor_mem`) e leitura (pin-check do doctor)
  passam por ele, removendo o literal duplicado (pin VALUE e drift-check
  intactos); `_ = Optional` morto removido de `distiller.py`; docstring de
  `engine/integrations/mem.py` referencia `MEM_PINNED_VERSION` em vez de
  repetir o literal de versão; teste real-mem `apply_proposal_to_l2_knowledge`
  alinhado ao guard `@pytest.mark.skipif` dos vizinhos.

## [1.6.1] - 2026-06-24

Remediação do piloto: rodar `forge qa` end-to-end contra o consumer real MeoBonsai-qa expôs um bug no `forge doctor` que rejeitava o `schema-version` canônico que o próprio `forge init` escreve — todo consumer recém-inicializado falhava o primeiro `doctor`. Junto, alinhamentos de consistência entre os templates/agents do fluxo qa e o que o engine de fato lê.

### Fixed
- A (HIGH — afeta todo consumer vivo): `forge doctor` rejeitava o `schema-version` canônico. `engine/doctor.py` `_check_config` só aceitava `schema-version == 1` e marcava qualquer outra coisa como hard FAIL; mas `forge init` escreve `schema-version: "1.3"` (string) e RULE-001 (`docs/schemas/forge-config.md`) documenta o conjunto aceito como `[1, 1.3]`. Resultado: todo consumer recém-`init`-ado falhava o primeiro `forge doctor` na categoria Config integrity. Fix: doctor agora aceita `{1, "1", 1.3, "1.3"}` → OK; versão desconhecida → WARN (doctor não migra, mas um config válido atual NÃO pode ler como red). Canon do `init` e dos config writers intocado — só a aceitação do doctor mudou. RED→GREEN: `tests/unit/test_doctor_schema_version.py`.
- B (usabilidade qa): o template `templates/qa-fixture-validator-claim.template.yaml` usava o campo `target_validator`, que o engine ignora — o reconstruct lê `evidence.{fixture_path, validator_path, tree_rel_path}` do FINDING + o arquivo materializado, não o descritor YAML. Renomeado `target_validator` → `validator_path` e adicionado cabeçalho deixando explícito que o descritor é humano-legível apenas (`file_content`/`expected_exit_code` não são lidos pelo engine — materialize o arquivo real). Espelhado em `agents/qa-auditor-validator-claim.md`.
- C (consistência de doc): `templates/qa-finding.template.json` descrevia o fingerprint como `{vector, target, normalized-description}`, mas o canon (Decisão 25 + `docs/schemas/qa-finding.md` + `.claude/rules/disciplines.md §6`) é `{type, name, normalized-description, sorted-provenance-set}`. Template corrigido pra casar com o canon (o synthesizer recalcula na Phase 4 — o valor do draft é placeholder).
- D (sinal de cobertura degradada): `agents/qa-auditor-{spec-vs-spec,coverage,chaos}.md` ganharam uma linha instruindo a auditar só o que está presente E registrar a cobertura degradada como finding quando inputs opcionais (navigation/ui-state/analytics-spec, screen-analysis) faltam no snapshot — torna a degradação visível em vez de silenciosa.
- E (precisão de mensagem): (1) `templates/qa-finding.template.json` — reescrita a regra de `evidence.sandbox_result` pra dizer "null no draft; o engine hidrata na Phase 3" (antes lia como se null fosse inválido); (2) `engine/qa/__init__.py` — a mensagem de emit nomeava `proposed-evolutions.yaml`, mas o arquivo real é `.claude/memory/L1/proposed-evolutions/proposed.yaml` — corrigido pra o usuário achar o arquivo.

## [1.6.0] - 2026-06-24

Milestone: campanha de piloto — unblock do ciclo AI-first (resume de `init`/`plan`/`reconfigure`) + fluxo agêntico de `forge qa` operacional + hardening de segurança do sandbox (Decisão 30) + e2e do secrets-gate.

### Tests
- Cobertura e2e do secrets-gate (`check_secrets`): novo `tests/integration/test_secrets_gate_end_to_end.py` (marker `integration`) com os cenários determinísticos que os unit tests com mock NÃO cobrem — per-task fail + 3-paths block (o `.kt` realmente staged num repo git de verdade flui via `git_staged_files` → `_dispatch_for_stage` → parse até o `what-failed`) e override-permit (`SECRETS-OVERRIDE` no commit body silencia limpo o único finding → `pass`). Mais dois smoke tests locais com gitleaks/trufflehog reais guardados por `@pytest.mark.skipif` (skipam quando as tools nativas estão ausentes; quando presentes, asserts determinísticos: gitleaks detecta o AKIA do fixture → `fail`, trufflehog `--only-verified` não confirma o token FAKE → `pass`). Cenários redundantes com os unit tests do engine (cascade position, fail-fast skip, bypass JSONL) NÃO entram — são dups verbatim de `test_secrets_position_after_cc` / `test_secrets_fail_fast_respected` / `test_run_secrets_gate_bypassed_by_env_var`. Acompanha as fixtures-fonte `tests/fixtures/secrets/file_with_secret.kt` e `file_with_test_fixture.kt`. Doc-sync: bloco `check_secrets` em `.claude/rules/testing.md` §"Validators são código" — corrigido o path do bypass log pra `.claude/forge/state/secrets-gate-bypass.jsonl` (`forge_state_dir`).

### Fixed (code-review remediation PR #27 — review-comment polish)
- PC-1: `qa-report.json` (o output PRINCIPAL da run) era escrito via `write_text` pelado em Phase 0 (skeleton) e Phase 4 (finalize) — um crash no meio do flush deixava o report torn/parcial. Fix (Mandamento 3 — DRY): extraí `_atomic_write_text(path, content)` com o padrão tmp + fsync + `os.replace` + dir-fsync (antes inline só no `_write_sandbox_results`) e roteei ambas as escritas de `qa-report.json` por ele; `_write_sandbox_results` também foi refatorado pra delegar ao helper (sem mudança de comportamento — mesmo tmp suffix, mesma durabilidade). `OSError` (ex.: disco cheio) PROPAGA — melhor falhar alto que persistir half-write silencioso. RED tests: `test_atomic_write_text_failure_leaves_no_partial`, `test_finalize_qa_report_atomic_no_partial`.
- PC-2: drafts de findings malformados/ilegíveis (`findings/*.json`) eram logados e pulados per-file, mas sem resumo agregado — o under-reporting de findings sumia no ruído quando havia muitos drafts. Fix: acumula os nomes dos drafts pulados e emite um único resumo mentor-calmo em stderr após o loop (`⚠ N findings file(s) puladas por erro de leitura/parse: a.json, b.json`); o skip per-file (degradação graciosa) é preservado. RED test: `test_malformed_findings_files_emit_aggregate_summary` (dois drafts quebrados → resumo nomeia ambos; draft válido segue processado).
- PC-3: quando um `validator_path` relativo de um validator-claim não resolvia NEM no projeto NEM no FORGE_HOME, o reconstruct silenciosamente mantinha o candidato do projeto (que depois falha no sandbox) sem nenhum sinal em stderr na hora do reconstruct — o finding A4 (`validator-claim-unresolvable`) só chega downstream. Fix: warning mentor-calmo de uma linha em `_reconstruct_fixtures_from_findings` nomeando os dois paths tentados (projeto + FORGE_HOME), pra debuggability imediata. Comportamento de resolução e o finding A4 inalterados. Test: `test_validator_path_unresolvable_warns_with_tried_paths`.

### Fixed (code-review remediation PR #27 round-3 — qa edge cases)
- WR-01: A8 dedup podia suprimir um validator-claim legítimo não-relacionado. A supressão do draft original casava por basename (`Path(fixture_path).stem`); dois validator-claim fixtures em dirs distintos com o mesmo basename (ex.: `dir-a/validator-claim-foo.yaml` e `dir-b/validator-claim-foo.yaml`) colidiam — declarar um irresolvível suprimia AMBOS os drafts, perdendo o sinal real do claim legítimo. Fix: `_suppress_superseded_validator_claims` casa pelo `fixture_path` COMPLETO. `_UnresolvableValidatorClaim` ganhou `fixture_path` e `_ReconstructResult` ganhou `fixture_path_by_name` (stem → path íntegro) pra o caller recuperar o path completo tanto do caso out-of-roots quanto in-roots-missing. RED test: `test_same_basename_distinct_paths_only_unresolvable_suppressed` (mesmo basename, paths distintos → só o irresolvível é suprimido).
- WR-02: captura parcial no caminho NORMAL era apresentada como íntegra. `engine/qa/sandbox.py` `_run_bounded`: quando o filho direto sai com exit-code 0 (sem `TimeoutExpired`) mas um grandchild benigno herdou e segura o write-end de um pipe, o `.join(timeout=_JOIN_TIMEOUT_S)` da drain thread ESTOURA — a captura fica parcial mas era devolvida com `truncated=False`. Fix: `drain_incomplete = t_out.is_alive() or t_err.is_alive()` após os joins do caminho normal, dobrado em `truncated` (+ warning mentor-calmo em stderr); o caminho de timeout (que propaga `TimeoutExpired` → `status=timeout`) não é tocado. RED test: `test_normal_path_drain_join_timeout_marks_truncated` (grandchild segura stdout além do join-timeout, pai sai 0 → `status=ok` mas `truncated=True`; falha se o termo `or drain_incomplete` for removido).

### Security (code-review remediation PR #27 round-2 — qa sandbox)
- A5: `forge qa` DoS na fronteira LLM→exec fechado. `engine/qa/sandbox.py` `_run_bounded` spawna o subprocess com `start_new_session=True` (POSIX) e, no `TimeoutExpired`, mata o GRUPO inteiro via `os.killpg(os.getpgid(pid), SIGKILL)` (`_killpg_safe`, fallback `proc.kill()`). Antes só `proc.kill()` (filho direto) era chamado — um validator hostil que forkava um grandchild herdando os write-ends dos pipes mantinha os pipes abertos, as drain threads (`.join()` sem timeout, non-daemon) bloqueavam pra sempre e a run inteira travava. Defense-in-depth: `.join()` agora têm timeout (2s) e as threads são `daemon=True`. Bonus: `from typing import Any` faltava (anotação de `_drain_bounded` levantaria `NameError` sob `get_type_hints()`). RED test: `test_forking_validator_does_not_hang_on_timeout` (forking validator travava 30s pré-fix; pós-fix completa em <1s, `status=timeout`).
- A7: detection asymmetry — `validator_path` fora dos roots permitidos era false-clean. Um `validator-claim` cujo `validator_path` resolve FORA de `project/validators/` ∪ `FORGE_HOME/validators/` (absoluto fora ou `../` traversal — o caso MAIS suspeito, possível tentativa de escape) era dropado no reconstruct via `continue` → nunca virava `Fixture` → A4 nunca derivava finding → só uma linha em stderr. Fix: `_reconstruct_fixtures_from_findings` retorna `_ReconstructResult` (fixtures + `unresolvable_out_of_roots`); `run_qa` constrói stubs sintéticos `status=error` pros out-of-roots e os feed em `findings_from_sandbox_results`, surfaçando um finding determinístico `validator-claim-unresolvable` ("possível tentativa de escape"). Per calibração do projeto (detection asymmetric = min HIGH).

### Fixed (code-review remediation PR #27 round-2 — qa hardening)
- A6: regressão de resume — o sandbox SEMPRE re-rodava. O gate da A3 confiava em `sandbox-results.json` só quando o checkpoint atestava `last_phase_completed >= 3`, mas NENHUM caminho normal persistia phase>=3 (o `_phase` chegava a 3 só após sandbox+synthesis e o checkpoint era limpo na conclusão). O branch "trust existing results" era DEAD code → todo resume de run engine-owned RE-RODAVA o sandbox — gasto de budget + side-effects de validator repetidos, violando a Decisão 27 ("resume continua, não refaz"). Fix: `run_qa` persiste `write_checkpoint(last_phase_completed=3)` IMEDIATAMENTE após `_write_sandbox_results`; phase<3 (sandbox incompleto/torn) continua re-rodando.
- A8: double-finding pra validator-claim irresolvível. Um claim irresolvível (in-roots-missing OU out-of-roots da A7) gerava DOIS findings pro mesmo issue — o draft original do auditor (`validator-claim`) + o derivado pelo engine (`validator-claim-unresolvable`). Vetores diferentes → `dedup_findings` (fingerprint inclui o vetor) não os colapsava. Fix: `_suppress_superseded_validator_claims` remove o draft original quando o claim resolve irresolvível → exatamente 1 finding por issue (o derivado, mais informativo).
- A9 (future-proofing): `validator-claim-unresolvable` + `sandbox-breach` + `sandbox-timeout` (vetores DERIVADOS pelo engine) entraram no set `_ENGINE_VECTORS` de `validators/validate_qa_finding.py` (additive ao `_CORE_VECTORS`). Inócuo hoje (o engine nunca chama `validate_qa_finding` nos derivados), mas um futuro wiring não os rejeitaria.
- A10: `_write_sandbox_results` fsynca o diretório pai após `os.replace` (`os.open(dir, O_RDONLY)` + `os.fsync`), best-effort. O fsync do arquivo (A3) durabiliza o conteúdo, mas a ENTRADA do rename só é garantida em disco após fsync do dir — um crash logo após o replace poderia perder o rename (resume re-rodaria ou veria o arquivo antigo).

### Accepted risk (code-review remediation PR #27 round-2)
- A11: `allowed_root` que é ele próprio um symlink (ex.: `project/validators` → `/etc`) seguiria pra fora da allowlist em `validator_within_allowed_roots`. ACEITO out-of-threat-model — não é vetor de input do LLM (a fixture só controla `evidence.validator_path`, nunca repõe os allowed roots; exige comprometimento prévio do FS/deployment). Rejeitar roots symlinkados quebraria checkouts legítimos via symlink (worktrees, `/var → /private/var` no macOS). Documentado no docstring de `validator_within_allowed_roots` + `docs/design/04-pending.md` (reabrível se forge rodar em multi-tenant).

### Security (code-review remediation PR #27 — qa sandbox)
- C1: `forge qa` sandbox escape via abreviação de argparse fechado (Decisão 30). `engine/qa/sandbox.py` `_scrub_extra_args` virou ALLOWLIST — passa SÓ `--scope`/`--id` (com valores), dropa todo o resto. O denylist anterior só removia `--project-root` literal; como os validators forge usam argparse com abreviação honrada, `--p`/`--proj`/`--project`/`--project-roo` (formas espaço E `=`) todos setavam `project_root` e, como última ocorrência após o `--project-root <sandbox>` que o engine controla, OVERRIDE o root (last-wins). Uma fixture LLM com `invocation_args: ["--p","/etc"]` rodaria o validator REAL contra `/etc` → escape total. A asserção de containment (`tests/engine/qa/test_sandbox.py`) virou matriz parametrizada que afere o root EFETIVO == mini-tree (não mera ausência de substring).
- A1: `validator_path` constrangido a um ALLOWLIST de roots resolvidos — `project/validators/` ∪ `FORGE_HOME/validators/`. Antes a reconstrução de `Fixture` só checava `.is_file()`, então um path absoluto fora ou `../`-traversal apontava o sandbox pra QUALQUER `.py` do disco, executado com `sys.executable` (arbitrary code execution). Aplicado no reconstruct (`engine/qa/__init__.py`) E defensivamente em `run_sandbox` (novo param `allowed_validator_roots` → `status=error` sem execução). Docstring enganoso de `Fixture.validator_path` corrigido.

### Changed (code-review remediation PR #27 — defense-in-depth)
- C1 (defense-in-depth): `validators/_common.py` `build_argparser` passa a usar `allow_abbrev=False`. Mudança de comportamento deliberada project-wide — abreviações de flag deixam de ser honradas por qualquer validator, fechando a classe inteira de override de `--project-root` via abreviação. Verificado: nenhum validator/test dependia de flag abreviada (lane `tests/validators/` verde, 317 passed).

### Fixed (code-review remediation PR #27 — qa sandbox hardening)
- A2: captura de output do subprocess capeada em 1 MiB/stream (`engine/qa/sandbox.py` `_run_bounded` via `Popen` + drenagem bounded). `subprocess.run(capture_output=True)` acumulava stdout/stderr ilimitado — um validator hostil emitindo GBs estouraria a memória do pai (×N fixtures → OOM/DoS); o timeout limitava TEMPO, não VOLUME. `SandboxResult` ganhou `truncated:bool` (serializado em `sandbox-results.json`); o timeout existente foi preservado.
- A3: replay de `sandbox-results.json` stale no resume fechado. O writer (`_write_sandbox_results`) virou ATÔMICO (tmp + `fsync` + `os.replace`); o consumo da Phase 3 deixou de ser existence-only — o engine só confia num arquivo existente quando NÃO é dono da Phase 3 (sem fixtures executáveis → conductor/legado) OU quando um checkpoint atesta `last_phase_completed >= 3`. Engine-owns + phase < 3 → arquivo de fase incompleta tratado como stale e re-rodado.
- A4: validator-claim com validator irresolvível deixou de ser false-clean. `findings_from_sandbox_results` deriva um finding `validator-claim-unresolvable` (severity medium — "claim não verificável") pra `status=error` em fixture validator-claim, em vez de droppar silenciosamente; `run_qa` também emite warning em stderr. Antes a ausência de validator (project nem FORGE_HOME) virava NO evidence + NO sinal pro vetor exato "validator que mente".
- B1: `find_resumable_run` (`engine/qa/checkpoint.py`) guarda `isinstance(scope_type, str)` além de `report_type` — um `scope_type` None não exclui mais todo report typed (defense-in-depth; latente hoje).
- B2: `run_qa` guarda `isinstance(raw, dict)` ao ler `sandbox-results.json` — raiz JSON escalar (nem list nem dict) não levanta mais `AttributeError` em `raw.get` (não capturado pelo except).
- B3: `hydrate_validator_claim_evidence` (`engine/qa/synthesis.py`) loga em stderr o `fixture_name` ambíguo que pula (WR-04 mantém o skip correto; ganha traceability).
- B4/B5 (doc): `agents/qa-conductor.md` ganha a tabela de contrato status → auto-finding (§5.3, incluindo o `validator-claim-unresolvable` da A4 e o campo `truncated` da A2); a garantia "um `--project-root` aqui é IGNORADO (Decisão 30)" em `templates/qa-fixture-validator-claim.template.yaml` e `agents/qa-auditor-validator-claim.md` foi tightened pro modelo allowlist explícito, agora honesta pós-C1/A1.

### Fixed (code-review remediation PR #26)
- A1: `check-no-suppress` (`cards/compose-screens/validators/check-no-suppress.py`) `_strip_noise` trata char literals (`'...'`) ANTES do ramo de string. Um char literal com aspas duplas (ex.: `val q = '"'`) fazia o scanner entrar em modo string e engolir um `@Suppress` real posterior na mesma linha — falso negativo que deixava um silenciamento real passar o hard gate. Char literals são neutralizados respeitando escapes.
- A2: `check-no-suppress` `scan_file` falha FECHADO em arquivo `.kt` ilegível em escopo Compose — emite aviso no stderr e devolve falha sintética em vez de `[]` (que tratava o arquivo não-auditável como limpo / fail-open).
- A3: `forge init` (`engine/init.py`) corrige o comentário e as mensagens do resume — não afirmam mais reaproveitar `selected_card_names`. Resume re-confirma o backend A PARTIR do preset salvo (pula só a confirmação do Step 4); a seleção de cards é refeita no Step 5. Os card-names salvos só são regravados pra integridade do checkpoint de audit. Comportamento do prompt inalterado (honest-wording, escopo R1 conservador).
- M1: ambos os validators do card `compose-screens` (`check-no-suppress.py`, `check-screen-layout.py`) substituem `rglob("*.kt")` por uma varredura `scandir` manual que pula `build`/`.gradle`/`node_modules`/`.git`/dot-dirs e NÃO desce em dirs symlinkados — evita varrer gerados e loop/hang em árvores grandes.
- M2: `_drop_unresolvable_cards` (`engine/init.py`) parseia ofensores ANCORADO aos prefixos estáveis do resolver (`DEP-MISSING`/`CONFLICT-NAME`/`CONFLICT-SINGULAR`/`CONFLICT-LABEL`) em vez de varrer qualquer `[...]` no texto. Listas entre colchetes só são parseadas sob os marcadores de conflito; wording desconhecido não poda cards por engano.
- M3: `forge init` guarda o re-resolve do caminho de recuperação "c" — se a poda esvazia o conjunto, aborta com "Nada resta resolvível — abortado." em vez de rodar `resolve([])` (instalação silenciosa de zero cards).
- M4: `forge reconfigure` (`engine/reconfigure.py`) não reabre o prompt de grant sob `_skip_to_apply` (replay com response de apply-confirm em-voo). Antes, `evaluate_sensitive_grants` rodava incondicionalmente e podia emitir um 3-caminhos fresco pra uma var sensitive não-granted no draft adotado — colidindo com a response terminal in-flight (`IntentMismatchError`, mesma classe de deadlock que P-18 fechou). Sob replay, a avaliação de grants é pulada (no-op); var sensitive pendente vira aviso no stderr, sem prompt.
- M5: `read_response` (`engine/ui/intent_state.py`) guarda root não-dict ANTES de `_check_schema_version` — um `forge-response.json` corrompido (lista/escalar) levantava `AttributeError` cru, violando o contrato "nunca vaza traceback bruto". Agora levanta `IntentMismatchError` preservando o arquivo.
- M6: `intent-id` é output não-confiável do host. `read_response` levanta `IntentMismatchError` (arquivo preservado) e `host_is_replaying` retorna `False` quando o id não é string — evita `TypeError` cru em `written_id in log` quando o valor é lista/dict unhashable.
- B1: `read_pending` (`engine/ui/intent_state.py`) levanta `JsonIOError` em root não-dict, simétrico ao contrato dict da response.
- B2: remove o param morto `selected_names` de `_resolver_error_gate` (`engine/init.py`) e o arg computado-e-descartado no call site.
- B2 (follow-up): a remoção do `selected_names` no B2 deixou passar 2 call sites em `tests/integration/test_init_brownfield_multi_axis.py` que ainda passavam o kwarg — `main` ficou RED na lane de integração com `TypeError: ... unexpected keyword argument 'selected_names'`. Os dois calls (`test_resolver_error_gate_pauses_not_aborts`, `test_resolver_error_gate_question_short_errors_to_stdout`) agora alinham à assinatura atual `(errors, *, project_root)`. Release fecha a regressão.
- B3: `scan_dir` (`check-screen-layout.py`) protege `directory.iterdir()` com try/except — dir inacessível é pulado com aviso em vez de estourar traceback.

### Fixed (pilot R8 — qa flow polish)
- Item 3 (`validator_path` FORGE_HOME fallback): a reconstrução de `Fixture` dos findings validator-claim resolve o `validator_path` por precedência projeto > `FORGE_HOME/validators/`. Antes o path era tratado como relativo ao projeto consumidor; mas os validators forge canônicos vivem no FORGE_HOME, não no consumidor — declarados por basename nu ficavam irresolúveis e o vetor validator-claim não alcançava o validator real. O fallback fecha o gap (relacionado a P-22 / R7-VALIDATOR-PATH-XPROJ): se o path não resolve sob a raiz do projeto, tenta `FORGE_HOME/validators/<basename>`.
- Item 4 (`invocation_args` + scrub de hardening): a fixture validator-claim ganhou `invocation_args` (ex.: `--scope feature --id <slug>`), threadado pro sandbox via `Fixture.extra_args` e apendado pelo `run_sandbox` à invocação do validator — validators feature/task-scoped (`validate_task_contract`, `validate_feature_package`) viram alvos limpos do vetor (fecha R7-FEATURE-SCOPED-ID). O HARDENING da Decisão 30 foi PRESERVADO: o engine continua dono do `--project-root` (aponta pro mini-tree do sandbox), e `_scrub_extra_args` neutraliza qualquer `--project-root` injetado na fixture pela LLM — a fixture não escapa o sandbox por essa via. `tree_rel_path`, chdir guard, env allowlist e budget/timeout inalterados.
- Item 2 (`actual_exit_code` stale removido): removida a linha stale `actual_exit_code` do exemplo em `agents/qa-auditor-validator-claim.md`. O schema do report usa `evidence.sandbox_result.exit_code` como fonte do exit-code do subprocess; o campo `actual_exit_code` não existe no contrato e induzia o auditor a preencher um campo fantasma (fecha R7-LEGACY-ACTUAL-EXIT na dimensão do exemplo do auditor).

### Fixed (pilot R7 — qa flow)
- F-1: `forge qa` Phase 3 sandbox monta um mini-tree e invoca o validator com `--project-root <mini-tree>` em vez de passar a fixture como argumento posicional. Validators forge reais usam `argparse` com `--project-root`; a invocação posicional batia `exit 2` sem nunca ler a fixture, deixando o vetor validator-claim ("validator que mente") INERTE pra qualquer validator forge real. `Fixture` ganhou o campo opcional `tree_rel_path` (path relativo do arquivo materializado dentro do mini-tree). O hardening da Decisão 30/31 foi preservado e ENDURECIDO: `_validate_paths_inside_sandbox` agora cobre o mini-tree + o arquivo materializado (containment intacto), e traversal via `tree_rel_path` vira `sandbox-breach` antes de qualquer subprocess; chdir/fchdir guard, env allowlist (sem PYTHONPATH herdado) e budget/timeout inalterados. O caminho legado posicional (`tree_rel_path=None`) segue funcionando.
- F-2: resume real do fluxo `forge qa` via checkpoint auto-resume — estende a Decisão 27 (pausa = `deferred` auto-resumable) SEM introduzir flag de CLI (Decisão 10 honrada). O checkpoint é escrito na fronteira da Phase 0 e limpo na conclusão (Phase 5); `run_qa(resume_run=...)` reata a run tree existente e continua da phase inferida pelo estado em disco em vez de criar uma run nova.
- F-3: `_finalize_qa_report` computa `run.duration_s` (derivado de `finished - started`, da MESMA referência que escreve `finished_at` — zero jitter), que o `validate_qa_report` exigia. Degradação graciosa pra `started_at` ausente/malformado (`duration_s = 0.0`).
- F-4: synthesize hidrata `evidence.sandbox_result` nos findings validator-claim draft — determinístico, engine-side, casando o stub de `sandbox-results.json` por basename. Antes só breach/timeout derivavam `sandbox_result`; o draft validator-claim sobrevivia com `null` e perdia o audit trail do subprocess. Não inventa evidência: draft sem stub correspondente (ou stub sem `exit_code` int) permanece `null` válido.
- CR-01 (review holístico R7): o engine passa a ser DONO da Phase 3 — `run_qa` reconstrói as Fixtures dos findings validator-claim, roda `run_sandbox` no próprio flow e escreve `sandbox-results.json` ANTES do synthesize. Antes `run_sandbox` era dead code (a Phase 3 nunca rodava pelo caminho do engine) e o `qa-conductor.md` se contradizia com o engine sobre quem rodava o sandbox — o vetor validator-claim ficava inalcançável pelo fluxo documentado. Agora o engine é o dono (honra a Decisão 30 + o anti-padrão "Phase 3 core-Python-only"); o contrato do conductor foi alinhado.
- WR-01/03/04 (review holístico R7): `find_resumable_run` discrimina `scope.type` (runs de targets homônimos cross-tipo não reatam mais a run errada); `_compute_duration_s` faz strip só do sufixo `Z` (não de qualquer `Z` no meio do timestamp); o matching de `sandbox_result` é robusto a basename colidente cross-fixture (não hidrata ambíguo em vez de trocar o audit trail).

### Changed (pilot R7 — qa flow)
- F-5 (doc): o exit-code de BLOCK do `forge qa` é exit 1 + `[FORGE-ERR:QA-BLOCK]` em stderr (não exit 8). Alinha `agents/qa-conductor.md`, o spec e os docstrings de `run_qa` ao contrato vigente pós-C3 EXIT-2-COLLISION (`fail_with_tag(ERR_QA_BLOCK)`); o "exit 8" original fica como superseded, não apagado. Sem mudança de comportamento de engine.

### Validated (re-piloto MeoBonsai-qa — pilot R7)
- Re-piloto `forge qa` end-to-end no MeoBonsai-qa confirmou a Phase 3 executando: validator real saindo `exit 1` via `--project-root`, `evidence.sandbox_result` populado, verdict BLOCK / exit 1 + `[FORGE-ERR:QA-BLOCK]`, checkpoint limpo na conclusão e hardening do sandbox intacto.

### Fixed (pilot R6 — blockers AI-first)
- P-17: phase-lock liberado no plan-complete via `release_phase_lock` (helper `_finalize_planned` em `engine/plan.py`) — `forge implement` não bate mais o `ERR_LOCKED` stale `by 'None'`. O bug era fonte-de-verdade dupla: plan-complete zerava o mirror em `status.json` mas deixava o sentinel `.phase-lock` em disco; `current_phase_lock` (sentinel-first) reportava o holder stale e `acquire_phase_lock` do `implement` batia `FileExistsError`. A ordem do fix libera o sentinel PRIMEIRO e grava `status=planned` DEPOIS (idempotente).
- P-17: mensagem de erro de phase-lock mostra o holder REAL via `current_phase_lock` (sentinel-first) em `engine/implement.py` e `engine/plan.py` — em vez de ler `read_l1_status(...).phase_lock` (mirror potencialmente desatualizado) que imprimia `by 'None'`.
- P-19: `forge qa` Phase 0 popula `snapshot/` — `snapshot_artefacts` (`engine/qa/ingest.py`) recursa em diretórios de scope. Antes, `scope.paths` de feature era um DIRETÓRIO; `os.link`/`copy2` falhavam (IsADirectoryError engolido pelo `except OSError`) e o snapshot ficava vazio. Agora, quando `src` é diretório, recursa nos arquivos (`rglob`) preservando o layout relativo; arquivo regular mantém o comportamento. Cascata hardlink→copy2 extraída em `_copy_one` (DRY intra-módulo).
- P-20: `conductor-handoff.json` carrega `snapshot`/`config_snapshot`/`auditors` (4 core) conforme contrato do `agents/qa-conductor.md`. Antes o handoff só tinha `scope`/`run_id`/`root`/`config`. `auditors` lista os 4 core canônicos (`spec-vs-spec`, `coverage`, `chaos`, `validator-claim`) filtrando `extensions_disabled`; `config_snapshot` congela a section `qa:` da workflow-config; `snapshot` lista paths relativos à raiz da run.
- P-18: `forge reconfigure` aplica mutações via loop canônico AI-first — `host_is_replaying` estendido ao apply path via `_skip_to_apply` (`engine/reconfigure.py`). Antes, no loop AI-first o draft-resume guard interceptava a response do apply-confirm em-voo, re-navegava pelo category-menu e o apply-confirm nunca consumia sua response → mismatch (exit 1), mutação não aplicada. Agora, sob replay com response de apply-confirm pendente, o pipeline alcança o apply-confirm e consome a response (aplica a mutação) sem o category-menu intervir; re-entrada HUMANA genuína (sem response in-flight) continua mostrando o draft-resume guard (gate de navegação R4 intacto).
- WR-04 (review R6): `forge undo` `_abort_feature` (`engine/undo.py`) libera o sentinel `.phase-lock` via `release_phase_lock` — mesma classe latente do P-17, exposta pelo `current_phase_lock` sentinel-first. Antes setava só `phase_lock=None` no mirror e deixava o sentinel em disco; pós P-17 isso reportaria holder stale. Agrava porque a própria mensagem de erro do P-17 prescreve `forge undo` como recovery — o workaround prescrito não liberava o lock por esse vetor.
- WR-01/02/03 (review R6 — robustez do validator novo): `check-no-suppress` (`cards/compose-screens/validators/check-no-suppress.py`) ficou string-aware no `_strip_noise`: neutraliza string literais ANTES de cortar comentário de linha (WR-01 — `//` dentro de string não trunca mais a linha e deixa `@Suppress` real passar); rastreia raw-string `"""` multi-linha (WR-02 — `@Suppress` em raw-string deixa de bloquear commit legítimo); e fecha block comments aninhados via contador de profundidade em vez do primeiro `*/` (WR-03 — `/* /* */ */` não trata mais `@Suppress` aninhado como código vivo).

### Added (pilot R6 — validators reais do card compose-screens)
- P-24: validators REAIS do card `compose-screens` — eram stubs Phase 5 `return 0` declarados `severity: error` ("validator mente sobre cobertura"). `check-no-suppress` bloqueia `@Suppress`/`@file:Suppress` em código Compose (string-aware: ignora ocorrências em comentário de linha, KDoc, string literal e raw-string; escopo = source sets Compose UI, exclui test source sets). `check-screen-layout` exige o par `{Screen}Screen.kt` + `{Screen}Content.kt` no mesmo diretório de tela sob escopo Compose (`{Screen}Components.kt`/`{Screen}Mappers.kt` opcionais). Ambos seguem o contrato de invocação canônico (`--project-root` + tolerância a `--scope`/`--id`, `cwd=project_root`, exit 0 limpo / exit 1 + `arquivo:linha` em stderr).

### Validated (re-piloto MeoBonsai 3/3 — pilot R6)
- P-17/P-18/P-19 validados no sandbox MeoBonsai via loop canônico AI-first, sem workaround de engine: phase-lock liberado no plan-complete (`forge implement` destravado), `forge reconfigure` aplica a mutação via replay, `forge qa` Phase 0 popula o snapshot.

### Fixed (pilot R1 — unblock init AI-first)
- P-01: gate do prompt de resume durante o loop mecânico do host (fim do deadlock IntentMismatchError).
- P-11: resume real continua do step do checkpoint + labels honestas.
- P-03: cards UI/nav declaram `identity.platforms` — fim do CONFLITO falso de pareamento KMP.
- P-09: dep-closure de provider antes do resolver — fim do DEP-MISSING em firestore-security-rules.
- P-10: gate RESOLVER-ERRORS pausa (exit 2) pra escolha em vez de abortar.
- P-04: tabela de detecção como contexto, campo `question` curto.
- P-02: remove texto dev "[W7.2 …]" das labels brownfield; W7.2 anotado em 04-pending.
- P-05: `forge <subcmd> --help --json` emite JSON ou erro explícito.
- P-07: abertura do init determinística (`greeting_stable`).
- P-08: remove opção morta `outro` do prompt de preset.
- P-12: rótulo de passo + nota de duração em vez de relógio interno.
- WR-02 (review R1): gate `RESOLVER-ERRORS` deixa de embutir o detalhe multi-linha dos erros no campo `question` do intent — imprime os erros como contexto via renderer e mantém o `question` curto, consistente com o padrão que P-04 estabeleceu no mesmo módulo.
- WR-03 (review R1): paths brownfield "b" (ajustar células) / "c" (começar do zero), ainda não disponíveis nesta versão, deixam de produzir um conjunto degradado silencioso (`selected` vazio) — redirecionam pra "confirmar como-is" com a mesma seleção do composer + aviso explícito ao usuário, em vez de mentir sobre o que fazem.

### Added (pilot R1)
- `identity.platforms` documentado em `docs/schemas/card.md` (campo aditivo opcional).
- Marker stdout `<FORGE_INTENT>` documentado em `docs/schemas/intent-protocol.md`.

### Changed (pilot R1)
- README: reconciliação de stats (22 validators + 3 helpers, 29 cards, tests 1863/204/30).

### Added (pilot R4 — generaliza re-entry guard gating)
- `host_is_replaying(project_root, guard_intent_id)` em `engine/ui/intent_state.py`: gate compartilhado que suprime guards de re-entrada durante o loop mecânico do host (P-15). Compõe `_response_path` + `_read_intent_log` — `True` quando há `forge-response.json` in-flight pra um prompt downstream (id ≠ guard E não-consumido). Documentado em `docs/schemas/intent-protocol.md` §4.1.

### Fixed (pilot R4)
- P-15: `forge plan` / `forge reconfigure` / `forge init` não deadlockam mais (`IntentMismatchError`, exit 1) quando um guard de re-entrada colide com a response de um prompt downstream durante o loop AI-first. Generaliza o fix de P-01 (que gateava só o resume do `init`) num mecanismo compartilhado cobrindo a classe inteira: colisão de slug (`_handle_active_slug_collision`) — o bug PRIMÁRIO do comando central —, menu de feature-done (`_handle_done_feature_branch`) e draft-confirm do `reconfigure`.

### Changed (pilot R4)
- Gate de resume do `init` agora usa `host_is_replaying` em vez de `_response_path().exists()` cru (DRY com P-01; precisão melhorada — não suprime quando a única response no disco é pra o próprio prompt de resume).
- README: tests 1885/215/31 (pilot R4 — +12 unit/refinement + 1 e2e do loop canônico; integration medido em 215, reconciliando o drift do baseline 204).

## [1.5.0] - 2026-06-19

### Added

- **PLACEHOLDER-VERIFY** (W-DEBT, 2026-06-18): novo validator
  `validators/check_unfilled_placeholders.py` no cascade default de `forge verify`
  (entre `check_no_invented_behavior` e `check_cyclomatic_complexity` — cheap,
  bloqueia early). Escaneia os artefatos staged DENTRO do dir da feature
  (.md/.yaml/.yml/.json) procurando `{{token}}` crus não-substituídos — um
  template não-preenchido passando como "verificado" é detection-failure.
  Compõe `_common` + `_diff` + `feature_path` (subtype-aware); sem helper novo.
- **ABORTED-DEADEND** (W-DEBT, 2026-06-18): novo op de recovery `un-abort feature`
  no menu de `forge undo` (opção 8). `_abort_feature` passa a preservar o status
  pré-abort em `raw["pre-abort-status"]` ANTES do overwrite; `_undo_abort`
  restaura esse status (default `deferred` p/ features abortadas por engine
  antigo, sem o marker), limpa os markers `pre-abort-status`/`aborted-reason` e
  loga no undo-log. Fecha o dead-end onde abortar uma feature só deixava o
  caminho de deletar a L1 + recomeçar. Op não-destrutivo (confirm simples).
- **CARDS-DISCONNECT** (W-DEBT, 2026-06-18): `forge init` agora materializa os
  templates mergeados per-projeto em `.claude/forge/templates/`
  (`_materialize_merged_templates` reusa `render_merged_template` — o mesmo
  render que `forge raw rebuild-templates` usa, mas escrevendo no destino
  per-projeto em vez de mutar o FORGE_HOME global). O campo `target` do card é o
  nome de OUTPUT (`tech-spec.md`); `_source_template_name` mapeia pro
  template-fonte (`tech-spec.template.md`, inserindo `.template` antes da
  extensão — a convenção `(template_name, output_name)` das tuplas
  `WAVE_*_TEMPLATES`), e o materializado é escrito sob o nome do FONTE porque é
  por ele que `plan._render_template` resolve. `plan._resolve_template(project_root,
  template_name)` prefere o dir per-projeto **per-FILE** (só quando ESSE template
  existe lá), com fallback per-FILE pro global — materialização parcial não quebra
  templates não-contribuídos. O fluxo default `init`→`plan` deixa de ignorar as
  seções de template que os cards ativos contribuem (validators de card já
  chegavam via snapshot). NOTA: `forge raw rebuild-templates` ainda carrega o
  mesmo mismatch target→base latente (resolve `templates_root / target` direto);
  fix dedicado anotado em `docs/design/04-pending.md` (afeta caminho pré-existente
  do merger global).
- Camada de interação AI-first (Wave 1): driver `skills/feature-forge/SKILL.md`
  (Claude Code) + `templates/AGENTS.md.template` (opencode) instalados
  brownfield-safe por `forge init`. Ensinam o host a dirigir o intent loop
  (exit 2 + linha `<FORGE_INTENT/>` → AskUserQuestion com options-JSON →
  response com o mesmo intent-id → re-invoca o argv idêntico) e a dispatchar
  o `planning-conductor.md` lido do FORGE_HOME. Decisão 22 preservada — são
  comportamento pro host, não import do engine.
- `forge plan` front-door: aceita ticket-id (ex.: `IN-37234`) ou frase livre
  como argv posicional, deriva um slug kebab-case determinístico, confirma
  conversacionalmente e semeia o texto cru no `feature-intake.md` pro grill
  refinar. Decisão 10 preservada — argv posicional, sem flag.
- Grounded-challenge Phase 2.5 no `planning-conductor.md`: antes de elicitar,
  confronta o pedido contra grafo (Q1/Q11-Q17) + inventory + L2 em quatro
  frentes (duplicação / terminologia / decisão frozen / fora-do-design-system).
  Não-bloqueante (D3: confronta + humano decide), com no-visual branch
  (3-caminhos) e degradação graciosa quando grafo/inventory/L2 estão ausentes.
- Readiness enforce: `validators/validate_readiness.py` + `readiness-reviewer.md`
  Phase 5 agora escaneiam `needs-elicitation` não-promovido — block-severity
  em contract spec (match estruturado), warning em narrativa. Fecha o
  ponto-cego "thin-but-structurally-complete".
- Graph-first pro consumidor (W-GRAPH): `forge init` agora escreve
  `.claude/forge/GRAPH-FIRST.md` (regra "consulte o grafo antes de ler o
  source" + quick-start das queries q1/q2/q3/q4/q8) e
  `.claude/forge/graph-skill.md` (tabela tarefa→query→exemplo cobrindo o
  catálogo `q1`..`q17`+`r`, aliases aceitos, e a seção "quando NÃO usar o
  grafo"). Fecha o NO-ONBOARDING do grafo — antes o `forge init` construía o
  `graph.db` mas nunca ensinava o consumidor a usá-lo (grafo órfão).
- Lembrete graph-first no `hooks/session-start-drift-check.sh`: quando
  `.claude/graph.db` existe, o hook emite 2-3 linhas em stderr lembrando que
  o grafo está disponível + como consultá-lo. Host-aware (emoji em TTY, `[graph]`
  ASCII fora) e guardado pela presença do grafo.
- **FORGE_HOME-carries-skills** (W-DEBT, 2026-06-18): nova categoria de
  `forge doctor` (`_check_forge_home_driver`, 17ª no full scope) que assere a
  presença de `FORGE_HOME/skills/feature-forge/SKILL.md` — o driver do host
  (DRIVER-001). Espelha a categoria de Hooks (presença de arquivo esperado no
  FORGE_HOME); FAIL com hint mentor-calmo quando ausente, pegando clone
  parcial/sparse que deixaria o driver dormente sem aviso.
- Token economy / machine-legibility (W3, A1 TOKEN-BLIND + A2): output-mode
  global host-aware (`engine/ui/output_mode.py` — enum TTY/PLAIN/JSON + context
  var + allowlist `_JSON_CAPABLE_COMMANDS`), consultado pelo chokepoint único
  `renderer.write`. `FORGE_OUTPUT=json` env ativa o modo JSON pros read-commands.
- `forge status --json` / `doctor --json` / `verify --json` / `memory --json`
  (snapshot read-only dos 3 layers) — output machine-readable pros read-commands
  (stdout JSON puro, erros→stderr, exit 0/1; modelo idêntico ao `graph --json`).
- `forge status --json` inclui `suggested_next_command` — workflow router que
  mapeia o estado da feature mais recente pro próximo verbo (A2 NO-WORKFLOW-ROUTER).
- `forge --help --json` — manifesto machine-readable de comandos/args/flags
  a partir de `_VISIBLE_ORDER` + `_COMMAND_META` (metadata hand-maintained em
  lockstep com `COMMANDS`, com drift-guard de teste; A2 NO-MANIFEST);
  read-commands anunciam `--json`.

### Removed

- **PHANTOM-STATES** (W-DEBT, 2026-06-18) — estados `verified` e `paused`
  removidos de `engine.memory.l1._VALID_STATES`. Nenhum dos dois era escrito
  por handler: `verify` restaura o status anterior no sucesso (nunca grava
  `verified`); `implement` vai `implementing → done` direto; pausa é `deferred`
  auto-resumable (Decisão 27 — `07-discipline.md:670` já afirmava "Não há
  `state: paused` separado de `deferred`"). O router de `forge status`
  (`_suggested_next_command`) simplificou de 11 → 9 estados; o resume-set de
  `forge plan` perdeu o literal morto `paused`. Docs de state-machine
  reconciliados (`ROADMAP.md`, `07-discipline.md`, `06-command-surface.md`).
  Não toca `01-decisions.md` — alinhamento doc↔código, sem cerimônia "Revisita
  decisão N". Clean-break pré-produção.

### Changed (load-bearing)

- Revisita Decisão 10: conversacional human-first + meta-flags opt-in (--json,
  --help --json, FORGE_OUTPUT=json) pros read-commands — intent protocol
  inalterado pros interativos. Destrava token economy / machine-legibility
  (auditoria §3.2 A1/A2).

### Fixed

- **Remediação cross-AI (PRs #18–#22, 2026-06-18)** — 52 correções consolidadas
  do review cross-AI (codex + claude-opus + bots). Destaques:
  - **HIGH detection-failures:** `forge verify` cascade agora threada
    `--scope`/`--id` até os validators (C-43 — o PLACEHOLDER-VERIFY gate estava
    shipped-but-inert) + scan de filesystem em vez de git-staged;
    `validators/validate_memory._VALID_L1_STATES` sincronizado com
    `engine.memory.l1._VALID_STATES` (C-44 — aceitava `paused` removido, rejeitava
    estados canônicos); readiness `_is_active_marker` detecta string descritiva
    (C-05); `engine/status._suggested_next_command` tie-break dead-code corrigido
    (`feature_slug`→`slug`, C-33); `forge graph --json` honra `FORGE_OUTPUT=json`
    sem `--json` posicional (C-35); `verify --json task` guarda ambiguidade antes
    de mutar L1 (C-34); `read_pending` probe Windows não desativa race detection
    (C-49); manifesto de comando verídico (`prompts_by_default` + `machine_readable`
    separados, C-37); qa-report template alinhado aos enums do validator (C-42q);
    error-paths roteados via `fail_with_tag` (C-23); reconfigure card-removal
    derivado de disk-vs-config + move idempotente (C-22); config-path com fallback
    legado uniforme via `active_config_path` (C-04/C-10).
  - **MED/LOW:** plan.py handlers de pausa capturam as exceções REAIS
    (UserPaused/Cancelled, C-06), screenshot multi-path (C-08), colisão de slug
    ativo com 3-caminhos (C-03); init.py brownfield-safe (UnicodeDecodeError +
    settings shape, C-07/C-07b), git-hook delegator relativo (C-09), template
    materialization falha init em card ativo (C-47); undo double-abort + raw guard
    (C-48/C-50); memory --json guard (C-36/C-40); output_mode isatty guard (C-41);
    json_io orphan-tmp sweep (C-25); guards defensivos em reuse_apply/slug/
    flock/intent-state (C-13/C-14/C-28); path-drift `.claude/state/`→
    `.claude/forge/state/` em schemas load-bearing (C-02/C-12); enum L1 em
    `docs/schemas/memory.md` + `agents/retrospective-agent.md` (C-46).
  - **Path canônico:** `docs/schemas/intent-protocol.md` e `docs/schemas/memory.md`
    (load-bearing) atualizados; `docs/design/06-command-surface.md` reflete verify
    como observador com side-effects de L1.
- **un-abort enum guard** (W-DEBT holistic review CR/WR-01, 2026-06-18) —
  `_undo_abort` (`engine/undo.py`) valida `pre-abort-status` contra
  `_VALID_STATES` ANTES de restaurar. Um valor ausente OU não-membro do enum
  (abort legado, OR um estado removido por wave futura — exatamente o que T1 fez
  com `verified`/`paused`) cai pro default seguro `deferred` com aviso
  mentor-calmo, em vez de propagar o `MemoryError` cru de `write_l1_status` como
  traceback no dispatch do `forge undo`. Fecha a assimetria T1×T3 (recovery não
  defendia contra estados que deixaram de ser válidos).
- **SCHEMA-1 / SCHEMA-LEAK** (W-DEBT, 2026-06-18; tratamento de campo-ausente
  alinhado em WR-02) — `_check_schema_version` (`engine/ui/intent_state.py`) agora
  roda em `read_pending` e `detect_race`, não só em `read_response`: version skew
  num pending vira a mensagem friendly "atualize o forge" em vez de cair no sweep
  ou virar "race" confusa. **Contrato simétrico de campo-ausente (WR-02):** os
  DOIS caminhos só disparam o check quando `schema-version` está PRESENTE e
  diverge (guard `if "schema-version" in payload:`). Ausência = pending
  malformed/legado (pré-protocolo), tratada idêntica em ambos — não version-skew
  (`SchemaVersionMismatch` significa "versão errada", não "sem versão"). Antes,
  `read_pending` levantava em campo-ausente enquanto `detect_race` tolerava — a
  assimetria que esta entrada vendia como "simétrico". `SchemaVersionMismatchError`
  entrou na tupla de except do `engine/cli.py` (junto de `RaceDetectedError`/
  `IntentMismatchError`) → exit 1 mentor-calmo em vez de traceback cru.
- **STALE-1** (W-DEBT, 2026-06-18) — `detect_race` faz liveness probe
  (`os.kill(pid, 0)`) antes de levantar `RaceDetectedError`: pending recente de
  processo morto (crash sem cleanup) é varrido em vez de travar a raia até o
  stale threshold (~10 min). `ProcessLookupError`/pid inválido (≤0) → varre;
  `PermissionError` (processo vivo de outro dono) → race genuína. Testes de race
  pré-existentes migrados pra `pid=os.getpid()` (PID vivo) — a race determinística
  agora exige processo vivo.
- **validate_readiness non-product blind** (W-DEBT, 2026-06-18) —
  `validators/validate_readiness.py` resolve o dir da feature via
  `feature_path(project_root, slug, subtype=current_subtype(...))` em vez do
  `feature_dir` hardcoded em `features/`. Features non-product (refactor/spike/
  chore/bugfix) param de varrer o dir product vazio e reportar "review ausente"
  falso. Conserta o needs_elicitation scan E o lookup do review de uma vez
  (mesmo pattern de `undo._delete_feature_artifacts`).
- **DETECT-1 / M6 dead-code** (W-DEBT, 2026-06-18) — `detect_any_agentic`
  (`engine/host/env.py`) e `_detect_brownfield` (`engine/init.py`) removidos:
  ambos eram dead-code (zero caller de produção, só testes). `detect_codex`/
  `detect_cursor` MANTIDOS (paralelo a `detect_opencode` future-proofing +
  superfície de verificação do scrub ENV-1) com docstrings honestas
  ("não-wirada em `detect_host`"). O init é brownfield-safe por construção (merge
  append-only + delegator encadeado + sub-namespace), sem switch de modo — o
  docstring de `_detect_brownfield` que anunciava "em-uso" era drift.
- **L-1 docstrings legados** (W-DEBT, 2026-06-18) — docstrings/comentários
  citando o anchor legado `.claude/state/` corrigidos pra `.claude/forge/state/`
  (anchor canônico v1.3) em `question.py`/`json_io.py`/`cli.py`/`intent_file.py`/
  `evolve.py`/`init.py`; `iso.py` corrigido pra `.claude/*.yaml` (checkpoints
  vivem em `claude_dir`, não em `state/`).
- **M9 HELP-DOC-PATH** (W-DEBT, 2026-06-18) — `cli._print_help` resolve o
  caminho do doc de command-surface via `forge_home()` (XDG-aware) em vez do
  `~/Documents/feature-forge/docs/...` hardcoded que não resolvia em instalações
  XDG.
- **M8 template rules** (W-DEBT, 2026-06-18) — `templates/qa-finding.template.json`
  e `templates/qa-report.template.json` ganharam `_template_description` +
  `_template_rules` (guide-keys `_*` toleradas pelos validators). Spec YAML
  `data-contract-spec.template.yaml` trocou o free-text enum
  `{{server_only_local_only_both_none}}` por placeholder + comment-enum
  (`# one of: server-only | local-only | both | none`).
- **IMPLEMENT-HANDOFF docstring** (W-DEBT, 2026-06-18) — docstring de
  `engine/implement.py` clarificado: `forge implement` ORQUESTRA o lifecycle e
  faz handoff de autoria-de-código pro host (Decisão 22), NÃO gera código nem é
  stub quebrado a completar. É o exec model canônico.
- **C-001 JSON carve-out vazava intent protocol** (W3 holistic review, 2026-06-18) —
  `forge verify` e `forge graph` (read-commands no allowlist `_JSON_CAPABLE_COMMANDS`)
  tinham caminho de prompt NÃO gateado em `output_mode.is_json_mode()`. Sob
  `FORGE_OUTPUT=json` (ou `--json`) o modo global resolvia JSON, `renderer.write`
  virava no-op, mas o handler ainda alcançava `question.ask` → disparava
  `PausedForInputError` (exit-2, reservado ESTRITO pro intent protocol DRIFT-1)
  com a prosa do prompt engolida e um `<FORGE_INTENT/>` marker órfão corrompendo
  o stdout-puro-JSON. Agora `verify.run()` resolve scope sem prompt em JSON mode
  e emite erro determinístico (stderr + exit 1) quando ambíguo; `graph_cli.run()`
  exige query explícita sob JSON mode global e sai com erro em vez de cair no
  menu interativo. Testes de regressão em `tests/unit/test_json_mode_no_intent_leak.py`.
- **H-001 erro amigável sumia em `verify --json`** (W3) — `ProjectRootNotFound`
  em JSON mode escrevia via `renderer.write` (no-op), perdendo a mensagem
  descritiva. Agora espelha `status`/`doctor`/`memory`: emite `forge verify: <exc>`
  em stderr + exit 1, stdout puro.
- **H-002 workflow router cobria só 6 de 11 estados** (W3) —
  `engine.status._suggested_next_command` deixava `not-started`/`aborted`/`done`/etc.
  caírem no default `doctor`, mis-guiando o agente. Agora mapeia todos os estados
  de `_VALID_STATES` (`not-started→plan`, `aborted→plan`, `done→status`, etc.).
  Teste parametrizado cobre o enum inteiro. (O fork PHANTOM-STATES do `verified`
  foi resolvido em W-DEBT — `verified`/`paused` removidos do enum, router de
  11 → 9 estados; ver `### Removed`.)
- **W-003 router não-determinístico com timestamps None** (W3) —
  `max(key=last_action_at or "")` colapsava features sem timestamp em `""` e
  retornava a primeira por ordem de iteração. Agora o tie-break é estável
  (timestamp, depois slug), tornando o verbo sugerido independente da ordem.
- **C2 DEAD-VERIFY** (W2 — protocol robustness, 2026-06-17) — `hooks/git-pre-commit`
  agora checa o validador em `.claude/forge/hooks/` (sub-namespace canônico de
  consumidores) além do path legado `.claude/hooks/` (repo maintainer). O gate
  pre-commit deixou de ser no-op silencioso em projetos inicializados via
  `forge init`. Teste de integração exercita a cadeia REAL do delegator
  (`tests/integration/test_git_pre_commit_delegator.py`).
- **C4 CONC-1** (W2) — `engine/utils/json_io.write_json` usa tempfile por-processo
  (`{pid}.{uuid}.tmp`) eliminando torn write / `FileNotFoundError` quando dois
  forge escrevem o mesmo state file (C4-A). `engine/ui/intent_state.pending_lock`
  (novo CM `fcntl`/`msvcrt`) é APLICADO na seção crítica real
  `detect_race`+`write_pending` de `engine/host/adapters/intent_file.py::_ask_loop`,
  fechando a janela TOCTOU em produção (C4-B). Os testes de concorrência
  (`test_intent_state_concurrency.py`) tiveram as asserções flipadas de
  "documenta o gap" para "sem torn write" e ganharam um teste do caminho real do
  adapter sob contenção.
- **A3 ENV-1** (W2) — `engine/host/env.scrubbed_subprocess_env` remove sinais de
  host agêntico (CLAUDECODE / OPENCODE_* / CODEX* / CURSOR_* / FORGE_FORCE_*_MODE)
  do env de subprocessos spawnados por `engine/ingest.py`. Um forge aninhado não
  escolhe mais o adapter errado nem pende esperando driver inexistente.
- **A4 REPLAY (card-removal)** (W2) — `forge reconfigure` defere o `shutil.move`
  (snap → `.bak`) da remoção de card pra DEPOIS do apply-confirm. Cancelar não
  deixa mais o snapshot removido sem a config correspondente. O campo interno
  `_pending_card_removals` nunca é persistido (nem na config, nem no draft) —
  um resume não re-dispara o move.
- W-GRAPH I-1: header do `_GRAPH_SKILL_MD` (artefato `forge init`) não afirma
  mais "17 graph queries canônicas" quando a tabela lista um subconjunto das
  mais frequentes — agora descreve a tabela como "principais" e aponta o
  catálogo completo (`q1`..`q17` + `r`) via `forge graph --json`.
- W-GRAPH I-4: abertura do `_GRAPH_FIRST_MD` deixou de prometer de forma
  absoluta um grafo populado — texto condicional ("quando este projeto tem
  fontes suportadas indexadas") cobre o caso greenfield, onde o grafo pode
  estar vazio até a primeira indexação e as queries retornam listas vazias.
- W-GRAPH I-5: novo teste `test_doc_query_labels_match_handlers` amarra os
  labels canônicos da tabela do `_GRAPH_SKILL_MD` (ex.: `q3` (orphan-files)) a
  `engine.graph_cli._HANDLERS` — renomear um label no código sem atualizar o
  doc gerado passa a quebrar o teste (fecha drift docs-vivo↔código latente).
- W-GRAPH I-6: `test_skill_file_path_matches_hook_reference` agora lê o corpo
  do `session-start-drift-check.sh` e assere que o path `.claude/forge/graph-skill.md`
  aparece literalmente nele — antes só provava o lado do init; renomear o path
  num lado sem o outro não quebrava teste.
- W-GRAPH I-2: `session-start-drift-check.sh` agora detecta TTY no fd 2
  (stderr) e não no fd 1 (stdout). O lembrete graph-first é emitido em stderr
  (`} >&2`), então a heurística de host-awareness precisa casar o stream usado
  — antes (`-t 1`) ela mentia em redirecionamento assimétrico (stdout pra
  arquivo + stderr no terminal renderizava ASCII; vice-versa escrevia emoji
  num log). Test helper de integração ligado a stdout+stderr no mesmo pty pra
  acompanhar.
- CASING-BUG: `_render_template` agora preenche `{{feature_slug}}` lowercase
  (a forma que os templates usam) + os tokens de origem — antes só substituía
  `{{FEATURE_SLUG}}` uppercase e o token lowercase sobrava cru nos artefatos
  gerados.

### Changed

- `engine/vision/screenshot.py` (antes dormente) agora é ligado ao front-door
  do `forge plan`: screenshot fornecido conversacionalmente na source-inquiry
  é sanitizado (normalize traversal-safe), validado, copiado pra
  `{feature}/screenshots/` e registrado com fingerprint sha256. Aceita também
  mockup externo validate-gated. O engine não interpreta pixel — `platform_hint`
  é só hint de baixa confiança que o conductor pode sobrepor.
- `_render_template` passou a fazer substituição single-pass (sem reinjection
  de token entre passos).
- **C3 EXIT-2-COLLISION (load-bearing UX/contract)** (W2 — protocol robustness,
  2026-06-17) — recontrato estrito de exit codes: `2` é reservado SÓ pra pausa
  (`PausedForInputError` + `UserPausedError`); a escada legada (3/4/5/6/7/8 +
  not-a-project=2) colapsou em `exit 1` + tag machine-readable `[FORGE-ERR:<TAG>]`
  em stderr. `127` (editor-not-found) preservado como exceção POSIX. Tags
  canônicas centralizadas em `engine/ui/exit_codes.py` (`fail_with_tag`). Contrato
  + tabela de tags em `docs/design/06-command-surface.md §Exit codes`. Clean-break
  pré-produção (sem migrator; único caller é o driver host). Decisão 27 honrada
  (pausa), não revisitada.
- **BL-01: C3 EXIT-2-COLLISION — fecha o último escape** (W2 review holístico,
  2026-06-18) — `engine/undo.py` ainda retornava `2` puro em
  `ProjectRootNotFoundError` (fora de projeto forge) — colidia com `EXIT_PAUSED`
  e o host lia como paused-for-input, procurando um pending nunca escrito (hang).
  Migrado pra `fail_with_tag(ERR_PROJECT_NOT_FOUND)` (exit 1 + tag). O teste de
  contrato (`tests/unit/test_exit_code_contract.py`) deixou de varrer uma lista
  hardcoded de 8 handlers (que escondia `undo`) e agora AUTO-DESCOBRE todos os
  handlers despachados a partir de `engine.cli.COMMANDS` — qualquer handler novo
  entra no contrato sem editar o teste. `undo` adicionado à linha `PROJECT-NOT-FOUND`
  da tabela de tags; descrição de exit codes do `forge upgrade` corrigida (era
  "exit 4", agora "exit 1 + `[FORGE-ERR:UPGRADE-FAILED]`"). 7 testes legados que
  trocaram `==N` por `==1` ganharam assert da tag (`[FORGE-ERR:<TAG>]`), travando
  a categoria do erro além do código.

## [1.4.0] - 2026-06-17

Esforço codinome v1.3-pilot-ready; shipa como 1.4.0 (1.3.0 = graph-ia, já em main).

Release piloto: host abstraction completa, adapters para os 4 contextos de
execução (Claude Code / TTY / Opencode / IntentFile), init brownfield-safe,
instalador curl one-liner, `forge upgrade`, e 7 bugs MeoBonsai fechados.
Clean-break deliberado frente a v1.2.x — projetos experimentais reinicializam.

### Added

- **`engine/host/` module** — abstração de host completa: adapter ABC
  (`HostAdapter`, `HostName`, `AskKind`, `AskResult`) + env detectors
  (`CLAUDECODE` / `OPENCODE_*` / `CODEX_*` / `CURSOR_*`) + registry +
  detecção de host com precedência config > env > TTY > fallback. Wave 0.
- **`ClaudeCodeAdapter`** — adapter in-process para Claude Code: emite
  marcador stdout `<FORGE_INTENT/>` que o host intercepta em tempo real;
  zero subprocess overhead. Wave 0.
- **`IntentFileAdapter`** — adapter DRIFT-1 fallback: escreve intent JSON em
  `.claude/forge/state/forge-pending.json`, lê response de
  `.claude/forge/state/forge-response.json`, exit 2 sinaliza pausa pro host.
  Wave 0.
- **`TtyAdapter` in-process** — `engine/host/adapters/tty.py`: lê
  `sys.stdin` diretamente (line buffered), valida resposta localmente e
  devolve `AskResult` ao engine sem subprocess. Substitui
  `engine/ui/tty_bridge.py` subprocess-loop. `engine/ui/_stdin_prompt.py`
  extrai helpers de prompt/validação reusados pelo adapter. Wave 2.
- **OPENCODE → `IntentFileAdapter` fallback (Veredito B)** — research W2.T0
  (`docs/research/opencode-tool-api.md`) documentou que opencode NÃO suporta
  adapter in-process: stdout de subprocess não é interceptado em tempo real e
  não existe env var oficial confiável. Veredito B: opencode usa
  `IntentFileAdapter` como fallback, sem execução in-process de tools.
  Spec R1 success criterion #4 atendido. `engine/host/detect.py::detect_opencode`
  permanece documentado como **aspiracional/inativo** — não há env var oficial
  confiável pra opencode, então a resolução cai no fallback intent-file por
  design (clarificação cross-AI review PR #17). Wave 2.
- **Sub-namespace `.claude/forge/`** — isola state e hooks do forge do
  `.claude/` do usuário. Novos helpers em `engine/utils/paths.py`:
  `forge_dir`, `forge_config_path`, `forge_state_dir`, `forge_cards_local_dir`,
  `forge_hooks_dir`. `engine/init.py` escreve projetos greenfield sob
  `.claude/forge/`. 50+ callsites em engine/ + validators/ migrados. Wave 0.
- **Brownfield-safe init (Wave 1)** — `_detect_brownfield` detecta
  `.claude/{skills,agents,settings.json}`. `engine.utils.settings_merge`:
  `merge_settings_json` append-only com dedup-via-deep-equal +
  `read_settings_tolerant` JSON5-tolerante (comments + trailing commas via
  lib `json5`). `engine.init._install_git_hooks` reescrito como chained
  delegator: hooks existentes do usuário migram para `<name>.user` e são
  encadeados via bash wrapper com `FORGE_DELEGATOR_MARKER`. Idempotente;
  faz upgrade de installs symlink-style antigos. Fixture sintética
  `tests/fixtures/meobonsai-class/` (5 skills + 3 agents + 2 user hooks +
  settings.json + CLAUDE.md) valida 3 regression tests + 3 brownfield
  contract tests. Nova dep: `json5>=0.9.10` em `pyproject.toml`.
  `engine.init._run_pipeline` invoca `_merge_forge_hooks_into_settings`
  pós-install de hooks: registra SessionStart → session-start-drift-check.sh;
  PostToolUse(Edit|Write|NotebookEdit) → post-edit-codebase-graph.sh;
  PostToolUse(Write) → post-write-feature-artifact.sh; SubagentStop →
  post-subagent-validate.sh. Tudo apontando para `.claude/forge/hooks/`.
- **`scripts/install.sh`** (244 LOC, bash 3.2 portável) — instalador curl
  one-liner. Clone `--depth=1` de `github.com/thgMatajs/feature-forge` em
  `FORGE_HOME` (`~/.local/share/feature-forge` — XDG default) + criação de
  venv + `pip install -e .` + symlink em `~/.local/bin/forge`. PATH detection
  marker-guarded e idempotente: detecta `~/.zshrc` / `~/.bashrc` /
  `~/.config/fish/config.fish` e oferece 3-caminhos (auto-append / manual /
  skip). Alias conflict detection: se `forge` já existe no PATH (de outro
  tool), propõe `forge-cli` como `BIN_NAME` alternativo via 3-caminhos.
  Wave 4.
- **`engine/upgrade.py`** + subcomando **`forge upgrade`** — git
  `pull --ff-only` na `FORGE_HOME` + venv refresh (`pip install -e .
  --upgrade`) + smoke (`forge --version`). Rollback automático
  (`git reset --hard prev_head`) em falha de smoke. API pública:
  `run_upgrade(*, forge_home=None, force=False) -> int`. Wired em
  `engine/cli.py` `COMMANDS` (subcomandos 13 → **14**) e em
  `_BOOTSTRAP_SKIP`. Wave 4.
- **Per-host e2e** — `tests/e2e/test_per_host_dispatch.py` (claude_code
  adapter via marker+exit2 / intent_file pending round-trip / opencode
  fallback) + `tests/e2e/test_tty_adapter_pty.py` (TtyAdapter via pty,
  stdin in-process sem subprocess). Cobertura dos 4 caminhos de detecção
  de host. Wave 2.
- **Pilot smoke e2e** — `tests/e2e/test_install_sh.bats` +
  `tests/e2e/test_install_sh.py` (PATH/alias/version scenarios; skipif bats
  ausente) + `tests/e2e/test_forge_upgrade.py` (pull cycle + rollback via
  repos git locais). Wave 4.
- **Renderer ASCII fallback non-TTY** — `engine/ui/renderer.py::write()`
  degrada box-drawing Unicode (┌┐└─│) pra ASCII (+,-,|) em contextos
  non-TTY via `_BOX_TO_ASCII` map + `to_ascii_box()` helper. Corrige bug U3:
  box-drawing virava `?` em pipes e captura de stdout em CI. Wave 2.
- **Parser fixes (PR #16 Wave A)** — Objective-C: body extraction
  brace-matched + `_mask_strings_and_comments` + categorias
  `@interface Foo (Bar)` / class extensions `@interface Foo ()` como símbolos
  próprios; P-N-018 pre-computa posições de `@end` (evita O(N²)). XML:
  prefixes fully-qualified, sanitização de IDs, perf de attributes,
  cobertura de view IDs e data-binding actions. Java: generics em assinatura,
  modifiers (default/static/synchronized/etc.), tipos de retorno
  parametrizados. Kotlin: logging consistente + docstring sobre limites regex.
  `_mask_strings_and_comments` promovido para `engine/graph/_body_text.py`
  (módulo compartilhado); `engine/graph/kinds.py` consumido por parsers
  (deixa de ser dead code).
- **Test coverage additions (PR #16)** — cobertura nova em arquivos
  preexistentes (delta full suite 1548 → 1619 = +71):
  `tests/unit/test_parser_objc.py` 14 → 25; `tests/unit/test_parser_xml.py`
  7 → 13; `tests/unit/test_parser_java.py` 9 → 19;
  `tests/engine/test_migrations.py` 2 → 5 (T-N-012);
  `tests/integration/test_multilang_graph_build.py` cobertura expandida
  (T-N-011). 84 tests em arquivos novos do PR (Java 19 + ObjC 25 + XML 13 +
  bootstrap 6 + lazy 6 + json 9 + migrations 5 + integration 1).
- **Regression suite MeoBonsai** (`752b0fd`) —
  `tests/integration/test_bug_regressions.py` cobre 7 cenários
  integration-level: 3 críticos (bug #1 intent-id mismatch, bug #2 stale
  response poisoning, bug #3 piped stdin) + 4 utilitários (U1 exit codes,
  U2 WARN, U3 ASCII fallback, U4 qa sem-args). Wave 3.

Test counts finais (pós-Wave 4 + pilot-blocker fix + remediação cross-AI review
PR #17): rapid **1611 passed**, integration **168 passed**, e2e **30 passed**,
0 falhas.

### Changed

- **install.sh + forge upgrade agora baseiam-se na última release tag** (não no main bleeding-edge). `scripts/install.sh` descobre a última tag `v*` (`git ls-remote --tags --sort=-v:refname`) e clona ela (`--branch <tag>`, detached HEAD na release; fallback main se não há tags). `forge upgrade` faz `git fetch --tags` + checkout da última tag (rollback pra tag/sha anterior em smoke fail). Garante que instalações e upgrades rodem releases estáveis, não commits intermediários de main.
- **`validate_workflow_config.py` → `validate_forge_config.py`** — validator
  renomeado + classe `ValidateWorkflowConfig` → `ValidateForgeConfig` + schema
  bump 1.2 → 1.3. Wave 0.
- **`engine/ui/question.py` delega ao host adapter** — `ask` / `ask_multi` /
  `ask_text` / `ask_three_paths` / `confirm` delegam ao adapter registrado,
  preservando exception classes, normalização de tokens e semântica de
  pause/cancel. `ask_three_paths` e `confirm` foram migrados pro adapter na
  remediação cross-AI review (eram os últimos consumidores nativos), fechando
  a unificação de todos os caminhos de prompt sob o host. Wave 0 + remediação
  PR #17.
- **Resolução de config ativa unificada (`active_config_path`)** — todos os
  comandos passam a resolver a config via `engine/utils/paths.py::active_config_path`,
  com precedência primário `.claude/forge/forge-config.yaml` (se existe) →
  legado `.claude/workflow-config.yaml` (se existe) → primário como destino de
  escrita canônico quando nenhum existe. Antes, vários comandos liam apenas o
  legado. Migrados: `status` / `verify` / `reconfigure` / `cli` / `doctor` /
  `implement` / `evolve` / `memory` / `ingest` / `undo` / `raw` + a resolução de
  feature-roots. Leitura e escrita caem no mesmo path resolvido (sem split).
  Remediação cross-AI review PR #17.
- **`bin/forge` dispatcher simplificado** — `exec python -m engine.cli`
  diretamente em todos os casos; detecção de host (TTY, ClaudeCode, opencode,
  intent-file) 100% no lado Python via `detect_host()`. Branch
  `FORGE_FORCE_TTY_MODE` removida (clean break — `tty_bridge.py` não existe
  mais). Wave 2.
- **Exit codes unificados** — `forge graph`, `forge memory`, e
  `forge reconfigure` invocados antes de `forge init` (pre-init) agora
  retornam exit 1. Contrato completo: `pre-init=1 / intent-pause=2 /
  cancel=130`. Wave 3 (bug U1).
- **`FORGE_FORCE_INTENT_MODE` movido para `detect_host`** — preserve escape-hatch
  DRIFT-1 §439 pós clean-break de `tty_bridge.py`. Wave 2.
- **`intent_state._state_dir` default migrado** — de `.claude/state/` para
  `forge_state_dir(project_root)` = `.claude/forge/state/`. Fecha 13 falhas
  de integration pré-existentes (tty_bridge + question.confirm/ask_three_paths
  lendo do path legacy enquanto adapters escrevem no sub-namespace). ~50 test
  path assertions migrados. Wave 1 follow-up.
- **Bootstrap hardening (PR #16 Wave C)** — `.claude/bootstrap.sh`: `flock -n`
  em `.claude/state/bootstrap.lock` previne race em runs simultâneos (fallback
  gracioso quando flock indisponível no macOS); captura stderr de
  `pip install -e .` em `.claude/state/pip-install.log`; log de
  `forge graph --json q3` em `.claude/state/bootstrap-graph.log`; glob
  `hooks/git-*` substitui lista hardcoded.
- **`hooks/post-edit-codebase-graph.sh` early-exit** — pula re-ingest custoso
  em `*/build/*`, `*/node_modules/*`, `*/.gradle/*`, `*/dist/*`, `*/target/*`,
  `*/DerivedData/*`, `*/.next/*`, `*/out/*` (PR #16 T-N-017).
- **Engine robustness (PR #16 Wave B)** — symlink-safe walker via `scandir`
  (substitui `rglob`) em `engine/graph/builder.py`; narrow de exceptions em
  handlers + fail-loud em invariants quebrados em `engine/cli.py`; TOCTOU
  migration race coberto por commit-after-migration em
  `engine/utils/sqlite_io.py`; overload collision em parsers Kotlin/Java
  emite warning estruturado em vez de silent overwrite.

### Changed (load-bearing)

- **Revisita decisão 18**: skill location → `~/.local/share/feature-forge/`
  (XDG default; respeita `$XDG_DATA_HOME`). Era `~/Documents/feature-forge/`.
  Razão: XDG é convenção universal pra ferramentas instaladas via script;
  `~/Documents/` confunde com o diretório de docs do usuário. Linha antiga
  preservada em `docs/design/01-decisions.md` (row 18 superseded by row
  18-v2). `scripts/install.sh` já usa o destino XDG. Wave 5.

### Fixed

- **CLI lifecycle — `cli.main` limpa pending/response no exit de sucesso**
  (remediação cross-AI review PR #17, BL-001) — no terminal exit de SUCESSO
  (exit 0, não-paused, não-erro), `engine/cli.py::main` agora chama
  `clear_intent_files` (apaga `forge-pending.json` + `forge-response.json`),
  além de limpar o intent-log. Os paths de erro (mismatch / race / schema)
  continuam preservando pending+response pra forense (SPEC §3). Corrige
  `IntentMismatchError` espúrio no comando seguinte a um comando terminado em
  `confirm` / `ask_three_paths`: o stale `forge-response.json` de um comando já
  concluído não envenena mais o próximo. Honra o contrato documentado em
  `clear_intent_log_only` sem reintroduzir cleanup per-prompt. Afeta
  IntentFileAdapter (fallback opencode + harnesses disk-based) e
  ClaudeCodeAdapter; TTY é imune (sem state em disco). Regression test cobre
  invocação-3-após-confirm.
- **`install.sh` — smoke falho sai com exit≠0** (remediação cross-AI review
  PR #17, HIGH) — `scripts/install.sh` falha explicitamente (exit 1) quando o
  smoke pós-instalação (`forge --version`) não passa, em vez de aparentar
  sucesso. Além disso valida `LATEST_TAG` como semver (`case` + `printf | grep
  -Eq` ancorado, bash 3.2 portável) antes de `git clone --branch <tag>`; tag
  malformada cai no fallback `main` com aviso. e2e `test_install_sh_real.bats`
  roda o script íntegro contra um remote `file://` fake, cobrindo tag válida E
  `vGARBAGE` → fallback.
- **`forge init` — `.claude/settings.json` corrompido/ilegível vira backup**
  (remediação cross-AI review PR #17, HI-001) — `engine/init.py` faz backup
  `.bak` + warn em vez de sobrescrever silenciosamente quando o settings.json
  do usuário não pode ser lido. O caso JSON inválido (`ValueError`) e o caso de
  leitura falha (`OSError`) tentam `backup_file` antes de prosseguir; se o
  backup também falha, o merge não escreve por cima (preserva o arquivo
  intacto). Brownfield-safe: zero perda silenciosa de config do usuário.
- **`forge upgrade` — rollback re-roda o venv refresh** (remediação cross-AI
  review PR #17) — quando o `pip install` do upgrade falha, o rollback de
  `engine/upgrade.py` agora re-executa `_pip_refresh` na revisão restaurada,
  simétrico ao path de smoke-fail. Antes restaurava só o código (git reset),
  deixando as deps no estado pós-falha; agora restaura código E deps.
  `CalledProcessError` no re-refresh é surfado ("rollback ou pip re-refresh
  falhou — estado pode estar inconsistente"), não mascarado.
- **TTY — `ask_multi` re-prompta seleção fora dos limites** (remediação cross-AI
  review PR #17) — `engine/host/adapters/tty.py` re-pergunta (dentro do budget
  de tentativas) quando a seleção viola `min_selected`, em vez de estourar.
  Espelha exatamente o `len(result) < min_selected` de `question.ask_multi`.
- **Bug #1 — intent-id mismatch (DRIFT-1 multi-pergunta-por-ciclo)** —
  `engine/ui/intent_state.py::read_response` e `detect_race` agora tratam
  `intent-id` já presente no consumed-log como stale-leftover (resposta de
  pergunta anterior na mesma invocação), não como erro: `read_response` retorna
  `None` (caller emite novo pending), `detect_race` varre e remove o pending
  stale. Comandos multi-pergunta-por-ciclo (ex.: `forge reconfigure`
  category→submenu) funcionam sob host real sem `IntentMismatchError` espúrio.
  Mismatch genuíno e race genuíno ainda levantam `IntentMismatchError` /
  `RaceDetectedError`. Drive loop limpo em e2e reconfigure via
  `drive_intent_loop`. Refs commits 5827900/7c26377. Wave 2.
- **Bug #2 — stale response poisoning** — `read_response` verifica
  consumed-log antes de consumir response, evitando que response de
  intent-id anterior envenene ciclo seguinte. Coberto pela regression suite
  MeoBonsai (bug #2 scenario). Wave 2.
- **Bug #3 — TtyAdapter guard non-TTY com mensagem DEPRECATED** (`00dad0d`)
  — `engine/host/adapters/tty.py` detecta stdin piped (non-TTY interativo)
  e emite mensagem `DEPRECATED v1.3` orientando ao uso do harness agentic
  ou terminal real, em vez de travar aguardando input que nunca chega.
  Wave 3.
- **Bug U1 — exit codes unificados** (`edfd20c`) — ver seção Changed acima.
  Wave 3.
- **Bug U2 — WARN de cleanup suprimido em `--help`/`-h`/sem-args** (`d9d3bb5`)
  — guard `is_help` adicionado no bloco `finally` de `engine/cli.py`;
  invocações de ajuda e sem argumentos não emitem mais o aviso de cleanup de
  log. Residual: bloco `finally` captura `ProjectRootNotFoundError`
  silenciosamente em contextos pre-init (`b0fcb35`). Wave 3.
- **Bug U3 — renderer ASCII fallback** — ver seção Added acima. Wave 2.
- **Bug U4 — `forge qa` sem args apresenta 3-caminhos** (`137a993`) — guard
  adicionado em `_qa_run` antes de `resolve_scope`; ao ser invocado sem
  argumentos, exibe bloco mentor-calmo de 3-caminhos em stdout com exit 0,
  sem `ValueError` nem traceback. Wave 3.
- **e2e env scrub** — `tests/e2e/conftest.py::env_with_forge_home` faz scrub
  de variáveis agentic (`CLAUDECODE`, `OPENCODE_*`, `CODEX_*`, `CURSOR_*`)
  antes de iniciar subprocesso forge. Sem o scrub, suites rodadas dentro de
  Claude Code herdavam o env agentic e roteavam pro adapter errado — e2e
  não-determinístico dependendo do host de CI. Bug pré-existente surfaced
  durante verificação Wave 2. Wave 2.
- **`scripts/install.sh` bash 3.2 portability** (`b5d0bee`) — substituição
  `${var,,}` → `echo "$var" | tr '[:upper:]' '[:lower:]'` para
  compatibilidade com o bash 3.2 default no macOS. Wave 4.
- **`test_read_settings_tolerant_handles_comments` skipif** — pula quando lib
  `json5` ausente (system pytest fallback); os outros 4 testes de
  settings_merge funcionam com fallback stdlib `json`. Wave 1 follow-up.
- **find_project_root marker mismatch (pilot-blocker)**: `engine/utils/paths.py::find_project_root` reconhece agora `.claude/forge/forge-config.yaml` (marker v1.3 que `forge init` cria) como raiz de projeto, além do legacy `.claude/workflow-config.yaml` (compat v1.2). Antes, após `forge init` greenfield, os ~12 comandos que resolvem a raiz via find_project_root levantavam ProjectRootNotFoundError ("não inicializado") mesmo com o projeto inicializado — ciclo init→uso quebrado. Gap herdado da migração de sub-namespace (Wave 0), não coberto por teste (testes semeavam o marker legacy à mão). Regression test fecha o gap (init greenfield → find_project_root resolve + comando de subdir funciona).
- **`install.sh` — guarda disponibilidade de `/dev/tty` em ambiente
  não-interativo** (review PR #17, F27 + F28) — os dois prompts interativos
  (conflito de binário + setup de PATH) ganham guard 3-vias: stdin tty → lê
  do stdin; senão `/dev/tty` legível → lê de `/dev/tty`; senão (curl|bash em
  CI/Docker sem terminal) assume o default seguro e avisa em vez de ler de
  `/dev/tty` sob `set -euo pipefail` (que abortava o install inteiro). Default
  seguro: conflito de binário → instala como `forge-cli` (não sobrescreve o
  `forge` existente); PATH → imprime a linha manual sem editar o rc file.
- **tests/upgrade — asserts de rollback e warning de no-tags reforçados**
  (review PR #17, F37 + F38) — `test_upgrade_rollback_on_smoke_fail` passa a
  verificar a sequência completa de checkout (forward pro tag de release
  ANTES do rollback pro prev_sha), não só a última chamada;
  `test_upgrade_no_op_when_no_tags` captura stdout via `capsys` e ancora no
  warning documentado do branch sem release tags. Asserts existentes
  preservados; mudança aditiva.

### Removed

- **`engine/ui/tty_bridge.py` subprocess-loop** — substituído por
  `engine/host/adapters/tty.py` in-process (TtyAdapter). `tty_bridge`
  re-invocava o engine completo via subprocess pra cada pergunta TTY —
  model mental mais complexo, mais lento, gerava processos extras. Clean
  break; sem shim de retrocompatibilidade. Wave 2.
- **`FORGE_FORCE_TTY_MODE` branch em `bin/forge`** — env var de fallback pra
  `tty_bridge` removida junto com o módulo. `FORGE_FORCE_INTENT_MODE`
  preservado em `detect_host` (escape-hatch DRIFT-1 diferente). Wave 2.
- **`tests/e2e/test_tty_bridge_e2e.py`** e **`tests/unit/test_ui_tty_bridge.py`**
  — testes do subprocess-loop removidos. Cobertura equivalente migrada para
  `test_tty_adapter_pty.py` e `test_per_host_dispatch.py`. Wave 2.
- **Nenhum migrator v1.2→v1.3** — clean-break deliberado. Projetos
  experimentais em v1.2 reinicializam: limpar `.claude/` + `forge init`.

### Deferred (anotados em `docs/design/04-pending.md`)

- **P-N-007** (is_method_call heurística refinamento — exige parser real,
  fora do escopo regex)
- **N-004** (AC-11 escopo bootstrap-detection — policy decision pendente
  com user)
- **N-007 / N-015** (silent audit log em `.claude/state/hook-failures.jsonl`
  — cross-cutting cross-hook)
- **N-012** (migrations dentro de transaction — refactor estrutural;
  parcialmente coberto por commit-after-migration)
- **N-013** (3-state helper `_db_has_full_rebuild_marker`)
- **M-003** (perf O(N²) Java/XML — pre-compute newlines positions via
  `bisect`; ObjC já coberto por P-N-018, registrado pra v1.3.1+)
- **T-N-025** (plan-auditor severity calibration — DOC only, exige
  discussion com user antes de mexer)

## [1.3.0] — 2026-06-15

### Added (graph-ia-evolution — body column + multi-language parsers + --json + onboarding UX)

Expansão do codebase graph pra consumo direto por IA: símbolos agora
carregam `body` text, novos parsers cobrem Java/XML/ObjC, flag `--json`
habilita queries non-interactive, e onboarding UX detecta bootstrap state
ausente. 8 ondas lógicas (11 commits atômicos: plan-extension + extension-fix
+ doc-sync ficaram em commits separados das ondas principais) acumuladas em
`feat/graph-ia-evolution`.

- **`symbols.body` column** — `engine/utils/sqlite_io.py` ganha
  `_ensure_graph_body_column` (ALTER TABLE idempotente). DBs novos
  contêm `body TEXT` na criação; DBs existentes migram em-place sem
  rebuild + sem bump de `SCHEMA_VERSION`. Populado por todos os parsers
  com corpo delimitado por chaves (Kotlin/Swift/TS/Java/ObjC); NULL pra
  XML symbols. Habilita assistentes IA a inspecionar implementação direto
  do graph sem abrir o arquivo-fonte.
- **`forge graph --json <query> [args...]`** — flag non-interactive emite
  JSON parseável em stdout, sem prompts. Aceita aliases (`q1..q17`/`r`),
  numeric keys (`1..17`), ou labels textuais (`where-is-used`,
  `blast-radius`, …). Modo interactivo (`forge graph` sem `--json`)
  continua inalterado. Stderr reservado pra erros.
- **Java parser** — `engine/graph/parser_java.py` expõe
  `parse_java_file(text, path) -> JavaFileInfo`: package declaration,
  imports (incl. wildcards), classes/interfaces/enums/records (top-level
  e nested), methods/constructors com body text e reuse-intelligence
  metadata. Constructor distinguido de method via match de nome contra
  classe enclosing (heurística regex).
- **XML parser** — `engine/graph/parser_xml.py` expõe
  `parse_xml_file(text, path) -> XmlFileInfo`: view IDs (`@+id/...`),
  classes referenciadas (tag fully-qualified + atributos
  `android:name`/`class=`), data binding variables, resource keys
  (`string`/`dimen`/`color`/etc.), e expressões de binding action
  (`@{...}` com método invocado).
- **Objective-C parser** — `engine/graph/parser_objc.py` expõe
  `parse_objc_file(text, path) -> ObjcFileInfo`: `#import` e `@import`,
  `@interface`/`@protocol`/`@implementation`, methods (instance `-` e
  class `+`), properties com attributes (`nonatomic`, `strong`, …).
  Mensagens enviadas (`[obj selector]`) explicitamente NÃO geram call
  edges (non-goal v1.3).
- **Extensões `.java` / `.xml` / `.m` / `.mm` registradas** — em
  `_LANGUAGE_EXTENSIONS` (`engine/graph/builder.py`), `_GRAPH_EXTENSIONS`
  (`engine/ingest.py`), `_SUPPORTED_LANGS` (`engine/graph/_body_text.py`,
  exceto `xml` que não tem body extraction), e no `case` match de
  `hooks/post-edit-codebase-graph.sh`. Build full e incremental
  dispatcham os novos parsers via `_persist_java`/`_persist_xml`/
  `_persist_objc`.
- **CLAUDE.md AI consumption instructions** — seção `## Codebase Graph
  — IA-ready` instrui o modelo a consultar `forge graph --json <q>` antes
  de ler arquivos-fonte quando a pergunta cabe em Q1–Q17. Inclui
  exemplos canônicos por query + lista de linguagens cobertas.
- **Bootstrap state detection** — `engine/cli.py::_check_bootstrap_state`
  detecta `.git/hooks/pre-commit` symlink ausente/broken e emite friendly
  error instruindo o user a rodar `bash .claude/bootstrap.sh`. Onboarding
  UX pra novos devs num projeto que já tem forge.
- **Lazy graph auto-build** — `engine/graph_cli.py::_maybe_auto_build`
  detecta `.claude/graph.db` ausente/empty e dispara build inicial
  silenciosamente na primeira invocação de `forge graph` (~30s-2min,
  one-shot). Bootstrap script (`bash .claude/bootstrap.sh`) faz o mesmo
  build idempotentemente no setup inicial.
- **Flag `--no-auto-build`** — em `forge graph` desativa o lazy rebuild
  pra uso em CI/scripts determinísticos (espera que o DB já exista).
  Combina com `--json` pro pattern não-interativo completo.

### Changed (graph-ia-evolution)

- **`.claude/bootstrap.sh` Step 6** — após install de deps via
  `pip install -e .`, dispara build inicial do graph + inventory
  (idempotente). Sem isso, a primeira invocação de `forge graph`
  triggera lazy rebuild. Ambos caminhos convergem no mesmo state.

### Documentation (graph-ia-evolution)

- **`docs/schemas/graph.md`** — documenta a coluna `symbols.body`
  (semântica + populated-for + NULL-for + ALTER TABLE migration) e a
  flag `--json` (non-interactive JSON queries) com exemplos canônicos.
- **`docs/design/08-session-handoff.md`** — Estado v1.3.0 entregue;
  Última atualização 2026-06-15.
- **`README.md`** — §Stats bump (parser count 3 → 6, test count
  baseline + 84 tests novos em arquivos novos do PR: Java 19 + ObjC 25 +
  XML 13 + bootstrap 6 + lazy 6 + json 9 + migrations 5 + integration 1;
  full suite cresce de 1548 → 1619, +71 considerando cobertura nova em
  arquivos preexistentes — diferença é Wave A+B+C fix-pack pós-review)
  + §Command surface menciona `forge graph --json` como entrypoint
  non-interactive.
- **`docs/design/04-pending.md`** — registra v1.3.0 shipped + 6
  non-goals como follow-ups v1.4+ (tree-sitter, MCP server, ObjC call
  graph, call graph preciso, SCHEMA_VERSION bump, visualização
  gráfica). Critério explícito pra reentrada de cada um.
- **`docs/superpowers/plans/2026-06-12-graph-ia-evolution.md`** —
  extensão Task 9.5 (onboarding UX) + Step 9.6/9.7 (pending + README).

## [Unreleased — pre-1.3 carry-over]

### Changed

- **chore(gitignore)** — Adicionadas entradas faltantes pra runtime
  artifacts: `.claude/state/*.lock`, `.claude/worktrees/`, `.gsd-tmp/`,
  `.planning/*-review/` (generic), `.ultra-review/`, `docs/design/outputs/`.
  Reduz noise em `git status` pós-bootstrap.
- **chore(gitignore PR #14)** — `.planning/*` agora catch-all com whitelist
  explícita pra `det-3/`, `det-6/`, `drift-1/`. Scratch de review/audit/fix
  não polui mais o working tree.
- **`.claude/rules/orchestrator-persona.md`** — nova seção §Cleanup de
  `.planning/` ao final do trabalho — disciplina manual paralela aos `.bak`
  retention.

### Added (User-facing docs, 2026-06-12)

- **`docs/guides/getting-started.md`** — Guia de primeiros passos: onboarding completo para devs mobile, incluindo instalação, init, e adoção em time.
- **`docs/guides/daily-workflow.md`** — Guia de comandos do dia a dia: cobertura dos 13 comandos com cenários, exemplos e árvore de decisão.
- **`docs/guides/feature-lifecycle.md`** — Lifecycle de uma feature: pipeline do intake à retrospectiva, com artefatos e variações por subtipo.
- **`docs/guides/dot-claude-reference.md`** — Referência amigável dos arquivos `.claude/`: tabela versionado vs local, explicações detalhadas.
- **`docs/diagrams/bootstrap-flow.mermaid`** — Diagrama do fluxo de adoção do forge pelo time.
- **`docs/diagrams/feature-lifecycle.mermaid`** — Diagrama do pipeline completo de uma feature.
- **`docs/diagrams/command-decision-tree.mermaid`** — Diagrama de decisão: qual comando usar em cada situação.
- **`docs/diagrams/graph-query-flow.mermaid`** — Diagrama de fluxo de consulta do graph.
- **`docs/diagrams/files-versioned-vs-local.mermaid`** — Diagrama de arquivos versionados vs locais.

### Fixed (PR #14 docs review — 2026-06-15)

Aplicando findings do review independente do PR #14 (`docs/user-guides`).
Counts agora consistentes entre guides, diagrams, `CLAUDE.md` raiz e a
ground truth do `main`.

- **Counts factuais** corrigidos em todos os artefatos:
  - `forge doctor`: 14/12 → **16 categorias** (`engine/doctor.py` tem 16
    funções `_check_*`)
  - `forge verify`: 8/20/15 → **3 validators built-in + N contribuídos por
    cards ativos**; 21 validators no diretório `validators/` (era anunciado
    como 15 no `CLAUDE.md`)
  - Commands: 13 user-facing (ingest é hook interno, documentado como tal)
  - Tests: 637 → ~1531 (consulte handoff pra count atual)
- **`forge ingest`**: nova seção em `daily-workflow.md` documentando que
  é hook interno (não digitado manualmente) — fecha gap apontado em
  H-001.
- **`feature-lifecycle.md` Fase 5**: lista de gates expandida pra cobrir
  `check_no_invented_behavior`, `check_files_in_allowed_files`,
  `check_no_behavior_change` (refactor); separa gates da task do cascade
  completo do `forge verify`.
- **`feature-lifecycle.mermaid`**: Fase 6 corrigida pra `forge verify`
  (era `forge doctor`); `forge undo` movido pra subgraph TRANSVERSAL
  (não é comando de retrospectiva).
- **`files-versioned-vs-local.mermaid`**: `memory/L1/archived/` isolado
  no nó VERSIONADO; `memory/L1/ (WIP)` no LOCAL — resolve ambiguidade
  visual do nó único anterior.
- **`forge raw` (daily-workflow)**: adiciona `rebuild-templates` como 4º
  subcomando (estava omitido).
- **Q11–Q17 labels**: padronizado pra slugs canônicos em inglês entre
  `getting-started.md` (tabela), `daily-workflow.md` (menu) e
  `graph-query-flow.mermaid`.
- **Voz mentor calmo**: `shipada/shipado` → `entregue`; `Fora da caixa`
  → `Por padrão`; `Phase 6` qualificado como `Phase 6 do roadmap
  (docs/design/02-phases.md)`.
- **`CLAUDE.md` raiz**: counts em §Anatomia rápida e §Comandos úteis
  alinhados à ground truth.

### Changed (User-facing docs, 2026-06-12)

- **`README.md`** — Adicionada seção "Quick Start" com instalação e first steps + tabela "Guias do usuário" com links para os 4 guias.
- **`docs/design/08-session-handoff.md`** — Última atualização e seção de User-facing docs registrada.

### Fixed (master review PR #15 remediation — 2026-06-15)

Aplica todos os 22 findings do master review PR #15 (14 do Group A —
security/correctness + 8 do Group B — broad-except scrub + validators).
Test baseline 1350 → 1353 (3 testes novos de A-013 cobrindo o vetor de
path-traversal do guard de undo).

**Alto (A-001, A-002, A-003, B-001):**
- **A-001** (`engine/undo.py`) — `_delete_feature_artifacts_guard` agora
  rejeita também `target_resolved == project_resolved`. Sem isso, um slug
  malicioso `../../..` resolveria pra raiz e `shutil.rmtree` apagaria o
  projeto inteiro após os 2 confirms (`Path.relative_to` retorna
  `Path('.')` em equality, sem `ValueError`).
- **A-002** (`engine/undo.py`) — `_delete_feature_artifacts` agora usa
  `feature_path(..., subtype=current_subtype(...))` em vez de `feature_dir`,
  honrando o subtype enum. Features non-product (refactor/spike/chore/
  bugfix) — que vivem em `non-product/{slug}/` — voltam a ser delete-able
  via `forge undo`.
- **A-003** (`docs/design/04-pending.md`) — entrada H-02/MD-01 reforçada
  com referência explícita a A-003 e detalhamento do vetor YAML anchor
  bomb (`yaml.safe_load` sem flag nativa pra limitar aliases).
- **B-001** (`engine/status.py`) — `_render_recent_activity` agora pega
  `(MemoryError, OSError, UnicodeDecodeError)` em vez de
  `(JSONDecodeError, OSError, UnicodeDecodeError)`. `read_history` empacota
  `JSONDecodeError` em `MemoryError`, então a tupla antiga era no-op e
  JSONL corrompido crashava o status render.

**Médio (A-004, A-005, A-006, B-002, B-003):**
- **A-004** (`validators/check_secrets.py`) — detecção de colisão no
  `_rel_map` quando dois staged paths viram a mesma relativização (caso
  de projetos com symlinks). Modo conservador filtra com paths originais
  em vez de descartar silenciosamente.
- **A-005** (`validators/check_secrets.py`) — fail-loud em regex inválida
  na config `secrets-gate.ignore-paths` via `_collect_invalid_patterns` +
  `result_warn`. Antes era skip silencioso.
- **A-006** (`engine/utils/paths.py`, `engine/plan.py`) — promovido
  `_resolve_features_root` de plan.py pra paths.py (leaf real, sem dep
  de `engine.plan`). Elimina lazy import circular dentro de `feature_path`.
  Shim retrocompatível em plan.py.
- **B-002** (`engine/doctor.py`) — adiciona `CardError` à tupla de except
  em `_check_card_snapshots` + import. Race condition no
  `compute_directory_sha256` agora vira `_STATUS_FAIL` por categoria
  em vez de explodir o doctor inteiro.
- **B-003** (`engine/doctor.py`) — troca `(YamlIOError, OSError)` por
  `(yaml.YAMLError, OSError)` em `_stamp_last_doctor_run` + import yaml.
  `write_yaml` NÃO levanta `YamlIOError` (só `read_yaml` levanta) — o
  tipo real era `YAMLError` de `safe_dump`, que escapava silenciosamente.

**Baixo (A-007, A-008, A-009, A-010, B-004, B-005, B-008):**
- **A-007** (`engine/graph/builder.py`) — comment estendido do `finally`
  pra cobrir `ValueError` do guard de allowlist (sem mudança funcional).
- **A-008** (`engine/implement.py` + test) — `_topo_sort` troca
  `raise SystemExit` por nova `TaskGraphError(RuntimeError)`. SystemExit
  é `BaseException` e não era pego por `except Exception` de chamadores
  defensivos. CLI `run()` mapeia para exit code 1.
- **A-009** (`engine/verify.py`) — `run_scope` agora retorna `1` quando
  `project_root` não é diretório, espelhando o guard de `_run_validator`.
- **A-010** (`engine/persona/mentor_calmo.py`) — docstring de `set_seed`
  documenta thread-safety explicitamente.
- **B-004** (`engine/graph/builder.py`) — comments por-tipo justificando
  cada exception da tupla em `_populate_ds_components_from_inventory`.
- **B-005** (`validators/validate_workflow_config.py`) — comment
  justificando exaustividade do `OSError` em torno de `file_sha256`.
- **B-008** (`validators/validate_feature_package.py`) — `_check_cross_refs`
  reporta parse error como warn em vez de silenciar.

**Sugestão (A-011, A-012, A-013, A-014, B-006, B-007):**
- **A-011** (`engine/undo.py`) — narrow do broad-except em
  `_append_undo_log` pra `(OSError, ValueError)`, com aviso ao usuário.
- **A-012** (`engine/undo.py`) — narrow do broad-except em `_undo_evolve`
  pra `(KeyError, OSError, YamlIOError, MemoryError)`.
- **A-013** (`tests/engine/test_undo_delete_traversal.py`) — adiciona 3
  testes (target == project_root, symlink escaping project, slug literal
  `../../..`), cobrindo o vetor de A-001.
- **A-014** (`validators/check_no_invented_behavior.py`) — comment
  explícito + `noqa: E402` cobrindo `sys.path.insert` antes dos imports
  de `engine.`.
- **B-006** (`docs/design/04-pending.md`) — nota retrospectiva sobre
  scope hygiene do M-02 (parcialmente endereçado por A-008).
- **B-007** (`tests/unit/test_commands_{implement,plan,verify}.py`) —
  pin exit code in `{1, 2}` em vez de `!= 0` amplo.

### Fixed (master review remediation — final review, 2026-06-15)

- **Master review H-1** — Fix `engine/doctor.py:1308-1309` `_` redefinition
  (mypy no-redef): renomeou segundo binding para `_safe_read_yaml_ref` +
  corrigiu noqa code.
- **Master review M-1** — Atualizou `engine/graph/builder.py` para usar
  `GitIgnoreSpecPattern` (de `pathspec.patterns.gitignore.spec`) no lugar
  de `GitWildMatchPattern` (deprecated). Elimina ~1500 DeprecationWarnings
  em test runs.
- **Master review M-3** — Consolidou 3 cópias adicionais de `_utc_now_iso`
  em `engine/memory/{l1,l2,distiller}.py` para import direto de
  `engine.utils.iso.utc_now_iso`. Fecha LO-01 parcialmente (7 módulos
  restantes documentados em `04-pending.md`).
- **Master review L-1** — Atualizado campo `**Última atualização:**` do
  handoff para 2026-06-15 (refletindo final review remediation).

### Fixed (REVIEW.md remediation — Bloco 5: medium/low polish, 2026-06-12)

- **M-01** — Substituído over-mock em `tests/unit/test_commands_*.py`
  por assertions sobre exit code real.
- **M-05** — Removido `import json` interno em `_readiness_from_handoff`
  (side-effect Task 4.1 / H-03 narrow).
- **L-01 + L-04** — Removido parâmetro `project_root` dead em
  `_print_blocked_refusal` (`engine/implement.py`).
- **L-03** — Consolidado `_utc_now_iso_implement/_plan/_verify` em
  import direto de `engine.utils.iso.utc_now_iso` em `engine/implement.py`,
  `engine/plan.py`, `engine/verify.py` (5 shims, 12 callers). Shims
  similares em outros módulos (`engine/undo.py`, `engine/evolve.py`,
  `engine/reconfigure.py`, `engine/memory_cli.py`, `engine/graph_cli.py`,
  `engine/init.py`, `engine/doctor.py`) ficam fora de scope desta entrega
  — gap registrado em `04-pending.md` (LO-01 follow-up).
- **L-06** — `sys.path.insert` em `tests/conftest.py` mantido com
  comment justificando + gap aberto em `04-pending.md` pra revisitar
  quando CI pipeline oficial vier.
- **L-07** — Marker `meobonsai` registrado em `pyproject.toml`; 11 tests
  dependentes da fixture `meobonsai_root` agora carregam o marker.

### Added (REVIEW.md remediation — Bloco 3: mypy advisory, 2026-06-12)

- **H-09** — `mypy >= 1.8` adicionado em `[project.optional-dependencies]
  dev` + seção `[tool.mypy]` em advisory mode. Baseline de 17 errors
  registrado em `docs/design/04-pending.md`. CI gate não ativo nesta
  sessão (rollout incremental planejado).

### Changed (REVIEW.md remediation — Bloco 3: mypy advisory, 2026-06-12)

- **M-10** — Removido import unused `Optional` em `engine/implement.py`,
  `engine/verify.py`, `engine/status.py`, `engine/vision/screenshot.py`.
  19 usos remanescentes padronizados pra `X | None` intra-arquivo.

### Changed (REVIEW.md remediation — Bloco 2: functional bugs, 2026-06-12)

- **M-07 (dep nova)** — Adicionado `pathspec >= 0.12` em
  `[project.dependencies]` runtime. Lib pura Python implementando
  `.gitignore` semantics canonicas. Decision 19 (Python stack) e
  Decision 22 (no skill runtime deps) não afetadas — pathspec é PyPI
  lib genérica.

### Fixed (REVIEW.md remediation — Bloco 4: broad-except scrub, 2026-06-12)

- **H-03** — Narrow `except Exception` em 24 sites críticos:
  - `engine/implement.py`: 1 site (JSON read) narrowed; 3 sites preservados broad
    com `# noqa: BLE001` em validator/QA dispatch boundaries
  - `engine/verify.py`: 2 sites narrowed `(MemoryError, OSError)` em
    L1 status write/restore
  - `engine/graph/builder.py`: 1 site narrowed em inventory load
  - `engine/init.py`: 2 narrowed (overlay, FS copy) + 4 preservados em
    discovery-step heuristic scanners
  - `engine/status.py`: 1 site narrowed (L1 history JSON read)
  - `engine/doctor.py`: 2 sites narrowed (stamp write + category snapshot)
  - `validators/validate_*.py`: 18 sites narrowed em 10 validators
    (YAML reads + 1 file_sha256), `YamlIOError` adicionado aos imports

### Fixed (REVIEW.md remediation — Bloco 1: security quick wins, 2026-06-12)

- **H-01** — SQL allowlist em `_reset_domain_tables` previne wipe de tabela
  fora do conjunto canônico (`engine/graph/builder.py`).
- **H-02** — Cap de 10MB em `read_yaml` evita YAML bomb / anchor explosion
  (`engine/utils/yaml_io.py`).
- **H-04** — PRAGMA `foreign_keys = ON` em `finally` tolera erro de SQLite
  sem mascarar a exception original (`engine/graph/builder.py`).
- **H-06** — Path-traversal guard em `forge undo` delete-feature recusa
  rmtree fora do project_root (`engine/undo.py`).
- **H-07** — RNG de `mentor_calmo` isolado por call quando seed unset;
  contrato determinístico de tests preservado (`engine/persona/mentor_calmo.py`).
- **H-10 (parcial)** — Validação `project_root.is_dir()` antes do
  subprocess de validators retorna `degraded` em vez de crashar
  (`engine/verify.py`). Batch git-diff optimization fica deferred — ver
  `docs/design/04-pending.md`.
- **M-02** — Unknown task dep agora levanta `SystemExit` em
  `_topo_sort` em vez de tratar silenciosamente como satisfeita
  (`engine/implement.py`).
- **M-04** — `feature_path` consolidado em `engine/utils/paths.py`;
  `implement.py` agora encontra non-product features (refactor/spike/chore).
- **M-07 + M-08** — `pathspec` substitui parser custom de `.gitignore`;
  bracket classes, escapes, trailing space e `a/**/b` agora cobertos
  corretamente (`engine/graph/builder.py`).
- **M-09** — `validators/check_no_invented_behavior.py` reusa
  `git_staged_files` de `validators/_diff.py` (rename detection -M80%
  agora disponível).
- **M-12** — Ignore patterns em `check_secrets` âncoram em `^` —
  `src/tests/fixtures/secrets/...` não é mais false-positive ignored.

### Added (Phase B — DET-6 multi-axis backend, 2026-06-11)

- **Schema canônico multi-axis** — `docs/schemas/backend-axes.md` define
  8 axes (`data`, `auth`, `observability`, `analytics`, `storage`,
  `persistence`, `notifications`, `flags`) cada um produzindo
  `Map[axis][platform] → Cell | null`. Cell shape: `{card, status,
  migrating-to?}`. Validação enforçada via RULE-019..024 em
  `validate_workflow_config.py`. Refs: commits `c60eeb1` + `26c0822`
  (W1 foundation) + waves W5-W7 que consomem o schema.
- **6 cards novos** cobrindo 3 axes novos: `firebase-analytics`,
  `posthog-analytics` (axis analytics); `fcm`, `onesignal` (axis
  notifications); `firebase-remote-config`, `posthog-flags` (axis flags).
  Cada card com `card.yaml` + `detection/signals.yaml` + README +
  template stub. Refs: W4.1-W4.6.
- **Card sqldelight** — KMP-native persistence axis pra kmp platform.
  Pareia com `room-database` (android-only). Fecha gap W6 onde
  `firebase-full.yaml` referenciava card ainda inexistente.
- **4 starter bundles** em `presets/kmp-mobile/bundles/`:
  `firebase-full`, `rest-with-firebase-telemetry`, `local-only`, +
  sentinela `custom-from-scratch` (sem YAML — pula bundle, prompta cada
  axis). Substituem o bloco `backend-candidates:` monolítico.
- **Detection composer** — `engine/detection/composer.py` com
  `compose_backend_axes(project_root, active_cards) ->
  dict[axis][platform] -> Cell | Conflict | None`. Reusa
  `_eval_detection_signals` + `_eval_gradle_dep` de `engine/init.py`.
  Conflict.candidates ordenado determinísticamente por card_id. Refs:
  W5.1 + W5.2 + W5-fix.
- **AskUserQuestion-fronted init flow** (consumer da Phase A intent
  protocol):
  - `_handle_backend_multi_axis_brownfield` (`engine/init.py`):
    composer-driven, 3-caminhos confirm/adjust/scratch.
  - `_handle_backend_multi_axis_greenfield` (`engine/init.py`): bundle
    picker (4 opções) → opt override → per-axis prompts.
  - `_handle_backend_axes_submenu` (`engine/reconfigure.py`): tabela
    current 8 axes × N platforms, multiSelect cells, per-cell prompts
    (null/card/status/migrating-to) com validation enforçada.
- **Validator novo** — `validate_presets.py` cobre schema dos bundle
  YAMLs (axes válidos, platforms válidos, card references existentes).
  16 tests TDD. Refs: W6.3.
- **3 adapters em init.py** — `_composer_result_to_cells`,
  `_bundle_to_cells`, `_summarize_backend_cells` convertem handler
  returns pra workflow-config cell structure. Refs: W7.1+W7.2.

### Changed (Phase B — DET-6, 2026-06-11)

- **identity.category cleanup** — 9 cards migrados de `category: backend`
  ou `category: network` pros 8 axes canônicos. `firebase-auth` →
  `auth`; `auth-jwt-bearer` → `auth`; `firebase-storage` → `storage`;
  `firestore-persistence` → `data`; `firestore-realtime` → `data` (sub-
  axis "realtime" follow-up); `firestore-security-rules` → `data`
  (sub-axis "rules" follow-up); `rest-api-contract` → `data` (sub-axis
  "data-contract" follow-up); `retrofit-client` → `data`; `ktor-client`
  → `data`. CARD-004 enum em `engine/cards/loader.py` ampliado.
  Refs: W2.
- **Label refactor** — labels singulares `auth-provider`, `http-client`,
  `crash-reporting` removidos de `cards/*/card.yaml § provides`.
  Cardinalidade enforçada pelo cell shape (1 card per cell). Refs: W3.
- **Card rename** — `cards/crashlytics/` → `cards/firebase-crashlytics/`
  (paridade com `firebase-auth`, `firebase-analytics`, etc.). 25
  arquivos atualizados (incluindo 12 consumers cross-card via grep
  canary). YAML field name `crashlytics:` em contratos analytics
  mantém-se (concept independente).
- **`docs/schemas/card.md`** — CARD-004 enum revisado: `+ analytics`,
  `+ notifications`, `+ flags`; `- backend`, `- network` (granularidade
  backend-axes substitui o blob monolítico). Novo campo opcional
  `identity.platforms` + CARD-022 (platforms enum dentro do conjunto
  canônico; ID alocado pós-rebase contra `main` que já consumia
  CARD-020/021 pra DET-3). Adicionada seção "Backend axes — when
  identity.category is an axis" cross-referenciando `backend-axes.md`.
  Open-detail anchors preservados.
- **`docs/schemas/workflow-config.md`** — bloco `backend:` reescrito
  para shape multi-axis `backend.<axis>.<platform>` → cell|null.
  Removidos `identity.backend-choice` (legacy single-pick) e
  `backend.provider` string monolítico + sub-blocos provider-específicos.
  Slots RULE-010 e RULE-011 ficam reservados como audit-trail dos
  campos legacy + cross-ref pra RULE-019..024 (autoridade em
  `backend-axes.md`); sub-IDs alfanuméricos eliminados. Top-level
  table sincronizada.
- **CARD-022 renumber** — schema rule pra `identity.platforms` (W1)
  realocada de CARD-020 pra CARD-022 devido à colisão com DET-3
  (CARD-020/021 já alocados pra gradle-dep). Audit-trail em
  `docs/schemas/card.md`.

### Removed (Phase B — DET-6, 2026-06-11)

- `backend-candidates:` bloco completo em `presets/kmp-mobile/preset.yaml`
  (substituído por `bundles-dir` + `bundle-options` sentinela). Refs:
  W6.2.
- `identity.backend-choice` field em workflow-config.yaml. ConfiguratorCheckpoint
  `backend_choice` field idem. 15 referências removidas de
  `engine/init.py`. Refs: W7.4.
- `_build_backend` function legacy em `engine/init.py` (mapeava
  `backend_choice → backend.provider` enum). Substituída por adapters.
  Refs: W7.4.
- `_handle_backend` legacy em `engine/reconfigure.py` (handler antigo do
  submenu backend). Substituído por `_handle_backend_axes_submenu`.
  Refs: W7.3.
- Labels singulares `auth-provider`, `http-client`, `crash-reporting`
  de `provides`. Cardinalidade enforçada pelo schema. Refs: W3.

### Added (Phase B — DET-6 polish, 2026-06-12)

- **Test discipline gap fechado** — `tests/unit/test_validators_workflow_config.py`
  ganhou 8 tests positive/negative individuais cobrindo RULE-019..024
  (axis enum, platform check, card.card existence, status enum,
  migrating-to consistency, migrating-to card existence). Closes M-003
  do W7 cluster review.
- **Validator agora aceita local cards** — `validate_workflow_config.py`
  RULE-021 e RULE-024 reconhecem `.claude/cards/local/<name>/card.yaml`
  além do snapshot dir canônico. Alinha com behavior do reconfigure
  (Caminho B do M-001 W7 cluster review).
- **E2E coverage forge init/reconfigure** — 3 e2e tests novos
  (`test_e2e_brownfield_init.py`, `test_e2e_greenfield_init.py`,
  `test_e2e_reconfigure_backend.py`) substituem stubs pre-W7. Helpers
  compartilhados em `tests/e2e/conftest.py` (`_scaffold_minimal_project`,
  `_run_forge`, `_drive_intent_loop`). Cobertura AC-6/AC-7/AC-8 end-to-end
  no CLI level via subprocess + file-based intent protocol.
- **Consumed-intent log (Phase A protocol)** — `engine/ui/intent_state.py`
  ganhou `_log_path` + `_read_intent_log` + `_append_intent_log`.
  `read_response` agora checa log primeiro pra cached response do
  intent-id; faz handler re-entry idempotente entre subprocess
  invocations (resolve W7.2 multi-intent re-invocation pitfall).
  Schema documentado em `docs/schemas/intent-protocol.md §4`.

### Changed (Phase B — DET-6 polish, 2026-06-12)

- **`_SKIP_DIRS` semântica** — `engine/inventory/_walk_cache.py` +
  `engine/init.py` agora comparam `path.relative_to(project_root).parts`
  em vez de `path.parts` absoluto. Top-level `.claude/` continua
  filtrado em project_root; `.claude/` como PARENT do project_root
  (caso worktree) deixa de filtrar descendentes. Regression test em
  `tests/unit/test__walk_cache_worktree.py`.
- **`clear_intent_files` ganhou parâmetro `also_log`** — default `False`
  preserva log (re-entry idempotency). Caller terminal (engine/cli.py
  exit lifecycle) passa `also_log=True` para reset. SPEC §3 forensic
  preservation preservada via função separada `clear_intent_log_only`.
- **Microcopy stale removido** — `engine/init.py` gate RESOLVER-ERRORS
  label "voltar e escolher outro backend-candidate" → "voltar e ajustar
  a configuração de backend (composer/bundle)". Module docstring linhas
  1-15 atualizada pra refletir composer-driven flow (W7.4) em vez de
  legacy backend-candidate picker (Cena 6.5).
- **Test fixture categoria stale** — `tests/integration/test_e2e_local_card_pilot.py`
  linha 80 `category: "network"` → `category: "data"` (alinhamento tardio
  com DET-6 W2 migration de cards/network → cards/data).

### Fixed (Phase B — DET-6 polish, 2026-06-12)

- **W7 cluster review findings** — 1 High (stale microcopy) + 4 Medium
  (cross-validator asymmetry, type guard inconsistency, test discipline
  gap, module docstring stale) + 3 Low (comment stale, uniform-detection
  consolidation deferida, crashlytics filenames anotados). Detalhe em
  `.planning/det-6/W7-cluster-review-r1.md`.
- **`_SKIP_DIRS` worktree bug** — 2 tests que falhavam do worktree
  agora passam (`test_eval_gradle_dep::test_ac6_file_content_preserved`
  + `test_gradle_dep_card_activation::test_ac6_file_content_signal_still_active_alongside_gradle_dep`).
- **Phase A multi-intent re-invocation pitfall** — handlers que emit
  2+ intents agora sobrevivem subprocess re-invocations sem
  `IntentMismatchError`.
- **DET-6 W2 fixture cleanup tardio** — 2 tests
  (`test_pilot_local_card_added_appears_in_cascade`,
  `test_pilot_local_cards_manifest_written`) verdes pós-categoria fix.

### Changed (PR #13 review Wave B — 2026-06-12)

Refactors cross-module do review de PR #13 (DET-6 multi-axis backend).
Quebram ciclos de import, consolidam constantes duplicadas e
substituem duck-typing por isinstance dispatch:

- **Ciclo composer↔init quebrado** (review #3405252850 + #3405253600 +
  #3405256623) — `_eval_detection_signals` + helpers (`_glob_any`,
  `_eval_gradle_dep`, `_load_toml_catalog`, `_module_matches_coordinate`,
  `_scan_build_gradle_for_coordinate`, `_SKIP_DIRS`) movidos de
  `engine/init.py` para novo `engine/detection/_eval.py` (módulo neutro
  sem deps em init). Composer agora importa de `_eval` em vez de
  `engine.init` — os dois `# noqa: PLC0415` lazy imports em init.py
  removidos. `_normalize_cards_for_composer` mantido (refactor maior
  fora do escopo). 7 arquivos de test ajustados pra novos imports.
- **Shape guard no composer** (review #3405256439) — quando
  `card.detection.signals` não é list, composer agora pula o card com
  `logging.warning` em vez de silenciar via score=0 (que mascarava o
  card mal-formado no card_index).
- **`isinstance` em vez de `hasattr` pra Cell/Conflict** (review
  #3405253823) — 5 sites em init.py
  (`_detect_axis_uniformity`, `_render_axes_table` × 2,
  `_collect_confirm_selection`, `_composer_result_to_cells`) trocam
  duck-typing sobre `cell.candidates` por `isinstance(cell, Conflict)`
  / `isinstance(cell, Cell)`. Contrato explícito vinculado aos types
  importados do composer. Regression test paramétrico cobre os 5
  helpers com instâncias reais.
- **`BACKEND_AXES` shared** (review #3405254057) — tuple de 8 axes
  consolidado em `engine/detection/_axes.py`; init.py e reconfigure.py
  importam de lá. Antes, duas tuplas idênticas
  (`_BACKEND_AXES` em init, `_BACKEND_AXES_RECONFIGURE` em reconfigure)
  documentadas como "deliberate pra evitar ciclo" — ciclo nunca
  existiu, duplicação era defensiva por hábito.
- **`VALID_AXES` / `VALID_PLATFORMS` shared** (review #3405255016) —
  3 constantes consolidadas em `validators/_common.py`:
  `VALID_BACKEND_AXES`, `VALID_BUNDLE_PLATFORM_KEYS`,
  `VALID_PROJECT_PLATFORMS`. Os dois sets antes-homônimos de "platforms"
  agora têm nomes desambiguados (bundle slot keys × workflow active
  platforms — conteúdos semanticamente diferentes). Validators
  preservam aliases locais pra compat de tests/callers.

### Added (PR #13 review Wave B — 2026-06-12)

- **`engine/detection/_eval.py`** — módulo neutro pra signal evaluation.
- **`engine/detection/_axes.py`** — fonte canônica de `BACKEND_AXES`.
- **Cache `_log_cache` em `engine/ui/intent_state.py`** (review
  #3405256063) — process-level cache evita re-parse O(n) do JSONL em
  multi-intent handlers. `_append_intent_log` atualiza incrementalmente;
  `clear_intent_files(also_log=True)` + `clear_intent_log_only`
  invalidam pareado com delete on-disk. `_reset_log_cache` exposto como
  escape hatch pra testes.
- **`tests/unit/test_init_isinstance_cell_conflict.py`** — 9 regression
  tests cobrindo isinstance dispatch nos 5 sites afetados.
- **`tests/unit/test_intent_state_log_cache.py`** — 6 regression tests
  cobrindo cache hit, append incremental, invalidations, reset, mutation
  protection.

Rapid lane pós-Wave B: 1321 passed (+15 vs Wave A baseline 1306) / 11
skipped / 6 failures pré-existentes herdadas (cards_resolver_w3 × 4,
test_run_empty_args, test_no_cards_returns_pass_or_warn — não tocadas
nesta wave).

### Fixed (PR #13 review Wave A — 2026-06-12)

Remediação dos 7 fixes contidos do review de PR #13 (DET-6 multi-axis
backend). Single-file, baixo risco, sem cross-cutting:

- **`engine/cli.py` exit-cleanup refactor + observability** — substitui
  flag mutável `clear_log_on_exit` por sentinela `paused_exc:
  PausedForInputError | None` (review #3405256255); substitui bare
  `except Exception: pass` por logged best-effort no stderr (review
  #3405253379 + #3404131724). Mesma semântica, observabilidade ganhada.
- **`engine/ui/intent_state.py::_append_intent_log`** — adiciona
  `f.flush()` explícito após write pra honrar a docstring "JSONL append
  + flush is the durability contract" (review #3405254528). Regression
  test spies em `Path.open` confirma flush precede close.
- **`validators/validate_presets.py`** — unifica imports em
  `from validators._common`, remove o dual-branch `if __package__`
  hack (review #3405254868). Script mode + package mode ambos
  preservados via insert idempotente do project root em `sys.path`.
- **`validators/validate_workflow_config.py` RULE-020 cascade guard** —
  quando `platforms.active` está ausente/vazia/malformada, emite uma
  única mensagem de guidance em vez de cascatear 1 violação RULE-020
  por cell (review #3405255318). RULE-021..024 seguem rodando no
  mesmo pass. Regression test garante "platform desconhecida" não
  vaza no what-failed.
- **`docs/design/04-pending.md`** — anota gap RULE-023/024 ciclo
  `migrating-to` (review #3405255904) — detecção DFS 2-hop deferida
  pra hardening dedicated; feature menor, baixo impacto runtime.

### Changed (PR #13 review Wave A — 2026-06-12)

- **`tests/unit/test_ui_intent_state.py`** — +1 regression test
  (`test_append_intent_log_flushes_after_write`).
- **`tests/unit/test_validators_workflow_config.py`** — +1 regression
  test (`test_empty_platforms_active_emits_single_guidance_not_cascade`).

Fix 4 do review (delegação `clear_intent_log_only` →
`clear_intent_files(also_log=True)`) skipped: as semânticas divergem —
`clear_intent_log_only` preserva pending/response (SPEC §3 forensic),
`clear_intent_files(also_log=True)` apaga os três. Delegar mudaria
behavior do finally em `cli.py`. Anotado pra triage Wave B caso o
cleanup seja revisitado.

### Fixed (PR #11 master-review remediação — 2026-06-11)

Remediação completa dos 28 findings do master-review de PR #11
(`/tmp/master-review-pr-11-drift1-REVIEW.md`) em 10 commits sobre o
W6 doc-sync (`e992e01`). Cobertura: 3 Críticos + 7 Altos + 10 Médios +
5 Baixos + 3 Sugestões — todos endereçados em Wave 1 + Wave 2. Rapid
lane: 1199 passed / 11 skipped (sobe de 1151 → 1199 com +32 testes
novos cobrindo race-detection threading, schema-version mismatch,
EOFError no tty_bridge, dir fsync, chmod 0600, intent-id stability sob
mesmo prompt em comandos distintos, etc.).

Crítico:

- **#1** (`engine/cli.py main()`) — captura `RaceDetectedError`,
  `IntentMismatchError` e `JsonIOError` antes do exit 1. Mensagem
  mentor-calmo de `RaceDetectedError` agora chega ao usuário em vez de
  vazar como traceback (SPEC §3/§9). Commit `ad49c40`.
- **#2** (`engine/ui/question.py`) — `_stable_intent_id` agora inclui
  `command` + `command-args` no payload do hash. Dois `ask()`
  textualmente idênticos em comandos distintos não colidem mais. Combina
  com fix #11 (paths-detail) e #18 (confirm signature). Commit `2c49d0f`.
- **#3** (`bin/forge`) — implementa `FORGE_FORCE_TTY_MODE` (paridade com
  CHANGELOG/SPEC §7). Drift CHANGELOG↔impl fechado. Commit `cd6d616`.

Alto:

- **#4** (`engine/ui/intent_state.py`) — `read_response` valida
  `schema-version == 1` antes do intent-id check; nova exceção
  `SchemaVersionMismatchError` raise quando diverge. Future v2 deixa de
  consumir v1 silenciosamente. Commit `8eeff89`.
- **#5** (`engine/utils/checkpoint_io.py` + `engine/utils/iso.py` novos)
  — helper compartilhado consolida 30 funções (`_save_*_checkpoint`,
  `_load_*_checkpoint`, `_clear_*_checkpoint` × 10 module handlers) +
  10 cópias de `_utc_now_iso_<module>`. Shim de 1-linha por módulo
  preserva API pública dos tests; alvo de remoção registrado em
  FU-DRIFT-1-CHECKPOINT-CONSOLIDATE. Fecha Mandamento #3. Commit
  `916a062`.
- **#6** (`engine/ui/tty_bridge.py`) — `_prompt_user_via_stdin` captura
  `EOFError` (Ctrl+D, pipe quebrado) e roteia para mesmo path de cancel
  do `KeyboardInterrupt` (exit 130). Commit `6a00e1e`.
- **#7** (`engine/utils/json_io.py`) — `write_json` aplica
  `os.chmod(path, 0o600)` após `os.replace`. Pending/response files
  deixam de ser world-readable em sistemas POSIX multi-tenant. Commit
  `7d965c6`.
- **#8** (`engine/ui/question.py`) — `_stable_intent_id` promovida a
  `stable_intent_id` (símbolo público) com alias deprecated preservando
  os 13 callsites de produção sem breakage. Alvo de remoção em
  FU-DRIFT-1-DEPRECATE-INTENT-ID-ALIAS. Commit `916a062`.
- **#9** (concurrency coverage) — teste threading (5 workers via
  `threading.Barrier`) em `tests/integration/test_intent_state_concurrency.py`
  documenta TOCTOU window declarada no SPEC §9 e valida que pelo menos
  4 dos 5 saem com erro determinístico. Lock real via `fcntl.flock`
  registrado em FU-DRIFT-1-LOCK. Commit `626a4f0`.
- **#10** (`engine/utils/json_io.py`) — dir fsync POSIX após
  `os.replace` (open `path.parent` com `O_RDONLY` + `os.fsync`, skip em
  Windows). Atomic rename agora resiste a power-loss real. Commit
  `7d965c6`.

Médio:

- **#11** (`engine/ui/question.py`) — `paths-detail` entra no `extra`
  mapping do `_stable_intent_id` (ask_three_paths). Dois prompts com
  mesmo gate_name + labels mas motives diferentes não trocam mais
  responses. Commit `2c49d0f`.
- **#12** (`engine/ui/question.py`) — `_command_context()` normaliza
  fallback: quando `head` matches `r'.*\.py$'` ou `__main__`, retorna
  `("unknown", [])` em vez de "cli.py"/"__main__.py" como nome de
  comando. Commit `2c49d0f`.
- **#13** (`engine/ui/tty_bridge.py`) — `_build_response_value` para
  `kind=confirm` faz re-prompt loop (até 3 tentativas) em tokens
  inválidos antes de propagar erro. Usuário que digita "talvez"
  recebe orientação clara em vez de exit 1 críptico. Commit `6a00e1e`.
- **#14** (`engine/ui/tty_bridge.py`) — env var dead `FORGE_INTERNAL_TTY_BRIDGE`
  removida do subprocess env. Observability channel registrado em
  FU-DRIFT-1-OBS pra emergir quando log infrastructure aparecer. Commit
  `6a00e1e`.
- **#15** (SPEC + plan) — search-replace `CLAUDE_CODE_HOST` →
  `CLAUDECODE` em `docs/superpowers/specs/drift-1-intent-protocol.md`
  + `docs/superpowers/plans/drift-1-intent-protocol.md` com nota de
  rodapé "renomeado em W4-FU após verificação empírica vs Claude Code
  2.1.153". Commit `d999ced`.
- **#16** (`docs/schemas/intent-protocol.md`) — nova seção
  `## Schema evolution policy` explicita (a) bump em breaking; (b)
  reader rejeita versões desconhecidas; (c) engine + host co-bumpam;
  (d) sem v0. Commit `d999ced`.
- **#17** (`engine/ui/intent_state.py`) — `_parse_created_at` /
  `detect_race` toleram clock skew até 60s. Negative `age_seconds` >
  60s (clock inválido) trata como stale → sweep; <=60s trata como
  recém-criado. Commit `8eeff89`.
- **#18** (SPEC + question.py) — exemplo de `confirm` no SPEC §2.1
  passa a `allow-pause: true` alinhando com impl real;
  `tests/unit/test_ui_question_api_signatures.py` ganha regression test
  travando a signature pra evitar drift futuro. Commits `d999ced` +
  `2c49d0f`.
- **#19** (concurrency test) — implementado em commit `626a4f0` (ver
  finding #9 acima). Cobre o gap declarado no SPEC §9.
- **#20** (`docs/design/06-command-surface.md`) — seção Exit codes ganha
  nota explícita distinguindo as 2 rotas pra 130: (a) `KeyboardInterrupt`
  em TTY mode; (b) host response `cancelled: true` em intent mode.
  Caller pode tratar identicamente. Commit `d999ced`.

Baixo:

- **#21** — `_utc_now_iso_*` consolidado em `engine.utils.iso.utc_now_iso`
  (10 cópias → 1 helper canônico). Commit `916a062`. Nota: `engine/verify.py`
  mantém `_utc_now_iso` local com microseconds (semantically distinto
  do shared helper que trunca pra seconds) — migração registrada em
  FU-DRIFT-1-VERIFY-ISO.
- **#22** (`engine/ui/intent_state.py`) — `RaceDetectedError` ganha
  bloco 3-caminhos canônico (Mandamento #5 + Discipline §1): (a)
  aguarda outro processo; (b) `rm .claude/state/forge-pending.json` se
  sessão anterior travou; (c) `forge undo` se conflito de feature
  paralela. Combina com fix #1 (mensagem agora chega ao usuário).
  Commit `8eeff89`.
- **#23** (`engine/ui/question.py`) — stub `_read_line` que raise
  `NotImplementedError` removido. Substituído por comentário apontando
  pra `engine.ui.tty_bridge` como home canônica de stdin reading.
  Commit `2c49d0f`.
- **#24** (`tests/integration/test_intent_protocol_e2e.py`) —
  `test_race_detection_rejects_stale_concurrent` usa stale_id literal
  determinístico (`"deadbeef-0000-0000-0000-000000000000"`) em vez de
  `uuid.uuid4()`. Assertion adicional confirma que difere do engine
  determinístico. Commit `626a4f0`.
- **#25** (`tests/e2e/test_tty_bridge_e2e.py`) —
  `pytest.skip(allow_module_level=True)` no topo quando
  `sys.platform == "win32"`. Evita silently-passing-zero-assertions em
  Windows CI. Commit `626a4f0`.

Sugestão:

- **#26** (`engine/ui/intent_state.py`) — `detect_race` catch genérico
  trocado por `(JsonIOError, OSError)` específicos. Programming errors
  propagam em vez de ficar escondidos. Commit `8eeff89`.
- **#27** (`engine/ui/exit_codes.py` novo) — consolida constantes
  `EXIT_OK=0`, `EXIT_ERROR=1`, `EXIT_PAUSED=2`, `EXIT_CANCELLED=130`
  importadas por `engine/cli.py` e `engine/ui/tty_bridge.py`. Evita
  drift de duplicação local. Commit `3071fe9`.
- **#28** (`bin/forge`) — `FORGE_VERSION` dinâmico via
  `engine.__version__` (custo +20-50ms cold start aceito). Drift do
  hardcoded "1.0.0" fechado. Commit `cd6d616`.

Follow-up pós-master-review (2026-06-11):

- `engine/init.py`: `_load_checkpoint` agora valida `isinstance(data, dict)` e retorna `None` em YAML corrompido. Master-review threads #3396896063 + #3396903793 (`[Critico]`). Alinha com pattern dos 9 outros checkpoint-loaders. (commit `6dd40af`)

### Changed (PR #11 master-review remediação)

- State files (`.claude/state/forge-pending.json`,
  `.claude/state/forge-response.json`) escritos com mode `0o600` por
  default via `engine/utils/json_io.py::write_json`. Hardening de
  permissões aplicado em sistemas POSIX (Windows ignora silenciosamente).
- `engine.ui.question.stable_intent_id` agora é símbolo público; alias
  deprecated `_stable_intent_id = stable_intent_id` preservado pra
  compat dos 13 production callsites + 4 test modules. Remoção
  registrada em FU-DRIFT-1-DEPRECATE-INTENT-ID-ALIAS, target v1.3.


### Added (Phase A — DRIFT-1 intent protocol close, 2026-06-10)

Fechamento da Phase A em 6 commits W3-W6 sobre a base W2 (range total
`1b1d289..50203f3`, 21 commits). Engine deixa de ler stdin diretamente;
intent JSON emitido em `.claude/state/forge-pending.json`, response
consumida de `.claude/state/forge-response.json`, exit code 2 sinaliza
pausa pro host (Claude Code OR `tty_bridge` em fallback). AC-1..AC-9
verificados em integration + e2e pty.

- `engine/ui/tty_bridge.py` (W3.T1) — loop subprocess pra fallback TTY
  fora de contexto Claude Code. Lê pending, prompta no stdin com
  helpers per `kind`, escreve response via `intent_state.write_response`
  e re-invoca o subcomando até exit 0/1/130. Estende
  `engine/ui/intent_state.py` com `read_pending` + `write_response`.
- `bin/forge` dispatcher (W4.T1+W4-FU) — detecta TTY via `[[ -t 0 ]]`
  e contexto Claude Code via env var `CLAUDECODE` (verificado
  empiricamente vs Claude Code 2.1.153). Roteia entre intent mode
  (host loop) e tty_bridge fallback; overrides `FORGE_FORCE_INTENT_MODE`
  / `FORGE_FORCE_TTY_MODE` pra teste. Hooks audit (W4.T2) não exigiu
  patches — invocações existentes continuam funcionando.
- 15 integration tests
  (`tests/integration/test_intent_protocol_e2e.py`,
  `tests/integration/test_callsites_smoke.py`) + 3 e2e pty tests
  (`tests/e2e/test_tty_bridge_e2e.py`) cobrindo AC-1..AC-9 (W5.T1+T3+T4
  + W5.T2). Integration lane: 119 collected. E2E lane: 17 collected.
- Exit code 2 (paused-for-input) documentado em
  `docs/design/06-command-surface.md` (seção `## Exit codes` nova) —
  ladder completa 0/1/2/130 vinculada ao SPEC §4.

### Changed (Phase A — DRIFT-1 close)

- `docs/design/06-command-surface.md` ganha seção `## Exit codes`
  formalizando o contrato 0/1/2/130. Load-bearing edit justificado por
  Mandamento #6 (doc-sync): exit code contract mudou (adicionado 2).
- `.claude/rules/subagent-workflow.md` ganha subseção
  `## Quando subagent invoca \`forge\`` esclarecendo que exit 2 é
  contrato (não erro) e responsabilidade do orquestrador, não do
  subagente sozinho. Load-bearing edit justificado por Mandamento #6
  — protocolo afeta workflow de dispatch.
- README + handoff atualizados pra refletir 21 commits de Phase A na
  branch `feat/drift-1-intent-protocol`. Test count: rapid lane 1151
  passed / 11 skipped preservada (1162 collected pós-W5);
  integration 119; e2e 17; total 1298.

### Added (Phase A W2 — DRIFT-1 intent protocol chokepoint refactor, 2026-06-10)

Phase A W2 entrega o refactor do chokepoint (`engine/ui/question.py`) + integração de checkpoint em todos os 10 subcommands. 15 commits acumulados sobre o foundation W1 (commit `1b1d289`). Outcome C "init-pattern" locked em W2.T0: per-subcommand dataclass + 3 helpers + handler wiring; sem promoção a shared module enquanto pattern não se repetir 3+x.

- Três sentinels exportadas de `engine/ui/question.py`: `PausedForInputError` (intent emitido, host deve sair com exit 2), `UserCancelledError` (response com `cancelled: true` mapeia exit 130 + Ctrl+C path) e `UserPausedError` (alias direcional pra futuro tty_bridge). `PromptAbortedError` legado preservado como re-export pra back-compat.
- 10 per-subcommand checkpoint dataclasses, cada uma com 3 helpers (`_save_*`, `_load_*`, `_clear_*`) + `_*_checkpoint_path` resolver: `_InitCheckpoint`, `_PlanCheckpoint`, `_ImplementCheckpoint`, `_VerifyCheckpoint`, `_ReconfigureCheckpoint`, `_EvolveCheckpoint`, `_UndoCheckpoint`, `_MemoryCliCheckpoint`, `_GraphCliCheckpoint`, `_DoctorCheckpoint`. Cobertura per checkpoint-audit.json: 8 add-new + 2 extend (init e evolve já tinham checkpoints próprios; ganharam campo `intent_id` aditivo).
- 10 novos arquivos de teste em `tests/unit/test_engine_*_resume.py` cobrindo save → exit 2 → re-invoke → consume → resume. Rapid lane: 1046 → 1114 passed (+68 tests; 11 skipped agregam migrações legadas do stdin).
- Campo `paths-detail` no payload de `ask_three_paths` intent — host renderiza o bloco 3-caminhos completo (motive de cada caminho preservado na serialização). Fecha REVIEW CR-003.
- Schema canônico `docs/schemas/intent-protocol.md` atualizado em W2.T1+T2 (paths-detail, hash de validator_hint, contextvar argv).
- `.planning/drift-1/checkpoint-audit.json` (W2.T3a artifact) — classifica os 10 módulos antes da integração + serve de referência pros commits T3b PART A/B/C.

### Changed (Phase A W2 — chokepoint refactor)

- `engine/ui/question.py` migrado de stdin reader pra intent emitter. As 5 funções públicas (`ask`, `ask_three_paths`, `ask_yes_no`, `ask_text`, `ask_number`) preservam API surface bit-a-bit; internamente emitem intent via `intent_state` + `json_io` e levantam sentinel apropriada em vez de bloquear leitura. Hosts não-Claude-Code chamando essas funções recebem exceção em vez de prompt — comportamento documentado no SPEC §1.
- `engine/cli.py::main()` ganhou ramos exit 2 (Paused*) + exit 130 (UserCancelledError) antes do `except KeyboardInterrupt`. Ladder de exit codes documentada em SPEC §4. Argv capturado via contextvar pra re-invocação determinística pelo host.
- `engine/init.py` e `engine/evolve.py` — checkpoints existentes estendidos com campo `intent_id` aditivo (sem quebrar payloads em disco de sessões pré-W2; `intent_id=None` é fallback aceito).
- Forensic preservation honrado: invalid responses (schema fail / value fora de options) NÃO chamam `_clear_state()` antes do raise — state files permanecem em disco como pista pro host (SPEC §3 + REVIEW CR-002 fix).
- SPEC `docs/superpowers/specs/drift-1-intent-protocol.md` §2.1, §4, §5 (tabela final 10/10), §8 e AC-5 atualizados inline ao longo dos 15 commits — fonte de verdade do contrato.

### Added (DET-3 gradle-dep signal type, 2026-06-10)

- Signal type `gradle-dep` em `engine/init.py:_eval_detection_signals` — abstrai presença de coordenada Maven em catálogo `gradle/*.versions.toml` (TOML moderno, formato `module = "<group>:<artifact>"` e `group + name` split) OU em `**/build.gradle*` (legado). Card declara `type: gradle-dep` + `coordinate: <group>:<artifact>`; engine resolve onde procurar. Resolve DET-3 do pilot v1.2-dev 2026-06-10 (scanner cego pra libs.versions.toml). Helper privado `_eval_gradle_dep(project_root, coordinate)` ao lado de `_glob_any`, com curto-circuito no primeiro match e try/except silencioso pra TOML mal-formado. Plan: `docs/superpowers/plans/det-3-gradle-dep-signal.md`.
- Regra de validação CARD-020 em `engine/cards/loader.py` — `detection.signals[*].coordinate` (quando `type=gradle-dep`) deve ser `<group>:<artifact>`, sem versão sufixada, sem espaços. (ID alocado como CARD-020 porque CARD-019 já é usado por `legacy-marker`; SPEC §AC-8 autorizou "CARD-019 ou next free".)

### Changed

- 9 signals em 8 cards canônicos migrados de `file-content` em `**/build.gradle*` pra `gradle-dep` (mesma coordenada, semântica mais ampla cobrindo catálogos modernos): crashlytics, firebase-auth (base + ktx), firebase-storage, firestore-persistence, firestore-realtime, koin-annotations, kotlinx-serialization-json, ktor-client (variante ktor-client-core). Confidence preservada em cada signal — CARD-016 sanity intacta. Audit determinístico em `.planning/det-3/migration-audit.json`.
- Signals em `**/*.kt`, `**/Podfile*`, `**/Package.swift`, e prefixos de família (`androidx.compose`, `androidx.datastore`, `androidx.room`, `navigation3`, `kotlinx-serialization` sem `-json`, `io.ktor:ktor-client` sem suffix, plugin DSL `kotlin("multiplatform")`) preservados como `file-content` per SPEC §Migration policy. Backward compat de `file-content` integralmente mantida.
- `docs/schemas/card.md` §"Signal types" lista `gradle-dep` com schema completo; nota explícita sobre o vapor `dependency` (declared no schema mas nunca implementado no avaliador) — cleanup separado tracked em `04-pending.md`.
- Apresentação (`docs/presentation/feature-forge.html`) atualizada para v1.2-dev: 22 → 24 slides — adicionados slides de subtypes/bugfix e forge qa, slide verify enriquecido com os gates fortes (CC + secrets + no-behavior-change), status e roadmap reescritos (todas as fases shipadas, timeline v1.0→v1.2→autopilot). DESIGN.md sincronizado.

### Documentation

- v1.2-dev pilot 2026-06-10 capturado em `docs/design/04-pending.md` — 6 findings (DRIFT-1 conceitual primário, B1, B2, DET-3, DET-5, DET-6) + sequenciamento Phase 0 → Phase A (DRIFT-1) → Phase B (DET-6) decidido com user. UX/microcopy/persona findings do modo fallback CLI deferred até Phase A (engine emite intent estruturado pra Claude Code → strings deixam de ser responsabilidade do Python).
- DET-3 (Phase 0) marcado ✅ resolvido em `04-pending.md`. Follow-ups não-bloqueantes registrados na mesma página: (1) cleanup do vapor `dependency`, (2) `signals.yaml` schema-version bump nos cards migrados.

### Changed (load-bearing)

- Revisita decisão 30: sandbox isolation guard via sitecustomize.py (não PYTHONSTARTUP) — texto da Decisão atualizado pra refletir mecanismo real implementado em engine/qa/sandbox.py. Comportamento de isolamento idêntico; só o mecanismo nomeado mudou.

### Fixed

- Tighten CARD-020 whitespace validation to reject tab/newline in gradle-dep coordinate (M-001 from DET-3 code review; commit 475f695).

### Fixed (PR #11 master-review remediação — DET-3, 2026-06-10)

Wave 1+2 cobrindo 9 findings do master-review do PR #11 sobre o signal type `gradle-dep` (DET-3 / Phase 0). Severities variam de Alto (2) a Baixo (4); todos endereçados em 7 commits atômicos antes do merge.

- **A-1 [alto] — ktor-client primary signal migrado** — `cards/ktor-client/{card.yaml,detection/signals.yaml}`: signal primário (confidence 0.5) migrou de `file-content` substring família (`io.ktor:ktor-client`) para `gradle-dep` exato `io.ktor:ktor-client-core`. SPEC §AC-1 ("fixture TOML-only → ktor-client retorna auto-activate") agora é exercido na realidade do card, não apenas pelo helper isolado. Commit `7847e5a`.
- **A-2 [alto] — integration test cobre cards reais** — `tests/integration/test_gradle_dep_card_activation.py` (novo): carrega `cards/ktor-client/card.yaml` real e roda detection contra as 5 fixtures (`gradle-dep-{toml-only,toml-split,legacy,hybrid,negative}`), assertando score vs threshold. Sem este teste, A-1 cria falsa segurança permanente. Commit `a7d0947`.
- **M-2 [médio] — CARD-021 rejeita `type: dependency`** — `engine/cards/loader.py` ganha CARD-021 que rejeita o tipo descontinuado no load time, em vez de silenciosamente ignorá-lo. Tabela canônica de Signal types em `docs/schemas/card.md` purga `dependency` da listagem ativa e move para sub-seção "Tipos descontinuados" com referência ao sucessor (`gradle-dep`). Commit `3e4cc65`.
- **M-3 [médio] — branch defensivo morto removido** — `engine/init.py`: removido `if tomllib is not None:` que contradizia o invariante `requires-python >=3.11` (tomllib é stdlib desde 3.11). Captura FU-4 (cosmética post-review). Commits `2e13e3a` + `680a59b`.
- **M-4 [médio] — `forge doctor` warn pra catálogo fora de `gradle/`** — `engine/doctor.py` ganha check que avisa quando `**/libs.versions.toml` existe fora de `<root>/gradle/` (composite builds, `buildSrc/`). Scope preservado conforme SPEC §Non-Goals; warning ajuda diagnóstico sem expandir scanner. Commit `b2749dc`.
- **M-5 [médio] — comments filtrados em build.gradle** — `engine/init.py`: substring match no fallback build.gradle agora strippa comments Groovy/KTS (`//` line-comments + `/* */` block-comments) antes do match. Falso-positivo `// io.ktor:ktor-client-core retirado em 2024` não retorna mais True. Commit `680a59b`.
- **B-1 [baixo] — `_load_toml_catalog` cached** — `engine/init.py`: helper de parse decorado com `@functools.lru_cache(maxsize=None)` evita re-parse do mesmo `libs.versions.toml` quando N signals do mesmo card consultam. Cache key por `project_root` resolvido. Commit `680a59b`.
- **B-2 [baixo] — TOML `module` com version-suffix** — `engine/init.py`: match tolera `module = "group:artifact:version"` no TOML batendo coordinate `group:artifact` (formato inválido mas observado no wild). Match exato preservado para shape canônico; prefix-aware só para o caso version-suffix. Commit `680a59b`.
- **B-3 [baixo] — helper `parse_gradle_coordinate` extraído** — `engine/cards/_signal_shapes.py` (novo): `parse_gradle_coordinate(coord) -> tuple[group, artifact] | None` consolidado e reusado por CARD-020 (loader) + `_eval_gradle_dep` (init). Elimina drift de validação cross-módulo e prepara reuso pra futuros `pod-dep` / `npm-dep` / `swift-dep`. Commit `4a6a42d`.

### Added (PR #11 master-review — DET-3 edge case coverage, 2026-06-10)

- **S-1 cobertura de testes** — `tests/unit/test_eval_gradle_dep.py` ganha 5 edge cases: (1) BOM UTF-8 no `libs.versions.toml` silenciosamente pulado (tomllib stdlib rejeita BOM por aderir à TOML 1.0; helper engole `TOMLDecodeError` → catálogo invisível — comportamento documentado, surfaced como FU-MR-3); (2) block-table form (`[libraries.ktor-client-core]`) com chaves `module`/`group+name` split; (3) build.gradle com coordenada misturada em comentários + linha real (cobre M-5 fix); (4) variant `-ktx` em TOML-only com coordenada base — confirma assimetria documentada (FU-MR-1 trade-off); (5) catálogo customizado em path não-canônico (`dependencies.toml` fora de `gradle/`) — exercita SPEC §Non-Goals. Commit `e6305df`.

### Changed (PR #11 master-review — DET-3 assimetria documentada, 2026-06-10)

- **M-1 [médio] — Assimetria TOML-exact vs build.gradle-substring documentada** — Decisão deliberada do master-review (Caminho A): o signal `gradle-dep` faz match EXATO `group:artifact` no passo TOML (`libs.versions.toml`) e SUBSTRING no passo build.gradle (`**/build.gradle*`). Consequência observável: cards declarando coordenada base (ex.: `com.google.firebase:firebase-storage`) NÃO detectam variantes sufixadas (ex.: `-ktx`) em projetos TOML-only puros — variante seria invisível por igualdade exata. Cards devem declarar coordenadas explícitas pra cada variante quando relevante. Documentado em `docs/schemas/card.md` §Signal types nova nota de assimetria; follow-up FU-MR-1 captura trigger pro schema-version bump quando demanda do oposto (`match: prefix` opcional) emergir. Commit `c1db782`.

### Fixed (QA-11 ultra-review remediação — PR #9, 2026-06-09)

Remediação de 16 findings do ultra-review (deep.json) sobre QA-11 sandbox env hardening + QA-13. Severities variam de critical (1) a suggestion (7); todas aplicadas exceto onde indicado.

- **deep-001 [crítico]** — `engine/qa/sandbox.py::_hardened_env` não herda mais `PYTHONPATH` do parent process. A versão anterior concatenava `os.environ['PYTHONPATH']` ao `guard_dir`, permitindo que um parent hostil ou shell poluído injetasse paths de import no subprocess do sandbox. PYTHONPATH é vetor de code-execution; defense-in-depth exige drop incondicional. Callers que precisem de paths extras declaram via `extras` (que passa pelo grant flow). Test de regressão `test_hardened_env_drops_parent_pythonpath` falharia antes do fix.
- **deep-002** — `SENSITIVE_PATTERN` reescrita com boundary semantics (`(?:^|[_-])TOKEN|...(?:$|[_-])`) — elimina false-positive em `AUTHOR`, `CO_AUTHOR`, `BASE_PATHTOKEN_NAME` sem perder cobertura canônica. `AUTHORIZATION` e `AUTH(?=$|[_-])` cobertos explicitamente; `is_sensitive` passou de `.match` a `.search`.
- **deep-003** — `build_safe_env` ganha `allow_sensitive=False` default. Raise `ValueError` se `extras` contém var sensitive sem `allow_sensitive=True`. `_hardened_env` (pós-grant) passa True; callers com extras non-sensitive hardcoded (engine.verify com JAVA_HOME/ANDROID_HOME/GRADLE_USER_HOME) mantêm default seguro.
- **deep-004** — `_prompt_sensitive_grant` re-prompta até 3x antes de declarar abort e captura `EOFError` com mensagem explícita ('stdin fechado — abortando grant'). Anteriormente, qualquer input não-reconhecido (typo, '4', EOF em CI sem TTY) cancelava forge init/reconfigure silenciosamente.
- **deep-005** — `_alert_sensitive_drops` mascara nomes de vars sensitive no stderr (formato `AW********`). Em CI com log verboso, expor nomes completos como `STRIPE_LIVE_KEY` ou `OAUTH_INTERNAL_VAULT_TOKEN` era information disclosure (atacante aprende namespace de secrets do host).
- **deep-006** — `_compute_allowed_extras` ganha isinstance guard antes de `set(raw_grants)`. Shape malformado (dict, string, int) virava semantic drift silencioso: `set('GITHUB_TOKEN')` resultava em `{'G','I','T','H','U','B','_',...}` — cada char virava 'grant'. Guard duplicado consciente do já presente em `grant.py._load_existing_grants`; TODO de reuse anotado pra PR separado (extrair pra `engine/qa/_grants.py`, Mandamento #3).
- **deep-007** — magic number `0.05` em `run_sandbox` promovido a constante module-level `_MIN_REMAINING_S_FOR_SPAWN` com comentário explicando spawn overhead floor + nota de tunabilidade pra platform mais lenta.
- **deep-008** — `is_sensitive` aceita `object` e retorna `False` para non-str (fail-open) em vez de `TypeError`. Defensivo contra chamadores que esquecem `isinstance` upstream.
- **deep-009** — `evaluate_sensitive_grants` short-circuita o loop de `denied_cards` quando `denied_vars` está vazio (caminho comum em re-run sem novos prompts).
- **deep-013** — `test_core_allowlist_is_frozen` reescrito como `test_core_allowlist_is_immutable_and_contains_essentials`, asserindo a invariante de segurança real (essentials presentes, secrets ausentes) em vez da manifestação 'add raise AttributeError'.
- **deep-015** — emoji warning padronizado para `⚠` plain (sem variation selector U+FE0F) em `engine/cards/grant.py` para render consistente cross-terminal.
- **deep-016** — `extras` materializado em tupla na entrada de `build_safe_env` e `inspect_dropped` para re-iteração segura contra generators.
- **deep-017** — `_prompt_sensitive_grant` ganha `prompt_fn=input` como DI seam — tests injetam callable em vez de monkeypatch global.
- **deep-018** — `SENSITIVE_PATTERN: re.Pattern` → `re.Pattern[str]`.
- **deep-019** — `var_to_cards` em `evaluate_sensitive_grants` usa set internamente, dedup quando um mesmo card declara a mesma var duas vezes por yaml duplication user-error.
- **deep-020** — `_write_chdir_guard` aplica `chmod 0700` ao guard dir e `0600` ao `sitecustomize.py` em best-effort (Windows ignora). Em multi-tenant POSIX evita TOCTOU window entre write e subprocess spawn.
- **deep-022** — `_maybe_alert_sensitive_drops` captura `RuntimeError` adicional. `validate_qa_extensions` pode raise `RuntimeError` em catalog corrompido — sem este catch o alert layer quebrava o contrato 'NUNCA bloqueia QA run' documentado no docstring.

### Deferred (QA-11 ultra-review — fora do PR #9)

Endereçados em PRs separados por requererem refactor cross-cutting fora da whitelist do fix-loop atual:

- **deep-010** — structured warning channel (`engine/_warn.py emit_warn`) substituindo `print(..., file=sys.stderr)` em scope/qa-init/grant. Requer novo módulo e refactor cross-cutting de 3 call-sites.
- **deep-011** — normalização de `state` legacy ('aborted_by_user' → 'aborted') em `engine/qa/scope.py::_is_terminal_state`. Não está na whitelist atual.
- **deep-012** — memoização opcional de `_is_terminal_state` em `engine/qa/scope.py` para paranoid scope com muitos features. Trade-off de complexidade vs benefício; aceitar O(features) por enquanto.
- **deep-014** — plumbing de `_compute_allowed_extras` pra `engine/verify.py` substituindo o tuple hardcoded `(JAVA_HOME, ANDROID_HOME, GRADLE_USER_HOME)`. Requer propagar `workflow_config` por `_run_cascade` → `_invoke_validator` (cross-cutting). Defesa atual continua funcionando (extras hardcoded são non-sensitive).
- **deep-021** — warning em `engine/cards/loader.py` quando `env_needs[idx]` não é string. Loader não está na whitelist atual.

### Tests (QA-11 ultra-review, 2026-06-09)

- **1097 → 1113 passed** (+16 tests). Cobertura: test de regressão pra `PYTHONPATH` leak (deep-001); 9 unit tests novos pra pattern boundary semantics (deep-002 positivos + negativos); 3 tests pra defense-in-depth do `build_safe_env` (deep-003); test fail-open de `is_sensitive` para non-str (deep-008); 4 tests pra alert layer (deep-005 mask + deep-006 isinstance guard + deep-022 runtime catch); 3 tests pra grant prompt EOF + re-prompt + abort após 3 typos (deep-004); dedup de cards em var_to_cards (deep-019).

### Added (PR #8 forge qa CONF gaps + pause/resume, 2026-06-08)

- `forge qa` Phase 0 inicializa `<run>/qa-report.json` com `verdict=pending` + finaliza após Phase 5 com verdict/findings/totals + completed_at (CONF-001).
- `forge qa` Phase 0 faz snapshot dos artefatos resolvidos via hardlink (fallback copy) em `<run>/snapshot/` — preserva reprodutibilidade se user editar mid-run (CONF-002).
- `forge qa` deriva findings determinísticos de SandboxResults problemáticos via `findings_from_sandbox_results` — `sandbox-breach` (critical, always BLOCK) e `timeout` (medium) não dependem mais do LLM synthesizer pra emitir (CONF-003).
- `forge qa` pause/resume implementado via `<run>/checkpoint.json` (Decisão 27 + SDD §16 edge 6 + Gap QA-12 fechado). SIGINT salva checkpoint atomicamente; nova invocação detecta e retoma sem criar novo `run_id`. Auto-resume; corrupt checkpoint cai em 3-caminhos mentor calmo (CONF-004).
- Novo módulo `engine/qa/checkpoint.py` (`Checkpoint` dataclass, `CheckpointCorruptError`, `write_checkpoint`/`read_checkpoint`/`find_resumable_run`).
- Novo módulo `engine/qa/_common.py` (helper `utc_iso_z()` consolidado entre `__init__.py` e `checkpoint.py`).
- Novo helper `sanitize_scope_target` em `engine/qa/ingest.py` (single source of truth pra regex de path sanitization).
- `agents/qa-conductor.md` ensina conductor LLM a serializar SandboxResults em `<run>/sandbox-results.json` após Phase 3 (sem isso, CONF-003 fica dormente em produção — synthesis lê esse arquivo pra derivar findings determinísticos).

### Changed (PR #8 forge qa CONF gaps + pause/resume, 2026-06-08)

- E2E `tests/e2e/test_qa_cli_smoke.py` valida estrutura on-disk de `qa-report.json` (schema_version, run.id, run.scope, verdict ∈ {pending, PASS, FLAG, BLOCK}); disabled-path assert `qa-report.json` NÃO existe (CONF-007).
- `engine/qa/synthesis.py` `dedup_findings` alinhado com `agents/qa-synthesizer.md`: duplicates vão em `evidence.duplicates` (lista de auditor names) — `evidence_extras` removido (spec alignment).
- `engine/utils/sha256.py` promove `_normalise_description` → `normalise_description` (public API + `__all__`); alias deprecated mantido pra backward-compat.
- `engine/qa/reconfigure` `_qa_list_disable_auditors` substitui (não une) a lista de desativados — user pode re-ativar auditor já desabilitado omitindo da seleção.
- `engine/qa/sandbox.py` `_validate_paths_inside_sandbox` usa `Path.relative_to()` (robusto contra symlinks/mount points vs comparação string+os.sep anterior). Subprocess paths são `.resolve()`'d antes de `subprocess.run` pra evitar resolução relativa ao cwd do sandbox.

### Fixed (PR #8 forge qa fixes da review wave 1, 2026-06-08)

- `engine/qa/run_id.py` raise `ValueError` explícito se naive datetime é passado (antes: silenciosamente interpretado como local time pelo `astimezone`, gerando `run_id` offset incorreto).
- `engine/qa/scope.py` `_list_features_for_paranoid` filtra dirs hidden (`.DS_Store`, `.git`); `_find_screen`/`_find_task` ordenam `iterdir()` pra determinismo cross-machine.
- `engine/qa/ingest.py` `parse_qa_config` wrap `float()/int()` casts em warnings mentor-calmo + default fallback (antes: `ValueError` propagava raw traceback ao user). Sanitiza `scope.target` via whitelist `[A-Za-z0-9._-]` (preveniu path traversal).
- `engine/qa/__init__.py` `json.loads` dos findings em try/except (degradação graciosa por arquivo malformado).
- `engine/qa/emit.py` dedup por fingerprint antes de append em `proposed.yaml`; `yaml.safe_load` em try/except (OSError, YAMLError); read+merge preserva metadata pre-existente.
- `validators/validate_qa_finding.py` regex `_ID_RE` aceita uppercase (ISO 8601 T/Z); `sandbox_result=null` aceito em drafts (template default).
- `engine/reconfigure.py` `_qa_adjust_budgets` usa `float()` (preserva sub-second); rejeita valores ≤0 com mensagem mentor-calma.
- `tests/engine/qa/test_synthesis.py` `pytest.raises((AttributeError, dataclasses.FrozenInstanceError))` (antes `Exception` vacuous).

### Tests (PR #8, 2026-06-08)

- **847 → 933 passed** (+86 tests). Cobertura: 20 fixes da review wave 1, 4 CONF gaps (001/002/003/007), CONF-004 pause/resume + 4 fixes do review CONF-004, helper `utc_iso_z` em `engine/qa/_common.py`.

### Changed (PR #7 review fixes — 2026-06-08)

- **`validators/_common.py`** — `gate_threshold_lookup` aceita kwargs
  `card_override_key` / `workflow_block_key` / `defaults`;
  `format_three_paths_message` aceita kwargs `gate_title` / `why_lines` /
  `override_example` / `format_annotation`. Defaults preservam CC gate
  byte-a-byte; outros gates numéricos (Cognitive Complexity, Function
  Length) reusam direto. Fecha Gap GATE-INFRA-1 (4 PR threads, A1/A2).
- **`validators/_gate_infra.py`** — quatro robustness fixes:
  (B1) `render_config_with_placeholders` ordena placeholders por len
  desc antes de replace (evita prefix-collision); (B2) write/close em
  try/except com unlink + re-raise (sem leak de tempfile em disk-full);
  (B3) `apply_overrides` valida `override_key_fields` contra named
  groups do `key_pattern` up-front (ValueError em vez de KeyError
  tardio); (B4) `parse_overrides` adiciona `KeyError` à tupla de
  exceções do value_converter (match the docstring promise).
- **`validators/check_cyclomatic_complexity.py`** — drop dead re-exports
  `check_tool_available` / `render_config_with_placeholders` (C2).
  Tests migraram pra importar direto de `_gate_infra`.
- **`validators/_diff.py`** — (D1) `read_commit_body` resolve gitdir via
  `git rev-parse --git-dir` + fallback parse manual de `.git` file,
  suportando worktrees (`.git` é arquivo, não diretório). Antes
  silently caía pro `git log` fallback (commit prévio em pre-commit
  context). (E1) `DiffHunk.kind` promovido pra
  `Literal["add", "del", "ctx"]` (alias `HunkKind`) — sem behavior
  change em runtime.
- **`docs/design/04-pending.md`** — Gap GATE-INFRA-1 marcado como
  resolvido; novo Gap GATE-INFRA-2 (N+1 subprocess em
  `extract_diff_hunks`) registrado como deferred YAGNI até 2º consumer
  de hunks aparecer.

10 testes novos cobrindo as 4 áreas: `test_common_cc_helpers.py` (+8),
`test_gate_infra_robustness.py` (+6), `test_diff_worktree.py` (+3).
Suite total continua verde (819 passed + 19 skipped + 1 known-fail em
worktree environment).

### Changed (Phase 0 — gate-infra extraction)

- **Reusable gate infrastructure** extracted from CC gate into:
  - `validators/_gate_infra.py` — `DispatchResult`, `check_tool_available`,
    `dispatch_native_tool` (cmd_builder param), `render_config_with_placeholders`,
    `parse_overrides`, `apply_overrides` (prefix/key_pattern/extractor params).
  - `validators/_diff.py` — `DiffHunk`, `classify_range_against_hunks`,
    `extract_diff_hunks`, `git_staged_files`, `read_commit_body`.
- **Renamed in `validators/_common.py`:** `cc_threshold_lookup` →
  `gate_threshold_lookup`, `cc_format_three_paths` → `format_three_paths_message`.
  `DEFAULTS_CC` preserved (CC-specific).
- **`check_cyclomatic_complexity.py`** refactored to compose from `_gate_infra`
  + `_diff` + renamed `_common` helpers. ~1127 LOC → ~840 LOC. No behavior
  change (suite delta: -1 test, justified — removed test of internal
  `_TOOL_BIN[lang]` lookup that no longer exists post-refactor).
- **Unblocks Wave R1+** (check_secrets, check_deps_cve, check_duplication,
  check_cognitive_complexity, check_dead_code, check_arch_rules,
  check_function_length_and_nesting): gates compõem em vez de copiar a infra.

### Added

- **Plan auditor** — `.claude/rules/plan-auditor.md` define prompt
  determinístico + 12 checks com severity (2 Critical / 4 High / 3
  Medium / 3 Low) pra auditoria pós-`superpowers:writing-plans`.
  Orquestrador dispatcha `gsd-code-reviewer` com este prompt antes do
  "Execution Handoff" do SKILL.md; Critical findings bloqueiam o handoff
  até fix-dispatch resolver. Output em `.planning/plan-reviews/<plan-slug>-review-r<N>.md`
  (gitignored). Re-audit cap em 3 rodadas, override inline via
  `<!-- audit-override: C-XXX — razão -->` no topo do plano. Integração
  documentada em `CLAUDE.md` §Workflow por verbo,
  `.claude/rules/superpowers.md`, `.claude/rules/subagent-workflow.md`,
  `.claude/rules/README.md`. Spec:
  `docs/superpowers/specs/2026-06-04-plan-auditor-design.md`. Plano:
  `docs/superpowers/plans/2026-06-04-plan-auditor.md`.

  Refinements pós-smoke r1 (2026-06-04): H1 chicken-and-egg exception
  quando task cria target do plano; nova seção "Triggers que não
  dispararam" no output pra distinguir no-trigger de trigger-passou;
  M2 esclarece que anti-goals do spec contam; L2 exceção pra placeholders
  em blocos verbatim; novo verdict tier `PASS_WITH_NOTES` entre
  `PASS_WITH_WARNINGS` e `PASS` pra findings com mitigação contextual
  escrita.

  Sync r2 (2026-06-04): bloco verbatim da Task 1 do plano sincronizado
  com `.claude/rules/plan-auditor.md` atual (341 linhas, refinements
  inclusos) — endereça H-002 Caminho A do smoke r2. 5 meta-findings de
  r2 anotados em `docs/design/04-pending.md` §"Meta-findings r2
  (refinements pra plan-auditor v1.1)" como gaps deferidos pra revisita
  quando padrão recorrer em smokes futuros.

  Ultra-review r1 (2026-06-05): engine externo (`ultra-review-deep`) pegou
  11 findings que a dogfood interna de 3 rounds não viu (bias confirmação
  LLM-auditing-LLM — exatamente F-001 articulado). 10 fixes aplicados
  nesta rodada: §Verdict logic ganha critério determinístico pra
  PASS_WITH_NOTES (cita exceção ou mandamento; sem isso é WARNINGS); §Override
  mechanism trata check-ID inválido explicitamente; template `**Verdict:**`
  lista 4 tiers (incluía só 3); CLAUDE.md row "Editar schema/template"
  ganha plan-auditor (coverage consistente); linha de plan-auditor
  removida da tabela "Skills do superpowers" (Decision 22: skills ≠ rules
  locais — info preservada em §Extensão local); handoff ganha ref ao
  histórico v1.2.0 em git; §C1 valida que N é número real (não literal
  template); §H2 trigger inclui `.claude/rules/**`; subagent-workflow
  ganha cross-ref §"Loop pós-plano (plan-auditor)"; §H4 ganha nota sobre
  hooks. F-009 (README rule count) marcado como FP — README não lista
  per-rule count.

  Power-review PR #6 r3 (2026-06-05): power-review externo (mode
  `code_review`, sonnet) pegou 4 findings pendentes além dos já
  fixados (PR-001 high gap-spec, PR-002/PR-003 medium code-quality,
  PR-004 low code-quality). Endereçado em 4 commits atômicos: sync
  verbatim Task 1 ≡ rule vivo (commit `60cde77` — drift em §Verdict
  logic, §Override mechanism, H2 trigger, H4 nota hooks, C1 cond 4);
  back-port da spec inteira pós refinements r1/r2/ultra-review
  (commit `3f77879` — §Fluxo decisório 4 tiers, §Output format,
  §Integração doc-sync correcta, nota de sync ao final);
  override mechanism aceita qualquer dash separator unicode (commit
  `9282e88` — flex de `-`/`–`/`—`/`--`, propagado pro plan
  verbatim); meta-finding r2 §"Tensão snapshot-vs-vivo" ganha
  case-1 factual citando PR-001 (commit `997a21a` — contagem 1/3
  pra threshold de revisita ficar visível). Spec passa a apontar
  rule vivo como veredito; quando divergir de novo, rule vence.

### Added (PRD docs/product/, 2026-06-04)

- **`docs/product/`** — PRD consolidado do feature-forge com 4 docs (~2205 LOC totais):
  - `docs/product/00-prd.md` (583 LOC) — porta de entrada, 13 seções (Por-quê / Vision / Princípios / Escopo IN-OUT / Personas-resumo / Scenarios-resumo / Roadmap-resumo / Success criteria / Anti-personas / Cross-refs docs técnicos / Glossary 15 termos / FAQ 9 perguntas / Risks 6 + Open questions 4).
  - `docs/product/01-personas.md` (555 LOC) — 8 personas em 3 camadas: Marina (primária) + Bruno + Sub-agente Claude (dedicadas) / Carlos + Lucas + Carolina (variantes Marina) / Patricia + Diego (downstream read-only).
  - `docs/product/02-scenarios.md` (679 LOC) — 6 user journeys end-to-end (C1 Brownfield init / C2 Feature product / C3 Bugfix IN-37234 / C4 Retomar pausado / C5 Extension Gap 9 / C6 Reuse intelligence).
  - `docs/product/03-roadmap.md` (388 LOC) — 3 ondas (Autopilot v1.3-1.4 / Catálogo evolutivo v1.5-2.0 / Inteligência adaptativa v2.x) + Matriz Eisenhower + Anti-roadmap (8 items NÃO entrarão) + cross-ref bidirecional pro `docs/design/ROADMAP.md` técnico.
- Spec fonte: `docs/superpowers/specs/2026-06-04-prd-design.md` (commit `2e1a266`).
- Plan executado: `docs/superpowers/plans/2026-06-04-product-docs.md` (commit `4134744`).
- Coexistência paralela com `docs/design/` (lente arquitetura) e `docs/ux/` (roteiros) — sem mexer em load-bearing (`docs/design/00-vision.md` e `docs/design/ROADMAP.md` permanecem intactos).

### Added

- `forge qa` — 13º comando (adversarial red-team gate). 4 attack vectors
  (spec-vs-spec, chaos, coverage, validator-claim), 4 scope targets
  (feature / screen / task / paranoid), 6 phases (ingest → static →
  generative → sandbox → synthesis → emit), sandbox isolado (Decisão 30).
  Spec: `docs/superpowers/specs/2026-06-05-forge-qa-design.md`.
- Cards podem estender qa via campo aditivo `qa-extensions:` em
  `card.yaml` (schema-version permanece 1; overlay-aware Gap 5).
- Schemas novos: `docs/schemas/qa-report.md`, `docs/schemas/qa-finding.md`,
  `docs/schemas/qa-extensions.md`.
- Workflow-config ganha section `qa:` com 7 campos configuráveis.
- `forge init` Step QA novo (após Step 7.5 do Gap 5).
- `forge reconfigure` menu `[ ] qa` com 5 opções.
- `forge doctor` categoria `qa-coherence` (13ª).
- `forge implement` Phase 6 hook auto-run pré-retrospective (opt-in via
  `qa.auto-run-on-feature-done`).
- Roteiro UX: `docs/ux/forge-qa-roteiro.md` (8 cenas).
- §11 nova em `docs/design/07-discipline.md` — "QA verdict não-bloqueante".
- `engine/_sandbox/env.py` — safe env builder pra subprocess de validators
  (`build_safe_env`, `inspect_dropped`, `is_sensitive`); pure stdlib, zero
  deps em `engine.*` (QA-11).
- Campo `qa-extensions.env-needs` em cards (lista opcional de env vars
  que o card declara precisar no sandbox; QA-11).
- Campo `workflow-config.qa.sensitive-env-grants` (lista de env vars
  sensitive autorizadas explicitamente pelo user; QA-11).
- `engine/cards/grant.py` — `evaluate_sensitive_grants` + `GrantDecision`
  + `UserAbortError`. Prompt 3-caminhos mentor-calmo dispara em
  `forge init` / `forge reconfigure` quando card pede sensitive var sem
  grant prévio (QA-11).
- `engine.qa._alert_sensitive_drops` — alert mentor-calmo pré Phase 3
  quando vars sensitive serão dropadas e nenhum card as declara (QA-11).

### Added (CC gate)

- **Cyclomatic Complexity gate (`check_cyclomatic_complexity`)** — multi-language
  CC validator que roda no cascade de `forge verify` (após
  `check_no_invented_behavior`) e per-task em `forge implement` (entre review e
  commit). Threshold via precedência card `cc-gate-override` > workflow-config
  `cc-gate` > defaults (kotlin=10, swift=10, ts=15, python=10). Dispatch pra
  tools nativas: Detekt (Kotlin), SwiftLint (Swift), eslint (TS/JS), Radon
  (Python). Tools NÃO instaladas pelo forge — `forge doctor` reporta na
  categoria nova `cc-gate-tools` com instruções de install. Regra de fail:
  função `new` com `cc > threshold` OU função `modified` com `cc_after >
  cc_before`. Override-justify via `CC-OVERRIDE: <file>:<func> cc=<N> — <razão>`
  no commit body silencia fail apenas pra aquele commit (auditável via
  `git log --grep='CC-OVERRIDE'`). 3-caminhos canônico on-fail
  (refactor / override-justify / split-task). Bypass de emergência via
  `NO_CC_GATE=1` env var, logado em `.claude/state/cc-gate-bypass.jsonl`.
- Helpers `cc_threshold_lookup` + `cc_format_three_paths` em `validators/_common.py`.
- Configs internos `engine/_cc_configs/{detekt.yml,swiftlint.yml,eslint.json,radon.cfg}`
  controlados pelo forge (versionados junto da release).
- Doctor categoria `cc-gate-tools` (13ª categoria, full scope) com status
  por tool (detekt/swiftlint/eslint/radon) + instruções de install pras
  missing.
- ~63 unit + integration tests novos (`tests/validators/test_cc_*.py`,
  `tests/validators/test_check_cyclomatic_complexity.py`,
  `tests/engine/test_*_cc_*.py`, `tests/integration/test_cc_gate_end_to_end.py`).
  Suite total cresce de 630 → 693 tests collected.
- **Check Secrets gate (`check_secrets`)** — gate multi-tool que barra secrets
  em staged files, com per-stage split: `gitleaks` roda no per-task hook de
  `forge implement` (fast, regex-based, ~100ms) e `trufflehog --only-verified`
  roda na cascade de `forge verify` (deep, verificação ativa contra a origem).
  Posicionado **após** `check_cyclomatic_complexity` no cascade — fail-fast
  Decision 23 preservado. Override via `SECRETS-OVERRIDE: <file>:<line>
  kind=<token-type> — <razão>` no commit body silencia o finding `(file, line,
  kind)` apenas naquele commit (auditável via `git log --grep='SECRETS-OVERRIDE'`).
  Hard-fail sempre quando secret sobrevive; tool missing → warn (cascade segue
  alive, mesmo contrato do CC gate). Bypass de emergência via `NO_SECRETS_GATE=1`,
  logado em `.claude/state/secrets-gate-bypass.jsonl`. Composto inteiramente da
  infra Phase 0 (`dispatch_native_tool`, `apply_overrides`, `check_tool_available`,
  `git_staged_files`, `read_commit_body`, `result_*`). Doctor ganha 14ª categoria
  `secrets-tools` (gitleaks + trufflehog + install hints). Validators 15→16.
  Tests em `tests/validators/test_check_secrets*.py` +
  `tests/integration/test_secrets_gate_end_to_end.py`.

### Added (CC gate refinements — final review fixes)

- **Dynamic threshold propagation** for Detekt and SwiftLint: configs use
  `__CC_THRESHOLD__` placeholder rendered per invocation via tempfile.
  Spec §3 contract "threshold via CLI args sempre" honored — mechanism
  differs from eslint `--rule` flag because Detekt/SwiftLint don't accept
  CC threshold via CLI.
- **Radon rank filter** changed from `-n F` (rank F = CC ≥ 41) to `-n A`
  (all functions). Previous filter masked CC ∈ [11..40], making Python
  gate effectively cc=41 instead of configured threshold.
- **Canonical 3-caminhos render** now reaches the user: `cc_format_three_paths`
  output stored in `result["render"]`, consumed by `engine/implement.py:_render_cc_gate_block`.
- **Malformed override warnings** propagate from `_apply_overrides` (now
  returns 3-tuple `(silenced, surviving, warnings)`) up to the result
  dict so users see why their CC-OVERRIDE attempt didn't count.
- +8 tests novos (1 dispatch radon `-n A`, 2 dispatch threshold-via-config
  Detekt/SwiftLint, 1 validate canonical render, 1 validate warnings,
  1 helper apply_overrides warnings, 2 implement render canonical). Suite
  total: 682 passed, 17 skipped.

### Added (Gap 9 — extends-feature mechanic, 2026-06-03)

- **Gap 9 resolvido — extends-feature mechanic (re-escopado 2026-06-03)** —
  feature done pode ser estendida via novo slug derivado (e.g.,
  `lembrete-rega-watch-extension`) que herda contexto da pai via campo
  aditivo `extends-feature: {parent-slug}` no `status.json` + intake. Sem
  cards canon novos; sem mudança no enum `platforms`; sem upgrade de
  inventory schema. Pattern leve product-derived. Cobertura nova:
  - **Schema** — `docs/schemas/memory.md` ganha `extends-feature` +
    `parent-feature` em `status.json`; MEM-L1-008 atualizada com regra
    "se `extends-feature != null` → parent existe E `parent.state == done`".
    Forward-compat: status.json pré-Gap 9 carregam normais (default null).
  - **Engine** — `engine/memory/l1.py` `L1State` ganha `extends_feature` +
    `parent_feature` + helpers `parent_state()` + `list_extensions_of()`.
    `engine/plan.py` Cena 1 oferece 4º caminho **"Estender"** quando
    feature pai existe em `state=done`; context-pack import lê `status.json`,
    `hypothesis.yaml`, `data-contract-spec.yaml`, `screen-analysis.yaml`,
    `tech-spec.md`, `existing-helpers.yaml` da pai e popula o intake da
    extensão.
  - **Template** — `templates/feature-intake.template.md` ganha bloco
    condicional §Extension context (parent feature, parent shipped, scope of
    extension, reuse from parent, out-of-scope vs parent). Ausente quando
    `extends-feature` é null — standalone feature fica idêntica ao pré-Gap 9.
  - **UX** — `docs/ux/forge-plan-roteiro.md` Cena 1 ganha 4º caminho
    "Estender" com sub-cenários (happy / parent não-done / slug derivado
    duplicate / cancelar).
  - **Validator** — `validators/validate_extension_feature.py` novo:
    EXT-001 (parent existe), EXT-002 (parent.state == done), EXT-003
    (slug derivado != parent), EXT-004 (dedupe por `extension-scope`).
    3-caminhos canônico no fail (discipline §1). Inativo quando
    `extends-feature` é null (no-op pass). **Wiring na cascade `forge
    verify` deferido pra v1.x+ (W-001)** — validator existe standalone +
    coberto por testes; cascade auto-discovery (via cards/hooks) vem
    com piloto smoke. Hoje invocação é manual ou via hook custom; ver
    `docs/design/04-pending.md` Gap 9 TODO residual.
  - **Agents patched (4):** `planning-conductor` (Phase 1 step 5 extension
    import + Phase 4 wave dispatch variants A/B/D + Phase 6 retrospective
    variant + closing format), `feature-intake-agent` (extension block
    elicitation), `tech-spec-agent` (context-pack ganha `extends-feature` +
    `parent-baseline` references — sem mudança em rendering), `retrospective-
    agent` (extension variant 4 perguntas: herdei literal / delta mínimo /
    criei do zero apesar de extension / sinais pra refactor parent + extension
    pra shared base).
  - **Discipline §10 nova** em `docs/design/07-discipline.md` formaliza
    semantics + distinção formal vs refactor/bugfix/standalone (tabela
    4-eixos) + wave dispatch semantics + filesystem layout
    (`L1/{parent}-{suffix}/`, **não** `non-product/`) + hypothesis schema +
    Phase 6 retrospective (herança vs adição, sem 5-whys) + cheat-sheet
    entry + cross-link com §8 + §9 + Gap 5.
  - **Tests** — 37 novos (`tests/unit/test_extension_feature.py` cobre
    round-trip L1State + helpers + validator happy + 4 fail paths;
    `tests/unit/test_plan_extension.py` cobre Cena 1 4º caminho detection +
    sub-cenários). Suite total: 595 → 637 passing (+42 cumulativo desde
    v1.2.0: 37 Gap 9 + 5 do fix loop).
- `engine/implement.py` escreve `shipped-at` (ISO 8601 UTC) automático na
  transição `state=done` (sob o mesmo bloco que escreve
  `last_action_kind = "implement-completed"`). Suportado por `L1State.raw`
  round-trip — forward-compat com features done pre-Gap 9 (campo é
  nullable, intake renderiza `unknown` quando ausente). Fix do W-002 do
  REVIEW: extension intake rendering de `Parent shipped: {{parent_shipped_at_iso8601}}`
  passa a ser populado em vez de sempre `null`/`unknown`.

### Changed

- `docs/design/04-pending.md` Gap 9 re-escopado e fechado: watchOS / Wear OS /
  tvOS / multi-target movidos pra **"out-of-scope explícito permanente"**
  (feature-forge cobre mobile = Android + iOS + KMP). Mecânica
  `extends-feature` continua útil pra variant / sub-area / módulo paralelo.
  Sinergia com Gap 5: plataforma exótica futura entra via overlay local
  (`.claude/cards/local/`), não via canon expansion. Nenhuma decisão locked
  revisitada (Decisões 9, 10, 14, 22, 28 aceitam aditivo natural).
  Contadores atualizados (7 resolvidos / 9 acionáveis pra v1.x+).
- `docs/design/07-discipline.md` §10 header padronizado (`## 10. Extension
  feature`) alinhado ao paralelismo das §§ 1-9 (fix do I-007 do REVIEW —
  consistência estilística vs prefixo `§10` + parênteses inline).
- `engine/plan.py` `_create_extension_l1` ganha guard explícito enforçando
  `parent_status.status == "done"` (fix do W-005 do REVIEW). Defesa em
  profundidade: write-time check além do validator runtime. Custo: 4
  linhas + 1 test.
- `agents/retrospective-agent.md` extension variant agora cobre as **4
  perguntas** canônicas do discipline §10 (era 3 — faltava "sinais pra
  refactor parent + extension pra shared base"). Fix do W-003 do REVIEW.
  `agents/planning-conductor.md` template prompt for retrospective-agent
  (extension variant) idem.
- `validators/validate_extension_feature.py` remove check redundante
  `parent-feature != extends-feature` (fix do I-002 do REVIEW). Lockstep
  é garantido por `_create_extension_l1` e `write_l1_status` no write path
  — defender contra arquivo escrito à mão é overkill pra v1; os 4 codes
  EXT-001..004 do plano canônico ficam estritos.
- `CLAUDE.md` baseline de testes atualizado: `pytest (367 tests baseline)` →
  `pytest (637 tests baseline)` (fix do I-006 do REVIEW — drift pré-existente
  desde v1.1.0 + acumulado em v1.2.0 + Gap 9). Re-baselinar pra próximo
  gap saber a verdade.
- `engine/memory/l1.py`: simplifica fallback kebab/snake em `read_l1_status`
  com `dict.get(kebab, dict.get(snake))` (refactor puro, sem mudança de
  comportamento) — endereça nit gemini-code-assist no PR #3 (commit
  `7313a30`).
- `engine/qa/sandbox.py._hardened_env` agora delega base do env pra
  `build_safe_env(extras=...)` em vez de `dict(os.environ)`. Refactor
  mantém PYTHONPATH guard + FORGE_QA_SANDBOX marker (QA-11).
- `engine.verify` linha 624 — `subprocess.run` pra validator agora usa
  `env=build_safe_env()` (era default: herdar env completo do pai). Bug
  silente de leak fechado (QA-11).

### Changed (load-bearing)

- Revisita decisão 9: command surface 12 → 13 subcomandos — adiciona `forge qa` (adversarial red-team gate). Design completo em `docs/superpowers/specs/2026-06-05-forge-qa-design.md`. Locked at 12 histórico preservado em `docs/design/01-decisions.md` linha 9; novo lock em linha 29.
- Adiciona decisão 30: sandbox isolation pra `forge qa` Phase 3 — subprocess CWD dedicado em `.planning/qa/<run-id>/fixtures/`, SandboxBreachError em writes fora, budget global configurável.

### Security

- **QA-11 fechado.** Secrets do processo pai (`AWS_TOKEN`, `GITHUB_TOKEN`,
  `DB_PASSWORD`, `*_SECRET`, etc.) não vazam mais pro subprocess de
  validators rodando em `forge qa` Phase 3 sandbox nem em `forge verify`.
  Mitigação cobre dois threats: card extension malicioso (`qa-extensions.
  auditors` lendo `os.environ`) e leak acidental em validator canon
  (traceback que printa env em debug). Defesa = allowlist core
  (`CORE_ALLOWLIST` hardcoded em `engine/_sandbox/env.py`) + per-card
  opt-in declarativo + grant explícito do user pra vars sensitive.

### Fixed (PR #4 review)

- `_path_matches_ignore` agora emite warning quando regex inválida em
  `cc-gate.ignore-paths` (era silently swallowed). Pré-validação via
  helper `_compile_ignore_patterns` em `validate()`, warnings propagam
  no result dict (`cc-gate.ignore-paths: regex inválida '<pat>' (<erro>)`)
  — D-006.
- `_parse_overrides` emite warning pra `CC-OVERRIDE: ... cc=N — ` com
  reason vazia/whitespace após em-dash (era loose-skipped). Strict regex
  ganhou guard `reason.strip() == ""` pra não aceitar reason em branco;
  loose-pass inspeciona o tail após `—` — D-008.
- Warnings de `_run_tools_for_staged` agora distinguem tool ausente
  (`[<tool>] tool ausente: ...`) de tool crashada
  (`[<tool>] tool crashou: ...`) — D-009.
- `_git_staged_files` adiciona `-M80%` ao `git diff` pra rename detection
  (SDD §2 — função renomeada até 20% mudança vira `modified` no delta
  rule, não `new` + delete) — F-006.
- Test assertions tightened: `install_hints` específico pro `eslint`
  (filtra por `c.name == "eslint"` antes de checar substring),
  `next()` lookup safer em `test_verify_cc_position` (default None +
  assertion descritivo) — codereviewbot 3353045999/3353046005.
- +6 tests novos cobrindo D-006/D-008/D-009/F-006. Suite total:
  688 passed, 17 skipped, 1 falha pre-existing
  (`test_bootstrap_is_idempotent` em worktree — Gap BOOTSTRAP-1).

### Fixed (QA-11 post-review remediação)

- **QA-11 final review remediação** (commits `0563cfa` + `728aa79`):
  - **CR-01:** `conductor-handoff.json` agora inclui
    `config.allowed_env_extras` (list[str] derivada de cards' `env-needs`
    + `sensitive-env-grants`); `agents/qa-conductor.md` documenta contrato
    de consumo (`run_sandbox(extras=...)`). Sem isso, a chain card
    `env-needs` → sandbox subprocess ficava plumbing-only em produção.
  - **CR-02:** `_alert_sensitive_drops` em `engine/qa/__init__.py` tinha
    interseção invertida (`card_env_needs & (CORE ∪ granted)` — filtrava
    non-sensitive vars de cards). Substituída pela semântica correta:
    non-sensitive sempre passa; sensitive só com grant.
  - **CR-03:** `engine/cards/loader.py` agora guarda `isinstance(v, str)`
    antes de `is_sensitive(v)` — `env-needs` malformado no canon path não
    crasha mais com `TypeError` cru.
  - **IM-01:** `engine/verify.py` subprocess de validator agora passa
    `extras=("JAVA_HOME", "ANDROID_HOME", "GRADLE_USER_HOME")` — CC
    validator (detekt/swiftlint) volta a funcionar em codebases
    Kotlin/Android.
  - **IM-02:** alert layer `except Exception` estreitado pra
    `(CardError, OSError, ValueError, KeyError)` — deixa de mascarar bugs
    reais.
  - **IM-03:** `evaluate_sensitive_grants` agora ordena `cards_requesting`
    antes do join — prompt UX determinístico cross runs.
  - **IM-04:** alinhamento de calling style de `three_paths_block` entre
    `engine/qa/__init__.py` e `engine/cards/grant.py` (positional
    consistente).
- Re-review confirmou os 7 findings endereçados corretamente. Suite
  rapid lane: 896 tests verdes.

### Fixed (QA-13)

- `engine/qa/scope.py._list_features_for_paranoid` agora filtra features
  com `state ∈ {"aborted", "archived"}` (per spec §5.0). Fail-safe
  default-include pra features legacy (sem status.json) ou status.json
  malformado — paranoid quer audit broad, broken features ficam visíveis
  pra user notar gaps. Fecha pré-piloto bloqueador QA-13.

## [1.2.0] — 2026-06-03

### Added (Gap 5 — Card local overlay, 2026-06-02)

- **Gap 5 resolvido — Card local overlay (Approach A)** —
  `.claude/cards/local/<name>/` versionado no projeto consumidor, lido via
  loader cascade canon ∪ local com hard-fail em colisão. Valida via
  `validate_card_yaml` (canon/local discrimination por path resolved) +
  `validate_capability_labels` (overlay-aware via `validators/_common.load_catalog`).
  Reconfigure ganha submenu `card-local` (listar/adicionar/remover). Init
  ganha Step 7.5 com 3-caminhos pra signals órfãos (criar local / ignorar /
  abortar). Edge case: orphan em label reservada vira "abrir ADR".
- **Cards canon novos:** `retrofit-client` (provê `http-client`) e
  `shared-preferences-prefs` (provê `local-prefs-storage` legacy com
  `legacy-marker: true`). 20 → 22 cards canon.
- **Schema bump aditivo:** novo campo top-level opcional `legacy-marker: bool`
  no `card.yaml` (default false). `schema-version` permanece `1`.
- Nova exception `CardConflictError` em `engine.cards`.
- Nova validação `CARD-019` (legacy-marker, if present, must be bool).
- **Nova decisão locked 28** (Card local overlay — Approach A) registrada
  em `docs/design/01-decisions.md`. Não revisita decisão prévia — é decisão
  *adicionada*; a ceremony "revisita decisão" do hook pre-commit fica
  satisfeita por esta nota explícita pra que o commit doc-sync passe sem
  bypass (não é revisita; é decisão nova append-only).

### Fixed (Power-review PR #2 follow-ups — 2026-06-03)

- **CARD-008 conformity em `validate_capability_labels`** — `conflicts-with`
  passa a aceitar label OR card-name conforme o schema. Antes, o validator
  rejeitava o canon `shared-preferences-prefs` (que declara
  `conflicts-with: [datastore-prefs]` por card-name) — bloqueava qualquer
  consumer rodando `forge verify`.
- **Orphan signals grouping por capability** em `engine/init.py` Step 7.5
  caminho 1 — múltiplos orphans com a mesma `suggested_capability` agora
  geram UM único card local com signals consolidados (antes, o segundo
  write sobrescrevia silenciosamente o primeiro). `_card_local_add_inline`
  aceita `OrphanSignal | list[OrphanSignal]` (backward compat).
- **`_count_needle_hits` respeita `_SKIP_DIRS`** em `engine/init.py` —
  `node_modules`, `build`, `.gradle`, `Pods`, `DerivedData`, `dist` são
  filtrados no walk. Sem isso, init em monorepos travava por minutos
  varrendo deps/build artifacts.
- **Atomic write** em `_write_local_cards_manifest` (`engine/cards/loader.py`)
  via `tempfile.mkstemp` + `os.replace` — sem manifest parcial em disco se
  o processo morrer no meio do write.
- **Rollback** em `_card_local_add` (`engine/reconfigure.py`): falha de
  OSError em qualquer um dos 3 writes (card.yaml, README.md,
  detection/signals.yaml) remove o card_dir parcial e mostra erro colored.
- **OSError capture** em `validators/_common.load_catalog` e
  `validators/validate_card_yaml.validate` — antes apenas YAMLError era
  capturado; OSError vazava como traceback bruto.
- **N2/N3 init** — docstring + UX copy de Step 7.5 caminho 1 agora avisa
  honestamente que catálogo expandido só ativa no próximo `forge init`
  (re-detection inline fica pra v1.2). Anti-colisão canon adicionada em
  `_card_local_add_inline` (sufixo `-local` se nome colide com canon).
- **N4 reconfigure** — `_save_draft` surface OSError via renderer warn
  (era silently-swallowed). Reconfigure continua, mas user é avisado.
- **N12 reconfigure** — label do caminho 1 no submenu de colisão de nome
  troca "fornecer outro nome" por "ver cards existentes e voltar
  (re-prompt em v1.2)" pra honrar o contrato 3-paths (disciplina #1).
- **N10 refactor** — `_LOCAL_CARD_NAME_RE` promovido de
  `engine.reconfigure` (private) pra `engine.cards.LOCAL_CARD_NAME_RE`
  (public). Engine/init.py e engine/reconfigure.py importam da fonte
  canônica; alias antigo mantido em reconfigure pra back-compat.
- **N11 loader** — `_write_local_cards_manifest` fallback graceful pra
  paths não-subpath de project_root (`relative_to` ValueError → str
  absoluto). Raro mas observável em fixtures de teste.
- **Tests strengthened** — `test_cascade_raises_on_malformed_local_card_yaml`
  ganha assert do path/marker no erro (C9); novo
  `test_cascade_writes_local_cards_manifest_with_multiple_cards_sorted`
  cobre 2+ locals + ordem canônica (C10); dead imports limpos em
  `test_e2e_local_card_pilot.py` (N8) e `test_card_md_schema.py` (N9);
  type annotation em `_check_orphan_signals.catalog` (N5).
- **Novos testes TDD** (rapid lane 521 → 533, +12):
  - `tests/unit/test_validate_capability_labels_conflicts_with_card_name.py`
    (N1, 3 testes)
  - `tests/unit/test_init_count_needle_hits_skip_dirs.py` (C16, 5 testes)
  - 3 testes adicionais em `tests/unit/test_init_orphan_signals.py` (C14/C15)
  - 1 teste adicional em `tests/unit/test_cards_loader_local.py` (C10)
- **Graph schema_version integration test drift** — `tests/integration/test_graph_build_meobonsai.py::test_build_full_creates_meta_schema_version`
  agora trackeia `sqlite_io.SCHEMA_VERSION` dinamicamente em vez de hardcoded `"1"`.
  Drift introduzido em `65c358c` (feat: reuse-intelligence shipped novas tabelas de
  graph + bump pra "2") nunca foi refletido no integration test. Pré-existente ao
  PR #2 / Gap 5; identificado durante power-review R1.

### Fixed (PR #1 round 3 — 2026-06-02)

- `implement.run` blocked-on-external branch não chama mais
  `release_phase_lock` antes do acquire — preservava lock stale de
  outro fluxo, violando single-writer invariant. Recovery de lock
  stale fica via `forge undo` (A3; `engine/implement.py`).
- `.claude/bootstrap.sh` detecta symlinks quebrados (target ausente) e
  re-linka em vez de pular silenciosamente.
- `.claude/hooks/post-edit-doc-drift.sh` agora usa `fcntl.flock` (via
  python3 inline) ao ler-modificar-escrever os JSON state files
  (`drift-warned.json`, `drift-pending.json`) — protege contra race em
  invocações concorrentes do hook.
- `.claude/hooks/pre-tool-use-load-bearing.sh` agora usa `fcntl.flock`
  no append do audit log — sem corrupção de JSONL em invocações
  paralelas.
- `.claude/hooks/session-start-orientation.sh` removeu
  `set -euo pipefail` que violava o contrato "sempre exit 0". Errors
  internos não derrubam mais a sessão.
- `engine/doctor._check_reuse_findings` usa `contextlib.closing()` em
  vez de try/finally — conn fecha mesmo em exceções não-sqlite3
  (RuntimeError, MemoryError).
- `engine.graph.parser_kotlin._simplify_generics` ganhou ceiling de
  iteração + increment garantido — input malformed (`"List<T"` sem
  fechamento) não pode mais loopar infinitamente.
- `engine.memory.acquire_phase_lock` agora emite warning via stderr
  quando o unlink do sentinel falha após `_mirror_phase_lock_to_status`
  raise — operadores vêem o sentinel stuck em vez de o erro ser
  silenciado.
- `blocking_deps` warning wording mudou pra `corrupt YAML — failed to
  parse` (era `skipping unreadable`); test regex agora exige keyword
  específico ao invés de só checar task ID.

### Tests (R3)

- 5 novos regression tests pra R3: foreign-lock preservation,
  doctor conn-close-on-error, parser_kotlin simplify_generics
  termination (com threading watchdog), bootstrap symlink repair
  (integration), e tightened blocking_deps warning assertion.
- Total: **463 unit tests passing** (era 455 fim de R2 → +8).

### Fixed (PR #1 round 2 — 2026-06-02)

- `_fingerprint` agora usa `\x00` (NUL) como separador em vez de `|`, fechando colisão com TS union types em body text (A7; `engine/graph/duplicates.py`).
- `GROUP_CONCAT` agora usa `\x1F` como separador em vez de `,`, suportando paths com vírgulas em occurrence rows (A8; `engine/graph/duplicates.py`, `engine/graph/queries.py`).
- `blocking_deps` sobrevive a `TASK-*.yaml` corrupto — per-file try/except + stderr warning (A10; `engine/memory/l1.py`).
- `parser_kotlin` máscara strings/comments antes de `_RE_DECL.finditer`, eliminando false-positives dentro de raw strings `"""...fun fake() {...}"""` e block comments (A11; `engine/graph/parser_kotlin.py`).
- `detect_after_update` / `update_file` / `update_batch` agora fecham `conn` em todo exit path (mesma classe que C2 lock leak; `engine/graph/incremental.py`).
- RFC arrow regex tolera one-level nested parens (e.g., `({callback = (x) => x}) => <div/>`) e aceita JSX `<` como body start (`engine/graph/parser_typescript.py`). Aviso: comp count vai crescer em projetos consumidores com RFCs JSX-style.
- `_resolve_subtype` em `check_no_behavior_change` propaga exceções inesperadas (incluindo `MemoryError`) em vez de silenciar tudo; só `FileNotFoundError, OSError, ValueError, KeyError, yaml.YAMLError` fall through pra default `"product"` (`validators/check_no_behavior_change.py`).

### Changed

- `.claude/rules/orchestrator-persona.md` ganhou seção "Não-procrastinação" formalizando default "endereça agora" vs "defer com razão concreta" (5 categorias legítimas de defer). CLAUDE.md root aponta pra ela em nova seção "Mentalidade operacional". Origem: feedback de sessão 2026-06-02 no PR #1, depois que expansão de escopo R1→R2→R3 cobriu 55 commits em vez dos 15 iniciais (2026-06-02).
- `engine.memory.l1.phase_lock_held` context manager substitui o flag pattern em `engine.implement.run` — release estrutural via `__exit__` em vez de `if not lock_released: release_phase_lock(...)`. NOT REENTRANT-SAFE — documentado em docstring + test (MD-03).
- `parser_typescript._RE_RFC_ARROW`: body start lookahead expandido de `[\(\{]` para `[\(\{<]` (aceita JSX raw bodies). Subprodute: contagem de RFCs detectados vai crescer em codebases com `const X = () => <div/>`.

### Performance

- `list_reuse_findings` agora usa single JOIN em vez de N+1 query loop (A13; `engine/graph/queries.py`). 50 findings + 150 locations = 2 queries (era 51).

### Tests

- 24 novos regression tests pra round-2 fixes: fingerprint NUL, occurrence separator, blocking_deps corrupt YAML, parser_kotlin mask, incremental conn lifecycle, RFC arrow regex, phase_lock_held CM (+ reentrant contract), _resolve_subtype narrow except, A13 perf (query count instrumentation).
- 12 cobertura mínima do master review: Q12-Q17 (6 query tests), `infer_suggested_target` 6 categorias (5 do plano + duplicate-ts-helper via IN-03), Kotlin raw-string brace regression, Swift `"""` + escapes.
- Total: **508 tests passing** (unit + integration) — era 367 baseline original v1.1.0; cumulativo no PR #1.

### Documentation

- `engine/utils/sqlite_io.py` — comentário explicando trade-off de `synchronous=NORMAL` (3x faster writes, last-tx-may-be-lost on power loss, graph DB é cache recuperável via `forge reconfigure`).
- `engine/reconfigure.py` — comentário sobre `kill -9` mid-loop deixar partial state cross-file; recovery é MANUAL via `.bak` files no disco (`forge undo` NÃO cobre esse path — gap em `docs/design/04-pending.md`).
- `engine/doctor.py` — docstring de `_stamp_last_doctor_run` documenta last-write-wins em CI matrix; stamp é observabilidade informacional.
- `engine/graph/_body_text.py` — `hash_body` docstring expandido com collision math (64 bits → birthday collision ~50% @ 2^32 ~4B symbols), alternativas BLAKE3-128 (2x DB) e SHA-1 full (2.5x DB).
- `engine/memory/l1.py` — `phase_lock_held` docstring marca não-reentrante + nomeia callers atuais + aponta pra v1.1.1.

## [1.1.0] — 2026-06-01

### Released

- Released as **v1.1.0** — `engine/__version__` e `pyproject.toml` alinhados em `1.1.0` (commit `7286fa0`, C4). `forge --version` agora reporta `forge 1.1.0`.

### Added (Claude Code rules system)

- `CLAUDE.md` root + `.claude/rules/*.md` (12 operational rules) — Mandamento 0 (orchestrator-mantenedor com delegação total via Agent tool) + 6 mandamentos (decisões locked, verde antes de pronto, reuso, escopo, voz mentor calmo, doc-sync) + workflow por verbo + map dos 10 superpowers skills ativos.
- `.claude/hooks/*.sh` (4 hooks): `session-start-orientation.sh` (injeta Mandamento 0 + estado), `pre-tool-use-load-bearing.sh` (warn + audit em load-bearing edits), `post-edit-doc-drift.sh` (lembrete doc-sync once-per-file-per-session), `pre-commit-feature-forge.sh` (HARD BLOCK em `01-decisions.md` sem ceremony "Revisita decisão" + SOFT WARN em código vivo sem doc-sync).
- `.claude/settings.json` registrando os 3 hooks Claude Code (SessionStart, PreToolUse, PostToolUse).
- `.claude/bootstrap.sh` (idempotent one-time setup — symlinks `.git/hooks/`).
- `tests/integration/test_claude_rules_system.py` — 36 testes (marker `integration`).
- `docs/superpowers/specs/2026-06-01-claude-md-design.md` (brainstorm) + `docs/superpowers/plans/2026-06-01-claude-md-rules-system.md` (plan executável).

### Adicionado

#### Stress-test 2026-05-29 — 4 Gaps shipped

- **Gap 1 — Bugfix subtype** (hotfix urgency fast-path): `subtype="bugfix"` no
  `_VALID_SUBTYPES`, keyword + ticket-pattern detection (`IN-/PD-/BUG-`),
  Wave B conditional sub-question (`A·C·D·E` logic-only OR `A·B·C·D·E`
  UI-observable), template `feature-intake-bugfix.template.md`.
- **Gap 2 — Non-product feature track** (refactor only; spike + chore stubbed):
  `subtype=refactor|spike|chore`, filesystem layout `non-product/{slug}/`,
  template `feature-intake-refactor.template.md`, validator
  `check_no_behavior_change` gateando Wave E.
- **Gap 8 — `blocked-on-external` state** (orthogonal to subtype): state
  enum value, manual unblock via `forge reconfigure → external-deps`,
  preservado em retomadas.
- **Gap 18 — Reuse intelligence** (expansão completa): detecção init-time +
  incremental + 6 categorias (within-module, cross-module, redundant-platform,
  near-duplicate, kmp-migration, ts-helper) + integração com `forge plan`
  refactor subtype.

#### Reuse intelligence (Gap 18 expandido)

- **6 detection categories** em `engine/graph/duplicates.py`:
  - `duplicate-within-module` (Kotlin extension repetida em 1 módulo, conf 0.95)
  - `duplicate-cross-module` (sibling modules → smallest-common-ancestor via
    Gradle dependency closure, conf 0.85)
  - `redundant-platform-specific` (Android Kotlin idêntico a shared commonMain, conf 0.90)
  - `near-duplicate` (mesma assinatura, body_hash diferente — drift signal, conf 0.40)
  - `kmp-migration-candidate` (Swift ↔ Kotlin shared com Jaccard ≥0.4, conf 0.50–0.75)
  - `duplicate-ts-helper` (TypeScript top-level duplicado, conf 0.95)
- **Schema v2 — colunas + tabelas**:
  - `files.source_set` (commonMain / androidMain / iosMain / …)
  - `symbols.{receiver_type, body_hash, body_tokens, modifiers}`
  - `module_deps` (Gradle dependency graph parsed de cada `build.gradle(.kts)`)
  - `reuse_findings` + `reuse_finding_locations` (materialized detection output)
- **Parser overhaul** (Kotlin / Swift / TypeScript):
  - visibility agora persistida (era hardcoded "public")
  - signature normalizada (param names dropped, generics simplified)
  - body extraction brace-aware em `engine/graph/_body_text.py`
  - body_hash (SHA-1[:16]) + body_tokens (JSON) para Jaccard cross-language
  - Swift two-pass captura receiver de `extension Type { func ... }`
- **Module inference** (settings.gradle + build.gradle parsing):
  - `engine/graph/gradle_modules.py`: longest-prefix match para multi-módulo
    (KMP `:shared:feature:auth` ou Android `:androidApp:feature:bonsai`)
  - `engine/graph/gradle_deps.py`: transitive closure + smallest-common-ancestor
- **Apply flow** (`engine/graph/reuse_apply.py`):
  - 6 novos kinds em `_VALID_KINDS` do distiller
  - `apply_proposal_to_l2` dispatcha para `apply_reuse_intelligence_proposal`
  - Renderiza `templates/feature-intake-refactor.template.md` com payload
  - Escreve L1 `status.json` com `subtype="refactor"` → `forge plan {slug}`
    detecta automaticamente e pula Wave A discovery (Gap 2 integration)
- **Engine wiring**:
  - `engine/init.py` Step 11.5: `queue_proposals_from_table` após graph build
  - `engine/init.py` Step 11.6: escreve `.claude/hooks/post-edit-detect-duplications.sh`
  - `engine/reconfigure.py`: re-queue após rebuild
  - `engine/doctor.py`: `_check_reuse_findings` agregado por categoria
  - `engine/graph_cli.py`: opções 12–17 + `r` (combined) + `forge graph detect-incremental <file>` non-interactive
  - `engine/graph/incremental.py`: `detect_after_update` para hook entrypoint
- **Q11 backward-compat**: filtro `f.module = 'shared'` → `LIKE 'shared:%'`
  para multi-módulo shared.
- **Tests iniciais**: 20 unit tests em `tests/unit/test_reuse_intelligence.py`,
  cobrindo body extraction, gradle parsing, parser fields, detection completo,
  apply + status.json.
- **Schema docs**: `docs/schemas/graph.md` + `docs/schemas/proposed-evolutions.md`
  ganham seção "Reuse Intelligence (schema v2)".

### Fixed (PR #1 bloqueadores — 2026-06-01)

Round final de hardening da v1.1.0: critical (C1–C4), alta (A1, A2, A5, A6, A9, A12), review (CR-01, CR-02, MD-01, HG-01, HG-02, HG-03). Conjunto coberto por 38 novos regression tests; nenhum locked decision foi revisitado.

- **C1 + A1 — Phase lock atomic** (`engine/memory/l1.py`, commit `0b96212`): `acquire_phase_lock` fazia read-then-write em `status.json` — sob N processos racing, múltiplos passavam o check e o último writer ganhava. Sentinela `.phase-lock` via `os.open(O_CREAT | O_EXCL)` é agora o gate atômico; `status.json` continua espelhando o lock id pra read APIs. Regressão coberta com `multiprocessing.Barrier` (16 workers, um único vencedor).
- **C2 — Implement lock release em qualquer exception path** (`engine/implement.py`, commit `f0776ab`): o `try/except` da critical section só capturava `PromptAbortedError`. Qualquer outra exceção (RuntimeError, OSError, KeyError) escapava com o lock retido, forçando `forge undo` pra recuperar. Flag `lock_released` + `finally` backstop garantem release em qualquer caminho — auditável em `history.jsonl`.
- **C3 — `_reset_domain_tables` atomic + FK pragma restore** (`engine/graph/builder.py`, commit `c84779a`): rodava `PRAGMA foreign_keys = OFF` → DELETEs → `PRAGMA = ON`. Se um DELETE raise no meio, o pragma final nunca executava e a conexão silenciosamente vazava `foreign_keys=OFF` pra toda transação subsequente. `try/finally` dentro de `with conn:` garante rollback + pragma sempre restaurado.
- **C4 — Version bump 1.0.0 → 1.1.0** (`engine/__init__.py` + `pyproject.toml`, commit `7286fa0`): engine e pyproject reportavam `1.0.0` apesar do release v1.1.0 já cobrir reuse-intelligence schema v2 + 17 graph queries + Claude Code rules system. `forge --version` e `import engine.__version__` agora batem com CHANGELOG.md e session-handoff.
- **A2 — `forge plan` retorna 130 em deferred wave** (`engine/plan.py`, commit `f9e5b48`): `_run_waves_for_subtype` retornava `0` quando uma wave setava `WaveResult.deferred=True`. Caller `run` então pulava o guard `if rc != 0` e marcava a feature como `planned`, destruindo silentemente o estado pausado. Contract do docstring (`0=ok, 130=paused, other=hard gate`) restaurado.
- **A5 — Swift triple-quoted strings no brace counter** (`engine/graph/_body_text.py`, commit `426b278`): brace counter só entrava em triple-quote mode pra Kotlin. Body Swift com `"""` literal contendo `"` ímpar flipava `in_string_double` parity, e o próximo `}` era parseado como código — popping o scope da função prematuramente. Trigger estendido pra `{kotlin, swift}`.
- **A6 — Groovy DSL parens opcionais** (`engine/graph/gradle_deps.py`, commit `56fefae`): regex só cobria forma Kotlin DSL `implementation(project(":x"))` com outer parens. Groovy DSL `implementation project(":x")` (sem parens) silentemente caía fora da dependency closure. Parens externos agora opcionais, whitespace separator aceito.
- **A9 — Tie-breaker determinístico em `find_smallest_common_ancestor`** (`engine/graph/gradle_deps.py`, commit `56fefae`): tie-breaker usava `-ord(c[0])` (inspeciona só primeiro char) — produzia ordem inconsistente com o docstring que promete lexicográfico. Trocado por `key=(in_degree, c)` puro lex.
- **A12 — Root-level `test/` folder reconhecido** (`validators/check_no_behavior_change.py`, commit `a8c5ac4`): heurística `_looks_like_test_file` comparava contra segments tipo `/test/` (leading + trailing slash); paths root-level `test/MockData.kt` caíam no suffix check e eram misclassificados como production code, enfraquecendo o refactor gate. `/` prepended antes do segment match.
- **CR-01 — Implement `try/finally` cobre full critical section** (`engine/implement.py`, commit `0029c59`): C2 fechou o leak parcialmente; CR-01 estende o `try` pra cobrir o cinematic header completo (`read_l1_status`, `current_subtype`, etc.) — qualquer raise antes do dispatch também passa pelo release path agora.
- **CR-02 + MD-01 — Lex-smallest tie-breaker + Groovy closure regression** (`engine/graph/gradle_deps.py`, commit `13559e2`): docstring de `find_smallest_common_ancestor` prometia "lex-smallest among ties" mas a implementação ainda preferia ordem instável quando `in_degree` empatava. Tie-breaker `min(candidates)` puro + regression test cobrindo Groovy DSL com trailing config closure.
- **HG-01 — `_reset_domain_tables` asserta no open transaction** (`engine/graph/builder.py`, commit `3b7dcd3`): `PRAGMA foreign_keys` é no-op dentro de transação (SQLite contract). Adicionado `assert conn.in_transaction is False` no entry pra capturar uso indevido cedo, em vez de pragma silenciosamente ignorado.
- **HG-02 + HG-03 — `current_phase_lock` consulta sentinela; retry reentrant** (`engine/memory/l1.py`, commit `65b8904`): HG-02 — `current_phase_lock` lia `status.json.phase_lock`, mas o sentinela `.phase-lock` é o gate autoritativo após C1/A1. Read agora consulta sentinela primeiro, `status.json` como espelho. HG-03 — branch reentrant de `acquire_phase_lock` lia sentinela exatamente uma vez; se o read race com o writer que ainda não fez fsync, retornava empty e a reentrância falhava. Retry curto com backoff quando sentinela existe mas vazio.

### Changed

- **Doc-sync claude-rules**: corrige smoke checklist execution — hooks PreToolUse/PostToolUse confirmados em subagent context via doc oficial + side-effect persistente; veredito anterior estava furado por capturar só stderr. Veredito final: 4/5 (Check #3 corrigido pra PASS via audit log; Check #2 permanece FAIL por entrega inconsistente do PostToolUse). Gap de observabilidade anotado em `docs/design/04-pending.md`.
- `_VALID_KINDS` do `engine/memory/distiller.py` ganha 6 entries reuse-related.
- `engine/graph/queries.py` Q11 (`find_reusable_helpers`) suporta multi-módulo
  shared via `LIKE 'shared:%'`.

### Refactored

- **TS arrow dedup hoisted to loop start** (`engine/graph/_ts_parser.py`, commit `9680ea8`): pure refactor, behavior unchanged. Duplicate check sentava após body extraction + hashing + tokenization — uma função same-named sombreada por arrow posterior pagava custo full só pra ser descartada. Mover dedup pro topo do loop pula trabalho desperdiçado. Test counts inalterados (31 tests em `tests/unit/test_graph_parsers.py` + `test_reuse_intelligence.py`).

### Tests

- **+38 regression tests** cobrindo os bloqueadores + review findings — `test_memory_l1_phase_lock_atomic.py` (multiprocessing race), `test_implement_lock_release.py` (exception paths), `test_builder_reset_tables.py` (mid-stream failure), `test_plan_deferred_exit_code.py` (rc=130 contract), `test_plan_deferred_state_persisted.py` (MD-02), `test_body_text_swift_triple_quote.py` (A5), `test_gradle_deps_regressions.py` (A6 + A9), `test_check_no_behavior_change_paths.py` (A12), entre outros.
- **Total: 458 tests passing** (vs baseline original v1.1.0 = 367; +91 incluindo as 38 do round bloqueadores + 36 integration do rules system + 17 reuse-intelligence extras).

### Conhecidos limites v1.1

- **Pre-existing**: `tests/integration/test_graph_build_meobonsai.py::test_build_full_creates_meta_schema_version` assertava `meta.schema_version == "1"`, mas `engine/utils/sqlite_io.py:20` declara `SCHEMA_VERSION = "2"` desde o bump da reuse-intelligence schema. Falha não bloqueia rapid lane nem o ship v1.1.0; fix pequeno (ler `sqlite_io.SCHEMA_VERSION` em vez de hardcoded) agendado pra v1.1.1.
- `kmp-migration-candidate` confidence é shallow (token Jaccard, não AST).
  False positives possíveis — apply NUNCA auto-runs; usuário revisa.
- Hook script `.claude/hooks/post-edit-detect-duplications.sh` é escrito
  no init, mas wiring em `.claude/settings.local.json` é manual (opt-in).
- Gradle dependency parsing cobre `implementation(project(...))` e
  variantes comuns. DSL Kotlin avançado ou `includeBuild` pode falhar.

[1.2.0]: https://github.com/thgMatajs/feature-forge/releases/tag/v1.2.0
[1.1.0]: https://github.com/thgMatajs/feature-forge/releases/tag/v1.1.0

## [1.0.0] — 2026-05-29

### Adicionado

#### Fase 1 — Schemas + filesystem (espinha dorsal)

- 9 schemas canônicos (`docs/schemas/{workflow-config, card, memory, graph, inventories, proposed-evolutions, rejected-evolutions, workflow-config-history, capability-labels}.md`)
- 27 decisões locked em `docs/design/01-decisions.md`
- 7 disciplinas universais em `docs/design/07-discipline.md`
- Filesystem layout canônico em `docs/design/05-filesystem-layout.md`

#### Fase 2 — Agents + UX roteiros (cérebros)

- 10 agent prompts: planning-conductor + 9 sub-agents (feature-intake, feature-prd, screen-analysis, contract-planner, tech-spec, task-contract-writer, readiness-reviewer, retrospective, memory-distiller)
- 7 roteiros UX cinemáticos (init, plan, implement, verify, doctor, reconfigure, evolve)
- ~7.000 LOC de markdown

#### Fase 3 — Templates + cards + preset (conteúdo)

- 16 templates canônicos (feature-intake, feature-prd, screen-analysis, bdd, ui-state-spec, navigation-spec, data-contract-spec, analytics-spec, test-strategy, tech-spec, task-breakdown, task-contract, implementation-readiness-review, plan-feature-handoff, evals)
- 12 cards canônicos iniciais (kotlin-language, kmp-shared, compose-screens, swiftui-screens, koin-annotations, skie-bridge, nav3, swiftui-navigation, firebase-auth, firebase-firestore (monolítico), firebase-storage, crashlytics)
- Preset `kmp-mobile-firebase` (depois substituído pelo `kmp-mobile` na 3.5)

#### Fase 3.5 — Refactor backend-agnostic + REST coverage

- Catálogo canônico de capability labels (40 labels v1: 16 singular + 3 latente + 14 auxiliar + 5 reservada)
- `firebase-firestore` monolítico ARQUIVADO; split em `firestore-persistence` + `firestore-realtime` + `firestore-security-rules`
- 6 cards REST novos: `ktor-client`, `rest-api-contract`, `kotlinx-serialization-json`, `room-database`, `datastore-prefs`, `auth-jwt-bearer`
- Preset `kmp-mobile-firebase` ARQUIVADO; substituído por `kmp-mobile` base + 4 backend-candidates (firebase-stack / rest-stack / hybrid / local-only)
- 3 templates refatorados pra agnóstico (`data-contract-spec`, `tech-spec`, `test-strategy`)
- 29 FOLLOWUPs herdados fechados em rodada paralela de 4 sub-agents

#### Fase 4 — Python engine + Bash dispatcher (músculos)

- `bin/forge` Bash dispatcher
- Foundation: `engine/cli.py` + `engine/utils/` + `engine/ui/` + `engine/persona/`
- State: `engine/cards/` + `engine/memory/` + `engine/graph/` + `engine/inventory/`
- Integration: `engine/mcp/` + `engine/vision/`
- 13 commands handlers: init, plan, implement, verify, status, doctor, reconfigure, evolve, undo, graph_cli, memory_cli, raw, ingest
- 57 arquivos Python · ~12.880 LOC

#### Fase 5 — Hooks + validators + tests (pele e validação)

- 9 hooks (5 Claude Code + 3 git wrappers + 1 GitHub Actions workflow)
- 13 validators Python (+2 helpers) com 3-caminhos discipline + JSON tail-on-stdout contract
- Suite pytest: 266 tests (unit + integration + 13 commands smoke + validators)
- Hooks instalação automática no `forge init`

### Mudado

- **Cleanup pós-review crítico** (47 fixes em 6 sub-agents paralelos):
  - Schema drift triplo (memory.l2 key alignment + backend block real + MEM-L1-VL warn)
  - Decision 27 (Ctrl+C pause) honrada de verdade em init.py
  - Phase lock auto-release em plan + implement
  - `apply_proposal_to_l2` raise NotImplementedError nos fall-through (não mais silent drop)
  - `_handle_pre_commit` deriva slug da branch/L1 (gates voltam a bloquear)
  - CI workflow instala forge de verdade
  - Performance: `blast_radius` 250 queries → 1 (~50× speedup), `_persist_*` executemany (3-5×), walk cache compartilhado
  - JUnit5 false positive fix
  - Path traversal block em `normalize_screenshot_path`
  - BOM UTF-8 tolerância em card.yaml
  - Setext + ATX heading mix em merger
  - 13 smoke tests novos pros commands handlers

### Removido

- Preset `kmp-mobile-firebase` (movido pra `presets/.archived/kmp-mobile-firebase-pre-3.5/`)
- Card `firebase-firestore` monolítico (movido pra `cards/.archived/firebase-firestore-monolithic/`)
- Capability labels `realtime-data`, `auth-server` (renomeadas/splitadas)

### Conhecidos limites v1

Ver `docs/design/08-session-handoff.md § Conhecidos limites v1`:

- `forge implement` é stub manual (Apply Mode automatizado em Phase 6)
- `forge init` Cena 7 (Jira/ticketing) não prompted
- 9 kinds de `apply_proposal_to_l2` raise NotImplementedError
- LLM hookup real é Phase 6
- Tree-sitter / AST: regex parsers v1 por design

[1.0.0]: https://github.com/thgMatajs/feature-forge/releases/tag/v1.0.0
