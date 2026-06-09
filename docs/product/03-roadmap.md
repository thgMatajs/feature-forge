# Roadmap-produto do feature-forge

> **Cross-ref:** Este doc é referenciado por [`00-prd.md`](00-prd.md) §7. Complementa [`docs/design/ROADMAP.md`](../design/ROADMAP.md) (lente técnica — Phases 6-13) com lente produto (ondas agrupadas por outcome de persona). Personas citadas vivem em [`01-personas.md`](01-personas.md); cenários em [`02-scenarios.md`](02-scenarios.md).

3 ondas agrupadas por outcome de persona + anti-roadmap explícito + cross-ref bidirecional pro roadmap técnico.

A lente "produto" responde "quem ganha o quê, e quando" — a lente "técnica" responde "qual Phase entrega isso, e como". Os dois eixos andam juntos mas não são intercambiáveis:

- Uma onda produto pode compor 1 ou mais Phases técnicos
- Um Phase técnico pode ficar fora de qualquer onda quando é demand-driven sem persona-âncora dedicada
- Uma onda fechada aqui dispara update no ROADMAP técnico em paralelo (auditoria mensal protege o loop)
- Uma decisão de ROADMAP técnico (ex: adicionar Phase 14 novo) não cria onda automaticamente — exige justificativa persona-impact pra entrar aqui

**Resumo executivo das 3 ondas:**

| # | Onda | Persona-âncora | Versão alvo | Status |
|---|---|---|---|---|
| 1 | Autopilot completo | Marina | v1.3 → v1.4 | planned (próxima) |
| 2 | Catálogo evolutivo + colaboração | Lucas + Bruno | v1.5 → v2.0 | planned (depois de Onda 1) |
| 3 | Inteligência adaptativa | Todas (transversal) | v2.x | aspiracional |

---

## §1 — Princípios do roadmap-produto

Esta lista define o que entra (e o que NÃO entra) no eixo produto. Diverge intencionalmente do roadmap técnico em [`docs/design/ROADMAP.md`](../design/ROADMAP.md) §Princípios do roadmap, que é mais incremental e menos amarrado a persona.

Os dois rosters convivem — o técnico organiza entrega de capabilities (Phases 6-13, cards reservados, polish items); o produto organiza outcome perceptível pra Marina/Bruno/Lucas/Carolina (ondas com persona-âncora e OKRs).

**1. Demand-driven**

- Onda entra com base em demanda real observada em campo: ticket P0 recorrente em squad consumidora, squad sufocada por overhead operacional, dev solo travada em refazer arquitetura por feature.
- Não entra em "checklist técnico bonito" nem em paridade com competidor. Sem onda inflada por entusiasmo.
- Quando demanda é fraca, fica em backlog (`04-pending.md`) até virar concreta.
- Quando demanda é forte mas viola visão, vira anti-roadmap (§6).

**2. Persona-impact**

- Cada onda lista qual persona ganha o quê, com nome canônico de [`01-personas.md`](01-personas.md).
- "Phase 6 done" não é outcome de produto; "Marina deixa de fazer manual edits per task" é.
- Persona-impact obriga conversão de capability técnica em mudança de fricção sentida pela persona.
- Se uma onda não consegue articular "X persona deixa de fazer Y" ou "X persona passa a conseguir Z em N min vs antes", não é onda — é Phase técnico re-embalado em apresentação atraente. Volta pro eixo técnico até articular impacto persona.

**3. Backwards-compat**

- Schema migrators via `forge raw migrator-N-to-M` (Decision 9, locked).
- Nenhuma onda quebra silenciosamente projetos antigos.
- Rupturas exigem: migrator escrito + entry em CHANGELOG + nota em handoff + smoke test em projeto-canon.
- Projetos consumidores rodando v1.2 não devem precisar reescrever artefatos pra entrar em v1.4 — migrator faz upgrade transparente, ou onda não shippa.

**4. Auditável**

- Cada onda fechada vira entry em `CHANGELOG.md` (`### Added` ou `### Changed`) e linha em `docs/design/08-session-handoff.md §Última atualização`.
- Sem ondas declaradas "done" sem trilha escrita.
- Auditoria mensal manual (ver `.claude/rules/README.md §Auditoria contínua`) re-verifica que entry existe + que ROADMAP técnico foi atualizado em paralelo, fechando o loop bidirecional.
- Quando entry está ausente mas commits mostram trabalho entregue, é dívida — abre task de doc-sync pra fechar antes da próxima onda começar.

**5. Anti-roadmap explícito**

- Listar o que **NÃO** entrará é tão importante quanto o que entra (§6).
- Anti-roadmap é a defesa do produto contra scope creep — "todo mundo pede X" não é razão suficiente; razão é tripla:
  - Cabe na visão de [`docs/design/00-vision.md`](../design/00-vision.md)
  - Atende persona declarada em [`01-personas.md`](01-personas.md)
  - Não viola decisão locked em [`docs/design/01-decisions.md`](../design/01-decisions.md)
- Quando os três critérios não casam, vira linha em §6 com rationale escrito + cross-ref pro contract violado.
- Revisão de anti-roadmap exige revisita formal do contract referenciado (Mandamento 1 do projeto — não silent drift).

---

## §2 — Onda 1: "Autopilot completo" (v1.3 → v1.4)

A Onda 1 é a onda que fecha o ciclo planning → implementing → verified → done sem dev fazer manual edit per task. Em v1.2.0 o `forge plan` está completo (5 waves end-to-end com auto-resume), `forge verify` cobre 15 validators em cascade fail-fast, `forge graph` indexa 17 queries — mas `forge implement` ainda é stub manual: o engine renderiza handoff em texto e o dev aplica diff à mão. Onda 1 fecha esse gap.

**Persona primária impactada**

- **Marina** (mobile dev solo KMP/Android, PRIMÁRIA de [`01-personas.md`](01-personas.md) Camada A). É a persona-âncora; toda decisão da Onda 1 é otimizada pra reduzir fricção dela primeiro. O day-in-life de Marina em [`01-personas.md`](01-personas.md) §Marina §Day-in-life típico assume `forge implement` funcionando — Onda 1 entrega exatamente isso.

**Personas secundárias**

- **Carlos** (Android-only, [`01-personas.md`](01-personas.md) Camada B) — herda o autopilot, sem cards iOS/KMP no caminho gerando ruído. Stack 100% Android (Compose + Hilt-OU-Koin + Retrofit + Room) ganha autopilot na mesma proporção da Marina.
- **Lucas** (iOS-only, Camada B) — caveats v1.2 não melhoram nessa onda (Onda 2 endereça preset `ios-only`), mas autopilot reduz custo do workaround manual que Lucas usa hoje via `forge reconfigure` + overlay local Gap 5.
- **Carolina** (iniciante/onboarding, Camada B) — autopilot vira material didático operacional. "Vê o engine aplicar diff, aprende o pattern fazendo" substitui parcialmente "aprende por osmose de PR review", que era o caminho default em squad sem ferramenta dirigida.
- **Sub-agente Claude** (persona técnica não-humana, Camada A) — passa de "renderizar template" pra "aplicar diff end-to-end com extension-points respeitados". `allowed_files` declarado na task vira contrato auditável no diff, não apenas anotação na agenda.

**Phase técnico correspondente**

- [`docs/design/ROADMAP.md`](../design/ROADMAP.md) **Phase 6** (Apply Mode automatizado), 4 sub-fases:
  - **6.1** LLM/sub-agent invocation real — integrar `engine/plan.py` + `engine/implement.py` com Anthropic SDK (ou similar) para invocar sub-agents reais durante waves
  - **6.2** Apply Mode automatizado — `forge implement` aplica diff gerado em vez de handoff manual; pre-commit review automatizado interno; out-of-scope detection real
  - **6.3** Atomic commit + completion evidence — commit canônico + evidence record + L1 status update automático
  - **6.4** Retrospective auto-trigger — última task verificada dispara retrospective-agent automaticamente

A Onda 1 é Phase 6 visto pela lente persona. 1:1 — sem desfasagem, sem onda compondo múltiplas Phases.

**Outcome esperado**

- `forge implement` deixa de ser stub manual → autopilot real. Marina passa de "engine ajuda metade do trabalho" pra "engine dirige, Marina confirma ou redireciona". O salto não é em capability nova; é em fechamento de loop — Phase 6 amarra cards atômicos + memory + reuse-intelligence (já entregues v1.0-v1.2) em fluxo end-to-end automatizável.

- Sub-agente Claude pode aplicar diff end-to-end (não só renderizar template) — `allowed_files` respeitado por diff real submetido ao engine, não por contrato declarativo que depende de Marina conferir. Pre-commit review do diff é parte do contrato do sub-agente, não responsabilidade da Marina pós-dispatch.

- Pre-commit review automatizado detecta out-of-scope com 3-caminhos canônico (atualizar contract / revert / split nova task). Quando sub-agente extrapola escopo declarado em `allowed_files`, gate dispara 3-caminhos antes do commit — não depois em PR review humano, onde o custo de correção é maior.

- Atomic commit canônico (`{TASK-NNNN}: {description}`) sem Marina escrever message manual. Disciplina mecânica de commit (escopo respeitado, contract referenciado, evidence link explícito) vira responsabilidade do engine, não da memória de Marina às 14h de uma terça apertada.

- Retrospective dispara automaticamente após última task verificada — `proposed-evolutions.yaml` populado pra `forge evolve`. Marina não precisa lembrar de rodar retro; engine puxa o gatilho na transição de estado `verified → done`. Cena 14 do roteiro `forge-implement-roteiro.md` deixa de ser aspiracional e vira default.

**OKRs aspiracionais**

- **Time-to-merge** (ticket → PR merged): ≤ 4h por feature product nova. Hoje ~6-8h em projeto product-grade com stack canon — Wave A-E já leva 15-20min, mas implement + verify + commit ainda absorve 4-6h adicionais quando dev edita à mão. Onda 1 corta isso pra 30-60min de "engine entrega + Marina confirma".

- **Manual edits per task**: 0 (hoje 5-15 por task em média). Engine vai aplicar diff e Marina apenas confirma/redireciona via 3-caminhos quando out-of-scope dispara. Edit manual passa de fluxo principal pra exceção esporádica.

- **Regression rate cross-feature** (bug retornando em feature anterior depois de 3 sprints): ≤ 2% (hoje ~5-8% empírico). Atalho-virou-hábito de pular regression test em bugfix urgente cobra preço no quarter seguinte; com regression test obrigatório aplicado pelo engine, o débito sai do fluxo.

- **L1 auto-status updates**: 100%. Transições `implementing` → `verified` → `done` sem Marina tocar `status.json` manualmente. Transição de estado é parte do contrato do engine, não do dev. Inconsistência entre estado-de-arquivo e estado-mental do dev some.

**Anti-feature explícito (NÃO entra na Onda 1)**

- **Automatizar decisão de produto** — engine pode sugerir subtype / cards / threat model com base em ticket-pattern + L2 history, mas Marina (ou Bruno) decide WHAT. Engine dirige HOW. Princípio non-negociável (Decision 22 + [`docs/design/00-vision.md`](../design/00-vision.md) §What feature-forge is NOT). Mesmo com Apply Mode automatizado, gate de decisão produto permanece humano via 3-caminhos.

- **Pre-commit review humano automatizado** — Diego (code reviewer humano, [`01-personas.md`](01-personas.md) Camada C) ainda decide se o PR merge. Forge detecta violações mecânicas + escopo via pre-commit review automatizado interno (Phase 6.2); veredito final em arquitetura/produto é humano. Onda 1 não toca essa fronteira.

- **IDE plugin (VSCode / IntelliJ / Xcode)** — CLI-first permanece. Integração via shell hooks já cobre dispatch transparente; plugin nativo é IDE-coupling que viola portability ([`docs/design/00-vision.md`](../design/00-vision.md)). Marina invoca `forge implement` em qualquer terminal; nada de "instale o plugin Y pra funcionar".

**Sinais de prontidão pra Onda 1 entregar**

- LLM/sub-agent SDK escolhido + smoke test funcionando em projeto-canon (`engine/plan.py` + `engine/implement.py` invocam sub-agent e recebem diff válido)
- Pre-commit reviewer-agent prompt estabilizado com 3-caminhos canônico em out-of-scope detection
- Apply Mode aplica diff em projeto-canon (MeoBonsai fixture) sem manual intervention em ≥ 3 features consecutivas
- Atomic commit + evidence record + L1 transition `verified → done` automático em fluxo end-to-end
- Retrospective auto-trigger dispara em fim de feature; `proposed-evolutions.yaml` populado e revisável via `forge evolve`

**Cenário ilustrativo (variação de C2 de [`02-scenarios.md`](02-scenarios.md))**

- 9:15 — Marina abre `forge plan IN-42100 lembrete-rega`; Wave A-E em 15min (já funcionava v1.2)
- 10:45 — Marina abre `forge implement lembrete-rega`; em vez de ler handoff manual e editar à mão, sub-agente Claude (Phase 6.1) recebe context-pack + render diff dentro de `allowed_files` declarado por task
- 11:00 — Pre-commit reviewer (Phase 6.2) detecta task 3 tentou mexer em `engine/cli.py` que não está em `allowed_files`; 3-caminhos dispara, Marina escolhe "atualizar contract" pra incluir o arquivo
- 12:30 — 8 tasks aplicadas + commits atômicos (Phase 6.3) + L1 transitions automáticas; Marina rodou `forge verify` no fim, verde
- 12:45 — Retrospective auto-trigger (Phase 6.4); 3 evolutions L2 propostas em `proposed-evolutions.yaml`; Marina revisa via `forge evolve`, aceita 2 reject 1
- **Total**: 3h30 ticket → PR (vs 6-8h em v1.2). Atinge OKR ≤ 4h.

---

## §3 — Onda 2: "Catálogo evolutivo + colaboração" (v1.5 → v2.0)

Onda 2 amplia o canon pra cobrir personas secundárias com qualidade-canon (não só "funciona via overlay local") e abre caminho pra squads maiores rodarem multi-dev opcional. Em v1.2.0 o catálogo cobre KMP/Android primeiro, iOS via workaround — Onda 2 inverte essa hierarquia pra Lucas e Carlos terem preset dedicado, e amplia `forge status` pra Patricia/Bruno usarem o board com mais granularidade.

**Persona primária impactada**

- **Lucas** (iOS-only sem KMP, Camada B de [`01-personas.md`](01-personas.md)) — Onda 2 entrega preset `ios-only` e cards iOS standalone. Caveats v1.2 da tabela de Lucas em [`01-personas.md`](01-personas.md) §Lucas (`forge init` auto-detection retorna 0 signals; cards canon iOS limitados a `swiftui-screens`, `swiftui-navigation`, `auth-jwt-bearer`, `crashlytics`, `firebase-storage`) param de doer.

- **Bruno** (tech lead/staff engineer, Camada A) — squad maior + multi-dev opcional + filtros operacionais em `forge status`. Bruno passa de "supervisiona por amostragem em PR review" pra "supervisiona com filtros temporais e por squad em `forge status`". Multi-dev opcional resolve `04-pending.md §Gap 6`, tirando squads grandes do workaround "divida em features menores".

**Personas secundárias**

- **Patricia** (PM / Product Owner, Camada C) — `forge status --release-q3` ganha filtros temporais e por sprint sem violar boundary. Forge não estima/scheduela; só dá visibility filtrada. Patricia continua dona da estimativa em Linear/Notion; só ganha lente operacional do board mobile em tempo real.

- **Carolina** (iniciante/onboarding, Camada B) — mais material didático em cards locais consolidados. Aprende stack-specific pattern do projeto via overlay maduro com mesmas garantias do canon (validators, README substantivo, agent-contributions). Cards locais deixam de ser "exceção mal documentada" pra serem "caminho oficial documentado".

**Phase técnico correspondente**

- [`docs/design/ROADMAP.md`](../design/ROADMAP.md) **Phase 7** (Tree-sitter / AST parsers) — habilita semantic reuse mais robusto pra UX nativa iOS (parser regex pragmático tem false-positive rate alto em Swift idiomático denso, especialmente em projetos com lots de Combine + property wrappers)
- **Gap 5 maturity** — cards locais como caminho oficial pra stack-specific, com piso de qualidade enforced via validators próprios
- **Multi-dev opcional** — resolve [`docs/design/04-pending.md`](../design/04-pending.md) §Gap 6 deferred (merge-strategy formal documentada + phase-lock cross-dev visível)

**Outcome esperado**

- Preset `ios-only` shippa → Lucas tem UX nativa em vez de workaround manual via `forge reconfigure`. Auto-detection em `forge init` passa de "0 signals positivos" pra "preset detectado". Cards canon iOS aplicam sem cards KMP/Android no caminho gerando ruído visual e validações irrelevantes.

- Cards canon iOS standalone (sem assumir KMP shared) — Alamofire / KeychainAccess / Combine / CoreData padrões viram canon, não overlay local obrigatório. Squad iOS puro deixa de depender de Gap 5 pra stack basal; Gap 5 fica reservado pra customizações genuinamente locais (helper específico da empresa, design system proprietário).

- Marketplace **LOCAL** de cards maduro — Gap 5 cobre `.claude/cards/local/<name>/` versionado em repo do projeto consumidor; squad acumula ≥ 5 cards locais por projeto e engine reconhece como caminho oficial (não fallback). Cards locais ganham mesmas garantias de canon (validators, agent-contributions, README substantivo, smoke test obrigatório).

- Multi-dev opcional — 2 devs simultâneos na mesma feature, merge-strategy resolvida via metadata. Quem está em qual wave; phase-lock cross-dev visível em `forge status`. Resolve [`docs/design/04-pending.md`](../design/04-pending.md) §Gap 6 — saída de "feature dividida em N features menores" pra "feature genuinamente compartilhada" quando squad escolher.

- Patricia: `forge status --release-q3` (filtros temporais) + `forge status --squad=mobile-android` (filtros organizacionais). PM ganha visibility mais granular sem violar boundary — forge continua não estimando nem priorizando, só dando recorte filtrado do board read-only. Não substitui Linear/Notion; complementa com lente operacional de feature-em-execução.

**OKRs aspiracionais**

- **Preset count**: 1 → ≥ 3 (`kmp-mobile`, `ios-only`, `android-only`). Lucas, Carlos e Marina cobertos por preset dedicado em vez de manual via `forge reconfigure`. Onboarding squad nova com `forge init` detecta preset correto sem dev intervir; auto-detection passa de fraca pra robusta.

- **Cards locais aceitos por squad** (em projeto real, não fixture): ≥ 5 por squad madura. Indicador de Gap 5 atingiu maturidade operacional. Cards locais sobreviverem ≥ 2 retrospectivas sem serem deprecados também conta como sinal de qualidade — overlay efêmero que entra-e-sai a cada sprint não vale como métrica.

- **Features merged sem conflict em multi-dev**: ≥ 10 cumulativo cross-projetos. Multi-dev opcional saiu do `Gap 6 deferred` pra fluxo testado em campo, com merge-strategy formalizada e phase-lock confiável. Conflitos isolados são esperados em multi-dev real; meta é que NÃO sejam regra.

**Anti-feature explícito (NÃO entra na Onda 2)**

- **Marketplace pública de cards** — viola Decision 22 (no runtime deps em outras skills). Gap 5 cobre apenas local versionado em `.claude/cards/local/` por projeto consumidor; pública exigiria runtime registry + signing + scoring → quebra portability + viola Decision 18 (snapshot copy local via `forge init`). Cards comuns entre squads compartilham via cópia explícita, não via fetch dinâmico de registry.

- **Hosted service / SaaS** — CLI-first permanece (Decision 18 + 22). Snapshot copy local em `~/Documents/feature-forge/` (ou equivalente) é parte do contrato com o projeto consumidor; SaaS é outra ferramenta, não feature-forge evolução. Quem quiser dashboard hosted pode construir em cima do output do `forge status`, mas o engine não vira backend.

- **Multi-target watchOS / Wear OS / tvOS** — Gap 9 revisita 2026-06-03 moveu pra **out-of-scope permanente** (ver §6). Caminho oficial pra plataforma exótica é Gap 5 overlay local; canon expansion comprometeria foco em Android + iOS + KMP + Web sem ganho proporcional de adoção. Já tentamos relaxar duas vezes em sessões anteriores — anti-roadmap reafirma.

**Sinais de prontidão pra Onda 2 entregar**

- Tree-sitter grammar pra Kotlin + Swift + TypeScript adotada com cobertura ≥ 90% em projetos-canon
- Preset `ios-only` definido com cards canon standalone + auto-detection em `forge init` retornando signal positivo em projeto iOS puro
- Multi-dev opcional documentado em `docs/design/07-discipline.md §novo` + smoke test multi-dev em fixture com 2 contas simultâneas
- `forge status` ganha sub-comandos `--release-<Q>` + `--squad-<name>` com output read-only filtrado
- Gap 5 maduro: ≥ 5 cards locais em projeto-canon sobrevivendo ≥ 2 retros sem deprecation; piso de qualidade enforced via validator próprio

**Cenário ilustrativo (Lucas em projeto iOS puro)**

- Dia 1 — Lucas abre `forge init` em projeto iOS-only novo; auto-detection (Phase 7 AST-based) identifica Swift puro + SwiftUI + Combine, sugere preset `ios-only`
- Lucas confirma; preset aplica cards iOS canon (`swiftui-screens`, `swiftui-navigation`, `auth-jwt-bearer`, `crashlytics`, `firebase-storage`, `alamofire`, `keychainaccess`, `coredata`)
- Cards KMP/Android NÃO entram (sem signal positivo); zero ruído de `kmp-shared`/`koin-annotations`/`retrofit-client`
- Dia 2 — Lucas planeja feature primeira em projeto; Wave A-E fluem com cards iOS direto, sem workaround manual; squad iOS puro deixa de depender de Gap 5 pra stack basal
- **Outcome**: caveats v1.2 da tabela de [`01-personas.md`](01-personas.md) §Lucas saem da realidade. Tabela ganha update na revisita Onda 2 fechada.

---

## §4 — Onda 3: "Inteligência adaptativa" (v2.x — aspiracional)

Onda 3 é aspiracional — não tem versão alvo fixa, depende de Phase 7 entregue (Onda 2) + dados L2/L3 acumulados em campo + LLM real-time signals viáveis. Listar Onda 3 aqui agora não compromete entrega; serve pra evitar que iniciativas aparentemente isoladas na Onda 1 ou Onda 2 destruam compatibilidade futura com a direção adaptativa.

**Persona afetada**

- **TODAS** (transversal). Marina, Bruno, Sub-agente Claude (Camada A); Carlos, Lucas, Carolina (Camada B); Patricia, Diego (Camada C). Onda 3 não favorece persona única; eleva o nível de toda a stack do produto. Cada persona ganha algo diferente — Marina ganha menos drill-down; Bruno ganha L3 cross-project; Carolina ganha `forge ensina`; Diego ganha PR mais previsível com menos exceção.

**Phase técnico correspondente**

- [`docs/design/ROADMAP.md`](../design/ROADMAP.md) **Phase 7+** (Tree-sitter AST semantic ativo + idioma denso resolvido com confidence alta) + **LLM real-time signals** (sub-agent consulta L2 + L3 durante wave, não só no final em retrospective). Aspiracional — não bloqueia v2.0 baseline; entra quando Phase 7 estiver entregue e L2/L3 tiverem dados suficientes pra alimentar sugestões com confidence > 80%.

**Outcome esperado**

- **Reuse-intelligence semantic**, não syntactic. Resolve `kmp-migration-candidate shallow confidence` (Q16 do graph fica forte com confiança alta); engine entende equivalência semântica de `validateName` em Kotlin + Swift + TypeScript sem dependência de regex pragmático. Resultado: detecção de near-duplicate com false-positive rate < 5%, contra ~20-30% empírico do parser regex v1.

- **Conductor lembra decisões cross-feature** — L3 cross-project memory ativa. Sub-agente sabe que "essa squad já decidiu X em 12 features anteriores" e propõe seguir o pattern em vez de perguntar do zero. L3 é read-only mas auto-injetado em context-pack quando aplicável; sub-agente não escreve em L3, só consome.

- **Engine sugere subtype / cards / threat model** com base em L2+L3 history, não só catálogo estático. Marina abre `forge plan IN-NNNNN`, engine sugere subtype antes da Cena 2.5 confirmar — hipótese vem do histórico cumulativo, não da heurística estática de ticket-pattern. Sugestões vêm rotuladas com confidence ("85% confiança via 12 features similares anteriores") pra Marina avaliar.

- **Carolina**: `forge ensina <pattern>` (verbo novo Onda 3?) — explora cards + decisões com lente didática. Dev iniciante aprende padrão arquitetural conversando com o engine ("por que escolhi Koin aqui?", "qual o trade-off entre Hilt e Koin pra Android-only?"), não só fazendo PR após PR. Verbo `ensina` é experimental; pode virar `forge explica` ou `forge porque` na implementação real — nome importa menos que o verbo existir.

- **Sub-agente Claude** opera com **confiança histórica** — sabe que decisão X foi tomada 12x antes em features similares; reduz drill-down rounds porque sub-agente já entra com hipótese baseada em L2+L3. Permanece preservado: 3-caminhos em qualquer gate; hipótese é ponto de partida, não veredito. Sub-agente confiante ainda pergunta quando ambíguo; só pergunta menos coisa óbvia.

**OKRs aspiracionais**

- **Drill-down rounds** (perguntas Wave A médias por feature): 2 → 0.5 (engine entra com hipóteses, persona confirma ou redireciona). Métrica observável em telemetria do conductor (count de iterações por wave); baseline atual é instrumentável já em v1.2 via L1 status.

- **Questions per Wave A**: −30% (menos pergunta redundante por feature; engine consulta L2 antes de perguntar). Redução não é "engine pergunta menos cega"; é "engine pergunta o que efetivamente faltou no L2+L3, não o que já está documentado em pattern conhecido".

- **L2 patterns auto-inject**: ≥ 60% das features. Hoje L2 cresce mas auto-injeção em template é manual via `forge evolve`; Onda 3 vira automático com confirmação de persona. 60% é piso aspiracional; 100% não é meta porque alguns patterns são context-dependent e injection cega quebra o pattern em casos legítimos de divergência.

**Anti-feature explícito (NÃO entra na Onda 3)**

- **Tomar decisões sem confirmação humana** — sempre 3-caminhos antes de qualquer mutação. Engine pode sugerir com alta confiança; Marina/Bruno confirma. Princípio 3-caminhos é load-bearing ([`docs/design/07-discipline.md`](../design/07-discipline.md) §1) e Onda 3 não relaxa, mesmo quando confidence é > 95%. Confidence alta ≠ permissão pra pular gate.

- **Substituir mentor humano** — engine ensina padrões mecânicos (cards, contracts, validators, naming, structure); Bruno/Diego ensinam contexto + cultura + julgamento situacional. Forge não substitui peer review humano nem mentoria interpessoal. `forge ensina` é didático sobre o canon, não psicológico sobre carreira.

**Sinais de prontidão pra Onda 3 entregar**

- L2/L3 cross-project memory com ≥ 50 features acumuladas em projeto-canon (dados suficientes pra confidence > 80% em sugestões)
- LLM real-time signals técnico viável (latência < 2s pra consulta L2+L3 durante wave; custo aceitável pra projetos consumidores)
- Phase 7 (Tree-sitter AST) entregue como pré-requisito — semantic matching de patterns cross-language
- `forge ensina` (ou verbo equivalente) com prompts didáticos curados + smoke test em projeto-canon com dev iniciante de teste
- Telemetria do conductor (drill-down rounds, questions per wave) instrumentada e mensurável vs baseline v1.2

**Cenário ilustrativo (Marina + Carolina em Onda 3 entregue)**

- Marina abre `forge plan IN-50000 alerta-pragas`; conductor consulta L2+L3, detecta squad já decidiu 12 features-similares de "alerta + notificação periódica" com pattern `WorkManager + LocalDatabase + AnalyticsEvent canonical naming`
- Conductor sugere subtype=product + cards `koin-annotations`+`workmanager-periodic`+`firebase-analytics` com "92% confiança via 12 features anteriores"; Marina confirma sem drill-down
- Wave A termina em 2 minutos com 1 pergunta (não 4-5 como em v1.2) — perguntas vinham de "qual o user value?" + "qual platform suporte?" + "qual data class?"; L3 já tem respostas-padrão pra essa squad
- Paralelo: Carolina (dev iniciante, na mesma squad) abre `forge ensina workmanager-periodic`; engine renderiza didática do card + 3 decisões de WHY tomadas em features-similares + trade-offs vs alternativas (AlarmManager / Coroutines Job)
- **Outcome**: Marina entrega feature 30% mais rápida em planning; Carolina aprende pattern conversando em vez de só fazendo PR. Atinge OKRs `Drill-down rounds ≤ 0.5` + `Questions per Wave A −30%`.

---

## §5 — Matriz Eisenhower (persona-impact × esforço)

Trade-off entre impacto direto em persona vs esforço técnico de entrega.

Útil pra justificar ordem das ondas e pra dialogar com [`docs/design/ROADMAP.md`](../design/ROADMAP.md) que organiza por Phase técnico mas não por impacto-relativo. Eisenhower aqui é descritivo (mapeia o que está sendo entregue), não prescritivo (não dita que toda iniciativa precise caber em quadrante específico).

|                     | Low-effort                                          | High-effort                                      |
| ------------------- | --------------------------------------------------- | ------------------------------------------------ |
| **High-impact**     | **Onda 1 (Autopilot)** — done now                   | **Onda 2 (Catálogo)** — strategic                |
| **Low-impact**      | Backlog [`04-pending.md`](../design/04-pending.md) (gaps individuais) | Anti-roadmap (rejected — §6)         |

**Por que Onda 1 está em "low-effort × high-impact"?**

Em termos relativos. Phase 6 técnico é estimado L (large) em [`docs/design/ROADMAP.md`](../design/ROADMAP.md), mas no eixo persona-impact é direct hit em Marina (primária).

A parte cara da arquitetura — cards atômicos, memory L1/L2/L3, reuse-intelligence syntactic, 15 validators, 17 graph queries — já foi entregue em v1.0-v1.2. Onda 1 é "fechar a última perna do tripé", não "construir tripé novo".

Métrica decisiva: time-to-merge ≤ 4h corta fricção diária de Marina de modo direto; toda outra onda só importa depois disso fechar.

**Por que Onda 2 está em "high-effort × high-impact"?**

Tree-sitter exige adoção de dep externa + migration cuidadosa (Phase 7); multi-dev exige merge-strategy formal documentada e phase-lock cross-dev; preset `ios-only` exige cards iOS standalone novos com validators próprios.

Esforço L+M+M = High; impacto é também High porque:

- Libera Lucas (Camada B) de workaround manual via `forge reconfigure` + overlay local
- Amplia adoção em squad maior (Bruno expansão pra squads de 5-8 devs)
- Dá Patricia visibility filtrada sem violar boundary
- Carolina ganha cards locais com piso de qualidade canon

**Por que backlog `04-pending.md` está em "low-effort × low-impact"?**

Gaps individuais (`Gap 2 spike completo`, `Gap 7 cards reservados`, polish items) entregam fricção pequena por gap — não justificam onda dedicada.

Entram via incremento de Phase técnico (9, 10, 12) sem persona-âncora; cada um vale ≤ 30min de tempo de Marina por mês quando shippado. Importam acumulados; não individualmente.

**Por que anti-roadmap está em "high-effort × low-impact"?**

Hosted service, marketplace pública, multi-target watchOS, IDE plugin nativo — cada um exigiria refactor pesado (XL de esforço técnico) E desvia da visão (low impact relativo à persona declarada).

Marketplace pública atrai 50 contribuidores hipotéticos no Discord; canon focado em 22 cards de qualidade atende as 8 personas reais melhor.

Rejected explicitamente (§6) — anti-roadmap não é "ainda não fizemos", é "decidimos não fazer". Diferença importa: "ainda não" vive em backlog; "não" vive em anti-roadmap com cross-ref pro contract violado.

---

## §6 — Anti-roadmap (NÃO entrará — explícito com rationale)

8 items que NÃO entrarão no roadmap-produto, com rationale e cross-ref pro contract que os bloqueia.

Anti-roadmap é a defesa contra scope creep — quando "todo mundo pede X" começar a aparecer, retornar a esta tabela primeiro.

Cada linha tem um contract canônico que ancora o veto. Rever uma linha exige revisita formal do contract referenciado (Mandamento 1 do projeto — não silent drift).

Itens que tentaram entrar em sessões anteriores e foram rejeitados aparecem na trilha de [`04-pending.md`](../design/04-pending.md) (gaps deferred → rejected); o que está aqui é o destilado final.

**Critérios pra um item entrar em §6 (anti-roadmap):**

- Viola decisão locked em [`docs/design/01-decisions.md`](../design/01-decisions.md) OU
- Fica fora da visão declarada em [`docs/design/00-vision.md`](../design/00-vision.md) §What feature-forge is OU
- Cabe melhor em outra ferramenta (PM tool, SaaS, IDE plugin) sem complementar feature-forge OU
- Atende anti-persona (ver `docs/product/00-prd.md` §9 quando shipado) em vez de persona declarada

**Critérios pra remover um item de §6** (sair de anti-roadmap pra entrar em onda futura):

- Brainstorm explícito do user atualizando contract referenciado
- Revisita formal do contract com entry em `CHANGELOG.md ### Changed (load-bearing)` no formato "Revisita decisão N: ..." quando aplicável
- Re-derivação do critério de persona — se persona declarada agora demanda o item, anti-roadmap entry sai de cena

Sem brainstorm + revisita formal, anti-roadmap entry **permanece**.

| Item | Por quê NÃO | Cross-ref |
|---|---|---|
| Multi-target watchOS / Wear OS / tvOS | Out-of-scope **permanente** (Gap 9 revisita 2026-06-03). Caminho oficial pra plataforma exótica é Gap 5 overlay local (`.claude/cards/local/`), não canon expansion. Manter canon focado em Android + iOS + KMP + Web preserva qualidade do catálogo. | [`docs/design/04-pending.md`](../design/04-pending.md) §Gap 9 §OUT-OF-SCOPE explícito |
| PM / scheduling / estimativa | Boundary explícito em [`docs/design/00-vision.md`](../design/00-vision.md) §What feature-forge is NOT. Patricia (PM, [`01-personas.md`](01-personas.md) Camada C) ganha **visibility** via `forge status` read-only, não decision-making automation. Estimativa e schedule são domínio do PM com Confluence/Notion/Linear. | [`docs/design/00-vision.md`](../design/00-vision.md) |
| Code review final automático | Diego (code reviewer humano, [`01-personas.md`](01-personas.md) Camada C) decide. Forge detecta violações mecânicas (escopo, contracts, analytics presente, regression test em bugfix). Veredito final em arquitetura/produto é humano, não algoritmo. | [`docs/design/00-vision.md`](../design/00-vision.md) |
| Hosted service / SaaS | CLI-first (Decision 18 + 22, locked). Snapshot copy local via `forge init`; cada projeto tem cópia em `~/Documents/feature-forge/` ou equivalente. SaaS exigiria runtime dep + cloud state — quebra portability. | [`docs/design/01-decisions.md`](../design/01-decisions.md) D18, D22 |
| Marketplace pública de cards | Viola Decision 22 (no runtime deps em outras skills). Gap 5 cobre **local** versionado em `.claude/cards/local/`; pública exigiria registry runtime + signing/verification → quebra portability + introduz attack surface não-mitigada. | [`docs/design/01-decisions.md`](../design/01-decisions.md) D22 |
| Auto-decidir produto / arquitetura | Decisão de produto e arquitetura é do usuário (Marina ou Bruno). Engine pode sugerir com base em L2+L3 history; nunca decidir sem confirmação humana via 3-caminhos. Princípio non-negociável. | [`docs/design/00-vision.md`](../design/00-vision.md) |
| IDE plugin (VSCode / IntelliJ / Xcode) | CLI-first permanece. Integração via shell hooks (`hooks/` directory já distribuído via `forge init`) cobre dispatch. Plugin nativo é IDE-coupling que viola portability + multiplica superfície de manutenção. | [`docs/design/00-vision.md`](../design/00-vision.md) |
| Skill auto-installer cross-project (multi-skill orchestrator) | Snapshot via `forge init` (Decision 22). Cada projeto consumidor tem cópia local; sem dep runtime na skill-mãe. Auto-installer cross-project significaria runtime registry, viola Decision 22. | [`docs/design/01-decisions.md`](../design/01-decisions.md) D22 |

---

## §7 — Cross-ref bidirecional com `docs/design/ROADMAP.md` técnico

Mapeamento explícito Onda produto ↔ Phase técnico. A relação não é 1:1 estrita; algumas ondas compõem mais de um Phase, alguns Phases vivem fora de qualquer onda. Manter os dois eixos sincronizados é trabalho de auditoria mensal — quando uma onda fecha aqui, a Phase correspondente em [`docs/design/ROADMAP.md`](../design/ROADMAP.md) também marca status `done` na mesma sessão.

| Onda produto (este doc) | Phase técnico ([`docs/design/ROADMAP.md`](../design/ROADMAP.md)) | Conexão | Esforço técnico estimado | Persona-âncora |
|---|---|---|---|---|
| **Onda 1** (Autopilot completo) | **Phase 6** (Apply Mode + LLM hookup + Atomic commit + Retro auto-trigger) | 1:1 — Onda 1 É Phase 6 visto pela lente persona | L (large) | Marina |
| **Onda 2** (Catálogo evolutivo + colaboração) | **Phase 7** (Tree-sitter AST) + Gap 5 maturity + multi-dev opcional (Gap 6) | Phase 7 habilita semantic reuse pra UX nativa iOS; Gap 5 escala overlay local; multi-dev resolve Gap 6 deferred | L + M + M (combinado) | Lucas + Bruno |
| **Onda 3** (Inteligência adaptativa) | **Phase 7+** (semantic ativo) + LLM real-time signals (extensão Phase 6.1) | Aspiracional — não bloqueia v2.0; depende de Phase 7 entregue e dados L2+L3 acumulados em campo | XL (cumulativo + dados em produção) | Todas (transversal) |

**Phases técnicos sem onda produto direta** (continuam relevantes no eixo técnico, mas demand-driven ou incremental sem persona-âncora dedicada):

- **Phase 8** (MCP real connections — Jira, Linear, GitHub Issues, Context7) — entra sob demanda quando squad pede integração; não casa com onda persona específica porque é integração externa, não outcome de persona. Marina/Bruno se beneficiam via `forge plan IN-NNNNN` resolvendo ticket real, mas isso é UX de comando, não onda de produto. Implementação per-MCP segue contract canônico já estabelecido em `engine/mcp/types.py` (auth, fetch_ticket, list_tickets, post_comment).
- **Phase 9** (Cards reservados v1.1+ — `firebase-analytics`, `apollo-kmp`, `ktor-websocket`, `sse-client`, `oauth2-full-flow`) — incremental por card, conforme demanda real chegar. Cada card adicionado fortalece catálogo canon mas não vira "onda" sozinho. Squad com GraphQL pede `apollo-kmp` → card entra; squad com SSE pede `sse-client` → card entra. Sem batch entrega.
- **Phase 10** (Cards out-of-scope v1 / legacy support — `hilt-di`, `koin-dsl`, `android-xml-views`, `ios-ui-uikit`, `navigation2-android`, `material3`) — demand-driven por projeto-alvo. Cards legacy entram quando projeto real demandar; Gap 5 overlay local cobre quando canon não cobre. Critério pra promover legacy a canon: ≥ 3 projetos consumidores em campo ativo + sem alternativa moderna viável.
- **Phase 11** (Windows support) — demand-driven quando Windows-only dev pedir onboarding. Não bloqueia POSIX-first contract de v1. Fallbacks Windows existem (`msvcrt.locking`) mas precisam validação em projeto real + path handling cross-platform em hooks bash.
- **Phase 12** (Validators expandidos — RULEs restantes em `validate_workflow_config.py`, `validate_memory.py`, novos validators como `validate_analytics_spec.py` standalone) — incremental. Cada RULE fortalece cascade `forge verify` sem mudança de UX. Marina/Bruno não percebem RULE individual; percebem agregado quando `forge doctor` reporta categoria nova de health.
- **Phase 13** (Marketplace de cards user-contributed) — **ANTI-ROADMAP** (ver §6). Listado no `ROADMAP.md` técnico como "v2+" pelo plano original; no eixo produto fica como "não entrará" — viola Decision 22 (no runtime deps em outras skills). Gap 5 (overlay local versionado) cobre a substância da demanda sem o custo arquitetural.

---

> **Próxima revisão:** Onda 1 fechar (entrega `forge implement` autopilot) dispara update desta tabela — mover Onda 1 pra "done" + métricas reais empíricas substituem aspiracionais.
>
> **Auditoria de progresso:** `CHANGELOG.md` `### Added` cobrindo Phase 6 + `docs/design/08-session-handoff.md §Última atualização` referenciando Onda 1 fechada + entry em `.claude/state/` se aplicável.
>
> **Gatilho pra revisita formal deste doc:** quando uma onda completa, quando um anti-roadmap item é reconsiderado (via revisita do contract referenciado em §6), ou quando demanda concreta de persona declarada exige nova onda fora do roadmap atual. Em qualquer um dos três casos, o doc passa por brainstorm + writing-plan + dispatch — não edit silent.
>
> **Onde este doc NÃO é fonte de verdade:**
>
> - Decisões técnicas finais vivem em [`docs/design/01-decisions.md`](../design/01-decisions.md)
> - Capabilities concretas vivem em [`docs/design/ROADMAP.md`](../design/ROADMAP.md)
> - Estado atual vive em [`docs/design/08-session-handoff.md`](../design/08-session-handoff.md)
> - Gaps abertos vivem em [`docs/design/04-pending.md`](../design/04-pending.md)
> - Personas canônicas vivem em [`01-personas.md`](01-personas.md)
> - Cenários canônicos vivem em [`02-scenarios.md`](02-scenarios.md)
>
> Roadmap-produto orquestra, não declara. Em qualquer conflito de informação, doc canônico vence.
