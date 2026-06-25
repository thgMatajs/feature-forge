# Fase 0 — forge dogfoods mem · Implementation Plan

> **For agentic workers:** este plano segue o terminal-state do
> `superpowers:writing-plans`. A execução é despachada via subagentes
> (Mandamento 0 — o orquestrador nunca edita direto). **REQUIRED SUB-SKILL:
> `subagent-driven-development`** — toda task de código vai pra `gsd-executor`
> com TDD estrito; tasks de migração de doc/classificação vão pra
> `gsd-executor` com deliverable verificável (comandos `mem` + greps), nunca
> pytest.

> **Voz:** mentor calmo em todo artefato gerado (notas mem, índice Tier-0,
> mensagens 3-caminhos). Sem voz corporativa, sem emoji decorativo.

---

## Goal

O próprio repo `feature-forge` adota o `mem` pra gerenciar o conhecimento
DELE: o conhecimento rico (decisões/disciplinas/pending/handoff/learnings +
detalhe das rules) vira notas mem recuperáveis sob-demanda, e os docs
operacionais sempre-on (`CLAUDE.md` + `.claude/rules/**`) são enxugados pra
um núcleo Tier-0 lean + índice do mem — SEM perder informação e SEM enfraquecer
os gates que enforçam o Mandamento 0.

---

## Architecture

O `mem` (script único, v0.8.1, stdlib-pura) é embarcado como asset pinado no
repo forge (`engine/assets/mem/mem`), vendorizado pra `.claude/bin/mem`, e
invocado por subprocess via uma fronteira shell enxuta
(`engine/integrations/mem.py:mem_call`) — mesmo padrão de
`dispatch_native_tool`, nunca `import mem`. O conhecimento do forge é
CLASSIFICADO em Tier-0 (invariante, fica injetado lean) vs. Tier-1 (referência
→ vira nota mem); a divisão é PROPOSTA ao humano (3-caminhos) ANTES de qualquer
`mem add` + enxugue. A migração ADICIONA ao mem; o enxugue do injetado é um
passo SEPARADO e posterior, só após o conteúdo estar comprovadamente
recuperável via `mem find`/`get`. Os arquivos canônicos `docs/design/*` NÃO são
deletados — deixam de ser injetados sempre, passam a ser consultáveis.

---

## Tech Stack

- **mem** — `/Users/thg.inchurch/Documents/mem/mem` (script único Python3
  stdlib, v0.8.1, schema v4). Invocação canônica: `python3 <mem> <subcmd>` no
  dev clone; `.claude/bin/mem <subcmd>` vendorizado. **O flag global `--json`
  precede o subcomando** (`mem --json doctor`, NÃO `mem doctor --json` — este
  último dá `unrecognized arguments`). Exit codes: `0` ok · `1` uso · `2`
  não-encontrado · `3` interno.
- **Python** — `engine/integrations/mem.py` (novo módulo, fronteira shell);
  reusa a espinha de `validators/_gate_infra.py:dispatch_native_tool`
  (`check_tool_available`/subprocess+timeout/captura stdout+exit-code/fail-soft)
  sem forçar o encaixe inteiro (multi-file/config-template não se aplicam).
- **pytest** — `.venv/bin/pytest` (canonical — tem json5 + deps; system pytest
  gera false-fail). Markers: unit (sem marker), `integration`, `e2e`.
- **git** — `/usr/bin/git` em todos os comandos. Branch única
  `feat/mem-integration`.
- **Gate de aceite** — `.claude/rules/SMOKE-CHECKLIST.md` (5 checks) +
  `.claude/hooks/pre-commit-feature-forge.sh` (hard-block Mandamento #1) +
  observação de comportamento do Mandamento 0. NÃO são unit tests.

---

## Global Constraints

Copiados verbatim das premissas do spec (§Fronteira, §Fase 0, §Decisões
resolvidas). Inegociáveis pra toda task abaixo:

- **G-VENDOR — vendor + shell, nunca import.** O forge invoca `.claude/bin/mem`
  por subprocess, exatamente como `dispatch_native_tool` invoca detekt/gradle.
  NUNCA `import mem`. O `mem` permanece um arquivo opaco, pinado por versão. O
  asset vive em `engine/assets/mem/mem`; o init/vendor copia pra
  `.claude/bin/mem` (chmod 755). Sem download via `gh` no fluxo.
- **G1/G2 — proposto, nunca silencioso.** A divisão Tier-0/Tier-1 é apresentada
  ao humano (3-caminhos: aceitar / ajustar / pular) ANTES de qualquer `mem add`
  + enxugue. O `.claude/rules/` humano NUNCA é trucidado sem aprovação.
- **"→ mem não deleta o arquivo canônico."** Migrar pro mem é ADITIVO. Os docs
  `docs/design/*` são fonte de verdade load-bearing e alguns têm enforcement
  acoplado (hard-block de `01-decisions.md`, SessionStart de
  `08-session-handoff.md`). O que muda: deixam de ser injetados sempre via
  CLAUDE.md/rules e passam a ser consultáveis via mem. O enxugue é do CLAUDE.md
  + `.claude/rules/` injetado, e é SEPARADO/POSTERIOR à migração.
- **Branch única `feat/mem-integration`.** Todo o trabalho acumula nela; um PR
  ao final. Sem worktree por task. NÃO criar branch nova por task.
- **Gate de aceite ANTES de merge.** Os 5 smoke checks (foco #5 — dispatch do
  Mandamento 0) + hard-block de `01-decisions.md` intacto + rules acessíveis
  via `mem find`/`get` + zero info perdida DEVEM passar na branch antes de
  qualquer merge. A task final VALIDA e REPORTA — NÃO faz merge.
- **Sequência reversível.** Migração (aditiva) precede enxugue (destrutivo do
  injetado). Se o gate falhar, o enxugue é revertível por `git checkout` dos
  arquivos injetados, com o conteúdo já preservado no mem.

---

## Task 1: Embarcar o asset mem pinado + fronteira shell `mem_call` (TDD)

Estabelece a fundação técnica: o asset pinado no repo + o wrapper de subprocess
que todas as tasks seguintes usam pra falar com o mem. Código → TDD estrito.

**Files**
- Create: `engine/assets/mem/mem` (cópia byte-a-byte de
  `/Users/thg.inchurch/Documents/mem/mem`, v0.8.1, chmod 755)
- Create: `engine/assets/mem/VERSION` (conteúdo: `0.8.1`)
- Create: `engine/integrations/__init__.py` (vazio — pacote)
- Create: `engine/integrations/mem.py` (`mem_call`, `MemResult`,
  `MEM_PINNED_VERSION = "0.8.1"`, resolução de binário)
- Create: `tests/integrations/__init__.py` (vazio)
- Create: `tests/integrations/test_mem_call.py` (TDD — testes primeiro)

**Interfaces**
- Produces: `engine.integrations.mem.mem_call(project_root: Path,
  subcmd_args: list[str], *, json: bool = True, timeout: int = 10) ->
  MemResult` e `MemResult(found: bool, exit_code: int, stdout: str, stderr:
  str)`. Consumida por Tasks 4, 5, 6 e pela task final.
- Produces: `engine.integrations.mem.MEM_PINNED_VERSION` (pin do forge).
- Consumes: a espinha de `validators/_gate_infra.py` (`check_tool_available`
  via `shutil.which`; padrão `subprocess.run(timeout)` com captura).

**Steps**
- [ ] Ler `validators/_gate_infra.py` (`check_tool_available`,
  `dispatch_native_tool`) pra reusar a espinha de subprocess sem copiar
  (Mandamento #3 — `forge graph` Q11 antes de criar helper novo).
- [ ] Escrever `tests/integrations/test_mem_call.py` com os casos FALHANDO
  primeiro (módulo ainda não existe → ImportError = vermelho legítimo):
  - `test_resolve_prefers_vendored`: com `.claude/bin/mem` presente (stub),
    `mem_call` resolve pra ele antes de `shutil.which`.
  - `test_resolve_falls_back_to_which`: sem vendored, usa `shutil.which("mem")`.
  - `test_not_found_returns_found_false`: sem vendored e sem PATH →
    `MemResult(found=False)`, NÃO crasha.
  - `test_json_flag_precedes_subcommand`: o argv montado coloca `--json` ANTES
    do subcomando (`["<bin>", "--json", "doctor"]`), nunca depois (regression
    do bug `unrecognized arguments: --json`).
  - `test_exit_0_parses_stdout`: monkeypatch `subprocess.run` retornando exit 0
    + JSON canônico → `MemResult(found=True, exit_code=0, stdout=<json>)`.
  - `test_exit_2_not_found_mapped`: exit 2 → `MemResult(exit_code=2)`
    (not-found tratado, sem exceção).
  - `test_timeout_fail_soft`: `subprocess.TimeoutExpired` → `MemResult` com
    sinal de timeout, sem propagar exceção.
  - `test_env_scrubbed`: o env do subprocess não herda
    `CLAUDECODE`/`OPENCODE_*`/`CODEX`/`CURSOR_*` (lição operacional — reusar o
    padrão de scrub já presente nos testes de subprocess do forge).
- [ ] Rodar `.venv/bin/pytest tests/integrations/test_mem_call.py -x` →
  confirmar FAIL (vermelho).
- [ ] Implementar `engine/integrations/mem.py` minimal pra passar: resolução
  `<project_root>/.claude/bin/mem` → `shutil.which("mem")` → `found=False`;
  argv com `--json` antes do subcomando quando `json=True`; `subprocess.run`
  com timeout + env scrub; mapeamento de exit-code → `MemResult`; fail-soft em
  timeout/erro.
- [ ] Copiar o asset: `gsd-executor` copia
  `/Users/thg.inchurch/Documents/mem/mem` → `engine/assets/mem/mem`, chmod 755,
  cria `engine/assets/mem/VERSION` com `0.8.1`. Confirmar
  `python3 engine/assets/mem/mem --version` imprime `mem 0.8.1`.
- [ ] Rodar `.venv/bin/pytest tests/integrations/test_mem_call.py -x` →
  confirmar PASS (verde).
- [ ] Rodar suíte rápida `.venv/bin/pytest -m "not integration and not e2e" -q
  | tail -1` → confirmar 0 falhas + count ≥ baseline.
- [ ] Commit atômico: `feat(integrations): mem_call shell boundary + pinned
  asset (Fase 0 T1)`.

**Deliverable verificável**
- `engine/assets/mem/mem --version` → `mem 0.8.1`; `mem_call` resolve, parseia
  `--json`, e degrada sem crash quando o binário falta — provado por
  `test_mem_call.py` verde.

---

## Task 2: Vendorizar o mem no repo forge + scaffold `.claude/memory/` + gitignore

Coloca o mem rodando DENTRO do repo forge (o dogfood exige o substrato vivo
aqui). Vendor + scaffold são operações de filesystem idempotentes; a
verificação é por comandos `mem` reais, não pytest.

**Files**
- Create: `.claude/bin/mem` (cópia vendorizada de `engine/assets/mem/mem`,
  chmod 755)
- Modify: `.gitignore` (adicionar `.claude/memory/mem.db*`; preservar as linhas
  existentes `41:.claude/memory/L1/*` e `42:!.claude/memory/L1/archived/` —
  o corte do L1 state-machine é Fase 1, NÃO toca aqui)
- Create (via `mem init`): `.claude/memory/` (scaffold do layout mem) +
  upsert do bloco rule-índice no índice do mem (o `mem init` cria o que
  precisar; NÃO sobrescrever conteúdo humano existente)

**Interfaces**
- Consumes: `engine/assets/mem/mem` (asset da Task 1).
- Produces: `.claude/bin/mem` operacional + `.claude/memory/` scaffoldado.

**Steps**
- [ ] `gsd-executor`: copiar `engine/assets/mem/mem` → `.claude/bin/mem`,
  chmod 755. Confirmar `.claude/bin/mem --version` → `mem 0.8.1`.
- [ ] Rodar `.claude/bin/mem init` (scaffold idempotente:
  cria `.claude/memory/`, adiciona gitignore `mem.db*`, instala skills
  `mem-resume`/`-consolidate`/`-report`). Capturar o output pra revisar o que
  foi criado.
- [ ] Confirmar via `git status --short` que `.claude/memory/mem.db` NÃO
  aparece como untracked (gitignored); e que `.gitignore` tem a linha
  `.claude/memory/mem.db*`. Se o `mem init` não a adicionou, adicionar à mão.
- [ ] Confirmar `.claude/bin/mem --json doctor` retorna os 4 checks
  (`project-root`/`author`/`schema`/`version`) todos `ok` (schema "not yet
  built" é `ok`, não erro).
- [ ] Confirmar `.claude/bin/mem --json stats` retorna `{"total": 0, ...}`
  (acervo vazio, índice saudável).
- [ ] Doc-sync mínimo desta task: registrar em `CHANGELOG.md` `## [Unreleased]`
  `### Added` a entrada "mem vendorizado em `.claude/bin/mem` (asset pinado
  v0.8.1) + scaffold `.claude/memory/` (Fase 0 dogfood)".
- [ ] Commit atômico: `chore(mem): vendor mem 0.8.1 + scaffold memory (Fase 0
  T2)`.

**Deliverable verificável**
- `.claude/bin/mem --json doctor` → todos `ok`; `.claude/bin/mem --json stats`
  → `total: 0`; `git status` confirma `mem.db` gitignored e as linhas L1 do
  gitignore preservadas.

---

## Task 3: Classificar Tier-0 vs Tier-1 + PROPOR a divisão ao humano (3-caminhos)

O passo de governança (G1/G2). Produz o mapa de classificação por arquivo
concreto e o APRESENTA ao humano. NENHUM `mem add` e NENHUM enxugue acontecem
aqui — esta task é a aprovação. É o gate que impede trucidar rule humana em
silêncio.

**Files**
- Create: `.planning/mem-fase0/tier-classification.md` (scratch — o mapa
  proposto, por arquivo concreto; consumido pela apresentação 3-caminhos)
- (NENHUM arquivo canônico tocado nesta task)

**Steps**
- [ ] Ler e contar o conteúdo real (scout, não inventar) de cada fonte:
  - `CLAUDE.md` (263 linhas) — Mandamento 0 + os 6 mandamentos (enunciado) +
    workflow-por-verbo + superpowers map + anatomia rápida + comandos +
    codebase graph + pointers + bootstrap.
  - `.claude/rules/orchestrator-persona.md` (244) ·
    `subagent-workflow.md` (139) · `decisions.md` (86) · `disciplines.md` (97)
    · `doc-sync.md` (129) · `testing.md` (180) · `scope.md` (95) ·
    `reuse.md` (147) · `superpowers.md` (69) · `plan-auditor.md` (425) ·
    `project-anatomy.md` (98) · `SMOKE-CHECKLIST.md` (161) · `README.md` (43).
- [ ] Classificar cada fragmento por arquivo, usando o mapeamento do spec
  (§Mapeamento Tier-0 vs →mem) como base e EXPANDINDO por arquivo:
  - **Tier-0 (fica injetado, lean)** — o invariante que NÃO pode ser
    sob-demanda sem quebrar enforcement: Mandamento 0 (regra absoluta +
    whitelist de ferramentas), os 6 mandamentos (enunciado de 1 linha cada),
    o workflow-loop canônico essencial, e os ponteiros pro mem. Os arquivos com
    enforcement acoplado que DEVEM continuar legíveis pelo SessionStart/hooks
    ficam citados (não enxugados nesta task).
    Destino: núcleo lean de `CLAUDE.md` + índice `RULE_INDEX` (~30 linhas) que
    ensina a consultar o mem.
  - **Tier-1 (→ mem, sob-demanda)** — detalhe rico recuperável por tema:
    - `orchestrator-persona.md`, `subagent-workflow.md` → `reference` (detalhe
      de despacho/context-pack/trust-but-verify).
    - `decisions.md`, `disciplines.md`, `doc-sync.md`, `testing.md`,
      `scope.md`, `reuse.md`, `superpowers.md`, `plan-auditor.md` →
      `reference`/`feedback` (prescritivo→feedback; descritivo→reference).
    - `project-anatomy.md`, `README.md`, `SMOKE-CHECKLIST.md` → `reference`.
  - **Fontes `docs/design/*` (índice consultável, arquivo CANÔNICO permanece):**
    - `docs/design/01-decisions.md` → `decision` (uma nota por decisão); arquivo
      permanece (hard-block depende dele).
    - `docs/design/07-discipline.md` → `reference`; arquivo permanece.
    - `docs/design/04-pending.md` → `reference`; arquivo permanece.
    - `docs/design/08-session-handoff.md` → `mem session` (handoff curado);
      arquivo permanece (SessionStart depende dele).
  - **Learnings da auto-memory do autor** (feedback recorrentes em
    `~/.claude/projects/.../memory/MEMORY.md`) → `feedback`.
- [ ] Pra cada fragmento Tier-1, registrar no mapa: arquivo-fonte, `--type`
  proposto, título de 1 linha, tags derivadas, e a justificativa
  prescritivo-vs-descritivo (default conservador: prescritivo → `feedback`).
- [ ] Escrever `.planning/mem-fase0/tier-classification.md` com o mapa completo
  + um "diff de cobertura" antecipado (cada bloco do canônico mapeia pra ≥1
  nota OU permanece em Tier-0 — zero órfãos).
- [ ] **PROPOR ao humano via 3-caminhos** (G1/G2): apresentar o mapa e pedir
  veredito com os três caminhos canônicos:
  - ✅ aceitar a classificação como está
  - 🔧 ajustar (humano move fragmentos entre Tiers)
  - ⏭️ pular (não migrar este fragmento)
- [ ] Registrar o veredito do humano no mapa (a versão aprovada é o input das
  Tasks 4–6). NENHUMA escrita em mem/rules até aprovação.

**Deliverable verificável**
- `.planning/mem-fase0/tier-classification.md` existe, cobre todos os 14
  arquivos + as 4 fontes `docs/design/*` + learnings, com zero fragmento órfão;
  o humano deu veredito 3-caminhos ANTES de qualquer migração. (Gate G1/G2
  satisfeito.)

---

## Task 4: Migrar o conteúdo Tier-1 das rules pro mem (aditivo, sem enxugar)

Executa a migração APROVADA na Task 3. Cada fragmento Tier-1 das
`.claude/rules/**` + `CLAUDE.md` vira nota mem via `mem_call`/`.claude/bin/mem
add`. ADITIVO — nenhum arquivo canônico é enxugado aqui. A verificação é
recuperabilidade via `mem find`/`get`, não pytest.

**Files**
- Modify (append-only ao acervo): `.claude/memory/<autor>.jsonl` (escrito pelo
  `mem add`; NÃO editar à mão)
- (NENHUM `.claude/rules/*.md` nem `CLAUDE.md` enxugado nesta task)

**Interfaces**
- Consumes: o mapa aprovado de `.planning/mem-fase0/tier-classification.md`
  (Task 3); `.claude/bin/mem` (Task 2).

**Steps**
- [ ] Pra cada fragmento Tier-1 das rules aprovado, emitir
  `.claude/bin/mem add --type <T> -t "<título>" --tags <tags derivadas>
  --source "dogfood:rules:<arquivo>" "<corpo markdown do fragmento>"`. Voz
  mentor calmo no título e corpo. (Usar `add` direto — NÃO `mem import`, que é
  one-shot sem dedup e só entende frontmatter; o conteúdo das rules não é
  markdown-frontmatter.)
- [ ] Pra `orchestrator-persona.md` + `subagent-workflow.md`: notas
  `reference` (detalhe de despacho). Pra `decisions.md`/`disciplines.md`/
  `doc-sync.md`/`testing.md`/`scope.md`/`reuse.md`/`superpowers.md`/
  `plan-auditor.md`: `reference` (descritivo) ou `feedback` (prescritivo) por
  fragmento conforme o mapa. Pra `project-anatomy.md`/`README.md`/
  `SMOKE-CHECKLIST.md`: `reference`.
- [ ] Pra o conteúdo Tier-1 do `CLAUDE.md` que sai do núcleo (superpowers map
  detalhado, anatomia rápida, comandos úteis, codebase graph howto): notas
  `reference` com `--source "dogfood:claude-md:<seção>"`.
- [ ] Após cada lote, rodar `.claude/bin/mem --json stats` e confirmar o `total`
  subir conforme esperado (sem near-dup warnings inesperados; se houver, anotar
  e revisar — não silenciar).
- [ ] **Verificação de recuperabilidade por tema** (o coração do dogfood):
  pra cada arquivo migrado, rodar pelo menos um `mem find "<tema do arquivo>"`
  e confirmar que a nota correspondente aparece no top-k; depois `mem get <id>`
  e confirmar que o corpo bate com o fragmento canônico. Exemplos:
  - `.claude/bin/mem find "despacho subagente context-pack"` → nota de
    `subagent-workflow.md`.
  - `.claude/bin/mem find "reuso forge graph antes de criar helper"` → nota de
    `reuse.md`.
  - `.claude/bin/mem find "TDD pytest gates verde antes de pronto"` → nota de
    `testing.md`.
  - `.claude/bin/mem find "12 checks auditoria de plano"` → nota de
    `plan-auditor.md`.
- [ ] Registrar em `.planning/mem-fase0/coverage-rules.md` o mapa
  arquivo→note-id→query-que-recupera (prova de cobertura zero-perda das rules).
- [ ] Commit atômico: `chore(mem): migrar Tier-1 das rules pro acervo (Fase 0
  T4, aditivo)`. (O `.claude/memory/<autor>.jsonl` entra no diff — é a fonte
  commitada.)

**Deliverable verificável**
- Cada `.claude/rules/*.md` Tier-1 + cada seção Tier-1 do `CLAUDE.md` é
  recuperável: o `mem find "<tema>"` correspondente devolve a nota e
  `mem get <id>` mostra o corpo equivalente. `.planning/mem-fase0/
  coverage-rules.md` lista arquivo→id→query pra todos. Nenhuma rule canônica
  foi enxugada.

---

## Task 5: Migrar decisões/disciplinas/pending/handoff/learnings pro mem (aditivo)

Migra as 4 fontes `docs/design/*` aprovadas + os learnings da auto-memory.
ADITIVO — os arquivos canônicos `docs/design/*` PERMANECEM intactos (são fonte
de verdade load-bearing com enforcement acoplado). A verificação é
recuperabilidade + confirmação explícita de que os canônicos não mudaram.

**Files**
- Modify (append-only ao acervo): `.claude/memory/<autor>.jsonl` (via `mem add`/
  `mem session`)
- (NENHUM `docs/design/*` tocado — confirmar via `git status`)

**Interfaces**
- Consumes: o mapa aprovado (Task 3); `.claude/bin/mem` (Task 2);
  `docs/design/01-decisions.md`, `07-discipline.md`, `04-pending.md`,
  `08-session-handoff.md` (LEITURA apenas).

**Steps**
- [ ] **Decisões** (`docs/design/01-decisions.md`): pra cada decisão (27 locked
  + 7 direcionais), emitir `.claude/bin/mem add --type decision -t
  "<decisão N: enunciado>" --tags decision,forge --source
  "dogfood:docs:01-decisions:N" "<rationale + consequência se quebrar>"`.
  Importance maior (4–5) pras 8 load-bearing.
- [ ] **Disciplinas** (`docs/design/07-discipline.md`): notas `reference` por
  disciplina (1–6) com `--source "dogfood:docs:07-discipline:N"`.
- [ ] **Pending/gaps** (`docs/design/04-pending.md`): notas `reference` por gap
  aberto com `--source "dogfood:docs:04-pending:<gap>"`.
- [ ] **Handoff** (`docs/design/08-session-handoff.md`): emitir
  `.claude/bin/mem session "<estado curado: v1.5.0 + próximos passos +
  conhecidos limites>"` (captura `git_meta` automático). O arquivo permanece
  pro SessionStart.
- [ ] **Learnings** (auto-memory do autor,
  `~/.claude/projects/-Users-thg-inchurch-Documents-feature-forge/memory/
  MEMORY.md` + os arquivos `feedback_*.md` linkados): pra cada feedback
  recorrente, emitir `.claude/bin/mem add --type feedback -t "<lição>" --tags
  <derivadas> --source "dogfood:auto-memory:<slug>" "<corpo + porquê>"`.
  Exemplos do acervo: branch-per-implementation, reuse-first-in-planning,
  zero-tolerance-code-review, .venv-pytest-canonical, env-scrub.
- [ ] **Verificação de recuperabilidade:**
  - `.claude/bin/mem find "persistência sqlite arquivos" --type decision` →
    Decisão 20.
  - `.claude/bin/mem find "zero runtime dep skill" --type decision` →
    Decisão 22.
  - `.claude/bin/mem find "3 caminhos gate resolution" --type reference` →
    disciplina 1.
  - `.claude/bin/mem find "branch dedicada antes de impl" --type feedback` →
    learning.
- [ ] **Confirmar canônicos intactos:** `git status --short docs/design/` →
  vazio (nenhum `docs/design/*` modificado). `git diff --stat
  docs/design/01-decisions.md` → sem mudança.
- [ ] Registrar em `.planning/mem-fase0/coverage-docs.md` o mapa
  fonte→note-id→query (prova de cobertura).
- [ ] Doc-sync: anotar em `CHANGELOG.md` `### Added` "decisões/disciplinas/
  pending/handoff/learnings espelhados no acervo mem (aditivo; canônicos
  preservados) — Fase 0 dogfood".
- [ ] Commit atômico: `chore(mem): espelhar decisões/disciplinas/handoff/
  learnings no acervo (Fase 0 T5, aditivo)`.

**Deliverable verificável**
- Decisões 20 e 22 (e as demais), as 6 disciplinas, os gaps de pending, o
  handoff e os learnings-chave são recuperáveis via `mem find`/`get`;
  `git status docs/design/` está limpo (canônicos não tocados);
  `.planning/mem-fase0/coverage-docs.md` lista fonte→id→query.

---

## Task 6: Enxugar o núcleo injetado (CLAUDE.md + rules) pra Tier-0 + índice mem

O passo DESTRUTIVO-do-injetado, e SÓ AGORA — após o conteúdo estar
comprovadamente recuperável (Tasks 4–5). Enxuga `CLAUDE.md` pro núcleo Tier-0 +
escreve o `RULE_INDEX` (~30 linhas) que ensina o agente a consultar o mem;
reduz as `.claude/rules/**` Tier-1 a ponteiros. Reversível por `git checkout`
(conteúdo já no mem). Verificação: o invariante permanece verbatim + zero perda.

**Files**
- Modify: `CLAUDE.md` (enxugar pro núcleo Tier-0 aprovado: Mandamento 0
  verbatim + 6 mandamentos enunciado + workflow-loop essencial + índice mem +
  ponteiros; o detalhe Tier-1 vira ponteiro pro `mem find`)
- Modify: `.claude/rules/orchestrator-persona.md`, `subagent-workflow.md`,
  `decisions.md`, `disciplines.md`, `doc-sync.md`, `testing.md`, `scope.md`,
  `reuse.md`, `superpowers.md`, `plan-auditor.md`, `project-anatomy.md`,
  `SMOKE-CHECKLIST.md`, `README.md` (reduzir cada um a um ponteiro lean:
  "detalhe consultável via `.claude/bin/mem find \"<tema>\"`" + manter o que é
  invariante de enforcement)
- Create: o bloco `RULE_INDEX` (~30 linhas, padrão do mem) — emitido em
  `CLAUDE.md` ou no índice que o SessionStart lê

**Interfaces**
- Consumes: o veredito 3-caminhos (Task 3); a cobertura provada (Tasks 4–5).

**Steps**
- [ ] **Pré-condição (gate interno):** confirmar que
  `.planning/mem-fase0/coverage-rules.md` + `coverage-docs.md` existem e
  cobrem TODO fragmento que será enxugado. Se algum fragmento a enxugar não tem
  nota recuperável correspondente → PARAR (3-caminhos ao humano), NÃO enxugar.
- [ ] Enxugar `CLAUDE.md` pro núcleo Tier-0 aprovado. **Manter VERBATIM**: o
  Mandamento 0 (regra absoluta + whitelist de ferramentas legítimas + override
  do usuário), o enunciado dos 6 mandamentos, e o workflow-loop canônico.
  Substituir as seções de detalhe (superpowers map expandido, anatomia,
  comandos, graph howto) por ponteiros `mem find`.
- [ ] Escrever o `RULE_INDEX` (~30 linhas): "Este repo tem memória persistente
  via `.claude/bin/mem`. Consulte `mem find <tema>` antes de despacho,
  review, decisão, ou ao tocar um tema com convenção. Grave em correções,
  decisões, fim de sessão. As rules detalhadas (despacho, reuso, testing,
  doc-sync, plan-auditor, decisões) estão no acervo — recupere por tema." Voz
  mentor calmo.
- [ ] Reduzir cada `.claude/rules/*.md` Tier-1 ao ponteiro lean + invariante de
  enforcement. NÃO remover o que SessionStart/hooks leem diretamente para
  enforçar (confirmar antes via leitura dos hooks
  `.claude/hooks/session-start-orientation.sh` e
  `pre-tool-use-load-bearing.sh`).
- [ ] **Verificação de invariante (grep gates, comentário-safe):**
  - `grep -v '^#' CLAUDE.md | grep -c "NUNCA usa .Write"` ≥ 1 (Mandamento 0
    verbatim presente).
  - `grep -v '^#' CLAUDE.md | grep -c "mem find"` ≥ 1 (índice mem presente).
  - confirmar os 6 mandamentos ainda enunciados (`grep -c "### [1-6]\."` ou
    equivalente ao formato real).
- [ ] **Verificação de cobertura zero-perda:** pra cada bloco removido de um
  arquivo, confirmar (via `coverage-rules.md`/`coverage-docs.md`) que existe
  `mem find`→`mem get` que o recupera. Anexar a confirmação ao mapa.
- [ ] Doc-sync: `CHANGELOG.md` `### Changed` — "CLAUDE.md + `.claude/rules/**`
  enxugados pra Tier-0 lean + índice mem; detalhe migrado pro acervo
  (recuperável via `mem find`). Canônicos `docs/design/*` preservados." +
  incluir a **ADR-note das Decisões 20/22** verbatim do spec (§Texto da
  ADR-note) sob `### Changed` (honra, não revisita — sem tocar
  `01-decisions.md`, então o hard-block não dispara). + atualizar
  `docs/design/08-session-handoff.md` (`**Última atualização:**` + `**Estado:**`
  refletindo Fase 0).
- [ ] Commit atômico: `refactor(rules): enxugar CLAUDE.md + rules pra Tier-0 +
  índice mem (Fase 0 T6)`.

**Deliverable verificável**
- `CLAUDE.md` contém o Mandamento 0 verbatim + os 6 mandamentos + o índice
  `mem find` (grep gates passam); cada bloco enxugado tem nota recuperável
  registrada na cobertura; `docs/design/*` permanecem intactos; CHANGELOG tem a
  ADR-note das Decisões 20/22.

---

## Task 7: GATE DE ACEITE da Fase 0 — validar e reportar (NÃO faz merge)

A verificação terminal do dogfood. Roda os 5 smoke checks + confirma o
Mandamento 0 enforçado + o hard-block de `01-decisions.md` intacto + rules
acessíveis via mem + zero info perdida. Esta task SÓ valida e reporta o
veredito ao humano — NÃO faz merge, NÃO faz PR.

**Files**
- Create: `.planning/mem-fase0/acceptance-gate.md` (relatório do gate: cada
  critério → pass/fail + evidência)
- (NENHUM arquivo de produto tocado — esta task é verificação)

**Steps**
- [ ] **Critério 1 — sessão de manutenção fresca + Mandamento 0 enforçado.**
  Rodar o `SMOKE-CHECKLIST.md` check #5 (Mandamento 0 dispatch behavior):
  confirmar que, com o CLAUDE.md enxuto, o orquestrador-mantenedor PROPÕE
  dispatch de subagente em vez de editar direto. Registrar a evidência
  (o próprio fluxo de execução deste plano por subagentes já é evidência
  factual de Mandamento 0 ativo). Critério: o invariante sobreviveu ao enxugue.
- [ ] **Critério 2 — os 5 smoke checks que dependem de rules/hooks.** Rodar
  `SMOKE-CHECKLIST.md` checks #1–#5 (SessionStart injeta orientação;
  PostToolUse drift; PreToolUse load-bearing; pre-commit hard-block; Mandamento
  0 dispatch). Para os hooks com entrega inconsistente em subagent context
  (#2, documentado no checklist), usar o canal de audit confiável
  (side-effect em `.claude/state/*`) conforme a lição operacional do checklist.
  Registrar pass/fail por check.
- [ ] **Critério 3 — hard-block do Mandamento #1 intacto.** Confirmar que
  `docs/design/01-decisions.md` NÃO foi removido (`ls -la` + `git status` limpo
  pra ele) e que `.claude/hooks/pre-commit-feature-forge.sh` ainda existe e
  bloqueia edit de `01-decisions.md` sem ceremony (reproduzir o sub-cenário
  4a/4b do checklist; reverter o probe com `git reset --soft HEAD~1` +
  `git checkout`).
- [ ] **Critério 4 — rules acessíveis via mem.** Re-rodar a bateria de
  `mem find`/`mem get` das Tasks 4–5 (cobertura-rules + cobertura-docs) e
  confirmar que TODO fragmento enxugado continua recuperável. Cruzar com
  `.planning/mem-fase0/coverage-rules.md` + `coverage-docs.md` — zero órfão.
- [ ] **Critério 5 — proposto, nunca silencioso.** Confirmar que o veredito
  3-caminhos da Task 3 está registrado e precedeu todo `mem add`/enxugue
  (auditável pela ordem dos commits: T3 aprovação → T4/T5 add → T6 enxugue).
- [ ] **Critério 6 — zero info perdida (diff de cobertura final).** Pra cada
  arquivo enxugado, confirmar: conteúdo invariante permanece no Tier-0 OU
  conteúdo migrado é recuperável via mem. Nenhum bloco sumiu sem destino.
- [ ] **Suíte verde:** `.venv/bin/pytest -m "not integration and not e2e" -q |
  tail -1` → 0 falhas + count ≥ baseline; `.venv/bin/pytest
  tests/integrations/ -q` → verde.
- [ ] Escrever `.planning/mem-fase0/acceptance-gate.md` com o veredito por
  critério + evidência. Se QUALQUER critério falhar → veredito GATE-FAIL +
  3-caminhos ao humano (ajustar classificação / re-migrar / reverter enxugue);
  a Fase 0 NÃO avança pra merge.
- [ ] **Reportar ao humano** o veredito do gate. NÃO fazer merge, NÃO abrir PR
  (decisão do orquestrador no handoff).

**Deliverable verificável**
- `.planning/mem-fase0/acceptance-gate.md` com pass/fail por critério +
  evidência; os 5 smoke checks rodados; hard-block reproduzido e intacto; toda
  rule enxugada confirmada recuperável; suíte verde. Veredito (GATE-PASS ou
  GATE-FAIL) reportado ao humano sem merge.

---

## Self-Review

**Cobertura do spec Fase 0:**
- ✅ Asset pinado `engine/assets/mem/mem` + `VERSION` (Decisão #3) — Task 1.
- ✅ Fronteira shell `engine/integrations/mem.py:mem_call`/`MemResult` +
  `MEM_PINNED_VERSION` reusando a espinha de `dispatch_native_tool`, nunca
  `import mem` (Decisão #2, G-VENDOR) — Task 1, TDD estrito.
- ✅ Vendor pra `.claude/bin/mem` + scaffold `.claude/memory/` + gitignore
  `mem.db*` (§Fronteira, §Reconciliação) — Task 2. Linhas L1 do gitignore
  preservadas (corte do L1 é Fase 1, fora de escopo aqui).
- ✅ Mapeamento Tier-0 vs →mem expandido por arquivo concreto (14 rules +
  CLAUDE.md + 4 `docs/design/*` + learnings) — Task 3, com PROPOSTA 3-caminhos
  (G1/G2) antes de qualquer escrita.
- ✅ Migração ADITIVA (`mem add`/`mem session`, NÃO `mem import` cru) — Tasks
  4–5; canônicos `docs/design/*` preservados e confirmados via `git status`.
- ✅ Enxugue SEPARADO/POSTERIOR, com gate interno de recuperabilidade antes de
  remover — Task 6; ADR-note Decisões 20/22 verbatim no CHANGELOG (honra, não
  revisita; `01-decisions.md` não tocado → hard-block não dispara).
- ✅ Gate de aceite = 5 smoke checks + Mandamento 0 + hard-block intacto + mem
  recuperável + zero perda; valida e reporta, NÃO faz merge — Task 7.
- ✅ Detalhe crucial grounded: `mem --json <subcmd>` (flag global ANTES do
  subcomando) — capturado em Task 1 como regression test e usado em todas as
  invocações.

**Placeholder scan:** sem TODO/FIXME/"similar à Task N"/"etc." em conteúdo
load-bearing. `<autor>`, `<T>`, `<tema>`, `<id>`, `<seção>`, `<slug>`,
`<arquivo>` são placeholders de template de comando (paths/argumentos genéricos
do `mem`), não lacunas do plano. Caminhos de arquivo concretos sempre dados.

**Consistência de nomes:** `mem` (ferramenta) · `mem.db` (índice derivado,
gitignored) · `engine/assets/mem/mem` (asset pinado) · `engine/integrations/
mem.py:mem_call`/`MemResult`/`MEM_PINNED_VERSION` (fronteira) · `.claude/bin/
mem` (vendorizado) · `.claude/memory/<autor>.jsonl` (fonte commitada) ·
Tier-0/Tier-1 · `RULE_INDEX` · `feat/mem-integration` (branch única). Verbo
"forge" só como verbo (Decisão 4 do projeto). Voz mentor calmo em todos os
artefatos gerados.

**Reversibilidade (risco ALTO — docs operacionais load-bearing):** a sequência
T4/T5 (aditivo) → T6 (enxugue) garante que o conteúdo está no mem ANTES de
sair do injetado; o enxugue é `git checkout`-reversível; o gate (T7) valida na
branch ANTES de merge. Os arquivos com enforcement acoplado (`01-decisions.md`,
`08-session-handoff.md`) e o Mandamento 0 verbatim NÃO são deletados.
