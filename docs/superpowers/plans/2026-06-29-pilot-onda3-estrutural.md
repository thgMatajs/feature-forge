# Plano — Onda 3: P0s estruturais restantes

> **Plano executável**, derivado de `superpowers:writing-plans`.
> **Spec upstream:** `docs/superpowers/specs/2026-06-29-pilot-remediation-design.md` §"Onda 3".
> **Report-mãe:** `docs/reports/2026-06-25-piloto-meobonsai-gaps.md` §Tema 5 + BUG-5/BUG-2/BUG-PLAN-1.
> **Catálogo:** `docs/design/04-pending.md` §"Piloto MeoBonsai 2026-06-25 — gaps" (P0).
> **Branch:** `docs/pilot-remediation`.
> **Voz:** mentor calmo. **Status:** pré-implementação (aguarda plan-auditor antes do handoff).
> **Data:** 2026-06-29.

---

## Objetivo

Desbloquear o **primeiro contato** (perf do `forge init`) e tirar o **crash** do
gate de readiness do `forge plan`. Três P0 estruturais, independentes entre si:

1. **BUG-5** — extrair UM helper compartilhado `_walk_recursive_pruned` (poda
   `_SKIP_DIRS` na descida) e trocar os rglob crus do hot-path de inventory +
   detection + needle-count. Reuso-first: o helper já existe na branch
   `fix/pilot-init-perf` (commit `003d72e`) — cherry-pick, não reimplementa.
2. **BUG-2** — cachear o resultado de discovery no checkpoint do init e reusá-lo
   quando há response pendente (loop mecânico). Hoje discovery re-roda integral
   (~220s) a cada invocação.
3. **BUG-PLAN-1** — o path A do gate de readiness do `_run_wave_e` recursa
   síncrono (`return _run_wave_e(...)`) → RecursionError quando o verdict não
   muda. Fix: re-renderizar + PAUSAR (deferred), nunca recursar.

**Por que estes três juntos numa onda:** são os P0 que o mem **não** toca e que
não são correctness-de-gate (Onda 1) nem gates-com-dentes (Onda 2). Compartilham
o tema "estrutural": perf de varredura, perf de cache, e controle de fluxo de um
gate. Cada um é uma task discreta com TDD próprio.

**Fora do escopo (não confundir com regressão a evitar):** os fechados em main
(BUG-1 via filtro inline `_eval.py:72`, BUG-A, BUG-IMPL-1, BUG-MEM) — tocá-los é
regressão, não trabalho. A decisão de housekeeping (mergear-ou-descartar a branch
`fix/pilot-init-perf`) está no §"Riscos & decisões em aberto" — não é code-work
desta onda.

---

## Estado do código (scout read-only verificado 2026-06-29)

Registrado aqui pra o executor **não re-explorar**. Tudo confirmado por leitura
direta em `main` + `git show` da branch.

### O helper na branch (reuso-first — fonte do cherry-pick)

- `fix/pilot-init-perf` (commit `003d72e`, consolidado em `4649d78`) adiciona
  `_walk_recursive_pruned(project_root: Path, pattern: str) -> Iterator[Path]`
  em `engine/detection/_eval.py` (logo acima de `_glob_any`).
- **Assinatura e contrato** (do `git show 003d72e`): walk manual com `stack`,
  `iterdir()`, poda na descida (`if entry.name in _SKIP_DIRS: continue`), NÃO
  segue symlinks de diretório, yield de dirs E arquivos (igual `rglob`).
  `pattern == ""` (vinda de `"**/"`) replica `rglob("")` (yield TODOS os
  descendants — `Path.match("")` levantaria ValueError, então é tratado à parte).
  Contrato declarado **no-behavior-change**: o conjunto yielded é idêntico ao de
  `rglob(pattern)` filtrado por skip-dirs.
- Na branch, o helper é consumido SÓ por `_glob_any` (substitui
  `project_root.rglob(pattern)` na L72). **Em `main` o helper NÃO existe** — o
  `_glob_any` de main usa `project_root.rglob(pattern)` cru (`_eval.py:72`) +
  filtro `_SKIP_DIRS` relativo DEPOIS de enumerar (L80-85). Ou seja: main fechou
  BUG-1 por OUTRO caminho (cap de 800 + filtro pós), mas o anti-padrão "materializa
  antes de podar" PERSISTE no `_glob_any` e em todos os sites de inventory.

> **Nuance de cherry-pick:** o commit `003d72e` também edita `_glob_any` pra
> consumir o helper. Em main o `_glob_any` divergiu (ganhou o cap de 800 + filtro
> relativo). Portanto **NÃO** faça `git cherry-pick 003d72e` cego — ele vai
> conflitar no corpo de `_glob_any`. Extraia APENAS a função `_walk_recursive_pruned`
> (copiá-la verbatim do `git show 003d72e`) e re-wire os callers à mão,
> preservando o cap/filtro relativo que main já tem.

### Sites de rglob cru no hot-path (footprint exato — grep verificado)

`engine/detection/_eval.py`:
- L72 — `_glob_any`: `project_root.rglob(pattern)` (caminho `**/`). Tem cap de
  800 (L86) + filtro relativo (L80-85).

`engine/inventory/design_system.py` (todos `rglob(<filename>)` cru, filtrados por
`_should_skip` DEPOIS):
- L444 — `Spacing.kt` / `Spacing.swift`
- L446-448 — `CornerRadius.kt` / `BorderRadius.kt` / `Radius.swift`
- L451-453 — `MeoBonsaiColors.kt` / `Colors.kt` / `Color.kt`
- L455 — `*Typography.kt` / `FontFamilies.kt`
- L485 — `index.css` / `globals.css`

`engine/inventory/conventions.py` (todos `rglob(*<pattern>)`):
- L308 — `*Screen.kt`
- L313 — `*Content.kt`
- L323 — `*ScreenView.swift`
- L328 — `*ScreenContentView.swift`
- L338 — `*ViewModel.kt`

`engine/inventory/i18n.py`:
- L101 — `path.rglob("*.json")` em `_detect_source_of_truth` (varre cada SOT
  candidate inteiro). **Hot-path real.**
- L110 — `sot.rglob("*.json")` em `_collect_locale_files`. Opera sob `sot` (já
  reduzido), mas `sot` pode ser grande; é a SEGUNDA varredura do mesmo dir.
- L154 — `project_root.rglob("locales")` (busca diretórios `locales`). Cru,
  filtrado por `_should_skip` no L156.

`engine/init.py`:
- L317 — `_count_needle_hits`: `project_root.rglob(pattern)` num loop sobre
  4 patterns (`*.kt`, `build.gradle`, `build.gradle.kts`, `settings.gradle*`),
  filtro `_SKIP_DIRS` + `startswith(".")` DEPOIS (L334). Chamado em loop sobre
  `_ORPHAN_HEURISTICS` em `_check_orphan_signals` (L289) — **hot-path do Step 7.5**.

`engine/inventory/_walk_cache.py`:
- L60 — `walk_project`: `root.rglob("*")` cru + filtro `_SKIP_DIRS` relativo (L68)
  DEPOIS. JÁ é LRU-cacheado (`@lru_cache(maxsize=32)`), MAS a PRIMEIRA varredura
  ainda materializa tudo antes de podar. É o walk principal dos 3 extractors
  (design_system L129, conventions L104, i18n L141/L148).

> **Importante (não-overreach):** os 3 extractors já usam `walk_project` (cache)
> para o walk por-extensão. Os rglob crus listados acima são walks ADICIONAIS,
> por-filename/por-pattern, que NÃO passam pelo cache. Não há duplicação a
> "consolidar" entre walk_project e os rglob por-filename — são propósitos
> diferentes (um pega TODOS os .kt; o outro busca UM filename). O fix é trocar o
> `rglob` cru pelo `_walk_recursive_pruned` em cada site, não unificar tudo num
> walk só.

### Fragmentação de `_SKIP_DIRS` (4 definições independentes)

- `engine/detection/_eval.py:48` — `_SKIP_DIRS` (set). Importado por `init.py:59`.
- `engine/inventory/_walk_cache.py:17` — `_SKIP_DIRS` (frozenset, **o mais
  completo**: adiciona `target`, `vendor`, `worktrees`, `.vscode`, `.turbo`,
  `.pytest_cache`).
- `engine/inventory/design_system.py:42` — `_SKIP_DIR_PARTS`.
- `engine/inventory/conventions.py:26` — `_SKIP_DIR_PARTS`.
- `engine/inventory/i18n.py:44` — `_SKIP_DIR_PARTS`.

> **Decisão de escopo (consolidação de `_SKIP_DIRS`):** o `_walk_recursive_pruned`
> precisa de UM set de skip-dirs pra podar na descida. Para preservar o contrato
> no-behavior-change **por site**, o helper deve podar usando o MESMO set que o
> filtro pós-enumeração de cada site usava — senão muda o comportamento. A forma
> mais limpa e segura: o helper aceita o `skip_dirs` como **parâmetro**
> (`_walk_recursive_pruned(root, pattern, skip_dirs)`), e cada site passa o seu
> set atual. Isso evita o risco de unificar 4 sets divergentes num só (que mudaria
> o que cada extractor pula). Consolidar os 4 sets num módulo compartilhado é
> trabalho de reuse legítimo, MAS é uma 2ª dimensão — só faça se o plan-auditor /
> review pedir, e nunca à custa do no-behavior-change. Default desta onda:
> **parametrizar `skip_dirs`, não unificar os sets.**

### Discovery + checkpoint no init (BUG-2)

- Step 2 (discovery) roda em `engine/init.py:2059-2115`: `load_all_cards`,
  `extract_design_system`, `extract_i18n`, `extract_conventions` dentro de um
  `ui_progress.progress` block.
- O comentário L2146-2147 é explícito: *"Discovery (Step 2) re-roda sempre — é
  idempotente e produz os canonical_cards que o pipeline usa."* — esse é o bug.
- O checkpoint (`_InitCheckpoint`, `_save_checkpoint` L174) salva
  `step/preset/selected-card-names/backend-cells/intent-id` — **NÃO** o resultado
  caro de discovery (`ds_inv`/`i18n_inv`/`conv_inv`).
- O loop mecânico já tem o discriminador certo: `_host_loop_in_progress`
  (L1990) — quando há response pendente, o init "sigo o pipeline sem reabrir o
  prompt de resume". É exatamente o ponto onde discovery deveria carregar o cache
  em vez de re-rodar.
- Os resultados de discovery são consumidos adiante: `ds_inv`/`i18n_inv`/`conv_inv`
  alimentam `_build_conventions` (L2857), `_build_workflow_config` (L2784), e o
  summary final (L2754-2755). Qualquer cache precisa reproduzi-los fielmente.

### Gate de readiness no plan (BUG-PLAN-1)

- `engine/plan.py::_run_wave_e` (L980). O path A está em L1056-1059:
  ```
  if chosen == "a":
      renderer.write("Re-rodando Wave E após você ajustar os artefatos...")
      append_history(slug, project_root, {"event": "wave-e-rerun-requested"})
      return _run_wave_e(slug, project_root, feature_path)   # ← RECURSÃO SÍNCRONA
  ```
  Se o host responde `a` mas o verdict continua `partial` (não ajustou), recursa
  infinito (~979 níveis → RecursionError, exit 1, ~1.3MB stdout). O history
  acumula `wave-e-rerun-requested` em cada nível.
- **Contrato de pausa canônico do plan** (verificado): os IRMÃOS deste gate
  (wave-d pausa L952-953, wave-e pausa L1006-1007, b/c do próprio gate L1062-1063)
  usam `_persist_deferred(...)` + `return WaveResult(deferred=True)`. O caller
  `_run_waves_for_subtype` (L1846-1851) mapeia `result.deferred` → **exit 130**
  (pausa), conforme o docstring de `run()` (L1858: "0=ok, 130=paused, other=hard").
  Teste de contrato existente: `tests/unit/test_plan_deferred_exit_code.py`.
- **Atenção à divergência spec↔código sobre o exit code:** a spec e o report
  dizem "PAUSAR (exit 2)". No CÓDIGO REAL, o caminho `deferred=True` resulta em
  **130**, não 2 — o exit 2 é reservado para `PausedForInputError` (intent loop,
  via `cli.main`). O caminho coerente com os três irmãos deste mesmo gate é
  `_persist_deferred` → `deferred=True` → 130. **Não inventar exit 2** onde o
  resto do gate usa 130 — seria divergir do contrato testado. O TDD desta task
  asserta "NÃO RecursionError + defere limpo (sem recursar)"; o exit-code-exato
  segue o contrato canônico (130), não a prosa da spec.
- `_persist_deferred` (L794): marca status `deferred`, libera `phase_lock`, emite
  pause copy. `mentor_calmo.three_paths_block` + `question.ask_three_paths` já
  estão montados no gate (L1023-1055) — a re-renderização das waves apontadas
  como gap pode reusar `_render_template` (mesmo mecanismo das waves).

---

## Reuso-first (Mandamento #3 — antes de criar)

- **UM helper, cherry-pick da branch.** `_walk_recursive_pruned` já existe em
  `fix/pilot-init-perf` (`git show 003d72e`). Copiar verbatim a FUNÇÃO; **não**
  re-derivar, **não** `git cherry-pick` o commit inteiro (conflita no `_glob_any`).
  Parametrizar `skip_dirs` (ver §scout) pra preservar no-behavior-change por site.
- **NÃO** criar um 2º walk helper. Todos os sites de rglob cru passam pelo mesmo
  `_walk_recursive_pruned`. O `walk_project` (cache) PODE também consumir o helper
  internamente (troca o `root.rglob("*")` L60 por `_walk_recursive_pruned(root, "")`),
  fechando o último site cru — fazê-lo no mesmo PR é coerente (UM helper em todos).
- **NÃO** unificar os 4 `_SKIP_DIRS` divergentes nesta onda (risco de
  no-behavior-change) — parametrizar. Consolidação é 2ª dimensão opcional.
- **Discovery cache** reusa o mecanismo de checkpoint existente
  (`checkpoint_io` / `_save_checkpoint`) — não inventar um cache paralelo.
- **Gate de readiness** reusa `_persist_deferred` + `WaveResult(deferred=True)` +
  `_render_template` — todos já no arquivo. Não criar novo mecanismo de pausa.

---

## Tasks

### Task 1 — BUG-5: helper `_walk_recursive_pruned` compartilhado + troca dos sites

**Objetivo:** eliminar o anti-padrão "rglob cru materializa antes de podar" no
hot-path do init, extraindo UM helper (cherry-pick da branch) que poda
`_SKIP_DIRS` na descida, e re-wirar todos os sites de rglob cru a ele.

**Bug:** BUG-5 (Alto, Tema 5) — `engine/inventory/design_system.py:444` etc.,
`conventions.py:308` etc., `i18n.py:101`, `init.py:317`, `_eval.py:72`,
`_walk_cache.py:60`.

**ARQUIVOS PERMITIDOS PARA EDIT (whitelist):**
- `engine/detection/_eval.py` (adiciona `_walk_recursive_pruned` + re-wire `_glob_any`)
- `engine/inventory/design_system.py` (troca rglob → helper nos sites)
- `engine/inventory/conventions.py` (idem)
- `engine/inventory/i18n.py` (idem)
- `engine/inventory/_walk_cache.py` (troca `root.rglob("*")` → helper)
- `engine/init.py` (troca rglob de `_count_needle_hits`)
- `tests/unit/test_walk_recursive_pruned.py` (NOVO — teste do helper)
- `tests/unit/test_init_count_needle_hits_skip_dirs.py` (estender — já existe)
- `CHANGELOG.md` (Unreleased — doc-sync, Mandamento #6)

**ARQUIVOS PARA LER (contexto, read-only):**
- `git show 003d72e -- engine/detection/_eval.py` (a fonte do helper)
- `engine/inventory/_walk_cache.py` (o `_SKIP_DIRS` mais completo, referência)
- `tests/unit/test_init_count_needle_hits_skip_dirs.py` (estilo dos testes de skip)
- `tests/unit/test__walk_cache_worktree.py` (cobre o caso worktree/`.claude/`)

**TDD (teste VERMELHO concreto — escrever ANTES do fix):**
1. `test_walk_recursive_pruned.py` novo:
   - `test_pruned_walk_equals_rglob_filtered` — num tmp tree com `node_modules/`,
     `.gradle/`, `build/` + arquivos legítimos, o conjunto de paths de
     `_walk_recursive_pruned(root, "*.kt", skip)` é IDÊNTICO ao de
     `[p for p in root.rglob("*.kt") if not any(part in skip for part in p.relative_to(root).parts)]`
     (contrato no-behavior-change — RED antes do helper existir: ImportError).
   - `test_pruned_walk_does_not_descend_skip_dirs` — semear um arquivo dentro de
     `node_modules/deep/x.kt`; asserta que NÃO aparece no resultado.
   - `test_pruned_walk_empty_pattern_yields_all` — `pattern=""` yield TODOS os
     descendants (paridade com `rglob("")`), sem ValueError.
   - `test_pruned_walk_does_not_follow_dir_symlinks` — symlink de dir não é
     descido (evita ciclo).
2. Estender `test_init_count_needle_hits_skip_dirs.py`: os testes existentes
   (node_modules/build/Pods → 0 hits) DEVEM seguir verdes após a troca para o
   helper (regressão no-behavior-change). Adicionar um caso de profundidade
   (`node_modules/a/b/c/x.kt`) que comprove a poda na descida.
3. **Grep gate** (no §gate de aceite): `grep -nE 'rglob' engine/inventory/ engine/detection/_eval.py engine/init.py | grep -v '^#'` retorna 0 rglob CRU no hot-path (todos os matches restantes, se houver, devem estar dentro de `_walk_recursive_pruned` ou comentários). Filtrar comentários: `grep -vE '^\s*#'`.

**Critério de sucesso:**
- `.venv/bin/pytest tests/unit/test_walk_recursive_pruned.py tests/unit/test_init_count_needle_hits_skip_dirs.py tests/unit/test__walk_cache_worktree.py tests/unit/test_init_orphan_signals.py -q` verde.
- Lane rápida completa verde: `.venv/bin/pytest -m "not integration and not e2e" -q`.
- Grep confirma: 0 rglob cru fora de `_walk_recursive_pruned` nos 6 arquivos do
  hot-path (os sites listados no scout viram chamadas ao helper).
- `_walk_recursive_pruned` é a ÚNICA fonte (grep `_walk_recursive_pruned` mostra
  1 def + N callers; nenhum 2º helper de walk criado).
- No-behavior-change: nenhum teste de inventory/detection/init pré-existente
  regride (counts iguais; o cap de 800 do `_glob_any` preservado).

**Reuso-first:** copiar a função da branch (`git show 003d72e`), parametrizar
`skip_dirs`, re-wirar à mão. Não cherry-pick cego (conflita no `_glob_any`).

**Anti-padrões / escopo:**
- NÃO unificar os 4 `_SKIP_DIRS` divergentes (parametrizar `skip_dirs` por site).
- NÃO mudar o cap de 800 nem o filtro relativo de `_glob_any` (preserva BUG-1 fix
  de main — regressão a evitar).
- NÃO tocar os parsers do graph (`engine/graph/builder.py` já usa `scandir` —
  fora do escopo, fechado em E-N-001).
- NÃO "aproveitar" pra refatorar os extractors além da troca do walk.

---

### Task 2 — BUG-2: cachear discovery no checkpoint do init

**Objetivo:** parar de re-pagar os ~220s de discovery a cada invocação do init.
Cachear o resultado de discovery (ds_inv/i18n_inv/conv_inv + canonical_cards) e
reusá-lo no loop mecânico (response pendente), em vez de re-rodar Step 2.

**Bug:** BUG-2 (Alto → Crítico-UX, Tema 5) — `engine/init.py:190` / Step 2
(L2059-2115); re-discovery integral toda invocação (~18 min em 5 ciclos).

**ARQUIVOS PERMITIDOS PARA EDIT (whitelist):**
- `engine/init.py` (cache de discovery no checkpoint + load no loop mecânico)
- `engine/utils/checkpoint_io.py` (SOMENTE se o cache precisar de helper de
  serialização novo — preferir reusar o existente; justificar no commit se tocar)
- `tests/unit/test_engine_init_resume.py` (estender — já cobre resume)
- `tests/unit/test_init_discovery_cache.py` (NOVO, se o resume test não couber)
- `CHANGELOG.md` (Unreleased — doc-sync)

**ARQUIVOS PARA LER (contexto, read-only):**
- `engine/init.py` L174-217 (`_save_checkpoint`/`_load_checkpoint`), L1990-2062
  (loop mecânico + Step 2), L2745-2776 (consumo de ds_inv/i18n_inv no summary).
- `engine/utils/checkpoint_io.py` (helpers de save/load YAML de checkpoint).
- `engine/inventory/design_system.py` / `i18n.py` / `conventions.py` (a SHAPE
  dos objetos `DSTokens`/inventories que precisam round-tripar no cache).

**Decisão de design a confirmar no scout do executor (NÃO assumir cego):**
os inventories (`ds_inv`/`i18n_inv`/`conv_inv`) são dataclasses ricas. Duas
estratégias possíveis — o executor escolhe a de menor risco, documentando no
commit body (3-caminhos se ambíguo):
- **(A) Cache em arquivo derivado** (`.claude/.init-discovery-cache.yaml` ou
  similar, gitignored): serializa o resultado de discovery; o loop mecânico
  carrega em vez de re-rodar. Mais simples se as dataclasses já têm `asdict`.
- **(B) Cache em memória via LRU** já existe parcialmente (`walk_project` é
  LRU, `_load_toml_catalog` é LRU) — MAS cada invocação do init é um PROCESSO
  NOVO (CLI), então LRU intra-processo NÃO ajuda no loop mecânico file-based.
  Portanto **(A) é a única que fecha o BUG-2 real** (cada response = nova
  invocação). Registrar isto: o cache TEM que ser persistente em disco.
- Invalidação: o cache deve ser limpo junto do checkpoint (`_clear_checkpoint`
  já roda no fim, L2750) — discovery cache segue o lifecycle do checkpoint.

**TDD (teste VERMELHO concreto — escrever ANTES do fix):**
1. `test_init_discovery_not_recomputed_on_mechanical_reinvoke` — montar um init
   com checkpoint salvo + response pendente (`_host_loop_in_progress` True via
   o mesmo setup de `test_engine_init_resume.py`); espionar
   `extract_design_system` / `extract_i18n` / `extract_conventions` (monkeypatch
   contador). Primeira invocação: contador == 1 cada. Re-invoke mecânico:
   contador NÃO incrementa (carrega do cache). RED antes do fix: o contador
   incrementa em toda invocação.
2. `test_discovery_cache_roundtrips_inventories` — o cache carregado produz
   ds_inv/i18n_inv/conv_inv equivalentes ao discovery direto (mesmo n_components,
   mesmas keys i18n, mesma folder-layout) — garante que o summary/config final
   não muda por usar o cache.
3. `test_discovery_cache_cleared_with_checkpoint` — após `_clear_checkpoint`, o
   cache de discovery some (não vaza estado stale entre features).

**Critério de sucesso:**
- `.venv/bin/pytest tests/unit/test_engine_init_resume.py tests/unit/test_init_discovery_cache.py -q` verde.
- Lane rápida completa verde.
- Observável: re-invoke mecânico do init NÃO chama os 3 extractors de novo
  (contador estável) — o passo de discovery cai de re-execução para load do cache.
- O resultado final (forge-config.yaml, summary) é IDÊNTICO com e sem cache
  (no-behavior-change no OUTPUT; só o custo muda).

**Reuso-first:** reusar `checkpoint_io` / `_save_checkpoint` / `_clear_checkpoint`.
Não inventar um sistema de cache paralelo nem um diretório novo de estado fora
do `.claude/` já gitignored.

**Anti-padrões / escopo:**
- NÃO tentar cache LRU intra-processo (não fecha o BUG-2 file-based — ver §design).
- NÃO cachear discovery numa invocação humana fresh que ESCOLHEU `discard` — o
  discard recomeça do zero (cache deve ser invalidado no discard).
- NÃO expandir o que é cacheado além do resultado de discovery (não cachear
  backend_cells / card selection — esses já têm tratamento próprio no checkpoint).
- NÃO tocar a lógica de resume humano (3-caminhos resume/discard/abort) — só o
  ramo `_host_loop_in_progress` (loop mecânico) ganha o load do cache.

---

### Task 3 — BUG-PLAN-1: gate de readiness re-renderiza + PAUSA (sem recursar)

**Objetivo:** tirar o crash de RecursionError do path A do gate de readiness.
Em vez de recursar síncrono, re-renderizar as waves apontadas como gap e PAUSAR
(deferred), deixando o host ajustar e re-invocar pelo loop canônico.

**Bug:** BUG-PLAN-1 (Alto/Crítico, Tema 1) — `engine/plan.py:1059`
(`return _run_wave_e(...)` recursivo no path A).

**ARQUIVOS PERMITIDOS PARA EDIT (whitelist):**
- `engine/plan.py` (substituir a recursão do path A por re-render + deferred)
- `tests/unit/test_plan_deferred_exit_code.py` (estender — contrato de pausa)
- `tests/unit/test_plan_readiness_no_recursion.py` (NOVO — regressão do crash)
- `CHANGELOG.md` (Unreleased — doc-sync)

**ARQUIVOS PARA LER (contexto, read-only):**
- `engine/plan.py` L980-1063 (`_run_wave_e` inteiro), L785-819 (`_continue_or_pause`
  + `_persist_deferred`), L1838-1852 (caller `_run_waves_for_subtype` → exit 130).
- `tests/unit/test_plan_deferred_exit_code.py` (contrato 130 + persist deferred).
- `tests/unit/test_engine_plan_resume.py` (como o resume re-entra no wave).

**TDD (teste VERMELHO concreto — escrever ANTES do fix):**
1. `test_plan_readiness_path_a_does_not_recurse` — montar `_run_wave_e` com:
   `_continue_or_pause` → `"continuar"`; `_parse_readiness_status` → `"partial"`
   (verdict NÃO muda entre chamadas); `question.ask_three_paths` → `"a"`
   (re-revisar agora). **RED antes do fix:** isto recursa infinito →
   RecursionError. **GREEN após:** a chamada RETORNA `WaveResult(deferred=True)`
   sem recursar (asserta via contador de chamadas de `_render_template` ou de
   `_run_wave_e` ≤ 1, e/ou `pytest.raises` que NÃO captura RecursionError).
   Dica de implementação do teste: monkeypatch dos helpers + asserção de que
   `_run_wave_e` não é re-entrado (spy de chamada).
2. `test_plan_readiness_path_a_persists_deferred` — após o path A com verdict
   ainda `partial`, o status L1 é `deferred`, `phase_lock` é None, e o history
   registra um evento de re-render-then-pause (não 979× `wave-e-rerun-requested`).
3. `test_plan_readiness_path_a_returns_130_via_caller` — via
   `_run_waves_for_subtype` (como o teste de contrato existente), o path A
   resulta em exit **130** (pausa canônica do plan), não exit 1 nem crash.

**Critério de sucesso:**
- `.venv/bin/pytest tests/unit/test_plan_readiness_no_recursion.py tests/unit/test_plan_deferred_exit_code.py tests/unit/test_engine_plan_resume.py -q` verde.
- Lane rápida completa verde.
- Observável: responder `a` em `readiness=partial` (verdict imutável)
  re-renderiza as waves apontadas + PAUSA (deferred → 130), **nunca**
  RecursionError, **nunca** ~1.3MB de stdout, **nunca** acúmulo de N
  `wave-e-rerun-requested` no history.
- O path A ainda re-renderiza (o host pediu "re-revisar agora") — a re-renderização
  acontece UMA vez, depois pausa pro host ajustar e re-invocar.

**Reuso-first:** reusar `_persist_deferred` + `WaveResult(deferred=True)` (mesmo
contrato dos irmãos b/c do gate e das pausas de wave-d/wave-e). Reusar
`_render_template` pra re-renderizar. Não criar mecanismo de pausa novo.

**Anti-padrões / escopo:**
- NÃO inventar exit 2 — o contrato canônico do plan é 130 pra deferred (a prosa
  da spec diz "exit 2", mas o código + teste existente fixam 130). Seguir o código.
- NÃO transformar o path A num loop `while` síncrono (re-perguntar até verdict
  mudar) — isso só troca RecursionError por loop infinito interativo. O fix é
  re-render UMA vez + pausa; o host re-invoca pelo loop canônico.
- NÃO mexer no `ready-with-blocks` (gate binário) — é item de design fora desta
  onda (a spec lista como observação do report, não como gate de aceite da O3).
- NÃO tocar os outros waves (A/B/C/D) nem o gate binário de verdict.

---

## Verificação (gate de aceite da onda inteira)

Antes de declarar a onda pronta (Mandamento #2 — verde antes de pronto):

- `.venv/bin/pytest -m "not integration and not e2e" -q | tail -1` — lane rápida
  verde, count não regride sem justificativa no commit body.
- `.venv/bin/pytest -q | tail -1` — lane completa verde.
- `forge verify` sem hard fail.
- **BUG-5:** `grep -nE 'rglob' engine/inventory/ engine/detection/_eval.py engine/init.py | grep -vE '^\s*#'` — 0 rglob cru no hot-path fora de `_walk_recursive_pruned`.
- **BUG-2:** re-invoke mecânico do init não re-paga discovery (contador de
  extractors estável no teste; passo de discovery vira load de cache).
- **BUG-PLAN-1:** `a` em readiness=partial → exit 130 (deferred), NÃO RecursionError.
- Reviewer (`gsd-code-reviewer`, zero-tolerância) assinou off (sem high/critical).
- Doc-sync no MESMO commit: `CHANGELOG.md` Unreleased + mover BUG-5/BUG-2/BUG-PLAN-1
  de ABERTO → fechado em `docs/design/04-pending.md`.

---

## FOOTPRINT preciso

**Arquivos de produção tocados (7):**
- `engine/detection/_eval.py` — Task 1 (helper + re-wire `_glob_any`)
- `engine/inventory/design_system.py` — Task 1 (5 sites de rglob)
- `engine/inventory/conventions.py` — Task 1 (5 sites de rglob)
- `engine/inventory/i18n.py` — Task 1 (3 sites de rglob)
- `engine/inventory/_walk_cache.py` — Task 1 (1 site, `walk_project`)
- `engine/init.py` — Task 1 (`_count_needle_hits`) **+ Task 2** (discovery cache)
- `engine/plan.py` — Task 3 (gate de readiness path A)
- (condicional) `engine/utils/checkpoint_io.py` — Task 2, só se precisar helper novo.

**Arquivos de teste tocados/criados (6):**
- `tests/unit/test_walk_recursive_pruned.py` (NOVO — Task 1)
- `tests/unit/test_init_count_needle_hits_skip_dirs.py` (estender — Task 1)
- `tests/unit/test_engine_init_resume.py` (estender — Task 2)
- `tests/unit/test_init_discovery_cache.py` (NOVO — Task 2, se necessário)
- `tests/unit/test_plan_readiness_no_recursion.py` (NOVO — Task 3)
- `tests/unit/test_plan_deferred_exit_code.py` (estender — Task 3)

**Doc-sync (2):** `CHANGELOG.md`, `docs/design/04-pending.md`.

---

## Pontos de conflito de merge com Onda 2 e Onda 4

A Onda 3 executa DEPOIS que O2 e O4 mergearem (planejamento agora é read-only,
seguro). Pontos onde o estado pode ter mudado:

- **`engine/plan.py` — COMPARTILHADO com a Onda 2** (gates com dentes /
  content-check nas waves). A Onda 2 mexe nos GATES DE CONTEÚDO das waves; a
  Onda 3 mexe só no PATH A do `_run_wave_e` (control-flow do readiness). São
  regiões distintas do arquivo (O2 ~content-check de wave; O3 ~L1056-1059), MAS:
  - Se O2 refatorou `_run_wave_e` ou introduziu um content-check ANTES do gate de
    readiness, a região L1056-1059 pode ter deslocado. **Re-confirmar o número de
    linha do `return _run_wave_e(...)` recursivo antes do fix** (grep
    `return _run_wave_e` em `engine/plan.py`).
  - Se O2 mudou a assinatura de `WaveResult` ou `_persist_deferred`, a Task 3
    precisa alinhar (o fix reusa ambos). Re-ler L794-828 pós-O2.
  - **Risco de conflito textual:** MÉDIO se O2 tocou `_run_wave_e`; BAIXO se O2
    ficou nos waves A-D / content-check separado.

- **`engine/init.py` — COMPARTILHADO com a Onda 4** (BUG-B version-lock path +
  BUG-STATUS reconciliação não tocam init, mas BUG-4/MEM-5 `.gitignore` é semeado
  pelo init; BUG-IMPL-2 build commands derivam de gradlew — pode tocar discovery).
  - A Task 2 (discovery cache) mexe no Step 2 (L2059-2115) e no loop mecânico
    (L1990-2062). A Onda 4, se semear `.gitignore` no init, mexe em OUTRO step
    (provavelmente Step 14/15, perto do `_clear_checkpoint`). **Risco BAIXO** de
    overlap textual, mas **ATENÇÃO**: se a O4 adicionar entradas ao `.gitignore`,
    o discovery cache de Task 2 (se for arquivo derivado em `.claude/`) DEVE ser
    coberto por essa `.gitignore` — coordenar o nome do arquivo de cache com a
    lista que a O4 semeia (evitar que o cache vaze no `git status`). Registrar o
    nome do arquivo de cache no commit pra a O4 (ou esta onda) cobri-lo.
  - A Task 1 toca `_count_needle_hits` em init.py — região L317, isolada. **Risco
    BAIXO** de conflito com O4.
  - **Risco de conflito textual:** BAIXO (steps diferentes), mas há um
    acoplamento SEMÂNTICO no `.gitignore` (o cache derivado precisa estar lá).

- **`CHANGELOG.md` e `docs/design/04-pending.md` — COMPARTILHADOS com O1/O2/O4.**
  Todos os planos fazem doc-sync nesses dois. **Conflito textual quase certo** no
  CHANGELOG (mesma seção Unreleased) e no 04-pending (mesma seção de gaps). É
  conflito trivial de append — resolver mantendo as entradas de todas as ondas.
  Recomendação: a O3 faz seu doc-sync por ÚLTIMO no rebase, appendando após O1/O2/O4.

---

## Riscos & decisões em aberto

- **No-behavior-change do helper (Task 1) é o risco central.** Trocar rglob por
  walk-manual com poda na descida DEVE produzir o conjunto idêntico. O TDD
  `test_pruned_walk_equals_rglob_filtered` é o guard. Risco residual: ordem de
  iteração (rglob vs iterdir-stack) — se algum site DEPENDE da ordem (ex.: pega o
  PRIMEIRO match), parametrizar/sortear pra preservar determinismo. O `_glob_any`
  retorna no primeiro hit (ordem importa só pro short-circuit, não pro resultado
  booleano); os extractors de design_system fazem `break` no primeiro token
  encontrado — **verificar se a ordem de descoberta muda qual token ganha** (ex.:
  `Spacing.kt` em dois módulos). Se sim, ordenar o resultado do helper.
- **Strategy do discovery cache (Task 2)** — confirmado no scout que cache
  intra-processo (LRU) NÃO fecha o bug (cada response = processo novo). Tem que
  ser persistente em disco, gitignored, lifecycle = checkpoint. O executor
  confirma a serialização das dataclasses de inventory (asdict round-trip).
- **Exit code do BUG-PLAN-1** — spec diz "exit 2", código diz 130. Esta onda
  SEGUE O CÓDIGO (130, contrato testado). Se o mantenedor QUISER unificar em exit
  2, é decisão de design separada (mudaria o contrato de TODAS as pausas do plan,
  não só este path) — fora do escopo; anotar como follow-on se levantado.
- **Housekeeping da branch `fix/pilot-init-perf`** — após o cherry-pick do helper
  (Task 1), o único valor restante da branch foi absorvido (BUG-1 já fechou em
  main por outra impl; BUG-1b é parcial/deferred). Recomendação: **descartar** a
  branch após esta onda mergear (não há mais nada a extrair). Decisão final é do
  mantenedor — NÃO faz parte do code-work desta onda (sem `git branch -D` no plano).
- **Consolidação dos 4 `_SKIP_DIRS`** — deferida (parametrizar, não unificar).
  Reentrar se o plan-auditor/review julgar que a fragmentação é dívida prioritária.

---

## BLOCKED?

Não. As três tasks cabem num ciclo coeso (~7 arquivos de produção, 6 de teste,
2 de doc-sync), são independentes entre si (paralelizáveis por task, mas
compartilham init.py entre T1 e T2 → T1 e T2 sequenciais no mesmo arquivo), e o
reuso-first (helper já pronto na branch) reduz o custo de T1. Nenhuma task isolada
estoura um ciclo. Se durante a execução o no-behavior-change da T1 mostrar
divergência de ordem em múltiplos sites (custo de instrumentar cada um), o
executor escala com 3-caminhos (A: ordenar o helper globalmente / B: parametrizar
ordem por site / C: defer os sites order-sensitive pra sub-plano) — mas o default
é A (ordenar), barato e seguro.
