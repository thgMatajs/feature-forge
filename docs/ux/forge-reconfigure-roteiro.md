# `forge reconfigure` — roteiro end-to-end

The cinematic UX of `forge reconfigure`. Sibling of `forge init`: same voice,
same timing discipline, surgical scope. Reconfigure re-runs init-style
decisions **incrementally** and applies **diffs only to affected files** —
never a full rebuild.

## Context

- Standalone repo `~/Documents/feature-forge/` (canonical source of cards)
- `.claude/workflow-config.yaml` already exists (else: redirect to `forge init`)
- Active feature lock (`.claude/forge/state/lifecycle/*/status.json`) is the gatekeeper
- Persona: **mentor calmo** — warm in exploration, firm at gates, didactic on
  changes, asks confirmation before applying diffs
- Every applied change appends to `.claude/workflow-config-history.jsonl`

---

## Cena 1 — Entrada + lock check (0.0–2.0s)

```
$ forge reconfigure

   ╭──────────────────────────────────────────╮
   │  feature-forge · v1.0.0                  │
   │  Reconfigure — diff incremental.         │
   ╰──────────────────────────────────────────╯

[0:00] Antes de qualquer coisa, vou checar se há feature ativa.
       Reconfigure mexe em estado compartilhado e isso só rola se
       nada estiver no meio do caminho.

[0:01] 🔍 Scanning .claude/forge/state/lifecycle/*/status.json
       ├ auth                       done       (safe)
       ├ bonsai                     done       (safe)
       ├ bonsai-detail              done       (safe)
       ├ register                   paused     (safe)
       └ lembrete-rega              planning   ✋ ACTIVE
```

**Cenário A — feature ativa detectada (lock acionado):**

```
✋ Refusing: feature 'lembrete-rega' is currently planning (since 2026-05-28T14:23:11Z).
   Resolve before running this command:
     • Finish naturally — continue with `forge implement lembrete-rega` or
       `forge verify lembrete-rega` per the current state
     • Pause the active session — type "para" inside the running command;
       state transitions to `paused` and shared-state mutation unlocks
     • Resume later — run `forge plan lembrete-rega` (auto-resume) once paused

   Saindo sem mudar nada.
```

**Cenário B — nenhuma feature ativa, prossegue:**

```
[0:02] ✓ Sem feature ativa. Posso mexer no setup com segurança.
```

**Note:** lock check é a primeira coisa, sempre. Estados terminais (`done`,
`aborted`, `paused`) não bloqueiam — só `planning`, `implementing`,
`verifying`. Mensagem de recusa segue contrato literal de `memory.md` §L1 as
a lock mechanism.

---

## Cena 2 — Pre-flight + schema-version check (2.0–3.5s)

```
[0:02] Checando ambiente e config atual...
       ├ git repo                            ✓ (branch: main)
       ├ writable .claude/                   ✓
       ├ workflow-config.yaml                ✓ found
       ├ schema-version                      ✓ 1 (current)
       ├ cards snapshot integrity            ✓ 12/12 sha256 match
       └ forge-version recorded              1.0.0 (matches binary)
```

**Edge: schema-version mismatch**

```
       └ schema-version                      ⚠ 1 (binary supports up to 2)

⚠ Sua config está em schema v1 mas eu sou v2. Reconfigure exige migração
  antes pra não corromper o arquivo. Roda:

      forge raw migrator-1-to-2

  (`raw` é o escape hatch oficial pra migrations — ver
  `docs/design/06-command-surface.md`.)
  Depois volta aqui que eu sigo. Sem migrar não dá pra continuar.
```

**Note:** se `forge-version` registrada > binário instalado → pede upgrade do
forge. Reconfigure nunca opera sobre schema desconhecido.

---

## Cena 3 — Snapshot atual (3.5–6.0s)

Mentor calmo mostra **o que tem hoje** antes de perguntar o que mudar. Sem
contexto, nenhuma pergunta.

```
[0:04] 📋 Configuração atual

   Projeto:        MeoBonsai · meobonsai
   Preset:         kmp-mobile-firebase           (immutable via reconfigure)
   Plataformas:    android · ios · kmp · web
   Cards ativos:   12
                   kotlin-language · kmp-shared · compose-screens · swiftui-screens
                   koin-annotations · skie-bridge · nav3 · swiftui-navigation
                   firebase-auth · firebase-firestore · firebase-storage · crashlytics
   Backend:        firebase · bonsai-meo-dev (dev) · bonsai-meo (prod, write-blocked)
   Ticketing:      jira · inchurch.atlassian.net · project BONSAI
   Persona:        mentor-calmo · pt-BR · drill-down: medium
   Workflow:       strict (14 docs) · pre-commit-review blocking
   Memória:        L1 · L2 · L3 (L4/L5 não inicializados)

   Última reconfiguração:  2026-05-28T14:33:11Z (init original)
```

**Note:** mostra o estado de leitura única. Nada é editado nesta cena.

---

## Cena 4 — Menu de categorias (6.0–8.0s)

Multi-select cinemático. Categorias espelham blocos top-level de
`workflow-config.yaml`.

```
[0:06] Quais áreas você quer revisar?
       (espaço pra marcar, enter pra confirmar; vazio = sair sem mudar)

       [ ] cards                       adicionar / remover / atualizar
       [ ] paths                       feature-roots, test-roots, design-system
       [ ] conventions                 folder-layout, state, DI, test patterns
       [ ] backend                     provider, projetos, write-block
       [ ] ticketing                   provider, workspace, project, post-back
       [ ] workflow                    strictness, hard-gates, pre-commit-review
       [ ] persona                     tom, drill-down, closing-style
       [ ] memory                      policy de promoção L1→L2, retention
       [ ] external-docs               provider, cache TTL, privacy-mode
       [ ] hooks                       ativar/desativar hooks instalados
       [ ] external-deps               marcar dep externa como resolvida

       (não listado: preset, platforms, schema-version — exigem migração
        ou novo init. Pergunte se precisar.)
```

**Variação — usuário tenta trocar preset:**

```
> trocar preset

✋ Mudar de preset é mudança grande — `kmp-mobile-firebase` → `android-only`
   recompõe 8 cards, muda paths, redefine convenções inteiras.

   Reconfigure não suporta troca de preset. O caminho é re-init do zero:

       git checkout -b config/migrate-preset
       rm -rf .claude/                  # apaga setup atual
       forge init                       # init pergunta o preset interativamente

   Eu fico aqui esperando.
```

**Note:** preset, `project-slug`, `platforms.active` e `schema-version` são
**imutáveis** via reconfigure (forge-config.md §Top-level field reference).
Cada um tem mensagem de redirecionamento dedicada.

---

## Cena 5 — Revisão por categoria (8–35s, cinemático)

Para cada categoria marcada, mentor calmo mostra valor atual + pergunta.
Tudo conversacional, nunca formulário seco.

### 5.1 — Persona (tweak pequeno)

```
[0:08] 🎭 Persona
       atual:
         name:                       mentor-calmo
         primary-language:           pt-BR
         language-mirroring:         true
         drill-down-aggressiveness:  medium
         closing-style:              didactic

       Quer mudar algo?

       • drill-down: low (aceita primeira resposta)
       • drill-down: medium (atual — drilla quando vago)
       • drill-down: high (drilla até em confiança média)
       • closing-style: silent | brief | didactic (atual) | expressive
       • language: manter pt-BR
       • [manter tudo]

> drill-down: high
> closing-style: brief

       ✓ marcado pra diff
```

### 5.2 — Cards (mudança complexa: swap Hilt → Koin)

```
[0:14] 📦 Cards ativos (12)

       Ações disponíveis:
         add       instalar card novo
         remove    desinstalar card
         upgrade   atualizar snapshot pra versão canonical mais nova
         pin       congelar versão atual (não sugere upgrade)

> add hilt

       🔍 Resolvendo dependências e conflitos...
       
       ⚠ Conflito detectado
       
       O card `hilt` (DI Android) conflita com `koin-annotations` (já ativo).
       Ambos declaram capability `di-framework` — só pode haver um.
       
       Pra trocar:
         1. remover koin-annotations primeiro
         2. depois adicionar hilt
       
       Isso significa:
         · 4 anotações @KoinViewModel / @Single / @Factory viram @Inject / @HiltViewModel
         · agent-contributions/tech-spec-additions.md de koin sai
         · agent-contributions/tech-spec-additions.md de hilt entra
         · config-defaults: conventions.di-pattern: koin-annotations → hilt
         · Os subagents passam a receber prompt de Hilt daí em diante
       
       Trocar Hilt por Koin Annotations significa: remover 4 anotações @Inject
       de exemplo, adicionar 4 @Module @ComponentScan. Os agentes recebem
       prompts diferentes daí em diante.
       
       Topa?

> sim, trocar

       ✓ marcado: remove koin-annotations + add hilt
```

### 5.3 — Paths (restructure detectado)

```
[0:22] 📁 Paths

       Comparando paths configurados vs disco...
       
       ├ feature-roots.android      configurado: androidApp/feature
       │                            no disco:    androidApp/features        ⚠ não existe configurado, existe alternativo
       ├ feature-roots.ios          configurado: iosApp/iosApp/Features     ✓
       ├ feature-roots.shared       configurado: shared/feature             ✓
       └ feature-roots.web          configurado: webApp/src/features        ✓
       
       Parece que `androidApp/feature` virou `androidApp/features` no disco
       (rename de diretório). Atualizar o config?

> sim

       ✓ marcado: paths.feature-roots.android → androidApp/features
```

### 5.4 — Backend (mudança grande: Firebase → REST)

```
[0:28] 🔥 Backend
       atual:
         provider:           firebase
         dev-project:        bonsai-meo-dev
         prod-project:       bonsai-meo
         services-active:    [auth, firestore, storage, crashlytics]
         block-prod-writes:  true

       Quer trocar provider, ajustar serviços, ou mudar projetos?

> trocar provider pra REST

       Mudar de Firebase pra REST é mudança grande. O que vai acontecer:
       
         · 4 cards Firebase saem: firebase-auth, firebase-firestore,
           firebase-storage, crashlytics
         · Precisa entrar 1+ card REST (rest-client) — você tem um em mente?
         · Bloco `backend.firebase:` vira `backend.rest:` com base-url, auth-scheme
         · Templates de tech-spec mudam (sem regras Firestore, com OpenAPI)
         · Hooks de validação Firebase saem
       
       Isso passa de "tweak" pra "reformulação parcial". Continua?
       
> continua

       Cards REST disponíveis no catálogo canonical:
         · rest-ktor (Kotlin Ktor client, KMP-friendly)
         · rest-retrofit (Android-only)
         · rest-urlsession (iOS-only, SwiftUI-friendly)
       
       Como KMP shared está ativo, sugiro rest-ktor. Topa?

> rest-ktor
> base-url: https://api.meobonsai.com
> auth-scheme: bearer

       ✓ marcado: backend.provider firebase → rest
                  cards: -4 Firebase, +1 rest-ktor
                  backend.rest: { base-url, auth-scheme, error-format: rfc7807-problem-details }
```

### 5.5 — Ticketing (post-back tweak)

```
[0:32] 🎫 Ticketing
       atual:
         provider:                  jira
         workspace:                 inchurch.atlassian.net
         default-project:           BONSAI
         post-back.on-readiness-ready: true
         post-back.on-feature-done:    true
         post-back.require-confirmation: true

> desligar post-back automático

       ✓ marcado: post-back.on-readiness-ready: true → false
                  post-back.on-feature-done:    true → false
```

### 5.6 — External-deps (marcar dep externa como resolvida)

Discipline §9 — sub-menu dedicado a destravar features no estado
`blocked-on-external`. Single source of truth pra resolver
`depends_on_external[*].resolved-at` em task-contracts.

**Caso happy path — uma feature blocked, um ticket:**

```
[0:33] 🔗 External dependencies
       
       Procurando deps externas abertas em features ativas...
       ├ lembrete-rega                              1 ticket aberto
       │   · TASK-0003 ← BACKEND-1284 (jira) "Endpoint /api/weather pendente"
       │     declarada em 2026-05-30T14:37Z · há 18h
       └ (nenhuma outra feature blocked)
       
       Qual ticket marcar como resolvido?
       
         · BACKEND-1284
         · cancelar
       
       > BACKEND-1284
       
[0:34] Confirma marcar BACKEND-1284 como resolved?
       
       Vai afetar:
         · lembrete-rega/tasks/TASK-0003.yaml.depends_on_external[0].resolved-at
           null → 2026-05-30T08:34:00Z
       
       Após resolver, vou re-scan os task contracts da feature. Se zero
       deps blocking ficarem abertas, o feature-state volta de
       blocked-on-external pra implementing.
       
       [sim / não]
       
       > sim

[0:34] ✓ TASK-0003.yaml.depends_on_external[0].resolved-at = 2026-05-30T08:34:00Z
       ✓ Backup criado: tasks/TASK-0003.yaml.bak
       ✓ Re-scan lembrete-rega: 0 deps blocking abertas
       ✓ status.json.state: blocked-on-external → implementing
       
       Próximo: forge implement lembrete-rega
                (TASK-0003 destrancada)
```

**Caso edge — mesmo ticket em múltiplas tasks:**

```
[0:33] 🔗 External dependencies
       
       └ bonsai-detail-share                        1 ticket aberto
           · TASK-0005 ← DESIGN-44 (manual)
           · TASK-0008 ← DESIGN-44 (manual) (mesmo ticket)
       
       Marcar DESIGN-44 como resolvido afeta AMBAS:
         · TASK-0005.depends_on_external[0].resolved-at: null → agora
         · TASK-0008.depends_on_external[0].resolved-at: null → agora
       
       Confirma? [sim / não]
       
       > sim
       
[0:34] ✓ 2 entries atualizadas atomically (mesmo ticket = mesma decisão)
       ✓ Backups: TASK-0005.yaml.bak · TASK-0008.yaml.bak
       ✓ Re-scan: 0 deps blocking abertas
       ✓ state: blocked-on-external → implementing
```

Mentor calmo dedupa por `ticket` value: 1 prompt, 1 confirmação, N
entries atualizadas atomically. Anti-pattern explícito: nunca perguntar
N vezes pro mesmo ticket.

**Caso edge — nenhuma dep externa aberta:**

```
[0:33] 🔗 External dependencies
       
       Procurando deps externas abertas...
       └ (zero deps blocking abertas no projeto)
       
       Nada pra resolver aqui. Saindo dessa categoria sem mudança.
```

Aceita silently. Não vira blocker pro flow de reconfigure.

**Caso edge — ticket não existe em nenhuma feature:**

User digita um ticket id que não tem entry correspondente:

```
> ABC-999

       ✋ ABC-999 não aparece em nenhuma task contract ativa.
       
       Possíveis causas:
         · Erro de digitação (re-checar)
         · Dep já foi resolvida e a entry foi removida via undo
         · Ticket pertence a feature já archived (não destravável daqui)
       
       Quer:
         · Re-digitar
         · Cancelar
       
       > cancelar
```

Mentor calmo nunca silently no-ops uma marcação que não bate em nada —
o usuário ia jurar que destravou.

**Note operacional:**

- A operação é **atomic**: backup primeiro (`.bak` ao lado de cada
  TASK-NNNN.yaml editada — discipline §3), depois write, depois
  re-scan, depois state flip. Falha em qualquer ponto → rollback do
  backup.
- `history.jsonl` da feature ganha entrada:
  ```jsonl
  {"at":"...","kind":"external-dep-marked-resolved","ticket":"BACKEND-1284","entries-updated":2}
  ```
- `forge undo` consegue reverter: lê `kind: external-dep-marked-resolved`
  do history, restaura `resolved-at: null` nas N entries afetadas.

**Note:** cada revisão por categoria fecha em `✓ marcado pra diff`. Nada é
escrito ainda. Reconfigure constrói um **plan de diff** em memória.

> **Exceção pra 5.6 (external-deps):** essa categoria é **write-now**
> ao invés de **stage-and-diff**. Diff de "task-contract YAML mutou
> resolved-at de null pra timestamp" é binário (resolvido/não) e não
> precisa preview tradicional. O usuário já confirmou no prompt
> interno. Demais categorias mantêm o stage-and-diff classic.

---

## Cena 6 — Diff preview completo (35–45s)

O momento da transparência. Antes de qualquer escrita, mentor calmo mostra
**tudo que vai mudar**.

```
[0:35] 📋 Plano de diff (8 mudanças em 5 arquivos)

       ╭── .claude/workflow-config.yaml ───────────────────────────────────────╮
       │                                                                       │
       │   identity:                                                           │
       │ -   last-reconfigure: 2026-05-28T14:33:11Z                            │
       │ +   last-reconfigure: 2026-05-28T16:12:44Z                            │
       │                                                                       │
       │   paths:                                                              │
       │     feature-roots:                                                    │
       │ -     android: androidApp/feature                                     │
       │ +     android: androidApp/features                                    │
       │                                                                       │
       │   conventions:                                                        │
       │ -   di-pattern: koin-annotations                                      │
       │ +   di-pattern: hilt                                                  │
       │                                                                       │
       │   backend:                                                            │
       │ -   provider: firebase                                                │
       │ +   provider: rest                                                    │
       │ -   firebase:                                                         │
       │ -     dev-project:       bonsai-meo-dev                               │
       │ -     prod-project:      bonsai-meo                                   │
       │ -     services-active:   [auth, firestore, storage, crashlytics]     │
       │ -     emulator-strategy: dev-project                                  │
       │ -     block-prod-writes: true                                         │
       │ +   rest:                                                             │
       │ +     base-url:      https://api.meobonsai.com                        │
       │ +     auth-scheme:   bearer                                           │
       │ +     error-format:  rfc7807-problem-details                          │
       │                                                                       │
       │   ticketing:                                                          │
       │     post-back:                                                        │
       │ -     on-readiness-ready: true                                        │
       │ +     on-readiness-ready: false                                       │
       │ -     on-feature-done:    true                                        │
       │ +     on-feature-done:    false                                       │
       │                                                                       │
       │   persona:                                                            │
       │ -   drill-down-aggressiveness: medium                                 │
       │ +   drill-down-aggressiveness: high                                   │
       │ -   closing-style: didactic                                           │
       │ +   closing-style: brief                                              │
       │                                                                       │
       │   cards.active:                                                       │
       │ -   - name: koin-annotations                                          │
       │ -   - name: firebase-auth                                             │
       │ -   - name: firebase-firestore                                        │
       │ -   - name: firebase-storage                                          │
       │ -   - name: crashlytics                                               │
       │ +   - name: hilt                                                      │
       │ +   - name: rest-ktor                                                 │
       │                                                                       │
       ╰───────────────────────────────────────────────────────────────────────╯

       ╭── .claude/cards/  (snapshot changes) ─────────────────────────────────╮
       │   - koin-annotations/ · firebase-auth/ · firebase-firestore/          │
       │     firebase-storage/ · crashlytics/      (move to .bak/ then delete) │
       │   + hilt/                  (copy from canonical · sha256: 7a3b...)    │
       │   + rest-ktor/             (copy from canonical · sha256: 9f1e...)    │
       ╰───────────────────────────────────────────────────────────────────────╯

       ╭── .claude/inventory/conventions.yaml ─────────────────────────────────╮
       │ -   di-pattern: koin-annotations                                      │
       │ +   di-pattern: hilt                                                  │
       ╰───────────────────────────────────────────────────────────────────────╯

       ╭── .claude/workflow-config-history.jsonl ──────────────────────────────╮
       │ + 1 new entry appended (reconfigure event)                            │
       ╰───────────────────────────────────────────────────────────────────────╯

       Resumo:
         8 mudanças · 5 arquivos · 5 cards removidos · 2 cards adicionados
         backup automático em .bak/ pra rollback se algo falhar
```

**Note:** o diff é completo, agrupado por arquivo, anotado com `+`/`-` no
estilo unified diff. Sem surpresas pós-apply. Para diffs grandes (> 100
linhas), oferece `forge raw cat-diff` pra abrir em pager.

---

## Cena 7 — Gate de confirmação (45–48s)

Mentor calmo firme no gate. Pergunta direta, sem ambiguidade.

```
[0:45] Aplicar essas 8 mudanças?

       Antes de dizer sim, lembra:
         · cards/koin-annotations → .bak/ (recuperável por 7 dias)
         · todos os agents passam a receber prompts de Hilt + REST
         · próximas features usam os novos defaults
         · workflow-config-history.jsonl registra quem mudou o quê e quando

       [s = aplicar  ·  n = cancelar  ·  d = mostrar diff de novo  ·  e = editar plano]

> s
```

**Variação — usuário cancela:**

```
> n

       Cancelado. Nada foi escrito.
       
       Plano de diff salvo em .claude/.reconfigure-draft.yaml caso queira
       retomar depois — rode `forge reconfigure` de novo e eu detecto o
       draft automaticamente (sem flag de resume).
```

**Edge: Ctrl-C entre confirmação e apply**

```
^C

       Interrompido entre confirmação e escrita.
       Verifico se algo foi tocado... ✓ nada. Saindo limpo.
```

**Note:** o draft salvo permite retomar sessão depois sem refazer a revisão
toda. Reconfigure é interruptible em qualquer ponto até começar a escrita.

---

## Cena 8 — Apply cinemático (48–60s)

Cada arquivo aparece com timing real, igual init. Backup antes de cada
escrita.

```
[0:48] ⚡ Aplicando mudanças

       ├ backup workflow-config.yaml → .bak/2026-05-28T16-12-44/           ✓
       ├ removing cards (5)
       │   ├ koin-annotations · firebase-auth · firebase-firestore         ✓
       │   └ firebase-storage · crashlytics  → .bak/                       ✓
       ├ installing cards (2)
       │   ├ hilt        from canonical (sha256 ✓ · conflicts ✓ · merged ✓) ✓
       │   └ rest-ktor   from canonical (sha256 ✓ · conflicts ✓ · merged ✓) ✓
       ├ rewriting workflow-config.yaml                                    ✓
       ├ updating inventory/conventions.yaml                               ✓
       ├ re-merging hooks (.claude/hooks/)                                 ✓
       └ appending workflow-config-history.jsonl                           ✓
```

**Edge: apply falha no meio**

```
       ├ installing cards (2)
       │   ├ hilt                   from canonical                         ✗ FAIL
       │   │   └ sha256 mismatch — canonical may be corrupt
       │
       ⚠ Apply parou no meio. Rollback automático iniciando...
       
       ├ restoring workflow-config.yaml from .bak/                         ✓
       ├ restoring cards from .bak/                                        ✓
       ├ inventory/conventions.yaml restored                               ✓
       └ history.jsonl entry rolled back (last line removed)               ✓
       
       Estado restaurado. Investigue:
         forge doctor
         forge raw verify-card hilt
       
       Nada foi mantido em meio termo.
```

**Edge: card source remote indisponível**

```
       │   └ rest-ktor              from canonical                         ⚠
       │       └ canonical unreachable, trying local cache...              ✓
       │           (using cached snapshot from 2026-05-20)
```

**Note:** rollback é atômico via `.bak/`. Apply nunca deixa o repo em estado
parcial. Qualquer falha → estado anterior 100%.

---

## Cena 9 — Verificação pós-apply (60–65s)

Reconfigure dispara um doctor scope `quick` automaticamente (chamada interna,
sem flag pública). Mentor calmo não confia em si mesmo sem checar.

```
[1:00] 🩺 doctor (quick) — chamado internamente

       ├ schema · slug · preset · platforms        ✓ (RULE-001..004)
       ├ cards exist · sha256 · requires/conflicts ✓ (RULE-005..007) 9/9
       ├ paths exist · conventions populated       ✓ (RULE-008..009)
       ├ backend.rest.base-url valid               ✓ (RULE-010)
       ├ ticketing MCP callable                    ✓ (RULE-012)
       ├ workflow strictness · persona installed   ✓ (RULE-013..014)
       ├ hooks executable                          ✓ (RULE-017)
       └ no active feature lock                    ✓ (RULE-018)
       
       doctor: passing (15/15 quick checks)
```

**Edge: doctor falha pós-apply**

```
       ├ backend.rest.base-url valid           ✗ (RULE-010)
       │   reason: malformed URL "htps://api.meobonsai.com" (typo?)
       
       doctor: failing
       
       1 problema introduzido por essa reconfigure. Opções:
         • forge reconfigure        corrigir agora (recomendado)
         • forge undo               desfazer essa reconfigure inteira (escolher "last action")
         • forge raw edit-config    edição manual (use por sua conta)
```

**Note:** doctor é última fronteira de qualidade. Se passa aqui, reconfigure
deu certo. Se falha, mentor calmo oferece 3 saídas claras.

---

## Cena 10 — History entry (65–66s)

Entrada permanente no log de mudanças de config. Auditável.

```
[1:05] 📝 workflow-config-history.jsonl

       Appended:
       {
         "timestamp":      "2026-05-28T16:12:44Z",
         "event":          "reconfigure-applied",
         "actor":          "thiago.pacheco@inchurch.com.br",
         "forge-version":  "1.0.0",
         "schema-version": 1,
         "changes": [
           {"path": "paths.feature-roots.android",   "from": "androidApp/feature", "to": "androidApp/features"},
           {"path": "conventions.di-pattern",        "from": "koin-annotations",   "to": "hilt"},
           {"path": "backend.provider",              "from": "firebase",           "to": "rest"},
           {"path": "persona.drill-down-aggressiveness", "from": "medium",         "to": "high"},
           {"path": "cards.active", "removed": ["koin-annotations","firebase-*","crashlytics"], "added": ["hilt","rest-ktor"]}
         ],
         "diff-bytes": 1842,
         "doctor-status": "passing"
       }
```

**Note:** history.jsonl é commitado em git junto com `workflow-config.yaml`.
Time inteiro vê quem mudou o quê. Audit trail completo.

---

## Cena 11 — Fechamento + sugestão (66–68s)

Mentor calmo encerra didático, aponta próximo passo natural.

```
[1:07] ✨ Reconfigure aplicado

       8 mudanças · 5 arquivos · doctor passando · 1 entrada no history
       
       Resumo do que mudou:
         📦 Cards:     -5 (Firebase + Koin), +2 (Hilt + REST Ktor)
         🔥 Backend:   Firebase → REST (https://api.meobonsai.com)
         📁 Paths:     android feature root atualizado
         🎭 Persona:   drill-down high · closing brief
         🎫 Ticketing: post-back automático desligado
       
       O que sugiro fazer agora:
         · forge plan                   testa o novo setup com uma feature
         · forge reconfigure → "rebuild graph"  regenera graph com novos paths
         · git add .claude/             commit do novo setup pro time
       
       Os snapshots antigos ficam em .claude/cards/.bak/ por 7 dias
       (limpeza automática). Se algo der errado:
         forge undo            (e escolher "last action" no menu)
       
       Pronto.
```

---

## Variações resumidas

| Variação | Cenas afetadas | Tom |
|---|---|---|
| **Persona-only tweak** | 5.1 apenas; diff de 2 linhas | Rápido, didático mas econômico |
| **Card swap** (Hilt → Koin) | 5.2 + resolver pede remover dependente primeiro | Didático sobre impacto |
| **Path restructure** | 5.3 detecta automaticamente, oferece update | Mostra disco vs config lado a lado |
| **Backend change** | 5.4 grande; cards mudam; novo bloco backend | Confirma duas vezes antes de marcar |
| **Preset change refusal** | Cena 4 redireciona pra new-init em branch | Firme, sem aplicar nada |
| **Diff vazio** | Pula direto pra "nada mudou" | Cena 6 + saída sem escrita |
| **Active feature lock** | Para na Cena 1 com refusal contract | Firme + opções claras |

---

## Edge cases (apêndice)

### 1. Active feature lock

Coberto na Cena 1. Recusa imediata, sem fallback. Mensagem exata do contrato
em `memory.md` §L1 as a lock mechanism. Nenhum byte escrito.

### 2. Schema-version mismatch

Coberto na Cena 2. Se config.schema-version < binário: pede
`forge raw migrator-N-to-M` primeiro (raw é o escape hatch oficial pra
migrations). Se config.schema-version > binário: pede upgrade do forge.
Reconfigure nunca opera em schema desconhecido.

### 3. User cancels mid-diff (Ctrl-C entre confirm e apply)

Coberto na Cena 7. Sai limpo, nada escrito. Draft salvo em
`.claude/.reconfigure-draft.yaml` — pra retomar basta rodar `forge reconfigure`
de novo (auto-detect, sem flag). Se Ctrl-C **durante** apply: rollback
automático via `.bak/` (Cena 8).

### 4. Card conflict introduced

Coberto na Cena 5.2. Resolver detecta no momento da revisão (antes do diff
preview), explica conflito de capability, pede pra remover dependente
primeiro. Nunca chega no diff preview em estado inválido.

### 5. Network needed but unavailable

Coberto na Cena 8 (edge). Card cuja origem é canonical remote → tenta cache
local primeiro. Se sem cache e sem rede → falha graciosa com mensagem clara
+ rollback. Não trava esperando rede.

### 6. Diff vazio (usuário revisou tudo mas manteve tudo igual)

```
[0:35] 📋 Plano de diff
       
       Nenhuma mudança detectada. Você revisou tudo mas decidiu manter
       como estava. Tudo certo — vou sair sem escrever nada.
       
       (Se isso foi por engano, roda `forge reconfigure` de novo.)
```

Sai sem tocar `workflow-config.yaml`, sem entrada no history. Reconfigure é
**idempotente** quando nada muda.

### 7. Apply fails mid-flight

Coberto na Cena 8 (edge). Rollback automático e atômico via `.bak/`. Estado
final: idêntico ao anterior à reconfigure. History.jsonl tem a última linha
removida (entrada nunca foi flushada). `forge doctor` confirma integridade
após rollback.

---

## Design points this script crystallizes

| Implicit decision | Practical implication |
|---|---|
| **Lock check é absolute first** | Nenhuma cena 2+ executa se há feature ativa. Memória > config. |
| **Snapshot antes de perguntar** | Cena 3 sempre. Nunca pergunta no escuro. |
| **Diff preview completo antes de qualquer escrita** | Cena 6 obrigatória. Confirma o que o user vê. |
| **Backup `.bak/` automático** | Rollback nunca depende de git stash. |
| **Doctor pós-apply automático** | Reconfigure não confia em si. |
| **History.jsonl append-only** | Audit trail commitado em git. |
| **Idempotência** | Diff vazio = sai sem tocar nada. |
| **Preset/platforms/slug imutáveis** | Forçam novo init em branch dedicada. |
| **Total time: 60–70s típico** | Mais rápido que init (sem scan profundo). |

---

## Graph rebuild + reuse intelligence re-queue

Quando o usuário escolhe `[ ] graph` → "rebuild full" no menu de reconfigure,
o engine executa duas operações em sequência:

```
[0:42] Rebuilding graph…
        parsing: 1247/1247
        ✓ 1247 files · 5892 symbols · 14103 edges · 8214ms

[0:51] ✓ 3 reuse proposal(s) (re)queued — `forge evolve`
```

A segunda linha vem de `engine/graph/duplicates.queue_proposals_from_table`:
ao rebuildar o graph, qualquer mudança no codebase (extensions adicionadas,
movidas ou removidas) reflete na detecção. Fingerprints SHA-256 são **group
identity** (não membership), então:

- Mesmo grupo cresceu (4ª duplicação aparece): payload da proposta refresca
  com locations atualizadas; entry NÃO duplica.
- Grupo encolheu (alguém já consolidou): proposta antiga não some
  automaticamente — usuário aplica/rejeita normalmente.
- Grupo desaparece (consolidação completa): proposta vira stale → será
  removida no próximo evolve scan (Cena 13 evolve roteiro).
- Rejeição persiste: fingerprint na `rejected-evolutions.yaml` impede
  re-proposta. Mentor calmo: rejeitar uma vez é pra sempre.

Quando o codebase está limpo:

```
[0:42] Rebuilding graph…
        ✓ 1247 files · 5892 symbols · 14103 edges · 8214ms
```

(sem linha de re-queue — silêncio é o sinal de OK.)

---

## Init vs reconfigure (cheat sheet)

| Aspecto | init | reconfigure |
|---|---|---|
| Pré-condição | config ausente | config presente |
| Lock check | n/a | **primeiro de tudo** |
| Scan profundo do repo | sim (+ graph build) | só paths mudados |
| Cards | instala preset inteiro | add/remove/upgrade incremental |
| Perguntas | 4 grupadas + ticketing | só do que user marcou |
| Tempo típico | 85–90s | 60–70s |
| Output final | mapa cinemático grande | resumo compacto + sugestões |

Init é **descoberta**. Reconfigure é **cirurgia**. Mesma voz, escopos
diferentes.
