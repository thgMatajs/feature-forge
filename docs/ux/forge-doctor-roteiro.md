# `forge doctor` — roteiro end-to-end

The cinematic UX of `forge doctor`. Read-only health check across every
moving piece of the feature-forge installation in this project. Mentor calmo:
warm during exploration, didactic on findings, prescriptive at the close.

## Context

- Read-only. Never mutates `workflow-config.yaml`, cards, inventory, memory,
  or graph (other than appending its own `doctor.last-run` + `last-status`).
- Walks 9 categories (config, cards, inventory, memory, graph, hooks, MCPs,
  i18n scripts, connectivity).
- Returns 🟢 (exit 0), 🟡 (exit 1), 🔴 (exit 2).
- Doctor pergunta scope no início (`full` ou `quick`). `quick` mode skips
  network checks and runs only the critical block. Sem flag — escolha
  conversacional dentro do próprio comando.

---

## Cena 1 — Entrada (0.0–1.0s)

```
$ forge doctor

   ╭──────────────────────────────────────────╮
   │  feature-forge · doctor                  │
   │  Health check · read-only                │
   ╰──────────────────────────────────────────╯

Vou checar o setup todo. Nada vai ser modificado.
9 categorias, cerca de 8 segundos.
```

**Note:** sempre afirma read-only logo de cara. Reduz ansiedade do
desenvolvedor que rodou `doctor` justamente porque está achando que algo
está estranho.

---

## Cena 2 — Pre-flight (1.0–1.8s)

```
[0:01] Localizando estado do forge...
       ├ .claude/workflow-config.yaml          ✓ found
       ├ schema-version                        ✓ 1 (supported)
       ├ forge-version                         ✓ 1.0.0 (matches binary)
       └ doctor mode                           full (responde "quick" pra critical-only)
```

**Note:** se `.claude/workflow-config.yaml` não existir, doctor termina aqui
com a sugestão `forge init`. Ver edge case 1.

---

## Cena 3 — Cascade cinematográfico (1.8–8.5s)

Cada categoria aparece sequencialmente, com sub-checks. Linhas terminadas
com ✓ (pass), ⚠ (warn), 🛑 (fail). Símbolo final por categoria reflete o
pior dos sub-checks.

### 3.1 — Config integrity (1.8–2.4s)

```
[0:02] 🔍 Config integrity
       ├ RULE-001 schema-version ∈ [1]                              ✓
       ├ RULE-002 project-slug regex [a-z0-9-]+                     ✓ meobonsai
       ├ RULE-003 preset references known definition                ✓ kmp-mobile-firebase
       ├ RULE-004 platforms.active ⊆ {android, ios, kmp, web}       ✓ [android, ios, kmp, web]
       ├ RULE-008 paths.* point to existing dirs                    ✓ 11/11
       ├ RULE-009 conventions sub-keys non-null                     ✓
       ├ RULE-010 backend.provider block populated                  ✓ firebase
       ├ RULE-011 firebase.dev-project regex                        ✓ bonsai-meo-dev
       ├ RULE-013 readiness-strictness ∈ {strict, standard, lean}   ✓ strict
       └ RULE-014 persona references installed spec                 ✓ mentor-calmo
                                                                    ─────────
                                                                    ✓ passing
```

### 3.2 — Cards integrity (2.4–3.4s)

```
[0:03] 📦 Cards integrity  ·  12 active
       ├ RULE-005 every card exists at snapshot-root               ✓ 12/12
       ├ RULE-006 sha256 matches disk                              ✓ 12/12
       ├ RULE-007 requires/conflicts satisfied                     ✓
       ├ CARD-001..018 per-card schema validation                  ✓ 12 clean
       │
       │  kotlin-language · kmp-shared · compose-screens · swiftui-screens
       │  koin-annotations · skie-bridge · nav3 · swiftui-navigation
       │  firebase-auth · firebase-firestore · firebase-storage · crashlytics
       │
       └                                                            ✓ passing
```

### 3.3 — Inventory freshness (3.4–4.4s)

```
[0:04] 🌿 Inventory freshness
       ├ design-system.yaml
       │   ├ last-scan                          2026-05-27 (1d ago)
       │   ├ INV-DS-001..008                   ✓
       │   ├ drift detection                   ✓ no new Meo* components on disk
       │   └ coverage Android↔iOS              0.96
       │
       ├ i18n.yaml
       │   ├ last-scan                          2026-05-27 (1d ago)
       │   ├ INV-I18N-001..008                 ✓
       │   ├ drift detection                   ✓ 487 keys × 3 locales (parity 1.0)
       │   └ orphan-keys                       0
       │
       └ conventions.yaml
           ├ last-scan                          2026-05-28 (today)
           ├ INV-CONV-001..008                 ✓
           ├ features-analyzed                  3
           └ conflicts-detected                 [] (single consistent pattern)
                                                ─────────
                                                ✓ passing
```

### 3.4 — Memory consistency (4.4–5.2s)

```
[0:05] 🧠 Memory consistency
       ├ L1 — per-feature
       │   ├ active feature locks               0  (no state ∈ {planning, implementing, verifying})
       │   ├ paused features                    1  (lembrete-rega — safe to resume)
       │   ├ archived summaries                 3  (auth, bonsai, bonsai-detail)
       │   └ MEM-L1-001..008                    ✓
       │
       ├ L2 — project
       │   ├ location writable                  ✓ .claude/memory/L2-project.yaml
       │   ├ size                               142 KB / 500 KB (28%)
       │   ├ MEM-L2-001..007                    ✓
       │   └ promotion-candidates pending       2 (below confidence threshold)
       │
       └ L3 — user-global
           ├ link                                ✓ ~/.claude/projects/{hash}/memory/
           ├ MEMORY.md readable                  ✓
           └ write policy                        read-only (forge never writes)
                                                ─────────
                                                ✓ passing
```

**Note:** active feature locks são informacionais aqui (doctor não bloqueia
nada). Mas a presença é destacada porque outros comandos vão respeitar.

### 3.5 — Graph health (5.2–6.2s)

```
[0:06] 🗺️ Graph health
       ├ GRAPH-001 schema_version supported               ✓ 1
       ├ GRAPH-008 WAL mode enabled                       ✓
       ├ GRAPH-002 features.slug ↔ on-disk dirs           ✓ 12/12
       ├ GRAPH-003 files.path exist on disk               ✓ 1,247 files (0 orphans)
       ├ GRAPH-004 files.module ⊆ paths.feature-roots     ✓ 4 modules
       ├ GRAPH-005 ds_components ↔ inventory              ✓ 28 components aligned
       ├ GRAPH-006 i18n_keys naming matches pattern       ✓ 487/487
       ├ GRAPH-007 foreign keys resolve                   ✓ 0 orphan rows
       │
       └ Stats
           ├ symbols                            5,892
           ├ imports                            14,103
           ├ routes                             19
           ├ DI providers                       34
           └ last full rebuild                  2026-05-28 09:14 UTC
                                                ─────────
                                                ✓ passing
```

### 3.5.1 — Reuse intelligence (6.2–6.4s)

Agregação dos `reuse_findings` materializados pelo init scan + rebuilds.
Categorias com counts > 0 viram WARN; tudo zerado é OK. SKIP quando o
graph ainda não foi construído.

```
[0:06] 🔍 Reuse intelligence
       ├ findings                                ⚠ 4 pending — `forge evolve`
       │   duplicate-cross-module: 1
       │   kmp-migration-candidate: 2
       │   near-duplicate: 1
       │                                                ─────────
       │                                                ⚠ warn
```

Quando zerado:

```
[0:06] 🔍 Reuse intelligence
       └ findings                                ✓ nenhuma duplicação pendente
```

### 3.6 — Hooks (6.2–6.7s)

```
[0:06] 🪝 Hooks  ·  RULE-017 hooks must exist + be executable
       ├ post-edit-codebase-graph              ✓ executable
       ├ pre-commit-feature-forge              ✓ executable
       └ post-subagent-validate                ✓ executable
                                                ─────────
                                                ✓ passing
```

### 3.7 — MCPs reachability (6.7–7.5s)

```
[0:07] 🌐 MCPs reachability
       ├ ticketing (jira)
       │   ├ RULE-012 mcp-tool-prefix callable           ✓ mcp__claude_ai_Atlassian
       │   ├ workspace ping                              ✓ inchurch.atlassian.net
       │   └ default project (BONSAI) reachable          ✓ 247 issues visible
       │
       └ external-docs (context7)
           ├ mcp-tool-prefix callable                    ✓ mcp__context7
           └ privacy-mode                                false (probes allowed)
                                                         ─────────
                                                         ✓ passing
```

**Note:** se `external-docs.privacy-mode: true`, pula o probe e mostra
`skipped (privacy-mode)`. Em scope `quick`, todo este bloco é skipped.

### 3.8 — i18n scripts (7.5–7.9s)

```
[0:07] 🌍 i18n scripts
       ├ generation-script                     ✓ scripts/i18n/generate.py runnable
       ├ verification-script                   ✓ scripts/i18n/verify.py runnable
       └ dry-run verify (no writes)            ✓ 0 errors, 0 warnings
                                                ─────────
                                                ✓ passing
```

### 3.9 — Connectivity (7.9–8.4s)

```
[0:08] 🔌 Connectivity
       ├ git repo                              ✓ branch: feature/lembrete-rega
       ├ detached HEAD                         ✓ no
       ├ merge in progress                     ✓ no
       ├ rebase in progress                    ✓ no
       └ working tree                          ✓ clean (or: 3 unstaged — informational)
                                                ─────────
                                                ✓ passing
```

---

## Cena 4 — Verdict box (8.4–8.7s)

The single box that summarizes the run. Investment in polish: alignment,
spacing, counts.

```
[0:08] ✨ Verdict

       ╭───────────────────── feature-forge · MeoBonsai · doctor ─────────────────────╮
       │                                                                              │
       │   Overall:  🟢 healthy                                                       │
       │                                                                              │
       │   Categories         passed   warn   fail                                    │
       │     config              10      0      0                                     │
       │     cards               12      0      0                                     │
       │     inventory            3      0      0                                     │
       │     memory               3      0      0                                     │
       │     graph                8      0      0                                     │
       │     hooks                3      0      0                                     │
       │     mcps                 2      0      0                                     │
       │     i18n                 3      0      0                                     │
       │     connectivity         5      0      0                                     │
       │                       ────   ────   ────                                     │
       │     total              49      0      0                                     │
       │                                                                              │
       │   Duration:  8.4s   ·   Mode: full   ·   Last run: never                     │
       │                                                                              │
       ╰──────────────────────────────────────────────────────────────────────────────╯

[0:08] 📝 Saved to:
       .claude/workflow-config.yaml
         doctor.last-run    = 2026-05-28T14:33:11Z
         doctor.last-status = passing

       🟢 Tudo saudável. 49 checks passaram, 0 warnings.
```

**Note:** este é o "magic moment" do happy path. Sem advice porque não há
o que prescrever. Mentor calmo: silêncio é resposta.

---

## Cena 5 — Drill-down em warnings (variação amarela)

When at least one ⚠ is found, doctor expands the first warning per
category with a didactic block. Order matches cascade order.

```
[0:08] ⚠ Inventory freshness — design-system.yaml last-scan = 43 dias atrás.
       
       Por que importa
         Inventory desatualizada faz o planning-conductor usar dados
         antigos ao eleger componentes Meo* pra reusar. Drift detection
         já viu 2 novos Meo* no disco fora da inventory.
       
       Como resolver
         forge reconfigure                       (escolher "re-scan completo" no menu)
         forge reconfigure                       (escolher "re-extrair inventory: design-system")
       
       Risco: baixo — só qualidade de sugestão. Nada quebra.
```

E mais embaixo, o verdict box muda só na cor e na linha total:

```
   Overall:  🟡 healthy with warnings
   ...
     total              47      2      0
   ...

   🟡 47 checks passaram, 2 warnings. Não é bloqueante.
      Prescrição mais simples: forge reconfigure quando puder.
```

**Note:** drill-down por warning é estruturado em 4 blocos fixos: o quê,
por que importa, como resolver, risco. Mentor calmo: nunca solta erro
solto.

---

## Cena 6 — Drill-down em block-level failure (variação vermelha)

When at least one 🛑 hard fail is found, doctor expands every failure
with prescriptive guidance. Verdict turns red and exit code = 2.

```
[0:03] 🛑 Cards integrity — firebase-firestore sha256 mismatch (RULE-006).
       
       Por que importa
         sha256 garante que o snapshot local é o que foi instalado.
         Mismatch significa: edição local (OK se intencional), upgrade
         parcial, ou conflito de merge em .claude/cards/.
       
       Como ler
         · esperado (workflow-config):  abc123...
         · encontrado (disco):           def456...
         · arquivo divergente:          templates/firestore-tech-spec.md
       
       Como resolver
         Intencional:        forge reconfigure → menu cards → "travar edição local: firebase-firestore"
         Não intencional:    forge reconfigure → menu cards → "atualizar card do canonical: firebase-firestore"
       
       Risco: alto — validators e agent-prompts do card podem
       comportar diferente do esperado pela versão registrada.
```

```
[0:08] ✨ Verdict

       ╭───────────────────── feature-forge · MeoBonsai · doctor ─────────────────────╮
       │                                                                              │
       │   Overall:  🔴 broken                                                        │
       │                                                                              │
       │   Categories         passed   warn   fail                                    │
       │     config              10      0      0                                     │
       │     cards               11      0      1   🛑 firebase-firestore             │
       │     inventory            3      0      0                                     │
       │     memory               3      0      0                                     │
       │     graph                8      0      0                                     │
       │     hooks                3      0      0                                     │
       │     mcps                 2      0      0                                     │
       │     i18n                 3      0      0                                     │
       │     connectivity         5      0      0                                     │
       │                       ────   ────   ────                                     │
       │     total              48      0      1                                     │
       │                                                                              │
       │   Duration:  8.4s   ·   Mode: full   ·   Exit code: 2                        │
       │                                                                              │
       ╰──────────────────────────────────────────────────────────────────────────────╯

       🔴 1 check bloqueante.
          Comandos que mutam estado (forge plan, reconfigure, card *)
          vão recusar até resolver.
```

**Note:** falha vermelha sempre cita o comando exato de recuperação.
Mentor calmo é prescritivo aqui: não há ambiguidade pra explorar.

---

## Cena 7 — Modo `quick` (variação rápida)

```
$ forge doctor

   ╭──────────────────────────────────────────╮
   │  feature-forge · doctor                  │
   ╰──────────────────────────────────────────╯

Vou checar o setup. Qual scope?
  • full         9 categorias, ~8s
  • quick        config + cards + locks apenas, ~2s

> quick

   ╭──────────────────────────────────────────╮
   │  feature-forge · doctor (quick)          │
   │  Critical checks only · ~2s              │
   ╰──────────────────────────────────────────╯

[0:00] 🔍 Quick mode — config + cards + locks
       ├ RULE-001..010   config core                       ✓
       ├ CARD-005..007   snapshot + sha256 + conflicts     ✓ 12/12
       └ MEM-L1-008      active feature lock scan          ✓ 0 active locks
                                                            ─────────
[0:02] 🟢 Quick: 3 blocos verificados em 2.1s.
       Para o check completo: rode `forge doctor` e responda "full".
```

**Note:** `quick` é o "vou rodar antes de cada `forge plan`" do
desenvolvedor. Pula MCPs (rede), inventory drift (I/O pesado), graph
deep checks (joins). Mantém só o que impede mutate. Escolha conversacional,
sem flag — ver `docs/design/06-command-surface.md`.

---

## Edge cases

### 1. Init not run yet

```
$ forge doctor

   ╭──────────────────────────────────────────╮
   │  feature-forge · doctor                  │
   ╰──────────────────────────────────────────╯

[0:00] 🔍 Localizando estado do forge...
       └ .claude/workflow-config.yaml          🛑 not found

       Não consigo checar saúde sem o config. Este projeto ainda não
       passou por `forge init`.

       Próximo passo:
         forge init                  inicializa o setup (≈85s)
       
       Exit code: 2
```

### 2. Schema version drift (forge older than config)

```
[0:01] 🛑 schema-version mismatch
       
       workflow-config.yaml schema-version = 2
       forge binary supports up to             1
       
       O config foi escrito por uma versão mais nova do forge. Não posso
       seguir sem risco de interpretar campos errado.
       
       Próximo passo:
         brew upgrade feature-forge         (ou git pull no canonical)
         forge --version                    confirma que ficou ≥ 2
         forge doctor                        roda de novo
       
       Exit code: 2
```

### 3. Active feature lock detected

```
[0:05] 🧠 Memory consistency  ·  active feature lock detected
       ├ L1/lembrete-rega/status.json
       │   ├ state                              planning
       │   ├ state-since                        2026-05-28T14:23:11Z (≈10 min)
       │   └ last-action                        elicitation-completed
       │
       └ doctor itself does not block this
       
       Por que mencionar
         Esta L1 trava qualquer comando que mute estado compartilhado
         (forge reconfigure — qualquer mutação de cards mora no menu
         interativo dele). Doctor é read-only e segue normalmente — só
         te alerto pra você saber antes de tentar outra coisa.
       
       Como desbloquear (quando precisar)
         · Continue:   forge plan lembrete-rega    (auto-resume)
         · Pause:      digite "para" dentro do comando ativo
         · Aborte:     forge undo                  (escolher "last action")
```

**Note:** doctor é read-only — informa, não bloqueia. Categoria fica em
passing; apenas adiciona uma nota informacional.

### 4. Card snapshot tampering

```
[0:03] ⚠ Cards integrity — kotlin-language sha256 mismatch (RULE-006).
       
       Como ler
         Um arquivo dentro de .claude/cards/kotlin-language/ foi editado
         localmente desde o install. É OK se intencional.
         · esperado (workflow-config):  e3b0c4...
         · encontrado (disco):           f1a920...
       
       Decida
         Mantenho minha edição local:
           forge reconfigure → menu cards → "travar edição local: kotlin-language"
         Volto pro canonical:
           forge reconfigure → menu cards → "atualizar card do canonical: kotlin-language"
       
       Risco: médio — doctor continua avisando até você declarar.
```

**Note:** este é warn (não fail). Diferente da Cena 6 (firebase-firestore),
aqui o tom é didático porque não bloqueia mutate.

### 5. Graph corruption

```
[0:06] 🛑 Graph health — .claude/graph.db malformed.
       
       Por que importa
         Sem graph, planning-conductor cai em grep — funcional, mas mais
         lento e menos preciso (similar features, blast-radius, orphans).
       
       Como resolver
         forge reconfigure → escolher "rebuild graph" no menu
         (30-60s em repos médios; não toca config, cards, memory.)
       
       Risco: alto — queries do graph vão falhar com mensagem genérica.
```

### 6. MCP offline

```
[0:07] ⚠ MCPs reachability — ticketing (jira) unreachable.
       
       Por que importa
         `forge plan` puxa ticket detail do Jira. Sem o MCP,
         planning-conductor cai no fluxo de paste inline (decisões
         registradas com source: user-paste em rationale-trace).
       
       Como resolver
         Re-autenticar via /mcp no Claude Code, ou
         forge reconfigure → ticketing.provider: none
       
       Risco: baixo — fluxo segue, só mais manual.
```

**Note:** MCP offline é sempre warn (nunca fail). Mentor calmo nunca
bloqueia trabalho por causa de rede.

### 7. Memory L2 oversized

```
[0:05] ⚠ Memory L2 — 567 KB > max-size-mb 0.5 (113%).
       
       Por que importa
         L2 inflada carrega contexto demais no planning-conductor.
         Não é bug; é ineficiência.
       
       Como resolver
         memory-distiller roda automaticamente quando a última task
         da feature corrente é verificada (retrospective auto-trigger).
         Não há comando manual — distilação não tem entrypoint próprio
         por design (ver `docs/design/06-command-surface.md`).
       
       Risco: baixo — degrada com o tempo, nunca quebra.
```

---

## Design points this script crystallizes

| Implicit decision | Practical implication |
|---|---|
| Doctor is **always read-only** | Único campo que escreve é `doctor.last-run` + `last-status`. |
| Cascade matches **schema rule codes** | Cada linha de check cita RULE/CARD/INV/MEM/GRAPH. Auditável. |
| Drill-down é estruturado em 4 blocos | quê → por que → como resolver → risco. Nunca improvisa. |
| Scope `quick` skipa rede + I/O pesado | Roda em <3s. Pensado pra pre-`forge plan` reflex. Escolhido via prompt, sem flag. |
| Active lock é **info, não warn** | Doctor não pune o usuário por ter feature aberta. |
| Verdict box é **single canvas** | Mesma estética do `forge init`. Coerência visual. |
| Exit codes seguem **0/1/2** | Scriptável: CI roda `forge doctor` em modo não-interactive (env var pra forçar quick — não flag). |

---

## Cross-references

- Rule codes vêm de `docs/schemas/forge-config.md` (RULE-001..018),
  `docs/schemas/card.md` (CARD-001..018), `docs/schemas/inventories.md`
  (INV-DS/INV-I18N/INV-CONV), `docs/schemas/memory.md` (MEM-L1/MEM-L2) e
  `docs/schemas/graph.md` (GRAPH-001..008).
- Doctor estado persistido em `forge-config.yaml.doctor`
  (ver `docs/schemas/forge-config.md §DOCTOR`).
- Estética e timing seguem `docs/ux/forge-init-roteiro.md`.
