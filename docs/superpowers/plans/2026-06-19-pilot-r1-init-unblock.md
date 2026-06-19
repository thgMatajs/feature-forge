# Pilot R1 — Unblock `forge init` AI-first (brownfield KMP) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Each task ends with an atomic commit.

**Spec (contract):** `docs/reports/pilot-meobonsai-2026-06-19/report.md` (este plano cobre P-01 a P-12 + drift de stats do README; o relatório É o spec).
**Phase tag:** pilot-r1-init-unblock — round 1 de fixes pós-piloto MeoBonsai
**Branch alvo:** `fix/pilot-r1-init-unblock` (base = `pilot/meobonsai-report-2026-06-19`, que contém o relatório)
**Created:** 2026-06-19
**Voz:** mentor calmo. PT neutro.

**Goal:** Destravar `forge init` IA-first end-to-end num projeto brownfield KMP real + corrigir findings de qualidade baratos. Critério macro: rodar `forge init` no MeoBonsai (host claude_code/intent-file) COMPLETA sem deadlock e sem RESOLVER-ERRORS, produzindo `forge-config` válido.

**Architecture:** Quatro work-streams (WS-A intent loop / resume · WS-B detecção brownfield + resolver · WS-C paths phantom mínimo · WS-D quality baratos). Funcionais primeiro (WS-A destrava o loop, WS-B destrava o resolver), depois cosméticos (WS-C/WS-D). Nenhum toque em arquitetura load-bearing além de docs/schema aditivos. **Decisão 27 NÃO é tocada** — ver §"Decisão 27" abaixo. Reuso-first: cards declaram `identity.platforms` (campo aditivo, schema-version 1) em vez de criar lógica nova de partição; detecção de provider reusa `compose_backend_axes` + `resolve`; resume real reusa o `_save_checkpoint`/`step` que já existe.

**Tech Stack:** Python 3.13 (engine core), pytest (`.venv/bin/pytest` canônico — tem json5 + deps), YAML/MD specs. Composição sobre `engine/detection/composer.py`, `engine/cards/resolver.py`, `engine/ui/question.py`, `engine/ui/intent_state.py`.

## Global Constraints

- `.venv/bin/pytest` é o runner canônico — system pytest gera false-fail (sem json5). Usar SEMPRE o caminho `.venv/bin/`.
- TDD obrigatório (`.claude/rules/testing.md`): teste falhando primeiro → impl mínima → verde. Para features, happy-path test falha (função/comportamento não existe); para fixes de comportamento, regression test reproduz o bug.
- Voz mentor calmo em qualquer artefato/mensagem ao usuário; sem emoji decorativo (exceto ✓/🛑/⚠ já convencionais na UI cinematográfica e ✅⏭️🤔 do template 3-caminhos).
- Test count NUNCA regride sem justificativa no commit body (`Removed N tests because ...`).
- Reuse-first (Mandamento #3): antes de criar helper, evidência de consulta a `forge graph` Q11-Q17 / `validators/_*.py` / grep de precedente em `engine/`.
- Tests novos: marker `integration` quando cruzam ≥2 módulos ou usam fixture pesada; `e2e` quando subprocessam o CLI; sem marker pra unit puro (`.claude/rules/testing.md §markers`).
- Doc-sync (Mandamento #6) é tarefa explícita (Task WS-D-5), não improvisada por task.
- Escopo: cada task lista "Files:" com paths exatos. Não tocar arquivos fora da lista.

## Decisão 27 (pause vs abort) — análise de cerimônia

**Veredito: cerimônia NÃO necessária.** Decisão 27 (`docs/design/01-decisions.md:38`) governa
*pause vs abort semantics*: "Ctrl+C / `para` = pause (state `deferred`, auto-resumable); abort
terminal só via `forge undo`". As mudanças de WS-A são **aditivas e alinhadas** a essa decisão:

- **Gating do resume (WS-A-1):** suprimir o prompt "Resume?" *durante o loop mecânico do host*
  (quando há response pendente) não muda o contrato pause/abort — só evita um prompt espúrio que
  o `SKILL.md` não documenta. Em re-entrada humana genuína, o prompt continua aparecendo.
- **Resume real (WS-A-2):** fazer o "resume" continuar do step do checkpoint *honra* a promessa
  "auto-resumable" da própria Decisão 27 (hoje ambas opções recomeçam do zero — o relatório P-11
  mostra que a label "resume" mente). Tornar o resume real aproxima o comportamento da decisão, não
  a contradiz.

Logo: **não tocar `docs/design/01-decisions.md`**, sem entrada "Revisita decisão 27". Caso a
implementação descubra que precisa alterar a *semântica* de pausa (improvável — o gating é aditivo),
PARAR e escalar pro orquestrador antes de tocar `01-decisions.md`.

---

## WS-A — Intent loop / resume (P-01, P-11, P-06)

### Task WS-A-1: Gate o prompt de resume — suprimir durante o loop mecânico do host (P-01)

**Files:**
- Modify: `engine/init.py:1311-1372` (bloco `existing_checkpoint` — gating do prompt de resume)
- Test: `tests/unit/test_engine_init_resume.py` (adicionar casos de gating; arquivo já existe — ver docstring de `_save_checkpoint`/`_load_checkpoint`)

**Interfaces:**
- Consumes: `engine.ui.intent_state.read_response(project_root, intent_id, *, state_dir=None) -> dict | None` (branch 1 consulta o consumed-log, branch 2 o `forge-response.json`); `engine.ui.intent_state._response_path(project_root, *, state_dir=None) -> Path`; `engine.ui.question.stable_intent_id(kind, question_text, options, *, extra, command=None, command_args=None) -> str`.
- Produces: comportamento gated — o prompt "Resume de init pendente?" só é emitido quando NÃO há `forge-response.json` pendente correspondente a algum intent downstream do checkpoint.

**Reuse-first:** sem helper novo. O gating consulta o estado on-disk via `intent_state` (já importado em `init.py` indiretamente via `ui_question`). Grep de precedente: `read_response` é o leitor canônico do par pending/response (`engine/ui/intent_state.py:521`); `_response_path` resolve o caminho do `forge-response.json`. NÃO escrever um leitor paralelo — reusar `intent_state`.

**Contexto crítico (causa-raiz, do relatório P-01):** quando o host segue o `SKILL.md` (escreve `forge-response.json` pro intent X = pergunta real, ex. preset, e re-invoca argv idêntico), a re-invocação detecta o checkpoint e emite o prompt de resume (intent Y = "Resume de init pendente?") ANTES de chegar na pergunta X. Como `read_response(Y)` retorna `None` (a response on-disk é pra X, não Y) → emite pending(Y) + exit 2 → próxima re-invocação: a response pra X colide com Y → `IntentMismatchError` → exit 1. O fix: detectar que existe uma response pendente (= loop mecânico do host) e PULAR o prompt de resume, deixando o pipeline fresh consumir a response via o consumed-log (idempotência §4 do schema). O resume só aparece em re-entrada HUMANA genuína (sem response pendente).

- [ ] **Step 1: Escrever o teste do gating (failing first)**

Em `tests/unit/test_engine_init_resume.py`, adicionar:

```python
def test_resume_prompt_suppressed_when_response_pending(tmp_path, monkeypatch):
    """Loop mecânico do host: existe forge-response.json pendente (pra a
    pergunta real do pipeline, NÃO pro resume) → o init NÃO deve emitir o
    prompt 'Resume de init pendente?'. Caso contrário o intent-id do resume
    colide com a response → IntentMismatchError (P-01 deadlock)."""
    project_root = tmp_path
    _seed_init_checkpoint(project_root, step="step-4-preset-confirmation")  # helper local (ver Step 2)
    _seed_pending_response(project_root, intent_id="qualquer-intent-downstream", value="sim")
    # Sob FORGE_FORCE_INTENT_MODE, o init re-invocado NÃO deve produzir um
    # pending cujo intent-id == stable_intent_id do prompt de resume.
    resume_id = _resume_intent_id(project_root)
    pending = _run_init_and_capture_pending(project_root)
    assert pending is None or pending.get("intent-id") != resume_id, (
        "resume prompt vazou durante loop mecânico — P-01 não corrigido"
    )

def test_resume_prompt_shown_on_genuine_human_reentry(tmp_path):
    """Re-entrada humana: checkpoint existe mas NÃO há forge-response.json
    pendente → o prompt de resume DEVE aparecer (comportamento preservado)."""
    project_root = tmp_path
    _seed_init_checkpoint(project_root, step="step-4-preset-confirmation")
    resume_id = _resume_intent_id(project_root)
    pending = _run_init_and_capture_pending(project_root)
    assert pending is not None and pending.get("intent-id") == resume_id, (
        "resume prompt deve aparecer em re-entrada humana sem response pendente"
    )
```

Os helpers `_seed_init_checkpoint` / `_seed_pending_response` / `_resume_intent_id` / `_run_init_and_capture_pending` reusam o pattern dos testes existentes em `test_engine_init_resume.py` (eles já semeiam checkpoint via `_save_checkpoint`). `_resume_intent_id` chama `ui_question.stable_intent_id("ask", "Resume de init pendente?", {...resume_options...}, extra={"default": "discard", "min-selected": None, "validator-hint": None})` — mesma assinatura usada hoje em `init.py:1347-1356`.

- [ ] **Step 2: Rodar o teste, confirmar FAIL**

Run: `.venv/bin/pytest tests/unit/test_engine_init_resume.py -k "suppressed or genuine_human" -v`
Expected: `test_resume_prompt_suppressed_when_response_pending` FALHA (hoje o prompt sempre emite, o pending tem intent-id == resume_id). `test_resume_prompt_shown_on_genuine_human_reentry` provavelmente PASSA (comportamento atual já mostra o prompt) — é o guard de não-regressão.

- [ ] **Step 3: Implementar o gating no bloco `existing_checkpoint`**

Em `engine/init.py`, no bloco `if existing_checkpoint:` (linha ~1312), ANTES de salvar o checkpoint de resume + chamar `ui_question.ask("Resume de init pendente?", ...)`, inserir o gate:

```python
from engine.ui import intent_state  # topo do módulo, ou lazy import local

# Gate do resume (pilot R1, P-01): durante o loop mecânico do host existe
# uma forge-response.json pendente que pertence a uma pergunta DOWNSTREAM
# (preset, backend, ...). Emitir o prompt de resume aqui injetaria um intent
# cujo id não casa com essa response → IntentMismatchError (deadlock). Só
# emitimos o resume em re-entrada HUMANA genuína: quando NÃO há response
# pendente no disco. O pipeline fresh consome a response via o consumed-log
# (idempotência §4 do schema intent-protocol).
_response_file = intent_state._response_path(project_root)
_host_loop_in_progress = _response_file.exists()
```

Envolver a emissão do prompt de resume (`_save_checkpoint(...)` do resume + `resume_choice = ui_question.ask(...)` + o `if resume_choice == ...`) num `if not _host_loop_in_progress:`. Quando `_host_loop_in_progress` é True, NÃO perguntar — seguir direto pro Step 2 do pipeline (discovery), preservando o checkpoint intacto (o pipeline o regrava). Comportamento de re-entrada humana (sem response) fica idêntico ao de hoje.

- [ ] **Step 4: Rodar o teste, confirmar PASS + suíte de resume verde**

Run: `.venv/bin/pytest tests/unit/test_engine_init_resume.py -v`
Expected: ambos os novos testes PASS; os pré-existentes continuam verdes. Se algum pré-existente assumia o prompt de resume sempre-emitido com response pendente, ele estava codificando o bug — atualizar com nota no commit body.

- [ ] **Step 5: Commit**

```bash
git add engine/init.py tests/unit/test_engine_init_resume.py
git commit -m "fix(init): gate prompt de resume durante loop mecânico do host (P-01)

Suprime 'Resume de init pendente?' quando existe forge-response.json
pendente (loop do host) — o prompt espúrio colidia com a response da
pergunta real → IntentMismatchError (deadlock do piloto MeoBonsai).
Re-entrada humana genuína (sem response) segue mostrando o prompt.
Aditivo a Decisão 27 (pause/abort inalterados)."
```

---

### Task WS-A-2: Resume real — continuar do step do checkpoint + labels honestas (P-11)

**Files:**
- Modify: `engine/init.py:1329-1372` (labels do `_resume_options` + ramo `resume` continua do step salvo)
- Modify: `engine/init.py:1374-1478` (pipeline pós-resume: pular steps já completos com base no `step` do checkpoint)
- Test: `tests/unit/test_engine_init_resume.py` (resume continua do step; labels refletem o comportamento)

**Interfaces:**
- Consumes: `_InitCheckpoint` dataclass (`engine/init.py:140-144`, campos `step`/`preset`/`selected_card_names`/`backend_cells`/`intent_id`); `_load_checkpoint(project_root) -> dict | None`; os step labels canônicos (`step-1-greeting` ... `step-7-5-orphan-signals`) já gravados em `checkpoint.step`.
- Produces: ramo `resume` que pula os steps `< checkpoint.step` (greeting/discovery/preset já feitos), reaproveitando `checkpoint.preset` / `checkpoint.selected_card_names` / `checkpoint.backend_cells`; labels do prompt deixam de mentir.

**Reuse-first:** o checkpoint JÁ persiste `step` + `preset` + `selected_card_names` + `backend_cells` (`_save_checkpoint`, `engine/init.py:167-182`). Resume real lê esses campos em vez de re-rodar os steps. Sem estrutura nova — só wiring do que já está salvo. Grep: `checkpoint.step` é setado em cada barreira de step (`init.py:1375,1432,1476,1541,1603,1621`) — esses são os marcos pra pular.

**Contexto crítico (P-11):** hoje as labels mentem — `resume` = "começar do zero mantendo o checkpoint como audit", `discard` = "apagar e começar limpo". NENHUMA continua do step. O fix tem 2 partes: (1) labels honestas; (2) o ramo `resume` realmente pula os steps já completos. Escopo conservador: pular greeting/discovery/preset-confirmation quando `checkpoint.preset` já está setado e `checkpoint.step` indica progresso além de `step-4`. NÃO reimplementar resume pra todos os steps intermediários complexos (orphan-signals etc.) — cobrir o caminho linear até `step-5-backend-selection`, que é onde o piloto trava. Steps posteriores caem no pipeline normal.

- [ ] **Step 1: Escrever o teste de resume real (failing first)**

Em `tests/unit/test_engine_init_resume.py`:

```python
def test_resume_continues_from_checkpoint_step(tmp_path, monkeypatch):
    """resume escolhido em re-entrada humana com checkpoint em
    step-5-backend-selection (preset já confirmado) → o init NÃO deve
    re-perguntar 'Confirmar preset kmp-mobile?'; deve reaproveitar
    checkpoint.preset e seguir do backend selection."""
    project_root = tmp_path
    _seed_init_checkpoint(
        project_root,
        step="step-5-backend-selection",
        preset="kmp-mobile",
    )
    _seed_pending_response(project_root, intent_id=_resume_intent_id(project_root), value="resume")
    pending = _run_init_and_capture_pending(project_root)
    # Próxima pausa NÃO pode ser o preset (já confirmado no checkpoint).
    preset_id = ui_question.stable_intent_id(
        "ask", "Confirmar preset kmp-mobile?", _PRESET_OPTIONS,
        extra={"default": "sim", "min-selected": None, "validator-hint": None},
    )
    assert pending is None or pending.get("intent-id") != preset_id, (
        "resume re-perguntou o preset — não continuou do step (P-11)"
    )

def test_resume_labels_do_not_claim_false_continuation(tmp_path):
    """Guard de voz: as labels do prompt de resume não devem afirmar
    'mantendo o checkpoint como audit' para a opção que continua. Após o fix,
    'resume' = 'continuar de onde parou'."""
    from engine.init import _resume_option_labels  # extraído no Step 3
    labels = _resume_option_labels()
    assert "continuar" in labels["resume"].lower()
    assert "audit" not in labels["resume"].lower()
```

- [ ] **Step 2: Rodar, confirmar FAIL**

Run: `.venv/bin/pytest tests/unit/test_engine_init_resume.py -k "continues_from or labels_do_not" -v`
Expected: FAIL — hoje o resume re-pergunta o preset (recomeça do zero) e a label diz "mantendo o checkpoint como audit".

- [ ] **Step 3: Labels honestas + extrair `_resume_option_labels`**

Em `engine/init.py`, extrair o dict de labels do resume pra uma função testável e reescrever as labels:

```python
def _resume_option_labels() -> dict[str, str]:
    """Labels do prompt de resume — honestas pós pilot R1 (P-11).

    'resume' agora CONTINUA do step salvo; 'discard' recomeça limpo.
    """
    return {
        "resume": "continuar de onde o init parou (reaproveita o progresso salvo)",
        "discard": "descartar o checkpoint e recomeçar do zero",
        "abort": "sair sem mexer em nada",
    }
```

Substituir o literal `_resume_options = {...}` (linha ~1329) por `_resume_options = _resume_option_labels()`. O `stable_intent_id` do resume recalcula automaticamente (options mudaram) — atualizar quaisquer testes que hardcodam o id antigo.

- [ ] **Step 4: Implementar continuação do step no ramo `resume`**

Quando `resume_choice == "resume"`, derivar o ponto de retomada do `existing_checkpoint`:

```python
_resume_step = str(existing_checkpoint.get("step") or "step-1-greeting")
_resume_preset = existing_checkpoint.get("preset")
```

No pipeline (Steps 2-4), envolver a re-execução em guards condicionais: se `_resume_step` indica que o preset já foi confirmado (`_resume_step` em `{"step-5-backend-selection", "step-6-resolve", "step-7-snapshot", "step-7-5-orphan-signals"}` E `_resume_preset` setado), pular o `ui_question.ask("Confirmar preset kmp-mobile?", ...)` e usar `preset = _load_preset(_resume_preset)` diretamente, setando `checkpoint.preset = _resume_preset`. Discovery (Step 2) re-roda sempre (é idempotente e barato; produz os `canonical_cards` em memória que o pipeline precisa). Documentar no código que steps após backend-selection caem no pipeline normal (não há resume granular pra orphan-signals nesta rodada).

- [ ] **Step 5: Rodar, confirmar PASS + suíte de resume verde**

Run: `.venv/bin/pytest tests/unit/test_engine_init_resume.py -v`
Expected: PASS. Confirmar que `test_resume_prompt_suppressed_when_response_pending` (WS-A-1) segue verde.

- [ ] **Step 6: Commit**

```bash
git add engine/init.py tests/unit/test_engine_init_resume.py
git commit -m "fix(init): resume real continua do step do checkpoint + labels honestas (P-11)

'resume' agora reaproveita o progresso salvo (pula preset já confirmado)
em vez de recomeçar do zero; labels deixam de afirmar 'mantendo como audit'.
Honra a promessa auto-resumable da Decisão 27 (sem revisita — alinhamento)."
```

---

### Task WS-A-3: Documentar o marker stdout `<FORGE_INTENT>` no schema (P-06)

**Files:**
- Modify: `docs/schemas/intent-protocol.md` (nova seção `## Canal stdout — marker <FORGE_INTENT> (host claude_code)` entre `## File locations` e `## Pending file`)

**Interfaces:**
- Consumes: o formato do marker já emitido por `engine/host/adapters/claude_code.py:283-354` (`_emit_marker`) — atributos `kind`/`intent-id`/`question`/`options`/`default`/`allow-pause` + opcionais `validator-hint`/`min-selected`/`paths-detail`.
- Produces: doc fiel ao canal real do host primário, reconciliando schema ↔ SKILL.md.

**Reuse-first:** doc-only — sem código. O conteúdo é descrição do que `claude_code.py:_emit_marker` já faz (não inventar campos). Confirmar cada atributo lendo `_emit_marker` (`engine/host/adapters/claude_code.py`) antes de documentar.

**Contexto crítico (P-06):** `intent-protocol.md` hoje documenta SÓ o protocolo file-based (`forge-pending.json`). O adapter claude_code (host primário) usa um marker stdout `<FORGE_INTENT .../>` e **NÃO escreve pending.json** (docstring deliberado em `claude_code.py:28-33`). O SKILL.md cobre o marker; o schema diverge. Documentar a diferença: **claude_code = marker stdout, sem pending em disco; intent-file = pending.json em disco**. A response side (`forge-response.json` + consumed-log) é IDÊNTICA nos dois canais.

- [ ] **Step 1: Escrever a seção do marker no schema**

Inserir após `## File locations` (linha ~44, antes do `---` que precede `## Pending file`):

```markdown
## Canal stdout — marker `<FORGE_INTENT>` (host claude_code)

O host **primário** (Claude Code, `CLAUDECODE=1`) NÃO lê `forge-pending.json`.
O `ClaudeCodeAdapter` (`engine/host/adapters/claude_code.py`) anuncia o pending
por um marker auto-fechado de uma linha em **stdout**, e deliberadamente **não
escreve `forge-pending.json`** (seria peso morto — o host já viu o marker):

    <FORGE_INTENT kind="ask" intent-id="…" question="…" options="…" default="…" allow-pause="true" />

| Atributo | Sempre? | Significado |
|---|---|---|
| `kind` | sim | `ask` \| `ask_text` \| `ask_multi` \| `confirm` \| `ask_three_paths` |
| `intent-id` | sim | mesmo `stable_intent_id` do canal file-based (determinístico) |
| `question` | sim | texto da pergunta |
| `options` | sim | JSON-encoded `{key: label}` (vazio `{}` em `ask_text`) |
| `default` | sim | valor default, ou a string literal `"null"` quando ausente |
| `allow-pause` | sim | `"true"` \| `"false"` |
| `validator-hint` | não | presente só quando setado (ex.: `email`) |
| `min-selected` | não | presente só em `ask_multi` com mínimo |
| `paths-detail` | não | JSON-encoded list[dict] — só em `ask_three_paths` |

Valores são XML-attribute-quoted (`xml.sax.saxutils.quoteattr`); `options` e
`paths-detail` são JSON dentro do atributo. O marker é parseável com
`ElementTree.fromstring` (externo) + `json.loads` (payloads aninhados).

### Diferença entre canais

| Canal | Pending | Response | Re-entrada |
|---|---|---|---|
| **claude_code** (`CLAUDECODE=1`) | marker stdout `<FORGE_INTENT>` — sem `forge-pending.json` | `forge-response.json` (host escreve) | idêntica ao file-based |
| **intent-file** (`FORGE_FORCE_INTENT_MODE=1`) | `forge-pending.json` em disco | `forge-response.json` | idêntica |

A **response side é idêntica** nos dois canais: o host escreve
`forge-response.json` com o mesmo `intent-id`, o engine re-invocado consome via
`read_response` (consumed-log §4 garante idempotência). O marker stdout É a
notificação de pending — substitui o arquivo, não o complementa.
```

- [ ] **Step 2: Verificar fidelidade ao código**

Cross-check cada atributo contra `engine/host/adapters/claude_code.py:_emit_marker` (linhas 331-352). Confirmar: `default=None` → `"null"` (linha 337); opcionais emitidos só quando `is not None` (linhas 342-347). Sem `forge verify`/pytest necessário (doc-only), mas rodar `.venv/bin/pytest tests/ -k "intent_protocol or schema" -m "not integration and not e2e"` se houver teste de doc-schema (não bloqueante se ausente).

- [ ] **Step 3: Commit**

```bash
git add docs/schemas/intent-protocol.md
git commit -m "docs(schema): documenta marker stdout <FORGE_INTENT> + canais claude_code vs intent-file (P-06)

Reconcilia intent-protocol.md com SKILL.md: o host primário usa marker
stdout (sem pending em disco), o fallback usa forge-pending.json. Response
side idêntica nos dois. Fiel a claude_code.py:_emit_marker."
```

---

## WS-B — Detecção brownfield + resolver (P-03, P-09, P-10, P-04)

### Task WS-B-1: Cards por-plataforma declaram `identity.platforms` — fim do CONFLITO falso (P-03)

**Files:**
- Modify: `cards/compose-screens/card.yaml` (adicionar `identity.platforms: [android]`)
- Modify: `cards/swiftui-screens/card.yaml` (`identity.platforms: [ios]`)
- Modify: `cards/nav3/card.yaml` (`identity.platforms: [android]`)
- Modify: `cards/swiftui-navigation/card.yaml` (`identity.platforms: [ios]`)
- Modify: `docs/schemas/card.md` (documentar `identity.platforms` como campo aditivo opcional, schema-version permanece 1)
- Test: `tests/integration/test_init_brownfield_multi_axis.py` (per-platform não conflita; partição correta)

**Interfaces:**
- Consumes: `engine.init._card_platforms(card: CardManifest) -> list[str]` (`engine/init.py:2187`) — lê `identity.platforms` com fallback KMP `["android","ios","kmp"]`; `engine.detection.composer.compose_backend_axes(project_root, active_cards) -> dict[axis][platform] -> Cell|Conflict|None` (chaveia por `(axis, platform)` — conflito só quando 2+ cards no MESMO `(axis, platform)`).
- Produces: cards UI/nav por-plataforma mapeados à sua plataforma própria → composer não os coloca no mesmo `(axis, platform)` → sem Conflict; partição android/ios/kmp deixa de repetir o mesmo set nas 3 linhas.

**Reuse-first:** NÃO escrever lógica de partição nova. O composer JÁ chaveia por `(axis, platform)` corretamente (`composer.py:222-244`) — Conflict só surge quando 2+ cards compartilham o mesmo `(axis, platform)`. A causa-raiz (relatório P-03) é `_card_platforms` retornar o fallback `["android","ios","kmp"]` pra TODO card que não declara `identity.platforms` — então `compose-screens` (Android) e `swiftui-screens` (iOS) ambos caem em `(ui, android)`, `(ui, ios)`, `(ui, kmp)` → CONFLITO em toda linha. Fix: os cards declaram suas plataformas reais; o fallback existente cobre cards genuinamente cross-platform. `forge graph` Q11/grep confirma que `_card_platforms` é o único ponto de derivação de platforms — sem duplicata a corrigir.

**Contexto crítico:** o fix é DECLARATIVO (4 card.yaml) + DOC, não código. Validar via `validate_card_yaml.py` que `identity.platforms` (quando presente) é list[str] não-vazia com valores ∈ `{android, ios, kmp}`. Confirmar se o validator já aceita o campo aditivo (schema-version 1 permanece — campo opcional). Se `validate_card_yaml` rejeitar campo desconhecido, estender o schema-allow (escopo mínimo: aceitar `platforms` opcional).

- [ ] **Step 1: Escrever o teste de não-conflito por-plataforma (failing first)**

Em `tests/integration/test_init_brownfield_multi_axis.py`:

```python
import pytest
from engine.init import _normalize_cards_for_composer
from engine.detection.composer import compose_backend_axes, Conflict
from engine.cards.loader import load_all_cards
from engine.utils.paths import cards_canonical_dir

@pytest.mark.integration
def test_kmp_per_platform_ui_cards_do_not_conflict(tmp_path):
    """compose-screens (Android) + swiftui-screens (iOS) são complementares
    por-plataforma, NÃO conflito. Após declararem identity.platforms, o
    composer não os coloca no mesmo (ui, platform) → zero Conflict no eixo ui."""
    cards = load_all_cards(cards_canonical_dir())
    by_name = {c.name: c for c in cards}
    subset = [by_name["compose-screens"], by_name["swiftui-screens"],
              by_name["nav3"], by_name["swiftui-navigation"]]
    normalized = _normalize_cards_for_composer(subset)
    # Força match dos signals: tmp_path com markers mínimos OU monkeypatch do
    # threshold — reusar o pattern de fixtures existente neste arquivo que
    # já exercita compose_backend_axes (ver setup do teste de uniformity).
    result = compose_backend_axes(tmp_path, normalized, threshold=0.0)
    for axis in ("ui", "navigation"):
        for platform, cell in result.get(axis, {}).items():
            assert not isinstance(cell, Conflict), (
                f"({axis}, {platform}) é Conflict — partição por-plataforma quebrada (P-03)"
            )

@pytest.mark.integration
def test_per_platform_cards_partition_to_own_platform(tmp_path):
    """compose-screens só aparece em (ui, android); swiftui-screens só em
    (ui, ios). O mesmo set não pode repetir nas 3 linhas."""
    cards = load_all_cards(cards_canonical_dir())
    by_name = {c.name: c for c in cards}
    normalized = _normalize_cards_for_composer([by_name["compose-screens"], by_name["swiftui-screens"]])
    result = compose_backend_axes(tmp_path, normalized, threshold=0.0)
    ui = result.get("ui", {})
    # compose-screens NÃO deve estar em (ui, ios); swiftui-screens NÃO em (ui, android).
    assert "ios" not in ui or _cell_card_ids(ui.get("ios")) != {"compose-screens"}
    assert "android" not in ui or "swiftui-screens" not in _cell_card_ids(ui.get("android"))
```

`_cell_card_ids` é helper local: extrai `{card_id}` de um `Cell` ou os de um `Conflict.candidates`.

- [ ] **Step 2: Rodar, confirmar FAIL**

Run: `.venv/bin/pytest tests/integration/test_init_brownfield_multi_axis.py -k "per_platform" -v`
Expected: FAIL — hoje os 4 cards caem em todas as plataformas (fallback) → Conflict em `(ui, *)` e `(navigation, *)`.

- [ ] **Step 3: Declarar `identity.platforms` nos 4 cards**

Em cada `card.yaml`, no bloco `identity:`, adicionar a chave `platforms`:
- `cards/compose-screens/card.yaml` → `platforms: [android]`
- `cards/swiftui-screens/card.yaml` → `platforms: [ios]`
- `cards/nav3/card.yaml` → `platforms: [android]`
- `cards/swiftui-navigation/card.yaml` → `platforms: [ios]`

Inserir logo após `maintainer:` no bloco identity, com a indentação canônica do arquivo (2 espaços + alinhamento dos valores como os campos vizinhos).

- [ ] **Step 4: Garantir que `validate_card_yaml` aceita o campo + atualizar schema**

Conferir se `validators/validate_card_yaml.py` rejeita chaves desconhecidas em `identity`. Se rejeitar, adicionar `platforms` à allow-list de identity como `list[str]` opcional, valores ∈ `{android, ios, kmp}`. Em `docs/schemas/card.md`, na seção do bloco `identity`, documentar: `platforms` (opcional, list[str], default = `[android, ios, kmp]` quando ausente; declara a quais plataformas o card aplica — usado pelo composer pra partição por-plataforma; schema-version permanece 1, campo aditivo).

- [ ] **Step 5: Rodar testes + validar cards**

Run: `.venv/bin/pytest tests/integration/test_init_brownfield_multi_axis.py -v` e `.venv/bin/pytest tests/validators/test_validate_card_yaml.py -v`
Run: `forge verify` (cascade não deve hard-fail nos 4 cards editados)
Expected: PASS. Os 4 cards validam; composer não gera Conflict por-plataforma.

- [ ] **Step 6: Commit**

```bash
git add cards/compose-screens/card.yaml cards/swiftui-screens/card.yaml cards/nav3/card.yaml cards/swiftui-navigation/card.yaml docs/schemas/card.md validators/validate_card_yaml.py tests/integration/test_init_brownfield_multi_axis.py
git commit -m "fix(cards): cards UI/nav declaram identity.platforms — fim do CONFLITO falso KMP (P-03)

compose-screens/nav3 = [android]; swiftui-screens/swiftui-navigation = [ios].
O composer chaveia por (axis, platform) — sem platforms reais, o fallback
[android,ios,kmp] punha Android+iOS no mesmo bucket → CONFLITO em toda linha.
Campo aditivo opcional (schema-version 1). Doc em card.md."
```

---

### Task WS-B-2: Detecção inclui o provider quando a security-rule é detectada — fim do DEP-MISSING (P-09)

**Files:**
- Modify: `engine/init.py:1532-1567` (após compor `selected_card_names`, fechar deps de provider antes do resolver)
- Test: `tests/integration/test_init_brownfield_multi_axis.py` (security-rule detectada arrasta o provider)

**Interfaces:**
- Consumes: `engine.cards.loader.CardManifest` (campos `.name`, `.requires: list[str]`, `.provides: list[str]`); `card_index: dict[str, CardManifest]` já construído em `init.py:1495` via `_index_cards`; `engine.cards.resolver.resolve(cards, *, user_provided_capabilities) -> ResolverResult`.
- Produces: quando `firestore-security-rules` está em `selected_card_names` mas `persistence-server` não é provido por nenhum card selecionado, o init INCLUI o card provider (`firestore-persistence`) automaticamente, tornando o conjunto resolvível.

**Reuse-first:** o resolver (`engine/cards/resolver.py:62-69`) JÁ computa DEP-MISSING comparando `card.requires` vs `providers`. NÃO reimplementar resolução de deps. A correção é um passo de *dep-closure* no init ANTES do resolver: pra cada card selecionado com `requires`, se nenhum card selecionado provê o label e existe um card no catálogo que o provê, incluí-lo. Reusar `card.requires`/`card.provides` (já no CardManifest) + `card_index` (já construído). Grep: `known_singular_labels`/`providers` no resolver são a referência de como labels são providos — espelhar a lógica de match (label ∈ card.provides) sem duplicar o resolver inteiro (closure é só o passo aditivo de "puxar o provider faltante").

**Contexto crítico (P-09):** MeoBonsai tem `firestore.rules` → `firestore-security-rules` detecta (threshold 0.4, signal `firestore.rules` confidence 0.5). Mas `firestore-persistence` (provê `persistence-server`) precisa de gradle-dep `firebase-firestore` + uso de `FirebaseFirestore` (threshold 0.5) que a detecção não alcançou. `firestore-security-rules.requires = [persistence-server]` → resolver aborta DEP-MISSING. Fix (design aprovado, opção "incluir o provider"): ao detectar `firestore-security-rules` (ou qualquer card cujo `requires` não está coberto), incluir o card que provê o label faltante. Escopo: dep-closure de 1 nível pelos cards CANÔNICOS (não inventar cards). Se NENHUM card canônico provê o label, deixar o resolver reportar DEP-MISSING (caso genuíno → cai no gate de recuperação interativa do WS-B-3).

- [ ] **Step 1: Escrever o teste de dep-closure (failing first)**

Em `tests/integration/test_init_brownfield_multi_axis.py`:

```python
@pytest.mark.integration
def test_security_rule_detection_pulls_persistence_provider(tmp_path):
    """firestore-security-rules selecionado sem o provider → o init deve
    incluir firestore-persistence (provê persistence-server) antes do
    resolver, tornando o conjunto resolvível (P-09)."""
    from engine.init import _close_provider_deps  # extraído no Step 3
    from engine.cards.loader import load_all_cards
    from engine.utils.paths import cards_canonical_dir
    cards = load_all_cards(cards_canonical_dir())
    card_index = {c.name: c for c in cards}
    selected = ["firestore-security-rules"]
    closed = _close_provider_deps(selected, card_index)
    assert "firestore-persistence" in closed, (
        "dep-closure não puxou o provider de persistence-server (P-09)"
    )

@pytest.mark.integration
def test_closed_set_resolves_without_dep_missing(tmp_path):
    from engine.init import _close_provider_deps
    from engine.cards.resolver import resolve
    from engine.cards.loader import load_all_cards
    from engine.utils.paths import cards_canonical_dir
    cards = load_all_cards(cards_canonical_dir())
    card_index = {c.name: c for c in cards}
    closed = _close_provider_deps(["firestore-security-rules"], card_index)
    res = resolve([card_index[n] for n in closed if n in card_index],
                  user_provided_capabilities=["android-platform", "ios-platform"])
    assert not any("DEP-MISSING" in e for e in res.errors), (
        f"resolver ainda reporta DEP-MISSING: {res.errors}"
    )
```

(`user_provided_capabilities` reusa o `LATENT_CAPS` que `init.py:1567` passa — conferir o símbolo exato e espelhar.)

- [ ] **Step 2: Rodar, confirmar FAIL**

Run: `.venv/bin/pytest tests/integration/test_init_brownfield_multi_axis.py -k "persistence_provider or resolves_without" -v`
Expected: FAIL — `_close_provider_deps` não existe ainda (ImportError) ou o set não inclui o provider.

- [ ] **Step 3: Implementar `_close_provider_deps`**

Em `engine/init.py`, adicionar:

```python
def _close_provider_deps(
    selected_card_names: list[str],
    card_index: dict[str, "CardManifest"],
) -> list[str]:
    """Fecha deps de provider de 1 nível antes do resolver (pilot R1, P-09).

    Pra cada card selecionado, se algum label em `requires` não é provido por
    nenhum card já selecionado, procura no catálogo canônico um card que o
    provê e o inclui. Conservador: 1 nível (o provider incluído pode trazer
    seus próprios requires — esses caem no resolver, que reporta DEP-MISSING
    real se ainda faltar; daí o gate de recuperação do WS-B-3). NÃO inventa
    cards — só puxa do catálogo existente. Determinístico: ordem de inclusão
    alfabética por nome do provider.

    Latentes (android-platform/ios-platform/...) NÃO são fechados aqui — são
    user_provided_capabilities passados ao resolver.
    """
    closed = list(selected_card_names)
    selected_set = set(closed)
    # provider index: label -> sorted card names que o provêem (catálogo todo).
    label_providers: dict[str, list[str]] = {}
    for name, card in card_index.items():
        for label in (card.provides or []):
            label_providers.setdefault(label, []).append(name)
    for plist in label_providers.values():
        plist.sort()
    # Labels já cobertos pelos cards selecionados.
    def _provided_by_selected() -> set[str]:
        covered: set[str] = set()
        for name in closed:
            card = card_index.get(name)
            if card:
                covered.update(card.provides or [])
        return covered
    covered = _provided_by_selected()
    for name in list(closed):
        card = card_index.get(name)
        if not card:
            continue
        for need in (card.requires or []):
            if need in covered:
                continue
            providers = label_providers.get(need, [])
            if not providers:
                continue  # nenhum card canônico provê → resolver reporta DEP-MISSING
            provider = providers[0]
            if provider not in selected_set:
                closed.append(provider)
                selected_set.add(provider)
                covered.update(card_index[provider].provides or [])
    return closed
```

- [ ] **Step 4: Wire o dep-closure no pipeline antes do resolver**

Em `engine/init.py`, entre a composição de `selected_card_names` (linha ~1534-1537) e a montagem de `selected_cards` (linha ~1545), inserir:

```python
selected_card_names = _close_provider_deps(selected_card_names, card_index)
```

Atualizar o comentário do bloco pra citar P-09. O loop `for name in selected_card_names:` que segue (monta `selected_cards`/`missing_cards`) consome o set já fechado.

- [ ] **Step 5: Rodar testes + suíte de init**

Run: `.venv/bin/pytest tests/integration/test_init_brownfield_multi_axis.py -v` e `.venv/bin/pytest -k "init" -m "not e2e"`
Expected: PASS. Conjunto com firestore-security-rules resolve sem DEP-MISSING.

- [ ] **Step 6: Commit**

```bash
git add engine/init.py tests/integration/test_init_brownfield_multi_axis.py
git commit -m "fix(init): dep-closure de provider antes do resolver — fim do DEP-MISSING (P-09)

Quando firestore-security-rules é detectado sem o provider de
persistence-server, o init puxa firestore-persistence do catálogo antes do
resolver. 1 nível, só cards canônicos (não inventa). Deps genuinamente
órfãs caem no gate de recuperação (WS-B-3)."
```

---

### Task WS-B-3: Gate RESOLVER-ERRORS pausa (exit 2) pra escolha em vez de abortar (P-10)

**Files:**
- Modify: `engine/init.py:1564-1591` (substituir `three_paths_block` + `fail_with_tag(ERR_ABORTED)` por `ask_three_paths` real)
- Test: `tests/integration/test_init_brownfield_multi_axis.py` (gate emite intent exit-2, não exit-1)

**Interfaces:**
- Consumes: `engine.ui.question.ask_three_paths(gate_name: str, paths: Sequence[Mapping[str,str]]) -> str` (retorna `"a"|"b"|"c"`, emite intent + raise `PausedForInputError` na primeira entrada → exit 2 via `cli.main`); `engine.ui.exit_codes.fail_with_tag`; `ResolverResult.errors`.
- Produces: o gate de resolver-errors PAUSA (exit 2) pra o usuário escolher recuperação, em vez de abortar (exit 1). Caminho "a" (voltar/re-rodar backend), "b" (abortar pra investigar), "c" (seguir só com cards resolvíveis — best-effort).

**Reuse-first:** `ask_three_paths` JÁ é o mecanismo canônico de gate interativo (`engine/ui/question.py:722`) — usado em `plan.py:1029,1392,1651`. NÃO escrever um gate custom. A correção troca o `mentor_calmo.three_paths_block(...)` (render cosmético read-only) + `fail_with_tag(ERR_ABORTED)` por uma chamada real a `ask_three_paths`, cujo retorno o init processa. Grep: `plan.py:1029` (`ask_three_paths("readiness-not-ready", [...])`) é o template de uso — espelhar a forma (3 paths com label+motive, switch no retorno).

**Contexto crítico (P-10):** hoje o gate renderiza o bloco "Três caminhos" mas termina com `fail_with_tag(ERR_ABORTED)` (exit 1) — o 3-caminhos é COSMÉTICO (não emite intent, não aceita escolha). Combinado com P-02/P-09 deixava o usuário sem saída. Após WS-B-2, a maioria dos DEP-MISSING some; este gate é a rede pra DEP-MISSING genuíno (label sem provider canônico) ou CONFLICT residual. Escopo: pausar pra escolha. Caminho "c" (seguir best-effort) deve usar o subconjunto resolvível — se inviável dentro do escopo, "c" = "abortar e investigar" e o terceiro caminho real é "voltar ao backend selection". Manter exatamente 3 paths (disciplina §1).

- [ ] **Step 1: Escrever o teste do gate-pausa (failing first)**

Em `tests/integration/test_init_brownfield_multi_axis.py`:

```python
@pytest.mark.integration
def test_resolver_error_gate_pauses_not_aborts(tmp_path, monkeypatch):
    """Quando o resolver retorna errors, o init deve PAUSAR (exit 2, emite
    intent ask_three_paths) em vez de abortar (exit 1) — P-10. Sem response
    pendente, a primeira entrada emite o intent e levanta PausedForInputError."""
    from engine.host.adapter import PausedForInputError
    # Forçar um conjunto com DEP-MISSING genuíno (label sem provider canônico):
    # monkeypatch _close_provider_deps pra no-op + selecionar um card cujo
    # requires não tem provider no catálogo (fixture/seed conforme pattern
    # existente). OU testar _resolver_error_gate diretamente (ver Step 3).
    from engine.init import _resolver_error_gate
    with pytest.raises(PausedForInputError):
        _resolver_error_gate(["DEP-MISSING: card 'x' requires 'y' ..."],
                             selected_names=["x"], project_root=tmp_path)
```

- [ ] **Step 2: Rodar, confirmar FAIL**

Run: `.venv/bin/pytest tests/integration/test_init_brownfield_multi_axis.py -k "gate_pauses" -v`
Expected: FAIL — `_resolver_error_gate` não existe (ImportError) ou o caminho atual retorna exit 1 sem raise.

- [ ] **Step 3: Extrair + reescrever o gate como `ask_three_paths` real**

Em `engine/init.py`, extrair o bloco de erro do resolver pra uma função e usar `ask_three_paths`:

```python
def _resolver_error_gate(
    errors: list[str],
    *,
    selected_names: list[str],
    project_root: Path,
) -> str:
    """Gate de resolver-errors — PAUSA pra escolha (exit 2), não aborta (P-10).

    Retorna a escolha 'a'|'b'|'c'. Na primeira entrada, ask_three_paths emite
    o intent + levanta PausedForInputError (cli.main → exit 2); na re-entrada
    consome a response. Mantém exatamente 3 caminhos (disciplina §1).
    """
    paths = [
        {
            "label": "voltar e re-selecionar o backend",
            "motive": "alguns cards ficaram sem dependência satisfeita — re-rodar o backend selection pode incluir o provider faltante",
        },
        {
            "label": "abortar e investigar os cards canônicos",
            "motive": "pode ser um card.yaml com requires sem provider no catálogo (bug de card)",
        },
        {
            "label": "seguir só com os cards resolvíveis",
            "motive": "descarta os cards problemáticos e instala o subconjunto que resolve (best-effort)",
        },
    ]
    gate_name = (
        "RESOLVER-ERRORS\n\nErros do resolver:\n"
        + "\n".join(f"  · {e}" for e in errors[:5])
    )
    return ui_question.ask_three_paths(gate_name, paths)
```

No `_run_pipeline`, substituir o bloco `if res.errors:` (linhas ~1568-1591) por:

```python
if res.errors:
    choice = _resolver_error_gate(res.errors, selected_names=[c.name for c in selected_cards], project_root=project_root)
    if choice == "a":
        # Volta ao backend selection — re-deriva selected_card_names.
        # Escopo R1: sinaliza re-run; loop estruturado fica pra rodada futura
        # se necessário. Por ora, instrui o usuário e aborta limpo.
        renderer.write("Re-rode `forge init` após ajustar — o backend será re-perguntado.")
        return fail_with_tag(ERR_ABORTED)
    if choice == "b":
        return fail_with_tag(ERR_ABORTED)
    # choice == "c": filtra os cards envolvidos em DEP-MISSING/CONFLICT e
    # re-resolve o subconjunto. Se o subconjunto resolve, segue; senão aborta.
    resolvable = _drop_unresolvable_cards(selected_cards, res.errors)
    res = resolve(resolvable, user_provided_capabilities=LATENT_CAPS)
    if res.errors:
        renderer.write(renderer.colored("Subconjunto ainda não resolve — abortado.", "yellow"))
        return fail_with_tag(ERR_ABORTED)
    selected_cards = resolvable
```

`_drop_unresolvable_cards(selected_cards, errors)` é helper local minimalista: parseia os nomes de card citados nos erros DEP-MISSING/CONFLICT-* e os remove do set (determinístico, preserva ordem). Documentar que é best-effort. (Reuso: o formato das mensagens é estável — `resolver.py:65-105` — então o parse é por prefixo de mensagem.)

- [ ] **Step 4: Rodar testes + suíte de init**

Run: `.venv/bin/pytest tests/integration/test_init_brownfield_multi_axis.py -v` e `.venv/bin/pytest -k "init" -m "not e2e"`
Expected: PASS. O gate levanta `PausedForInputError` na primeira entrada (exit 2), não exit 1.

- [ ] **Step 5: Commit**

```bash
git add engine/init.py tests/integration/test_init_brownfield_multi_axis.py
git commit -m "fix(init): gate RESOLVER-ERRORS pausa pra escolha (exit 2) em vez de abortar (P-10)

ask_three_paths real (intent + exit 2) substitui o three_paths_block
cosmético + fail_with_tag. Caminho c re-resolve o subconjunto resolvível.
Rede pra DEP-MISSING genuíno após o dep-closure de WS-B-2."
```

---

### Task WS-B-4: Separar a tabela de detecção do campo `question` (P-04)

**Files:**
- Modify: `engine/init.py:2421-2427` (parar de embutir a tabela no `gate_name`; imprimir como contexto antes)
- Test: `tests/integration/test_init_brownfield_multi_axis.py` (a tabela não vai no campo question/gate_name)

**Interfaces:**
- Consumes: `engine.init._render_axes_table(composer_result, uniformity) -> str` (`init.py:2266`); `renderer.write` (já usado no pipeline pra contexto cinematográfico); `ui_question.ask_three_paths(gate_name, paths)`.
- Produces: a tabela de detecção é impressa como contexto (via `renderer`) ANTES do `ask_three_paths`; o `gate_name` passa a ser curto (`"init-brownfield-detection"`).

**Reuse-first:** `renderer.write` JÁ é o canal de contexto pré-prompt no pipeline (ex.: `init.py:1505-1506` imprime "[1:00] Backend…"). NÃO criar um campo de payload novo no intent — mover a tabela pra o canal de contexto que já existe. A tabela em si (`_render_axes_table`) não muda.

**Contexto crítico (P-04):** hoje `gate_name = "init-brownfield-detection\n\nDetection composta:\n" + table` (`init.py:2425`) embute 20+ linhas no `question`/`gate_name`. `ask_three_paths` constrói `question_text = f"Qual caminho para resolver '{gate_name}'?"` (`question.py:757`) — o blob gigante vira a "pergunta". Fix: imprimir a tabela via `renderer.write` (host vê como contexto), manter `gate_name` curto. O host renderiza a pergunta curta + as 3 opções; a tabela aparece antes, no fluxo de saída.

- [ ] **Step 1: Escrever o teste (failing first)**

Em `tests/integration/test_init_brownfield_multi_axis.py`:

```python
@pytest.mark.integration
def test_detection_table_not_embedded_in_question(tmp_path, monkeypatch):
    """A tabela de detecção NÃO deve estar no gate_name/question do intent
    ask_three_paths — apenas um gate_name curto (P-04)."""
    captured = {}
    import engine.ui.question as q
    orig = q.ask_three_paths
    def _spy(gate_name, paths):
        captured["gate_name"] = gate_name
        raise SystemExit(0)  # interrompe após capturar
    monkeypatch.setattr(q, "ask_three_paths", _spy)
    # ... invocar _handle_backend_multi_axis_brownfield com active_cards que
    # produzem uma tabela (reusar fixture existente do arquivo) ...
    try:
        _invoke_brownfield_handler(tmp_path)  # helper local
    except SystemExit:
        pass
    gn = captured.get("gate_name", "")
    assert "·" not in gn and "CONFLITO" not in gn and gn.count("\n") <= 1, (
        f"tabela ainda embutida no gate_name: {gn!r}"
    )
```

- [ ] **Step 2: Rodar, confirmar FAIL**

Run: `.venv/bin/pytest tests/integration/test_init_brownfield_multi_axis.py -k "not_embedded_in_question" -v`
Expected: FAIL — hoje o `gate_name` carrega a tabela inteira.

- [ ] **Step 3: Mover a tabela pro canal de contexto**

Em `engine/init.py`, no `_handle_backend_multi_axis_brownfield` (linhas ~2421-2427), substituir:

```python
gate_name = "init-brownfield-detection\n\nDetection composta:\n" + table
choice_key = ui_question.ask_three_paths(gate_name, paths)
```

por:

```python
# P-04: tabela vai como CONTEXTO (canal renderer), não no campo question.
from engine.ui import renderer as _renderer  # ou o import canônico já usado
_renderer.write("")
_renderer.write("Detecção composta (axis × plataforma):")
_renderer.write(table)
_renderer.write("")
choice_key = ui_question.ask_three_paths("init-brownfield-detection", paths)
```

Conferir o símbolo de renderer já usado no módulo (init.py usa `renderer.write` — usar o mesmo handle). `gate_name` curto e estável.

- [ ] **Step 4: Rodar testes**

Run: `.venv/bin/pytest tests/integration/test_init_brownfield_multi_axis.py -v`
Expected: PASS. A tabela continua visível (canal de contexto), o `gate_name` é curto.

- [ ] **Step 5: Commit**

```bash
git add engine/init.py tests/integration/test_init_brownfield_multi_axis.py
git commit -m "fix(init): tabela de detecção vira contexto, question curto (P-04)

A tabela (20+ linhas) embutida no gate_name virava um blob gigante como
'pergunta' no AskUserQuestion. Agora imprime via renderer antes do prompt;
gate_name = 'init-brownfield-detection'."
```

---

## WS-C — Paths phantom mínimo (P-02)

### Task WS-C-1: Ocultar paths b/c não-implementados com label limpa + anotar W7.2 (P-02)

**Files:**
- Modify: `engine/init.py:2394-2449` (paths b/c sem texto dev "[W7.2 …]"; garantir caminho funcional "a")
- Modify: `docs/design/04-pending.md` (anotar W7.2 como gap deferido)
- Test: `tests/integration/test_init_brownfield_multi_axis.py` (sem leak "W7.2"; "a" funcional)

**Interfaces:**
- Consumes: `ui_question.ask_three_paths(gate_name, paths)` (exige exatamente 3 paths, disciplina §1); o handler `_handle_backend_multi_axis_brownfield` (`init.py:2338`) que retorna `choice ∈ {confirm, adjust, scratch}`.
- Produces: as 3 labels não vazam roadmap interno ("[W7.2 …]"); b/c têm motive honesto ("ainda não disponível nesta versão") e o caller trata `adjust`/`scratch` como fallback limpo (cai em "confirm as-is" ou aborta com mensagem clara), NUNCA com texto dev.

**Reuse-first:** sem código novo. A disciplina §1 exige 3 paths — NÃO reduzir pra 1. A correção é editorial (remover "[W7.2 …]" + motive honesto) + garantir que o caller não trava em `adjust`/`scratch`. Grep: `_handle_backend_multi_axis_brownfield` retorna `selected_card_names: []` em adjust/scratch (`init.py:2439-2448`) — o caller (`init.py:1515-1516`) usa `result.get("selected_card_names")`; confirmar que set vazio + preset universals ainda produz um conjunto válido (preset cards sempre entram, `init.py:1534`).

**Contexto crítico (P-02 + Mandamento 5):** as labels b/c trazem "[W7.2 implementa o multi-select.]" / "[W7.2 implementa o fluxo greenfield.]" — texto de dev/roadmap no artefato do usuário (viola Mandamento 5). NÃO implementar W7.2 (anti-goal explícito). Manter 3 paths (disciplina), mas: (a) remover o texto "[W7.2 …]"; (b) motive honesto ("ainda não disponível — use 'confirmar como-is' por ora"); (c) garantir que escolher b/c não trava nem vaza texto dev — cai num fallback limpo. Após WS-B-1/B-2, "confirmar como-is" (path "a") é funcional, então b/c serem fallback-pra-a é aceitável nesta rodada.

- [ ] **Step 1: Escrever o teste (failing first)**

Em `tests/integration/test_init_brownfield_multi_axis.py`:

```python
@pytest.mark.integration
def test_brownfield_paths_no_dev_text_leak(tmp_path, monkeypatch):
    """As 3 labels/motives do gate brownfield NÃO podem conter 'W7.2' nem
    colchetes de roadmap interno (Mandamento 5 / P-02)."""
    captured = {}
    import engine.ui.question as q
    def _spy(gate_name, paths):
        captured["paths"] = paths
        raise SystemExit(0)
    monkeypatch.setattr(q, "ask_three_paths", _spy)
    try:
        _invoke_brownfield_handler(tmp_path)
    except SystemExit:
        pass
    blob = " ".join(p.get("label","") + " " + p.get("motive","") for p in captured["paths"])
    assert "W7.2" not in blob, "leak de roadmap interno nas labels (P-02)"
    assert "[" not in blob and "]" not in blob, "texto dev entre colchetes nas labels"

@pytest.mark.integration
def test_brownfield_confirm_path_produces_valid_set(tmp_path):
    """Path 'a' (confirmar como-is) produz selected_card_names não-vazio
    após WS-B (preset universals sempre entram)."""
    # response pendente = "a"; reusar pattern de seed do arquivo.
    result = _invoke_brownfield_handler_with_choice(tmp_path, "a")
    assert result["choice"] == "confirm"
```

- [ ] **Step 2: Rodar, confirmar FAIL**

Run: `.venv/bin/pytest tests/integration/test_init_brownfield_multi_axis.py -k "no_dev_text or confirm_path_produces" -v`
Expected: FAIL no leak test (hoje as labels contêm "[W7.2 …]").

- [ ] **Step 3: Reescrever os motives de b/c**

Em `engine/init.py`, no `paths` de `_handle_backend_multi_axis_brownfield` (linhas ~2396-2419), reescrever os motives de b e c removendo "[W7.2 …]" e dando motive honesto:

```python
paths = [
    {
        "label": "Confirmar detection como-is",
        "motive": (
            "Aceita a tabela detectada acima e segue com esses cards pro "
            "resolve. Caminho recomendado."
        ),
    },
    {
        "label": "Ajustar células divergentes",
        "motive": (
            "Escolher card por célula ainda não está disponível nesta versão "
            "— por ora, confirme como-is e ajuste depois com `forge reconfigure`."
        ),
    },
    {
        "label": "Começar do zero (custom)",
        "motive": (
            "O fluxo greenfield-style ainda não está disponível nesta versão "
            "— por ora, confirme como-is."
        ),
    },
]
```

Manter o switch em `choice_key`: "a"→confirm (já funcional); "b"/"c" continuam retornando `adjust`/`scratch` com `selected_card_names: []` — o caller compõe com os preset universals (sempre presentes). Atualizar os comentários do código pra refletir P-02 (sem citar W7.2 em texto user-facing; OK no comentário interno).

- [ ] **Step 4: Anotar W7.2 como gap deferido em 04-pending.md**

Em `docs/design/04-pending.md`, adicionar (antes do bloco de leitura final "For a fresh session…"):

```markdown
## W7.2 — multi-select per-cell + greenfield picker (deferido, pilot R1)

O handler brownfield (`engine/init._handle_backend_multi_axis_brownfield`)
oferece 3 caminhos, mas "Ajustar células divergentes" (b) e "Começar do zero
custom" (c) não estão implementados — caem em fallback pra "confirmar como-is".
O pilot R1 (P-02) removeu o texto dev "[W7.2 …]" das labels e deu motive
honesto; a implementação real dos paths b/c (multi-select per-cell, picker
greenfield) fica deferida. Quando implementar: `_run_per_axis_prompts` +
`_apply_axis_overrides` (já existem no módulo, usados pelo greenfield) são a
base reusável.
```

- [ ] **Step 5: Rodar testes**

Run: `.venv/bin/pytest tests/integration/test_init_brownfield_multi_axis.py -v`
Expected: PASS. Sem leak; path "a" produz conjunto válido.

- [ ] **Step 6: Commit**

```bash
git add engine/init.py docs/design/04-pending.md tests/integration/test_init_brownfield_multi_axis.py
git commit -m "fix(init): remove texto dev '[W7.2]' das labels brownfield + anota gap (P-02)

Motives honestos ('ainda não disponível nesta versão'); b/c caem em
fallback limpo pra 'confirmar como-is' (path funcional após WS-B).
Mantém 3 caminhos (disciplina §1). W7.2 anotado em 04-pending."
```

---

## WS-D — Quality baratos (P-05, P-07, P-08, P-12, README)

### Task WS-D-1: `forge <subcmd> --help --json` emite JSON ou erro explícito (P-05)

**Files:**
- Modify: `engine/cli.py:365-375` (interceptar `--help --json` per-subcomando no dispatch, antes do handler)
- Test: `tests/unit/test_cli_help_json.py` (novo, unit — `init --help --json` não imprime prosa silenciosamente)

**Interfaces:**
- Consumes: `engine.cli._COMMAND_META` (dict `name -> {summary, machine_readable, flags, args, prompts_by_default}`, `cli.py:~289`); `engine.cli._print_help_json()` (top-level manifest, `cli.py:304`); `engine.cli._resolve(cmd)`.
- Produces: `forge <subcmd> --help --json` emite um manifest JSON do subcomando (derivado de `_COMMAND_META[subcmd]`) OU, quando o subcomando não tem meta, um erro explícito em stderr + exit≠0 — nunca ignora `--json` silenciosamente caindo na prosa.

**Reuse-first:** `_COMMAND_META` + `_print_help_json` JÁ existem (top-level manifest). NÃO criar uma segunda fonte de meta. A correção é interceptar `--help --json` no `_main_dispatch` ANTES de delegar ao handler (que só sabe prosa), emitindo o slice de `_COMMAND_META[cmd]` como JSON. Grep: `cli.py:367-375` já trata `--help --json` no nível top-level — espelhar o padrão por-subcomando.

**Contexto crítico (P-05):** `forge --help --json` (top-level) emite manifest correto (`cli.py:371-372`). Mas `forge init --help --json` cai no handler `init.run(["--help","--json"])` que só imprime prosa (`init.py:1212-1224`), ignorando `--json`. Fix: no `_main_dispatch`, detectar `"--help" in rest and "--json" in rest` ANTES do `handler(rest)`, e emitir JSON do subcomando. Decisão 32 (row 32, já locked) cobre meta-flags `--help --json` — este fix é alinhamento, não revisita.

- [ ] **Step 1: Escrever o teste (failing first)**

Em `tests/unit/test_cli_help_json.py`:

```python
import json, io, contextlib
from engine.cli import main

def test_subcommand_help_json_emits_json(monkeypatch):
    """forge init --help --json deve emitir JSON (não prosa) — P-05."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(["init", "--help", "--json"])
    out = buf.getvalue().strip()
    assert rc == 0
    parsed = json.loads(out)  # FALHA se for prosa (não-JSON)
    assert parsed.get("name") == "init"
    assert "summary" in parsed

def test_subcommand_help_json_unknown_meta_errors(monkeypatch):
    """Subcomando sem meta + --help --json → erro explícito, não silêncio."""
    # ex.: um subcomando hidden/sem _COMMAND_META — exit != 0 + stderr.
    ...
```

- [ ] **Step 2: Rodar, confirmar FAIL**

Run: `.venv/bin/pytest tests/unit/test_cli_help_json.py -v`
Expected: FAIL — `forge init --help --json` hoje imprime prosa, `json.loads` levanta `JSONDecodeError`.

- [ ] **Step 3: Interceptar `--help --json` per-subcomando**

Em `engine/cli.py`, no `_main_dispatch`, após resolver `cmd`/`rest` e antes de `handler = _resolve(cmd)` (linha ~408), adicionar:

```python
# P-05: --help --json per-subcomando emite o manifest do subcomando (de
# _COMMAND_META), não a prosa do handler. Decisão 32 (meta-flags opt-in).
if ("--help" in rest or "-h" in rest) and "--json" in rest:
    meta = _COMMAND_META.get(cmd)
    if meta is None:
        sys.stderr.write(
            f"forge {cmd}: --help --json não disponível (sem manifest pra este comando).\n"
        )
        return fail_with_tag(ERR_USAGE)  # tag canônica de usage
    manifest = {"name": cmd, **meta}
    sys.stdout.write(json.dumps(manifest, indent=2, default=str) + "\n")
    return 0
```

Conferir o nome exato da tag de usage em `engine/ui/exit_codes.py` (`ERR_USAGE` ou similar) e o símbolo `_COMMAND_META` (pode ser `_COMMAND_META` ou `COMMAND_META`).

- [ ] **Step 4: Rodar testes**

Run: `.venv/bin/pytest tests/unit/test_cli_help_json.py -v` e `.venv/bin/pytest -k "help or cli" -m "not integration and not e2e"`
Expected: PASS. `forge init --help --json` emite JSON; subcomando sem meta dá erro explícito.

- [ ] **Step 5: Commit**

```bash
git add engine/cli.py tests/unit/test_cli_help_json.py
git commit -m "fix(cli): --help --json per-subcomando emite JSON ou erro explícito (P-05)

Antes caía no handler (só prosa), ignorando --json silenciosamente. Agora
o dispatch intercepta e emite o slice de _COMMAND_META como manifest.
Alinhamento com Decisão 32 (meta-flags opt-in)."
```

---

### Task WS-D-2: Frase de abertura do init — determinística OU documentada (P-07)

**Files:**
- Modify: `engine/init.py:1267` (usar abertura estável no init) OU `engine/persona/mentor_calmo.py:105-107` (documentar variação intencional)
- Test: `tests/unit/test_persona_mentor_calmo.py` (greeting do init é estável entre runs do mesmo comando)

**Interfaces:**
- Consumes: `engine.persona.mentor_calmo.greeting() -> str` (escolhe aleatório de `PHRASES_GREETING`, com seed pinning via `_seed`/`_get_rng`).
- Produces: o init usa uma abertura ESTÁVEL (mesma frase entre runs) — fix do P-07 via abertura fixa pro init, preservando a variação intencional do `greeting()` pra outros contextos.

**Reuse-first:** `mentor_calmo` JÁ tem `greeting()` + RNG com seed (`_get_rng`/`_seed`). A variação é deliberada por design (banner conversacional). Decisão de design (P-07): o piloto reportou a variação como fricção — tornar a abertura do INIT determinística (sem mexer no `greeting()` genérico que outros comandos usam). Reuso: usar a primeira frase de `PHRASES_GREETING` como abertura fixa do init, ou expor `greeting_stable()` que sempre retorna a mesma. NÃO remover a variação do `greeting()` (outros usos dependem do tom).

**Contexto crítico (P-07):** `greeting()` (`mentor_calmo.py:105`) escolhe aleatório de 4 frases. O init chama `mentor_calmo.greeting()` (`init.py:1267`) → varia entre runs. Decisão de design aprovada: o init é um fluxo determinístico (mesma sequência de steps); a abertura também deve ser estável. Fix mínimo: o init usa uma abertura fixa. Documentar no docstring de `greeting()` que a variação é intencional pra contextos conversacionais, mas o init opta por estabilidade.

- [ ] **Step 1: Escrever o teste (failing first)**

Em `tests/unit/test_persona_mentor_calmo.py`:

```python
def test_init_greeting_is_stable_across_runs():
    """A abertura do init deve ser determinística (mesma frase entre runs) —
    P-07. greeting() genérico segue variando (não testado aqui)."""
    from engine.persona.mentor_calmo import greeting_stable  # novo
    assert greeting_stable() == greeting_stable()
```

- [ ] **Step 2: Rodar, confirmar FAIL**

Run: `.venv/bin/pytest tests/unit/test_persona_mentor_calmo.py -k "stable_across_runs" -v`
Expected: FAIL — `greeting_stable` não existe (ImportError).

- [ ] **Step 3: Adicionar `greeting_stable` + wire no init**

Em `engine/persona/mentor_calmo.py`, adicionar:

```python
def greeting_stable() -> str:
    """Abertura determinística — usada por fluxos não-conversacionais (init).

    greeting() varia de propósito pra contextos conversacionais; o init é
    um pipeline determinístico e opta por uma abertura estável (P-07).
    """
    return PHRASES_GREETING[0]
```

Em `engine/init.py:1267`, trocar `renderer.write(mentor_calmo.greeting())` por `renderer.write(mentor_calmo.greeting_stable())`. Atualizar o docstring de `greeting()` (linha 105-107) com uma linha: "Variação intencional pra contextos conversacionais; fluxos determinísticos usam `greeting_stable()`."

- [ ] **Step 4: Rodar testes**

Run: `.venv/bin/pytest tests/unit/test_persona_mentor_calmo.py -v`
Expected: PASS. `greeting_stable` estável; `greeting()` segue variando (testes existentes verdes).

- [ ] **Step 5: Commit**

```bash
git add engine/persona/mentor_calmo.py engine/init.py tests/unit/test_persona_mentor_calmo.py
git commit -m "fix(init): abertura determinística via greeting_stable (P-07)

O init é pipeline determinístico — abertura também. greeting() genérico
preserva a variação intencional pra contextos conversacionais."
```

---

### Task WS-D-3: Opção `outro` do preset sem texto dev + opção `outro` do preset (P-08)

**Files:**
- Modify: `engine/init.py:1458-1473` (label da opção `outro` sem "(não disponível no v1)")
- Test: `tests/unit/test_engine_init_resume.py` ou `tests/integration/test_init_*.py` (label de preset sem texto dev)

**Interfaces:**
- Consumes: `ui_question.ask("Confirmar preset kmp-mobile?", {...}, default="sim")` (`init.py:1458`); o ramo `if choice == "outro": raise InitError(...)` (`init.py:1470-1473`).
- Produces: a opção `outro` ou some, ou tem label limpa (sem "(não disponível no v1 — só kmp-mobile)"); o menu user-facing não vaza roadmap.

**Reuse-first:** editorial — sem código novo. Decisão (P-08): remover a opção morta OU label limpa. Como `ask` precisa de pelo menos a opção `sim` + uma saída, manter `sim` + `abortar` e REMOVER `outro` (é morta — sempre levanta InitError). Grep: o único consumer de `"outro"` é o `if choice == "outro"` logo abaixo — removível junto.

**Contexto crítico (P-08, regressão F3 do v1.2):** label `outro` = "escolher outro preset (não disponível no v1 — só kmp-mobile)" — texto dev. Como só existe kmp-mobile, `outro` é opção morta. Fix mínimo: remover `outro` (e o ramo `if choice == "outro"`). O menu fica `sim`/`abortar`, ambos funcionais.

- [ ] **Step 1: Escrever o teste (failing first)**

```python
def test_preset_prompt_has_no_dead_outro_option(tmp_path, monkeypatch):
    """O prompt de preset não deve oferecer 'outro' (opção morta) nem vazar
    '(não disponível no v1)' — P-08."""
    captured = {}
    import engine.ui.question as q
    def _spy(question, options, default=None, **kw):
        captured["options"] = options
        raise SystemExit(0)
    monkeypatch.setattr(q, "ask", _spy)
    try:
        _run_init_until_preset_prompt(tmp_path)  # helper local
    except SystemExit:
        pass
    opts = captured.get("options", {})
    assert "outro" not in opts, "opção morta 'outro' ainda presente (P-08)"
    blob = " ".join(opts.values())
    assert "não disponível" not in blob and "v1" not in blob
```

- [ ] **Step 2: Rodar, confirmar FAIL**

Run: `.venv/bin/pytest -k "no_dead_outro" -m "not e2e"`
Expected: FAIL — `outro` presente com texto dev.

- [ ] **Step 3: Remover a opção `outro`**

Em `engine/init.py:1458-1466`, remover a entrada `"outro": "escolher outro preset (não disponível no v1 — só kmp-mobile)",` do dict de options. Remover o bloco `if choice == "outro": raise InitError(...)` (linhas ~1470-1473). O menu fica `{"sim": ..., "abortar": ...}`, default `"sim"`.

- [ ] **Step 4: Rodar testes**

Run: `.venv/bin/pytest -k "preset or init" -m "not e2e"`
Expected: PASS. Sem `outro`.

- [ ] **Step 5: Commit**

```bash
git add engine/init.py tests/
git commit -m "fix(init): remove opção morta 'outro' do prompt de preset (P-08)

Só existe kmp-mobile — 'outro' sempre levantava InitError e vazava
'(não disponível no v1)' no menu (regressão F3 do v1.2). Menu fica sim/abortar."
```

---

### Task WS-D-4: ETA antes de etapas longas OU rotular timestamps internos (P-12)

**Files:**
- Modify: `engine/init.py:1380,1506` (rotular os prefixos `[0:01]`/`[1:00]` OU adicionar ETA)
- Test: `tests/integration/test_init_*.py` ou `tests/unit/` (a saída não usa o prefixo `[m:ss]` cru sem rótulo)

**Interfaces:**
- Consumes: `renderer.write("[0:01] Scanning repo…")` (`init.py:1380`), `renderer.write("[1:00] Backend…")` (`init.py:1506`).
- Produces: os prefixos deixam de parecer relógio/ETA — ou são rotulados como passo (ex.: `[passo 1/7]`) ou ganham nota de ETA ("isto pode levar ~30s em monorepos").

**Reuse-first:** editorial. Decisão (P-12): os `[0:01]`/`[1:00]` são relógio interno, sem ETA. Fix mínimo: trocar por rótulo de passo (`[1/7]`) que NÃO se confunde com tempo, e adicionar nota de duração antes do discovery (que é o caro). Grep: só 2 ocorrências do prefixo `[m:ss]` no init (`1380`, `1506`).

**Contexto crítico (P-12, regressão F2/D6):** `[0:01]`/`[1:00]` parecem tempo decorrido/ETA mas são relógio interno fixo. Fix: rotular como passo + nota de duração antes do discovery (scan de monorepo pode demorar). Manter voz mentor calmo.

- [ ] **Step 1: Escrever o teste (failing first)**

```python
@pytest.mark.integration
def test_init_progress_labels_not_clock_like(tmp_path, capsys):
    """A saída do init não deve usar prefixos [m:ss] crus que parecem
    relógio/ETA — P-12. Usar rótulo de passo + nota de duração."""
    _run_init_discovery_phase(tmp_path)  # helper que roda até o discovery
    out = capsys.readouterr().out
    import re
    assert not re.search(r"\[\d:\d{2}\]", out), "prefixo relógio-like ainda presente (P-12)"
```

- [ ] **Step 2: Rodar, confirmar FAIL**

Run: `.venv/bin/pytest -k "progress_labels_not_clock" -m integration`
Expected: FAIL — `[0:01]`/`[1:00]` presentes.

- [ ] **Step 3: Rotular os prefixos + nota de duração**

Em `engine/init.py:1380`, trocar `"[0:01] Scanning repo + cards canônicos…"` por `"[1/7] Lendo o repositório + cards canônicos (pode levar ~30s em monorepos grandes)…"`. Em `init.py:1506`, trocar `"[1:00] Backend — preciso da sua escolha"` por `"[5/7] Backend — preciso da sua escolha"`. (Os números de passo batem com os `checkpoint.step` canônicos.) Voz mentor calmo preservada.

- [ ] **Step 4: Rodar testes**

Run: `.venv/bin/pytest -k "init" -m "not e2e"`
Expected: PASS. Sem prefixo relógio-like.

- [ ] **Step 5: Commit**

```bash
git add engine/init.py tests/
git commit -m "fix(init): rótulo de passo + nota de duração em vez de relógio interno (P-12)

[0:01]/[1:00] pareciam ETA mas eram relógio fixo (regressão F2/D6). Agora
[1/7]/[5/7] + nota 'pode levar ~30s' antes do discovery."
```

---

### Task WS-D-5: Reconciliar drift de stats do README + doc-sync (README + CHANGELOG + handoff)

**Files:**
- Modify: `README.md` (reconciliar validators/cards/tests pra fonte única)
- Modify: `CHANGELOG.md` (entrada `## [Unreleased]` cobrindo os fixes do pilot R1)
- Modify: `docs/design/08-session-handoff.md` (Última atualização + Estado)

**Interfaces:**
- Consumes: fonte canônica de counts = `docs/design/08-session-handoff.md` (handoff). Medições verificadas neste repo: **22 validators non-helper + 3 helpers** (`_gate_infra`/`_diff`/`_common`; `__init__.py` não conta); **30 cards**; tests release 1.5.0 = **rapid 1863 / integration 204 / e2e 30**.
- Produces: README com counts consistentes (uma só fonte): 22 validators (+3 helpers), 30 cards, tests 1863/204/30. CHANGELOG + handoff atualizados.

**Reuse-first:** doc-only. NÃO recontar à mão — usar as medições verificadas: `find validators -maxdepth 1 -name '*.py'` = 26 total; 4 helpers (`__init__`, `_common`, `_diff`, `_gate_infra`); 22 non-helper. `find cards -maxdepth 1 -type d | tail -n +2` = 30 dirs. Tests: handoff linha 7 (release 1.5.0) = rapid 1863 / integration 204 / e2e 30.

**Contexto crítico (drift do README, do relatório):** validators "20" (L14) vs "22" (L5/196) vs "25+3" (L122); cards "22" (L105) vs "29" (L5/120); tests "1797/190" (L125) vs "1863/204" (L5/196). Fonte única = handoff. Counts corretos verificados: **22 validators (3 helpers), 30 cards, tests 1863/204/30**. Reconciliar TODA menção no README pra esses números.

- [ ] **Step 1: Inventariar todas as menções de count no README**

Grep no README por linhas com "validators"/"cards"/"tests"/números de 3-4 dígitos. Listar cada ocorrência divergente (L5, L14, L105, L120, L122, L125, L196 conforme o relatório + quaisquer outras). NÃO editar ainda — mapear o conjunto de edits.

- [ ] **Step 2: Reconciliar para a fonte única**

Em `README.md`, atualizar TODAS as menções:
- Validators → **22 validators** (+ 3 helpers `_gate_infra`/`_diff`/`_common`) — corrigir "20", "25+3", e o "22" que já estava certo permanece. (Nota: "25+3" provavelmente contava algo a mais — usar a medição real: 22 non-helper.)
- Cards → **30 cards canônicos** — corrigir "22" e "29" (o relatório diz 29 mas a medição atual é 30; usar 30, o número real no disco).
- Tests → **rapid 1863 / integration 204 / e2e 30** — corrigir "1797/190".

Se "30" diverge do "29" citado em outros docs por um card adicionado recentemente, confirmar via `find cards -maxdepth 1 -type d | tail -n +2 | wc -l` antes de gravar (a medição manda). Anotar no commit body a fonte da medição.

- [ ] **Step 3: CHANGELOG Unreleased**

Em `CHANGELOG.md`, sob `## [Unreleased]`, adicionar entradas cobrindo o pilot R1:

```markdown
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

### Added (pilot R1)
- `identity.platforms` documentado em `docs/schemas/card.md` (campo aditivo opcional).
- Marker stdout `<FORGE_INTENT>` documentado em `docs/schemas/intent-protocol.md`.

### Changed (pilot R1)
- README: reconciliação de stats (22 validators + 3 helpers, 30 cards, tests 1863/204/30).
```

- [ ] **Step 4: Handoff**

Em `docs/design/08-session-handoff.md`, atualizar `**Última atualização:**` pra `2026-06-19 (pilot R1 — unblock init AI-first: P-01..P-12 + README drift)` e `**Estado:**` refletindo que o pilot R1 fechou os bloqueadores do init brownfield (intent loop gated + resume real + detecção por-plataforma + dep-closure + gate-pausa + quality baratos). Replicar o pattern de entrada existente (não inventar formato).

- [ ] **Step 5: Verificar consistência**

Run: `.venv/bin/pytest -k "readme or stats or doc" -m "not integration and not e2e"` (não-bloqueante se ausente). Conferir manualmente que nenhuma menção divergente sobrou no README.

- [ ] **Step 6: Commit**

```bash
git add README.md CHANGELOG.md docs/design/08-session-handoff.md
git commit -m "docs(pilot-r1): reconcilia stats do README + CHANGELOG/handoff (doc-sync)

Fonte única (handoff): 22 validators + 3 helpers, 30 cards, tests
1863/204/30. CHANGELOG Unreleased cobre P-01..P-12. Mandamento 6."
```

---

## Self-review checklist (rodar antes de marcar o plano completo)

- [ ] **Spec coverage (report ↔ plano):** P-01 (WS-A-1) · P-11 (WS-A-2) · P-06 (WS-A-3) · P-03 (WS-B-1) · P-09 (WS-B-2) · P-10 (WS-B-3) · P-04 (WS-B-4) · P-02 (WS-C-1) · P-05 (WS-D-1) · P-07 (WS-D-2) · P-08 (WS-D-3) · P-12 (WS-D-4) · README drift (WS-D-5). **13/13 findings cobertos.**
- [ ] **Anti-goals respeitados:** W7.2 NÃO implementado (anotado em 04-pending, WS-C-1 Step 4); sem fixes fora de escopo; sem refactor além do necessário.
- [ ] **TDD:** toda task de comportamento tem teste falhando primeiro → impl → verde.
- [ ] **Files explícitos:** toda task lista paths exatos.
- [ ] **Decisão 27:** cerimônia NÃO necessária (gating aditivo; resume real honra "auto-resumable") — `01-decisions.md` intacto.
- [ ] **Doc-sync:** WS-A-3 + WS-B-1 (card.md) + WS-C-1 (04-pending) + WS-D-5 (README/CHANGELOG/handoff) cobrem a matriz.
- [ ] **Placeholder scan:** sem TBD/FIXME; `...` aparece só em corpo de teste como elipse de fixture-seed (verbatim de código a escrever), não como placeholder do plano.
- [ ] **Type/name consistency:** `_close_provider_deps`, `_resolver_error_gate`, `_drop_unresolvable_cards`, `greeting_stable`, `_resume_option_labels` — grafias consistentes entre tasks.
