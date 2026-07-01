# mem como fonte primária de contexto — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps usam checkbox (`- [ ]`).

**Goal:** Promover mem-first a Mandamento Tier-0, reforçar o SessionStart, e espelhar os temas abertos ativos do backlog no mem como notas `reference` — fechando o split-brain de recall sem deletar docs nem tocar a Decisão 20.

**Architecture:** Governança (CLAUDE.md/hooks/rules) + conteúdo mem. Zero código de `engine/`. Remediação de gap da integração Fase 0/1 (ver spec §1).

**Tech Stack:** Markdown (CLAUDE.md, rules), Bash (hook SessionStart), `.claude/bin/mem` (notas), pytest (verificação estrutural).

## Global Constraints

- Voz mentor calmo em todo artefato (Mandamento #5).
- Self-edit do CLAUDE.md segue **additive → enxugue → gate-antes-de-merge**.
- **NÃO** deletar `04-pending.md` nem `08-session-handoff.md`. **NÃO** tocar Decisão 20. **NÃO** é Revisita de Decisão (mandamentos ≠ Decisões locked).
- `.venv/bin/pytest` é o canonical (system pytest dá false fail).
- Branch `feat/mem-first-context`. Sem push até `gh auth` = `thgMatajs` (drift reincide).
- **Correção factual sobre a spec:** o `.claude/bin/mem` NÃO tem `type: project` (tipos: decision/episode/feedback/reference/session). Os temas abertos são espelhados como `type: reference` (ponteiros pro doc canônico) — casa com as notas de gap-aberto já existentes no acervo. A Task 4 também corrige a redação da spec (`project` → `reference`).
- Contagem "6 mandamentos" → "7" só nos 3 sites REAIS: `CLAUDE.md:58` (heading), `CLAUDE.md:150`, `.claude/rules/README.md:10`. **NÃO** tocar "6 disciplinas universais" (conceito diferente, `docs/design/07-discipline.md`).

---

### Task 1: Mandamento #7 no CLAUDE.md (+ contagem consistente + enxugue)

**Files:**
- Modify: `CLAUDE.md` (heading L58; novo §7 após §6/L114; ref L150; enxugue da seção "Memória persistente" L115+)
- Modify: `.claude/rules/README.md:10` (contagem 6→7)
- Test: `tests/integration/test_claude_rules_system.py`

- [ ] **Step 1 (additive): adicionar o Mandamento #7** após a seção "### 6. Doc-sync na mesma mudança" (antes de "## Memória persistente"). Texto exato:

```markdown
### 7. mem é a primeira fonte de contexto passado

Antes de responder perguntas de estado / status / "o que falta" / histórico,
e antes de despachar subagente ou decidir algo com precedente, consulte
`.claude/bin/mem find "<tema>"` — no PRIMEIRO turno, em paralelo com Read/git,
não depois. O mem carrega a disciplina de processo, o handoff de estado (via
`mem session`) e os temas abertos ativos (notas `reference` que apontam pro
backlog). Os docs (`04-pending.md`, specs) enumeram o detalhe canônico; o mem
surfa o relevante. Recall raso = falha de processo, não do mem.

Detalhe: `.claude/bin/mem find "mem-first primeira fonte de contexto estado status"`.
```

- [ ] **Step 2: atualizar a contagem** — `CLAUDE.md:58` `## Os 6 mandamentos (não-negociáveis)` → `## Os 7 mandamentos (não-negociáveis)`; `CLAUDE.md:150` `Mandamento 0 + os 6 mandamentos + fluxo único` → `os 7 mandamentos`; `.claude/rules/README.md:10` `Tier-0 (Mandamento 0 + 6 mandamentos + fluxo único)` → `7 mandamentos`. NÃO tocar "6 disciplinas".

- [ ] **Step 3 (enxugue): reframe da seção "Memória persistente (mem)"** pra não duplicar o mandamento. Prefixe a seção com uma linha que defere ao #7 como autoridade, mantendo o resto como índice de recuperação:

```markdown
> O **Mandamento #7** (Tier-0) torna o mem-first invariante; esta seção é o
> índice de recuperação das rules por tema.
```
Inserir logo após o título "## Memória persistente (mem) — índice das rules". Manter o corpo da seção existente.

- [ ] **Step 4: rodar teste estrutural**

Run: `.venv/bin/pytest tests/integration/test_claude_rules_system.py -v`
Expected: PASS (CLAUDE.md existe, rules indexadas — integridade preservada).

- [ ] **Step 5: commit**

```bash
git add CLAUDE.md .claude/rules/README.md
git commit -m "feat(mem-first): Mandamento #7 — mem é a primeira fonte de contexto passado"
```

---

### Task 2: Reforço no SessionStart (nomear Mandamento #7)

**Files:**
- Modify: `.claude/hooks/session-start-orientation.sh` (bloco final `cat <<EOF`, linha "Regras:")
- Test: `tests/integration/test_session_start_graph_reminder.py`, `tests/integration/test_claude_rules_system.py`

**Interfaces:**
- Consumes: nada. Produces: o hook injeta o mesmo texto + a linha do Mandamento #7.

- [ ] **Step 1: adicionar a linha do Mandamento #7** no heredoc final, logo após a linha `Regras: CLAUDE.md · Mandamento 0: .claude/rules/orchestrator-persona.md`:

```
Mandamento #7 (mem-first): consulte \`.claude/bin/mem find\` no PRIMEIRO turno em
perguntas de estado / status / "o que falta" / histórico — em paralelo com Read/git.
```

- [ ] **Step 2: rodar o hook manualmente** pra confirmar que ainda injeta + nomeia o #7

Run: `bash .claude/hooks/session-start-orientation.sh "$PWD/.claude/memory"`
Expected: imprime a orientação (🔨 feature-forge…), o estado do último `mem session`, e a nova linha do Mandamento #7. Exit 0.

- [ ] **Step 3: rodar testes do hook + rules**

Run: `.venv/bin/pytest tests/integration/test_session_start_graph_reminder.py tests/integration/test_claude_rules_system.py -v`
Expected: PASS.

- [ ] **Step 4: commit**

```bash
git add .claude/hooks/session-start-orientation.sh
git commit -m "feat(mem-first): SessionStart nomeia o Mandamento #7"
```

---

### Task 3: Espelhar temas abertos ativos como notas `reference`

**Files:**
- Modify: `.claude/memory/thgmatajs_at_users.noreply.github.com.jsonl` (via `.claude/bin/mem add` — NÃO editar à mão)

- [ ] **Step 1: reconferir o conjunto aberto-ativo** contra o backlog

Run: `grep -nE "Abertos|Follow-on|DEFERIDO|PENDENTE|MI-02|I-02|M-001|_KNOWLEDGE_KINDS|W-MIGRATE|Nível 2|Nível 3" docs/design/04-pending.md | head -40`
Expected: confirma os ~7 temas abertos ativos. Se divergir do conjunto abaixo, use o conjunto REAL do grep (o backlog é canônico).

- [ ] **Step 2: criar as notas `reference`** (uma por tema aberto ativo). Cada body aponta pra seção do `04-pending` + status. Comandos:

```bash
.claude/bin/mem add --type reference -t "Aberto: Tema 6 Nível 2 (smoke) — verificação runtime" --tags "tema6,smoke,verify,aberto" "Tema 6 face runtime/visual, Nível 2 (smoke): 'app sobe + 1 assert'. Spec produto: docs/superpowers/specs/2026-06-30-runtime-visual-verification-design.md. Caminho A (consumidor declara native-gates.smoke.cmd; forge só RODA, skip→degraded, step do verify reusando engine/external_exec.py) PENDENTE DE CONFIRMAR. Canônico: 04-pending §Follow-on 'impl de runtime/visual'."

.claude/bin/mem add --type reference -t "Aberto/deferido: Tema 6 Nível 3 (screenshot diff)" --tags "tema6,screenshot,verify,deferido" "Tema 6 Nível 3 (screenshot + baseline): o mais frágil/caro. DEFERIDO pós-piloto de N2 (só sobe nível quando o anterior provou valor num consumer real). Spec: 2026-06-30-runtime-visual-verification-design.md §5. Canônico: 04-pending §Follow-on."

.claude/bin/mem add --type reference -t "Aberto: MI-02 — gate de progresso ignora FORGE_FORCE_COLOR" --tags "mi-02,tty,aberto" "Follow-on Fase 1 Track D: _is_tty usa stream.isatty() direto; renderer usa FORGE_FORCE_COLOR como proxy de TTY. Fix: _is_tty puro. Baixo impacto. Reentrar ao tocar renderer/gate de spinner. Canônico: 04-pending §Follow-on MI-02."

.claude/bin/mem add --type reference -t "Aberto: I-02 — dedup helper de teste external_exec" --tags "i-02,testes,aberto" "test_verify_build_only.py e test_verify_native_gates.py duplicam _write_fake_gradlew/_fake_run. Extrair pra conftest/helpers quando o 3º gate nativo (smoke/detekt/swiftlint) chegar. Canônico: 04-pending §Follow-on I-02."

.claude/bin/mem add --type reference -t "Aberto: W-VENDOR M-001 — reconfigure/upgrade não re-vendoriza mem" --tags "w-vendor,m-001,mem,aberto" "forge init re-vendoriza o mem; reconfigure/upgrade NÃO (drift de pin sinalizado por forge doctor cat mem→WARN; remédio é forge init manual). Gap: opção de re-vendorizar no reconfigure/upgrade. Reentrar quando mem virar substrato padrão de todos consumidores. Canônico: 04-pending §W-VENDOR."

.claude/bin/mem add --type reference -t "Aberto: _KNOWLEDGE_KINDS cobre só 3 dos kinds do retrospective" --tags "knowledge-kinds,retrospective,aberto" "_KNOWLEDGE_KINDS roteia pro mem inbox só promote-to-l2/l1-to-l2-promotion/consolidate-l2. Faltam convention-refinement/decay-signal/question-elimination (NotImplementedError). Limitação pré-existente v1.1. Reentrar quando o roteamento de knowledge kinds for ampliado. Canônico: 04-pending §W-AGENTS."

.claude/bin/mem add --type reference -t "Deferido: W-MIGRATE (migrador L2→mem) até brownfield real" --tags "w-migrate,mem,deferido" "Migrador forge-side L2→mem DEFERIDO na Fase 1 (pré-produção, sem consumidor brownfield com L2-project.yaml). Design congelado em 2026-06-25-mem-integration-design.md §Migração. Reentrada: ≥1 projeto brownfield adotar a integração. Canônico: 04-pending §W-MIGRATE."
```

- [ ] **Step 3: verificar recall** de 1º turno

Run: `.claude/bin/mem find "Tema 6 smoke runtime verificação nível 2"` e `.claude/bin/mem find "follow-ons abertos MI-02 I-02 backlog"`
Expected: as notas novas surgem nos resultados. (Commit do JSONL na Task 4.)

---

### Task 4: Disciplina de sincronia (doc-sync) + correção da spec + CHANGELOG

**Files:**
- Modify: `.claude/rules/doc-sync.md` (ponteiro da nova regra de sincronia)
- Modify: `docs/superpowers/specs/2026-07-01-mem-first-context-source-design.md` (`project` → `reference`)
- Modify: `CHANGELOG.md` (entrada [Unreleased])
- Modify: `.claude/memory/*.jsonl` (via mem add — nota da matriz doc-sync)
- Test: `tests/integration/test_claude_rules_system.py`

- [ ] **Step 1: ponteiro de sincronia no doc-sync.md** — na seção "Invariante always-on", adicionar:

```markdown
- **Sincronia mem↔backlog:** fechar um item em `docs/design/04-pending.md` →
  arquivar/supersede a nota `reference` correspondente do mem NO MESMO commit
  (o mem surfa só os temas ABERTOS ATIVOS; o doc enumera tudo). Mandamento #7.
```

- [ ] **Step 2: corrigir a redação da spec** — em `2026-07-01-mem-first-context-source-design.md`, trocar as ocorrências de nota `project` por nota `reference` (§4 Frente 3 e onde aparecer), com nota inline: "(mem não tem type project; reference é o tipo de ponteiro)".

- [ ] **Step 3: registrar a regra no mem**

```bash
.claude/bin/mem add --type reference -t "Doc-sync: fechar item 04-pending arquiva a nota reference do mem no mesmo commit" --tags "doc-sync,mem,sincronia,mandamento7" "Regra de sincronia mem-backlog (Mandamento #7): o mem carrega notas reference só dos temas ABERTOS ATIVOS; fechar um item em 04-pending → arquivar/supersede a nota reference correspondente NO MESMO commit. Doc enumera tudo; mem surfa o ativo. Ponteiro em .claude/rules/doc-sync.md."
```

- [ ] **Step 4: entrada no CHANGELOG** sob `## [Unreleased]`, seção `### Added`:

```markdown
### Added
- **Mandamento #7 (mem-first)** — mem é a primeira fonte de contexto passado
  (CLAUDE.md Tier-0). Remedia gap da integração mem Fase 0/1: a disciplina
  mem-first era ponteiro soft, agora é invariante always-on. SessionStart nomeia
  o mandamento; temas abertos ativos do backlog espelhados no mem como notas
  `reference`; regra de sincronia mem↔04-pending na matriz doc-sync.
  Spec: `docs/superpowers/specs/2026-07-01-mem-first-context-source-design.md`.
```

- [ ] **Step 5: teste estrutural + commit**

Run: `.venv/bin/pytest tests/integration/test_claude_rules_system.py -v`
Expected: PASS.

```bash
git add .claude/rules/doc-sync.md docs/superpowers/specs/2026-07-01-mem-first-context-source-design.md CHANGELOG.md .claude/memory/*.jsonl
git commit -m "feat(mem-first): disciplina de sincronia doc-sync + espelha abertos + CHANGELOG"
```

Nota: o `git add .claude/memory/*.jsonl` inclui as notas `reference` da Task 3 + a nota de sincronia + o handoff `mem session` acumulado — todos batch-commitados aqui (padrão do repo pra JSONL de memória).

---

### Task 5: Verification (full-lane + recall + SessionStart)

**Files:** nenhum (só verificação).

- [ ] **Step 1: lane rápida** — `.venv/bin/pytest -m "not integration and not e2e" -q | tail -3` → verde, sem regressão de count.
- [ ] **Step 2: lane completa** — `.venv/bin/pytest -q | tail -5` → rapid+integration+e2e verdes.
- [ ] **Step 3: SessionStart** — `bash .claude/hooks/session-start-orientation.sh "$PWD/.claude/memory"` → injeta handoff + índice + linha do Mandamento #7, exit 0.
- [ ] **Step 4: recall de 1º turno** — `.claude/bin/mem find "o que falta pendente aberto backlog"` → surfa os temas ativos espelhados.
- [ ] **Step 5:** sem commit (verificação). Reportar counts das 3 lanes.

---

## Self-Review (do autor)

- **Cobertura da spec:** F1→Task1, F2→Task2, F3→Task3, sincronia→Task4, gates §8→Task5. Item upstream §7 fica como candidato mem-report (fora do plano, por design).
- **Placeholders:** nenhum — todos os textos/comandos são literais.
- **Consistência:** `reference` usado em todas as tasks de mem; contagem 6→7 só nos 3 sites reais; testes nomeados existem (verificados no scout).

## Cross-refs

- Spec: `docs/superpowers/specs/2026-07-01-mem-first-context-source-design.md`.
- Backlog canônico: `docs/design/04-pending.md`.
- Trabalho pausado: `docs/superpowers/specs/2026-06-30-runtime-visual-verification-design.md`.
