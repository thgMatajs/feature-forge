# Análise Comportamental — Loops de Comando, Ambiguidade e o "Grill" (feature-forge 1.4.0)

> **Data:** 2026-06-17
> **Provenance:** reconcilia e fact-checa `docs/reports/loops-abertos.md` (auditoria opencode focada em "loops que não fecham"), + investigação própria do comportamento real do `forge plan` sob input ambíguo/raso/texto-livre.
> **Relação com a consolidada:** companheiro de `docs/reports/auditoria-consolidada-2026-06-17.md` (a fonte de findings). Este doc cobre **comportamento de fluxo** + o **design do grill** — input pro planejamento da evolução.
> **Voz:** mentor calmo. Severidade determinística.

---

## 0. Pergunta investigada + veredito

**Pergunta:** "Se eu chamar `forge plan` passando um ticket simples/ambíguo (lacunas, gaps) ou um texto livre (`forge plan adicionar detalhe do bonsai`), qual o comportamento? O forge faz perguntas pra resolver a ambiguidade, no estilo grill-me / grill-with-docs?"

**Veredito em uma linha:** No nível do **engine**, o forge **não grilha** — e nem aceita ticket/texto-livre (rejeita com `SystemExit`). O grill existe nos **prompts dos agentes** (só o `planning-conductor`), mas é **inerte num consumidor** por causa do DRIVER-001. O "grill-with-docs" (confrontar o pedido contra o domínio existente) **não existe** no repo.

---

## 1. Comportamento real do `forge plan` (cenários verificados em código)

| Cenário | O que acontece | Exit | O host observa |
|---|---|---|---|
| `forge plan IN-37234` (ticket uppercase) | `_is_valid_slug` rejeita uppercase → `raise SystemExit` (`plan.py:1081`) | **1** | 1 linha em stderr: "slug 'IN-37234' invalid. kebab-case...". Nenhum arquivo, nenhum L1, nenhum fetch de ticket. |
| `forge plan "adicionar detalhe do bonsai"` (texto livre) | `_is_valid_slug` rejeita espaços → `raise SystemExit` | **1** | Mesma rejeição. **Sem** normalizar pra `adicionar-detalhe-do-bonsai`, sem "quis dizer?", sem elicitar. |
| `forge plan adicionar-detalhe-bonsai` (slug válido, intent raso) | Cria L1 (`planning`) + lock → infere subtype (só do **slug**; "bonsai/detalhe" não casam keyword → `product`, sem perguntar) → renderiza esqueletos de template → "abra no editor, preencha, digite continuar" → bloqueia | 0/130 | Sessão wave-a-wave de **esqueletos** (placeholders crus). Pergunta só mecânica (task count, continuar/pausar, readiness 3-caminhos). **Nenhum agente é despachado pelo engine.** |
| `forge plan` (sem arg) | `question.ask_text` pede **só o slug** (kebab-case) — nunca a descrição/intent → depois idêntico ao caso acima | 0/130 | Pergunta o slug, re-pergunta até válido. |

**Dois fatos load-bearing:**
1. **Front-door rígido + erro cru.** `forge plan` exige um slug kebab-case já formado. `raise SystemExit("...")` (`plan.py:1081`) NÃO está na tupla de except do `cli.py` → imprime a string em stderr e sai **1**, **bypassando** a escada semântica de exit-codes e o bloco mentor-calmo de 3-caminhos. Ticket IDs (uppercase) e frases (espaços) morrem aqui.
2. **O bug de casing (`{{FEATURE_SLUG}}`).** `plan.py:401` faz `raw.replace("{{FEATURE_SLUG}}", slug)` (UPPERCASE), mas templates usam `{{feature_slug}}` (lowercase, 74×). A substituição é **no-op** — até o slug, único token que o engine sabe preencher, fica cru.

---

## 2. O mecanismo de ambiguidade é scaffolding morto (L3 confirmado)

| Peça | Existe? | Populada por | Lida/gateada por | Veredito |
|---|---|---|---|---|
| `ambiguity-map.yaml` (`write/read_ambiguity_map`, `l1.py:408`) | sim | **nada no engine** (só `tests/`) | só `forge memory` (viewer) — gateia **nada** | **morto** |
| `elicitation.yaml` (`read/write_elicitation`) | sim | só `record_external_dep` (`plan.py:1582`) | não consultada por `run()`/waves | repurposed (só external-deps) |
| readiness gate (`_parse_readiness_status`, `plan.py:612`) | sim | — | faz **grep** de `status: ready` no markdown que **o host já preencheu** | não é detector de ambiguidade |
| detecção engine-side de "intake raso/incompleto" | **não existe** | — | — | zero |

**Conclusão:** a detecção de ambiguidade é **100% delegada à prosa dos prompts** dos agentes; o engine não detecta nem gateia nada. Um plano pode chegar a "planned" com placeholders crus e perguntas em aberto, desde que o host escreva `status: ready`.

---

## 3. Onde o "grill" realmente vive (e por que está inerte)

- **Só o `planning-conductor` grilha.** Disciplina §1: "Never proceed with unresolved ambiguity. If confidence < 0.85, ask. If vague, drill down." Phase 2 monta um **Ambiguity Map** (~22 nós, cada um `value|source|confidence`); Phase 3 faz **um AskUserQuestion com ≤4 perguntas agrupadas**; drill-down adversarial de vago ("alguns"→"qual critério? liste") com **cap de 2 rounds** → vira open-question `blocking: true`.
- **Os 6 sub-agentes NÃO perguntam.** Marcam `needs-elicitation` + append em `open-questions` e seguem ("never invent / mark and proceed"). O `readiness-reviewer` **BLOQUEIA** em `blocking: true` open-questions + cadeias story→BDD→task→test quebradas. (Funil: sub-agentes marcam, conductor pergunta, readiness barra.)
- **Grill-with-docs é uni-direcional.** O conductor lê graph (Q1 similar-features, Q11 reusable-helpers) + inventory (design-system/i18n/conventions) + memory L2/L3 + cards — mas só pra **suprimir** perguntas e **semear** defaults ("When NOT to ask: se L2/L3 tem com confidence>0.85"). **Nunca confronta o pedido**: não existe "o grafo mostra que `bonsai-list` já persiste um starred flag — você está duplicando?", nem desafio de terminologia/decisão-N. Esse é exatamente o nicho do skill externo `grill-with-docs`, sem equivalente no repo.
- **Enforcement é confiança-de-prompt + 1 ponto-cego.** O readiness-reviewer declara "não sou o enforcer; o conductor aplica recusando emitir `readiness=ready`". E o scan de forbidden-phrases (`TBD|TODO|FIXME|placeholder`) **não inclui `needs-elicitation`** — um campo marcado `needs-elicitation` que o conductor não promova a `blocking` pode escapar como "ready" se a cadeia story→task ainda fechar nominalmente ("thin-but-structurally-complete").
- **TUDO inerte sem DRIVER-001.** Os agentes não são auto-despachados — um host LLM precisa carregar `agents/*.md` e dirigir o intent loop, e `forge init` não instala nada que ensine isso. Neste repo de maintainer, `CLAUDE.md` + `.claude/rules/*` dirigem (por isso funciona aqui); num consumidor fresco, **ninguém grilha** — `forge plan` morre no 1º prompt.

---

## 4. Veredito sobre `loops-abertos.md` (fact-check claim-by-claim)

`loops-abertos.md` é o **melhor** dos relatórios do opencode (mais aterrado que o `auditoria-pre-piloto.md`), mas ~metade dos itens-título é falso/by-design.

| Claim | Veredito | Nota |
|---|---|---|
| **L1** casing `{{FEATURE_SLUG}}` vs `{{feature_slug}}` | **REAL (estreito)** | Confirmado. Mas blast-radius = 1 token (slug), não 480 — templates são LLM-filled BY DESIGN. **HIGH, não P0.** |
| **L3** ambiguity-map morto / nunca lido | **REAL** | Confirmado (§2 acima). Importante pro grill. |
| **L4** `verified`/`paused`/`not-started` phantom states | **REAL** | Declarados em `_VALID_STATES`, nunca escritos; `verified` é prometido por `ROADMAP.md:35` + `07-discipline.md:675`; `implement` vai `implementing→done` direto. Doc↔código. |
| **L5** cards → plan/implement disconnect | **PARCIAL** | plan.py tem 0 refs a cards; `_templates_dir()` = `FORGE_HOME/templates/` (flat). init faz `merge_contributions` mas **não materializa** templates mergeados; só `forge raw rebuild-templates` faz a ponte — mutando o FORGE_HOME **global** (compartilhado). "Investimento desperdiçado" é overstated; "fluxo default ignora cards" é correto. |
| **L13** `aborted` dead-end | **REAL** | Sem transição de saída; recovery = deletar L1 + recomeçar. Parcialmente by-design (Decisão 27), mas sem caminho de recovery. |
| L8/L16 verify não checa placeholders crus | **REAL (menor)** | `forge verify` não escaneia `{{...}}`. Útil como gate AI-first pequeno. |
| **L6** MCP crash em `forge plan IN-37234` | **FALSO** | Inalcançável 2×: (a) plan/implement têm **zero** chamadas a `engine.mcp` (`_TICKET_PATTERN` só bumpa subtype); (b) slug uppercase é rejeitado antes. `doctor` SKIPa o probe. |
| **§5 / L2** implement "retorna antes dos gates / não executa nada" | **FALSO** | `_apply_mode_handoff` RODA `_run_cc_gate` + `_run_secrets_gate` (bloqueiam e retornam em falha). O handoff de autoria-de-código é o exec model canônico (Decisão 22), não stub quebrado. |
| **L7** `forge qa` vazio sem dispatch | **BY-DESIGN** | Engine faz scope/sandbox/schema/synthesis; a inteligência são os agentes despachados (conductor + 4 auditores). Arquitetura documentada. |
| **§7** 6 gates futuros não implementados | **BY-DESIGN/honesto** | Docs (`08-session-handoff.md:223`) os framam como **futuro** ("destrava Wave R1+"). A citação "`07-discipline.md §7`" do relatório é **fabricada** (lá §7 é Pause-vs-abort). |
| **§9** `distiller.apply_proposal_to_l2` "6 kinds NotImplementedError" | **FALSO/invertido** | Trata 9 kinds (promote/consolidate/forget + 6 reuse); levanta só pra kind **desconhecido**. `forge evolve --apply` normal nunca cai nisso. |

---

## 5. Findings novos verificados (entram na consolidada)

| ID | Sev | Resumo | Fix |
|---|---|---|---|
| **CASING-BUG** | ALTO | `plan.py:401` substitui `{{FEATURE_SLUG}}` (uppercase) — templates usam lowercase → no-op; nem o slug é preenchido | trocar pra `{{feature_slug}}` + substituir tokens triviais que o engine conhece (slug, data, source, paths) |
| **AMBIGUITY-DEAD** | ALTO | ambiguity-map/open-questions é scaffolding morto no engine; zero detecção de sparseness; readiness só faz grep de verdict que o host escreveu | wirar o grill (ver §6); engine-side completeness check no intake preenchido antes de avançar wave |
| **PLAN-FRONTDOOR** | MÉDIO | `forge plan` rejeita ticket/texto-livre com `SystemExit` (exit 1, bypassa escada); sem derivar slug nem elicitar | front-door que aceita ticket/frase → deriva slug + semeia intake (ponto de entrada do grill); trocar `SystemExit` por mensagem mentor-calmo + exit-code correto |
| **PHANTOM-STATES** | MÉDIO | `verified`/`paused`/`not-started` declarados mas nunca escritos; `verified` prometido por docs | implementar a transição `verified` (em `forge verify` sucesso) OU remover do enum + corrigir docs |
| **CARDS-DISCONNECT** | MÉDIO | fluxo default (`init`→`plan`) ignora contribuições de template/validator dos cards; só `forge raw rebuild-templates` faz a ponte (mutando FORGE_HOME global) | materializar merge per-projeto (`.claude/forge/templates/`) e fazer plan ler de lá; wirar `merged.validators` na cascade |
| **ABORTED-DEADEND** | BAIXO | sem recovery de `aborted` (delete + restart) | `forge reconfigure --un-abort` (ou opção no undo) restaurando de `history.jsonl` |
| **PLACEHOLDER-VERIFY** | BAIXO | `forge verify` não detecta `{{...}}` crus → template vazio passa como "verificado" | validador pequeno que escaneia placeholders não-preenchidos em artefatos de feature |

---

## 6. Design: onde encaixa skill/agente (grill AI-first)

Duas necessidades distintas, dois lares distintos.

### A. grill-with-docs → nova **Phase 2.5 "Grounded challenge"** no `planning-conductor` (reusa o que já existe)
Maior valor, menor fricção, e cabe no modelo orquestrador-dirige-tudo. O conductor já lê todas as fontes; falta só o passo **adversarial** (confrontar o pedido, não só semear default). Inserir entre Phase 2 (Ambiguity Map) e Phase 3 (Elicit):
- **Reusa (já wired):** graph **Q1** similar-features (duplicação / oferecer "Estender" Gap 9), graph **Q11-Q17** reuse-intelligence (helper/component já existe), `engine/inventory/` (terminologia/componente vs design-system), memory **L2 `decisions-frozen` + L3** (contradiz decisão D-N / preferência).
- **Output:** cada contradição vira uma pergunta na Phase 3 AskUserQuestion existente (com a citação-do-doc como o "por quê") + entra no `rationale-trace.yaml`. Sem artefato novo.
- **Forma:** inline na Phase 2.5 (conductor já é `opus` e tem o contexto) OU um `grill-with-docs-agent` read-only dedicado, se quiser reusar fora do `forge plan` (ex.: antes do `forge implement`).

### B. O **driver SKILL.md** (DRIVER-001) é o carrier — o grill loop É o intent loop
Toda pergunta de grill é emitida como `<FORGE_INTENT/>`; sem o driver, os markers de grill caem no vazio igual a qualquer `ask*` hoje. **A skill habilita o grill existente E o novo.** (P0, Decisão-22-safe.)

### C. Tornar o grill **enforçável** (não só performado)
Adicionar scan de `needs-elicitation: true` no `readiness-reviewer` Phase 5 (junto do forbidden-phrases) — block em contract specs. Fecha o ponto-cego "thin-but-structurally-complete" e torna o "mark and proceed" dos sub-agentes seguro por construção.

### D. Front-door do `forge plan` (entrada do grill)
Aceitar ticket/frase → derivar slug + semear o intake a partir do ticket/sentença (e, se ticketing configurado um dia, do fetch). Trocar o `raise SystemExit` por mensagem mentor-calmo + exit-code correto. É onde o usuário naturalmente "joga" um pedido cru pro forge transformar.

### NÃO virar verbo novo
`forge grill <slug>` é o pior fit — duplicaria o carregamento de contexto do conductor; grill é **parte do planejamento**, não fase separada. Lar correto: **Phase 2.5 do conductor (lógica) + driver SKILL.md (entrega)**. Mantém o engine emitindo intent e a LLM dirigindo (exec model canônico).

---

## 7. Implicação pro roadmap (atualiza a consolidada §6)

- **P0** ganha clareza: o **driver SKILL.md** não só faz o forge funcionar — é o que **habilita o grill** (loop idêntico). E **CASING-BUG** entra no P0 de output/qualidade (fix de 1 char).
- **P1** ganha: **grill-with-docs (conductor Phase 2.5)** reusando graph/inventory/L2; **PLAN-FRONTDOOR** (derivar slug + elicitar); **AMBIGUITY-DEAD** (completeness gate + enforce needs-elicitation no readiness).
- **P2** ganha: PHANTOM-STATES, CARDS-DISCONNECT, ABORTED-DEADEND, PLACEHOLDER-VERIFY.

> **Conclusão (mentor calmo):** a pergunta "o forge grilha?" tem resposta dupla. No engine, não — ele rejeita o que não é slug e empurra ambiguidade pro usuário/LLM, com a maquinaria de ambiguity-map morta. Nos prompts, sim, e bem feito — mas só o conductor, só uni-direcional (nunca confronta o pedido), e **inerte sem o driver**. O caminho AI-first não é um verbo novo: é (B) entregar o driver SKILL.md que carrega o intent loop, (A) dar ao conductor um passo de "grounded challenge" que reusa o grafo + inventory + decisões-frozen pra confrontar o pedido, (C) tornar o readiness enforçável, e (D) abrir um front-door que aceita um ticket ou uma frase e transforma em slug + intake semeado. O `loops-abertos.md` acertou os loops de ambiguidade e os phantom states; errou ao alarmar MCP/implement/qa, que ou são inalcançáveis ou são o exec model por design.
