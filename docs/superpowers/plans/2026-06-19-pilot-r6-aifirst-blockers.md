# Plano — Pilot R6 · 4 blockers AI-first (P-17, P-18, P-19/P-20, P-24)

**Data:** 2026-06-19 · forge v1.5.0
**Spec / fonte:** `docs/reports/pilot-meobonsai-2026-06-19/report.md` (findings P-17, P-18, P-19, P-20, P-24)
**Subtype:** bugfix (P-17, P-18, P-19, P-20) + feature (P-24, 2 validators reais)

---

## Goal

Fechar os 4 bloqueadores remanescentes do piloto AI-first no MeoBonsai, com
root-cause já diagnosticado:

- **P-17 (Grupo A):** `forge implement` bloqueado por phase-lock stale —
  plan-complete zera `status.json:phase-lock` mas nunca remove o sentinel
  `.phase-lock`; mensagem de erro mostra `'None'` em vez do holder real.
- **P-19 + P-20 (Grupo B):** `forge qa` Phase 0 cria `snapshot/` vazio
  (scope.paths de feature é um DIRETÓRIO e `snapshot_artefacts` só copia
  arquivos regulares); `conductor-handoff.json` não carrega os campos do
  contrato (`snapshot` paths, `config_snapshot`, `auditors`).
- **P-24 (Grupo C):** os 2 validators do card `compose-screens`
  (`check-no-suppress.py`, `check-screen-layout.py`) são stubs `return 0`
  declarados como `severity: error` — "validator mente sobre cobertura".
- **P-18 (Grupo D):** `forge reconfigure` não aplica mutações via loop
  canônico AI-first — o R4 (`host_is_replaying`) gateou guards de NAVEGAÇÃO
  mas não o caminho `apply-confirm × draft-resume`.

O Grupo E faz doc-sync consolidado (Mandamento #6) no FINAL.

**Anti-goal:** P-21/P-22/P-23 (ambiguidades de contrato do `qa-conductor.md`)
NÃO são implementados aqui — anotados como deferidos em `04-pending.md` no
Grupo E (decisão do mantenedor).

---

## Architecture

### Phase-lock — fonte de verdade dupla (Grupo A)

`engine/memory/l1.py` mantém DUAS representações do phase-lock:

1. **Sentinel `O_EXCL`** — `.claude/memory/L1/<slug>/.phase-lock`, conteúdo =
   `lock_id`. É a fonte AUTORITATIVA do gate atômico (`acquire_phase_lock`
   ~L496). `current_phase_lock` (~L683) consulta o sentinel PRIMEIRO.
2. **Mirror em `status.json:phase-lock`** — humano-legível, escrito por
   `_mirror_phase_lock_to_status` (~L583) DEPOIS do sentinel.

`release_phase_lock(slug, project_root)` (~L664) é o primitivo canônico que
remove o sentinel E reconcilia `status.json` (seta `phase_lock=None`,
`last_action_kind="phase-lock-released"`). **Não criar helper novo** — reusar
`release_phase_lock` + `current_phase_lock` (Mandamento #3).

O bug do P-17: `engine/plan.py:2048-2053` (plan-complete) faz
`final_state.phase_lock = None; write_l1_status(...)` — zera o MIRROR mas
deixa o SENTINEL "planning" em disco. As fontes divergem; quem lê
(`current_phase_lock`) reporta "planning" (sentinel-first) e `acquire_phase_lock`
de `forge implement` bate `FileExistsError` ("planning" ≠ task_id) → ERR_LOCKED.
A mensagem de erro em `implement.py:1342-1343` e `plan.py:1909-1910` lê
`read_l1_status(...).phase_lock` (=None no mirror) → imprime "by 'None'".

### QA Phase 0 — snapshot de artefatos (Grupo B)

`engine/qa/scope.py::resolve_scope` retorna `Scope(type="feature",
paths=(feature_path,))` (~L149) onde `feature_path` é um **diretório**
(`docs/feature-implementation-workflow/features/<slug>/`).
`engine/qa/ingest.py::snapshot_artefacts` (~L270) itera `scope.paths` e tenta
`os.link(src, dest)` / `shutil.copy2(src, dest)` — ambos falham em diretório
(IsADirectoryError ⊂ OSError) e o `except OSError: continue` engole. Resultado:
`snapshot/` vazio. **Fix:** quando `src` é diretório, recursar nos arquivos
(`rglob("*")`) preservando layout relativo; quando é arquivo, comportamento
atual. Reusar a mesma estratégia hardlink→copy2.

`_write_conductor_handoff` (~L677) escreve só `scope/run_id/root/config`. O
contrato em `agents/qa-conductor.md` (~L47-57) exige `snapshot` paths,
`config_snapshot` (qa: section), e `auditors` (4 core + N extension). **Fix:**
adicionar os 3 campos. A lista de snapshot vem do retorno de `snapshot_artefacts`
(propaga via novo param). Os 4 core auditors são canônicos
(`spec-vs-spec`, `coverage`, `chaos`, `validator-claim` — ver §Phase 1+2 do
contrato); extensões ativas = `cfg.extensions_disabled` filtra a lista.

### Card validators (Grupo C)

Contrato de invocação (autoritativo, lido em `engine/verify.py::_invoke_validator`
~L938): `python3 <script> --project-root <path>` + opcionalmente
`--scope <kind> --id <target>`, com `cwd=project_root`. Os validators DEVEM:

- aceitar `--project-root` (default `.`),
- TOLERAR `--scope`/`--id` (parse-only, ignoráveis),
- varrer a partir de `project_root`,
- exit 0 limpo / exit 1 com violações em stderr (`arquivo:linha`).

Forma copiada de `cards/koin-annotations/validators/check-koin-modules.py`
(argparse → rglob → failures → exit 1). Source sets KMP via constante de
segmentos de path (espelha `PRODUCTION_SOURCE_SETS`/`TEST_SOURCE_SETS` do koin).

### Reconfigure apply via loop canônico (Grupo D)

`engine/reconfigure.py::run` (~L223-443) tem dois pontos de `host_is_replaying`:

- **draft-resume guard** (~L247): se há draft em disco E `host_is_replaying`
  → adota draft silenciosamente (`working = draft`). Cobre NAVEGAÇÃO (R4).
- **apply-confirm** (~L397): `question.confirm("Aplicar essas mudanças?")` SEM
  guard `host_is_replaying`.

Deadlock P-18: no loop AI-first o host responde o apply-confirm e re-invoca
argv idêntico. A re-invocação re-entra no topo; o draft-resume guard vê a
response do apply-confirm pendente (id ≠ `_draft_confirm_id`, não-consumida) →
`host_is_replaying=True` → adota o draft → navega de novo (re-emitindo o
category-menu, intent ≠ apply-confirm) → mismatch / o apply-confirm nunca
consome sua response → exit 1, mutação não aplicada.

**Invariante alvo:** quando há uma response de apply-confirm pendente e o engine
está em replay, o pipeline deve ALCANCAR o apply-confirm e CONSUMI-LA (aplicando
a mutação) — sem o category-menu intervir. Re-entrada HUMANA genuína (sem
response in-flight) continua mostrando o draft-resume guard. O ponto mínimo de
inserção do guard depende da máquina de estados — o executor confirma após o
repro test (Task D1) verde-vermelho. Pointers exatos abaixo.

---

## Tech Stack

- Python (engine + validators), `argparse`, `re`, `pathlib`, `shutil`, `os`.
- pytest canônico = `.venv/bin/pytest` (system pytest gera falsos negativos —
  falta json5). SEMPRE invocar via `.venv/bin/pytest`.
- Markers: cruza ≥2 módulos OU fixture → `@pytest.mark.integration`;
  subprocessa CLI → `@pytest.mark.e2e`; unit puro → sem marker.

---

## Global Constraints

- TDD obrigatório em todo grupo de código: teste FALHA primeiro (RED), impl
  faz passar (GREEN). Grupo D começa por repro test que reproduz o deadlock.
- Voz mentor calmo em qualquer string user-facing (mensagens de validator,
  de erro de lock). Sem emoji decorativo. PT neutro.
- NÃO tocar `docs/design/01-decisions.md` (nenhuma task abaixo o toca).
- Doc-sync (CHANGELOG/handoff/README/04-pending) é o Grupo E SEPARADO no final —
  NÃO espalhar doc-sync por-fix.
- Commits atômicos por task. Convenção: test+impl no mesmo commit por task
  (consistente em todo o plano), mensagem `<tipo>(<escopo>): <descrição> (P-NN)`.
- Reuso antes de criar (Mandamento #3): Grupo A reusa `release_phase_lock` +
  `current_phase_lock`; Grupo B reusa/estende `snapshot_artefacts`; Grupo C
  copia a forma do koin validator; nenhum helper novo sem necessidade.
- Não expandir escopo (Mandamento #4): cada task lista ARQUIVOS PERMITIDOS;
  ficar dentro.

Ordem de execução: **A → B → C → D** (D por último, mais delicado).

---

## Grupo A — P-17: phase-lock stale no plan-complete (2 tasks)

### Task A1 — plan-complete libera o phase-lock via `release_phase_lock`

**Files:**
- Modify: `engine/plan.py` (bloco plan-complete ~L2048-2054)
- Test: `tests/unit/test_plan_complete_releases_lock.py` (Create)

**Interfaces:**
- Consumes: `engine.memory.l1.release_phase_lock(slug, project_root) -> None`
  (~L664; remove sentinel + reconcilia status.json),
  `engine.memory.l1.current_phase_lock(slug, project_root) -> Optional[str]`
  (~L683; sentinel-first), `read_l1_status`, `write_l1_status`,
  `_phase_lock_path` (todos já importados em plan.py).
- Produces: invariante final pós plan-complete → `status="planned"` +
  `phase_lock=None` + sentinel `.phase-lock` ausente do disco.

**Steps (TDD):**

1. RED — escreve o teste em `tests/unit/test_plan_complete_releases_lock.py`.
   O teste semeia a L1 num estado pós-acquire ("planning" com sentinel),
   chama o trecho de plan-complete (ou `plan.run` até completar), e asserta o
   invariante final. Modelado em `tests/unit/test_implement_lock_release.py`
   (helper `_seed_ready_feature` + asserts via `current_phase_lock`). Conteúdo:

   - Função helper local `_seed_planning_lock(project_root, slug)`: cria
     `.claude/workflow-config.yaml` (marker), chama
     `engine.memory.l1.acquire_phase_lock(slug, project_root, "planning")` pra
     plantar o sentinel + mirror exatamente como `forge plan` faz na L1908.
   - `test_plan_complete_clears_sentinel_and_mirror`: após semear o lock
     "planning", invoca a unidade que finaliza o plan (ver passo 2 — extrair
     helper testável OU dirigir via `plan.run`). Asserta:
     `assert current_phase_lock(slug, project_root) is None`
     `assert not _phase_lock_path(slug, project_root).exists()`
     `state = read_l1_status(slug, project_root); assert state.status == "planned"`
     `assert state.phase_lock is None`
   - `test_plan_complete_invariant_order`: garante que a ORDEM final não
     reintroduz o lock — após release, o status persistido é `planned`
     (não `phase-lock-released` sobrescrevendo `planned`). Asserta
     `state.status == "planned"` E `state.last_action_kind == "plan-completed"`.

2. Roda RED:
   `.venv/bin/pytest tests/unit/test_plan_complete_releases_lock.py -x`
   Esperado: FAIL (hoje plan-complete não remove o sentinel → o sentinel
   "planning" sobrevive → `current_phase_lock` retorna "planning", não None).

3. GREEN — em `engine/plan.py`, substituir o bloco plan-complete
   (atualmente):
   ```
   final_state = read_l1_status(slug, project_root) or state
   final_state.status = "planned"
   final_state.last_action_kind = "plan-completed"
   final_state.phase_lock = None
   write_l1_status(final_state, project_root)
   ```
   Nova lógica (ORDEM cuidada — `release_phase_lock` sobrescreve
   `last_action_kind="phase-lock-released"`, então liberar PRIMEIRO e gravar o
   estado `planned` DEPOIS):
   - `release_phase_lock(slug, project_root)` — remove sentinel + reconcilia
     mirror (`phase_lock=None`).
   - re-ler: `final_state = read_l1_status(slug, project_root) or state`
   - `final_state.status = "planned"`
   - `final_state.last_action_kind = "plan-completed"`
   - `final_state.phase_lock = None`  (idempotente — já None após release)
   - `write_l1_status(final_state, project_root)`
   Isso garante o invariante final: sentinel removido, mirror None,
   status=planned, last_action_kind=plan-completed.

   Nota: se for necessário extrair a unidade pra testar (passo 1), criar um
   helper local privado `_finalize_planned(slug, project_root, state)` em
   `engine/plan.py` que encapsula o bloco acima e é chamado de dentro de `run`.
   O teste importa o helper. Isso mantém o teste unit (sem dirigir todo o
   `plan.run`). Decisão de extrair fica a critério do executor; se `plan.run`
   for facilmente dirigível com prompts stubbados, testar via `run` é aceitável.

4. Roda GREEN:
   `.venv/bin/pytest tests/unit/test_plan_complete_releases_lock.py -x`
   Esperado: PASS.

5. Regressão: `.venv/bin/pytest tests/unit/test_implement_lock_release.py
   tests/unit/test_phase_lock_context_manager.py tests/unit/test_memory_l1.py -q`
   Esperado: PASS (nenhuma regressão no contrato de lock).

6. Commit: `fix(plan): release phase-lock no plan-complete (P-17)`

### Task A2 — mensagens de erro de lock leem o holder REAL (sentinel-first)

**Files:**
- Modify: `engine/implement.py` (~L1342-1343), `engine/plan.py` (~L1909-1910)
- Test: `tests/unit/test_lock_error_message_shows_real_holder.py` (Create)

**Interfaces:**
- Consumes: `engine.memory.l1.current_phase_lock(slug, project_root)`
  (sentinel-first; já importado em ambos os módulos — confirmar import e
  adicionar se ausente, dentro das ARQUIVOS PERMITIDOS).

**Steps (TDD):**

1. RED — `tests/unit/test_lock_error_message_shows_real_holder.py`. O teste
   planta um lock real de OUTRO holder e dirige a denial path de cada handler
   capturando stderr. Modelado em
   `test_blocked_on_external_does_not_release_foreign_lock` (mesmo arquivo de
   lock release) pra plantar o foreign lock via `acquire_phase_lock`. Conteúdo:

   - `test_implement_lock_denied_shows_real_holder`: semeia feature ready
     (reusar o `_seed_ready_feature` pattern), planta lock alheio
     `acquire_phase_lock(slug, root, "OTHER-HOLDER-99")`, stub de prompts
     autônomos, chama `implement.run([slug])`, captura `capsys`. Asserta:
     `assert "phase-locked by 'OTHER-HOLDER-99'" in captured.err`
     `assert "by 'None'" not in captured.err`
     `assert "[FORGE-ERR:LOCKED]" in captured.err`
   - `test_plan_lock_denied_shows_real_holder`: análogo dirigindo `plan.run`
     contra um slug com lock alheio plantado; asserta o holder real na
     mensagem do `plan.py:1911-1914` e ausência de "by 'None'".

2. Roda RED:
   `.venv/bin/pytest tests/unit/test_lock_error_message_shows_real_holder.py -x`
   Esperado: FAIL (hoje ambos leem `read_l1_status(...).phase_lock`; sob o
   sentinel-mirror race / mirror desatualizado a mensagem pode dizer 'None').

3. GREEN — em `engine/implement.py` (~L1342-1343), trocar:
   ```
   current = read_l1_status(slug, project_root)
   held = current.phase_lock if current else "?"
   ```
   por:
   ```
   held = current_phase_lock(slug, project_root) or "?"
   ```
   Idêntico em `engine/plan.py` (~L1909-1910). Garantir `current_phase_lock`
   importado em ambos (adicionar ao import de `engine.memory.l1` se faltar).

4. Roda GREEN:
   `.venv/bin/pytest tests/unit/test_lock_error_message_shows_real_holder.py -x`
   Esperado: PASS.

5. Regressão: `.venv/bin/pytest tests/unit/test_implement_lock_release.py -q`
   Esperado: PASS.

6. Commit: `fix(lock): mensagem de erro mostra holder real via current_phase_lock (P-17)`

---

## Grupo B — P-19 + P-20: qa Phase 0 snapshot + handoff (2 tasks)

### Task B1 — `snapshot_artefacts` recursa em diretórios

**Files:**
- Modify: `engine/qa/ingest.py` (`snapshot_artefacts` ~L270-346)
- Test: `tests/engine/qa/test_snapshot.py` (Modify — adiciona casos)

**Interfaces:**
- Consumes: `Scope.paths` (tupla; pra feature scope = `(feature_dir,)`).
- Produces: `snapshot_artefacts(...) -> list[Path]` agora inclui os arquivos
  copiados de DENTRO de diretórios em `scope.paths`, com layout relativo a
  `project_root` preservado.

**Steps (TDD):**

1. RED — adiciona em `tests/engine/qa/test_snapshot.py` (mesmo estilo dos
   testes existentes, fixture `_setup_proj_with_files`):

   - `test_snapshot_recurses_into_directory`: cria um dir de feature
     `docs/feature-implementation-workflow/features/snap-feat/` com
     `feature-spec.yaml`, `bdd.json`, e `tasks/TASK-0001.yaml` (arquivos
     reais). `scope = Scope(type="feature", target="snap-feat",
     paths=(feature_dir,))`. Chama `snapshot_artefacts(scope,
     tree.snapshot_dir, project_root=proj)`. Asserta:
     `assert (tree.snapshot_dir / "docs/feature-implementation-workflow/features/snap-feat/feature-spec.yaml").is_file()`
     `assert (tree.snapshot_dir / "docs/feature-implementation-workflow/features/snap-feat/tasks/TASK-0001.yaml").is_file()`
     `assert len(copied) >= 3`
   - `test_snapshot_directory_preserves_nested_layout`: confirma que o
     subdir `tasks/` é recriado dentro do snapshot (não achatado).

2. Roda RED:
   `.venv/bin/pytest tests/engine/qa/test_snapshot.py::test_snapshot_recurses_into_directory -x`
   Esperado: FAIL (hoje o dir é pulado silenciosamente — `os.link`/`copy2` em
   dir levanta OSError engolido → `copied` não contém os arquivos).

3. GREEN — em `engine/qa/ingest.py::snapshot_artefacts`, dentro do loop
   `for src in scope.paths:`, após o guard `if not src_path.exists(): continue`,
   ramificar:
   - Se `src_path.is_dir()`: iterar `for f in sorted(src_path.rglob("*")):`
     pulando `if not f.is_file(): continue`; pra cada arquivo, computar `rel`
     relativo a `project_root_resolved` (mesmo bloco try/except ValueError →
     flatten pelo `f.name`), `dest = snapshot_dir / rel`,
     `dest.parent.mkdir(parents=True, exist_ok=True)`, tentar
     `os.link(f, dest)` com fallback `shutil.copy2(f, dest)` (mesma cascata
     existente), `copied.append(dest)`.
   - Else (arquivo regular): comportamento atual inalterado.
   Extrair a cascata hardlink→copy2 num helper privado local
   `_copy_one(src_file, dest, copied)` pra não duplicar (Mandamento #3 — DRY
   intra-módulo); o helper é chamado tanto no ramo dir quanto no ramo arquivo.

4. Roda GREEN:
   `.venv/bin/pytest tests/engine/qa/test_snapshot.py -x`
   Esperado: PASS (novos + os 5 existentes continuam verdes — arquivos
   regulares mantêm comportamento).

5. Commit: `fix(qa): snapshot_artefacts recursa em diretórios de scope (P-19)`

### Task B2 — `conductor-handoff.json` carrega snapshot/config_snapshot/auditors

**Files:**
- Modify: `engine/qa/__init__.py` (`_write_conductor_handoff` ~L677-724 +
  os 2 callsites ~L217-219 e ~L255-257)
- Test: `tests/integration/test_qa_lifecycle_feature.py` (Modify — adiciona
  caso) OU `tests/engine/qa/test_conductor_handoff.py` (Create se preferível)

**Interfaces:**
- Consumes: lista de snapshot paths (retorno de `snapshot_artefacts` —
  `snapshot_copied`, já capturada no callsite ~L208/L234), `cfg: QAConfig`
  (`extensions_disabled`, budgets), `workflow_config` (qa: section).
- Produces: `conductor-handoff.json` com novos campos `snapshot` (lista de
  paths relativos a `run_tree.root`), `config_snapshot` (dict da qa: section),
  `auditors` (lista: 4 core + extensões não-desabilitadas).

**Steps (TDD):**

1. RED — adiciona em `tests/integration/test_qa_lifecycle_feature.py`
   (já tem `_make_feature_project` + invoca `run_qa`; marker `integration`):

   - `test_conductor_handoff_carries_contract_fields`: cria feature com
     artefatos (`feature-spec.yaml`, `tasks/TASK-0001.yaml`), invoca
     `run_qa(slug, project_root=proj, workflow_config={"qa": {"enabled": True}})`,
     localiza `conductor-handoff.json` (mesmo padrão do teste PASS existente —
     `run_dirs[0] / "conductor-handoff.json"`), parseia. Asserta:
     `assert "snapshot" in data and isinstance(data["snapshot"], list)`
     `assert len(data["snapshot"]) >= 1  # snapshot populado (depende de B1)`
     `assert "config_snapshot" in data`
     `assert "auditors" in data`
     `core = {"spec-vs-spec", "coverage", "chaos", "validator-claim"}`
     `assert core.issubset(set(data["auditors"]))`

2. Roda RED:
   `.venv/bin/pytest tests/integration/test_qa_lifecycle_feature.py::test_conductor_handoff_carries_contract_fields -x`
   Esperado: FAIL (hoje o handoff só tem `scope/run_id/root/config`).

3. GREEN — em `engine/qa/__init__.py`:
   - Estender a assinatura de `_write_conductor_handoff` com dois params
     kw-only: `snapshot_paths: list[Path] = ()` e
     `workflow_config: dict[str, Any] | None = None`.
   - No corpo, após montar o dict `handoff`, adicionar:
     - `"snapshot"`: `[str(p.relative_to(run_tree.root)) for p in
       snapshot_paths]` (paths relativos à raiz da run — portáveis no JSON).
     - `"config_snapshot"`: a qa: section congelada —
       `(workflow_config or {}).get("qa", {})` (dict; congela o estado da
       config no momento da run, per contrato §5.1 do qa-conductor).
     - `"auditors"`: lista derivada dos 4 core
       `["spec-vs-spec", "coverage", "chaos", "validator-claim"]` filtrando
       os presentes em `cfg.extensions_disabled` (extensões core não são
       desabilitáveis na prática, mas o filtro é defensivo e documenta a
       intenção). Definir como constante module-level
       `_CORE_AUDITORS = ("spec-vs-spec", "coverage", "chaos",
       "validator-claim")` no topo de `engine/qa/__init__.py`.
   - Atualizar os DOIS callsites (~L217-219 e ~L255-257) pra passar
     `snapshot_paths=snapshot_copied, workflow_config=workflow_config`.
     `snapshot_copied` e `workflow_config` já estão no escopo de `run_qa` em
     ambos os ramos.

4. Roda GREEN:
   `.venv/bin/pytest tests/integration/test_qa_lifecycle_feature.py -x`
   Esperado: PASS (novo caso + os 2 existentes).

5. Regressão: `.venv/bin/pytest tests/integration/test_qa_lifecycle_task.py -q`
   Esperado: PASS.

6. Commit: `fix(qa): conductor-handoff carrega snapshot/config_snapshot/auditors (P-20)`

---

## Grupo C — P-24: validators reais do card compose-screens (2 tasks)

### Task C1 — `check-no-suppress.py` real

**Files:**
- Modify: `cards/compose-screens/validators/check-no-suppress.py`
- Test: `tests/validators/test_compose_check_no_suppress.py` (Create)

**Interfaces:**
- Consumes (contrato de invocação, autoritativo de `engine/verify.py::_invoke_validator`):
  `python3 <script> --project-root <path>` + opcional `--scope <kind> --id <target>`,
  `cwd=project_root`.
- Produces: exit 0 quando limpo; exit 1 + linhas `arquivo:linha: <trecho>` em
  stderr quando há `@Suppress`/`@file:Suppress` em código Compose.

**Steps (TDD):**

1. RED — `tests/validators/test_compose_check_no_suppress.py`. Invoca o
   script como subprocess (`sys.executable`, argv `--project-root <tmp>`)
   sobre fixtures Kotlin num tmp dir (espelha a forma do contrato real).
   Conteúdo:

   - Helper `_run(project_root)`: `subprocess.run([sys.executable,
     str(SCRIPT), "--project-root", str(project_root)],
     capture_output=True, text=True)` onde `SCRIPT =
     Path("cards/compose-screens/validators/check-no-suppress.py").resolve()`.
   - `test_clean_compose_passes`: cria
     `androidApp/feature/home/ui/HomeScreen.kt` com um composable simples sem
     `@Suppress`. Asserta `result.returncode == 0`.
   - `test_suppress_annotation_fails`: cria
     `androidApp/feature/home/ui/HomeScreen.kt` com
     `@Suppress("LongMethod")` numa função. Asserta `result.returncode == 1`
     e `"HomeScreen.kt" in result.stderr` e `"@Suppress" in result.stderr`.
   - `test_file_suppress_fails`: arquivo com `@file:Suppress("ktlint")` no
     topo. Asserta exit 1.
   - `test_suppress_in_comment_ignored`: linha `// @Suppress aqui é só doc`.
     Asserta exit 0 (não conta ocorrência em comentário de linha).
   - `test_suppress_in_kdoc_ignored`: bloco `/** ... @Suppress ... */`.
     Asserta exit 0.
   - `test_suppress_in_string_literal_ignored`: `val s = "@Suppress fake"`.
     Asserta exit 0.
   - `test_non_compose_source_set_ignored`: `@Suppress` em
     `shared/src/commonTest/.../Foo.kt` (test source set). Asserta exit 0
     (escopo = Compose UI source sets, não test).

2. Roda RED:
   `.venv/bin/pytest tests/validators/test_compose_check_no_suppress.py -x`
   Esperado: FAIL (stub retorna 0 sempre — `test_suppress_annotation_fails`
   espera 1).

3. GREEN — reescrever `cards/compose-screens/validators/check-no-suppress.py`
   copiando a forma do koin validator:
   - `argparse`: `--project-root` (default `"."`); aceitar e ignorar
     `--scope` e `--id` (`parser.add_argument("--scope")`,
     `parser.add_argument("--id")` — parse-only).
   - Constantes de escopo Compose (segmentos de path):
     `COMPOSE_PATH_SEGMENTS = ("/androidApp/", "/composeApp/src/")` e
     `_COMPOSE_UI_HINT = "/ui/"` — varrer `.kt` cujo posix path contenha um
     segmento Compose; excluir test source sets
     (`/src/commonTest/`, `/src/androidUnitTest/`, `/src/test/`,
     `/src/iosTest/`).
   - Regex: `SUPPRESS_RE = re.compile(r"@(?:file:)?Suppress\b")`.
   - Pra ignorar comentário/KDoc/string: ler linha-a-linha; antes de aplicar
     a regex, strip-out conteúdo de comentário de linha (`//...`), blocos KDoc
     (`/** ... */` — rastrear estado multi-linha), e string literais simples
     (substituir `"..."` por vazio na linha via
     `re.sub(r'"(?:[^"\\]|\\.)*"', '""', line)`). Reportar `arquivo:linha:
     <trecho original>` no `failures`.
   - `main()`: resolve `project_root`, `for kt in root.rglob("*.kt")` filtrando
     escopo Compose, coleta failures; se há failures imprime cada uma em stderr
     prefixada `[compose-screens/check-no-suppress]` + sugestão mentor calmo
     ("Extraia a função pra {Screen}Components.kt ou corrija a violação na
     raiz — não silencie o linter em Compose.") e `return 1`; senão `return 0`.

4. Roda GREEN:
   `.venv/bin/pytest tests/validators/test_compose_check_no_suppress.py -x`
   Esperado: PASS (todos os 7 casos).

5. Commit: `feat(compose-screens): check-no-suppress real (P-24)`

### Task C2 — `check-screen-layout.py` real

**Files:**
- Modify: `cards/compose-screens/validators/check-screen-layout.py`
- Test: `tests/validators/test_compose_check_screen_layout.py` (Create)

**Interfaces:**
- Consumes: mesmo contrato de invocação da C1 (`--project-root` + opcionais
  `--scope`/`--id`, `cwd=project_root`).
- Produces: exit 0 quando todo dir de tela tem o par `{Screen}Screen.kt` +
  `{Screen}Content.kt`; exit 1 + `{dir}: missing {Screen}Content.kt` quando
  o pareamento quebra.

**Regra de detecção (precisa, testável):**
- Um "diretório de tela" é qualquer dir sob escopo Compose
  (`COMPOSE_PATH_SEGMENTS` da C1) que contenha ≥1 arquivo casando
  `(?P<screen>[A-Z][A-Za-z0-9]*)Screen\.kt` (PascalCase).
- Pra cada `{Screen}Screen.kt` encontrado, o MESMO dir DEVE conter
  `{Screen}Content.kt`. Ausência → falha
  `{dir}: missing {Screen}Content.kt`.
- Inverso: `{Screen}Content.kt` sem `{Screen}Screen.kt` no mesmo dir → falha
  `{dir}: missing {Screen}Screen.kt`.
- `{Screen}Components.kt` e `{Screen}Mappers.kt` são OPCIONAIS (presença não
  exigida, ausência não falha).
- Source sets KMP: o dir de tela pode estar em `androidMain` ou em
  `composeApp/src/...`; a detecção é por nome de arquivo no dir, agnóstica ao
  source set, desde que dentro do escopo Compose.

**Steps (TDD):**

1. RED — `tests/validators/test_compose_check_screen_layout.py` (mesmo helper
   `_run` subprocess da C1, apontando pro `check-screen-layout.py`):

   - `test_paired_screen_content_passes`:
     `androidApp/feature/home/ui/home/HomeScreen.kt` +
     `androidApp/feature/home/ui/home/HomeContent.kt`. Asserta exit 0.
   - `test_screen_without_content_fails`: só `HomeScreen.kt` no dir.
     Asserta exit 1 + `"missing HomeContent.kt" in result.stderr`.
   - `test_content_without_screen_fails`: só `HomeContent.kt`.
     Asserta exit 1 + `"missing HomeScreen.kt" in result.stderr`.
   - `test_optional_components_mappers_dont_break`: par completo +
     `HomeComponents.kt` + `HomeMappers.kt`. Asserta exit 0.
   - `test_composeapp_source_set_scope`: par válido em
     `composeApp/src/commonMain/kotlin/.../detail/DetailScreen.kt` +
     `DetailContent.kt`. Asserta exit 0.
   - `test_non_compose_dir_ignored`: `shared/domain/UseCase.kt` (sem
     `*Screen.kt`, fora do escopo Compose). Asserta exit 0.

2. Roda RED:
   `.venv/bin/pytest tests/validators/test_compose_check_screen_layout.py -x`
   Esperado: FAIL (stub retorna 0 — `test_screen_without_content_fails`
   espera 1).

3. GREEN — reescrever `cards/compose-screens/validators/check-screen-layout.py`:
   - `argparse` igual à C1 (`--project-root` + ignore `--scope`/`--id`).
   - Reusar `COMPOSE_PATH_SEGMENTS` (definir local — sem import cruzado entre
     scripts de card; cada validator é standalone subprocess, não há módulo
     compartilhado de card). Constante local idêntica é aceitável aqui pois
     são scripts subprocess isolados (não composição de engine).
   - `SCREEN_RE = re.compile(r"^(?P<screen>[A-Z][A-Za-z0-9]*)Screen\.kt$")`,
     `CONTENT_RE = re.compile(r"^(?P<screen>[A-Z][A-Za-z0-9]*)Content\.kt$")`.
   - Varrer dirs sob escopo Compose: `for d in
     {f.parent for f in root.rglob("*.kt") if _in_compose_scope(f)}:`. Pra
     cada dir, montar `screens = {m["screen"] for f in d.iterdir() if (m :=
     SCREEN_RE.match(f.name))}` e `contents = {...CONTENT_RE...}`. Failures:
     `for s in screens - contents: failures.append(f"{d}: missing {s}Content.kt")`
     `for s in contents - screens: failures.append(f"{d}: missing {s}Screen.kt")`.
   - Imprimir failures em stderr prefixadas `[compose-screens/check-screen-layout]`
     + sugestão mentor calmo; `return 1` se houver, senão `return 0`.

4. Roda GREEN:
   `.venv/bin/pytest tests/validators/test_compose_check_screen_layout.py -x`
   Esperado: PASS (6 casos).

5. Regressão de card (smoke): garantir que os 2 validators não quebram quando
   invocados sem arquivos Compose:
   `.venv/bin/pytest tests/validators/test_compose_check_no_suppress.py tests/validators/test_compose_check_screen_layout.py -q`
   Esperado: PASS.

6. Commit: `feat(compose-screens): check-screen-layout real (P-24)`

---

## Grupo D — P-18: reconfigure aplica via loop canônico AI-first (2 tasks)

### Task D1 — repro test do deadlock apply-confirm × draft-resume (RED)

**Files:**
- Test: `tests/unit/test_reconfigure_apply_via_replay.py` (Create) —
  unit dirigindo `reconfigure.run` com host pinado + responses plantadas
  (espelha `tests/unit/test_engine_reconfigure_resume.py` §P-15).

**Interfaces:**
- Consumes: `engine.reconfigure.run`, `engine.ui.intent_state.write_response`,
  `engine.ui.question.stable_intent_id`,
  `engine.ui.intent_state.host_is_replaying`,
  `engine.ui.intent_state.IntentMismatchError`.
- Produces: teste que PROVA o invariante (apply via replay aplica a mutação
  sem mismatch) — FALHA antes do fix.

**Steps (TDD):**

1. RED — escreve `tests/unit/test_reconfigure_apply_via_replay.py`. Modelado
   nos helpers de `tests/unit/test_engine_reconfigure_resume.py`
   (`_pin_intent_file_host`, `_seed_workflow_config`,
   `_run_reconfigure_expected_mismatch_id`). Conteúdo:

   - Helper `_apply_confirm_intent_id()`: espelha o callsite da L384-393 de
     reconfigure.run:
     `question.stable_intent_id("confirm", "Aplicar essas mudanças?",
     {"s": "sim", "n": "não"}, extra={"default": "n", "min-selected": None,
     "validator-hint": None})`.
   - Setup: `_seed_workflow_config(tmp)`, `monkeypatch.chdir(tmp)`,
     `_pin_intent_file_host(tmp, monkeypatch)`. Plantar um draft em disco
     (`.claude/.reconfigure-draft.yaml`) que represente uma mutação pendente
     (qa enable) DIVERGENTE da config atual — pra que o caminho chegue ao
     apply-confirm. Plantar via `intent_state.write_response(tmp,
     {"schema-version": 1, "intent-id": <apply_confirm_id>, "value": True})`
     simulando a response do apply-confirm em-voo (o host respondeu "sim,
     aplicar" e re-invocou).
   - `test_apply_confirm_response_consumed_during_replay`: roda
     `reconfigure.run([])` e asserta que NÃO levanta `IntentMismatchError` E
     que a mutação foi aplicada (config no disco mudou — qa enabled). Antes do
     fix: o draft-resume guard intercepta a response do apply-confirm,
     re-navega, e o id pedido diverge → mismatch (exit 1, config inalterada).
     Asserção dupla: capturar o resultado de `run` e verificar o
     `.claude/forge/forge-config.yaml` (ou `.claude/workflow-config.yaml`)
     reflete a mutação esperada.
   - `test_human_reentry_still_shows_draft_resume`: SEM response in-flight
     (limpar `forge-response.json`), com draft presente — `reconfigure.run`
     deve alcançar o draft-resume confirm (não suprimir). Asserta via
     `_run_reconfigure_and_capture_first_pending` que o pending emitido é o
     draft-confirm (`intent-id == _draft_confirm_intent_id()`). Protege o
     invariante: re-entrada humana genuína ainda vê o guard.

2. Roda RED:
   `.venv/bin/pytest tests/unit/test_reconfigure_apply_via_replay.py -x`
   Esperado: `test_apply_confirm_response_consumed_during_replay` FALHA
   (reproduz o deadlock P-18 — mismatch / mutação não aplicada);
   `test_human_reentry_still_shows_draft_resume` PODE já passar (protege o
   lado humano — confirma que o fix da D2 não regride).

   NOTA AO EXECUTOR: se a forma exata de plantar a response do apply-confirm
   não reproduzir o deadlock no nível unit (o pipeline pode precisar
   atravessar o category-menu primeiro), elevar o repro pra e2e subprocess
   espelhando `tests/e2e/test_plan_canonical_loop.py` com `drive_intent_loop`
   (responder category→qa→enable→apply-confirm→re-invoke). O repro DEVE
   reproduzir exit 1/mismatch + mutação não aplicada antes do fix. Escolher o
   nível (unit vs e2e) que reproduz o deadlock de forma determinística; marcar
   `@pytest.mark.e2e` se for subprocess.

3. Commit (RED isolado, test-commit-first pra este grupo delicado):
   `test(reconfigure): repro do deadlock apply × draft-resume (P-18)`

### Task D2 — estender `host_is_replaying` ao apply path (GREEN)

**Files:**
- Modify: `engine/reconfigure.py` (draft-resume guard ~L247 e/ou apply-confirm
  ~L378-405)
- Test: `tests/unit/test_reconfigure_apply_via_replay.py` (passa) +
  regressão `tests/unit/test_engine_reconfigure_resume.py`

**Interfaces:**
- Consumes: `engine.ui.intent_state.host_is_replaying(project_root,
  guard_intent_id)` (~L634; semântica: True quando há response in-flight cujo
  intent-id ≠ guard E não-consumida).

**Invariante alvo (o que o fix deve garantir, NÃO a linha exata):**
- Quando há response de apply-confirm pendente e o engine está em replay, o
  pipeline ALCANCA o apply-confirm e CONSOME a response (aplica a mutação),
  sem o draft-resume guard nem o category-menu intervirem com um intent
  divergente.
- Re-entrada HUMANA genuína (sem response in-flight) continua mostrando o
  draft-resume guard.

**Pointers exatos + semântica (executor confirma o ponto mínimo após D1):**
- O draft-resume guard (L247) usa `host_is_replaying(project_root,
  _draft_confirm_id)`. Hoje ele adota o draft em QUALQUER replay — inclusive
  quando a response in-flight é a do apply-confirm. Isso o leva a re-navegar.
  Opções de fix a avaliar (o executor escolhe a mínima que faz D1 passar SEM
  regredir os testes de resume existentes):
  - (a) No bloco de adoção do draft sob replay (L248 `working = draft`),
    quando a response in-flight corresponde ao apply-confirm id, pular a
    re-navegação pelo category-menu e ir direto ao bloco de apply (extrair o
    bloco apply L377-443 num caminho alcançável que CONSOME a response do
    apply-confirm). Isto é simétrico ao R4: o guard já sabe "estou em replay";
    falta rotear pro prompt dono da response.
  - (b) Adicionar guard `host_is_replaying` no apply-confirm (L397) de forma
    que, sob replay com a response do apply-confirm pendente, o
    `question.confirm` consuma essa response (em vez do category-menu intervir
    antes). Verificar como `question.confirm` reconcilia o id — o
    `stable_intent_id` do apply-confirm já é derivado na L384-393; a response
    plantada tem esse id; o pipeline precisa CHEGAR lá sem emitir outro intent
    no meio.
  - O ponto mínimo provável é rotear, durante o replay do draft-resume guard,
    direto pro caminho de apply quando a response in-flight ≠ category-menu E
    == apply-confirm id. Confirmar lendo `_choose_categories` (L284) e como
    ele emite o category-menu intent — é ele que colide no meio.
- Manter o gate de NAVEGAÇÃO existente (R4) intacto — não regredir
  `test_draft_confirm_suppressed_during_host_replay`.

**Steps:**

1. GREEN — aplicar o fix mínimo escolhido em `engine/reconfigure.py`,
   guiado pelo invariante e pelos pointers acima, APÓS confirmar com o repro
   D1 qual prompt o pipeline alcança hoje (instrumentar com
   `_run_reconfigure_expected_mismatch_id` revela o id pedido).

2. Roda GREEN:
   `.venv/bin/pytest tests/unit/test_reconfigure_apply_via_replay.py -x`
   Esperado: PASS (deadlock resolvido — mutação aplicada, sem mismatch).

3. Regressão (crítica — não quebrar resume nem navegação R4):
   `.venv/bin/pytest tests/unit/test_engine_reconfigure_resume.py -q`
   Esperado: PASS (todos, incl.
   `test_draft_confirm_suppressed_during_host_replay`,
   `test_resume_from_checkpoint`).
   `.venv/bin/pytest tests/integration/test_reconfigure_multi_axis.py -q`
   Esperado: PASS.

4. Commit: `fix(reconfigure): apply via loop canônico consome response sem mismatch (P-18)`

---

## Grupo E — Doc-sync consolidado (1 task)

### Task E1 — CHANGELOG + handoff + README + 04-pending

**Files:**
- Modify: `CHANGELOG.md`, `docs/design/08-session-handoff.md`,
  `README.md`, `docs/design/04-pending.md`

**Steps (sem código — doc-sync, Mandamento #6):**

1. `CHANGELOG.md` `## [Unreleased]`:
   - `### Fixed`:
     - "Phase-lock liberado no plan-complete via `release_phase_lock` —
       `forge implement` não bate mais ERR_LOCKED stale `by 'None'` (P-17)."
     - "Mensagem de erro de phase-lock mostra o holder real via
       `current_phase_lock` (sentinel-first) em `implement` e `plan` (P-17)."
     - "`forge qa` Phase 0 popula `snapshot/` — `snapshot_artefacts` recursa
       em diretórios de scope (P-19)."
     - "`conductor-handoff.json` carrega `snapshot`/`config_snapshot`/
       `auditors` conforme contrato do `qa-conductor.md` (P-20)."
     - "`forge reconfigure` aplica mutações via loop canônico AI-first —
       `host_is_replaying` estendido ao apply path (P-18)."
   - `### Added`:
     - "Validators reais do card `compose-screens`: `check-no-suppress`
       (bloqueia `@Suppress` em Compose) e `check-screen-layout` (par
       `{Screen}Screen.kt`+`{Screen}Content.kt`) — eram stubs Phase 5 (P-24)."

2. `docs/design/08-session-handoff.md`:
   - `**Última atualização:**` → `2026-06-19 (v1.5.0 — pilot R6 blockers)`.
   - `**Estado:**` → reflete P-17/18/19/20/24 fechados; QA snapshot+handoff
     reais; reconfigure apply via AI-first funcional.
   - Atualizar counts de teste (rapid/integration/e2e) com o valor real após
     a suíte (rodar `.venv/bin/pytest -m 'not integration and not e2e' -q |
     tail -1` + lanes integration/e2e) — registrar os 3 números.

3. `README.md`:
   - Seção "Limites conhecidos": REESCREVER as linhas stale que dizem
     "`forge implement` é stub manual — Apply Mode é Phase 6" e "plan.py/
     implement.py narram fluxo... integração Anthropic API é Phase 6". O
     piloto R5 confirmou (D4/D5) que plan e implement são fluxos AI-first
     REAIS dirigidos pelo host. Substituir por descrição correta do modelo
     CC-fronted. Atualizar counts de teste/validators/cards se mudaram
     (drift de stats notado no report — reconciliar contagens).

4. `docs/design/04-pending.md`:
   - Riscar/marcar fechados: P-17, P-18, P-19, P-20, P-24.
   - Anotar DEFERIDOS (decisão do mantenedor): P-21 (validator-claim
     fixture-extension mapeia mal scripts Python de card), P-22 (`must_pass`
     sem path / resolver implícito não documentado), P-23 (degraded-mode da
     Phase 3 sandbox não especificado no contrato). Marcar como gaps de
     CONTRATO do `qa-conductor.md` a endereçar em doc-sync futuro.

5. Verificação doc-sync: confirmar checklist de `.claude/rules/doc-sync.md`
   (CHANGELOG ✓, handoff ✓, README stats ✓, 04-pending ✓).

6. Commit: `docs: doc-sync pilot R6 blockers (P-17/18/19/20/24 + defer P-21..23)`

---

## Self-review

**Spec coverage (todo finding → ≥1 task):**
- P-17 → A1 (release lock) + A2 (mensagem holder real). ✓
- P-18 → D1 (repro) + D2 (fix apply via replay). ✓
- P-19 → B1 (snapshot recursa em dir). ✓
- P-20 → B2 (handoff carrega contrato). ✓
- P-24 → C1 (check-no-suppress) + C2 (check-screen-layout). ✓
- P-21/22/23 → Grupo E (deferidos em 04-pending, decisão do mantenedor). ✓

**TDD por grupo de código:**
- A: RED→GREEN em A1 e A2. ✓
- B: RED→GREEN em B1 e B2. ✓
- C: RED→GREEN em C1 e C2 (fixtures Kotlin tmp dir). ✓
- D: D1 é o RED isolado (repro do deadlock), D2 é o GREEN. ✓

**Placeholder scan:** sem `TODO`/`FIXME`/`...` em blocos de código do plano.
Os `{Screen}`, `<slug>`, `<path>`, `<run-id>` são sintaxe de contrato/template
do destino (verbatim), não placeholders pendentes. Comandos pytest têm path
concreto + expected FAIL/PASS.

**Type/name consistency:** `release_phase_lock`, `current_phase_lock`,
`snapshot_artefacts`, `_write_conductor_handoff`, `host_is_replaying`,
`_CORE_AUDITORS`, `SUPPRESS_RE`, `SCREEN_RE`, `CONTENT_RE`,
`COMPOSE_PATH_SEGMENTS` — grafia consistente entre tasks.

**Reuse-first (Mandamento #3):** A reusa `release_phase_lock`/`current_phase_lock`
(não cria helper); B estende `snapshot_artefacts` + extrai `_copy_one` DRY
intra-módulo; C copia a forma do koin validator (scripts subprocess isolados —
constante local aceitável); D reusa `host_is_replaying`. Documentado.

**Pontos onde assumi algo (validar no plan-auditor):**

1. **A1 — extração de `_finalize_planned`:** assumi que pode ser necessário
   extrair um helper testável do bloco plan-complete. Deixei a critério do
   executor (testar via `run` vs helper). Se o plan-auditor preferir contrato
   rígido, fixar a decisão.
2. **B2 — `config_snapshot` = qa: section inteira:** assumi que o
   `config_snapshot` do contrato é a section `qa:` da workflow-config
   (congelada). O contrato (`qa-conductor.md` L51) diz "qa: section da
   workflow-config no momento da run" — alinhado. Confirmar se deve incluir
   mais que a section qa:.
3. **B2 — `auditors` = 4 core hard-coded + filtro `extensions_disabled`:**
   assumi que os 4 core são canônicos e que extensões ativas viriam de cards
   `qa-extensions`. Não há um registry de extensões plugado no handoff hoje;
   listei só os 4 core + filtro defensivo. Se o auditor precisar das extensões
   reais, é trabalho adicional (não diagnosticado no report) — sinalizar.
4. **D1 — nível do repro (unit vs e2e):** assumi que o deadlock pode precisar
   de e2e subprocess pra reproduzir deterministicamente (o pipeline atravessa
   category-menu antes do apply-confirm). Deixei a escolha do nível ao
   executor, condicionada a reproduzir o exit 1/mismatch. Validar se o
   plan-auditor exige nível fixo.
5. **D2 — ponto exato de inserção do guard:** por instrução explícita do
   prompt, NÃO chutei a linha; descrevi o invariante + pointers + opções (a)/(b)
   e deixei o executor confirmar após D1. Isto é deliberado (máquina de estados
   delicada), não vagueza.
6. **C — escopo Compose por segmentos de path:** assumi `/androidApp/` e
   `/composeApp/src/` como segmentos canônicos de Compose UI (espelhando o
   docstring dos stubs originais). Se o MeoBonsai usar outro layout, o escopo
   precisaria de ajuste — mas os stubs já documentavam esses paths.
