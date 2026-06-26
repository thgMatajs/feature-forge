# W-RULES (Fase 1, Onda 5) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development.
> Steps use checkbox (`- [ ]`) syntax.

**Goal:** `forge init` lê os `.claude/rules/*`+`CLAUDE.md` do consumidor, classifica cada fragmento (Tier-0 injetado vs Tier-1 → mem) via um NOVO intent `classify` fulfillado pelo host-LLM, PROPÕE a divisão em 3-caminhos (G1/G2), e ao aprovar move Tier-1 pro mem + enxuga as rules (com `.bak`).

**Architecture:** Constrói o intent-kind `classify` end-to-end (a fundação reutilizável da camada AI-first conductor) + o passo `_reduce_rules` no init que o consome. Decisão 22: engine não classifica (sem LLM em runtime); emite o intent, o host fulfilla. Design refinement: `docs/superpowers/specs/2026-06-26-w-rules-design.md`.

**Tech Stack:** Python 3.13, pytest (`.venv/bin/pytest`), intent protocol (`.claude/forge/state/` pending/response), `mem_call`.

## Global Constraints

- **Decisão 22:** engine NÃO importa/roda LLM. A classificação é trabalho do host via o intent `classify`.
- **G1/G2:** nenhuma rule humana some sem ratificação 3-caminhos; `.bak` (Decisão 24) antes de editar.
- **Fallback honesto (detection-shaped):** em host SEM LLM (TtyAdapter/stdin humano), `classify` NÃO tem como classificar → degrada gracioso (pula a redução com aviso claro), NUNCA trava o init nem inventa classificação.
- **RULE_INDEX:** reusa o que o scaffold do mem (W-VENDOR) já escreveu em `AGENTS.md`; NÃO duplica.
- **Determinismo de teste:** scrub env (CLAUDECODE/OPENCODE_*/CODEX/CURSOR_*) + pin `host: intent-file` via forge-config pra testes do loop classify.
- `.venv/bin/pytest` canônico. Baseline: 10 falhas pré-existentes em `test_claude_rules_system.py` (débito Fase 0) — count não sobe.
- NÃO `git push`/PR. Voz mentor calmo.

---

### Task A: Intent-kind `classify` (infra end-to-end)

**Files:**
- Modify: `engine/host/adapter.py` (`AskKind.CLASSIFY` + método abstrato `classify`)
- Modify: `engine/host/adapters/intent_file.py`, `engine/host/adapters/claude_code.py`, `engine/host/adapters/tty.py` (impl `classify`)
- Modify: `engine/ui/question.py` (entrypoint `classify(...)`)
- Modify: `docs/schemas/intent-protocol.md` (kind `classify` + payload/response shape)
- Test: `tests/unit/test_classify_intent.py` (novo)

**Interfaces:**
- Produces:
  - `AskKind.CLASSIFY = "classify"`.
  - `HostAdapter.classify(*, fragments: list[dict], schema: dict) -> list[dict]` (abstract) — `fragments`: `[{"id","source","heading","text"}]`; retorna a classificação `[{"fragment_id","tier","rationale","mem_note"?}]` (`mem_note` só p/ tier 1: `{type,title,body,tags}`).
  - `question.classify(fragments, *, project_root=None) -> list[dict]` — monta o pending (kind=classify, payload=fragments+schema), levanta `PausedForInputError` (exit 2) na 1ª invocação; na re-invocação parseia a response. Espelha o loop pending/response de `ask_three_paths`.
  - Pending shape (extend `intent-protocol.md`): `{"schema-version", "kind":"classify", "intent-id", "command", "fragments":[...], "classification-schema":{...}}`. Response: `{"intent-id", "classification":[...]}`.

- [ ] **Step 1: Write the failing test (roundtrip via IntentFileAdapter + TTY degrade)**

```python
# tests/unit/test_classify_intent.py
import os, pytest
from pathlib import Path
from engine.ui import question, intent_state
from engine.host.adapter import AskKind, PausedForInputError
from engine.host.adapters.intent_file import IntentFileAdapter
from engine.host.adapters.tty import TtyAdapter

FRAGS = [{"id": "f1", "source": ".claude/rules/x.md", "heading": "## Reuso", "text": "..."}]

def test_classify_kind_exists():
    assert AskKind.CLASSIFY.value == "classify"

def test_classify_pending_then_response_roundtrip(tmp_path, monkeypatch):
    # 1ª invocação: sem response → escreve pending kind=classify + pausa (exit 2).
    for v in ("CLAUDECODE","OPENCODE_BIN","CODEX","CURSOR_TRACE_ID"):
        monkeypatch.delenv(v, raising=False)
    (tmp_path / ".git").mkdir()
    adapter = IntentFileAdapter()
    with pytest.raises(PausedForInputError):
        adapter.classify(fragments=FRAGS, schema={"tiers": [0, 1]}, project_root=tmp_path)
    pending = intent_state.read_pending(tmp_path)
    assert pending["kind"] == "classify"
    assert pending["fragments"] == FRAGS
    # host fulfilla: escreve response com a classificação.
    intent_state.write_response(tmp_path, {
        "intent-id": pending["intent-id"],
        "classification": [{"fragment_id": "f1", "tier": 1, "rationale": "ref",
                            "mem_note": {"type": "reference", "title": "Reuso x",
                                         "body": "...", "tags": ["reuso"]}}],
    })
    # 2ª invocação: consome a response.
    result = adapter.classify(fragments=FRAGS, schema={"tiers": [0, 1]}, project_root=tmp_path)
    assert result[0]["tier"] == 1 and result[0]["fragment_id"] == "f1"

def test_classify_tty_degrades_gracefully(tmp_path):
    # Host sem LLM (TTY): classify não pode classificar → sinaliza indisponível,
    # NÃO trava nem inventa. Contrato: retorna [] (ou levanta ClassifyUnavailable).
    adapter = TtyAdapter()
    result = adapter.classify(fragments=FRAGS, schema={"tiers": [0, 1]}, project_root=tmp_path)
    assert result == []  # _reduce_rules trata [] como "pular redução com aviso"
```

- [ ] **Step 2: Run to verify red**

Run: `.venv/bin/pytest tests/unit/test_classify_intent.py -v`
Expected: FAIL — `AttributeError: CLASSIFY` / `classify` não existe.

- [ ] **Step 3: Add `AskKind.CLASSIFY` + abstract method**

```python
# engine/host/adapter.py
class AskKind(str, Enum):
    ASK = "ask"; ASK_THREE_PATHS = "ask_three_paths"; ASK_MULTI = "ask_multi"
    ASK_TEXT = "ask_text"; CONFIRM = "confirm"; CLASSIFY = "classify"
```
Adicionar ao ABC `HostAdapter`:
```python
    @abstractmethod
    def classify(self, *, fragments: list[dict], schema: dict,
                 project_root: "Path | None" = None) -> list[dict]: ...
```

- [ ] **Step 4: Implement nos 3 adapters**

`IntentFileAdapter.classify`: montar o pending `{schema-version, kind:"classify", intent-id (via stable_intent_id sobre fragments), command, fragments, classification-schema}`; se não há response → `write_pending` + raise `PausedForInputError`; se há → `read_response` + retornar `payload["classification"]`. (Espelha o `ask`/`_pending_response` loop já no arquivo; reusar os helpers de pending/response existentes.)

`ClaudeCodeAdapter.classify`: emitir o marker stdout do pending classify (sem pending file, padrão do adapter) + raise `PausedForInputError`; re-entry via `intent_state.read_response`. Reusar o `_ask_loop`/marker helper existente, estendido pro payload classify.

`TtyAdapter.classify`: sem LLM in-process → retornar `[]` (sinal de "classificação indisponível neste host") + `emit_warn` que a redução será pulada. NUNCA inventar classificação.

- [ ] **Step 5: `question.classify` entrypoint**

```python
# engine/ui/question.py
def classify(fragments: list[dict], *, schema: dict | None = None,
             project_root: Path | None = None) -> list[dict]:
    """Emite o intent classify; host-LLM fulfilla. Retorna a classificação
    estruturada (lista). [] = host sem LLM → caller (init) pula a redução."""
    project_root = project_root if project_root is not None else _project_root_for_io()
    schema = schema or {"tiers": [0, 1]}
    from engine.host.adapter import PausedForInputError as _AdapterPaused
    try:
        return _resolve_adapter(project_root).classify(
            fragments=fragments, schema=schema, project_root=project_root)
    except _AdapterPaused:
        raise  # cli.py mapeia pra exit 2 (host fulfilla + re-invoca)
```

- [ ] **Step 6: `docs/schemas/intent-protocol.md`** — documentar o kind `classify`: payload (fragments + classification-schema) + response (classification[]). Seguir o formato dos kinds existentes.

- [ ] **Step 7: Run green + rapid lane**

Run: `.venv/bin/pytest tests/unit/test_classify_intent.py -v && .venv/bin/pytest -m "not integration and not e2e" -q | tail -1`
Expected: PASS; rapid sem regressão.

- [ ] **Step 8: Commit**

```bash
git add engine/host/adapter.py engine/host/adapters/ engine/ui/question.py docs/schemas/intent-protocol.md tests/unit/test_classify_intent.py
git commit -m "feat(intent): intent-kind classify (host-LLM fulfilla; TTY degrada)"
```

---

### Task B: `_reduce_rules` — passo de redução no init

**Files:**
- Modify: `engine/init.py` (`_reduce_rules` + helper de parse de fragmentos + wire no `_run_pipeline` após `_vendor_mem`)
- Test: `tests/integration/test_init_reduce_rules.py` (novo)

**Interfaces:**
- Consumes: `question.classify`, `question.ask_three_paths`, `mem_call`, `paths` helpers.
- Produces: `init._reduce_rules(project_root) -> bool` (True se reduziu; False se pulou — greenfield/sem-LLM/usuário-pulou).

- [ ] **Step 1: Write the failing test (fixture consumer + classify via intent-file)**

```python
# tests/integration/test_init_reduce_rules.py
# Fixture: projeto com .claude/rules/reuso.md (1 seção Tier-1) + CLAUDE.md (Tier-0).
# Pin host=intent-file + scrub env. Seed a response de classify + a de three_paths(aceitar).
# Asserts: .bak criado; mem add chamado p/ Tier-1 (mem stats / jsonl cresceu);
# .claude/rules/reuso.md virou ponteiro (sem o corpo Tier-1, com 'mem find');
# sentinel .claude/.rules-reduced presente.
# (Greenfield: sem .claude/rules → _reduce_rules retorna False, no-op.)
```
(O implementador escreve o teste completo seguindo o padrão de `tests/integration/test_init_*.py` + a forma de seed de response usada nos testes de intent existentes; cobre: happy-path aceitar, greenfield-skip, sem-LLM-skip (classify→[]), idempotência (sentinel).)

- [ ] **Step 2: Run to verify red** — `AttributeError: _reduce_rules`.

- [ ] **Step 3: Implement `_reduce_rules`**

Lógica:
1. Greenfield guard: se não há `.claude/rules/*.md` nem `CLAUDE.md` reduzível → return False.
2. Idempotência: se sentinel `.claude/.rules-reduced` existe e sem `--force` → return False.
3. Parse fragmentos: por seção (heading `##`/`###`) em cada rule + CLAUDE.md → `[{id, source, heading, text}]`.
4. `classification = question.classify(fragments)`. Se `[]` (host sem LLM) → `emit_warn` "redução de rules pulada (host sem LLM); rode em Claude Code pra assimilar convenções" → return False.
5. Renderizar a proposta + `ask_three_paths("reducao-de-rules", [aceitar, ajustar, pular])`. ajustar → re-loop (humano edita); pular → return False.
6. aceitar → `.bak` de CLAUDE.md + cada rule tocada (Decisão 24); p/ cada Tier-1: `mem_call(project_root, ["add", "--type", t, "-t", title, "--tags", tags, body], json=False)`; remover o fragmento Tier-1 do arquivo-fonte (substituir por ponteiro "detalhe: `mem find '<tema>'`"); enxugar CLAUDE.md p/ Tier-0 + ref ao RULE_INDEX; escrever sentinel.
7. return True.

Wire em `_run_pipeline` após `_vendor_mem(project_root)`.

- [ ] **Step 4: Run green (full + rapid)** — fixture tests pass; rapid sem regressão; integração não sobe além das 10 pré-existentes.

- [ ] **Step 5: Commit**

```bash
git add engine/init.py tests/integration/test_init_reduce_rules.py
git commit -m "feat(init): _reduce_rules — classifica + propõe 3-caminhos + move Tier-1 pro mem"
```

---

### Task C: Driver — instrução de fulfillment do `classify`

**Files:**
- Modify: `skills/feature-forge/SKILL.md` (como o host fulfilla um intent `classify`)
- Modify: `AGENTS.md` (root) + `templates/AGENTS.md.template` (o driver instalado no consumidor)

**Interfaces:** prosa de driver (instrução pro host).

- [ ] **Step 1:** Adicionar uma seção de driver: ao ver um `forge-pending.json` (ou marker) com `kind:"classify"`, o host lê `fragments`, classifica cada um em tier 0 (invariante sempre-on — gates, enforcement, "NUNCA/sempre") vs tier 1 (referência/exemplo/detalhe — recuperável sob demanda), gera `mem_note` p/ os tier-1, e escreve `forge-response.json` com `{intent-id, classification:[...]}`. Voz mentor calmo, instrução acionável.
- [ ] **Step 2:** Espelhar no `templates/AGENTS.md.template` (consumidor recebe a mesma instrução no init).
- [ ] **Step 3: Commit**

```bash
git add skills/feature-forge/SKILL.md AGENTS.md templates/AGENTS.md.template
git commit -m "docs(driver): instrução de fulfillment do intent classify"
```

---

### Task D: Doc-sync + 04-pending

**Files:**
- Modify: `CHANGELOG.md` (Added: intent classify + _reduce_rules no init)
- Modify: `docs/design/06-command-surface.md` (init agora reduz rules)
- Modify: `docs/design/04-pending.md` (gaps: ajustar-loop de three_paths, opencode adapter classify se deferido)
- **NÃO tocar:** históricos/congelados (08-session-handoff, docs/reports, docs/superpowers, outputs)

- [ ] **Step 1:** CHANGELOG `### Added` (voz mentor calmo): intent-kind `classify` (host-LLM fulfilla; TTY degrada gracioso) + `forge init` reduz rules do consumidor (classifica Tier-0/1, propõe 3-caminhos G1/G2, move Tier-1 pro mem com `.bak`).
- [ ] **Step 2:** `06-command-surface.md` — anotar o passo de redução no `forge init`.
- [ ] **Step 3:** `04-pending.md` — gaps conhecidos (ex.: opencode adapter classify; loop de "ajustar" refinado).
- [ ] **Step 4: Commit** (git add PATHS EXPLÍCITOS)

```bash
git add CHANGELOG.md docs/design/06-command-surface.md docs/design/04-pending.md
git commit -m "docs(rules): doc-sync intent classify + _reduce_rules no init"
```
