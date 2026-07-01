# mem como fonte primária de contexto — Design

> **Status:** spec de decisão de arquitetura de informação. Deliverable do
> brainstorm. Voz: mentor calmo.
> **Origem:** remediação de um gap deixado pela integração mem (Fase 0/1) —
> NÃO é feature nova. Ver §1.

---

## 1. Origem — gap da integração, não feature nova

Rastreável no git: a orientação mem-first no `CLAUDE.md` ("Consulte
`.claude/bin/mem find` ANTES de: despachar, revisar, decidir…") entrou no commit
`cef24d5` ("enxugar CLAUDE.md + rules pra Tier-0 + índice mem", Fase 0 T6). Foi
**hand-authored** na campanha de dogfooding — **não** gerada pelo `mem init`. A
ferramenta `mem` provê armazenamento + query (`engine/integrations/mem.py` é um
boundary de call: `mem_find`/`mem_get`/`mem_session`); ela não autora — e não
deveria — a governança (mandamentos) de um projeto consumidor. Isso é do
consumidor.

Logo: **não é bug do `mem` tool.** É gap na integração/dogfood da Fase 0/1 —
quando fizemos o mem virar substrato, codificamos o mem-first como **ponteiro
soft** ("consulte antes destas ações") e paramos antes de elevá-lo a Mandamento
Tier-0 cobrindo *toda* recuperação de contexto passado. A impressão digital do
gap: a disciplina "mem-first em perguntas de estado" ficou aprendida
empiricamente e estacionada na camada soft (auto-memória do Claude Code) em vez
da camada hard (mandamento). Sintoma observado: recall de 1º turno raso — a regra
existia sem força de mandamento, e o conteúdo tópico não estava espelhado no mem.

---

## 2. O problema concreto

- **Split-brain de recall.** O detalhe tópico do backlog (o que é o smoke, os
  P0/P1, os follow-ons) vive só nos docs (`04-pending.md`, specs, reports); não
  está no mem. `mem find` de 1º turno traz a camada de disciplina de processo,
  não a enciclopédia do design.
- **mem-first é soft.** Hoje é nota de feedback + ponteiro de rule, não
  mandamento. Não há invariante always-on de "mem é a primeira parada".

O objetivo: mem passa a ser a **primeira fonte de contexto passado, sempre** —
sem deletar os docs, que ganham papel claro.

---

## 3. Decisões travadas (do brainstorm)

1. **Profundidade — Caminho 1 (enforcement + espelhar abertos).** NÃO dissolve os
   docs; NÃO toca a Decisão 20 (`persistence = SQLite + arquivos: config, memory,
   docs`). Docs preservados como índice enumerável + registro de design diffável.
2. **Sincronia — doc canônico + notas dos temas ativos.** `04-pending.md` segue
   a fonte enumerável canônica; o mem carrega notas `reference` só dos TEMAS
   ABERTOS ATIVOS (um punhado). Fechar um item no doc → arquivar/supersede a nota
   `reference` correspondente NO MESMO commit (matriz doc-sync).
3. **Enforcement — Mandamento Tier-0 + SessionStart, sem hook por-prompt.**
   Eleva mem-first a Mandamento always-on + mantém a injeção que o SessionStart
   já faz. Sem hook `UserPromptSubmit` (sem custo de token/ruído por turno).
4. **Sequência — mem-first primeiro, depois N2 (smoke).** O brainstorm de N2 fica
   pausado no Caminho A (consumidor declara o comando de smoke), a confirmar
   depois desta campanha.

**Por que Caminho 1 e não dissolução total:** mem e `04-pending` são estruturas
de dados diferentes. mem `find` rankeia por SCORE (não recência) e pina por
`recall_count` → é otimizado pra *recall* (surfar o relevante), não pra
*enumeração* (listar exaustivamente o aberto). Dissolver o backlog no mem perderia
a enumeração determinística, o registro de design diffável em PR, e o fallback de
bootstrap do SessionStart — além de exigir Revisita da Decisão 20.

---

## 4. As três frentes

### Frente 1 — Mandamento #7 (Tier-0, CLAUDE.md)

Novo mandamento na seção "Os 6 mandamentos" (que passa a 7), texto na voz do repo,
sentido:

> **mem é a primeira fonte de contexto passado.** Antes de responder perguntas de
> estado / status / "o que falta" / histórico, e antes de despachar subagente ou
> decidir algo com precedente, consulte `.claude/bin/mem find "<tema>"` — em
> paralelo com Read/git, no PRIMEIRO turno, não depois. O mem carrega a disciplina
> de processo, o handoff de estado e os temas abertos ativos. Os docs
> (`04-pending.md`, specs) enumeram o detalhe canônico; o mem surfa o relevante.

Edit em `CLAUDE.md` = load-bearing → segue o ritual **additive → enxugue →
gate-antes-de-merge**. NÃO é Revisita de Decisão (mandamentos ≠ Decisões locked).
Eleva a nota `feedback_mem_first_on_state_questions` da auto-memória à camada hard.

### Frente 2 — Reforço no SessionStart

Mínimo: o `.claude/hooks/session-start-orientation.sh` já injeta a nota `session`
do mem + o índice high-value. O reforço é o texto injetado **nomear
explicitamente o Mandamento #7** (mem-first), do mesmo jeito que já nomeia o
Mandamento 0. Uma linha. Verificar que a injeção continua funcionando após a
mudança.

### Frente 3 — Espelhar abertos (conteúdo)

Escrever notas `reference` no mem (`.claude/bin/mem add`) só pros temas ABERTOS
ATIVOS do `04-pending` (mem não tem type `project`; `reference` é o tipo de
ponteiro pro doc canônico). Levantamento inicial (~6, reconferir na implementação):

- Tema 6 Nível 2 (smoke) — próximo trabalho, spec escrita
- Tema 6 Nível 3 (screenshot) — deferido pós-piloto de N2
- Follow-on MI-02 (gate de progresso ignora `FORGE_FORCE_COLOR`, usar isatty puro)
- Follow-on I-02 (dedup helper de teste quando 3º gate nativo chegar)
- W-VENDOR M-001 (reconfigure/upgrade não re-vendoriza mem)
- `_KNOWLEDGE_KINDS` cobre só 3 dos kinds do retrospective
- W-MIGRATE (deferido até brownfield real)

NÃO espelhar: histórico fechado, deferidos especulativos profundos (ex.: os 6
non-goals graph-ia).

**Disciplina de sincronia (nova entrada na matriz doc-sync):** fechar um item no
`04-pending` → arquivar/supersede a nota `reference` correspondente no mesmo commit.
Registrar essa regra no mem (nota da matriz doc-sync) e no ponteiro de
`.claude/rules/doc-sync.md`.

---

## 5. Non-goals

- **Não deletar** `04-pending.md` nem `08-session-handoff.md`.
- **Não tocar a Decisão 20** (docs seguem substrato de primeira classe).
- **Não** adicionar hook `UserPromptSubmit` por-prompt.
- **Não** espelhar histórico fechado nem deferidos especulativos.
- **Não** é trabalho de `engine/` — é governança (CLAUDE.md/hooks/rules) + conteúdo mem.
- **Não** resolver o item upstream do `mem init` aqui (ver §7).

---

## 6. Escopo de arquivos

- `CLAUDE.md` — Mandamento #7 + eventual ajuste na seção "Memória persistente".
- `.claude/hooks/session-start-orientation.sh` — nomear o Mandamento #7 (1 linha).
- `.claude/rules/` — ponteiro/índice (doc-sync + README index).
- `.claude/bin/mem add` — ~6 notas `reference` (temas abertos ativos).
- `CHANGELOG.md` — entrada do Mandamento #7 + frente de conteúdo.
- (esta spec.)

**Não toca:** `engine/`, `04-pending.md` (não deletado), `08-session-handoff.md`.

---

## 7. Item upstream separado

Pergunta upstream legítima, FORA do escopo desta campanha: *o `mem init` (a
ferramenta `inRadar/mem`) deveria oferecer um bloco de guidance mem-first
recomendado pro consumidor scaffoldar?* Candidato a `mem-report` pra
`inRadar/mem`. Irrelevante pro feature-forge em si (nosso SessionStart já injeta à
mão), mas registrado pra não se perder.

---

## 8. Gates de "pronto"

- Ritual additive → enxugue → gate-antes-de-merge no self-edit do CLAUDE.md.
- `.venv/bin/pytest` verde (lane completa antes do PR).
- plan-auditor 2 rodadas sobre o plano.
- Review zero-tolerância (11 dimensões) + cross-AI.
- Verificação de que o SessionStart ainda injeta o handoff + índice corretamente.
- Notas `reference` recuperáveis por `mem find` de 1º turno (recall dos temas ativos).

---

## Cross-refs

- Decisão 20 (persistence: SQLite + arquivos): `docs/design/01-decisions.md`.
- Backlog canônico: `docs/design/04-pending.md`.
- Integração mem (Fase 1): `docs/superpowers/specs/2026-06-25-mem-integration-design.md`.
- SessionStart: `.claude/hooks/session-start-orientation.sh`.
- Trabalho pausado (N2 smoke): `docs/superpowers/specs/2026-06-30-runtime-visual-verification-design.md`.
