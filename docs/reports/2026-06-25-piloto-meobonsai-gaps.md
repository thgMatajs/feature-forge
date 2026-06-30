# Piloto MeoBonsai — gaps IA-first (registro durável)

> **Data:** 2026-06-25
> **O que é:** registro durável do piloto end-to-end do `forge` exercitado
> contra um projeto KMP real — o MeoBonsai (Android/iOS/shared). Os 14 comandos
> foram dirigidos por um agente IA, sem stdin, para medir o quão "100% IA-first"
> o forge já está e onde ainda faltam dentes. Abaixo: scorecard dos 14 comandos,
> os 8 temas cross-cutting, o registro completo de bugs, os fixes já aplicados
> durante o piloto e as recomendações priorizadas P0/P1/P2.
> **Sobre as fontes:** este é o relatório-mãe. Os 11 relatórios por-comando que
> o embasaram (`01..11`) eram efêmeros — viveram no scratchpad da sessão do
> piloto e não foram versionados. Este documento é o que sobrevive deles:
> persiste aqui a síntese consolidada para consulta futura.

---

# Piloto feature-forge end-to-end (MeoBonsai) — Relatório-mãe

> Piloto: os 14 comandos do `forge` exercitados contra um projeto KMP real
> (MeoBonsai — Android/iOS/shared, ~519 arquivos / 4582 símbolos, com sistema
> agêntico próprio em `.claude/`). Feature de teste: "na home, listar os bonsai
> cadastrados como cards". Host: agente IA dirigindo o intent loop sem stdin.
> Branch descartável `pilot/forge-home-bonsai-list`; nenhum commit no upstream.
> Fontes: 11 relatórios por-comando em `scratchpad/pilot/01..11`.

## Sumário executivo

A **plumbing IA-first do forge está sólida e provada** end-to-end: nos 14
comandos, o contrato `<FORGE_INTENT/>` em stdout + exit 2 + resposta via
`forge-response.json` + idempotência por consumed-log funcionou de forma
confiável, sem necessidade de stdin em nenhum momento, e os comandos
read-only (graph, status, verify) provaram-se genuinamente read-only. A
feature foi construída de verdade — compila Android e iOS, 172 testes
unitários verdes, bate o screenshot (com care fields mockados por decisão
explícita do usuário). O que ainda **não** está pronto para "100% IA-first" é
a divisão de **inteligência/substância**: o engine entrega o mecanismo
(state, graph, intent, stepping, templates) com qualidade, mas delega
inteiramente ao host o julgamento e o conteúdo, e os pontos onde deveria
haver "dentes" — gates de qualidade no `verify`, orquestração da DAG no
`implement`, enforcement de readiness no `plan` — ou são procedurais (checam
presença, não substância), ou são inertes (stubs no-op + falso-positivo que
cega a cascade), ou simplesmente não orquestram (implement preso em
TASK-0001). Some-se a isso um gargalo de performance no `init` (parcialmente
corrigido durante o piloto) e papercuts de protocolo (schema-version não
anunciado, sub-intents multi-passo morrendo na memory). O forge **já tem o
blueprint da correção dentro de casa** — o plan-auditor com 12 checks
determinísticos roda nos planos do próprio forge, mas não no pipeline do
consumidor. A distância para 100% IA-first não é de plumbing; é de
substância de gate e de orquestração.

## Scorecard por comando

| # | Comando | Funcionou? | Perf | IA-first | Achado principal |
|---|---|---|---|---|---|
| 1 | init | Sim (só após fix de perf) | Ruim → aceitável | Sólido (4 intents, 0 exigem humano) | Travava em monorepo real por rglob sem poda; pós-fix completa mas ~33 min wall (discovery re-roda toda invocação) |
| 2 | doctor | Sim (exit 1 — FAIL é bug do forge) | Excelente (3.3s) | Sólido (1 intent) | Auto-inconsistência forge↔forge: init grava `schema-version '1.3'`, doctor exige int `1` → 🔴 broken logo após init |
| 3 | graph | Sim | Excelente (~0.1s/query, reusou db) | Sólido (1 intent) | Reuse-intelligence é o destaque (Q13/Q15 acham `logEventSafely` dup); Q4 silent-empty em nome de módulo errado |
| 4 | memory | Parcial | Excelente (sub-s) | Quebrado em multi-passo | Sub-intents inalcançáveis: 5/8 opções morrem (exit 1 + checkpoint apagado em vez de exit 2) |
| 5 | plan | Sim (após resolver blocker) | Excelente (sub-s, reusou) | Bom front-door + grounded-challenge | Recursão infinita no path A do gate de readiness (~979 níveis → RecursionError); gate binário sem `ready-with-blocks` |
| 6 | implement | Feature construída pelo HOST | Excelente (forge ~0-1s) | Médio-baixo (não orquestra DAG) | "Orchestration theater": re-apresenta TASK-0001 sempre, checkpoint mantém `task-id: null`; comandos de build no contrato errados |
| 7 | verify | Roda, exit 1 falso-positivo | Excelente (~1s) | Read-only correto | Verde inerte (6 stubs no-op + 4 built-in sem staged) + koin off-contract cega 5 validators iOS/KMP via fail-fast |
| 8 | qa | Sim — verdict BLOCK | Engine sub-s; LLM ~15 min | Conductor-dispatch (não intent loop) | Melhor para achar problemas reais (45 findings, IDOR + PII); mas red-teia contratos, não impl-vs-spec; não dirigível pelo SKILL.md instalado |
| 9 | status | Sim (exit 0) | Excelente (~84ms) | Read-only correto | Fiel ao forge mas cego ao git/qa: reporta `implementing` com 6 commits da feature invisíveis e qa BLOCK sem rastro |
| 10 | evolve | Sim | Excelente (~209ms) | Sólido (ask→confirm→fim) | Cadeia reuse→evolve→fingerprint coerente; §6 segura end-to-end; loop de re-render se stdout fecha cedo |
| 11 | reconfigure | Sim | Boa (~0.15s/passo) | Sólido (intent puro) | Dashboard re-impresso a cada passo (ruído no transcript IA-first) |
| 12 | upgrade | Não executado (guardrail) | n/a (só --help) | Não-interativo | Sem dry-run; muta o git do FORGE_HOME (checkout --detach) — perigoso em branch de dev |
| 13 | undo | Sim | Excelente (~0.1s/passo) | Sólido (8 caminhos) | Só toca ações forge-tracked (seguro); exit 1 em no-op de `last` é semântica discutível |
| 14 | raw | Sim | Excelente (~0.08s) | Não-interativo | Escape hatch limpo; `rebuild-templates` muta FORGE_HOME sem confirm |

## O que está BOM (com evidência)

**Colisão do init com `.claude/` pré-existente: não-destrutiva, append-only.**
O cenário "90% dos projetos já têm `.claude/`" é tratado com elegância. O
MeoBonsai tinha um sistema agêntico completo e rastreado (13 agents, 54
skills, 4 hooks, 12 rules, settings.json). Pré-fix, a fase de install nem
foi alcançada, mas os fingerprints SHA-1 ficaram idênticos. Pós-fix, a fase
de merge rodou: `settings.json` mudou (`864b69d8…` → `aa40ebaf…`) com diff
**100% linhas `+`** — 38 inserções, 0 remoções; os 3 hooks PostToolUse e 2
PreToolUse existentes preservados intactos, forge appendou os seus depois.
Mesmo padrão em AGENTS.md (sentinel `<!-- FORGE_AI_DRIVER -->`) e SKILL.md
(subdir novo entre os 54). Confirma o contrato append-only de
`merge_settings_json` (01-init §"Re-run pós-fix").

**Contrato IA-first sólido e provado nos 14 comandos.** Marker em stdout,
exit 2 = pausa, idempotência via consumed-log, sem fallback para stdin. No
init pós-fix, 4 pontos de decisão, 0 exigiriam humano (detecção bate o stack;
defaults sensatos). No doctor/graph/plan/evolve/reconfigure/undo, o loop
fecha limpo: intent emitido → host responde → engine consome (arquivo some do
disco) → segue. Sob `CLAUDECODE=1` o adapter deliberadamente NÃO escreve
`forge-pending.json` (o marker stdout é a notificação) — contrato cumprido,
confirmado em todos os relatórios. Ressalva: o qa usa modelo
**conductor-dispatch**, não intent loop (registrar a distinção — 08-qa §Veredito).

**reuse-intelligence + evolve + fingerprint = cadeia coerente e valiosa.** O
graph Q13/Q15 detecta `logEventSafely` byte-idêntico em
`shared:feature:bonsai` e `shared:feature:home` (mesmo `body_hash`
`d44b22a0…`), com `suggested_target shared/core/.../util/` e `confidence
0.85` (03-graph). O evolve transforma isso na proposta P-0001 "promote
duplicate helper to shared ancestor", verificada contra o código real
(10-evolve §Propostas). A rejeição grava fingerprint `d6e3fc96…` em
`rejected-evolutions.yaml`; re-injetar a proposta idêntica resulta em "1
proposta pulada por veto" sem re-perguntar — disciplina §6 segura
end-to-end (10-evolve §Fingerprint).

**grounded-challenge pegou um gap REAL de produto.** No plan, o confronto
contra o domínio recusou inventar os campos de cuidado do card (próxima ação
/ última rega / última adubação) porque NÃO há fonte no domínio `Bonsai` (sem
entidade `CareEvent`) — virou o blocker Q-001 que dominou o desfecho. Também
pegou que a home está intencionalmente vazia na Phase 1 e que não existe
método de listagem (`BonsaiService` só tinha `getBonsai` single-doc → Q-002).
Esses são exatamente os gaps que um plano ingênuo inventaria silenciosamente
(05-plan §Grounded-challenge).

**A feature foi construída e funciona.** 5 tasks, 6 commits + 1 doc.
`:shared:feature:bonsai`/`home` compilam (commonMain + iOS sim);
`:androidApp:feature:home:assembleDebug` passa; `xcodebuild` para iPhone 17
Pro: `** BUILD SUCCEEDED **`. 172 testcases (bonsai 130 + home 42), 0 falhas,
incluindo os testes novos (MAN-01..05 / SC-006..010). Reuso forte do
scaffolding e do design system existentes (MeoCard/MeoFab/MeoText, extensão
de `HomeCollectionViewModel`) — Mandamento 3 respeitado. Care fields mockados
por decisão do usuário, claramente marcados com `// TODO(CareEvent)` (06-implement).

**memory L3 faz proxy do MEMORY.md nativo do projeto, sem duplicar.** A
camada L3 não vive em `.claude/memory/`; é proxy read-only do `MEMORY.md` do
sistema agêntico próprio do MeoBonsai, surfando 31 entradas reais sem mexer
nem copiar. Coexistência limpa (04-memory §Estrutura).

## Os 8 temas cross-cutting

### Tema 1 — Divisão host-vs-engine: gates procedurais, não substantivos

O engine é mecanismo (state/graph/intent/stepping/templates); o host é
julgamento/conteúdo/orquestração. O problema é que os pontos que deveriam ter
"dentes" os têm de mentira:

- **plan não valida conteúdo entre waves.** Os gates são puramente mecânicos
  ("Status da Wave X? continuar/pausar"). Se o host preencher mal ou deixar
  `{{placeholders}}`, o engine avança sem reclamar. O piloto pegou DUAS vezes
  fills parciais que um "0 placeholders" superficial deixaria passar:
  tech-spec com §3-§7 ainda em stubs `{{ConceptViewModel}}`, e task-breakdown
  com `dependency_graph/critical_path` como `[]` default (05-plan §Pontos fracos).
- **verify tem dentes que quase não mordem** (ver Tema 6).
- **implement não orquestra a DAG** (ver Tema 7) — é "orchestration theater":
  apresenta a task e delega tudo ao host.

A qualidade fica auto-policiada pelo host. **Por que importa:** "100%
IA-first" exige que a substância — não só a forma — seja verificável pelo
engine; senão o forge é um andaime de templates, não um orquestrador de
qualidade. **Direção de fix:** o forge já tem o blueprint — o **plan-auditor**
(12 checks determinísticos: C1/C2 critical, H1-H4, M1-M3, L1-L3) roda nos
planos do próprio repo feature-forge mas NÃO no pipeline do consumidor.
Portar a mecânica de auditoria determinística para os gates do consumidor
(content-check leve nas waves do plan, classificação degraded vs fail no
verify, detecção de task-done no implement) é o caminho com maior alavancagem.

### Tema 2 — Footprint & namespace

O snapshot é pesado e espalhado, e colide de nome com o sistema agêntico do
próprio projeto:

- **Footprint.** O init cria 9 entradas untracked no top-level de `.claude/`
  além do `.claude/forge/` (graph.db 2.3 MB, cards/, memory/, inventory/,
  proposed-evolutions, locks, workflow-config-history) — nenhuma coberta por
  `.gitignore` (BUG-4, 01-init). [O `.claude/forge/.gitignore` cobre só
  `state/` + checkpoints; e mesmo entre os checkpoints, o de memory ficou de
  fora — BUG-MEM-5.]
- **Estado transiente vaza no git status.** `.init-checkpoint.yaml`,
  `.memory-cli-checkpoint.yaml`, etc.
- **Namespace.** O forge instala `.claude/skills/feature-forge/`,
  `.claude/forge/hooks/post-subagent-validate.sh`, etc., ao lado do sistema
  agêntico do qual ele descende geneticamente (o MeoBonsai usa gsd-* e
  superpowers; o forge absorveu patterns desses). A coexistência funcionou
  (Tema do positivo), mas o namespace `.claude/` é compartilhado sem prefixo
  forte além do subdir `forge/`.

**Por que importa:** um operador que faz `git add .` commita 2.3 MB de
graph.db e snapshots derivados; e a sobreposição de namespace confunde quem
mantém os dois sistemas. **Direção de fix:** init semear/anexar `.gitignore`
cobrindo artefatos derivados (graph.db, cards snapshot, memory, locks),
versionando só `forge-config.yaml`; consolidar todo estado transiente sob um
único subdir já ignorado.

### Tema 3 — Assimilação de convenção

O forge não ingere as convenções do projeto de forma sistemática:

- Não lê `.claude/rules/` do projeto de forma genérica — só 2 filenames
  hardcoded (testing.md, observability.md) [conforme a moldura; o piloto
  confirma que o conventions.yaml é 100% code-derived].
- `conventions.yaml` é derivado 100% do código (package, layout KMP,
  koin-annotations, nav3) — preciso, mas cego às regras escritas (01-init).
- O campo `conflicts-detected: []` fica morto — não há reconciliação entre o
  que o forge detecta e o que o projeto declara.

**Por que importa:** um projeto com regras explícitas (como o MeoBonsai, que
tem 12 rules) tem seu conhecimento escrito ignorado; o forge re-deriva o que
já está documentado e não detecta divergências. **Direção de fix:** ingerir
`.claude/rules/*` de forma genérica e popular `conflicts-detected` quando o
code-derived diverge do declarado.

### Tema 4 — Papercuts do intent protocol

A plumbing é sólida, mas há arestas que penalizam um host ingênuo:

- **schema-version não anunciado no `<FORGE_INTENT>`.** A resposta exige
  `"schema-version":1`, mas o marker não declara o requisito; host ingênuo
  omite e toma exit 1 (BUG-G2 em graph, BUG-MEM-4 em memory, confirmado em
  vários). Mensagem de erro é boa e mentor-calmo, mas o intent deveria ser
  auto-descritivo.
- **Sub-intents multi-passo morrem na memory.** Qualquer opção com 2º passo
  sai com exit **1** (não 2) e **apaga** o checkpoint em vez de avançá-lo →
  5/8 opções inalcançáveis; a próxima invocação reinicia no menu de topo
  (BUG-MEM-1/2, 04-memory). Um driver que mapeia exit 2 = pausa trata a pausa
  aninhada como falha hard.
- **intent-id do rodapé diverge do emitido** (BUG-MEM-3, intermitente): host
  que lê o id do rodapé responde o id errado.
- **Driver SKILL.md cobre só plan/implement/verify.** Não menciona
  qa/evolve/memory/reconfigure/upgrade/undo; e os agent prompts do conductor
  não estão instalados no projeto (BUG-QA-4). Host ingênuo não dirige IA-first
  esses verbos — funcionou no piloto porque o host leu o conductor do
  FORGE_HOME direto.

**Por que importa:** "100% IA-first" significa que um host genérico, dirigindo
só pelos artefatos instalados, consegue conduzir todo verbo. Hoje metade dos
verbos exige conhecimento fora do SKILL.md. **Direção de fix:** anunciar
`response-schema-version` no marker (ou aceitar ausência como default 1);
persistir checkpoint em sub-intents com exit 2 uniforme; expandir o mapa de
verbos do SKILL.md e instalar os prompts do conductor.

### Tema 5 — Performance

Localizada no init/discovery; as inspeções pós-init reusam artefatos e são
rápidas:

- **Discovery rglob sem poda (BUG-1).** `_glob_any` usava
  `project_root.rglob()` filtrando `_SKIP_DIRS` só depois de enumerar tudo;
  descia em node_modules (492M) + .gradle (484M). Medido:
  `rglob("*")` = 459.854 paths / 9.4s vs walk podado = 150.262 / 1.5s.
  Travava o init (EXIT=124 em 5+ min). Corrigido em `_glob_any`, mas BUG-5: o
  mesmo anti-padrão persiste em ≥3 sites no hot-path (`_walk_cache.walk_project`,
  ~18 rglob nos extractors de inventory, `_count_needle_hits`) → discovery
  ainda ~220s pós-fix.
- **Re-discovery a cada invocação (BUG-2).** O checkpoint salva o STEP mas não
  o resultado caro de discovery; cada re-invoke re-paga ~220s. Com 5
  invocações para completar o init = ~18 min só de discovery repetida; total
  ~33 min wall — péssimo no host IA-first canônico, onde cada resposta = nova
  invocação.

**Por que importa:** o init é o primeiro contato; ~33 min para configurar um
projeto bloqueia adoção real. **Direção de fix:** extrair
`_walk_recursive_pruned` para helper compartilhado e trocar todos os rglob de
hot-path; cachear o resultado de discovery no checkpoint e reusar quando há
response pendente.

### Tema 6 — Verificação inerte

Nenhum dos 14 comandos faz verificação runtime/visual; e a verificação
estática que existe (verify, qa) tem furos:

- **verify "verde inerte".** Dos 18 validators do scope: 6 são stubs Phase 5
  no-op (firebase/firestore/crashlytics/auth — `return success`); 4 built-in
  olham arquivos **staged** mas a feature está **commitada** → veem 0
  arquivos. Resultado: 10 "pass" sem substância. Nenhum dos 18 deu veredito
  substantivo e corretamente escopado sobre a feature (07-verify §Vereditos).
- **Falso-positivo do koin cega 5 validators.** `check-koin-modules.py` é stub
  legado fora do contrato canônico (usa `--root`, não conhece
  `--scope`/`--id`); o harness passa `--project-root/--scope/--id`, argparse
  morre com exit 2, harness mapeia para FAIL, fail-fast (Decisão 23) para a
  cascade — e os 5 validators iOS/Swift/ktor/nav3/skie, os que mais importam
  num KMP, ficam cegos (BUG-VERIFY-1, severity HIGH — detection/gate).
- **qa é o melhor para achar problemas reais** (45 findings: 2 critical IDOR +
  PII, 17 high) MAS red-teia **contratos** (spec-vs-spec, gate-vs-claim), não
  o **diff da implementação**. Não há vetor impl-vs-spec — um bug que viola o
  spec correto passaria (08-qa §Scope).
- **Nenhum passo runtime/visual** em nenhum comando — o piloto bateu o
  screenshot e os 172 testes manualmente, fora do forge.

**Por que importa:** o verde do verify comunica garantia que não existe; o qa
assume que a implementação obedece o spec. Para 100% IA-first, o forge
precisaria fechar o loop impl-vs-spec e ter ao menos um nível de verificação
de execução. **Direção de fix:** classificar validator quebrado como
`degraded` (não `fail`, não cega cascade); sumário honesto ("Pass: 10 — 6
stub no-op, 4 sem staged"); escopar verify ao diff da feature; adicionar
vetor impl-vs-spec ao qa; rodar os quality gates nativos do projeto
(ktlint/detekt/swiftlint pegaram problemas reais que o forge não pegou).

### Tema 7 — Orquestração de DAG

- **implement não avança a DAG.** É handoff manual por task ("Apply Mode v1").
  Após o host implementar e commitar TASK-0001, re-invocar `forge implement`
  re-apresenta TASK-0001 ("Detectei implementação em andamento — continuando
  em TASK-0001"); o checkpoint mantém `task-id: null` / `step: step-post-slug`
  permanentemente; o intent-id é idêntico entre invocações. Toda a condução
  0002→0005 (incluindo o paralelismo android/ios) foi feita pelo HOST. O
  history acumulou ~980 `wave-e-rerun-requested` e zero eventos de task
  concluída (06-implement, 09-status).
- **status não enxerga.** Reflete fielmente o estado interno (`implementing /
  verify-failed`) mas o forge nunca registrou as 5 tasks como done, nem o qa
  BLOCK (0 ocorrências de `qa` no history), nem os 6 commits do git. O status
  é fiel-ao-forge, mas o forge é cego-à-realidade (09-status §Fidelidade).

**Por que importa:** "orquestrar o lifecycle de features" é a proposta de
valor central do forge; sem avançar a DAG nem registrar progresso, o forge é
um gerador de contratos de task, não um orquestrador. **Direção de fix:**
persistir conclusão por task (via commit/evidence ou intent "task done") e
mover o ponteiro; persistir o verdict do qa no L1; status reconciliar com o
git e sinalizar descompasso.

### Tema 8 — Segurança de comandos destrutivos

- **upgrade sem dry-run muta o git do FORGE_HOME.** Faz `git checkout --detach
  <tag>` + `pip install` no repositório feature-forge. Não há
  preview/plan-only — só aplica ou não roda. Perigoso quando o instalador está
  numa branch de dev (como no piloto): tiraria o HEAD da branch silenciosamente
  (11-meta §upgrade). Por isso não foi executado (guardrail).
- **undo exit-1 em no-op.** `last → reconfigure` deu exit 1 ("nada a reverter"
  por falta de `.bak`); para um no-op legítimo, exit 0 seria mais coerente com
  a semântica do reconfigure (11-meta §undo).
- **raw rebuild-templates muta FORGE_HOME sem confirm** (11-meta §raw).

[Positivo: undo só toca ações forge-tracked — ignora commits git arbitrários,
não é um "git revert" genérico; os 6 commits da feature ficaram intactos.]

**Por que importa:** comandos que mutam estado fora do projeto-alvo (FORGE_HOME)
sem preview são uma armadilha de adoção. **Direção de fix:** `upgrade
--dry-run` + guard de branch ("você está em `fix/...`, não numa release —
continuar?"); exit 0 em no-ops de undo; aviso de escopo no rebuild-templates.

## Registro completo de bugs

Ordenado por severidade. Severidades preservadas dos relatórios; findings de
detection/gate/segurança não rebaixados.

| ID | Sev | Comando | Essência | Arquivo:linha / repro | Tema |
|---|---|---|---|---|---|
| BUG-1 | Crítico [FIXED] | init | Travava em monorepo: rglob sem poda desce em node_modules/.gradle | `engine/detection/_eval.py::_glob_any` ~L72/84 | 5 |
| BUG-1b | — [FIXED] | init | `compose_backend_axes` rodava 2× no step-5 | `engine/init.py:1736` + `:2652` (dedup) | 5 |
| BUG-PLAN-1 | Alto/Crítico | plan | Path A do gate readiness recursa infinito (~979 níveis) → RecursionError | `engine/plan.py::_run_wave_e` L1058; responder `a` em readiness=partial, re-invocar sem mudar verdict; exit 1, ~1.3MB stdout | 1 |
| BUG-5 | Alto | init | Fix do BUG-1 parcial: mesmo anti-padrão em ≥3 sites do hot-path | `engine/inventory/_walk_cache.py:60`; `design_system.py` 9× / `conventions.py` 5× / `i18n.py` 4×; `engine/init.py::_count_needle_hits:318` | 5 |
| BUG-2 | Alto (→Crítico-UX) | init | Discovery re-roda integral (~220s) toda invocação; ~18 min só nisso | observar `.init-checkpoint.yaml` volta a step-2 a cada re-invoke | 5 |
| BUG-A | Alto | doctor | init grava `schema-version '1.3'` (str), doctor exige `== 1` (int) → 🔴 broken | `engine/doctor.py:428` vs forge-config.yaml:1 | 1 |
| BUG-MEM-1 | Alto | memory | Sub-intents inalcançáveis: exit 1 + checkpoint apagado em vez de avançado | resp opção `3`/`4` → emite sub-intent, EXIT=1, `.memory-cli-checkpoint.yaml` some | 4 |
| BUG-MEM-2 | Alto | memory | Exit code de pausa inconsistente: topo=2, aninhado=1 | opção 3/4 → "paused" com EXIT=1 | 4 |
| BUG-IMPL-1 | Alto | implement | Não avança a DAG: re-apresenta TASK-0001; checkpoint `task-id: null` | `forge implement <slug>` → commit → re-invocar; exit 2 | 7 |
| BUG-VERIFY-1 | Alto (HIGH) | verify | koin off-contract derruba cascade, cega 5 validators iOS/KMP via fail-fast | `check-koin-modules.py` (`--root`) vs harness `--project-root/--scope/--id`; `engine/verify.py:938,970`; exit 2→FAIL | 6 |
| BUG-QA-1 | Alto | qa | invocation_args não chegam aos validators no sandbox → vetor inerte | `sandbox-results.json` mostra "no slug provided", engine marca `ok` | 6 |
| BUG-QA-2 | Alto (design) | qa | Sandbox cego a validators de card (Decisão 30 allowlist) — justo os com stubs mentirosos | 6/8 fixtures apontam `.claude/cards/*/validators/*.py`, recusadas | 1, 6 |
| BUG-3 | Médio | init | Resume reseta step e preset do checkpoint | re-invoke em step-5 volta a step-2 / preset:null | 5 |
| BUG-6 | Médio | init | `compose_backend_axes` re-roda ~86s/invocação (checkpoint não cacheia) | step-5 por invocação pós-dedup | 5 |
| BUG-B | Médio | doctor | version-lock lido no dir errado → falso "não criado"; check lock-vs-binário morto | `engine/doctor.py:865` usa `.claude/`, init grava `.claude/forge/` | 1 |
| BUG-G1 | Médio | graph | Q4 silent-empty (`[]`, exit 0) em nome de módulo errado; só `shared:feature:home` | `forge graph --json q4 :feature:home` | 1 |
| BUG-G2 | Médio (UX contrato) | graph | intent não anuncia `schema-version=1` exigido na resposta | responder sem schema-version → exit 1 | 4 |
| BUG-MEM-3 | Médio | memory | intent-id do rodapé de pausa diverge do emitido (opção 4) | rodapé cita `aa457823` vs emitido `e3d80acf` | 4 |
| BUG-IMPL-2 | Médio | implement | Comandos de build no contrato errados: `testDebugUnitTest` inexiste (KMP usa `testAndroidHostTest`); `run-ios-simulator.sh --build-only` não existe | TASK-000N.yaml validation_steps | 7 |
| BUG-IMPL-3 | Médio | implement | cc-gate e secrets-gate "unavailable (import failed)" degradam silencioso no Apply Mode | qualquer `forge implement` | 6 |
| BUG-QA-3 | Médio (contrato) | qa | Phase 4 synthesis rodou no engine, não via dispatch `qa-synthesizer` LLM | timestamps iguais em sandbox-results + qa-report | 1 |
| BUG-QA-4 | Médio (IA-first) | qa | qa não dirigível pelos artefatos instalados (SKILL.md não cobre; conductor não instalado) | `grep -i qa SKILL.md` só refs genéricas; `find .claude/skills/feature-forge -name qa-*` vazio | 4 |
| BUG-VERIFY-2 | Médio | verify | Verde inerte: 6 stubs no-op + 4 built-in sem staged = 10 pass sem substância | `forge verify --json` | 6 |
| BUG-STATUS-1 | Médio | status | Não reconcilia com git nem sinaliza descompasso (6 commits invisíveis) | feature commitada + `forge status` → `implementing` sem alerta; exit 0 | 7 |
| BUG-STATUS-2 | Médio | status | Não expõe qa verdict (BLOCK invisível — sem evento qa no history) | `forge status` após qa BLOCK | 7 |
| BUG-EVOLVE-1 | Médio | evolve | Loop de re-render se stdout fecha cedo (~90MB/30s); SIGPIPE/EOF não tratado | `forge evolve < /dev/null \| head -c 3000`; exit 143/trava | 4 |
| BUG-PLAN-2 | Baixo/Médio | plan | `paths-detail.motive` vazio no ask_three_paths (prosa tem, JSON não) → prompt anêmico | qualquer gate ask_three_paths; exit 2 | 4 |
| BUG-4 | Baixo | init | Artefatos top-level do init fora de qualquer `.gitignore` (9 untracked, graph.db 2.3MB) | `git status` pós-init | 2 |
| BUG-MEM-4 | Baixo | memory | schema-version não anunciado no intent (= BUG-G2) | omitir schema-version → exit 1 | 4 |
| BUG-MEM-5 | Baixo | memory | `.memory-cli-checkpoint.yaml` fora do gitignore (irmãos whitelisted) | `git status` pós forge memory | 2 |
| BUG-G3 | Baixo | graph | Resposta stale (intent-id divergente) bloqueia emissão seguinte | deixar forge-response.json velho → exit 1 | 4 |
| BUG-IMPL-4 | Baixo | implement | `forge implement --help` interpreta `--help` como slug inválido | `forge implement --help`; exit 0 | 4 |
| BUG-VERIFY-3 | Baixo | verify | Warns Compose varrem repo inteiro, não escopam à feature | warns sobre core/designsystem + feature/auth | 6 |
| BUG-QA-5 | Baixo | qa | Microcopy do emit ambígua ("-> proposed-evolutions.yaml") | destino real é `.claude/memory/L1/proposed-evolutions/proposed.yaml` | 2 |
| BUG-QA-6 | Baixo | qa | Leftover `_sandbox_guard/` + `__pycache__` no run tree pós Phase 5 | inspecionar run tree | 2 |
| BUG-EVOLVE-2 | Baixo | evolve | `--help` não reconhecido (cai no fluxo normal) | `forge evolve --help` | 4 |
| BUG-UNDO-1 | Baixo | undo | exit 1 em no-op de `last` (semântica discutível; reconfigure no-op = exit 0) | `forge undo` → last → sem .bak; exit 1 | 8 |
| BUG-RECONF-1 | Baixo | reconfigure | Dashboard re-impresso a cada passo do loop (ruído no transcript IA-first) | navegar reconfigure multi-passo | 4 |
| BUG-UPGRADE-1 | Alto (segurança) | upgrade | Sem dry-run; muta git do FORGE_HOME (checkout --detach) sem guard de branch | `forge upgrade` em branch de dev prosseguiria pro checkout | 8 |
| BUG-RAW-1 | Baixo | raw | `rebuild-templates` muta FORGE_HOME sem confirm/dry-run | `forge raw rebuild-templates` | 8 |

## Os fixes já aplicados durante o piloto

Branch do forge `fix/pilot-init-perf` (commit `4649d78`):

- **BUG-1 — poda em `_glob_any`.** Substituído `project_root.rglob()` por
  `_walk_recursive_pruned` (poda `_SKIP_DIRS` na descida). Mediu ~5-6× mais
  rápido por pass (459.854 paths/9.4s → 150.262/1.5s).
- **BUG-1b — dedup `compose_backend_axes`.** Removeu a 2ª chamada no step-5.

Efeito: o init que travava (EXIT=124 em 5+ min) passou a **completar
end-to-end (EXIT=0)** — preset kmp-mobile, 15 cards, graph.db (519 files /
4582 symbols), merge não-destrutivo de settings.json verificado. **O fix
desbloqueou o piloto inteiro.** Caveat: o fix é parcial (BUG-5) — o mesmo
anti-padrão persiste em ≥3 outros sites do hot-path, então discovery segue
~220s e o init total ~33 min wall (BUG-2). Recomendação registrada: extrair
`_walk_recursive_pruned` para helper compartilhado e padronizar todos os sites.

## Recomendações priorizadas

### P0 — bloqueia adoção real

1. **Completar o fix de perf do init (BUG-5 + BUG-2).** Extrair
   `_walk_recursive_pruned` para helper compartilhado; trocar todos os rglob
   de hot-path (`_walk_cache.walk_project`, ~18 nos extractors,
   `_count_needle_hits`); cachear discovery no checkpoint e reusar quando há
   response pendente. Sem isso, o init leva ~33 min — bloqueia o primeiro
   contato. (Tema 5)
2. **Reconciliar schema-version init↔doctor (BUG-A).** init grava `'1.3'`
   (str), doctor exige `1` (int) → todo projeto dá 🔴 broken logo após init.
   Adicionar test de round-trip init→doctor verde como gate de regressão.
   Corrigir junto o path do version-lock (BUG-B), que tem detecção morta. (Tema 1)
3. **Corrigir a recursão infinita no plan (BUG-PLAN-1).** Path A do gate de
   readiness deve re-renderizar e PAUSAR (exit 2) para o host ajustar — nunca
   recursar síncrono. É um crash de exit 1 + 1.3MB stdout no caminho oferecido
   como #1. (Tema 1)
4. **implement avançar a DAG (BUG-IMPL-1).** Persistir conclusão por task
   (via commit/evidence ou intent "task done") e mover o ponteiro. Hoje fica
   preso em TASK-0001; sem isso o forge não orquestra — é a proposta de valor
   central quebrada. (Tema 7)
5. **verify: não cegar a cascade por validator quebrado (BUG-VERIFY-1).**
   Classificar validator que morre por argparse error (exit 2 / "unrecognized
   arguments") como `degraded`, não `fail` — distinguir "validator quebrado"
   de "código reprovado". Atualizar o `check-koin-modules.py` ao contrato
   canônico. Sem isso, um falso-positivo cega 5 validators iOS/KMP. (Tema 6)
6. **Sub-intents multi-passo funcionarem na memory (BUG-MEM-1/2).** Persistir
   o checkpoint no sub-intent (o schema já antecipa `submenu`/`entry-id`) e
   unificar exit 2 em todo ponto de pausa. Hoje 5/8 opções da memory são
   inalcançáveis via IA-first. (Tema 4)

### P1 — fricção IA-first séria

7. Anunciar `response-schema-version` no `<FORGE_INTENT>` (ou aceitar ausência
   como default 1) — BUG-G2/MEM-4. (Tema 4)
8. Expandir o SKILL.md instalado para cobrir todos os verbos
   (qa/evolve/memory/reconfigure/upgrade/undo) e instalar os prompts do
   conductor no projeto — BUG-QA-4. (Tema 4)
9. verify: sumário honesto de cobertura ("Pass: 10 — 6 stub no-op, 4 sem
   staged") e escopar ao diff da feature — BUG-VERIFY-2/3. (Tema 6)
10. qa: aplicar invocation_args no sandbox + estender allowlist para
    `.claude/cards/*/validators/` + adicionar vetor impl-vs-spec —
    BUG-QA-1/2 + lacuna de Scope. (Temas 6, 1)
11. status: reconciliar com o git e sinalizar descompasso; persistir e expor o
    qa verdict — BUG-STATUS-1/2. (Tema 7)
12. upgrade: `--dry-run` + guard de branch antes do checkout destrutivo —
    BUG-UPGRADE-1. (Tema 8)
13. Portar a mecânica do plan-auditor (content-check determinístico) para os
    gates de wave do plan no pipeline do consumidor — Tema 1.
14. Cobrir todos os artefatos derivados do init no `.gitignore` (graph.db,
    cards, memory, locks, checkpoints) — BUG-4/MEM-5. (Tema 2)
15. Derivar os comandos de build dos contratos de task do projeto real (ler
    `gradlew tasks`) em vez de assumir `testDebugUnitTest` — BUG-IMPL-2. (Tema 7)

### P2 — polish

16. Feedback de progresso nos steps silenciosos longos do init (backend ~86s,
    orphan ~75s). (Tema 5)
17. graph: feedback "did-you-mean" em Q4 quando o módulo não casa; filtro de
    confiança em Q3 orphan-files — BUG-G1. (Tema 1)
18. evolve: tratar SIGPIPE/EOF no loop de render — BUG-EVOLVE-1. (Tema 4)
19. reconfigure: imprimir o dashboard só no 1º passo do loop — BUG-RECONF-1. (Tema 4)
20. `--help` reconhecido em todos os subcomandos (evolve, implement) —
    BUG-EVOLVE-2/IMPL-4. (Tema 4)
21. undo: exit 0 em no-op de `last`; raw: aviso de escopo no rebuild-templates;
    qa: qualificar microcopy do emit + limpar leftover — BUG-UNDO-1/RAW-1/QA-5/6.

## Veredito final: a distância para "100% IA-first"

A plumbing IA-first chegou: o intent loop é sólido, provado nos 14 comandos, e
a feature foi construída de verdade. A distância restante é de **substância e
orquestração**, não de protocolo. O forge hoje é um excelente gerador de
contratos e andaime de templates com um mecanismo de intent confiável, mas os
gates que deveriam morder ou não mordem (verify verde inerte, koin cegando a
cascade), ou não existem (impl-vs-spec, verificação runtime), e o orquestrador
central (implement) não avança a DAG. O caminho está claro e está dentro de
casa: o forge já possui o blueprint da auditoria determinística (plan-auditor)
— resta portá-lo para o pipeline do consumidor, fechar o loop de orquestração
e dar dentes reais aos gates. Com os 6 P0 endereçados, o forge sai de "demo
IA-first que constrói features sob condução cuidadosa do host" para
"orquestrador IA-first confiável em projeto real".

## Status update — verificação empírica pós-merge Fase 1 (2026-06-29)

> O corpo acima é o registro durável do piloto (2026-06-25) — não foi alterado.
> Esta seção (append-only) registra o que mudou desde então, verificado contra
> o código de **main pós-merge do PR#32** (campanha mem Fase 1, merge-commit
> `03a9f9c`, 2026-06-29). A campanha mem fechou os temas de footprint/namespace
> e memória; vários P0 que o report tratava como abertos hoje estão fechados.
> O backlog ativo dos ABERTOS está catalogado em `docs/design/04-pending.md`
> (seção "Piloto MeoBonsai 2026-06-25 — gaps"); o plano de ataque por ondas é
> a spec `docs/superpowers/specs/2026-06-29-pilot-remediation-design.md`.

### Resolvidos (verificado no código de main)

- **BUG-A (doctor schema-version) — FECHADO.** O report tratava como ABERTO P0
  (#2 das recomendações). Hoje `engine/doctor.py:440` aceita `{1,"1",1.3,"1.3"}`
  E `engine/init.py` grava `schema-version: 1` (int) em todos os sites — o
  desync init↔doctor é impossível. **Correção explícita ao corpo acima:** o
  veredito "🔴 broken logo após init" não vale mais.
- **Tema 7 / BUG-IMPL-1 (implement não avançava a DAG) — FECHADO.** O report
  tratava como ABERTO P0 (#4) e como falha da proposta de valor central. Hoje
  `engine/implement.py` tem `_pick_next_task()` keyed em status `done` (L374),
  grafo de deps + detecção de ciclo (L361) e checkpoint persistindo `task-id`
  resolvido (L142). **Correção explícita ao corpo acima:** o "orchestration
  theater / preso em TASK-0001 / checkpoint `task-id: null`" não existe mais.
- **BUG-MEM-1/2 (memory sub-intents inalcançáveis) — FECHADO.**
  `engine/memory_cli.py` foi reescrito como dispatcher stateless arg-driven na
  W-ROUTE 6a; sem menu interativo multi-passo, os 5/8 sub-intents inalcançáveis
  sumiram.
- **BUG-1 (init travava em monorepo por rglob sem poda) — FECHADO, com nuance.**
  O report registra o fix na branch `fix/pilot-init-perf` (commit `4649d78`,
  via `_walk_recursive_pruned`). Essa branch **NÃO foi mergeada**. O bug está
  fechado em main por uma implementação diferente: filtro inline `_SKIP_DIRS`
  em `engine/detection/_eval.py:72`. (O helper compartilhado `_walk_recursive_pruned`
  segue pendente para os outros sites — ver BUG-5 abaixo.)

### Parciais

- **BUG-1b** — a 2ª chamada de `compose_backend_axes` vive numa função W7.4
  deferred/unused; sem o duplo-custo ativo, limpeza completa pendente.
- **BUG-QA-4** — SKILL.md cobre o intent loop, não os prompts de
  qa/verify/memory/reconfigure/upgrade/undo.
- **BUG-UPGRADE-1** — tem rollback automático, mas sem `--dry-run` nem guard de
  branch.
- **BUG-4/MEM-5** — `.gitignore` cobre `state/` + checkpoints; faltam `graph.db`,
  `cards/`, `memory/`, `locks/`, `.memory-cli-checkpoint.yaml`.

### Abertos (backlog de remediação)

Catalogados em `docs/design/04-pending.md`, agrupados P0/P1/P2 com file:line e
direção de fix. Em síntese: o track que o mem **não** toca — correctness
(Tema 6, novo P0 #1: BUG-VERIFY-1/2), perf estrutural (BUG-5, BUG-2),
orquestração do gate de readiness (BUG-PLAN-1), e o hardening P1
(BUG-STATUS-1/2, BUG-G2, BUG-IMPL-2, BUG-B). A spec
`docs/superpowers/specs/2026-06-29-pilot-remediation-design.md` os organiza em
ondas, liderado pelo loop de correctness.

### Mapeamento tema → status (pós-merge)

- Tema 1 (host-vs-engine, gates com dentes): mem VIABILIZOU (rules curadas), mas
  os gates fortes ainda não foram construídos → **ABERTO** (Onda 2 da spec).
- Tema 2 (footprint/namespace): **✅ fechado** pela campanha mem (Fase 0+1).
- Tema 3 (assimilação de convenção): 🟡 substrato pronto; curadoria ativa = mem
  Fase 2.
- Tema 4 (papercuts do intent protocol): parcial — BUG-G2 aberto; BUG-MEM
  resolvido; BUG-QA-4 parcial.
- Tema 5 (performance): 🟡 BUG-1 fechado em main (não via a branch);
  BUG-1b parcial; BUG-5/BUG-2 abertos.
- Tema 6 (verificação inerte): **ABERTO — P0 #1.**
- Tema 7 (orquestração DAG): **✅ resolvido** (BUG-IMPL-1).
- Tema 8 (segurança de comando destrutivo): 🟡 BUG-UPGRADE-1 parcial; abertos os
  no-op de undo/raw.
