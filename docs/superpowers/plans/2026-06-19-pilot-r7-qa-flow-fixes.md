# Plan: pilot-r7 — forge qa flow fixes (F-1..F-5)

> **Branch/PR (nota pro executor, NÃO pro planner):** o R7 vai numa branch
> dedicada off o tip atual de `fix/pilot-r1-init-unblock` (que carrega os
> fixes do R6, incl. P-19/P-20 necessários pra validar `forge qa` real). PR
> separado, stacked sobre #26 ou main — decisão do orquestrador no handoff.
> NÃO é trabalho do executor criar a branch a partir deste plano; só registrar
> que o trabalho assume esse ponto de partida.

> **Voz:** mentor calmo em todo artefato gerado (template, agente, spec,
> mensagens). Sem voz corporativa, sem emoji decorativo.

---

## Goal

Destravar o fluxo `forge qa` que o piloto IA-first expôs em 5 pontos. Após
este plano:

1. **F-1** — o vetor validator-claim (o headline "validator que mente") deixa
   de ser INERTE pra validators forge reais. O sandbox monta um mini
   project-tree e invoca o validator com `--project-root <mini-tree>`, em vez
   de passar a fixture como argumento posicional (que validators argparse
   rejeitam com exit 2 sem nunca ler a fixture).
2. **F-2** — resume real no engine: re-invocar `forge qa` numa run existente
   reata a run tree e continua da phase apropriada (Phase 3 sandbox ou Phase 5
   emit), em vez de criar uma run nova. O contrato do `qa-conductor.md`
   (`re-invoque ... resume=phase-3`) passa a ter lastro no engine.
3. **F-3** — `_finalize_qa_report` computa `run.duration_s` (hoje só escreve
   `finished_at`; `validate_qa_report` exige `duration_s`).
4. **F-4** — `evidence.sandbox_result` é hidratado deterministicamente no
   engine pros findings validator-claim draft que têm fixture executável,
   casando com `sandbox-results.json`. Hoje só breach/timeout derivam
   `sandbox_result`; o draft validator-claim sobrevive com `null` e perde o
   audit trail do subprocess.
5. **F-5** (doc-only) — alinhar a menção stale a "exit 8" no `qa-conductor.md`
   (e no spec + docstring do engine) pro contrato real pós-C3
   EXIT-2-COLLISION: BLOCK → exit 1 + `[FORGE-ERR:QA-BLOCK]`.

**Anti-goal:** não tocar `docs/design/01-decisions.md`. Não introduzir CI mode
nem flags de comportamento de domínio além do estritamente decidido (ver
§Assumptions sobre Decisão 10 / row 32 — ponto crítico pro F-2). Não mudar a
rubric de severity, o fingerprint canonical-form, nem o cascade de
`forge verify`.

---

## Architecture

### Estado atual relevante (lido, não inventado)

- **Sandbox** (`engine/qa/sandbox.py`): `run_sandbox(run_dir, fixtures, *,
  budget_total_s, per_validator_s, extras)`. Por fixture invoca
  `subprocess.run([sys.executable, validator_path.resolve(),
  input_path.resolve()], cwd=run_dir/"fixtures", env=_hardened_env(...),
  timeout=remaining, check=False)`. Hardening Decisão 30/31: `sitecustomize.py`
  chdir/fchdir guard via PYTHONPATH (`_write_chdir_guard`),
  `_validate_paths_inside_sandbox` (input precisa resolver dentro de
  `run_dir/fixtures`; `validator_path` é exceção legítima — canon de produção),
  env allowlist via `build_safe_env` (sem PYTHONPATH herdado). `Fixture`
  dataclass frozen: `name: str`, `input_path: Path`, `validator_path: Path`.
- **Run handler** (`engine/qa/__init__.py`): `run_qa(raw_target, *,
  project_root, workflow_config) -> int`. Phase 0 cria run tree + skeleton +
  handoff. Resume hoje é SÓ via `find_resumable_run` (auto, exige
  `checkpoint.json` + `qa-report.json verdict=pending`); checkpoint só é
  escrito em SIGINT (`_sigint_checkpoint`). Após Phase 0 limpo (exit 0, sem
  checkpoint), re-invocação cria run NOVA. Se `findings/*.json` presentes:
  lê drafts → lê `sandbox-results.json` → `hydrate_sandbox_results` +
  `findings_from_sandbox_results` (só geram breach/timeout) → `synthesize` →
  `_finalize_qa_report` → `_print_verdict_block` → exit `fail_with_tag(
  ERR_QA_BLOCK)` se BLOCK senão 0.
- **Synthesis** (`engine/qa/synthesis.py`): `synthesize(draft_findings)`;
  `findings_from_sandbox_results` JÁ popula `evidence.sandbox_result` mas só
  pra status `sandbox-breach`/`timeout` (não pra validator-claim draft).
- **CLI** (`engine/cli.py` `_qa_run`): hoje ignora tudo além de `argv[0]`
  (docstring cita "Decisão 10: no flags"). Chama `run_qa(raw_target, ...)`.
- **Validator de finding** (`validators/validate_qa_finding.py`): vector
  `validator-claim` exige `evidence.sandbox_result` presente; aceita `None`
  como placeholder de draft (pula validação interna); se dict, exige
  `exit_code:int`, `stdout:str`, `stderr:str`, `duration_s:number`.
- **Validator de report** (`validators/validate_qa_report.py:62`): `run` exige
  `id, scope, config_snapshot, started_at, finished_at, duration_s`.
- **Conductor** (`agents/qa-conductor.md`): Phase 3 diz "re-invoque
  `engine.qa.run_qa(run_id, resume='phase-3')`"; Phase 5 idem com
  `resume='phase-5'`; linha 168 diz "exit code 0 (PASS/FLAG) ou 8 (BLOCK)"
  (stale).

### Forma alvo

- **F-1:** `Fixture` ganha campo opcional `tree_rel_path: str | None = None`
  (path relativo, dentro do mini-tree, onde o conteúdo da fixture é
  materializado). `run_sandbox` passa a:
  1. Materializar, por fixture executável de validator-claim, um mini-tree sob
     `run_dir/fixtures/<fixture.name>/` contendo o arquivo que o validator
     deve escanear em `tree_rel_path`.
  2. Invocar `[sys.executable, validator_path.resolve(), "--project-root",
     <mini-tree>.resolve()]` quando `tree_rel_path` está setado; manter a
     invocação posicional legada quando `tree_rel_path is None` (compat com
     fixtures que ainda usam input posicional — chaos).
  3. `_validate_paths_inside_sandbox` continua valendo: o mini-tree e o
     arquivo materializado moram DENTRO de `run_dir/fixtures` (containment
     check intacto). O `--project-root` aponta pra dentro do sandbox, nunca pro
     projeto real.
  - Template + auditor passam a descrever a fixture como "arquivo(s) colocado(s)
    num tree que o validator escaneia", com `tree_rel_path` declarado.
  - Spec §5.3 atualizada pro contrato `--project-root`.
- **F-2:** `run_qa` ganha param keyword-only `resume_run: str | None = None`.
  Quando setado, pula Phase 0 (não cria run nova), localiza o run dir
  existente por run_id sob `.planning/qa/<sanitized-target>/<run_id>/`, reata
  via `_reattach_run_tree`, e infere a phase pelo estado da run tree:
  - `findings/*.json` presentes E `sandbox-results.json` AUSENTE → roda Phase 3
    (sandbox) e devolve controle (escreve nada de synthesis — Phase 3 é
    core+conductor handshake). _(ver Assumption A-2 sobre como Phase 3 "roda"
    hoje no engine.)_
  - `qa-report.json` com `verdict != "pending"` (synthesizer já rodou) → roda
    Phase 5 (emit + finalize + verdict block).
  - Caso contrário (findings + sandbox-results presentes, verdict pending) →
    segue o caminho synthesis→emit já existente (equivale a "Phase 4+5").
  - CLI `_qa_run` ganha parsing de `--resume-run <id>` _(ver Assumption A-1:
    conflito com Decisão 10 / row 32 — REQUER veredito do orquestrador antes
    de implementar a forma de flag)_.
  - `qa-conductor.md` reescrito pra usar o entrypoint real de resume.
- **F-3:** `_finalize_qa_report` lê `run.started_at` do skeleton, parseia,
  computa `(finished - started).total_seconds()`, escreve `run.duration_s`
  (float, >= 0). Degradação graciosa se `started_at` ausente/malformado:
  `duration_s = 0.0` + segue (não derruba finalize).
- **F-4:** novo helper em `engine/qa/synthesis.py`
  (`hydrate_validator_claim_evidence(draft_findings, sandbox_stubs)`) que, pra
  cada draft com `vector == "validator-claim"` e `evidence.sandbox_result is
  None`, casa com um stub por basename de `evidence.fixture_path` ↔
  `stub.fixture_name`, e popula `evidence.sandbox_result` com `{exit_code,
  stdout, stderr, duration_s}`. Chamado em `run_qa` ANTES de `synthesize`.
- **F-5:** edição textual de `qa-conductor.md` (linha do "exit 8"), spec §5.5,
  e docstrings de `run_qa` em `engine/qa/__init__.py` (doc-only, sem mudança de
  comportamento — engine já retorna `fail_with_tag(ERR_QA_BLOCK)` = exit 1).

---

## Tech Stack

- Python 3 (engine core), `pytest` via **`.venv/bin/pytest`** (canônico — tem
  json5 + deps; system pytest gera false fail signals).
- Markers: `qa` cruza múltiplos módulos → `@pytest.mark.integration` quando o
  teste exercita run tree + synthesis + validators juntos; subprocess CLI →
  `@pytest.mark.e2e`; unit puro de helper isolado → sem marker.
- Sem libs novas. Reuso obrigatório: `engine.qa._common.utc_iso_z`,
  `engine.qa.checkpoint`, `engine.qa.ingest.sanitize_scope_target`,
  `engine.qa.synthesis.hydrate_sandbox_results`,
  `validators.validate_qa_finding`, `validators.validate_qa_report`. Antes de
  criar helper de parse de timestamp, `grep -rn "fromisoformat\|strptime"
  engine/qa/` — reusar se existir.

---

## Global Constraints

- **TDD obrigatório** (`.claude/rules/testing.md`): teste FALHANDO primeiro,
  rodar e confirmar FAIL, implementar mínimo, confirmar PASS, rodar suite. Cada
  task de código abaixo lista o comando `.venv/bin/pytest <path>::<test>` com
  expected FAIL→PASS.
- **NÃO tocar `docs/design/01-decisions.md`.** Se a implementação exigir
  revisitar Decisão 10/27/30, PARE e escale 3-caminhos (ver §Assumptions).
- **Preservar hardening Decisão 30/31 no F-1** — toda mudança no sandbox tem
  step explícito confirmando que `_validate_paths_inside_sandbox`, chdir guard,
  env allowlist e budget/timeout continuam valendo. Teste de breach continua
  passando (Task A.4).
- **Doc-sync no grupo final** (F), não espalhado nas tasks de código.
- **Escopo contido** — cada task lista `Files` exatos. Não refatorar além do
  pedido. `docs/schemas/**` é load-bearing — F-1/F-4 NÃO devem precisar tocar
  schemas (sandbox_result já está no schema qa-finding; se algum executor achar
  que precisa, PARE e escale).
- **`forge verify` cascade verde** + suite verde antes de "pronto".

---

## Ordem de execução (justificada)

**C → D → E → A → B.**

- C (F-3) e D (F-4) são baratos, sem dependência mútua, ganham momentum e
  validam o ciclo TDD cedo.
- E (F-5) é doc-only trivial, sem dependência.
- A (F-1) é design pesado no sandbox (segurança) — vem depois do aquecimento.
- B (F-2) é o mais pesado (CLI + engine + agente) E carrega o conflito de
  Decisão 10 (Assumption A-1), que pode bloquear até veredito do orquestrador.
  Por isso vem por último: não trava os 4 fixes anteriores.

Não há dependência de código entre os grupos: F-3 toca `_finalize_qa_report`,
F-4 toca synthesis + call-site em `run_qa`, F-1 toca sandbox+template+auditor,
F-2 toca CLI+`run_qa` resume branch. Único cuidado de merge: F-2 e F-4 ambos
editam `engine/qa/__init__.py` em regiões diferentes (resume branch no topo de
`run_qa` vs. call-site de synthesis no meio). Executor faz commits atômicos por
grupo; conflito textual, se houver, é trivial.

---

## Group C — F-3: `_finalize_qa_report` computa `duration_s`

### Task C.1 — duration_s no finalize

**Files:**
- `engine/qa/__init__.py` (`_finalize_qa_report`)
- `tests/qa/test_finalize_qa_report.py` (criar OU estender se já existir —
  `grep -rln "_finalize_qa_report\|finalize_qa" tests/` antes de criar)

**Interfaces:**
- Consumes: `run_tree.root / "qa-report.json"` (skeleton com
  `run.started_at` ISO-8601 Z), `SynthesisResult`.
- Produces: `qa-report.json` com `run.duration_s: float` (>= 0) +
  `run.finished_at` (já existia).

**Steps (TDD):**

1. **RED** — escrever teste que:
   - cria um `RunTree` mínimo num `tmp_path` (reusar fixture `tmp_project`/
     helper de `tests/qa/conftest.py` se existir; senão montar `run_tree.root`
     + escrever skeleton via `_write_qa_report_skeleton`).
   - força `started_at` num valor conhecido no passado (re-escreve o skeleton
     com `run.started_at = "2026-06-19T12:00:00Z"`).
   - chama `_finalize_qa_report(run_tree, SynthesisResult(findings=[],
     verdict="PASS", by_severity={k:0 for k in
     ("critical","high","medium","low","info")}, by_vector={"spec-vs-spec":0,
     "coverage":0,"chaos":0,"validator-claim":0}))`.
   - lê `qa-report.json`, assert `"duration_s" in report["run"]`, assert
     `isinstance(report["run"]["duration_s"], (int, float))`, assert
     `report["run"]["duration_s"] >= 0`.
   - assert `validate_qa_report(report)` NÃO levanta
     `QAReportValidationError`.
   - Marker: `@pytest.mark.integration` (exercita finalize + validator juntos).

2. Rodar: `.venv/bin/pytest tests/qa/test_finalize_qa_report.py::test_finalize_computes_duration_s -x`
   → **expected FAIL** (`duration_s` ausente → KeyError no assert OU
   `validate_qa_report` levanta "run.duration_s ausente").

3. **GREEN** — em `_finalize_qa_report`, após montar `run_block`:
   - ler `started_raw = run_block.get("started_at")`.
   - se `started_raw` é str: parsear com `datetime.fromisoformat` tratando o
     sufixo `Z` (substituir `Z`→`+00:00` antes do parse, pattern já usado em
     `engine.qa._common`/`run_id` — confirmar via grep e reusar helper se
     existir). `finished` = `datetime.now(timezone.utc)` (mesma fonte que
     `utc_iso_z` usa internamente — confirmar pra coerência).
   - `run_block["duration_s"] = max(0.0, (finished - started).total_seconds())`.
   - degradação graciosa: se `started_raw` ausente OU parse falha
     (`ValueError`/`TypeError`), `run_block["duration_s"] = 0.0` (não derruba
     finalize; audit trail incompleto é aceitável, alinhado ao padrão "skeleton
     ausente" já existente no método).
   - `finished_at` deve ser computado da MESMA referência `finished` que entrou
     em `duration_s` (consistência: `finished_at` e `duration_s` não podem
     divergir por jitter de duas chamadas `utc_iso_z()`).

4. Rodar mesmo comando → **expected PASS**.

5. Rodar suite qa: `.venv/bin/pytest tests/qa/ -m "not e2e" -q` → verde.

**Verify:** `.venv/bin/pytest tests/qa/test_finalize_qa_report.py -x` PASS +
`validate_qa_report` aceita o report finalizado.

**Done:** `qa-report.json` finalizado carrega `run.duration_s` coerente
(>= 0, derivado de `finished - started`); `validate_qa_report` passa.

**Commit:** `fix(qa): _finalize_qa_report computa run.duration_s (F-3)`

---

## Group D — F-4: hidratar `evidence.sandbox_result` em findings validator-claim

### Task D.1 — helper de hidratação determinística

**Files:**
- `engine/qa/synthesis.py` (novo helper `hydrate_validator_claim_evidence`)
- `tests/qa/test_synthesis.py` (estender — `grep -rln "def test" tests/qa/test_synthesis.py` pra anexar)

**Interfaces:**
- Consumes: `draft_findings: list[dict]` (com possíveis vector=validator-claim
  e `evidence.sandbox_result is None`), `stubs: list[SandboxResultStub]`
  (de `hydrate_sandbox_results`).
- Produces: mesma lista, com `evidence.sandbox_result` populado nos drafts
  validator-claim que casam um stub. Não muta o input (retorna cópias rasas
  dos findings tocados, pattern de `dedup_findings`).

**Steps (TDD):**

1. **RED** — teste:
   - draft = um finding `vector="validator-claim"`, `evidence={"auditor":
     "validator-claim", "auditor_reasoning": "...", "fixture_path":
     "fixtures/validator-claim-foo.yaml", "sandbox_result": None}`, demais
     campos válidos (id `vc-0001`, fingerprint 64-hex, title, description,
     scope.files, proposed_evolution `qa-finding-validator-claim`, created_at
     ISO-Z).
   - stub = `SandboxResultStub(fixture_name="validator-claim-foo",
     status="ok", exit_code=0, stdout="", stderr="", duration_s=0.3)`.
   - chamar `hydrate_validator_claim_evidence([draft], [stub])`.
   - assert resultado[0]`["evidence"]["sandbox_result"]` é dict com
     `exit_code==0`, `stdout==""`, `stderr==""`, `duration_s==0.3`.
   - passar resultado[0] por `validate_qa_finding(...)` → NÃO levanta.
   - segundo caso: draft validator-claim SEM stub correspondente → permanece
     `None` (e `validate_qa_finding` ainda aceita None em draft) — não inventa
     evidência.
   - terceiro caso: draft de OUTRO vector (chaos) → intocado.
   - Marker: sem marker (unit puro de helper).

   **Matching rule (explícita pro executor):** o basename a casar é
   `Path(evidence["fixture_path"]).stem` (sem extensão) ↔ `stub.fixture_name`.
   Confirmar contra o nome que o auditor gera
   (`validator-claim-<short>-<scenario>.yaml`) e o `fixture_name` que o
   conductor serializa em `sandbox-results.json`
   (`agents/qa-conductor.md` exemplo usa `"validator-claim-traversal"`, sem
   extensão). Se `fixture_path` ausente no draft, pular (não casar por
   adivinhação).

2. Rodar: `.venv/bin/pytest tests/qa/test_synthesis.py::test_hydrate_validator_claim_evidence -x`
   → **expected FAIL** (helper não existe → ImportError/AttributeError).

3. **GREEN** — implementar `hydrate_validator_claim_evidence(draft_findings,
   stubs)`:
   - build index `by_name = {s.fixture_name: s for s in stubs}` (último vence
     em colisão — documentar; colisão não esperada).
   - pra cada finding dict: se `f.get("vector") != "validator-claim"` →
     append intocado.
   - `ev = f.get("evidence")`; se não dict → intocado.
   - se `ev.get("sandbox_result") is not None` → intocado (já hidratado pelo
     conductor; não sobrescrever).
   - `fp = ev.get("fixture_path")`; se não str → intocado.
   - `key = Path(fp).stem`; `stub = by_name.get(key)`; se None → intocado.
   - construir cópia rasa do finding + cópia rasa do evidence; setar
     `evidence["sandbox_result"] = {"exit_code": int(stub.exit_code) if
     stub.exit_code is not None else <ver nota>, "stdout": stub.stdout,
     "stderr": stub.stderr, "duration_s": float(stub.duration_s)}`.
   - **Nota exit_code:** `validate_qa_finding` exige `exit_code: int` quando
     `sandbox_result` é dict (não aceita None dentro do dict). Se
     `stub.exit_code is None` (ex.: status timeout/skipped-budget), NÃO
     hidratar com dict inválido — deixar `sandbox_result` como `None`
     (draft-válido) e seguir. Casar só stubs com `exit_code` int (tipicamente
     `status=="ok"`/`"error"` com código real). Cobrir esse caso no teste
     RED (quarto caso: stub com `exit_code=None` → finding permanece `None`).

4. Rodar mesmo comando → **expected PASS**.

### Task D.2 — wire no call-site de `run_qa`

**Files:**
- `engine/qa/__init__.py` (`run_qa`, região onde `all_findings` é montado e
  `sandbox-results.json` é lido, ~L336-382)
- `tests/qa/test_run_qa_synthesis.py` (criar OU estender — `grep -rln
  "run_qa" tests/qa/` pra escolher arquivo)

**Interfaces:**
- Consumes: `all_findings` (drafts lidos de `findings/*.json`), `stubs` (de
  `hydrate_sandbox_results` sobre `sandbox-results.json`).
- Produces: `all_findings` hidratado ANTES de `synthesize(all_findings)`.

**Steps (TDD):**

1. **RED** — teste integração:
   - montar run tree num tmp com: `findings/validator-claim.json` contendo um
     finding draft validator-claim (`sandbox_result: null`, `fixture_path:
     "fixtures/validator-claim-foo.yaml"`); `sandbox-results.json` com entry
     `{"fixture_name": "validator-claim-foo", "status": "ok", "exit_code": 0,
     "duration_s": 0.2}`; skeleton `qa-report.json` (verdict pending).
   - chamar `run_qa(target, project_root=..., workflow_config={"qa":
     {"enabled": True}})` no modo "findings presentes".
   - ler `qa-report.json` final; localizar o finding validator-claim; assert
     `evidence.sandbox_result` é dict com `exit_code==0`.
   - assert `validate_qa_report(report)` NÃO levanta.
   - Marker: `@pytest.mark.integration`. Scrub env (`CLAUDECODE`,
     `OPENCODE_*`, `CODEX`, `CURSOR_*`) + pin host se necessário (memory:
     subprocess env scrub) — confirmar se este teste subprocessa; se for
     in-process `run_qa`, scrub não é necessário.

2. Rodar: `.venv/bin/pytest tests/qa/test_run_qa_synthesis.py::test_validator_claim_evidence_hydrated_in_report -x`
   → **expected FAIL** (sandbox_result fica null no report).

3. **GREEN** — em `run_qa`, após ler `sandbox-results.json` e gerar `stubs =
   hydrate_sandbox_results(...)` (esse bloco hoje só usa `stubs` pra
   `findings_from_sandbox_results`): reusar os MESMOS `stubs` pra chamar
   `all_findings = hydrate_validator_claim_evidence(all_findings, stubs)`
   ANTES de `synthesize(all_findings)`. Cuidado: hoje `stubs` é computado
   dentro do `if sandbox_results_file.exists():` — extrair `stubs` pra escopo
   acessível pelo call-site de hidratação (default `[]` quando o arquivo não
   existe). Quando não há sandbox-results, `hydrate_validator_claim_evidence`
   com `stubs=[]` é no-op (drafts permanecem `None`, válidos).

4. Rodar mesmo comando → **expected PASS** + suite qa verde.

**Verify:** `.venv/bin/pytest tests/qa/test_synthesis.py tests/qa/test_run_qa_synthesis.py -x` PASS.

**Done:** finding validator-claim com fixture executável e stub correspondente
chega ao `qa-report.json` final com `evidence.sandbox_result` dict populado;
`validate_qa_finding` e `validate_qa_report` passam; drafts sem stub (ou stub
sem exit_code int) permanecem `null` válido.

**Commit:** `fix(qa): hidrata evidence.sandbox_result em findings validator-claim (F-4)`

---

## Group E — F-5: exit 8 stale no conductor (doc-only)

### Task E.1 — alinhar "exit 8" → exit 1 + tag

**Files:**
- `agents/qa-conductor.md` (linha ~168 da Phase 5)
- `docs/superpowers/specs/2026-06-05-forge-qa-design.md` (§5.5 passo 5 — "8 se
  verdict == BLOCK")
- `engine/qa/__init__.py` (docstrings de `run_qa`: L103 "Retorna exit code
  (0 ou 8)" e L135 "8 (verdict=BLOCK)" — doc-only, sem mudança de
  comportamento; engine já retorna `fail_with_tag(ERR_QA_BLOCK)` = exit 1)

**Steps (sem TDD — doc-only, sem mudança de comportamento de código):**

1. `grep -rn "exit 8\|exit code 8\|(0 ou 8)\|8 (BLOCK)\|8 se verdict\|8 (verdict"
   agents/ docs/superpowers/specs/ engine/qa/ docs/design/` pra varrer TODAS as
   menções stale. Confirmar quais são `forge qa` (algumas referências a "exit
   8" no spec podem ser do Gap 5 / Step 7.5 histórico — preservar contexto
   histórico, alinhar só o contrato VIGENTE de `forge qa`).
2. Em `qa-conductor.md` Phase 5: trocar "sai com exit code 0 (PASS/FLAG) ou 8
   (BLOCK)" por "sai com exit code 0 (PASS/FLAG) ou 1 + `[FORGE-ERR:QA-BLOCK]`
   em stderr (BLOCK), conforme `docs/design/06-command-surface.md`".
3. Em spec §5.5 passo 5: alinhar o bullet do exit code pro contrato vigente,
   anotando que o "8" original foi superseded pela convenção `fail_with_tag`
   (C3 EXIT-2-COLLISION / W2). NÃO reescrever o spec inteiro — só o bullet
   relevante + nota de superseded.
4. Em `engine/qa/__init__.py`: corrigir as 2 docstrings de `run_qa`.
5. Verify manual: `grep -rn "exit.*8" agents/qa-conductor.md` retorna 0
   menções de "exit 8" como contrato vigente de `forge qa`.

**Done:** nenhuma menção stale a "exit 8" como contrato vigente de `forge qa`;
todas apontam exit 1 + `[FORGE-ERR:QA-BLOCK]`. Sem mudança de comportamento de
engine (verificável: nenhuma linha de código `return`/`exit` alterada).

**Commit:** `docs(qa): exit 8 stale → exit 1 + QA-BLOCK tag no conductor/spec (F-5)`

---

## Group A — F-1: sandbox monta mini-tree + invoca validator com `--project-root`

> **Segurança load-bearing:** este grupo mexe no sandbox de execução
> (Decisão 30/31). Cada task preserva: input/tree DENTRO de `run_dir/fixtures`,
> `_validate_paths_inside_sandbox` intacto, chdir/fchdir guard intacto, env
> allowlist (sem PYTHONPATH herdado) intacto, budget/timeout intactos. Task A.4
> é a confirmação explícita de hardening (breach test continua passando).

### Task A.1 — `Fixture.tree_rel_path` + invocação `--project-root` no sandbox

**Files:**
- `engine/qa/sandbox.py` (`Fixture` dataclass, `_validate_paths_inside_sandbox`,
  loop de `run_sandbox`)
- `tests/qa/test_sandbox.py` (estender — `grep -rln "run_sandbox\|Fixture"
  tests/qa/` pra confirmar arquivo)

**Interfaces:**
- Consumes: `Fixture(name, input_path, validator_path, tree_rel_path=None)`.
- Produces: quando `tree_rel_path` setado, invoca
  `[python, validator_path, "--project-root", <mini_tree>]` com `<mini_tree> =
  run_dir/fixtures/<fixture.name>` materializado a partir de `input_path`;
  quando `None`, mantém invocação posicional legada.

**Steps (TDD):**

1. **RED** — teste:
   - escrever um validator stub `tmp_validator.py` que usa `argparse` com
     `--project-root` (espelha validators forge reais: lê
     `--project-root`, escaneia, exit 0 ou 1; toleraria `--scope`/`--id`). O
     stub escreve em stdout o `--project-root` recebido e dá `exit 1` se achar
     um arquivo `offending.kt` dentro do tree (simula "validator deveria
     falhar").
   - criar `Fixture(name="vc-foo", input_path=<arquivo offending.kt sob
     run_dir/fixtures/vc-foo/src/offending.kt>, validator_path=<tmp_validator>,
     tree_rel_path="src/offending.kt")`.
   - chamar `run_sandbox(run_dir, [fixture], budget_total_s=30,
     per_validator_s=10)`.
   - assert `result.status == "ok"`, `result.exit_code == 1` (validator viu o
     arquivo via `--project-root` e falhou como esperado).
   - segundo caso (legado): `Fixture(... tree_rel_path=None)` com validator
     posicional → invocação posicional preservada (assert que o validator
     recebeu o input como argv posicional, não `--project-root`).
   - Marker: `@pytest.mark.integration` (subprocess real, cruza módulos).

2. Rodar: `.venv/bin/pytest tests/qa/test_sandbox.py::test_run_sandbox_project_root_invocation -x`
   → **expected FAIL** (`Fixture` não tem `tree_rel_path`; invocação ainda
   posicional → validator argparse sai 2 sem ler o arquivo).

3. **GREEN:**
   - adicionar `tree_rel_path: str | None = None` ao `Fixture` (frozen
     dataclass — campo opcional ao final preserva construção posicional
     existente).
   - em `_validate_paths_inside_sandbox`: quando `tree_rel_path` setado,
     validar que `(run_dir/fixtures/<name>/<tree_rel_path>).resolve()` resolve
     DENTRO de `sandbox_cwd` (mesmo `relative_to` guard). O containment check
     passa a cobrir o mini-tree, não só `input_path`. NÃO afrouxar o guard —
     adicionar cobertura, não remover.
   - no loop de `run_sandbox`: quando `fixture.tree_rel_path` setado,
     `mini_tree = sandbox_cwd / fixture.name`; garantir que o arquivo já existe
     em `mini_tree / tree_rel_path` (materialização é responsabilidade do
     conductor/Phase 2 OU de A.1 — ver Assumption A-3; default: o
     `input_path` JÁ é esse arquivo e `mini_tree` é seu ancestral; se
     `input_path` não estiver sob `mini_tree`, é breach). Construir cmd
     `[sys.executable, validator_path.resolve(), "--project-root",
     str(mini_tree.resolve())]`.
   - quando `tree_rel_path is None`: cmd posicional legado (inalterado).
   - `cwd`, `env`, `timeout`, `check=False` inalterados.

4. Rodar mesmo comando → **expected PASS**.

5. Rodar `.venv/bin/pytest tests/qa/test_sandbox.py -x` → toda a suite de
   sandbox verde (regressão dos paths legados).

**Verify:** `.venv/bin/pytest tests/qa/test_sandbox.py -x` PASS.

**Done:** validator com `--project-root` é invocado corretamente e escaneia o
mini-tree dentro do sandbox; fixtures legadas (posicional, `tree_rel_path=None`)
continuam funcionando.

**Commit:** `feat(qa): sandbox invoca validator com --project-root sobre mini-tree (F-1)`

### Task A.2 — template + auditor validator-claim refletem o mini-tree

**Files:**
- `templates/qa-fixture-validator-claim.template.yaml`
- `agents/qa-auditor-validator-claim.md`
- (NÃO tocar os `.py/.kt/.swift` templates a menos que o grep mostre que
  carregam a forma posicional explícita — `grep -n "posicional\|input_path\|
  argv" templates/qa-fixture-validator-claim.template.*`; se carregarem,
  incluir nesta task)

**Interfaces:**
- Produces: contrato de fixture validator-claim que declara `tree_rel_path` e
  descreve "arquivo(s) materializado(s) num mini-tree que o validator escaneia
  via `--project-root`", não "input posicional único".

**Steps (doc/contract — sem pytest; valida via `forge verify` + smoke do
template):**

1. No `template.yaml`: adicionar campo `tree_rel_path: "{{tree_rel_path}}"`
   (path relativo do arquivo dentro do mini-tree, ex.:
   `src/main/kotlin/Offending.kt`). Manter `target_validator`. Atualizar o
   comentário de topo: a fixture descreve o arquivo que o validator deve pegar
   quando escaneia o tree, e `expected_exit_code: 1` (validator deveria
   falhar). Voz mentor calmo no comentário.
2. No `qa-auditor-validator-claim.md`: atualizar §Output (bloco 2 "Fixtures") e
   §Mission pra instruir o auditor a (a) declarar `tree_rel_path`, (b) gerar o
   conteúdo do arquivo no formato/linguagem que o validator escaneia, (c)
   declarar no finding `evidence.fixture_path` apontando o arquivo do mini-tree
   e — quando aplicável — uma nota de que o sandbox invoca via `--project-root`.
   Atualizar o exemplo JSON de finding se referenciar invocação posicional.
3. Confirmar coerência com `agents/qa-conductor.md` §"Após Phase 3" (serializar
   `fixture_name` sem extensão — alinha com a matching rule do F-4 D.1).
4. Verify: `forge verify` cascade verde (templates/auditores não quebram
   validators de schema); smoke manual de leitura do template (sem placeholder
   órfão).

**Done:** template + auditor descrevem o contrato mini-tree + `--project-root`
de forma executável e sem ambiguidade; `forge verify` verde.

**Commit:** `docs(qa): template + auditor validator-claim refletem mini-tree --project-root (F-1)`

### Task A.3 — spec §5.3 atualizada pro contrato `--project-root`

**Files:**
- `docs/superpowers/specs/2026-06-05-forge-qa-design.md` (§5.3, pseudocódigo
  ~L204-264 + prosa do contrato de sandbox)

**Steps (doc-only):**

1. Atualizar o pseudocódigo de `run_sandbox` em §5.3: a invocação muda de
   `[sys.executable, fixture.validator_path, fixture.input_path]` (posicional)
   pra `[sys.executable, fixture.validator_path, "--project-root", <mini-tree
   dentro do sandbox>]` quando a fixture declara `tree_rel_path`. Documentar o
   campo `tree_rel_path` no contrato de `Fixture`.
2. Atualizar a prosa: explicar POR QUE (validators forge usam argparse
   `--project-root`; posicional gera exit 2 e o vetor validator-claim fica
   inerte). Preservar a seção de hardening Decisão 30/31 INTACTA (containment
   agora cobre o mini-tree).
3. NÃO renumerar seções; NÃO tocar §5.4/§5.5 além do necessário.
4. Verify manual: pseudocódigo coerente com `engine/qa/sandbox.py` pós-A.1.

**Done:** spec §5.3 pareada com a implementação A.1 (contrato `--project-root` +
`tree_rel_path` + hardening preservado).

**Commit:** `docs(qa): spec §5.3 sandbox usa --project-root sobre mini-tree (F-1)`

### Task A.4 — confirmação de hardening (breach test verde)

**Files:**
- `tests/qa/test_sandbox.py` (teste de breach — estender, NÃO substituir
  cobertura existente)

**Interfaces:**
- Consumes: `Fixture` com `tree_rel_path` apontando FORA do mini-tree (tentativa
  de traversal) E fixture cujo validator tenta `os.chdir`.
- Produces: `status == "sandbox-breach"` (traversal) e `RuntimeError` do guard
  (chdir) capturado.

**Steps (TDD — segurança):**

1. **RED/regression** — teste:
   - `Fixture(name="evil", input_path=<path FORA de run_dir/fixtures, ex.:
     /tmp/outside.kt>, validator_path=<stub>, tree_rel_path="../../escape.kt")`
     → `run_sandbox` retorna `status == "sandbox-breach"` (o
     `_validate_paths_inside_sandbox` estendido pega o tree_rel_path fora do
     sandbox). Assert sem subprocess disparado.
   - validator stub que chama `os.chdir("/")` → subprocess falha com a
     `RuntimeError` do `_CHDIR_GUARD` (status `ok` com `exit_code != 0` +
     stderr contendo "os.chdir bloqueado"). Confirma guard intacto pós-A.1.
   - reusar/manter qualquer teste de breach pré-existente (grep
     `"sandbox-breach\|chdir\|_validate_paths"` em `tests/qa/test_sandbox.py`).
   - Marker: `@pytest.mark.integration`.

2. Rodar: `.venv/bin/pytest tests/qa/test_sandbox.py -k "breach or chdir or hardening" -x`
   → após A.1 deve passar; se FALHAR, A.1 afrouxou o guard → corrigir A.1 antes
   de prosseguir (este é o gate de segurança).

3. **GREEN** — se A.1 foi feito corretamente, sem código novo aqui além dos
   testes. Se algum guard regrediu, corrigir em `sandbox.py` até verde.

**Verify:** `.venv/bin/pytest tests/qa/test_sandbox.py -x` PASS (incl. breach +
chdir + path-containment do mini-tree).

**Done:** hardening Decisão 30/31 comprovadamente preservado: traversal via
`tree_rel_path` vira `sandbox-breach`; chdir guard intacto; env allowlist e
budget/timeout inalterados (cobertos pelos testes pré-existentes que continuam
verdes).

**Commit:** `test(qa): hardening preservado pós-mini-tree (breach + chdir + containment) (F-1)`

---

## Group B — F-2: resume real no engine

> **⚠ BLOQUEIO POTENCIAL (Assumption A-1):** a forma `--resume-run <id>` (flag)
> conflita com Decisão 10 (zero flags), reafirmada pelo carve-out da Decisão 32
> (row 32): meta-flags only pros read-commands; `qa` é interativo e
> "flags de comportamento de domínio continuam proibidas". `--resume-run` é
> flag de comportamento de domínio. **O executor NÃO deve implementar a forma
> de flag até o orquestrador dar veredito** (3-caminhos em §Assumptions). O
> resume ENGINE-SIDE (param `resume_run` em `run_qa` + inferência de phase)
> NÃO conflita e pode ser implementado independente da decisão de superfície.

### Task B.1 — `run_qa(resume_run=...)` reata run tree + infere phase

**Files:**
- `engine/qa/__init__.py` (`run_qa` — novo param + branch de resume)
- `tests/qa/test_run_qa_resume.py` (criar)

**Interfaces:**
- Consumes: `run_qa(raw_target, *, project_root, workflow_config,
  resume_run: str | None = None)`.
- Produces: quando `resume_run` setado, reata
  `.planning/qa/<sanitize_scope_target(target)>/<resume_run>/` via
  `_reattach_run_tree` (sem `create_run_tree`, sem novo skeleton/handoff) e
  continua da phase inferida.

**Inferência de phase (lida do flow real — confirmar e ajustar se o estado
divergir):**
- `findings/*.json` presentes **E** `sandbox-results.json` AUSENTE → Phase 3
  (sandbox handshake): hoje o engine, nesse estado, escreve o handoff e devolve
  controle pro conductor rodar sandbox. No resume, reatar e devolver controle
  (não criar run nova). _(Assumption A-2: o engine atual NÃO invoca
  `run_sandbox` diretamente — o conductor o faz e escreve `sandbox-results.json`.
  "Rodar Phase 3" no resume = reatar + garantir handoff presente + devolver
  controle. Confirmar contra o flow e ajustar.)_
- `qa-report.json` com `verdict != "pending"` → Phase 5 (emit): re-finaliza +
  imprime verdict block + exit code. _(No estado atual, `verdict != pending` só
  acontece após `_finalize_qa_report`; o resume Phase 5 re-emite idempotente.)_
- senão (findings + sandbox-results presentes, verdict pending) → caminho
  synthesis→emit existente.

**Steps (TDD):**

1. **RED** — dois testes:
   - `test_resume_run_phase3_reattaches`: criar run tree com run_id conhecido
     contendo `findings/validator-claim.json` (1 draft) e SEM
     `sandbox-results.json`; chamar `run_qa(target, ...,
     resume_run=<run_id>)`; assert NÃO foi criada run nova (contar dirs sob
     `.planning/qa/<target>/` antes/depois == igual); assert o run dir reatado é
     o mesmo `<run_id>`; assert handoff presente / controle devolvido (return
     0).
   - `test_resume_run_phase5_emits`: criar run tree com `qa-report.json`
     `verdict="PASS"` (finalizado) + `findings/*.json`; chamar com
     `resume_run=<run_id>`; assert verdict block impresso (capsys) + exit 0;
     assert NÃO criou run nova.
   - Marker: `@pytest.mark.integration`.

2. Rodar: `.venv/bin/pytest tests/qa/test_run_qa_resume.py -x` →
   **expected FAIL** (`run_qa` não aceita `resume_run`; cria run nova).

3. **GREEN** — em `run_qa`:
   - adicionar param keyword-only `resume_run: str | None = None`.
   - quando `resume_run` setado (após `parse_qa_config` + `resolve_scope`):
     pular o bloco de resume-detection automático (`find_resumable_run`) E o
     bloco `create_run_tree`. Localizar
     `run_dir = project_root/".planning"/"qa"/sanitize_scope_target(
     scope.target)/resume_run`. Se não existe → mensagem mentor-calmo
     3-caminhos (run_id não encontrado: listar runs disponíveis / verificar
     target / começar nova) + `return 0`. Se existe → `run_tree =
     _reattach_run_tree(run_dir, <checkpoint ou stub>)`, `snapshot_copied = []`.
   - reusar o bloco existente "findings presentes → synthesis/emit"; a
     inferência de phase cai naturalmente nele (findings presentes → segue;
     ausentes → imprime "dispatch conductor" + return 0). Validar que o
     caminho `verdict != pending` re-emite sem recriar.
   - NÃO duplicar lógica: o branch de resume monta `run_tree` e cai no MESMO
     corpo pós-Phase-0 já existente.

4. Rodar mesmo comando → **expected PASS** + `.venv/bin/pytest tests/qa/ -m
   "not e2e" -q` verde.

**Verify:** `.venv/bin/pytest tests/qa/test_run_qa_resume.py -x` PASS; nenhuma
run nova criada no caminho de resume.

**Done:** `run_qa(resume_run=<id>)` reata a run existente e continua da phase
inferida sem criar run nova; run_id inexistente cai em 3-caminhos mentor-calmo.

**Commit:** `feat(qa): run_qa resume_run reata run tree + infere phase (F-2)`

### Task B.2 — CLI `--resume-run` (CONDICIONADA ao veredito de Decisão 10)

**Files:**
- `engine/cli.py` (`_qa_run`)
- `tests/qa/test_qa_cli.py` OU `tests/e2e/test_qa_resume_e2e.py` (criar —
  subprocess CLI → marker `@pytest.mark.e2e`)

**Pré-condição:** o orquestrador deu veredito em A-1. Se o veredito for
"não usar flag" (forma flagless: positional `resume:<run-id>` ou conversacional
via intent), ESTA task muda de forma — o executor implementa a superfície
aprovada, mantendo B.1 (engine) intacto. Não implementar a forma de flag por
default.

**Interfaces (forma flag, SE aprovada):**
- Consumes: `forge qa <target> --resume-run <run-id>`.
- Produces: `_qa_run` parseia `--resume-run`, repassa `resume_run=<id>` a
  `run_qa`.

**Steps (TDD — assumindo forma aprovada):**

1. **RED** — teste e2e: criar run tree finalizada (verdict PASS) num
   `tmp_project` inicializado; subprocessar `forge qa <target> --resume-run
   <run-id>` (env scrub: `CLAUDECODE`/`OPENCODE_*`/`CODEX`/`CURSOR_*` removidos,
   `host: intent-file` pinado via forge-config se o teste exigir determinismo);
   assert exit 0 + verdict block no stdout; assert NÃO criou run nova.
2. Rodar: `.venv/bin/pytest tests/e2e/test_qa_resume_e2e.py -x` →
   **expected FAIL** (`_qa_run` ignora tudo além de `argv[0]`).
3. **GREEN** — em `_qa_run`: parsear `--resume-run <id>` de `argv`
   (sem argparse pesado — varredura simples, consistente com o estilo do
   handler; `--resume-run` consome o próximo token como id). `raw_target` =
   primeiro token posicional não-flag. Repassar `resume_run=resume_id` a
   `run_qa`. Atualizar a docstring do `_qa_run` (a nota "Decisão 10: no flags"
   passa a referenciar o carve-out aprovado — texto exato conforme veredito do
   orquestrador; NÃO inventar; se veredito pendente, NÃO mexer na docstring).
4. Rodar mesmo comando → **expected PASS**.

**Verify:** `.venv/bin/pytest tests/e2e/test_qa_resume_e2e.py -x` PASS.

**Done:** superfície de resume aprovada pelo orquestrador implementada;
`run_qa(resume_run=...)` acessível via CLI na forma decidida.

**Commit:** `feat(qa): superfície CLI de resume (forma aprovada) (F-2)`

### Task B.3 — `qa-conductor.md` usa o resume real

**Files:**
- `agents/qa-conductor.md` (Phase 3 + Phase 5)

**Steps (doc-only):**

1. Trocar "re-invoque `engine.qa.run_qa(run_id, resume='phase-3')`" (Phase 3)
   e "Re-invoca `engine.qa.run_qa(run_id, resume='phase-5')`" (Phase 5) pela
   forma REAL aprovada:
   - se forma flag aprovada: `forge qa <target> --resume-run <run-id>`.
   - se forma flagless: a invocação aprovada.
   - se o conductor invoca Python direto (tem tool Bash): documentar
     `run_qa(<target>, project_root=..., workflow_config=...,
     resume_run="<run-id>")` com os kwargs reais (NÃO `resume="phase-3"` —
     esse contrato não existe no engine).
2. Garantir consistência com a inferência de phase de B.1 (o conductor não
   passa "phase-3"/"phase-5" — o engine infere pelo estado da run tree).
3. Atualizar §"Após Phase 3" se a forma de invocação mudou.
4. Verify manual: o contrato do conductor é executável (nenhum kwarg
   inexistente; alinhado a B.1/B.2).

**Done:** `qa-conductor.md` invoca o resume real do engine (kwargs/CLI que
existem); contrato "resume=phase-N" fantasma eliminado.

**Commit:** `docs(qa): conductor usa resume real do engine (F-2)`

---

## Group F — doc-sync + versionar plano

### Task F.1 — doc-sync (Mandamento #6)

**Files:**
- `CHANGELOG.md` (`## [Unreleased]`)
- `docs/design/08-session-handoff.md` (Última atualização + Estado + Conhecidos
  limites se aplicável)
- `docs/design/04-pending.md` (fechar/atualizar gaps do R7 referentes a F-1..F-5
  se existirem; anotar limitação nova se a forma de resume ficar flagless por
  decisão)
- `README.md` (SE stats mudarem — test count; este plano ADICIONA testes →
  atualizar count conforme `.venv/bin/pytest -m 'not integration and not e2e'
  -q | tail -1` + integration + e2e counts)
- (NÃO tocar `docs/design/01-decisions.md`)

**Steps:**

1. `CHANGELOG`: entradas em `### Fixed` (F-3, F-4, F-5) e `### Added`/`###
   Changed` (F-1 sandbox `--project-root`, F-2 resume engine). Voz mentor
   calmo.
2. `08-session-handoff.md`: `**Última atualização:** 2026-06-19 (R7 — qa flow
   fixes F-1..F-5)`; `**Estado:**` reflete; atualizar counts de testes (rapid/
   integration/e2e) conforme rodada real; `§Conhecidos limites` se a forma de
   resume ficou flagless por decisão (anotar o gap de superfície).
3. `04-pending.md`: fechar gaps do R7 cobertos; se F-2 ficou parcial (engine
   pronto, superfície pendente de decisão), anotar como gap rastreável.
4. `README.md`: atualizar Stats SE test count mudou.
5. Verify: checklist pré-commit de `.claude/rules/doc-sync.md`;
   `.venv/bin/pytest` full suite verde; `forge verify` verde.

**Done:** doc-sync completo na convenção do projeto; counts coerentes com a
suite real; nenhum gap silencioso.

**Commit:** `docs(qa): doc-sync R7 qa flow fixes (CHANGELOG + handoff + pending + README)`

### Task F.2 — versionar o plano

**Files:**
- `docs/superpowers/plans/2026-06-19-pilot-r7-qa-flow-fixes.md` (este arquivo —
  já criado pelo planner; o executor só o inclui no commit do grupo F se ainda
  não versionado)

**Steps:**

1. `git add docs/superpowers/plans/2026-06-19-pilot-r7-qa-flow-fixes.md` (se
   untracked) e incluir no commit de doc-sync OU commit dedicado.

**Done:** plano versionado.

**Commit:** (dobra com F.1 OU) `docs(qa): versiona plano R7 qa flow fixes`

---

## Assumptions (pro plan-auditor + orquestrador)

- **A-1 (CRÍTICA — Decisão 10 / row 32):** a forma `--resume-run <id>` (flag)
  conflita com Decisão 10 (zero flags), reafirmada pelo carve-out da Decisão 32
  ("flags de comportamento de domínio continuam proibidas"; meta-flags only;
  `qa` interativo inalterado). O plano honra a decisão de design DADA (F-2
  pediu `--resume-run`) implementando o resume ENGINE-SIDE (não-conflitante,
  B.1) independente, e CONDICIONANDO a superfície CLI (B.2) ao veredito do
  orquestrador. Três caminhos pro orquestrador:
  1) **Aprovar a flag** como carve-out explícito — exige revisitar Decisão 10
     formalmente (`Revisita decisão 10` em CHANGELOG + ceremony), o que está
     FORA do escopo deste plano (não tocar 01-decisions.md). Bloqueia até
     revisita.
  2) **Forma flagless** — resume via positional (`forge qa resume:<run-id>` ou
     `forge qa <target> <run-id>`) ou conversacional (intent protocol). Mantém
     Decisão 10. B.2 implementa a forma aprovada; B.1 inalterado.
  3) **Resume só engine-side + conductor invoca Python direto** — sem
     superfície CLI nova; o conductor (que tem Bash) chama `run_qa(...,
     resume_run=...)`. B.2 vira no-op; B.3 documenta a chamada Python. Menor
     superfície, zero conflito de decisão.
  Default sugerido: **caminho 3** (menor risco, zero ceremony de decisão),
  com caminho 2 como segunda opção. O executor NÃO implementa a flag até
  veredito.
- **A-2 (Phase 3 no resume):** o engine atual NÃO invoca `run_sandbox`
  diretamente — o `qa-conductor` roda o sandbox e escreve `sandbox-results.json`.
  "Resume Phase 3" = reatar run tree + garantir handoff + devolver controle pro
  conductor, não "engine executa sandbox". A inferência de phase em B.1 assume
  isso; o executor deve CONFIRMAR contra o flow real e ajustar a regra se o
  estado divergir (o plano instrui "confirme e ajuste").
- **A-3 (materialização do mini-tree no F-1):** assumi que o `input_path` da
  fixture validator-claim JÁ aponta o arquivo materializado dentro do mini-tree
  (`run_dir/fixtures/<name>/<tree_rel_path>`), e que quem materializa é o
  auditor/conductor em Phase 2 (escreve o arquivo no tree). A.1 valida
  containment e invoca `--project-root`; A.2 instrui o auditor a materializar.
  Se a convenção real for "engine materializa a partir de um payload inline na
  fixture", A.1 ganha um step de materialização — confirmar a convenção real
  dos fixtures (scout do que Phase 2 escreve hoje) antes de implementar.
- **A-4 (matching F-4):** assumi `Path(fixture_path).stem ↔ stub.fixture_name`
  (basename sem extensão) como chave de casamento, baseado no exemplo do
  conductor (`"validator-claim-traversal"` sem extensão) e no nome que o
  auditor gera. Se o `fixture_name` real carregar extensão, ajustar a chave
  (normalizar ambos via `.stem`).
- **A-5 (schemas load-bearing):** F-1/F-4 NÃO tocam `docs/schemas/**`
  (`sandbox_result` já está no schema qa-finding; `--project-root`/
  `tree_rel_path` são contrato de fixture/template, não de schema canônico). Se
  algum executor concluir que precisa tocar schema, PARE e escale.
- **A-6 (test files):** assumi paths de teste (`tests/qa/test_*.py`,
  `tests/e2e/test_qa_resume_e2e.py`); o executor faz `grep -rln` pra reusar
  arquivos existentes antes de criar novos (reuse-first).

---

## Self-review

- **Spec coverage F-1..F-5:**
  - F-1 → A.1 (sandbox), A.2 (template+auditor), A.3 (spec §5.3), A.4
    (hardening). ✓
  - F-2 → B.1 (engine resume), B.2 (CLI, condicionada), B.3 (conductor). ✓
  - F-3 → C.1. ✓
  - F-4 → D.1 (helper), D.2 (wire). ✓
  - F-5 → E.1. ✓
- **TDD:** todas as tasks de código (C.1, D.1, D.2, A.1, A.4, B.1, B.2) têm
  step RED com comando `.venv/bin/pytest` + expected FAIL→PASS. Doc-only (E.1,
  A.2, A.3, B.3, F.*) sem pytest, com verify alternativo (`forge verify` /
  grep / checklist). ✓
- **F-1 task de segurança explícita:** A.4 (breach + chdir + containment do
  mini-tree continuam verdes). Cada task de A reitera preservação do hardening.
  ✓
- **Placeholder scan:** zero `TODO`/`FIXME`/`...` órfãos. Placeholders de
  template (`{{tree_rel_path}}`) aparecem só dentro de arquivos-alvo de tasks
  Create/Edit de template (exceção verbatim L2 do plan-auditor). ✓
- **Type/name consistency:** `tree_rel_path` (não `rel_path`/`tree_path`),
  `resume_run` (param) vs `--resume-run` (flag CLI, condicionada),
  `hydrate_validator_claim_evidence` (helper F-4), `_finalize_qa_report`
  (existente), `_validate_paths_inside_sandbox` (existente). Grafia consistente
  entre tasks. ✓
- **Não-tocar 01-decisions.md:** nenhuma task edita; A-1 escala revisita ao
  orquestrador em vez de editar. ✓
- **Hardening preservado:** A.1 ADICIONA cobertura ao containment (não
  afrouxa); A.4 é o gate. ✓
- **Markers:** integration pros testes que cruzam módulos (finalize+validator,
  synthesis+report, sandbox subprocess, run_qa resume); e2e pro CLI subprocess
  (B.2). ✓
