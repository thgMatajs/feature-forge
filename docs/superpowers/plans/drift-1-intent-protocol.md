# PLAN — DRIFT-1: Intent Protocol (Engine intent-only + file-based resume)

**Spec:** `docs/superpowers/specs/drift-1-intent-protocol.md`
**Status:** draft (locked design contract; awaiting plan-auditor)
**Phase tag:** Phase A — DRIFT-1
**Branch alvo:** `feat/drift-1-intent-protocol`
**Created:** 2026-06-10

## Goal

Implementar end-to-end o protocolo intent-only + tty_bridge fallback +
`bin/forge` dispatcher migration descrito no spec, em 6 waves
sequenciais, sem regressão dos 1125 tests baseline (pós-Phase 0b).

## Architecture sketch

```
┌────────────────────────────────────────────────────────────────┐
│ bin/forge (Bash dispatcher)                                    │
│   if CLAUDECODE || !tty:                                       │
│       exec python -m engine.cli "$@"          ── intent mode   │
│   else:                                                        │
│       exec python -m engine.ui.tty_bridge engine.cli "$@"      │
│                                               ── fallback TTY  │
└────────────────────────────────────────────────────────────────┘
       │                                       │
       │ subprocess (intent mode)              │ subprocess (loop mode)
       ▼                                       ▼
┌─────────────────────────────┐    ┌─────────────────────────────┐
│ engine/cli.py::main()       │    │ engine/ui/tty_bridge.py     │
│   - dispatcha subcommand    │    │   - subprocess loop         │
│   - captura                 │    │   - lê pending.json         │
│     PausedForInputError ──▶ │    │   - prompts stdin           │
│   - exit code 0/1/2/130     │    │   - escreve response.json   │
└─────────────────────────────┘    └─────────────────────────────┘
       │                                       ▲
       │ chama (mantém API)                    │ exec
       ▼                                       │
┌─────────────────────────────┐                │
│ engine/ui/question.py       │                │
│   - lê response.json?       │                │
│     - sim+match → consome   │                │
│     - não → escreve         │                │
│       pending.json + raise  │                │
│       PausedForInputError ──┴────────────────┘
│   - API surface intacta:                                       │
│     ask / ask_text / ask_multi / confirm / ask_three_paths     │
└─────────────────────────────┘
```

### Módulos novos

| Módulo | Linhas approx | Responsabilidade |
|---|---|---|
| `engine/ui/tty_bridge.py` | ~120 | Subprocess loop + stdin prompts pra fallback TTY |
| `engine/ui/intent_state.py` | ~140 | Read/write/delete `.claude/state/forge-pending.json` + `forge-response.json`; intent-id matching; race detection |
| `engine/utils/json_io.py` | ~50 | Atomic JSON write (helper compartilhado — análogo a `yaml_io.write_yaml`) |
| `docs/schemas/intent-protocol.md` | ~80 | Schema canônico dos dois arquivos JSON |

### Módulos modificados

| Módulo | Tipo de mudança |
|---|---|
| `engine/ui/question.py` | Refactor interno (API surface preservada): remove `_read_line` stdin path; adiciona `_check_response` + `_emit_pending`; adiciona `PausedForInputError`; mantém `PromptAbortedError`, `NonInteractiveError`, `_PAUSE_TOKENS` |
| `engine/cli.py::main()` | Captura `PausedForInputError` → exit 2 |
| `bin/forge` | Detection logic (env var + TTY check) |

## Reuse-first evidence

Antes de criar helpers novos, evidence de consulta a infra existente:

### Checkpoint pattern (precedente em `engine/init.py`)

```bash
grep -n "_save_checkpoint\|_load_checkpoint\|_clear_checkpoint\|checkpoint" engine/init.py
```

Resultado (verificado em pré-flight): 71 matches em `init.py`, incluindo
`_InitCheckpoint` dataclass (linha 104), `_save_checkpoint` (linha 120),
`_load_checkpoint` (linha 138), `_clear_checkpoint` (linha 145), helper
`_checkpoint_path` (linha 116).

Auditado também `engine/qa/checkpoint.py` (módulo compartilhado de QA):
`Checkpoint` dataclass linhas 31-56, `write_checkpoint` linhas 82-138,
`read_checkpoint` linhas 141-222, `find_resumable_run` linhas 225-285.

**W2.T0 outcome (locked): C — justificar incompatibilidade.** `Checkpoint`
em `engine/qa/checkpoint.py` é semanticamente atado a QA: o dataclass
exige `scope_type` (linha 52, valores canônicos `feature|screen|task|paranoid`
documentados linha 43), `scope_target` (linha 53, sanitizado via
`engine.qa.ingest.sanitize_scope_target` linhas 28/253), e
`last_phase_completed` (linha 54) com range hard-validado `0..5` (linha 200)
representando as 5 phases canônicas do pipeline QA (linhas 35-39 docstring).
Além disso, `find_resumable_run` (linha 225) ancora a busca em
`.planning/qa/<scope_target>/<run_id>/qa-report.json` com sentinela
`verdict == "pending"` (linhas 257, 267, 278) — diretório e contrato de
arquivo que DRIFT-1 não compartilha. DRIFT-1 precisa de `intent_id`,
`kind` (ask/ask_text/ask_multi/confirm/ask_three_paths), `pending_state`,
timestamp — zero overlap com phase-ordinals QA ou scope-types QA.

Outcome B (extract base shared) também foi avaliado e rejeitado: a única
superfície genuinamente genérica (atomic JSON write + timestamp ISO 8601 Z)
já é coberta pelos módulos que W1 entrega — `engine/utils/json_io.py`
(W1.T2) + `engine/ui/intent_state.py` (W1.T3). Não há resíduo
generalizável depois desses dois landed; promover campos QA-específicos
pra base inverteria a dependência (engine root passaria a importar
conceitos QA), violando o layering atual.

Caminho efetivo (consequência do outcome C): cada subcommand DRIFT-1
mantém dataclass dedicada análoga a `_InitCheckpoint` (linhas 100-108
de `engine/init.py`) com campos próprios (`step`, `at`, `project_root`
+ campos por-comando). Promoção pra `engine.utils.checkpoint` fica como
follow-up gap se ≥3 subcommands materializarem o mesmo shape após a
entrega real de W2.T3b.

### Atomic write

```bash
grep -n "atomic" engine/utils/yaml_io.py
```

`engine.utils.yaml_io.write_yaml(... atomic=True)` já existe.
**Caminho escolhido:** criar `engine/utils/json_io.py` com mesma
estratégia (tempfile + rename) — atomicidade é requisito do contrato
(escritor não pode deixar arquivo parcial). Justificativa pra criar e
não promover: JSON e YAML são serializers distintos; abstrair "atomic
serialize" sobre ambos é over-engineering pré-mature. Decisão revisitável
se aparecer 3º serializer.

### Renderer + persona pra tty_bridge

```bash
grep -n "^def \|^PHRASES_" engine/persona/mentor_calmo.py
grep -n "^def " engine/ui/renderer.py
```

Renderer (`box`, `divider`, `colored`, `write`, `section_header`) e
persona (`PHRASES_*`, `three_paths_block`, `acknowledgment`, `pause_message`)
já modulares. **Caminho escolhido:** `tty_bridge.py` importa direto, zero
refactor.

### Path utilities

```bash
grep -n "claude_dir\|state_dir" engine/utils/paths.py
```

`engine.utils.paths.claude_dir(project_root)` retorna `.claude/`. **Não
existe** `state_dir()` ainda — criar inline em `intent_state.py` como
`_state_path(project_root) = claude_dir(project_root) / "state"`.
Promoção pra `engine.utils.paths.state_dir()` fica como follow-up se
≥2 outros consumidores aparecerem.

### Callsite audit (preservação da API surface)

```bash
grep -rn "question\.\(ask\|confirm\|ask_text\|ask_multi\|ask_three_paths\)\|from engine\.ui\.question\|from engine\.ui import question" engine/
```

Resultado pré-flight: 108 matches em 10 módulos (`plan.py`, `evolve.py`,
`reconfigure.py`, `memory_cli.py`, `graph_cli.py`, `undo.py`,
`implement.py`, `verify.py`, `init.py`, `doctor.py`). **Caminho
escolhido:** API surface preservada — nenhum callsite editado.

## Wave breakdown

Total: 6 waves. Cada wave commit atômico. TDD shape obrigatório (failing
test FIRST, então impl).

---

### W1 — Schema + intent_state foundation

**Goal:** Schema JSON canônico + helpers de I/O + race detection,
ZERO touch em `question.py`.

#### Task W1.T1 — `docs/schemas/intent-protocol.md`

- **Files:** `docs/schemas/intent-protocol.md` (NOVO)
- **Justificativa load-bearing:** `docs/schemas/` é load-bearing
  (`.claude/rules/scope.md` whitelist). Justificado porque o spec
  declara JSON schema canônico — schema sem doc oficial vira drift.
  Mandamento #6 (doc-sync) exige.
- **Steps:**
  1. Esqueleto Markdown com seções: "Pending file", "Response file",
     "Lifecycle", "Examples per kind", "Exit code contract"
  2. Reusa exemplos do SPEC §2.1 + §2.2 verbatim
  3. Linka spec + 04-pending DRIFT-1
- **Critério:** arquivo existe, lint markdown passa
- **Anti-padrões:** NÃO inventar campos que o spec não declara

#### Task W1.T2 — `engine/utils/json_io.py` + tests

- **Files:** `engine/utils/json_io.py` (NOVO), `tests/utils/test_json_io.py` (NOVO)
- **Justificativa:** chokepoint atomic JSON write reusado por
  `intent_state.py`. Reuse-first: `yaml_io.write_yaml(atomic=True)`
  já existe; JSON precisa equivalente.
- **Steps:**
  1. **RED:** `tests/utils/test_json_io.py` — testa `write_json` atomic
     (tempfile + rename, garantia de no-partial); `read_json_or_default`;
     `delete_if_exists`. Rodar `pytest tests/utils/test_json_io.py` → FAIL
     porque módulo não existe.
  2. **GREEN:** implementa minimal pra passar. Rodar pytest → PASS.
  3. Rodar `pytest tests/utils/` → PASS no full module.
- **Critério:** `pytest tests/utils/test_json_io.py -xvs` verde

#### Task W1.T3 — `engine/ui/intent_state.py` + tests

- **Files:** `engine/ui/intent_state.py` (NOVO), `tests/ui/test_intent_state.py` (NOVO)
- **Justificativa:** chokepoint state I/O. Mantém `engine/ui/question.py`
  fininho (sentinel + dispatch só).
- **Steps:**
  1. **RED:** `tests/ui/test_intent_state.py` cobre:
     - `write_pending(intent_dict, project_root)` cria
       `.claude/state/forge-pending.json` com schema correto + atomic
     - `read_response(project_root, intent_id)` retorna dict se match,
       `None` se ausente, raise `IntentMismatchError` se intent-id diverge
     - `clear_intent_files(project_root)` deleta ambos se existirem
     - `detect_race(project_root, new_intent_id)` retorna `None` se
       caminho livre, raise `RaceDetectedError` se pending recente
       (≤10min) com outro intent-id, deleta stale se >10min
  2. **GREEN:** implementa minimal pra passar
  3. Rodar `pytest tests/ui/test_intent_state.py` → PASS
- **Critério:** todos os 4 helpers + exception classes testados verde
- **Anti-padrões:** NÃO referenciar `question.py` ainda (W1 é foundation
  pure)

#### Task W1.T4 — Verification W1

- **Files:** (nenhum write)
- **Steps:**
  1. `pytest tests/utils/test_json_io.py tests/ui/test_intent_state.py -xvs`
     → PASS
  2. `pytest` (full suite) → PASS, count ≥ 1125 + novos tests
  3. `forge verify` → PASS (cascade limpa)
- **Critério:** baseline preservado + 2 novos test files verdes

**Commit W1:** `feat(intent): json_io + intent_state foundation + schema doc`

---

### W2 — Refactor `engine/ui/question.py` (chokepoint)

**Goal:** `question.py` deixa de ler stdin. Emite intent + raise sentinel.
API surface preservada bit-a-bit.

#### Task W2.T0 — Analyze existing checkpoint infrastructure (Mandamento #3 — Reuse-first)

- **Files (read-only nesta task):** `engine/qa/checkpoint.py`,
  `engine/init.py` (`_save_checkpoint`/`_load_checkpoint`/`_clear_checkpoint`
  region linhas 104-152), `engine/plan.py` (se houver checkpoint pattern).
- **Justificativa (Mandamento #3 — Reuse-first):** SPEC §Reuse-first
  evidence cita `engine/init.py:104-152` como precedente, MAS existe
  também `engine/qa/checkpoint.py` com infra compartilhada
  (`Checkpoint` dataclass + `find_resumable_run`). Antes de W2.T3
  decidir "cada subcommand mantém dataclass próprio" (linhas 82-85
  deste plano), é mandatório avaliar reuso da infra de `qa/checkpoint`
  — Reuse-first é mandamento, não sugestão.
- **Steps (decision-task; nenhum write em código nesta task):**
  1. `grep -n "class \|^def \|@dataclass" engine/qa/checkpoint.py` —
     mapeia API exportada (`Checkpoint`, `find_resumable_run`, helpers
     de persistência).
  2. Ler o módulo inteiro pra entender shape: fields da dataclass,
     contrato de `find_resumable_run`, formato de persistência (JSON?
     YAML?), invariantes.
  3. Comparar contra shape esperado pra DRIFT-1 (intent-resume per
     subcommand: `intent_id`, `kind`, `pending_state`, timestamp).
  4. Decidir qual dos 3 outcomes aplica:
     - **A. Reuse direto** — se `Checkpoint` é genérica o suficiente
       (sem fields QA-específicos como chaos rounds / attack vectors),
       importar `engine.qa.checkpoint` em cada subcommand DRIFT-1 sem
       mudança.
     - **B. Extrair base shared** — se `qa/checkpoint` tem fields
       QA-específicos mas o pattern é generalizável, refactor pra
       `engine/_checkpoint.py` (base) + `engine/qa/checkpoint.py`
       (subclass com fields QA). DRIFT-1 usa base. Essa promoção
       supera a justificativa atual em §Reuse-first evidence (linhas
       82-85) de "cada subcommand mantém dataclass próprio".
     - **C. Justificar incompatibilidade** — se `qa/checkpoint` é
       semanticamente tied a QA (não generalizável sem deformar shape),
       documentar no §Architecture deste plano por que NÃO reusar; só
       nesse caso, prosseguir com dataclass dedicada per subcommand
       (status quo do §Reuse-first evidence).
  5. Patch ao §Architecture do plano (ou bloco "Reuse-first evidence")
     declarando o outcome escolhido + 1-parágrafo de justificativa
     concreta apontando linhas-âncora de `qa/checkpoint.py` que
     fundamentam a decisão.
- **Critério de sucesso:**
  - Outcome (A | B | C) escolhido e documentado no plano antes de
    W2.T3 começar.
  - Se B: `engine/_checkpoint.py` entra como módulo adicional na lista
    de "Módulos novos" do §Architecture (linhas 51-58).
  - Se A: lista de subcommands que vão importar `qa.checkpoint` é
    explícita no plano.
  - Se C: justificativa textual referencia campo(s) específico(s) de
    `Checkpoint` que tornam reuso impossível.
- **Anti-padrões:**
  - NÃO ignorar `engine/qa/checkpoint.py` repetindo a justificativa
    atual sem analisar — H-001 da rodada r1 do plan-auditor exige
    análise concreta deste módulo.
  - NÃO modificar `engine/qa/checkpoint.py` nesta task (read-only).
  - NÃO prosseguir pra W2.T3 sem outcome locked.

**Dependency:** W2.T3 (audit multi-subcommand) PRECISA do outcome desta
task antes de iniciar — a forma de T3 depende do path A/B/C escolhido.

#### Task W2.T1 — `PausedForInputError` + check-response-first contract

- **Files:** `engine/ui/question.py` (MODIFY), `tests/ui/test_question_intent.py` (NOVO)
- **Justificativa load-bearing:** `engine/ui/question.py` é chokepoint
  crítico — 108 callsites dependem da API (contagem reconciliada por
  LO-003 do W2 review via canonical grep). Justificativa: refactor
  interno preservando API surface; alinhado ao Mandamento #1 (sem
  silent drift entre intent docstring e impl). Driver é o spec DRIFT-1.
- **Steps:**
  1. **RED:** `tests/ui/test_question_intent.py` cobre:
     - `ask("Q?", {"a":"A"})` SEM response existente → escreve
       `.claude/state/forge-pending.json` schema-correto + raise
       `PausedForInputError`
     - `ask("Q?", {"a":"A"})` COM response existente intent-id matching
       → retorna valor, deleta ambos arquivos
     - Mesma cobertura pra `ask_text`, `ask_multi`, `confirm`,
       `ask_three_paths`
     - `_PAUSE_TOKENS` continuam reconhecidos via response
       `{"paused": true}` → raise `PromptAbortedError` (semantic
       preservada)
     - `allow_pause=False` + response `{"paused": true}` → raise
       `ValueError` (semantic preservada; pause não permitido)
  2. **GREEN:** implementa via:
     - Importa `from engine.ui import intent_state`
     - Cada função `ask*` agora segue padrão:
       ```
       response = intent_state.read_response(project_root, intent_id=None)
       if response and matches_kind:
           return process(response)
       intent_state.detect_race(...)
       intent_state.write_pending({...})
       raise PausedForInputError(intent={...})
       ```
     - `_read_line` REMOVIDO (movido pra `tty_bridge.py` em W3)
     - Renderização do prompt fica no `tty_bridge` — em modo intent-only,
       `renderer.write(question)` fica suprimida (ou: a question vai
       só no JSON; engine não imprime stdout pra evitar ruído)
  3. Rodar testes existentes `pytest tests/ui/test_question*.py` →
     espera-se RED inicial (testes antigos podem usar `monkeypatch.setattr(sys, 'stdin', ...)` que não vai funcionar mais)
  4. Migrar/marcar testes legacy: aqueles que dependiam de stdin
     monkeypatch ganham marker `pytest.mark.skip(reason="legacy stdin
     path migrated to tty_bridge — see test_tty_bridge.py em W3")`
     OU são adaptados pra usar `intent_state` directly.
- **Critério:**
  - `pytest tests/ui/test_question_intent.py -xvs` → PASS
  - `pytest tests/ui/` → PASS (legacy skipados ou adaptados)
  - `inspect.signature(question.ask)` etc. inalteradas — assertion em
    novo `tests/ui/test_question_api_signatures.py`
- **Anti-padrões:**
  - NÃO mudar assinaturas de `ask`, `ask_text`, `ask_multi`, `confirm`,
    `ask_three_paths`
  - NÃO tocar nos 10 callsite modules
  - NÃO importar `engine.cli` (circular)

#### Task W2.T2 — `engine/cli.py::main()` captura sentinel

- **Files (test, novo):** `tests/engine/test_cli_exit_codes.py` (NEW;
  extend existing `tests/cli/test_cli_exit_codes.py` se já existir —
  T3a confirma).
- **Files (impl, modify):** `engine/cli.py` (MODIFY).
- **Justificativa load-bearing:** `engine/cli.py` é top-level handler.
  Mudança escopada: novo `except PausedForInputError` ramo, exit 2.
- **Steps (TDD shape rigoroso — Mandamento #2):**
  1. **RED — write failing test FIRST:**
     `tests/engine/test_cli_exit_codes.py::test_sentinel_exception_maps_to_exit_2`.
     Assert: `cli.main(["init"])` quando handler raise
     `PausedForInputError` retorna exit code 2. Estrutura sugerida:
     monkeypatch `engine.init.run` pra raise `PausedForInputError`,
     invoca `cli.main(["init"])`, assert return value == 2.
  2. **Confirma RED:** rodar
     `pytest tests/engine/test_cli_exit_codes.py::test_sentinel_exception_maps_to_exit_2 -xvs`
     → confirmar FAIL (porque ou `PausedForInputError` ainda não existe
     OU `cli.main` ainda não captura). Documenta o motivo do FAIL no
     output do plan execution.
  3. **GREEN:** implementa em duas frentes:
     - Garante `from engine.ui.question import PausedForInputError`
       no topo de `engine/cli.py` (W2.T1 já definiu o sentinel).
     - Adiciona `except PausedForInputError: return 2` em
       `engine/cli.py::main()` (linha 153-160 region, paralelo ao
       `KeyboardInterrupt`).
  4. **Confirma GREEN:** re-rodar
     `pytest tests/engine/test_cli_exit_codes.py::test_sentinel_exception_maps_to_exit_2 -xvs`
     → confirmar PASS.
  5. **Regressão:** rodar `pytest tests/engine/` → confirmar baseline
     intacto (zero teste novo quebrado, zero teste antigo regredido).
  6. Mensagem mentor-calmo em stderr quando aplicável (opcional;
     pode ficar silent porque host renderiza).
- **Critério de sucesso:**
  - `pytest tests/engine/test_cli_exit_codes.py::test_sentinel_exception_maps_to_exit_2 -xvs`
    verde.
  - `pytest tests/engine/` verde (regressão zero).
  - Exit code 2 emitido limpo via subprocess smoke (opcional).
- **Anti-padrões:**
  - NÃO pular o RED step — TDD shape é mandamento, não sugestão.
  - NÃO escrever a impl antes do test falhar primeiro.

#### Task W2.T3 — Subcommand checkpoint audit + minimal patches (split em T3a + T3b)

**Pré-condição:** W2.T0 outcome (A | B | C) já está locked no plano.
A forma de T3a/T3b consome essa decisão — sem ela, T3 não inicia.

##### Task W2.T3a — Discover checkpoint candidates (read-only, persistence)

- **Files (read-only nesta sub-task):** `engine/plan.py`,
  `engine/implement.py`, `engine/verify.py`, `engine/reconfigure.py`,
  `engine/evolve.py`, `engine/undo.py`, `engine/memory_cli.py`,
  `engine/graph_cli.py`, `engine/doctor.py`, `engine/init.py`.
- **Files (write nesta sub-task):**
  - `.planning/drift-1/checkpoint-audit.json` (NOVO; artefato de
    discovery — persistido pra T3b consumir)
- **Justificativa (Mandamento #4 — escopo whitelist explícita):** scope
  whitelist exige paths concretos por sub-task. T3a é puro discovery;
  T3b é puro patching. Separação evita scope-creep "while I'm here".
- **Steps:**
  1. Grep over os 10 módulos:
     `grep -n "question\.\(ask\|confirm\|ask_text\|ask_multi\|ask_three_paths\)" engine/<module>.py`
     pra contar callsites interativos.
  2. Grep adicional:
     `grep -n "_save_checkpoint\|checkpoint_path\|find_resumable_run\|Checkpoint(" engine/<module>.py`
     pra detectar se módulo já tem checkpoint.
  3. Pra cada módulo, produzir entrada JSON:
     ```json
     {
       "module": "engine/init.py",
       "interactive_callsites": 8,
       "checkpoint_status": "already-has",
       "action": "skip" | "extend" | "add-new",
       "reuse_path": "qa-checkpoint" | "init-pattern" | "shared-base",
       "reason": "<frase concreta apontando o outcome de W2.T0>"
     }
     ```
  4. Persistir array em `.planning/drift-1/checkpoint-audit.json`.
- **Critério de sucesso:**
  - `.planning/drift-1/checkpoint-audit.json` existe, válido (10
     entradas — uma por módulo auditado).
  - Cada entrada com `action: "extend"` ou `"add-new"` tem `reason`
    citando o outcome de W2.T0 (A/B/C).
- **Anti-padrões:**
  - NÃO escrever em `engine/*.py` nesta sub-task — T3a é discovery
    puro.
  - NÃO criar dataclass nova sem referência ao outcome de W2.T0.

##### Task W2.T3b — Patch checkpoint integration (per-module, TDD)

- **Files (write nesta sub-task):** apenas módulos com
  `action: "extend"` ou `"add-new"` no audit JSON. Lista concreta vai
  ser determinada pelo output de T3a; expected superset (a confirmar
  por T3a): `engine/plan.py`, `engine/implement.py`,
  `engine/verify.py`, `engine/reconfigure.py`, `engine/evolve.py`,
  `engine/undo.py`. Read-only (`graph_cli` em modo query, `doctor`
  read-only) skipa.
- **Files (test, novo):** pra cada módulo patcheado, um arquivo
  `tests/engine/test_<module>_resume.py` (ex.:
  `tests/engine/test_plan_resume.py`, `tests/engine/test_evolve_resume.py`).
- **Files (doc-update, mesmo commit):**
  `docs/superpowers/specs/drift-1-intent-protocol.md` §5 (UPDATE inline)
  com lista final dos módulos que ganharam checkpoint nesta wave.
- **Justificativa (Mandamento #2 — TDD obrigatório):** H-002 da
  rodada r1 do plan-auditor exige TDD shape rigoroso per módulo.
- **Steps (TDD per módulo, repete pra cada entry com action em
  `["extend", "add-new"]` no audit JSON):**
  1. **RED:** escrever failing test em
     `tests/engine/test_<module>_resume.py::test_resume_from_checkpoint`
     — assert: módulo retoma do checkpoint após exit 2 (state files
     deletados + estado interno preservado).
  2. Rodar `pytest tests/engine/test_<module>_resume.py -xvs` →
     confirmar FAIL (checkpoint ainda não existe nesse módulo OU
     existe mas não cobre o caso).
  3. **GREEN:** implementar checkpoint per outcome de W2.T0:
     - Se outcome A: `from engine.qa.checkpoint import Checkpoint,
       find_resumable_run` + integrar.
     - Se outcome B: `from engine._checkpoint import Checkpoint` (base
       extraída).
     - Se outcome C: criar dataclass `_{Module}Checkpoint` análoga a
       `_InitCheckpoint` (linhas 104 de `engine/init.py`).
  4. Rodar test → confirmar PASS.
  5. Rodar `pytest tests/engine/` → confirmar zero regressão no módulo.
  6. Smoke test E2E per comando: invoca, força intent, exit 2;
     re-invoca, confirma retoma.
- **Critério de sucesso:**
  - Cada subcommand interativo identificado em T3a tem
    `tests/engine/test_<module>_resume.py::test_resume_from_checkpoint`
    verde.
  - SPEC §5 atualizada inline (mesmo commit que o último patch) com
    lista final dos módulos que ganham checkpoint.
- **Anti-padrões:**
  - NÃO pular o RED step — TDD shape é mandamento, não sugestão.
  - NÃO expandir comportamento de comandos além do checkpoint.
  - NÃO renomear nada.
  - NÃO incluir módulos com `action: "skip"` no audit JSON.

**Commit W2:** `refactor(ui): question.py emits intent + cli exits 2 on pause`

---

### W3 — `engine/ui/tty_bridge.py`

**Goal:** Implementar fallback TTY que reusa renderer + persona.

#### Task W3.T1 — `tty_bridge.py` + tests E2E

- **Files:** `engine/ui/tty_bridge.py` (NOVO), `tests/ui/test_tty_bridge.py` (NOVO; marker `e2e` se subprocess for slow, senão integration)
- **Justificativa:** SPEC §6. Sub-Q **Sc** locked.
- **Steps:**
  1. **RED:** test que simula:
     - Subprocess `python -m engine.ui.tty_bridge engine.cli init`
       executa em modo fake (env `FORGE_FAKE_INTENT=1` que injeta
       intent sintético)
     - Stdin alimentado com resposta → tty_bridge escreve
       `forge-response.json`
     - Re-invoca subprocess → exit 0
  2. **GREEN:** implementa loop:
     ```python
     def main(command_module: str, argv: list[str]) -> int:
         while True:
             rc = subprocess.run([sys.executable, "-m", command_module, *argv],
                                 env={**os.environ, "FORGE_INTERNAL_TTY_BRIDGE": "1"}).returncode
             if rc != 2:
                 return rc
             intent = intent_state.read_pending(project_root)
             try:
                 response = _prompt_user_via_stdin(intent)
             except KeyboardInterrupt:
                 return 130
             intent_state.write_response(project_root, response)
     ```
  3. `_prompt_user_via_stdin(intent)` resgata o código `_read_line` antigo
     + `renderer.write` pro prompt; reusa `persona.mentor_calmo` pra
     phrasing (greeting opcional, pause_message em response paused).
  4. Tokens de pause (`para`, `pausa`, `quit`, `q`, `exit`)
     reconhecidos aqui → response com `paused: true`.
  5. Ctrl+C aqui → KeyboardInterrupt → exit 130 (Decision 27).
- **Critério:**
  - `pytest tests/ui/test_tty_bridge.py -xvs` PASS
  - Smoke manual: `bash -c 'echo "kmp-mobile" | python -m engine.ui.tty_bridge engine.cli init'` (ou via pty) — flui sem hang
- **Anti-padrões:**
  - NÃO executar lógica de subcomando dentro do bridge
  - NÃO reimplementar prompt logic — reusa renderer + persona

**Commit W3:** `feat(ui): tty_bridge subprocess loop for fallback TTY mode`

---

### W4 — `bin/forge` dispatcher migration

**Goal:** Detection automática TTY/Claude Code, sub-Q **Sd** locked.

#### Task W4.T1 — `bin/forge` patch

- **Files:** `bin/forge` (MODIFY)
- **Justificativa load-bearing:** `bin/forge` é o entrypoint canônico.
  Mandamento citado: Decision 19 (Python core + Bash dispatcher) +
  Decision 10 (zero flags — detection é env-based, não flag).
- **Steps:**
  1. Confirmar (via doc oficial Claude Code lookup — Context7 MCP ou
     `ctx7 docs claude-code "host env var"`) o nome canônico da env
     var.[^claudecode-rename] Resolvido em W4-FU: nome real é
     `CLAUDECODE` (verificação empírica vs Claude Code 2.1.153,
     commit b149678).

     [^claudecode-rename]: Renomeado em W4-FU (verificação empírica vs
     Claude Code 2.1.153 mostrou que `CLAUDECODE` é o nome real exportado
     pelo host). SPEC inicial usava `CLAUDE_CODE_HOST` como placeholder.
  2. Patch:
     ```bash
     # Substituir linha 28 (exec atual):
     if [[ -n "${CLAUDECODE:-}" ]] || [[ ! -t 0 ]] || [[ ! -t 1 ]] || [[ -n "${FORGE_FORCE_INTENT_MODE:-}" ]]; then
       exec "$PYTHON" -m engine.cli "$@"
     elif [[ -n "${FORGE_FORCE_TTY_MODE:-}" ]]; then
       exec "$PYTHON" -m engine.ui.tty_bridge engine.cli "$@"
     else
       exec "$PYTHON" -m engine.ui.tty_bridge engine.cli "$@"
     fi
     ```
  3. Atualizar comentário existente nas linhas 26-27 explicando o
     dispatch.
- **Critério:**
  - `bash -n bin/forge` (syntax check) PASS
  - Smoke: `FORGE_FORCE_INTENT_MODE=1 bin/forge --version` retorna versão
  - Smoke: `bin/forge --version` em TTY funciona (passa por tty_bridge)
- **Anti-padrões:**
  - NÃO adicionar flag de CLI (Decision 10)
  - NÃO mudar resolução de `FORGE_HOME` (linhas 13-23)

#### Task W4.T2 — Hooks audit pra exit 2

- **Files:** audit `hooks/*.sh` + `.claude/hooks/*.sh` que invocam
  `forge` — patches MINIMAL se falham com exit 2
- **Justificativa:** hooks atuais assumem `forge` exit 0 ou 1. Novo
  exit 2 (paused) pode quebrar fluxo. Audit + ajuste explícito.
- **Steps:**
  1. `grep -rn "forge \|/bin/forge" hooks/ .claude/hooks/`
  2. Pra cada match, avaliar:
     - Se hook é background (PostToolUse, SessionStart): exit 2 é
       erro inválido (hook não deveria estar interativo). Documentar
       em código ou suprimir via redirect.
     - Se hook é synchronous (pre-commit, etc.): hooks NÃO devem
       invocar `forge` interativo. Confirmar isso é regra; se algum
       hook viola, abre gap em 04-pending.
- **Critério:** zero regressão observada em smoke do
  `SMOKE-CHECKLIST.md`

**Commit W4:** `feat(forge): bin/forge dispatcher with TTY/host detection`

---

### W5 — Integration tests E2E (ambos modos)

**Goal:** AC-1 a AC-9 testáveis automáticos.

#### Task W5.T1 — Integration test intent mode E2E

- **Files:** `tests/integration/test_intent_protocol_e2e.py` (NOVO; marker `integration`)
- **Justificativa:** AC-1, AC-2, AC-6, AC-7 do SPEC. Mandamento #2
  (verde antes de pronto).
- **Steps:**
  1. **RED:** testes:
     - `test_init_emits_intent_first_prompt`: invoca
       `subprocess.run(["python", "-m", "engine.cli", "init"], stdin=DEVNULL)` →
       exit code 2; lê `.claude/state/forge-pending.json` → schema
       válido + `kind == "ask"` + `question` contém texto esperado
     - `test_resume_consumes_response_and_deletes`: escreve response,
       re-invoca subprocess, valida exit code 0 OU exit code 2 com
       próximo intent (estado avançou)
     - `test_race_detection_rejects_stale_concurrent`: escreve pending
       sintético, invoca, espera exit 1 + mensagem de race
     - `test_response_intent_id_mismatch_exits_error`: escreve response
       com intent-id wrong, invoca, exit 1
  2. **GREEN:** ajusta engine onde necessário
  3. `pytest tests/integration/test_intent_protocol_e2e.py -xvs`
- **Critério:** todos os 4 testes verdes

#### Task W5.T2 — E2E test tty_bridge mode

- **Files:** `tests/e2e/test_tty_bridge_e2e.py` (NOVO; marker `e2e`)
- **Justificativa:** AC-3, AC-5 do SPEC.
- **Steps:**
  1. **RED:** testes via `pexpect` ou `pty` stdlib:
     - `test_tty_mode_prompts_stdin_like_legacy`: spawn
       `python -m engine.ui.tty_bridge engine.cli init`, alimenta stdin,
       valida fluxo de prompts equivalente ao legacy
     - `test_tty_mode_ctrlc_exits_130`: spawn, envia SIGINT, exit 130
     - `test_pause_token_propagates_as_paused_response`: envia `para` em
       prompt allow-pause, espera mesma semântica de
       `PromptAbortedError`
  2. **GREEN:** ajusta `tty_bridge` se necessário
  3. `pytest tests/e2e/test_tty_bridge_e2e.py -xvs`
- **Critério:** verdes; documentar dep `pexpect` em pyproject se for
  necessária (NÃO adiciona dep nova se `pty` stdlib basta).

#### Task W5.T3 — Smoke tests dos 10 callsite modules

- **Files:** `tests/integration/test_callsites_smoke.py` (NOVO; marker
  `integration`)
- **Justificativa:** AC-8 — preservação backward-compat.
- **Steps:**
  1. **RED:** pra cada um dos 10 módulos (`init`, `plan`, `implement`,
     `verify`, `reconfigure`, `evolve`, `undo`, `memory_cli`,
     `graph_cli`, `doctor`), test mínimo que invoca o módulo em modo
     que dispara pelo menos um prompt e valida que ele emite intent
     corretamente.
  2. **GREEN:** ajusta engine quando algum módulo for stale.
- **Critério:** smoke verde dos 10 módulos.

#### Task W5.T4 — Test count verification

- **Files:** (nenhum write)
- **Steps:**
  1. `pytest --collect-only -q | tail -1` — capturar count
  2. Esperado: ≥1125 (Phase 0b baseline) + ~25 novos tests = ~1150
  3. `pytest` (full) → 0 failures, 0 errors
- **Critério:** count cresce, zero regressão

**Commit W5:** `test(intent): integration + e2e + smoke per callsite module`

---

### W6 — Doc-sync (CHANGELOG + handoff + 04-pending + schemas + README)

**Goal:** Mandamento #6. Doc-sync OBRIGATÓRIO antes do final commit.

#### Task W6.T1 — `CHANGELOG.md`

- **Files:** `CHANGELOG.md` (MODIFY)
- **Steps:**
  1. Sob `## [Unreleased]`:
     - `### Added`:
       - `engine/ui/tty_bridge.py` — fallback TTY subprocess loop
       - `engine/ui/intent_state.py` — state file I/O helpers
       - `engine/utils/json_io.py` — atomic JSON write helper
       - `docs/schemas/intent-protocol.md` — canonical JSON schema
       - Exit code 2 (paused-for-input) no contract de `forge`
     - `### Changed`:
       - `engine/ui/question.py` — refactor interno; API surface
         preservada (108 callsites em 10 módulos intocados)
       - `bin/forge` — dispatcher com TTY/CLAUDECODE detection
       - `engine/cli.py::main()` — captura `PausedForInputError` → exit 2

#### Task W6.T2 — `docs/design/08-session-handoff.md`

- **Files:** `docs/design/08-session-handoff.md` (MODIFY)
- **Steps:**
  1. `**Última atualização:**` → `2026-06-10 (v1.2-dev — DRIFT-1)`
  2. `**Estado:**` linha que reflete: "Phase A — DRIFT-1 shipped: engine
     intent-only protocol + tty_bridge fallback + bin/forge dispatcher
     migration"
  3. Tabela `| Categoria | Status |` ganha linha "Intent protocol" /
     "v1.2-dev shipped"
  4. `§Conhecidos limites` se houver — ex.: race detection sem lockfile
     real (gap aberto)

#### Task W6.T3 — `docs/design/04-pending.md` — move DRIFT-1 to "Fechado em [Unreleased]"

- **Files:** `docs/design/04-pending.md` (MODIFY)
- **Justificativa (M-002 da rodada r1 do plan-auditor):** DRIFT-1
  NÃO está em lista de pendentes ativos do arquivo — está documentado
  na seção static `## v1.2-dev pilot 2026-06-10 — findings + phase
  sequencing` (sub-seção `### Achado conceitual primário — DRIFT-1`).
  Portanto, "riscar de 04-pending" como verbo não se aplica
  literalmente; o trabalho real é **mover/copiar** a entry pra
  `## Fechado em [Unreleased]` marcando entrega por este PR.
- **Steps:**
  1. Read da entry atual em
     `docs/design/04-pending.md` seção
     `## v1.2-dev pilot 2026-06-10 — findings + phase sequencing`
     sub-seção `### Achado conceitual primário — DRIFT-1`.
     Identificar bloco completo (do heading até próxima `###` ou
     `##`).
  2. Append nova entry em `## Fechado em [Unreleased]` (criar a seção
     se ainda não existir no arquivo), com shape:
     ```
     ### DRIFT-1 — Intent Protocol (Engine intent-only + tty_bridge)
     - **PR:** `feat/drift-1-intent-protocol`
     - **SPEC:** `docs/superpowers/specs/drift-1-intent-protocol.md`
     - **PLAN:** `docs/superpowers/plans/drift-1-intent-protocol.md`
     - **Resumo:** engine deixa de ler stdin diretamente; emite intent
       via state files; tty_bridge faz fallback TTY; bin/forge dispatcher
       detecta contexto. Exit code 2 = paused-for-input.
     ```
  3. Opcional (recomendado): marcar a entry original na seção pilot com
     sufixo `(resolved by Phase A — see "Fechado em [Unreleased]")` —
     preserva histórico do achado sem deletar.
  4. Adicionar seção/sub-seção `### Findings pós DRIFT-1 (a revisitar)`
     em ## Pendentes (ou similar), listando follow-ups:
     - Race detection via `fcntl.flock` (deferido — adicionar se padrão
       aparecer em produção).
     - Subcommand checkpoint promotion pra helper genérico (gap se ≥3
       subcommands materializarem mesmo shape; outcome de W2.T0 pode
       já ter feito esta promoção — atualizar conforme entrega real).
     - `engine.utils.paths.state_dir()` promotion (gap se ≥2
       consumidores).
     - Findings deferred da Phase A continuam parcialmente válidos pra
       fallback TTY (persona+microcopy do tty_bridge ainda precisam UX
       review; Phase B continua o trabalho).
     - Hooks audit conclusivo (W4.T2) — se nenhum hook quebrou, anotar;
       se algum quebrou, adicionar fix-task.
- **Critério de sucesso:**
  - DRIFT-1 entry presente em `## Fechado em [Unreleased]` com links
    PR/SPEC/PLAN.
  - Entry original da pilot section mantida (com marca de resolução)
    OU explicitamente removida — escolha consistente, documentada no
    commit body.
  - Follow-ups listados em seção própria.
- **Anti-padrões:**
  - NÃO deletar a entry pilot sem deixar trace ("resolved by ...")
    — histórico do achado é informação.
  - NÃO inventar entries que não correspondem ao trabalho real
    entregue pelas waves anteriores.

#### Task W6.T4 — `docs/schemas/intent-protocol.md`

- Já criado em W1.T1; aqui só assegurar que está consistente com impl
  final. Update inline se W2-W3 mudaram algum campo.

#### Task W6.T5 — `docs/design/06-command-surface.md`

- **Files:** `docs/design/06-command-surface.md` (MODIFY)
- **Justificativa load-bearing:** documento é load-bearing
  (`.claude/rules/scope.md` whitelist). Justificativa: exit code
  contract mudou (adicionado 2). Mandamento #6 (doc-sync).
- **Steps:**
  1. Adicionar seção "Exit codes" ou linha em existing pra documentar
     0/1/2/130

#### Task W6.T6 — `README.md` Stats

- **Files:** `README.md` (MODIFY)
- **Steps:**
  1. Stats updated: novo módulo count, novo schema count, novo test
     count

#### Task W6.T7 — `.claude/rules/subagent-workflow.md` (se afetado)

- **Files:** `.claude/rules/subagent-workflow.md` (MODIFY se aplicável)
- **Justificativa load-bearing:** `.claude/rules/**` é load-bearing.
  Justificativa: protocolo afeta como subagent dispatches que rodam
  `forge` devem manipular exit 2. Mandamento #4 (escopo) + #6
  (doc-sync).
- **Steps:**
  1. Nova subseção: "Quando subagent invoca `forge`": exit 2 é pause,
     orchestrator responsável por ler pending + responder. Subagent NÃO
     deve fazer isso autonomamente sem context-pack explícito.

#### Task W6.T8 — Final verify + commit

- **Files:** (commit prep)
- **Steps:**
  1. `pytest` full suite → 0 failures
  2. `forge verify` → cascade verde
  3. `./bin/forge --version` smoke
  4. Manual checklist:
     - [ ] CHANGELOG Unreleased atualizado
     - [ ] handoff Última atualização = hoje
     - [ ] 04-pending: DRIFT-1 movido pra Fechado
     - [ ] schemas/intent-protocol.md presente
     - [ ] README Stats refletem +N
     - [ ] subagent-workflow rule patched se aplicável
- **Critério:** todos os 6 documents sincronizados

**Commit W6:** `docs(drift-1): sync CHANGELOG, handoff, 04-pending, schemas, README`

---

## Verification end-to-end (post-W6)

Comandos exatos pra validar AC-1..AC-9:

| AC | Comando | Esperado |
|---|---|---|
| AC-1 | `pytest tests/integration/test_intent_protocol_e2e.py::test_init_emits_intent_first_prompt -xvs` | PASS, schema válido em pending.json |
| AC-2 | `pytest tests/integration/test_intent_protocol_e2e.py::test_resume_consumes_response_and_deletes -xvs` | PASS, arquivos sumiram |
| AC-3 | `pytest tests/e2e/test_tty_bridge_e2e.py::test_tty_mode_prompts_stdin_like_legacy -xvs` | PASS |
| AC-4 | `pytest tests/ui/test_question_api_signatures.py -xvs` | PASS — signatures idênticas |
| AC-5 | `pytest tests/e2e/test_tty_bridge_e2e.py::test_tty_mode_ctrlc_exits_130 tests/ui/test_question_intent.py::test_pause_token_via_response -xvs` | PASS ambos |
| AC-6 | `pytest tests/integration/test_intent_protocol_e2e.py::test_state_files_deleted_after_consume -xvs` | PASS |
| AC-7 | `pytest tests/ui/test_intent_state.py::test_race_detection -xvs` + `tests/integration/...::test_race_detection_rejects_stale_concurrent` | PASS ambos |
| AC-8 | `pytest tests/integration/test_callsites_smoke.py -xvs` | PASS — 10 módulos |
| AC-9 | `pytest --collect-only -q | tail -1` → count ≥ 1150 ; `pytest` → 0 fail | PASS |

**Test count expected pós-Phase A:** ~1150 (baseline 1125 + ~25 novos).

**Smoke manual:**
```bash
# Intent mode
FORGE_FORCE_INTENT_MODE=1 ./bin/forge init   # deve exit 2 ao primeiro prompt
cat .claude/state/forge-pending.json | jq .  # schema correto
echo '{"schema-version":1,"intent-id":"<uuid-from-pending>","kind":"ask","value":"kmp-mobile","answered-at":"2026-06-10T19:00:00Z"}' > .claude/state/forge-response.json
FORGE_FORCE_INTENT_MODE=1 ./bin/forge init   # avança

# TTY mode
FORGE_FORCE_TTY_MODE=1 ./bin/forge init      # prompt stdin clássico

# Auto-detection (sem env override)
./bin/forge init                              # depende do contexto
```

---

## Spec coverage table

| AC | Wave que cobre | Tasks |
|---|---|---|
| AC-1 | W1, W2, W5 | W1.T3, W2.T1, W5.T1 |
| AC-2 | W2, W5 | W2.T1, W5.T1 |
| AC-3 | W3, W5 | W3.T1, W5.T2 |
| AC-4 | W2 | W2.T1 (signature preservation test) |
| AC-5 | W2, W3, W5 | W2.T1, W3.T1, W5.T2 |
| AC-6 | W1, W2, W5 | W1.T3, W2.T1, W5.T1 |
| AC-7 | W1, W5 | W1.T3, W5.T1 |
| AC-8 | W2, W5 | W2.T3, W5.T3 |
| AC-9 | W5, W6 | W5.T4, W6.T8 |

Todos AC mapeados.

---

## Pending gaps coverage

Atualizações em `docs/design/04-pending.md` (W6.T3):

- **Fechado:** DRIFT-1 → mover pra "Fechado em [Unreleased]"
- **Aberto novo (registrar):**
  - Race detection via `fcntl.flock` (deferido)
  - Subcommand checkpoint promotion pra helper genérico (gap se ≥3
    subcommands convergirem)
  - `engine.utils.paths.state_dir()` promotion (se ≥2 consumers)
  - UX/persona findings da Phase A piloto continuam parcialmente
    válidos pro `tty_bridge` — não desvaneceram completamente; Phase B
    revisita
  - Audit de hooks que possam invocar `forge` e quebrar com exit 2
    (resultado em W4.T2)
  - Eventual MCP-mode (continua anti-goal, mas registrado pra futuro)
  - Migração dos 10 callsite modules pra usar intent diretamente
    (anti-goal nesta phase, follow-up se valor materializar)

---

## Anti-padrões globais

- NÃO mudar API surface de `question.py` (assinaturas dos 5 entrypoints)
- NÃO tocar nos 10 callsite modules além de checkpoint-stubs em W2.T3
- NÃO adicionar flag CLI (Decision 10)
- NÃO adicionar runtime dep (Decision 22)
- NÃO mexer em branch `feat/gradle-dep-signal` (Phase 0b paralela)
- NÃO mexer em main branch
- NÃO suavizar TDD: failing test FIRST em cada task que cria código
- NÃO pular doc-sync em W6
- Voz mentor calmo em qualquer artefato gerado por agent
