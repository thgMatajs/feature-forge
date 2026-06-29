# Onda 7 — W-AGENTS: re-rota dos conductor prompts pro mem — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development pra implementar task-a-task. Steps usam checkbox (`- [ ]`).

**Goal:** Os conductor prompts consultam o substrato de conhecimento via `mem find` (não mais o `L2-project.yaml` abandonado), e o memory-distiller órfão é removido.

**Architecture:** Trabalho de prompt-engineering (markdown em `agents/`), não código. Três frentes: (1) re-rota das LEITURAS de L2/L3 → `mem find` em 4 prompts; (2) DELETE do `memory-distiller.md` (órfão — job de compressão morto pós-mem) + limpeza de refs stale; (3) doc-sync com registro do desvio da spec. O write-path NÃO muda: os prompts seguem escrevendo `proposed-evolutions.yaml`, que o `forge evolve` já roteia pro `mem inbox add` (knowledge kinds, feito no 6b/6c).

**Tech Stack:** Markdown agent prompts; `.claude/bin/mem find` (binário vendorizado, degrade-soft); pytest (`.venv/bin/pytest`) pra guards de drift.

## Global Constraints

- `.venv/bin/pytest` é o CANONICAL — nunca o system pytest.
- Voz mentor-calmo em toda prosa de prompt. Sem emoji decorativo, sem inglês corporativo.
- **Padrão uniforme de re-rota de LEITURA:** onde um prompt instrui ler `.claude/memory/L2-project.yaml` (slice / patterns / findings / frozen-decisions) pra contexto de CONHECIMENTO, substituir por: consultar via `.claude/bin/mem find "<tema derivado da feature/área>"` — use `--type decision` pra decisões travadas; sem filtro (ou `--type reference`) pra patterns/findings/convenções. Usar os hits retornados. **Degrade-soft:** se o mem está ausente/vazio/erro, prosseguir sem o bloco — NUNCA surfar "forge init", NUNCA travar.
- **Detecção AUTORITATIVA das leituras-de-L2 (H-001/H-002, plan-audit r1):** as leituras de conhecimento estão majoritariamente em PROSA, não no path literal. O inventário canônico de read-sites de CADA prompt é derivado deste grep abrangente (rode-o PRIMEIRO; os anchors de linha no §Files de cada task são DICA não-exaustiva, não inventário): `grep -rniE "memory[ /-]?L2|L2[.) ](patterns|findings|frozen|decisions)|L2-project\.yaml" agents/<prompt>.md`. Pra cada hit, classifique: (a) write-path intencional (`proposed-evolutions.yaml`) → FICA; (b) L1/inventory/graph adjacente → FICA; (c) leitura-de-conhecimento → RE-ROTAR pra `mem find`. Critério de aceite = **0 leituras-de-conhecimento não-rotadas** (não "0 ocorrências do path literal").
- **NÃO TOCAR:** leituras de L1 lifecycle (`.claude/forge/state/lifecycle/`), `inventory/` (estrutura derivada de código — fica no forge), `forge graph query`, e o write-path (`proposed-evolutions.yaml`). Esses permanecem idênticos.
- **L3 global** (`~/.claude/memory/MEMORY.md`, prefs do usuário) NÃO é o substrato de projeto — manter a leitura como está; fora do escopo deste re-route.
- Write-path inalterado: a spec dizia "retrospective emite mem inbox add", mas na prática ele escreve `proposed-evolutions.yaml` e o engine (`forge evolve` → `distiller.apply_proposal_to_l2`) já roteia knowledge kinds pro `mem inbox add` desde 6b/6c. Não duplicar isso no prompt.

---

### Task 1: re-rota de leitura — feature-prd-agent + contract-planner-agent

**Files:**
- Modify: `agents/feature-prd-agent.md` (read-sites, lista NÃO-exaustiva: L40-42, L82-83, L88 [proveniência], L133-144, L158, L276; NOTA: L91 NÃO é leitura-de-L2 — a frozen-decision real está em L82-83)
- Modify: `agents/contract-planner-agent.md` (read-sites, lista NÃO-exaustiva: L46, L261, L542-543, L601, L703; NOTA: L266 é exemplo de YAML/output — NÃO re-rotar; L783 é checklist — alinhar à redação mem)

**Interfaces:** nenhuma (prompt-doc).

- [ ] **Step 1: scout AUTORITATIVO** — rode o grep abrangente do §Global Constraints em cada um dos dois prompts e derive a lista COMPLETA de read-sites a partir dele (os anchors do §Files são dica, não inventário). Inclua os sites que o grep-de-path-literal perde — confirmados pelo plan-audit: `feature-prd-agent` L82-83, L144, L158, L276; `contract-planner-agent` L261, L601, L703 (L266 é exemplo YAML/output — NÃO re-rotar; confirme). Classifique cada hit (write-path/L1/inventory → fica; conhecimento → re-rota).

- [ ] **Step 2: feature-prd-agent — aplicar o padrão de re-rota**
  - L40-42 (input slice `.claude/memory/L2-project.yaml` — patterns/frozen-decisions/findings): trocar a instrução de "ler o slice de L2" por "consultar `.claude/bin/mem find` pelos temas da feature (patterns/decisões/findings); degrade-soft".
  - L88: a citação de proveniência de constraint `(memory-L2: {id})` passa a `(mem: {id})` (o id agora é o id da nota do mem).
  - L91 (non-goals from L2 frozen-decisions): `mem find "<tema>" --type decision`.
  - L133-144 (Phase 3 cross-reference com memory): re-rotar a parte de memória pra `mem find`; manter a parte de `design-system.yaml`/graph (inventory/estrutura) intacta.
  - L158-159 (grep findings por keywords em L2): `mem find "<keywords>"`.

- [ ] **Step 3: contract-planner-agent — aplicar o padrão de re-rota**
  - L46 (`docs/schemas/memory.md` — L2 patterns/findings/decisions-frozen): a leitura de PADRÕES de conhecimento vira `mem find`; a referência ao SCHEMA (`docs/schemas/memory.md`) some se ela só servia pra ler L2 — confirme no contexto (se o schema doc é citado só como fonte de patterns de L2, troque por mem find; se descreve estrutura ainda usada, mantenha a parte estrutural).
  - L261, L266, L601 (conflict-strategy/pattern "from L2 patterns"): `mem find "conflict-strategy loading-guard cache-strategy"`.
  - L542-543 (memory L2: patterns/findings/decisions-frozen): `mem find` pelos temas; manter as linhas de `inventory.*` adjacentes intactas.
  - L783 (checklist "Listed every L2 pattern applicable"): reformular pra "consultou o mem pelos patterns aplicáveis".

- [ ] **Step 4: verificar que L1/inventory/graph/write-path ficaram intactos**
  Run: `git diff agents/feature-prd-agent.md agents/contract-planner-agent.md`
  Confirme: nenhuma linha de `.claude/forge/state/lifecycle/`, `inventory.`, `forge graph`, ou `proposed-evolutions` foi alterada. Toda mudança troca leitura-de-L2 por `mem find`.

- [ ] **Step 5: Commit**
```bash
git add agents/feature-prd-agent.md agents/contract-planner-agent.md
git commit -m "feat(agents): re-rota leitura L2->mem find em feature-prd + contract-planner (Onda 7 T1)"
```

---

### Task 2: re-rota de leitura — planning-conductor + retrospective-agent

**Files:**
- Modify: `agents/planning-conductor.md` (read-sites, lista NÃO-exaustiva: L45, L46 [L3 global: MANTER], L117, L331, L422-423, L431, L456, L464, L731, L896, L982, L1200)
- Modify: `agents/retrospective-agent.md` (read-sites, lista NÃO-exaustiva: L53 [constraint — ver Step 3], L89, L155, L163, L167, L175-176, L179-180, L184-186, L191, L211-213, L295, L595 [boundary note])

**Interfaces:** nenhuma (prompt-doc).

- [ ] **Step 1: scout AUTORITATIVO** — rode o grep abrangente do §Global Constraints em cada prompt e derive a lista COMPLETA de read-sites (anchors do §Files = dica). Sites confirmados pelo plan-audit que o grep-literal perde: `planning-conductor` L731 (path em bloco expected-input), L896, L982, L1200; `retrospective` L155, L163, L167, L179-180, L295. ATENÇÃO: ambos têm MUITA leitura/escrita de L1 lifecycle (`.claude/forge/state/lifecycle/`) — essas FICAM. E o retrospective ESCREVE `proposed-evolutions.yaml` — isso FICA (o engine roteia).

- [ ] **Step 2: planning-conductor — re-rota só das leituras de L2**
  - L45 (`.claude/memory/L2-project.yaml` — patterns cross-feature): `mem find "<área da feature> patterns"`.
  - L46 (`~/.claude/memory/MEMORY.md` — L3 global): MANTER como está (L3 global, fora do escopo).
  - L117 ("Load workflow-config + all inventories + memory L2/L3"): trocar "memory L2" por "consulta `mem find`"; manter inventories e L3.
  - L331 ("Memory L2 frozen-decisions"): `mem find "<tema>" --type decision`.
  - L422-423 ("L2 `decisions-frozen` + memory L2/L3"): re-rotar a parte L2 pra `mem find`; manter `engine/inventory/`.
  - L431, L456, L464 (terminologia vs entidade da L2 / reusar screen-analysis da L2 / "Grafo/inventory/L2 ausente"): trocar a consulta de L2 por `mem find`; manter grafo/inventory.

- [ ] **Step 3: retrospective-agent — re-rota das leituras + nota de boundary**
  - L89 (`.claude/memory/L2-project.yaml` full): trocar a leitura completa de L2 por `mem find` pelos temas relevantes (patterns/findings/decisions) — a curadoria global agora é do mem.
  - L175-176 ("Query L2.patterns by name/description"): `mem find "<pattern-name ou descrição>"`.
  - L184-186 ("Pattern already in L2"): `mem find "{pattern-name}"` pra checar existência.
  - L191 (cross-ref `L2.findings`): `mem find "<finding keywords>"`.
  - L211-213 ("prior Q via graph + memory"): a parte "memory" vira `mem find`; manter `forge graph query`.
  - L595 (boundary note "Not a memory-distiller. When L2 grows past max-size-mb, the separate memory-distiller agent handles compression."): REESCREVER — o memory-distiller foi removido (Task 3) e a compressão agora é do `mem evolve`. Nova redação: o agente segue só PROPONDO (escreve `proposed-evolutions.yaml`); a curadoria/compressão do acervo é do `mem evolve`. NÃO mencionar o memory-distiller.
  - L53 (constraint "never mutate `.claude/memory/L2-project.yaml`"): REESCREVER pra "never writes the knowledge substrate directly — proposals only, via `proposed-evolutions.yaml`" (M-001 plan-audit: a frase referencia um artefato que a onda aposenta; alinha com o boundary note de L595).
  - **NÃO TOCAR** as escritas de `proposed-evolutions.yaml` (L160-172, L181-199, L240-246) nem as leituras/escritas de L1 — o write-path já roteia via engine.

- [ ] **Step 4: verificar write-path + L1 intactos**
  Run: `git diff agents/planning-conductor.md agents/retrospective-agent.md`
  Confirme: `proposed-evolutions.yaml`, `.claude/forge/state/lifecycle/`, `forge graph`, e as linhas de `inventory.` NÃO mudaram (exceto a re-rota pontual de leitura-L2 e a nota de boundary L595).

- [ ] **Step 5: Commit**
```bash
git add agents/planning-conductor.md agents/retrospective-agent.md
git commit -m "feat(agents): re-rota leitura L2->mem find em planning-conductor + retrospective + boundary note (Onda 7 T2)"
```

---

### Task 3: DELETE memory-distiller órfão + limpeza de refs stale

**Files:**
- Delete: `agents/memory-distiller.md`
- Modify: `engine/doctor.py:588` (mensagem que cita "memory-distiller roda automático")
- Modify: `templates/evals.template.json` (descrições L2/L105 que citam memory-distiller como consumidor)

**Interfaces:** nenhuma.

- [ ] **Step 1: confirmar orfandade** — `grep -rn "memory-distiller" engine/ agents/ cards/ templates/ docs/` e confirme que NENHUM código DESPACHA o agente (as refs são: labels de atribuição em `distiller.py`/`l2.py` — ENGINE-side, ficam; a msg em `doctor.py:588`; a descrição em `evals.template.json`; a boundary note em `retrospective-agent.md:595` — já tratada na Task 2). `forge memory distill` já vai pro `mem evolve` (`memory_cli.py:13,154`).

- [ ] **Step 2: deletar o prompt**
```bash
git rm agents/memory-distiller.md
```

- [ ] **Step 3: limpar a msg do doctor** — em `engine/doctor.py:588`, a mensagem "memory-distiller roda automático no próximo verify" não faz mais sentido (agente removido; curadoria é `mem evolve`). Reescrever pra refletir que a curadoria do acervo é via `forge memory distill` (→ `mem evolve`), ou remover a sugestão se não se aplica mais. Mentor-calmo.

- [ ] **Step 4: limpar evals.template.json** — nas descrições (`_template_description` e o `_description` de "Candidatos a destilação L2", ~L2 e ~L105) que citam memory-distiller como consumidor de candidatos L2: atualizar pra refletir que o acervo é gerido pelo mem (candidatos vão pro `mem inbox`), removendo a menção ao memory-distiller. Não quebrar o JSON (validar).

- [ ] **Step 5: verificar que nada que DESPACHA o agente sobrou + JSON válido**
  Run: `grep -rn "memory-distiller" engine/ agents/ templates/` — só devem restar os labels de atribuição internos em `engine/memory/distiller.py`/`l2.py` (strings `"last-source"`/`"archived-by"` — atribuição histórica, OK manter).
  Run: `python3 -c "import json; json.load(open('templates/evals.template.json'))"` → sem erro.

- [ ] **Step 6: rodar a lane afetada (guard de drift / doctor)**
  Run: `.venv/bin/pytest -m 'not integration and not e2e' -q | tail -3`
  Expected: verde. Se algum teste assertava a existência do `memory-distiller.md` ou a msg antiga do doctor, ATUALIZE o teste (é mudança de contrato legítima da deleção) — e reporte qual. Se a mudança exigir tocar arquivo fora desta whitelist, PARE e reporte.

- [ ] **Step 7: Commit**
```bash
git add -A agents/ engine/doctor.py templates/evals.template.json
git commit -m "refactor(agents): remove memory-distiller órfão (job de compressão morto pós-mem) + limpa refs (Onda 7 T3)"
```

---

### Task 4: doc-sync + registro do desvio da spec

**Files:**
- Modify: `CHANGELOG.md` (Unreleased)
- Modify: `docs/design/04-pending.md`
- Modify: `docs/superpowers/specs/2026-06-25-mem-integration-design.md` (anotar o desvio na §Re-roteamento)
- Modify: `README.md` (só se algum stat exposto mudou)

**Interfaces:** nenhuma.

- [ ] **Step 1: CHANGELOG (Unreleased)**
  Sob `### Changed`:
```
- Conductor prompts (feature-prd-agent, planning-conductor, contract-planner-agent,
  retrospective-agent) consultam o acervo via `mem find` em vez do `L2-project.yaml`
  abandonado (Onda 7 / W-AGENTS). Write-path inalterado — proposals seguem via
  `proposed-evolutions.yaml` → `forge evolve` → `mem inbox add` (knowledge kinds).
```
  Sob `### Removed`:
```
- `agents/memory-distiller.md` — agente órfão; a compressão de L2 perdeu sentido
  pós-mem (o `mem evolve` gere o tamanho do acervo) e nada o despachava. Desvio
  consciente da spec §Re-roteamento (que previa repurpose pra gerador de inbox —
  descartado por duplicar o retrospective-agent + a skill mem-consolidate).
```

- [ ] **Step 2: 04-pending** — registrar (append, mentor-calmo) que a Onda 7 fechou a re-rota de leitura dos conductor prompts e removeu o memory-distiller; e que o `_KNOWLEDGE_KINDS` do engine cobre só `promote-to-l2`/`l1-to-l2-promotion`/`consolidate-l2` — os demais kinds que o retrospective emite (convention-refinement/decay-signal/question-elimination) seguem em `NotImplementedError` (limitação pré-existente v1.1, NÃO introduzida aqui).

- [ ] **Step 3: anotar o desvio na spec** — em `docs/superpowers/specs/2026-06-25-mem-integration-design.md`, na linha da tabela §Re-roteamento sobre `agents/memory-distiller.md` (~L680), adicionar uma nota (append, não apagar o texto original): `[Onda 7, 2026-06-29: o repurpose foi DESCARTADO — o agente foi REMOVIDO. Job de compressão morto pós-mem; repurpose duplicaria retrospective-agent + mem-consolidate. Ver CHANGELOG ### Removed.]`

- [ ] **Step 4: README** — `grep -n "agent" README.md` por algum stat de contagem de agentes; se existe e mudou (um agente a menos), atualizar pro número exato. Senão, não tocar.

- [ ] **Step 5: Commit**
```bash
git add CHANGELOG.md docs/design/04-pending.md docs/superpowers/specs/2026-06-25-mem-integration-design.md README.md
git commit -m "docs(onda7): doc-sync W-AGENTS — re-rota de leitura + remoção do distiller + desvio da spec (Onda 7 T4)"
```

---

## Notas de verificação final (pós-execução)

- Gate de re-rota (H-001): rode `grep -rniE "memory[ /-]?L2|L2[.) ](patterns|findings|frozen|decisions)|L2-project\.yaml" agents/` e classifique CADA hit remanescente — aceite = **0 leituras-de-conhecimento não-rotadas** (write-path/L1/inventory podem aparecer e ficam). NÃO usar o grep-de-path-literal como prova.
- `grep -rn "memory-distiller" agents/ engine/doctor.py templates/` → só atribuição interna em distiller.py/l2.py.
- Write-path intacto: `proposed-evolutions.yaml` ainda referenciado em planning-conductor + retrospective (não re-rotado no prompt — o engine roteia).
- L1/inventory/graph intactos nos 4 prompts.
- Lanes: rapid + integration (10 pré-existentes) + e2e (RUN_E2E=1) verdes; determinismo 25.
- Review holístico do diff cumulativo da Onda 7 por gsd-code-reviewer: convention-scout contra os prompts REAIS (a re-rota não deixou leitura-de-L2 órfã; o boundary note não cita mais o distiller; nenhuma duplicação com mem-consolidate introduzida).
