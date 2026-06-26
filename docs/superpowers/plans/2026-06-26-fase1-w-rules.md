# W-RULES (Fase 1, Onda 5) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development.
> Steps use checkbox (`- [ ]`) syntax.

**Goal:** `forge init` lê os `.claude/rules/*`+`CLAUDE.md` do consumidor, classifica cada fragmento (Tier-0 injetado vs Tier-1 → mem) via um NOVO intent `classify` fulfillado pelo host-LLM, PROPÕE a divisão em 3-caminhos (G1/G2), e ao aprovar move Tier-1 pro mem + enxuga as rules (com `.bak`).

**Architecture (corrigida pós-auditoria r1):** O `HostAdapter` é UNIFICADO (`ask(*, kind, ...)` despacha por kind; não há método por-kind). Mas `classify` tem payload rico (fragments+schema) e retorno estruturado (`list[dict]`), que NÃO cabem no `ask`/`AskResult(value: str|list[str])`. Logo `classify` é um **método novo do adapter** que reusa os **primitivos de baixo nível** do loop DRIFT-1 (`stable_intent_id`, `intent_state.read_response`, `pending_lock`+`detect_race`+`write_pending`, `_resolve_command_context`) — NÃO o `_ask_loop` (que é ask-shaped). Decisão 22: engine não classifica; emite o intent, host fulfilla. Design: `docs/superpowers/specs/2026-06-26-w-rules-design.md`.

**Tech Stack:** Python 3.13, pytest (`.venv/bin/pytest`), intent protocol (`.claude/forge/state/` pending/response), `mem_call`.

## Global Constraints

- **Decisão 22:** engine NÃO roda LLM. Classificação = host via intent `classify`.
- **G1/G2:** `.bak` (Decisão 24) ANTES de qualquer edição; 3-caminhos ANTES de aplicar. Nenhuma rule some sem ratificação.
- **Fallback honesto (H-101):** `classify` retorna `list[dict] | None`. `None` = host SEM LLM (TtyAdapter) → `_reduce_rules` PULA com aviso claro. Lista = classificação real (TODO fragmento recebe tier). NUNCA confundir os dois; NUNCA inventar classificação.
- **Apply ordenado (H-104, lição W-VENDOR M-002):** `.bak` → `mem add` de TODOS os Tier-1 + VERIFICAR cada `MemResult` (found && exit_code==0) → SÓ se todos OK, trim destrutivo dos arquivos-fonte. Add falhou → aborta o trim (dado preservado) + erro claro. `mem_call` é fail-soft (nunca levanta) — checar o resultado é obrigatório.
- **Schema aditivo (H-102):** o kind `classify` é ADITIVO em `intent-protocol.md`; kinds existentes intocados; teste de não-regressão dos kinds atuais.
- **`tier` é int (0|1)** na fronteira engine↔driver↔response (M-201) — consistente em todo lugar.
- **RULE_INDEX:** reusa o do mem em `AGENTS.md` (W-VENDOR); não duplica.
- **Determinismo de teste:** scrub env (CLAUDECODE/OPENCODE_*/CODEX/CURSOR_*) + `host: intent-file`. Adapters constroem com `(*, project_root=...)`; `intent_state.write_response/read_pending` ancoram em `forge_state_dir` (não no tmp_path raiz).
- `.venv/bin/pytest` canônico. Baseline 10 falhas pré-existentes (Fase 0) — count não sobe. NÃO `git push`/PR. Voz mentor calmo.

---

### Task A: Intent-kind `classify` (método novo de adapter, reusa primitivos)

**Files:**
- Modify: `engine/host/adapter.py` (`AskKind.CLASSIFY` + método abstrato `classify`)
- Modify: `engine/host/adapters/intent_file.py`, `engine/host/adapters/claude_code.py`, `engine/host/adapters/tty.py`
- Modify: `engine/ui/question.py` (`classify(...)` entrypoint)
- Modify: `docs/schemas/intent-protocol.md` (kind `classify` ADITIVO)
- Test: `tests/unit/test_classify_intent.py` (novo)

**Interfaces:**
- `AskKind.CLASSIFY = "classify"`.
- `HostAdapter.classify(*, fragments: list[dict], schema: dict) -> list[dict] | None` (abstract). `fragments`: `[{"id","source","heading","text"}]`. Retorno: `list[dict]` `[{"fragment_id","tier":int,"rationale","mem_note"?}]` (`mem_note` só p/ tier 1: `{type,title,body,tags}`), ou `None` (host sem LLM).
- `question.classify(fragments: list[dict], *, schema: dict | None = None, project_root: Path | None = None) -> list[dict] | None`.
- Pending shape (ADITIVO em intent-protocol.md): `{"schema-version","kind":"classify","intent-id","command","command-args","fragments":[...],"classification-schema":{...}}`. Response: `{"intent-id","classification":[...]}`.
- Re-entry: `classify` lê `intent_state.read_response(project_root, intent_id, state_dir)["classification"]`.

- [ ] **Step 1: Write the failing test (API REAL — adapters com project_root no __init__; state em forge_state_dir)**

```python
# tests/unit/test_classify_intent.py
import pytest
from engine.ui import intent_state
from engine.utils.paths import forge_state_dir
from engine.host.adapter import AskKind, PausedForInputError
from engine.host.adapters.intent_file import IntentFileAdapter
from engine.host.adapters.tty import TtyAdapter

FRAGS = [{"id": "f1", "source": ".claude/rules/x.md", "heading": "## Reuso", "text": "consulte o graph antes"}]
SCHEMA = {"tiers": [0, 1]}

def _scrub(monkeypatch):
    for v in ("CLAUDECODE", "OPENCODE_BIN", "CODEX", "CURSOR_TRACE_ID"):
        monkeypatch.delenv(v, raising=False)

def test_classify_kind_exists():
    assert AskKind.CLASSIFY.value == "classify"

def test_classify_pending_then_response_roundtrip(tmp_path, monkeypatch):
    _scrub(monkeypatch)
    (tmp_path / ".git").mkdir()
    adapter = IntentFileAdapter(project_root=tmp_path)
    # 1ª invocação: sem response → escreve pending classify + pausa (exit 2).
    with pytest.raises(PausedForInputError):
        adapter.classify(fragments=FRAGS, schema=SCHEMA)
    pending = intent_state.read_pending(tmp_path)
    assert pending["kind"] == "classify"
    assert pending["fragments"] == FRAGS
    iid = pending["intent-id"]
    # host fulfilla: escreve response (em forge_state_dir, ancorado por intent_state).
    intent_state.write_response(tmp_path, {
        "intent-id": iid,
        "classification": [{"fragment_id": "f1", "tier": 1, "rationale": "ref",
                            "mem_note": {"type": "reference", "title": "Reuso x",
                                         "body": "consulte o graph antes", "tags": ["reuso"]}}],
    })
    # 2ª invocação (mesmos fragments → mesmo intent-id): consome a response.
    result = adapter.classify(fragments=FRAGS, schema=SCHEMA)
    assert result is not None and result[0]["tier"] == 1 and result[0]["fragment_id"] == "f1"

def test_classify_tty_returns_none(tmp_path):
    # Host sem LLM (TTY) → None (distinto de lista vazia). _reduce_rules pula com aviso.
    adapter = TtyAdapter(project_root=tmp_path)
    assert adapter.classify(fragments=FRAGS, schema=SCHEMA) is None

def test_existing_ask_kinds_unchanged():
    # H-102: extensão aditiva — os kinds existentes seguem.
    assert {k.value for k in AskKind} >= {"ask", "ask_multi", "ask_text", "ask_three_paths", "confirm", "classify"}
```

- [ ] **Step 2: Run to verify red**

Run: `.venv/bin/pytest tests/unit/test_classify_intent.py -v`
Expected: FAIL — `AttributeError`/`AskKind.CLASSIFY` inexistente / `classify` não é método.

- [ ] **Step 3: `AskKind.CLASSIFY` + método abstrato**

```python
# engine/host/adapter.py — no enum:
    CLASSIFY = "classify"
# no ABC HostAdapter:
    @abstractmethod
    def classify(self, *, fragments: list[dict], schema: dict) -> list[dict] | None: ...
```

- [ ] **Step 4: `IntentFileAdapter.classify` (reusa primitivos do loop, NÃO `_ask_loop`)**

Espelha a MECÂNICA de `_ask_loop` (ler o arquivo pra a forma exata), mas com payload classify:
```python
def classify(self, *, fragments, schema):
    command, command_args = self._resolve_command_context()
    intent_id = stable_intent_id(
        kind=AskKind.CLASSIFY.value, question_text="classify-rules",
        options={}, extra={"fragments": fragments, "schema": schema},
        command=command, command_args=command_args)
    existing = intent_state.read_response(self.project_root, intent_id, state_dir=self._state_dir)
    if existing is not None:
        if existing.get("cancelled"): raise UserCancelledError(...)
        if existing.get("paused"): raise UserPausedError(...)
        return existing.get("classification")
    intent = {  # forma kebab-case + schema-version, espelhando _build_pending
        "schema-version": <a mesma const usada por _build_pending>,
        "kind": "classify", "intent-id": intent_id,
        "command": command, "command-args": command_args,
        "fragments": fragments, "classification-schema": schema}
    with intent_state.pending_lock(self.project_root, state_dir=self._state_dir):
        intent_state.detect_race(self.project_root, new_intent_id=intent_id, state_dir=self._state_dir)
        intent_state.write_pending(intent, self.project_root, state_dir=self._state_dir)
    raise PausedForInputError(f"forge paused awaiting classify (intent-id={intent_id})")
```
(Confirmar a const de schema-version e a forma exata de `_build_pending` lendo intent_file.py; reusar o mesmo `schema-version` pra o guard de `read_pending`/`detect_race` não rejeitar.)

- [ ] **Step 5: `ClaudeCodeAdapter.classify`**

Mesma estrutura (intent_id + read_response re-entry). No first-entry: CC NÃO escreve pending por default (marker stdout). Como `fragments` é payload grande, classify ESCREVE o pending (fragments) E emite o marker apontando pra ele — reusar o helper de marker/pending do adapter (ler claude_code.py pra a forma do marker). re-entry idêntico (read_response). Raise PausedForInputError.

- [ ] **Step 6: `TtyAdapter.classify` → None + warn**

```python
def classify(self, *, fragments, schema):
    self.emit_warn(message="redução de rules pulada: host TTY não tem LLM pra classificar")
    return None
```

- [ ] **Step 7: `question.classify` entrypoint**

```python
def classify(fragments, *, schema=None, project_root=None):
    project_root = project_root if project_root is not None else _project_root_for_io()
    schema = schema or {"tiers": [0, 1]}
    from engine.host.adapter import PausedForInputError as _AdapterPaused
    try:
        return _resolve_adapter(project_root).classify(fragments=fragments, schema=schema)
    except _AdapterPaused:
        raise  # cli.py → exit 2; host fulfilla + re-invoca
```

- [ ] **Step 8: `docs/schemas/intent-protocol.md`** — documentar o kind `classify` ADITIVO (payload fragments + classification-schema; response classification[]). Nota explícita: kinds existentes intocados.

- [ ] **Step 9: Run green + rapid**

Run: `.venv/bin/pytest tests/unit/test_classify_intent.py -v && .venv/bin/pytest -m "not integration and not e2e" -q | tail -1`
Expected: PASS; rapid sem regressão (os kinds existentes seguem — `test_existing_ask_kinds_unchanged` + a suíte de question/adapters verde).

- [ ] **Step 10: Commit**

```bash
git add engine/host/adapter.py engine/host/adapters/ engine/ui/question.py docs/schemas/intent-protocol.md tests/unit/test_classify_intent.py
git commit -m "feat(intent): intent-kind classify (método novo de adapter; TTY→None; aditivo)"
```

---

### Task B: `_reduce_rules` — passo de redução no init

**Files:**
- Modify: `engine/init.py` (`_reduce_rules` + parse de fragmentos + wire)
- Test: `tests/integration/test_init_reduce_rules.py` (novo)

**Interfaces:**
- Consumes: `question.classify`, `question.ask_three_paths`, `mem_call`, `paths`.
- Produces: `init._reduce_rules(project_root) -> bool` (True reduziu; False pulou).

**WIRE (H-105) — crítico:** `_reduce_rules` introduz um PONTO DE PAUSA (exit 2 via classify) no init. NÃO colocar dentro do try/except de `_vendor_mem`/hooks (que engole OSError/ValueError). Colocar onde `PausedForInputError` PROPAGA até cli.py (init já é resumível — `_InitCheckpoint`, init.py:~100). Ler `_run_pipeline` + o padrão de pausa de `plan.py`/`qa` pra posicionar: após o vendoring, como passo próprio, com a exceção borbulhando (sem captura local).

- [ ] **Step 1: Write the failing test (fixture + classify+three_paths via intent-file)**

```python
# tests/integration/test_init_reduce_rules.py
import pytest
from pathlib import Path
from engine import init
from engine.ui import intent_state

def _consumer(tmp_path):
    (tmp_path / ".git").mkdir()
    rules = tmp_path / ".claude" / "rules"; rules.mkdir(parents=True)
    (rules / "reuso.md").write_text("## Reuso\nConsulte o graph antes de criar helper.\n")
    (tmp_path / "CLAUDE.md").write_text("# Projeto\n## Gate\nNUNCA commitar sem teste.\n")
    return tmp_path

def test_reduce_rules_greenfield_skips(tmp_path):
    (tmp_path / ".git").mkdir()
    assert init._reduce_rules(tmp_path) is False  # sem rules → no-op

def test_reduce_rules_no_llm_skips(tmp_path, monkeypatch):
    # host TTY/sem-LLM → classify None → pula com aviso, não trava.
    c = _consumer(tmp_path)
    monkeypatch.setattr("engine.init.question.classify", lambda *a, **k: None)
    assert init._reduce_rules(c) is False
    assert not (c / ".claude" / ".rules-reduced").exists()

def test_reduce_rules_accept_moves_tier1_to_mem_with_bak(tmp_path, monkeypatch):
    c = _consumer(tmp_path)
    # classify: a seção Reuso é Tier-1; o Gate é Tier-0.
    monkeypatch.setattr("engine.init.question.classify", lambda *a, **k: [
        {"fragment_id": "reuso.md::Reuso", "tier": 1, "rationale": "ref",
         "mem_note": {"type": "reference", "title": "Reuso", "body": "Consulte o graph antes de criar helper.", "tags": ["reuso"]}},
        {"fragment_id": "CLAUDE.md::Gate", "tier": 0, "rationale": "invariante"}])
    monkeypatch.setattr("engine.init.question.ask_three_paths", lambda *a, **k: "a")  # aceitar
    calls = []
    monkeypatch.setattr("engine.init.mem_call", lambda pr, args, **k: calls.append(args) or _ok())
    assert init._reduce_rules(c) is True
    assert any(a[0] == "add" for a in calls)                       # mem add chamado
    assert (c / ".claude" / "rules" / "reuso.md.bak").exists()     # .bak (Decisão 24)
    assert "mem find" in (c / ".claude" / "rules" / "reuso.md").read_text()  # virou ponteiro
    assert (c / ".claude" / ".rules-reduced").exists()             # sentinel

def test_reduce_rules_aborts_trim_when_mem_add_fails(tmp_path, monkeypatch):
    # H-104: se algum mem add falha, NÃO faz o trim destrutivo (dado preservado).
    c = _consumer(tmp_path)
    monkeypatch.setattr("engine.init.question.classify", lambda *a, **k: [
        {"fragment_id": "reuso.md::Reuso", "tier": 1, "rationale": "ref",
         "mem_note": {"type": "reference", "title": "Reuso", "body": "...", "tags": ["reuso"]}}])
    monkeypatch.setattr("engine.init.question.ask_three_paths", lambda *a, **k: "a")
    monkeypatch.setattr("engine.init.mem_call", lambda pr, args, **k: _fail())  # add falha
    with pytest.raises(Exception):
        init._reduce_rules(c)
    assert "Consulte o graph" in (c / ".claude" / "rules" / "reuso.md").read_text()  # corpo PRESERVADO
```
(`_ok()`/`_fail()`: helpers que retornam `MemResult(found=True, exit_code=0/1, ...)`. O implementador importa `MemResult` real e ajusta a forma do `fragment_id` ao parser de seção que implementar.)

- [ ] **Step 2: Run to verify red** — `AttributeError: _reduce_rules`.

- [ ] **Step 3a: parse de fragmentos** — helper que lê `.claude/rules/*.md` + `CLAUDE.md`, fatia por heading (`##`/`###`), retorna `[{id: "<file>::<heading-slug>", source, heading, text}]`.
- [ ] **Step 3b: guards** — greenfield (sem rules/CLAUDE.md reduzível) → False; sentinel `.claude/.rules-reduced` presente (sem `--force`) → False.
- [ ] **Step 3c: classify** — `c = question.classify(fragments)`. `c is None` → `emit_warn` (host sem LLM) + return False. Validar que TODO fragmento recebeu tier (senão erro claro).
- [ ] **Step 3d: proposta 3-caminhos** — `ask_three_paths("reducao-de-rules", [aceitar, ajustar, pular])`. `pular` → False. `ajustar` → re-emite o classify pedindo revisão (M-202: o caminho "ajustar" re-dispara o intent classify com uma flag `revise=True` + o split atual no payload; host devolve split ajustado; volta ao 3-caminhos). `aceitar` → 3e.
- [ ] **Step 3e: aplicar (ordem H-104)** — (1) `.bak` de CLAUDE.md + cada rule tocada; (2) p/ CADA Tier-1: `res = mem_call(pr, ["add","--type",t,"-t",title,"--tags",tags,body], json=False)`; coletar `res`; se QUALQUER `not (res.found and res.exit_code==0)` → abortar ANTES de qualquer trim, levantar erro claro (dado preservado); (3) só com todos OK: remover os fragmentos Tier-1 dos arquivos-fonte (substituir por ponteiro "detalhe: `mem find '<tema>'`"), enxugar CLAUDE.md p/ Tier-0 + ref ao RULE_INDEX, escrever sentinel.
- [ ] **Step 3f: wire** — inserir `_reduce_rules(project_root)` no pipeline do init APÓS o vendoring, FORA de qualquer try/except que engula, com `PausedForInputError` propagando (ver WIRE acima).

- [ ] **Step 4: Run green** — os 4 testes passam; rapid sem regressão; integração não sobe além de 10.

- [ ] **Step 5: Commit**

```bash
git add engine/init.py tests/integration/test_init_reduce_rules.py
git commit -m "feat(init): _reduce_rules — classify + 3-caminhos + move Tier-1 pro mem (.bak, apply ordenado)"
```

---

### Task C: Driver — fulfillment do `classify`

**Files:**
- Modify: `skills/feature-forge/SKILL.md`, `AGENTS.md`, `templates/AGENTS.md.template`

- [ ] **Step 1:** Seção de driver: ao ver pending/marker `kind:"classify"`, o host lê `fragments`, classifica cada um em `tier:0` (invariante sempre-on: gates, enforcement, "NUNCA/sempre") vs `tier:1` (referência/exemplo/detalhe recuperável), gera `mem_note` p/ os tier-1, escreve `forge-response.json` `{intent-id, classification:[{fragment_id,tier,rationale,mem_note?}]}`. `tier` é INT. Voz mentor calmo.
- [ ] **Step 2:** Espelhar em `templates/AGENTS.md.template` (consumidor recebe no init).
- [ ] **Step 3: Commit** — `docs(driver): fulfillment do intent classify`

---

### Task D: Doc-sync + 04-pending

**Files:**
- Modify: `CHANGELOG.md`, `docs/design/06-command-surface.md`, `docs/design/04-pending.md`
- **NÃO tocar:** históricos/congelados.

- [ ] **Step 1:** CHANGELOG `### Added` (voz mentor calmo): intent-kind `classify` (host-LLM fulfilla; TTY→None degrada) + `forge init` reduz rules (classifica Tier-0/1, 3-caminhos G1/G2, move Tier-1 pro mem com `.bak`, apply ordenado).
- [ ] **Step 2:** `06-command-surface.md` — passo de redução no `forge init`.
- [ ] **Step 3:** `04-pending.md` — gaps: opencode adapter `classify` (se não coberto); refino do loop "ajustar"; classify em hosts adicionais.
- [ ] **Step 4: Commit** (git add PATHS EXPLÍCITOS) — `docs(rules): doc-sync intent classify + _reduce_rules`
