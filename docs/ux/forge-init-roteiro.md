# `forge init` — roteiro end-to-end

The cinematic UX of `forge init`. Each line that appears in the terminal,
with timing, voice in mentor-calmo tone.

## Context

- Standalone repo `~/Documents/feature-forge/` (canonical source)
- `forge` Bash dispatcher calls Python scripts
- Snapshot copy or symlink in `.claude/skills/feature-forge/` of target project
- New state recorded in target project's `.claude/`

---

## Cena 1 — Entrada (0.0–1.5s)

```
$ forge init

   ╭──────────────────────────────────────────╮
   │  feature-forge · v1.0.0                  │
   │  Planning workflow for mobile features.  │
   ╰──────────────────────────────────────────╯

Vou conhecer este projeto antes de te perguntar
qualquer coisa. Isso leva cerca de um minuto.
```

**Note:** calm tone, gente. No promise of speed it can't keep. No exaggerated ASCII.

---

## Cena 2 — Pre-flight (1.5–2.5s)

```
[0:01] Checando ambiente...
       ├ git repo                            ✓ (branch: feature/foo)
       ├ writable .claude/                   ✓
       ├ Python 3.10+                        ✓ 3.13.0
       └ existing forge config               not found (greenfield init)
```

**Note:** if `.claude/workflow-config.yaml` already exists, switches to
`existing forge config ✓ → use 'forge reconfigure' instead?` and exits gently.

---

## Cena 3 — Scanning (2.5–10s, cinematográfico)

```
[0:03] 🔍 Scanning repo
       ├ project root indexed
       │
       ├ Languages detected
       │   ├ Kotlin                   234 files
       │   ├ Swift                     89 files
       │   └ TypeScript                47 files
       │
       ├ Build systems
       │   ├ Gradle (settings.gradle.kts)
       │   ├ Xcode (iosApp.xcodeproj)
       │   └ npm (webApp/package.json)
       │
       └ Modules                              4
           shared · androidApp · iosApp · webApp
```

```
[0:08] 🧭 Inferring stack
       ├ KMP detected (shared/ + kotlin("multiplatform"))
       ├ Compose detected (androidx.compose.* in androidApp)
       ├ Navigation 3 detected (androidx.navigation3.*)
       ├ Koin Annotations detected (@Module @ComponentScan in shared)
       ├ SKIE detected (skie configure block in shared/build.gradle.kts)
       ├ SwiftUI detected (NavigationStack + .swift)
       ├ Firebase detected (google-services.json + GoogleService-Info.plist)
       │   ├ Auth · Firestore · Storage · Crashlytics
       │   └ Project IDs: bonsai-meo-dev (debug), bonsai-meo (release)
       └ React + Vite detected (webApp/)
```

**Note:** each line appears sequentially with ~150ms delay. Feels "thinking,"
not "spamming." Natural pause before next scene.

---

## Cena 4 — Convenções (10–18s)

```
[0:10] ⚡ Extracting conventions from 4 existing features
       ├ Folder layout (Android): {screen}Screen.kt + Content.kt + Components.kt
       ├ Folder layout (iOS):     {Screen}ScreenView.swift + Content + Components
       ├ State pattern:           StateUI<T> sealed class
       ├ DI pattern:              Koin Annotations (@KoinViewModel, @Single, @Factory)
       ├ Navigation:              AppRoute sealed interface (NavKey)
       └ Test pattern:            JUnit 5 + Turbine + assertIs<T>()
       
       saved to .claude/inventory/conventions.yaml
```

```
[0:14] ⚡ Design system inventory
       ├ Pattern detected:        "Meo*" prefix
       ├ Base paths:
       │   ├ Android:             androidApp/core/designsystem/.../atoms|molecules
       │   ├ iOS:                 iosApp/iosApp/.../Atoms|Molecules
       │   └ Web:                 webApp/src/shared/components/{atoms|molecules}
       ├ Components catalogued:   28
       │   atoms (8) · molecules (14) · organisms (6)
       ├ Status breakdown:        24 beta · 4 stable
       ├ Tokens detected:         colors (12) · spacing (9) · typography (2) · radii (7)
       └ Coverage Android↔iOS:    27/28 (96%)
       
       saved to .claude/inventory/design-system.yaml
```

```
[0:16] ⚡ i18n inventory
       ├ Source of truth:         shared/resources/i18n/
       ├ Format:                  JSON per locale
       ├ Locales:                 pt-BR, en-US, es-ES
       ├ Total keys:              487
       ├ Generation script:       scripts/i18n/generate.py
       └ Verification script:     scripts/i18n/verify.py
       
       saved to .claude/inventory/i18n.yaml
```

**Note:** here the user starts to feel the "wow." Skill **shows it understands
the project** without asking. Future L2 memory will be seeded from this.

---

## Cena 5 — Codebase graph (18–48s)

```
[0:18] 🗺️ Building codebase graph
       ├ Indexing files                        [████████████████░░] 87%
       ├ Resolving imports                     [████████████████░░] 92%
       ├ Mapping DI providers                  ✓
       ├ Mapping routes                        ✓
       ├ Mapping DS component usage            ✓
       ├ Mapping i18n key usage                ✓
       └ Mapping test coverage                 ✓
       
       Graph stats:
         · 1,247 symbols
         · 3,892 edges
         · 19 routes
         · 34 DI providers
         · 487 i18n keys → 1,103 usage sites
       
       saved to .claude/graph.db
```

**Note:** graph build is the slowest step. Real progress bar (not fake). If
> 60s in big repos, shows "(grandes repos podem levar mais tempo, normal)"
to reassure.

---

## Cena 5.5 — Reuse intelligence scan (48–50s)

Logo após o graph build, ainda dentro do mesmo step cinemático, o init varre
o graph recém-construído atrás de oportunidades de reuso já presentes no
codebase. **Brownfield** quase sempre tem helpers duplicados em features que
nasceram em momentos diferentes — surfaçar isso aqui é o que faz o forge
"nascer com inteligência" no primeiro contato com o projeto.

```
[0:19] 🔍 Scanning for reuse opportunities…
       ├ Same-module duplications                ✓
       ├ Cross-module duplications               ✓
       ├ Redundant platform-specific             ✓
       ├ Near-duplicates (signature match, body diff) ✓
       ├ KMP-migration candidates (Swift ↔ Kotlin shared) ✓
       └ TypeScript duplicate helpers            ✓

       3 reuse-intelligence proposal(s) queued — `forge evolve` to review.
```

**Quando há findings:**

- Cada finding vira proposta em `.claude/proposed-evolutions.yaml` com
  fingerprint estável (SHA-256). Idempotente — re-rodar init não duplica.
- 6 categorias possíveis, descritas em
  `docs/schemas/proposed-evolutions.md § Reuse Intelligence`.
- User revisa via `forge evolve` (não automático). Confidence < 0.50
  sempre exige review manual.

**Quando NÃO há findings:**

```
[0:19] 🔍 Scanning for reuse opportunities…
       ✓ no reuse opportunities detected
```

Mentor calmo: zero findings é um sinal positivo — projeto já está
internamente consistente OU é pequeno demais pra duplicar.

---

## Cena 5.6 — Incremental detection hook (50–51s)

Escreve `.claude/hooks/post-edit-detect-duplications.sh` que pode ser
referenciado em `.claude/settings.local.json` para detection inline durante
edits. **Wiring é opt-in** — não modificamos settings.local.json
automaticamente para não surpreender.

```
[0:20] · hook em .claude/hooks/post-edit-detect-duplications.sh
        (referencie em settings.local.json pra detection inline)
```

Quando ativado, edits que introduzem duplicações novas aparecem inline no
terminal:

```
⚠ 1 reuse-intelligence finding(s) touching edited files:
  · [duplicate-cross-module] FirebaseAnalytics.logEventSafely (conf=0.85)
      → shared/core/.../util/
      shared/feature/auth/.../AuthAnalytics.kt:42
      shared/feature/bonsai/.../BonsaiAnalytics.kt:51
  Run `forge evolve` to review proposals.
```

Não bloqueia o edit — informa apenas.

---

## Cena 6 — Confirmação + perguntas grupadas (48–60s)

Now the skill **shows what it understood** and asks only what it can't detect.

```
[0:48] 📋 Resumo do que detectei

   Projeto:        MeoBonsai
   Plataformas:    Android · iOS · Web (KMP shared)
   Stack:          Compose · SwiftUI · React
   DI:             Koin Annotations
   Navigation:     Nav3 (Android) · NavigationStack (iOS) · React Router (Web)
   Backend:        Firebase (Auth + Firestore + Storage + Crashlytics)
   Design System:  Meo* prefix, 28 componentes
   i18n:           shared/resources/i18n (3 locales)
   
   Preset proposto:  kmp-mobile (auto-match 96%)
   Núcleo do preset: 8 cards
     kotlin-language · kmp-shared · compose-screens · swiftui-screens
     koin-annotations · skie-bridge · nav3 · swiftui-navigation

   Backend ainda não confirmado — vou perguntar a seguir (Cena 6.5).

   Está correto?  [Y / corrigir / detalhar cards]
```

User accepts → proceeds. If "corrigir" → enters mode of card-by-card override.

```
[0:52] Algumas coisas eu não consigo descobrir lendo o repo.
       Quatro perguntas, todas com contexto.
```

**Grouped AskUserQuestion** (4 questions in single panel):

```
1. As features vêm de tickets externos?
   Detectei Atlassian MCP instalado mas não autenticado.
   
   • Sim, Jira (vou perguntar credenciais agora)
   • Sim, Linear
   • Sim, GitHub Issues
   • Não, specs vivem só no repo

2. Em que ambiente Firebase você desenvolve?
   Detectei bonsai-meo-dev e bonsai-meo no repo.
   
   • bonsai-meo-dev (recomendado pra desenvolvimento)
   • bonsai-meo (production — vou bloquear writes em alguns casos)
   • Outro projeto

3. Pre-commit review é bloqueante?
   Mentor calmo precisa saber: barro o commit se review falhar?
   
   • Sim, sempre (qualidade > velocidade)
   • Sim com override manual (--force)
   • Não, review é informativo

4. Quão estrito o readiness gate?
   Quantos docs preciso ter prontos antes de implementar?
   
   • Strict — todos os 14 (intake, PRD, screen, BDD, UI state, nav, data,
     analytics, test, tech-spec, task-breakdown, tasks, readiness, handoff)
   • Standard — 10 essenciais
   • Lean — 5 (intake, PRD, BDD, task-breakdown, tasks)
```

**Note:** each question cites what was detected. Mentor calmo: nunca pergunta
no escuro.

---

## Cena 6.5 — Escolha do backend (preset kmp-mobile) (60–63s)

O preset `kmp-mobile` cobre só o núcleo cliente (Kotlin, KMP, Compose, SwiftUI,
Koin, SKIE, Nav3, NavigationStack). A escolha do backend é uma decisão
**explícita** do usuário porque muda contratos: API contract, persistence,
auth, security rules. O engine apresenta os quatro `backend-candidates`
declarados em `presets/kmp-mobile.yaml` com os signals que casaram.

```
[1:00] 🧩 Backend — preciso da sua escolha

   O preset kmp-mobile traz só o cliente. Para o backend, encontrei estes
   candidatos no repo:

   1. firebase-stack   (signals casados: 3/3)
      • google-services.json encontrado em composeApp/
      • GoogleService-Info.plist encontrado em iosApp/Config/
      • firebase-firestore + firebase-auth declarados em build.gradle
      Cards extra: firebase-auth · firestore-persistence
                   firestore-security-rules · firebase-storage · crashlytics

   2. rest-stack       (signals casados: 0/2)
      • Nenhum ApiEndpoints.kt detectado
      • Sem Ktor/OkHttp em build.gradle
      Cards extra: rest-api-contract · auth-token-bearer

   3. hybrid-firebase-auth-rest-data  (signals casados: 1/3)
      • Firebase Auth detectado, mas data layer parece toda Firestore
      Cards extra: firebase-auth · rest-api-contract · crashlytics

   4. local-only       (signals casados: 1/2)
      • Room schemas em shared/feature/*/data/local/
      • Mas há tráfego de rede no repo — improvável que seja só local
      Cards extra: room-database

   > Qual cenário descreve este projeto?
     [1 / 2 / 3 / 4 / personalizar cards manualmente]
```

User picks 1 (firebase-stack):

```
[1:02] ✓ firebase-stack confirmado.

   Cards ativados no total (8 do preset + 5 do backend): 13
     kotlin-language · kmp-shared · compose-screens · swiftui-screens
     koin-annotations · skie-bridge · nav3 · swiftui-navigation
     firebase-auth · firestore-persistence · firestore-security-rules
     firebase-storage · crashlytics

   Conflitos detectados: 0
   Capabilities resolvidas: persistence-server (firestore-persistence),
                            auth (firebase-auth), crash-reporting (crashlytics)

   Sigo com a configuração?  [Y]
```

Se o usuário escolher "personalizar cards manualmente", o engine entra no
modo card-by-card override (mesmo modo da Cena 6, "corrigir").

**Note:** o engine SEMPRE pergunta o backend mesmo com 1 candidato com 3/3
signals — é uma decisão arquitetural que merece confirmação humana. Mentor
calmo: nunca decide backend sozinho.

---

## Cena 7 — Jira auth (se aplicável) (60–75s)

If user chose Jira:

```
[1:00] 🔐 Atlassian MCP authentication
       
       Vou abrir o fluxo do MCP. Após login, volto aqui.
       
       ⠋ Waiting for authentication...
       
       ✓ Authenticated as thiago.pacheco@inchurch.com.br
       ✓ Workspace: inchurch.atlassian.net
       
       Projetos disponíveis (15):
         BONSAI  ·  IN  ·  MEO  ·  DESIGN  ·  ...
       
       > Qual o project key padrão pra features deste repo? BONSAI
       
       ✓ Configurado
```

**Note:** if MCP not installed, offers install via find-skills (with permission).
If auth fails, defers without blocking init.

---

## Cena 8 — Card snapshot + memory init (75–80s)

```
[1:15] 📦 Installing 12 cards (snapshot copy from feature-forge canonical)
       ├ kotlin-language                       ✓
       ├ kmp-shared                            ✓
       ├ compose-screens                       ✓
       ├ swiftui-screens                       ✓
       ├ koin-annotations                      ✓
       ├ skie-bridge                           ✓
       ├ nav3                                  ✓
       ├ swiftui-navigation                    ✓
       ├ firebase-auth                         ✓
       ├ firebase-firestore                    ✓
       ├ firebase-storage                      ✓
       └ crashlytics                           ✓
       
       Snapshot copiados pra .claude/cards/
       Cada card é editável localmente sem afetar o canonical.

[1:18] 🧠 Initializing memory
       ├ L1 (per-feature)                      ready (empty)
       ├ L2 (project)                          seeded from inventory
       │   ├ 6 convention rules extracted
       │   ├ 28 DS components catalogued
       │   └ 487 i18n keys indexed
       └ L3 (user-global)                      linked to ~/.claude/memory/
       
       saved to .claude/memory/
```

**Note:** L4 (skill cross-project) and L5 (per-card) only appear if the skill
has been used in another project. Greenfield shows only L1–L3.

---

## Cena 9 — Mapa final cinemático (80–85s)

The culmination. User sees for the first time **the complete map of the project**
organized by the skill.

```
[1:20] ✨ Forge ready
       
       ╭───────────────────────── feature-forge · MeoBonsai ─────────────────────────╮
       │                                                                              │
       │   📦 PROJETO                                                                 │
       │     KMP · Compose · SwiftUI · React                                          │
       │     12 cards ativos                                                          │
       │     Preset: kmp-mobile-firebase                                              │
       │                                                                              │
       │   🧱 MÓDULOS  (4)                                                            │
       │     shared/              [KMP]                                               │
       │     androidApp/          [Android]                                           │
       │     iosApp/              [iOS]                                               │
       │     webApp/              [Web]                                               │
       │                                                                              │
       │   🌳 FEATURES  (12)                                                          │
       │     ●  auth              done    2026-04-01                                  │
       │     ●  bonsai            done    2026-04-18                                  │
       │     ●  bonsai-detail     done    2026-04-25                                  │
       │     ◐  register          partial 2026-05-10  (3 tasks open)                  │
       │     ○  water-tracker     planned                                             │
       │     ...                                                                      │
       │                                                                              │
       │   🎨 DESIGN SYSTEM  (28)                                                     │
       │     atoms (8) · molecules (14) · organisms (6)                               │
       │     Coverage Android ↔ iOS: 96%                                              │
       │                                                                              │
       │   🌐 I18N                                                                    │
       │     487 keys × 3 locales (pt-BR · en-US · es-ES)                             │
       │                                                                              │
       │   🔥 BACKEND                                                                 │
       │     Firebase                                                                 │
       │       Auth · Firestore (12 collections) · Storage · Crashlytics              │
       │       Dev project: bonsai-meo-dev                                            │
       │                                                                              │
       │   🎫 TICKETING                                                               │
       │     Jira (inchurch.atlassian.net · default project: BONSAI)                  │
       │                                                                              │
       ╰──────────────────────────────────────────────────────────────────────────────╯
       
       Próximos passos sugeridos:
         forge plan           começar uma feature nova
         forge graph query    explorar o mapa do projeto
         forge doctor         validar saúde do setup
```

**Note:** this is the "magic moment." The cena that sells. Investment in
polish here is high: perfect alignment, spacing, icons, choice of numbers to
highlight.

---

## Cena 10 — Persistência final + git hint (85–87s)

```
[1:25] 📝 Saved to project:
       
       .claude/
         workflow-config.yaml           your config & decisions
         cards/                         12 cards (snapshots)
         inventory/                     project knowledge extracted
         memory/                        L1, L2, L3 hooks
         graph.db                       codebase graph (SQLite)
       
       💡 Dica: commit .claude/ no git pra o time todo herdar este setup.
              Exceções: .claude/forge/state/lifecycle/*, .claude/graph.db
              (já incluí em .claude/.gitignore)
       
       Pronto.
```

---

## Design points this script crystallizes

| Implicit decision | Practical implication |
|---|---|
| Cinematic has **real timing**, not simulated | Each step finishes when work finishes. No fake `sleep`. |
| Every detection shows **what** and **where** found | Reinforces transparency. User can audit. |
| Questions come in **single block** with context | No bombardment. No interruption. |
| Final map is **single canvas** with visual hierarchy | Aesthetic investment. This is the screenshot. |
| `.gitignore` is **auto-created** | Small detail showing care for team workflow. |
| Total time: **85–90 seconds** | Acceptable. Not instant, not suffocating. |

---

## Edge cases the script needs to handle

1. **Greenfield total** (empty repo) — no features to extract conventions, no
   DS, no i18n. Questionnaire is longer, structure is the same.
2. **Repo bagunçado** (2 patterns coexisting) — reports conflict: "Detected 7
   features with Hilt and 4 with Koin — which is the current pattern?"
3. **Multi-subproject** (monorepo with /mobile and /web) — asks which
   sub-project to init.
4. **Repo enorme** (> 50k files) — graph build will take long. Shows real ETA,
   option to skip subdirs.
5. **Sem Internet** (no MCP, no Context7) — init proceeds with locally
   available data, marks externals as deferred.
