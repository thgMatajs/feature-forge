# Onda 2 — Gates com dentes (content-check nas waves do plan) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development`
> (recomendado) ou `superpowers:executing-plans` para implementar task-a-task. Os
> passos usam checkbox (`- [ ]`) pra tracking. Voz: mentor calmo, PT neutro, sem
> emoji decorativo (só ✅⏭️🤔 do template 3-caminhos).

**Goal:** Dar dentes reais aos gates de wave do `forge plan` no pipeline do
**consumidor**. Hoje cada wave renderiza templates e pergunta "continuar/pausar"
sem olhar o conteúdo (`engine/plan.py::_run_static_wave`, `_run_wave_d`,
`_run_wave_e`). O piloto MeoBonsai pegou DUAS substâncias parciais escapando pelo
gate procedural: **tech-spec.md** com §3-§7 ainda em stubs `{{...}}` e
**task-breakdown.yaml** com `dependency_graph.edges: []` / `critical_path: []` /
`totals: 0` no default. Esta onda porta a **mecânica determinística do
plan-auditor** (os 12 checks — em especial L2 placeholder-scan e C2/M2
substance-coverage) como um content-check Python leve que roda APÓS o
`continuar`, ANTES do `acknowledged`, e que classifica a wave como
`incomplete` (gate com 3-caminhos) quando a substância está vazia.

**Architecture:** Módulo novo `engine/plan_content_check.py` (helper puro,
sem I/O de prompt) que recebe `(wave_label, artefacts: list[Path])` e devolve
uma lista de `ContentFinding` determinística. Os runners de wave em
`engine/plan.py` chamam esse helper entre o `continuar` e o
`*-acknowledged`; se há findings, emitem o bloco 3-caminhos canônico
(`mentor_calmo.three_paths_block`) e ramificam: Re-revisar (re-render +
re-checar nesta sessão), Deferir (`_persist_deferred`), Pausar/investigar. O
helper é **reuso** da forma do plan-auditor (placeholder-scan = L2;
substance-coverage = C2/M2), NÃO uma reimplementação dos 12 checks como prompt.
Ancoragem opcional via `mem find` (subprocess, degrade-soft) fica fora do
caminho crítico do gate — o content-check é estrutural e roda mesmo sem mem.

**Tech Stack:** Python 3.11+, `re` (placeholder-scan), `engine.utils.yaml_io`
(parse do task-breakdown), `engine.persona.mentor_calmo.three_paths_block`,
`engine.ui.exit_codes.ERR_WAVE_INCOMPLETE` (tag já existente). pytest com a
lane rápida `.venv/bin/pytest -m "not integration and not e2e"`.

**Source spec:** `docs/superpowers/specs/2026-06-29-pilot-remediation-design.md`
§"Onda 2 — Gates com dentes (Tema 1)". Report durável:
`docs/reports/2026-06-25-piloto-meobonsai-gaps.md` §Tema 1 + §Pontos fracos do plan.

---

## Princípios desta onda (lidos antes de cada task)

- **Reuso antes de criar (Mandamento #3):** a mecânica dos 12 checks JÁ EXISTE
  como `.claude/rules/plan-auditor.md` + prompt do `gsd-code-reviewer` (roda nos
  planos do PRÓPRIO repo). NÃO reimplemente os 12 checks. Porte só os DOIS que o
  piloto provou necessários no consumidor: **L2** (placeholder-scan: `{{...}}`,
  TBD/TODO/FIXME residual) e **C2/M2** (substance-coverage: blocos substantivos
  deixados no default vazio). O helper é a tradução determinística-em-Python dessa
  forma — não um segundo prompt de auditoria.
- **Verde antes de pronto (Mandamento #2):** `.venv/bin/pytest` full verde +
  `forge verify` sem hard fail. O count NÃO regride sem justificativa no commit
  body. `.venv/bin/pytest` é o canonical (system pytest gera falso-negativo).
- **TDD (Mandamento #2):** cada task começa com teste VERMELHO reproduzindo o
  escape do piloto (tech-spec parcial / dependency_graph vazio PASSA hoje). Só
  depois o fix faz virar verde.
- **Escopo contido (Mandamento #4):** esta onda toca SÓ `engine/plan.py`
  (pontos de wave-gate), o módulo novo `engine/plan_content_check.py`, e os testes.
  NÃO toca `01-decisions.md`. NÃO toca a DAG do `implement` (Tema 7, fechado).
  NÃO reescreve a recursão de readiness (BUG-PLAN-1, é da Onda 3).
- **Doc-sync (Mandamento #6):** ao fechar a onda, atualizar
  `docs/design/04-pending.md` (mover Tema 1 de ABERTO) + `CHANGELOG.md` no MESMO
  commit. Anotado como Task 4.

> **Colisão conhecida com Onda 3:** ambas tocam `engine/plan.py`. A Onda 3 mexe
> em `_run_wave_e` (BUG-PLAN-1, recursão de readiness ~L1058). Esta onda
> **NÃO** mexe no corpo da recursão de readiness; só ADICIONA uma chamada ao
> content-check ANTES do `wave-e-acknowledged` (linha ~L1009, antes do parse de
> verdict). Ver §Footprint & disjunção no fim deste plano.

---

## File Structure

### Created

```
engine/plan_content_check.py          # helper puro: (wave_label, artefacts) -> list[ContentFinding]
tests/unit/test_plan_content_check.py # unit do helper (placeholder-scan + substance-coverage)
tests/unit/test_plan_wave_gate_content.py  # integração: gate pega tech-spec parcial / dep-graph vazio
```

### Modified

```
engine/plan.py            # _run_static_wave / _run_wave_d / _run_wave_e chamam o content-check
docs/design/04-pending.md # Tema 1 ABERTO -> fechado (Task 4, doc-sync)
CHANGELOG.md              # entrada Unreleased (Task 4, doc-sync)
```

---

## Tasks

### Task 1 — Helper de content-check (forma do plan-auditor: L2 + C2/M2)

- [ ] **Objetivo / item da spec:** spec §"Onda 2" — "a mecânica reusa a do
  plan-auditor (não reinventa os 12 checks)". Cria o helper determinístico que
  classifica um artefato de wave como `incomplete` quando a substância está vazia.
- [ ] **ARQUIVOS PERMITIDOS (whitelist):**
  - `engine/plan_content_check.py` (Create)
  - `tests/unit/test_plan_content_check.py` (Create)
- [ ] **TDD (teste VERMELHO antes do fix):** escrever
  `test_plan_content_check.py` com casos que FALHAM contra a ausência do módulo /
  da lógica:
  - tech-spec.md renderizado-cru (tokens `{{ConceptViewModel}}`, `{{...}}` de
    §3-§7 intactos) → o helper devolve ≥1 `ContentFinding` de categoria
    `placeholder` (forma de L2). [reproduz o escape do piloto]
  - tech-spec.md com todos os `{{...}}` preenchidos → 0 findings de placeholder.
  - task-breakdown.yaml com `dependency_graph.edges: []` + `topological_order: []`
    + `critical_path: []` + `totals.tasks_count: 0` enquanto `tasks:` tem ≥1
    entrada real → ≥1 `ContentFinding` de categoria `substance` (forma de C2/M2:
    bloco substantivo deixado no default vazio). [reproduz o 2º escape do piloto]
  - task-breakdown.yaml com dep-graph populado coerente com `tasks:` → 0 findings.
  - artefato inexistente no disco → finding `missing` (não crasha).
- [ ] **Action (forma, não código):**
  - Definir `@dataclass(frozen=True) ContentFinding` com campos `artefact: Path`,
    `category: str` (`placeholder` | `substance` | `missing`), `detail: str`,
    `severity: str` (default `high` — alinhado à calibração do auditor: detection
    findings recebem severity mínimo HIGH).
  - `scan_placeholders(text: str) -> list[str]`: regex pra `{{...}}` residual +
    `TBD`/`TODO`/`FIXME` (forma de L2). Exceção verbatim do auditor: ignorar
    tokens dentro de exemplos comentados (`# ex.:`) — o piloto provou que os
    templates carregam `# ex.: ["{{slug}}"]` legítimos. Decisão de robustez:
    escanear só linhas NÃO-comentadas (filtrar `^\s*#` e trailing `# ...`), pra
    o gate não auto-disparar nos exemplos do próprio template (mesma armadilha do
    grep-gate hygiene: `grep -v '^#'`).
  - `check_task_breakdown(path: Path) -> list[ContentFinding]`: parse YAML; se
    `tasks` tem ≥2 entradas reais MAS `dependency_graph.edges == []` E
    `critical_path == []`, emitir finding `substance` ("DAG vazio com N tasks");
    idem `totals.tasks_count == 0` com `tasks` não-vazio. Single-task features
    (`len(tasks) <= 1`) NÃO disparam (DAG vazio é legítimo). Reuso:
    `engine.utils.yaml_io.read_yaml_or_default`.
  - `check_artefacts(wave_label: str, artefacts: list[Path]) -> list[ContentFinding]`:
    despacha por extensão — `.md` → placeholder-scan; `task-breakdown.yaml`
    (por nome) → `check_task_breakdown` + placeholder-scan; demais `.yaml`/`.json`
    → placeholder-scan só. Wave A (intake) é EXENTA do substance-check de DAG.
- [ ] **Reuso-first:** NÃO copiar a lista dos 12 checks. Importar
  `read_yaml_or_default` de `engine.utils.yaml_io` (não reparsear YAML à mão).
  A categoria `placeholder` é a tradução de L2; `substance` é a de C2/M2 — citar
  isso em docstring (rastreabilidade ao auditor).
- [ ] **Critério de sucesso testável (gate de aceite da spec):**
  `.venv/bin/pytest tests/unit/test_plan_content_check.py -q` verde; os 2 casos
  de escape do piloto (tech-spec parcial; dep-graph vazio) produzem findings.
- [ ] **Anti-padrões / escopo:** NÃO chamar `mem` aqui (helper puro, sem
  subprocess no caminho crítico). NÃO emitir prompt/3-caminhos no helper (isso é
  da Task 2/3 — separação puro-vs-I/O). NÃO disparar em single-task features. NÃO
  escanear linhas comentadas (auto-invalidação do gate).

### Task 2 — Wirear o content-check nas waves estáticas (A/B/C/D)

- [ ] **Objetivo / item da spec:** spec §"Onda 2" — "content-check determinístico
  nas waves do plan do consumidor". Liga o helper aos runners
  `_run_static_wave` (A/B/C) e `_run_wave_d`, ANTES do `*-acknowledged`.
- [ ] **ARQUIVOS PERMITIDOS (whitelist):**
  - `engine/plan.py` (Modify — só os runners `_run_static_wave` e `_run_wave_d`)
  - `tests/unit/test_plan_wave_gate_content.py` (Create)
- [ ] **TDD (teste VERMELHO antes do fix):** em
  `test_plan_wave_gate_content.py`, dirigir `_run_static_wave` (subtype product,
  Wave C) com `feature_path` populado com um tech-spec.md PARCIAL (stubs `{{...}}`
  em §3-§7), monkeypatchando `_continue_or_pause` pra devolver `continuar` e
  `question.ask_three_paths` pra devolver o caminho "Re-revisar" depois "Pausar".
  Assertir que: HOJE (vermelho) a wave retorna `deferred=False` (acknowledged
  cego); DEPOIS do fix a wave detecta os findings e NÃO faz acknowledge direto —
  emite o bloco 3-caminhos e ramifica. Espelhar o harness de
  `tests/unit/test_plan_deferred_exit_code.py` (monkeypatch + `_run_waves_for_subtype`).
- [ ] **Action (forma, não código):**
  - Em `_run_static_wave`, APÓS `choice = _continue_or_pause(...)` retornar
    `continuar` e ANTES de `append_history(... "{label}-acknowledged")`, chamar
    `plan_content_check.check_artefacts(label, created)`.
  - Se há findings: emitir `mentor_calmo.three_paths_block` com `gate_name`
    = "Wave {label} — conteúdo incompleto", `what_failed` listando os artefatos
    com placeholder/substance vazia, `where` = paths relativos, `why` = ["host
    avançou a wave com substância parcial", "implement/readiness assumem
    artefatos completos"], e os 3 caminhos canônicos: Re-revisar agora (re-checar
    nesta sessão) / Deferir (`_persist_deferred`) / Pausar e investigar.
  - Ramificação via `question.ask_three_paths`: caminho "a" → `renderer.write`
    orientando o host a preencher + RE-CHECAR (re-chamar `check_artefacts`; se
    limpo, segue pro acknowledge — sem recursão profunda; loop bounded por
    re-leitura do disco, não por re-render); caminhos "b"/"c" → `_persist_deferred`
    + `WaveResult(deferred=True)`.
  - Em `_run_wave_d`: mesma inserção APÓS `continuar`, ANTES de
    `wave-d-acknowledged`. O `created` de Wave D inclui o `task-breakdown.yaml` —
    o `check_task_breakdown` dispara aqui (é o lugar do 2º escape do piloto).
  - Reuso da forma do gate de readiness EXISTENTE (`_run_wave_e` L1022-1063):
    o bloco 3-caminhos + `ask_three_paths` já têm precedente no mesmo arquivo —
    seguir o MESMO shape (sem inventar UX nova).
- [ ] **Reuso-first:** reusar `mentor_calmo.three_paths_block` (3-caminhos
  exatos, nunca 2/4), `_persist_deferred`, `question.ask_three_paths`,
  `append_history`. NÃO duplicar a prosa de pausa.
- [ ] **Critério de sucesso testável (gate de aceite da spec):**
  `.venv/bin/pytest tests/unit/test_plan_wave_gate_content.py -q` verde; um plano
  de wave do consumidor com tech-spec parcial ou `dependency_graph: []` é PEGO
  (verdict != "pass"/acknowledged direto) — reproduz o escape do piloto.
- [ ] **Anti-padrões / escopo:** NÃO tocar `_run_wave_e` nesta task (é a Task 3,
  pra isolar a colisão com Onda 3). O re-check do caminho "a" deve ser BOUNDED
  (re-ler disco, não re-render infinito — lição do BUG-PLAN-1). Manter os exit
  codes do contrato (`130` pausa via `_run_waves_for_subtype`). NÃO mudar a
  assinatura de `WaveResult`.

### Task 3 — Content-check na Wave E (readiness) — co-existência com a recursão

- [ ] **Objetivo / item da spec:** estender o content-check à Wave E, que
  renderiza `implementation-readiness-review.md` + `plan-feature-handoff.json` —
  os dois também sujeitos a placeholder residual. Inserção cirúrgica pra NÃO
  colidir com a Onda 3 (BUG-PLAN-1, recursão de readiness).
- [ ] **ARQUIVOS PERMITIDOS (whitelist):**
  - `engine/plan.py` (Modify — SÓ a região L1004-L1010 de `_run_wave_e`, ANTES do
    `_parse_readiness_status`)
  - `tests/unit/test_plan_wave_gate_content.py` (Modify — adicionar caso Wave E)
- [ ] **TDD (teste VERMELHO antes do fix):** caso onde
  `implementation-readiness-review.md` tem `{{...}}` residual mas o bloco
  `readiness_verdict.status: ready` foi preenchido. HOJE (vermelho) a Wave E
  parseia "ready" e retorna `deferred=False` — passa cego apesar do handoff
  incompleto. DEPOIS: o content-check pega o placeholder ANTES do parse de
  verdict e gate-bloqueia.
- [ ] **Action (forma, não código):**
  - Em `_run_wave_e`, APÓS `continuar` (L1004) e ANTES de
    `review_path = ...` / `_parse_readiness_status` (L1009-1010), chamar
    `check_artefacts("E", created)`. Se há findings: emitir o MESMO bloco
    3-caminhos da Task 2 e ramificar (Re-revisar bounded / Deferir / Pausar) —
    sem tocar no corpo da recursão de readiness que vem DEPOIS (L1019-1063).
  - **Disjunção com Onda 3:** a Onda 3 reescreve a recursão `_run_wave_e` L1056-1059
    (path "a" recursa síncrono → trocar por exit 2). Esta task INSERE um bloco
    NOVO em L1004-1010, ACIMA da região da Onda 3. Se as duas ondas executarem em
    paralelo e tocarem `_run_wave_e`, o merge é por região disjunta (inserção
    acima vs. reescrita abaixo). Anotar no commit body que o content-check NÃO
    altera o fluxo de readiness — só antecede.
- [ ] **Reuso-first:** reusar o helper da Task 1 e o padrão de gate da Task 2
  (extrair, se útil, um `_run_content_gate(label, created, slug, project_root,
  feature_path) -> Optional[WaveResult]` privado em plan.py pra os 3 sites não
  duplicarem o bloco 3-caminhos — composição > cópia).
- [ ] **Critério de sucesso testável:** `.venv/bin/pytest
  tests/unit/test_plan_wave_gate_content.py -q` verde incluindo o caso Wave E;
  readiness com placeholder residual é pego ANTES do parse de verdict.
- [ ] **Anti-padrões / escopo:** NÃO reescrever a recursão de readiness (Onda 3).
  NÃO mudar `_parse_readiness_status`. A inserção é estritamente ACIMA da região
  que a Onda 3 toca. Se a extração de `_run_content_gate` exigir tocar
  `_run_static_wave`/`_run_wave_d` de novo, fazer na Task 2 (não retrabalho aqui).

### Task 4 — Doc-sync + regressão de suite completa

- [ ] **Objetivo / item da spec:** Mandamento #6 + gate de aceite "pytest full
  verde". Fechar a onda com doc-sync no MESMO commit lógico e rodar a suite
  inteira (não só a lane rápida) pra garantir zero regressão nos waves existentes.
- [ ] **ARQUIVOS PERMITIDOS (whitelist):**
  - `docs/design/04-pending.md` (Modify — mover Tema 1 / BUG dos gates procedurais
    de ABERTO pra fechado, citando os arquivos de fix)
  - `CHANGELOG.md` (Modify — entrada `### Added` ou `### Changed` em Unreleased:
    "content-check determinístico nas waves do plan — porta a forma do plan-auditor
    (L2 placeholder-scan + C2/M2 substance-coverage) pro pipeline do consumidor")
- [ ] **TDD:** não aplicável (doc-sync). O gate é a suite completa.
- [ ] **Action (forma, não código):**
  - Atualizar `04-pending.md`: o item Tema 1 (gates procedurais não substantivos)
    sai de ABERTO; anotar a limitação remanescente se houver (ex.: o content-check
    cobre placeholder + DAG vazio; cobertura semântica mais profunda fica pra mem
    Fase 2 — M2 "limitação nova com anotação").
  - CHANGELOG: entrada Unreleased mentor-calmo.
- [ ] **Critério de sucesso testável:** `.venv/bin/pytest` (lane completa) verde +
  `.venv/bin/pytest -m "not integration and not e2e" -q | tail -1` sem regredir o
  count + `forge verify` sem hard fail. Os testes de wave existentes
  (`test_plan_deferred_exit_code`, `test_plan_subtype`, `test_e2e_full_plan`,
  `test_plan_canonical_loop`) continuam verdes (o content-check não dispara em
  artefatos completos — happy-path intacto).
- [ ] **Anti-padrões / escopo:** NÃO tocar `01-decisions.md`. NÃO expandir o
  CHANGELOG além da onda. Se a suite completa acusar regressão num teste de wave
  com artefatos completos, o helper está disparando em falso-positivo — voltar à
  Task 1 (não silenciar o teste).

---

## Verification (fim da onda)

- `.venv/bin/pytest` (lane completa) verde.
- `forge verify` sem hard fail.
- Reprodução do escape do piloto: tech-spec parcial e `dependency_graph: []`
  agora são PEGOS pelo content-check (testes vermelhos-antes viram verdes).
- Happy-path: artefatos completos passam o gate sem fricção (regressão guard).
- `grep -v '^#'` confirmado no placeholder-scan (gate não auto-invalida nos
  exemplos comentados dos templates).

## Success criteria (mensurável)

1. Novo módulo `engine/plan_content_check.py` é a fonte única dos checks; grep
   confirma que os 3 sites de wave-gate em `plan.py` chamam o mesmo helper (via
   `_run_content_gate` ou direto) — sem lógica de check duplicada.
2. Os 2 escapes documentados do piloto (tech-spec §3-§7 stub; task-breakdown
   dep-graph/critical_path/totals vazios) produzem `ContentFinding` e gate
   3-caminhos.
3. A mecânica é reuso da FORMA do plan-auditor (L2 + C2/M2), citada em docstring —
   não uma reimplementação dos 12 checks.
4. `04-pending.md` + `CHANGELOG.md` atualizados no mesmo commit (doc-sync).

---

## Footprint preciso & disjunção (pra confirmar paralelismo)

**Arquivos que esta onda EDITA na execução:**

| Arquivo | Ação | Região |
|---|---|---|
| `engine/plan_content_check.py` | Create | módulo novo |
| `tests/unit/test_plan_content_check.py` | Create | unit do helper |
| `tests/unit/test_plan_wave_gate_content.py` | Create | integração do gate |
| `engine/plan.py` | Modify | `_run_static_wave` (~L870-876), `_run_wave_d` (~L950-956), `_run_wave_e` (inserção ~L1004-1010, ACIMA da recursão), e (opcional) novo helper privado `_run_content_gate` |
| `docs/design/04-pending.md` | Modify | seção Tema 1 (doc-sync) |
| `CHANGELOG.md` | Modify | Unreleased (doc-sync) |

**Ponto de colisão: `engine/plan.py`.**
- **Onda 3 (BUG-PLAN-1)** reescreve a recursão de readiness em `_run_wave_e`
  L1056-1059 (path "a" recursa síncrono → exit 2). Esta onda **INSERE** um bloco
  ACIMA (L1004-1010, antes do `_parse_readiness_status`) e **NÃO** altera a
  recursão. Regiões disjuntas → merge limpo se serializado; se paralelo, baixo
  risco de conflito textual (inserção acima vs. reescrita abaixo). **Recomendação:
  serializar a edição de `_run_wave_e` — esta onda primeiro (inserção acima),
  Onda 3 depois (reescrita abaixo), ou vice-versa com rebase trivial.**
- **O1 (verify/qa)** e **O4 (status/adapters)** não tocam `engine/plan.py` →
  disjunção total com esta onda.

**Nada além de `plan.py` + testes + módulo novo + 2 docs de sync é tocado.**
Não há infra de auditor compartilhada a tocar: o plan-auditor vive como
prompt/rule (`.claude/rules/plan-auditor.md` + `gsd-code-reviewer`), NÃO como
módulo Python importável — por isso o content-check é um helper NOVO que porta a
FORMA, sem importar nada do auditor (composição limpa, sem acoplar engine a
artefato de skill — Decisão 22).

## Riscos / decisões abertas

1. **Placeholder-scan vs. exemplos legítimos dos templates.** Os templates
   carregam `# ex.: ["{{slug}}"]` — o scan DEVE ignorar linhas comentadas, senão
   auto-dispara. Mitigado na Task 1 (filtrar `^\s*#` + trailing `#`). Decisão
   aberta pro executor: confirmar empiricamente contra `templates/*.template.*`
   que nenhum `{{...}}` substantivo vive fora de comentário num artefato bem
   preenchido (scout dos templates reais antes de finalizar o regex).
2. **Single-task features e DAG vazio.** `dependency_graph.edges: []` é legítimo
   pra feature de 1 task. O check só dispara com `len(tasks) >= 2`. Decisão
   aberta: confirmar o threshold (2) contra o template e o piloto (a feature do
   piloto tinha 5 tasks).
3. **Profundidade do content-check.** Esta onda cobre placeholder + DAG vazio
   (os 2 escapes provados). Cobertura semântica mais profunda (ex.: card
   contribution contradiz contract, §14 reusability) NÃO entra — fica como
   limitação anotada em `04-pending.md` (mem Fase 2). NÃO expandir escopo.
4. **Ancoragem via mem.** A spec menciona que o content-check "pode consultar o
   acervo via `mem find`". Decisão: NÃO colocar mem no caminho crítico do gate
   (o check estrutural roda sempre, mesmo sem mem). Se desejável um HINT
   mem-ancorado na mensagem 3-caminhos, é aditivo e degrade-soft
   (`engine.integrations.mem.mem_find`) — pode entrar como sub-passo opcional da
   Task 2, mas NÃO é gate de aceite. Flagado pra o executor decidir com o user.

## Status: NÃO-BLOCKED

A onda cabe num plano coeso de 4 tasks (~1 módulo + 3 sites de wire + doc-sync),
todas em `engine/plan.py` + testes + módulo novo. Footprint disjunto de O1/O4;
colisão controlada e cirúrgica com Onda 3 em `_run_wave_e`. Sem dependência de
informação faltante. Sem necessidade de split.
