# Pilot R4 — Generalizar o gating de guards de re-entrada (P-15) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Each task ends with an atomic commit.

**Spec (contract):** `docs/reports/pilot-meobonsai-2026-06-19/report.md` §P-15 + este header (o relatório descreve o sintoma; este plano é o contrato de implementação da generalização aprovada pelo mantenedor).
**Phase tag:** pilot-r4-generalize-reentry — round 4 pós-piloto MeoBonsai
**Branch alvo:** `fix/pilot-r1-init-unblock` (ACUMULA nesta branch — não criar branch nova; rounds R1+R4 stackam no mesmo PR)
**Created:** 2026-06-19
**Voz:** mentor calmo. PT neutro.

**Goal:** Generalizar o fix de P-01 (gating do prompt de resume do `init`) num MECANISMO COMPARTILHADO que suprime QUALQUER guard de re-entrada quando o host está em loop mecânico (existe `forge-response.json` pendente cujo intent-id ≠ o do guard e ainda não consumido no log). Critério macro: dirigir `forge plan <slug>` end-to-end via loop canônico (responder + re-invocar argv idêntico, SEM apagar checkpoint/state) avança pelas waves sem `IntentMismatchError`; `forge init` continua funcionando (não regredir R1); o mesmo helper cobre `reconfigure` (draft-confirm) e `plan` (done-feature branch).

**Architecture:** Um helper compartilhado em `engine/ui/intent_state.py` — `host_is_replaying(project_root, guard_intent_id, *, state_dir=None) -> bool` — encapsula a decisão "há response pendente downstream não-consumida?". Três guards de re-entrada passam a consultá-lo antes de emitir intent: `plan._handle_active_slug_collision` (P-15, o bug primário), `plan._handle_done_feature_branch` (mesma classe), `reconfigure` draft-confirm (mesma classe). O gate local de P-01 em `init._run_pipeline` é REFATORADO pra usar o helper (DRY — hoje é `_response_path().exists()` cru, menos preciso que o helper). Doc-sync aditivo ao `docs/schemas/intent-protocol.md` (§4.1 novo: gating de guards de re-entrada) + CHANGELOG + handoff. **Decisão 27 NÃO é tocada** — ver §"Decisão 27" abaixo.

**Tech Stack:** Python 3.13 (engine core), pytest (`.venv/bin/pytest` canônico — tem json5 + deps), YAML/MD specs. Composição sobre `engine/ui/intent_state.py` (read_response, consumed-log, _response_path, _read_intent_log), `engine/ui/question.py` (stable_intent_id), `engine/init.py`, `engine/plan.py`, `engine/reconfigure.py`.

## Global Constraints

- `.venv/bin/pytest` é o runner canônico — system pytest gera false-fail (sem json5). Usar SEMPRE o caminho `.venv/bin/`.
- TDD obrigatório (`.claude/rules/testing.md`): teste falhando primeiro → impl mínima → verde. Para o helper (feature nova): happy-path test falha porque a função não existe. Para os guards (fix de comportamento): regression test reproduz o deadlock (`IntentMismatchError`) antes do fix.
- Voz mentor calmo em qualquer artefato/mensagem ao usuário; sem emoji decorativo (exceto ✓/🛑/⚠ já convencionais na UI cinematográfica e ✅⏭️🤔 do template 3-caminhos).
- Test count NUNCA regride sem justificativa no commit body (`Removed N tests because ...`).
- Reuse-first (Mandamento #3): o helper compartilhado É a aplicação do mandamento — antes de criar, evidência de consulta está documentada em cada task ("Reuse-first:"). Não escrever leitor paralelo de pending/response; reusar `intent_state`.
- Tests novos: sem marker pra unit puro (helper + guards são exercitados via state-files on-disk em `tmp_path`, dentro de um único módulo `engine.ui.intent_state` / handler — não cruzam ≥2 módulos de produção end-to-end). O teste e2e do loop canônico de `forge plan` (Task T6) leva marker `e2e` (subprocessa o CLI).
- Doc-sync (Mandamento #6) é tarefa explícita (Task T7), não improvisada por task.
- Escopo: cada task lista "Files:" com paths exatos. Não tocar arquivos fora da lista.

## Guards de re-entrada mapeados (pesquisa obrigatória — resultado)

Guard = prompt que emite intent CONDICIONALMENTE no topo do handler, baseado em ESTADO PRÉ-EXISTENTE (não no checkpoint do próprio prompt em-voo), e que portanto pode colidir com a response de um prompt downstream durante o loop mecânico.

| # | Comando | Guard | Arquivo:linha | Status |
|---|---------|-------|---------------|--------|
| G1 | `init` | prompt "Resume de init pendente?" | `engine/init.py:1533` (gate em `:1466-1492`) | JÁ gated (P-01, local `_response_path().exists()`) — REFATORAR pro helper |
| G2 | `plan` | `_handle_active_slug_collision` ("Já existe uma feature ativa 'X' (status=…)") | `engine/plan.py:1257` (call em `:1852`) | NÃO gated — **P-15, bug primário** |
| G3 | `plan` | `_handle_done_feature_branch` ("Detectei feature 'X' já feita (state=done)") | `engine/plan.py:1313` (call em `:1833`) | NÃO gated — mesma classe |
| G4 | `reconfigure` | draft-confirm ("Detectei um draft de reconfigure não aplicado. Retomar?") | `engine/reconfigure.py:246` (gate em `:225`) | NÃO gated — mesma classe |

**NÃO são guards de re-entrada (não emitem intent condicional no topo, ou são o prompt primário / não usam `question.ask`):**

- `init` brownfield 3-caminhos (`engine/init.py:1423-1428`) — é o prompt PRIMÁRIO determinístico (sempre emite quando config existe), não condicionado a response pendente downstream; a re-entrada é coberta pelo consumed-log §4.
- `evolve` resume check (`engine/evolve.py:369-377`) — só escreve mensagem `dim`, NÃO emite intent. O primeiro prompt (`_three_paths_overflow` / per-proposal) é o primário, coberto pelo consumed-log.
- `undo` menu (`engine/undo.py:681-719`) — prompt PRIMÁRIO (primeira pergunta interativa do handler), coberto pelo consumed-log via checkpoint.
- `qa` corrupt-checkpoint 3-caminhos (`engine/qa/__init__.py:163-189`) — usa `print` + `return 0`, NÃO emite intent via `question.ask`; auto-resume é silencioso.
- `verify` callsites (`engine/verify.py`) — prompts primários com intent-resume checkpoint, cobertos pelo consumed-log.
- `implement` callsites — idem (intent-resume checkpoint).

Escopo do fix: G2, G3, G4 ganham o gate via helper; G1 é refatorado pra reusar o helper (DRY).

## Decisão 27 (pause vs abort) — análise de cerimônia

**Veredito: cerimônia NÃO necessária.** Decisão 27 (`docs/design/01-decisions.md`) governa *pause vs abort semantics*: "Ctrl+C / `para` = pause (state `deferred`, auto-resumable); abort terminal só via `forge undo`". As mudanças deste round são **aditivas e alinhadas** — exatamente como o gating de R1 (P-01) foi julgado aditivo:

- Suprimir um guard de re-entrada *durante o loop mecânico do host* (quando há response pendente downstream não-consumida) NÃO muda o contrato pause/abort. O state `deferred`/checkpoint continua intacto; a re-entrada HUMANA genuína (sem response pendente) continua mostrando o guard com os 3 caminhos. O helper apenas evita um prompt espúrio que o `SKILL.md` não documenta no meio do handshake mecânico.
- Nenhum caminho de pause vira abort nem vice-versa; nenhum state é apagado pelo gating.

Logo: **não tocar `docs/design/01-decisions.md`**, sem entrada "Revisita decisão 27". Caso a implementação descubra que precisa alterar a *semântica* de pausa (improvável — o gating é aditivo), PARAR e escalar pro orquestrador antes de tocar `01-decisions.md`.

## Trade-off documentado: "não criar a feature cedo demais" (caso `plan`)

O relatório nota que `forge plan` cria a L1 da feature (status=planning, via `_initialize_status` em `engine/plan.py:1866`) já na PRIMEIRA invocação, antes da intake mínima terminar. Uma alternativa ao gating seria adiar `_initialize_status` até a intake mínima completar, de modo que o guard de colisão (G2) nunca dispare numa re-entrada mecânica (a feature ainda não existiria).

**Decisão: o fix PRIMÁRIO é o helper generalizado (G2/G3/G4 + refactor G1).** Razões:

1. O helper resolve a CLASSE inteira do bug (init, plan, reconfigure e futuros guards) com um único mecanismo; adiar a criação da L1 resolveria só o caso `plan`.
2. Adiar `_initialize_status` mexe no contrato de phase-lock e de auto-resume (a L1 é o que `find_resumable`/`acquire_phase_lock` observam) — risco cross-cutting maior que o gating aditivo.
3. O guard de colisão (G2) tem valor legítimo em re-entrada HUMANA (proteger feature alheia), então ele NÃO deve sumir — só ser suprimido no loop mecânico. O helper faz exatamente isso; adiar a criação removeria o sinal de colisão também pro caso humano de re-run rápido.

A alternativa fica anotada como **defer documentado** em `docs/design/04-pending.md` (Task T7): se um round futuro mostrar que a criação precoce da L1 causa outros sintomas (ex.: L1 órfã em `planning` após abort precoce), avaliar adiar `_initialize_status` como complemento — não substituto — do helper.

---

## T1 — Helper compartilhado `host_is_replaying` em `intent_state.py`

### Task T1: Criar `host_is_replaying(project_root, guard_intent_id)` (feature nova, TDD)

**Files:**
- Modify: `engine/ui/intent_state.py` (adicionar `host_is_replaying` após `read_response`, perto da família consumed-log)
- Test: `tests/unit/test_ui_intent_state.py` (adicionar bloco de casos do helper; arquivo já existe)

**Interfaces:**
- Consumes: `intent_state._response_path(project_root, *, state_dir=None) -> Path`; `intent_state._read_intent_log(project_root, *, state_dir=None) -> dict[str, dict]`; `engine.utils.json_io.read_json` (já importado no módulo via `from engine.utils import json_io`).
- Produces:
  ```python
  def host_is_replaying(
      project_root: Path,
      guard_intent_id: str,
      *,
      state_dir: Path | None = None,
  ) -> bool: ...
  ```
  Retorna `True` quando há `forge-response.json` no disco cujo `intent-id` ≠ `guard_intent_id` E esse `intent-id` ainda NÃO está no consumed-log (response in-flight pra um prompt downstream → loop mecânico). Retorna `False` quando: não há response no disco; a response é PRA o próprio guard (`intent-id == guard_intent_id` — a resposta do guard está chegando, não suprimir); ou a response é stale-leftover já consumida (`intent-id` no log).

**Reuse-first:** sem helper paralelo. Grep de precedente — `read_response` (`engine/ui/intent_state.py:521`) é o leitor canônico do par pending/response; `_read_intent_log` (`:284`) é o leitor canônico do consumed-log; `_response_path` (`:234`) resolve o caminho. `host_is_replaying` COMPÕE esses três (lê o response, lê o log, compara ids) — não reimplementa nenhum. O gate de P-01 hoje usa `_response_path().exists()` cru (`engine/init.py:1478-1479`), que é menos preciso (suprime mesmo quando a response é pro próprio guard); o helper substitui essa lógica por uma decisão correta. `forge graph` Q11 (reusable-helpers) não tem equivalente — esta é a primeira função que combina response-file + log pra decidir "replay".

**Contexto crítico (causa-raiz, P-15):** o `consumed-intent-log` (§4 do schema) NÃO resolve guards de re-entrada porque o intent do guard é NOVO a cada re-entrada — nunca foi consumido. O helper observa o estado on-disk de fora: "existe uma response pendente que NÃO é minha e que ninguém consumiu ainda? então o host está no meio de um handshake mecânico downstream — eu (guard) devo me calar e deixar o pipeline alcançar o prompt dono dessa response".

- [ ] **Step 1: Escrever os testes do helper (failing first)**

Em `tests/unit/test_ui_intent_state.py`, adicionar:

```python
def test_host_is_replaying_false_when_no_response(tmp_path):
    """Sem forge-response.json no disco → não há loop mecânico → False
    (re-entrada humana genuína; o guard deve aparecer)."""
    assert intent_state.host_is_replaying(tmp_path, "guard-abc") is False


def test_host_is_replaying_true_when_downstream_response_pending(tmp_path):
    """Response no disco pra um intent downstream (id ≠ guard) e NÃO no log
    → loop mecânico → True (guard deve ser suprimido). Reproduz P-15."""
    intent_state.write_response(
        tmp_path,
        {"schema-version": 1, "intent-id": "downstream-xyz", "value": "sim"},
    )
    assert intent_state.host_is_replaying(tmp_path, "guard-abc") is True


def test_host_is_replaying_false_when_response_is_for_the_guard(tmp_path):
    """Response no disco É pra o próprio guard (id == guard) → a resposta do
    guard está chegando; NÃO suprimir (o guard consome normalmente)."""
    intent_state.write_response(
        tmp_path,
        {"schema-version": 1, "intent-id": "guard-abc", "value": "retomar"},
    )
    assert intent_state.host_is_replaying(tmp_path, "guard-abc") is False


def test_host_is_replaying_false_when_response_is_stale_consumed(tmp_path):
    """Response no disco com id ≠ guard MAS já consumida (no log) →
    stale-leftover, não in-flight → False (mesma lógica do guard
    stale-consumido de read_response)."""
    intent_state.seed_consumed_log(
        tmp_path, intent_id="downstream-xyz", response={"value": "sim"}
    )
    intent_state.write_response(
        tmp_path,
        {"schema-version": 1, "intent-id": "downstream-xyz", "value": "sim"},
    )
    assert intent_state.host_is_replaying(tmp_path, "guard-abc") is False


def test_host_is_replaying_false_on_malformed_response(tmp_path):
    """Response malformado no disco → não dá pra provar replay → False
    (degrada pro caminho humano: o guard aparece em vez de sumir cego)."""
    path = intent_state._response_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8")
    assert intent_state.host_is_replaying(tmp_path, "guard-abc") is False
```

Rodar: `.venv/bin/pytest tests/unit/test_ui_intent_state.py -k host_is_replaying -x` → confirma FAIL (função não existe).

- [ ] **Step 2: Implementar `host_is_replaying` (impl mínima → verde)**

Em `engine/ui/intent_state.py`, após `read_response`, adicionar a função. Lógica:

1. Resolver `_response_path(project_root, state_dir=state_dir)`. Se não existe → `return False`.
2. Ler via `json_io.read_json`; em `json_io.JsonIOError` ou `OSError` → `return False` (malformed/transient: degrada pro caminho humano, não suprime cego).
3. Extrair `written_id = response.get("intent-id")`. Se `written_id == guard_intent_id` → `return False` (a resposta do guard está chegando).
4. Se `written_id` está em `_read_intent_log(project_root, state_dir=state_dir)` → `return False` (stale-leftover já consumido).
5. Caso contrário → `return True` (response in-flight pra prompt downstream).

Docstring deve: declarar a semântica dos 5 casos; nomear que substitui o `_response_path().exists()` cru do gate de P-01; referenciar §4.1 do schema (Task T7); referenciar P-15.

Rodar: `.venv/bin/pytest tests/unit/test_ui_intent_state.py -k host_is_replaying -x` → confirma PASS.

- [ ] **Step 3: Suite + commit**

`.venv/bin/pytest tests/unit/test_ui_intent_state.py -q` → verde.
Commit: `feat(intent): host_is_replaying — gate compartilhado de guards de re-entrada (P-15)`

---

## T2 — Refatorar o gate de P-01 no `init` pra usar o helper (DRY)

### Task T2: `init._run_pipeline` consome `host_is_replaying` em vez de `_response_path().exists()`

**Files:**
- Modify: `engine/init.py:1466-1492` (bloco `existing_checkpoint` — gate do resume)
- Test: `tests/unit/test_engine_init_resume.py` (os casos `test_resume_prompt_suppressed_when_response_pending` / `test_resume_prompt_shown_on_genuine_human_reentry` já existem — devem continuar verdes; adicionar 1 caso novo pro refinamento de precisão)

**Interfaces:**
- Consumes: `intent_state.host_is_replaying(project_root, guard_intent_id, *, state_dir=None)`; `ui_question.stable_intent_id(...)` pra derivar o `guard_intent_id` do prompt de resume.
- Produces: o gate de resume agora computa o `resume_intent_id` ANTES da decisão e passa pro helper, fixando a imprecisão do P-01 (hoje suprime mesmo quando a response é pra o próprio resume).

**Reuse-first:** remove a lógica local `_response_file = intent_state._response_path(...)` + `_host_loop_in_progress = _response_file.exists()` e substitui pela chamada ao helper. NÃO duplicar a leitura on-disk — o helper é a fonte única agora. Grep de precedente: o `resume_intent_id` já é derivado em `init.py:1521-1530` (no branch humano) e em `tests/unit/test_engine_init_resume.py::_resume_intent_id` — reusar a MESMA derivação (`stable_intent_id("ask", "Resume de init pendente?", _resume_option_labels(), extra={...})`).

**Contexto crítico:** o P-01 gate é correto pro caso comum (response downstream pendente), mas suprime o resume mesmo quando a única response no disco é a resposta do PRÓPRIO resume (re-entrada após o usuário responder o resume). Com o helper, esse caso vira `host_is_replaying == False` (id == guard) → o pipeline consome a resposta do resume corretamente em vez de pular cego. Comportamento de R1 preservado nos dois testes existentes; o caso novo cobre o refinamento.

- [ ] **Step 1: Escrever o caso novo (failing/regression)**

Em `tests/unit/test_engine_init_resume.py`, adicionar:

```python
def test_resume_not_suppressed_when_response_is_for_resume_itself(
    tmp_project_root, monkeypatch
):
    """Refinamento P-15 sobre P-01: quando a ÚNICA response no disco é pra o
    próprio intent de resume (o usuário acabou de responder o resume), o gate
    NÃO deve suprimir — o pipeline precisa consumir essa resposta. O P-01 cru
    (_response_path().exists()) suprimia cego; o helper distingue."""
    monkeypatch.chdir(tmp_project_root)
    _pin_intent_file_host(monkeypatch)
    _seed_init_checkpoint(tmp_project_root, step="step-5-backend-selection")
    resume_id = _resume_intent_id(tmp_project_root)
    # Response no disco é pra o resume (id == resume_id), não downstream.
    _seed_pending_response(tmp_project_root, intent_id=resume_id, value="resume")
    # O gate NÃO suprime → o resume é consumido; a próxima pausa é downstream
    # (backend), nunca um IntentMismatch.
    pending = _capture_first_pending(tmp_project_root)
    assert pending is None or pending.get("intent-id") != _MISMATCH_SENTINEL.get(
        "intent-id"
    ), "gate não deve produzir mismatch quando a response é pro próprio resume"
```

Rodar: `.venv/bin/pytest tests/unit/test_engine_init_resume.py -k "resume" -x` → o caso novo pode FALHAR contra o gate cru (P-01 suprime e pula o consume do resume). Confirmar o sinal antes do fix.

- [ ] **Step 2: Refatorar o gate (impl → verde)**

Em `engine/init.py`, no bloco `if existing_checkpoint:`:
- Derivar `_resume_options = _resume_option_labels()` e `_resume_intent_id = ui_question.stable_intent_id("ask", "Resume de init pendente?", _resume_options, extra={"default": "discard", "min-selected": None, "validator-hint": None})` ANTES do gate.
- Substituir `_host_loop_in_progress = intent_state._response_path(project_root).exists()` por `_host_loop_in_progress = intent_state.host_is_replaying(project_root, _resume_intent_id)`.
- Manter o resto do bloco (branches `if _host_loop_in_progress` / `else`) intacto, reusando `_resume_options`/`_resume_intent_id` já derivados (eliminar a re-derivação duplicada no branch `else`).
- Atualizar o comentário do gate pra referenciar o helper e P-15 (mantendo a referência a P-01).

Rodar: `.venv/bin/pytest tests/unit/test_engine_init_resume.py -q` → todos verdes (os 2 de R1 + o novo).

- [ ] **Step 3: Commit**

`.venv/bin/pytest tests/unit/test_engine_init_resume.py -q` verde.
Commit: `refactor(init): gate de resume usa host_is_replaying compartilhado (P-15, DRY com P-01)`

---

## T3 — Gate `plan._handle_active_slug_collision` (P-15, bug primário)

### Task T3: Suprimir o guard de colisão de slug durante o loop mecânico

**Files:**
- Modify: `engine/plan.py:1237-1274` (`_handle_active_slug_collision`) + o callsite em `:1845-1862`
- Test: `tests/unit/test_engine_plan_resume.py` (arquivo já existe)

**Interfaces:**
- Consumes: `intent_state.host_is_replaying(project_root, guard_intent_id, *, state_dir=None)`; `question.stable_intent_id("ask", <texto>, <options>, extra={...})` pra derivar o `guard_intent_id` do prompt de colisão.
- Produces: `_handle_active_slug_collision` retorna o `slug` existente (= caminho "retomar") SEM emitir intent quando `host_is_replaying(...)` é `True`. Em re-entrada humana (`False`) o comportamento atual é preservado (3-caminhos).

**Reuse-first:** reusa `host_is_replaying` (Task T1) — não reimplementa a detecção. O `guard_intent_id` é derivado com `question.stable_intent_id` usando o MESMO texto/options/extra que o `question.ask` em `:1257-1266` usa (kind="ask", question=f"Já existe uma feature ativa '{slug}' (status={status}). O que fazer?", options={"retomar","nova","abortar"}, extra={"default":"retomar","min-selected":None,"validator-hint":None}). Importar `from engine.ui import intent_state` no topo de `plan.py` se ainda não estiver (verificar imports existentes; `question` já é importado).

**Contexto crítico (P-15, causa-raiz verificada no piloto):** `forge plan <slug>` cria a L1 (status=planning) já na 1ª invocação (`_initialize_status`, `:1866`), ANTES da intake terminar. O loop AI-first re-invoca argv idêntico pra consumir cada response downstream. Na re-invocação, `run()` re-lê `existing_status` (`:1830`), vê status ∈ `_ACTIVE_COLLISION_STATES`, e chama `_handle_active_slug_collision` — que emite o intent do guard ANTES de re-alcançar o prompt em-voo. A response pendente (downstream) não casa com o id do guard → `IntentMismatchError` (`intent_state.py:615`) → exit 1. Deadlock. O fix: o guard consulta `host_is_replaying` e, se True, retorna `slug` (retomar) sem prompt — o pipeline segue até o prompt downstream dono da response.

- [ ] **Step 1: Escrever o teste de regressão (failing first)**

Em `tests/unit/test_engine_plan_resume.py`, adicionar (usar os helpers locais do arquivo pra seed de L1 + state-files; ver os helpers `_pin_intent_file_host` / seed de status já usados nos testes existentes):

```python
def test_active_collision_suppressed_during_host_replay(
    tmp_plan_root, monkeypatch
):
    """P-15: L1 já existe em status=planning (criada na 1ª invocação) e há
    forge-response.json pendente pra um prompt downstream. _handle_active_slug_
    collision NÃO deve emitir o guard de colisão — caso contrário o id do guard
    colide com a response downstream → IntentMismatchError (deadlock do piloto)."""
    monkeypatch.chdir(tmp_plan_root)
    _pin_intent_file_host(monkeypatch)
    _seed_planning_l1(tmp_plan_root, slug="meobonsai-login")  # helper local
    from engine.ui import intent_state
    intent_state.write_response(
        tmp_plan_root,
        {"schema-version": 1, "intent-id": "subtype-prompt-downstream", "value": "product"},
    )
    state = read_l1_status("meobonsai-login", tmp_plan_root)
    from engine.plan import _handle_active_slug_collision
    # Sob replay, o guard retorna o slug existente (retomar) sem emitir intent.
    result = _handle_active_slug_collision("meobonsai-login", state, tmp_plan_root)
    assert result == "meobonsai-login", (
        "guard de colisão vazou durante loop mecânico — P-15 não corrigido"
    )


def test_active_collision_shown_on_genuine_human_reentry(
    tmp_plan_root, monkeypatch
):
    """Re-entrada humana: L1 em planning, SEM response pendente → o guard de
    colisão DEVE emitir (3-caminhos preservado: proteger feature alheia)."""
    monkeypatch.chdir(tmp_plan_root)
    _pin_intent_file_host(monkeypatch)
    _seed_planning_l1(tmp_plan_root, slug="meobonsai-login")
    state = read_l1_status("meobonsai-login", tmp_plan_root)
    from engine.plan import _handle_active_slug_collision
    from engine.ui.question import PausedForInputError
    with pytest.raises(PausedForInputError) as exc:
        _handle_active_slug_collision("meobonsai-login", state, tmp_plan_root)
    # O pending emitido é o guard de colisão (3-caminhos preservado).
    assert "Já existe uma feature ativa" in (exc.value.intent or {}).get("question", "")
```

Rodar: `.venv/bin/pytest tests/unit/test_engine_plan_resume.py -k "active_collision" -x` → confirma FAIL no primeiro (guard vaza) / PASS no segundo (já é o comportamento atual). Se faltar helper `_seed_planning_l1`/`_pin_intent_file_host`, adicioná-los neste step (espelhando os de `test_engine_init_resume.py`).

- [ ] **Step 2: Implementar o gate (impl → verde)**

Em `engine/plan.py::_handle_active_slug_collision`, ANTES do `question.ask`:
- Derivar `_options` (o mesmo dict passado ao `ask`) e `_guard_id = question.stable_intent_id("ask", <mesmo texto>, _options, extra={"default":"retomar","min-selected":None,"validator-hint":None})`.
- `if intent_state.host_is_replaying(project_root, _guard_id):` → `return slug` (retomar; pipeline segue até o prompt downstream). Comentário referencia P-15 + `host_is_replaying`.
- Caso contrário, segue pro `question.ask` existente (3-caminhos preservado).

Rodar: `.venv/bin/pytest tests/unit/test_engine_plan_resume.py -k "active_collision" -x` → ambos verdes.

- [ ] **Step 3: Commit**

`.venv/bin/pytest tests/unit/test_engine_plan_resume.py -q` verde.
Commit: `fix(plan): gate guard de colisão de slug durante loop mecânico (P-15)`

---

## T4 — Gate `plan._handle_done_feature_branch` (mesma classe)

### Task T4: Suprimir o guard de feature-done durante o loop mecânico

**Files:**
- Modify: `engine/plan.py:1277-1322` (`_handle_done_feature_branch`, até o `question.ask` do menu) + o callsite em `:1831-1844`
- Test: `tests/unit/test_engine_plan_resume.py`

**Interfaces:**
- Consumes: `intent_state.host_is_replaying(project_root, guard_intent_id)`; `question.stable_intent_id("ask", "O que você quer?", <options 1..4>, extra={...})`.
- Produces: quando `host_is_replaying` é `True`, `_handle_done_feature_branch` retorna `parent_slug` SEM emitir o menu (segue como "retomar/replan" — caminho que mantém o slug). Em re-entrada humana, comportamento atual preservado (4-caminhos).

**Reuse-first:** reusa `host_is_replaying`. O `guard_intent_id` deriva do `question.ask` em `:1313-1322` (kind="ask", question="O que você quer?", options={"1","2","3","4"}, extra com default ausente → `default=None`; replicar o `extra` que `_build_pending` monta — `{"default": None, "min-selected": None, "validator-hint": None}`). **Atenção de type-consistency:** o `ask` deste guard NÃO passa `default=`, então `effective_default=None`; o `stable_intent_id` deve usar `default=None` no `extra` pra casar o id real emitido.

**Contexto crítico:** mesma classe de G2. Quando `forge plan <slug>` é re-invocado num loop mecânico e o slug aponta uma feature `status=done`, o menu de done-feature emitiria intent antes do prompt downstream. Sob replay, retornar `parent_slug` (caminho "retomar") deixa o pipeline alcançar a response em-voo. Re-entrada humana mantém os 4 caminhos.

**Nota de escopo:** o caminho "Estender" (choice 3) elicita um slug derivado interativo — isso só roda em re-entrada humana (quando o guard NÃO é suprimido), então não há regressão no fluxo de extensão sob replay (replay nunca chega no choice 3; retorna `parent_slug` antes).

- [ ] **Step 1: Teste de regressão (failing first)**

Em `tests/unit/test_engine_plan_resume.py`, adicionar:

```python
def test_done_feature_branch_suppressed_during_host_replay(
    tmp_plan_root, monkeypatch
):
    """Mesma classe de P-15: L1 em status=done + response downstream pendente
    → _handle_done_feature_branch NÃO emite o menu (retorna parent_slug)."""
    monkeypatch.chdir(tmp_plan_root)
    _pin_intent_file_host(monkeypatch)
    _seed_done_l1(tmp_plan_root, slug="meobonsai-login")  # helper local
    from engine.ui import intent_state
    intent_state.write_response(
        tmp_plan_root,
        {"schema-version": 1, "intent-id": "downstream-after-done", "value": "x"},
    )
    from engine.plan import _handle_done_feature_branch
    result = _handle_done_feature_branch("meobonsai-login", tmp_plan_root)
    assert result == "meobonsai-login", (
        "guard done-feature vazou durante loop mecânico"
    )


def test_done_feature_branch_shown_on_genuine_human_reentry(
    tmp_plan_root, monkeypatch
):
    """Re-entrada humana: L1 em done, SEM response pendente → menu 4-caminhos
    DEVE emitir (comportamento preservado)."""
    monkeypatch.chdir(tmp_plan_root)
    _pin_intent_file_host(monkeypatch)
    _seed_done_l1(tmp_plan_root, slug="meobonsai-login")
    from engine.plan import _handle_done_feature_branch
    from engine.ui.question import PausedForInputError
    with pytest.raises(PausedForInputError) as exc:
        _handle_done_feature_branch("meobonsai-login", tmp_plan_root)
    assert "O que você quer?" in (exc.value.intent or {}).get("question", "")
```

Rodar: `.venv/bin/pytest tests/unit/test_engine_plan_resume.py -k "done_feature_branch" -x` → confirma FAIL no replay-suppress. Adicionar `_seed_done_l1` se ausente.

- [ ] **Step 2: Implementar o gate (impl → verde)**

Em `_handle_done_feature_branch`, após o guard defensivo (`parent_status.status != "done" → return parent_slug`) e ANTES do bloco `renderer.write` + `question.ask` do menu:
- Derivar `_options` (o dict 1..4) e `_guard_id = question.stable_intent_id("ask", "O que você quer?", _options, extra={"default": None, "min-selected": None, "validator-hint": None})`.
- `if intent_state.host_is_replaying(project_root, _guard_id): return parent_slug` (segue como retomar — pipeline alcança a response downstream). Comentário referencia P-15 / mesma classe.

Rodar: `.venv/bin/pytest tests/unit/test_engine_plan_resume.py -k "done_feature_branch" -x` → verde.

- [ ] **Step 3: Commit**

`.venv/bin/pytest tests/unit/test_engine_plan_resume.py -q` verde.
Commit: `fix(plan): gate guard done-feature durante loop mecânico (P-15, mesma classe)`

---

## T5 — Gate `reconfigure` draft-confirm (mesma classe)

### Task T5: Suprimir o draft-confirm de reconfigure durante o loop mecânico

**Files:**
- Modify: `engine/reconfigure.py:223-255` (bloco `draft is not None` — gate do draft-confirm)
- Test: `tests/unit/test_engine_reconfigure_resume.py` (arquivo já existe)

**Interfaces:**
- Consumes: `intent_state.host_is_replaying(project_root, guard_intent_id)`; `question.stable_intent_id("confirm", "Detectei um draft de reconfigure não aplicado. Retomar?", {"s":"sim","n":"não"}, extra={...})` — o `guard_intent_id` é o MESMO já derivado em `:233-242` pro checkpoint (reusar essa derivação).
- Produces: quando `host_is_replaying` é `True`, o handler adota `working = draft` SEM emitir o `question.confirm` (continua o reconfigure do draft, que é o caminho "sim"/retomar). Em re-entrada humana, comportamento atual preservado (confirm aparece).

**Reuse-first:** reusa `host_is_replaying`. O `guard_intent_id` do draft-confirm JÁ é calculado em `engine/reconfigure.py:233-242` (`question.stable_intent_id("confirm", ...)`) pra persistir no checkpoint — extrair pra uma variável local e reusar tanto no checkpoint quanto na chamada ao helper (DRY; não derivar duas vezes). Importar `intent_state` se ausente (`question` já é importado).

**Contexto crítico:** mesma classe de G1/G2/G3. O draft (`.claude/.reconfigure-draft.yaml`) sobrevive de uma sessão cancelada. Num loop mecânico subsequente (ou mesmo num reconfigure que pausou downstream e foi re-invocado), o `question.confirm` do draft fira antes do prompt downstream → mismatch. Sob replay: adotar `working = draft` (o caminho "retomar o draft") sem perguntar, deixando o pipeline alcançar o prompt downstream. **Decisão de default sob replay = retomar o draft** (não descartar) — preserva trabalho, coerente com o contrato auto-resumable da Decisão 27 e com o default `True` do próprio confirm.

- [ ] **Step 1: Teste de regressão (failing first)**

Em `tests/unit/test_engine_reconfigure_resume.py`, adicionar:

```python
def test_draft_confirm_suppressed_during_host_replay(tmp_reconfig_root, monkeypatch):
    """Mesma classe de P-15: existe draft + response downstream pendente →
    o draft-confirm NÃO deve emitir; o handler adota o draft e segue."""
    monkeypatch.chdir(tmp_reconfig_root)
    _pin_intent_file_host(monkeypatch)
    _seed_reconfigure_draft(tmp_reconfig_root)  # helper local
    from engine.ui import intent_state
    intent_state.write_response(
        tmp_reconfig_root,
        {"schema-version": 1, "intent-id": "category-menu-downstream", "value": ["backend"]},
    )
    # O draft-confirm não deve aparecer como o primeiro pending; o primeiro
    # pending (se houver) é downstream (category-menu), nunca o draft-confirm.
    draft_confirm_id = _draft_confirm_intent_id(tmp_reconfig_root)  # helper local
    pending = _run_reconfigure_and_capture_first_pending(tmp_reconfig_root)
    assert pending is None or pending.get("intent-id") != draft_confirm_id, (
        "draft-confirm vazou durante loop mecânico"
    )


def test_draft_confirm_shown_on_genuine_human_reentry(tmp_reconfig_root, monkeypatch):
    """Re-entrada humana: draft existe, SEM response pendente → o draft-confirm
    DEVE aparecer (comportamento preservado)."""
    monkeypatch.chdir(tmp_reconfig_root)
    _pin_intent_file_host(monkeypatch)
    _seed_reconfigure_draft(tmp_reconfig_root)
    draft_confirm_id = _draft_confirm_intent_id(tmp_reconfig_root)
    pending = _run_reconfigure_and_capture_first_pending(tmp_reconfig_root)
    assert pending is not None and pending.get("intent-id") == draft_confirm_id, (
        "draft-confirm deve aparecer em re-entrada humana sem response pendente"
    )
```

Rodar: `.venv/bin/pytest tests/unit/test_engine_reconfigure_resume.py -k "draft_confirm" -x` → confirma FAIL no replay-suppress. Adicionar helpers locais (`_seed_reconfigure_draft`, `_draft_confirm_intent_id`, `_run_reconfigure_and_capture_first_pending`) espelhando os de `test_engine_init_resume.py` se ausentes.

- [ ] **Step 2: Implementar o gate (impl → verde)**

Em `engine/reconfigure.py`, no bloco `if draft is not None:`:
- Extrair o `_draft_confirm_id = question.stable_intent_id("confirm", "Detectei um draft de reconfigure não aplicado. Retomar?", {"s": "sim", "n": "não"}, extra={"default": "s", "min-selected": None, "validator-hint": None})` numa variável local (reusar no `_save_reconfigure_checkpoint` que hoje a calcula inline).
- `if intent_state.host_is_replaying(project_root, _draft_confirm_id): working = draft` (adota o draft sem perguntar) — pular o `_save_reconfigure_checkpoint` do draft-confirm e o `question.confirm`. Comentário referencia P-15 / mesma classe / Decisão 27 (auto-resume).
- `else:` mantém o bloco atual (checkpoint + `question.confirm` + branch sim/não).

Rodar: `.venv/bin/pytest tests/unit/test_engine_reconfigure_resume.py -k "draft_confirm" -x` → verde.

- [ ] **Step 3: Commit**

`.venv/bin/pytest tests/unit/test_engine_reconfigure_resume.py -q` verde.
Commit: `fix(reconfigure): gate draft-confirm durante loop mecânico (P-15, mesma classe)`

---

## T6 — Teste e2e: `forge plan` end-to-end via loop canônico (acceptance)

### Task T6: e2e que dirige `forge plan <slug>` pelo loop canônico sem `IntentMismatchError`

**Files:**
- Test: `tests/e2e/test_plan_canonical_loop.py` (novo)

**Interfaces:**
- Consumes: subprocessa `python -m engine.cli plan <slug>` (ou `./bin/forge plan <slug>`) num projeto fixture já inicializado; escreve `forge-response.json` entre re-invocações (loop canônico: responder + re-invocar argv idêntico, SEM apagar checkpoint/state); ambiente com `FORGE_FORCE_INTENT_MODE`/host pinado pra intent-file (ver `feedback_subprocess_env_scrub` — scrub `CLAUDECODE`/`OPENCODE_*`/`CODEX`/`CURSOR_*` + pin `host: intent-file`).
- Produces: prova de acceptance — o loop avança pela 1ª pergunta downstream (subtype/slug) na re-invocação SEM colidir com o guard de colisão (P-15 fechado end-to-end).

**Reuse-first:** reusa o harness e2e existente. Grep de precedente: `tests/e2e/` já tem testes que subprocessam o CLI com loop de pending/response (ver `tests/e2e/` e o padrão de `feedback_subprocess_env_scrub`/`feedback_venv_pytest_canonical`). Reusar a fixture de projeto inicializado se existir (`grep -rn "def.*fixture" tests/e2e/ tests/conftest.py`); senão, criar fixture mínima que roda `forge init` headless ou semeia `.claude/forge/forge-config.yaml` direto.

**Contexto crítico:** este é o critério macro do plano. A 1ª invocação de `forge plan <slug>` cria a L1 (status=planning) e pausa no 1º prompt downstream (exit 2). O teste escreve a response, re-invoca argv idêntico SEM tocar o checkpoint, e asserta que a re-invocação NÃO sai com exit 1 / `IntentMismatchError` — avança pra próxima pausa ou completa. Marker `e2e`.

- [ ] **Step 1: Escrever o e2e (failing first se rodado contra HEAD pré-T3)**

Estrutura (pseudo, ajustar à fixture real):

```python
import pytest

pytestmark = pytest.mark.e2e


def test_forge_plan_advances_through_canonical_loop(initialized_project, run_forge):
    """Acceptance P-15: dirigir `forge plan <slug>` via loop canônico
    (responder + re-invocar argv idêntico, sem apagar state) avança sem
    IntentMismatchError. A 1ª invocação cria a L1 (planning) e pausa; a
    re-invocação NÃO deve bater no guard de colisão."""
    slug = "demo-feature"
    # Invocação 1: cria L1, pausa no 1º prompt downstream (exit 2).
    r1 = run_forge(["plan", slug])
    assert r1.exit_code == 2, r1.stderr
    pending = _read_pending(initialized_project)
    assert pending is not None
    # Responde o prompt em-voo (ex.: subtype/elicit) e re-invoca argv idêntico.
    _write_response(initialized_project, intent_id=pending["intent-id"], value=_answer_for(pending))
    r2 = run_forge(["plan", slug])  # mesmo argv, state preservado
    # Acceptance: NÃO exit 1 / NÃO IntentMismatchError. Avança (exit 2 = próxima
    # pausa) ou completa (exit 0). Nunca o deadlock de P-15.
    assert r2.exit_code in (0, 2), (
        f"loop canônico travou: exit={r2.exit_code} stderr={r2.stderr}"
    )
    assert "IntentMismatchError" not in r2.stderr
    assert "intent-id mismatch" not in r2.stderr
```

Rodar: `.venv/bin/pytest tests/e2e/test_plan_canonical_loop.py -x` (com o env scrub do harness e2e). Se rodado contra um HEAD sem T3, falha com mismatch — prova que o e2e captura P-15.

- [ ] **Step 2: Verde + suite**

Com T3 aplicado, o e2e passa. Rodar `.venv/bin/pytest tests/e2e/test_plan_canonical_loop.py -q` → verde.

- [ ] **Step 3: Suite completa de regressão**

`.venv/bin/pytest -m "not integration and not e2e" -q | tail -1` (rapid lane verde, count ≥ baseline 1863) + `.venv/bin/pytest -m e2e -q | tail -1` (e2e verde, count ≥ 30).
Commit: `test(plan): e2e do loop canônico — forge plan sem IntentMismatchError (P-15)`

---

## T7 — Doc-sync (Mandamento #6)

### Task T7: CHANGELOG + handoff + schema intent-protocol + pending

**Files:**
- Modify: `CHANGELOG.md` (seção `## [Unreleased]`)
- Modify: `docs/design/08-session-handoff.md` (Última atualização + Estado)
- Modify: `docs/schemas/intent-protocol.md` (novo §4.1 — gating de guards de re-entrada)
- Modify: `docs/design/04-pending.md` (defer documentado: alternativa "adiar `_initialize_status`")

**Interfaces:**
- Consumes: nada de código — só documentação.
- Produces: contrato de re-entrada documentado (o gating de guards via `host_is_replaying`); trilha de doc-sync da matriz código→docs.

**Reuse-first:** doc-only, sem helper. Segue a matriz canônica de `.claude/rules/doc-sync.md`: mudança em `engine/ui/*` + `engine/{init,plan,reconfigure}.py` (handlers) → CHANGELOG + handoff obrigatórios; mudança no contrato de re-entrada → `docs/schemas/intent-protocol.md` (provável, conforme o briefing). Sem mudança de stats no README (sem novo validator/card/template/comando; test count sobe mas o README não enumera count por-arquivo de teste — confirmar `grep -n "test" README.md` antes; se houver count afetado, atualizar, senão omitir com nota).

**Contexto crítico:** o §4 do schema documenta o consumed-log (re-entry idempotency PARA prompts já vistos). O gating de guards é um mecanismo NOVO e complementar (suprime prompts NÃO-vistos que colidiriam). Precisa de seção própria — §4.1 — explicando: o que é um guard de re-entrada; quando é suprimido (`host_is_replaying == True`); por que o consumed-log sozinho não resolve (o intent do guard é novo a cada re-entrada); e a distinção replay-mecânico vs re-entrada-humana.

- [ ] **Step 1: `docs/schemas/intent-protocol.md` — adicionar §4.1**

Após o §4 (Consumed-intent log), adicionar `### §4.1 Gating de guards de re-entrada (host replay)`:
- Definir "guard de re-entrada": prompt condicional no topo de um handler, baseado em estado pré-existente (checkpoint/L1/draft), que pode colidir com a response de um prompt downstream durante o loop mecânico.
- Documentar `host_is_replaying(project_root, guard_intent_id)`: True quando há `forge-response.json` cujo `intent-id` ≠ `guard_intent_id` E ≠ está no consumed-log → response in-flight pra prompt downstream.
- Explicar por que o consumed-log (§4) NÃO cobre: o intent do guard é NOVO a cada re-entrada, nunca consumido.
- Listar os guards gated (init resume, plan colisão/done-feature, reconfigure draft-confirm) e a regra: suprimir no replay, mostrar na re-entrada humana.
- Referenciar P-15.

- [ ] **Step 2: CHANGELOG**

Em `## [Unreleased]`, adicionar entradas:
- `### Added` — `host_is_replaying` em `engine/ui/intent_state.py`: gate compartilhado que suprime guards de re-entrada durante o loop mecânico do host (P-15).
- `### Fixed` — `forge plan`/`forge reconfigure`/`forge init` não deadlockavam mais (`IntentMismatchError`) quando um guard de re-entrada colidia com a response de um prompt downstream durante o loop AI-first (P-15; generaliza o fix de P-01).
- `### Changed` — gate de resume do `init` agora usa `host_is_replaying` (DRY com P-01; precisão melhorada — não suprime quando a response é pro próprio resume).

- [ ] **Step 3: handoff + pending**

- `docs/design/08-session-handoff.md`: `**Última atualização:**` = 2026-06-19 (pilot-r4 — generaliza re-entry guard gating); `**Estado:**` reflete o round 4. Tabela `| Categoria | Status |` ganha linha se o pattern de wave/round for o convencionado.
- `docs/design/04-pending.md`: adicionar gap "Adiar `_initialize_status` no `forge plan` até intake mínima completar" como defer documentado (complemento — não substituto — do helper; ver §Trade-off deste plano). Referenciar P-15.

- [ ] **Step 4: Verde + commit**

`.venv/bin/pytest -m "not integration and not e2e" -q | tail -1` (verde, count ≥ baseline) + `forge verify` (cascade sem hard fail).
Commit: `docs(intent): doc-sync P-15 — gating de guards de re-entrada (schema §4.1 + CHANGELOG + handoff + pending)`

---

## Acceptance final (critério macro)

- [ ] `forge plan <slug>` dirigido via loop canônico (responder + re-invocar argv idêntico, SEM apagar checkpoint/state) avança pelas waves sem `IntentMismatchError` (Task T6 e2e verde).
- [ ] `forge init` continua funcionando — os testes de R1 (`test_resume_prompt_suppressed_when_response_pending`, `test_resume_prompt_shown_on_genuine_human_reentry`, `test_resume_continues_from_checkpoint_step`) seguem verdes (Task T2).
- [ ] O mesmo helper (`host_is_replaying`) cobre `reconfigure` (draft-confirm, T5) e `plan` (colisão T3 + done-feature T4).
- [ ] Suite rapid ≥ baseline 1863 / e2e ≥ 30, 0 falhas.
- [ ] `forge verify` cascade sem hard fail.
- [ ] Doc-sync executado (T7).
- [ ] Decisão 27 NÃO tocada (cerimônia não necessária — ver §Decisão 27).
