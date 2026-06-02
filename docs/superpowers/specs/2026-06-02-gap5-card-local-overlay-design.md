# Gap 5 — Card local overlay (design)

**Data:** 2026-06-02
**Origem:** brainstorming session orchestrator-mantenedor + thiago.pacheco
**Status:** APROVADO — pronto pra `superpowers:writing-plans`
**Gap fonte:** `docs/design/04-pending.md §Gap 5 — Cenário D2: Stack fora do catálogo`

## Contexto e motivação

feature-forge v1.1.0 está em produção mas nunca foi pilotado num projeto real fora do próprio repo. O projeto-alvo do usuário é um KMP Android+iOS em modularização. A stack identificada cobre parcialmente o catálogo canônico: Koin (canon), Room (canon), Compose/SwiftUI (canon) — mas Retrofit (sem card v1) e SharedPreferences (sem card; v1 só tem DataStore como `local-prefs-storage`) ficam de fora. Sem cobertura, `forge init` no projeto-alvo trava em `validate_capability_labels` com signals órfãos.

Gap 5 já declara isso explicitamente em pending: "20 cards canônicos cobrem só stack KMP-mobile; projetos com Hilt, Apollo, Realm não têm caminho oficial". A distinção em relação ao Gap 14 (preset coverage) é nítida — Gap 14 é "preset canônico errado pra começar"; Gap 5 é "stack canônica + algumas peças exóticas que precisam de caminho oficial sem release nova".

A solução escolhida é **híbrida**: ship Retrofit + SharedPreferences como cards canon novos (cobre o piloto imediato) **e** ship o mecanismo de overlay completo (cobre o próximo caso exótico sem release nova). Ambos juntos, escopo de ~2 sprints, ~1660 LOC. Híbrido evita duas falsas economias: shipar só os cards (não destrava o próximo time que entrar com Hilt) ou shipar só o overlay (deixa o piloto atual pendurado).

## Decisões de design tomadas no brainstorming

1. **Híbrido (canon + overlay infra)** — não puro canon (não escala fora do espaço amostral atual), não puro overlay (deixa o piloto sem solução pronta).
2. **`.claude/cards/local/` versionado** — team-shared no repo do projeto consumidor, não per-dev em home. Decisão alinhada com `validate_capability_labels` rodando em CI.
3. **Reservadas exigem promoção ao canon** — local não pode ativar label reservada. Promoção exige ADR + revisita do catálogo.
4. **Approach A (cascade simples)** — local só adiciona; conflito de nome canon×local = hard fail. Sem merge, sem override, sem precedência. Reversibility > flexibility.
5. **`legacy-marker` virou campo formal** — não metadata solto. Marker dispara 3-caminhos no init quando o detection prefere o legacy ao moderno (ex.: SharedPreferences vs DataStore).

## Seção 1 — Arquitetura geral

O overlay vive em dois lugares distintos: projeto consumidor (cards de equipe, versionados junto do código) e snapshot canon (já existente, gravado por `forge init`).

Cards canon vivem como **diretórios completos** sob `cards/<name>/` (schema oficial em `docs/schemas/card.md §Card anatomy`), e o overlay local espelha essa estrutura sob `.claude/cards/local/<name>/`. Não há single-file YAML em nenhum dos lados — a anatomia diretório-completo é load-bearing pra co-localizar templates, validators, agent-contributions e signals junto do `card.yaml` que os declara.

```
<projeto-consumidor>/
├── .claude/
│   ├── cards/
│   │   └── local/                          ← NOVO (versionado, team-shared)
│   │       └── <name>/
│   │           ├── card.yaml               (preenchido via prompts)
│   │           ├── README.md               (skeleton placeholder)
│   │           └── detection/
│   │               └── signals.yaml        (vazio com comentário até detection rodar)
│   ├── inventory/
│   │   ├── capability-labels.yaml          ← snapshot canon (já existe)
│   │   ├── capability-labels.local.yaml    ← NOVO (overlay, versionado)
│   │   ├── local-cards-manifest.yaml       ← NOVO (gerado, versionado)
│   │   └── ignored-signals.yaml            ← NOVO (gerado pelo caminho 2 do init)
│   └── settings.json
└── ...

~/Documents/feature-forge/
├── cards/                                   ← canon (já existe)
│   ├── koin-annotations/                    (estrutura dir completa)
│   │   ├── card.yaml
│   │   ├── README.md
│   │   ├── detection/signals.yaml
│   │   ├── templates/
│   │   ├── validators/
│   │   └── agent-contributions/
│   ├── room-database/                       (idem)
│   ├── retrofit-client/                    ← NOVO (canon, dir completo)
│   │   ├── card.yaml
│   │   ├── README.md
│   │   ├── detection/signals.yaml
│   │   ├── templates/
│   │   ├── validators/
│   │   └── agent-contributions/
│   └── shared-preferences-prefs/           ← NOVO (canon, dir completo, legacy-marker)
│       ├── card.yaml
│       ├── README.md
│       ├── detection/signals.yaml
│       ├── templates/
│       ├── validators/
│       └── agent-contributions/
└── docs/schemas/
    └── card.md                              ← MODIFICA (legacy-marker + local section)
```

**Princípios load-bearing preservados:**

- **Decision 9** (`card.yaml` é fonte canônica de capability) — local YAML usa mesmo schema, mesma validação.
- **Decision 10** (snapshot copy) — canon é snapshot em `.claude/inventory/`, não import runtime; local apenas estende esse snapshot.
- **Decision 22** (no runtime deps em outras skills) — overlay é arquivo plano lido por loader nativo da forge, sem dep externa.
- **Discipline §4** (`.bak` retention 7d) — remoção de card local em reconfigure passa por `.bak`, igual aos canônicos.

**Distinção canon × local é via path, não campo no YAML:** loader observa onde o `card.yaml` foi lido (`cards/<name>/` vs `.claude/cards/local/<name>/`) e tagga `card.origin` em memória (ver Seção 3). Nenhum campo `canonical: true` no schema — origem é propriedade do filesystem, não do conteúdo. Isso fortalece a separação porque um card local não pode mentir sobre ser canon mexendo num bool, e move o overlay layer (`.claude/cards/local/`) ainda é git-ignorable / git-versionado segundo política do time, sem precisar coordenar valor de flag.

## Seção 2 — Cards canon novos (Retrofit + SharedPreferences)

Ambos shippam no mesmo PR que o mecanismo overlay. Ficam em `cards/<name>/` (raiz da forge, estrutura diretório-completo conforme `docs/schemas/card.md §Card anatomy`), e o snapshotter de `forge init` passa a copiar os 22 canônicos (não 20).

Os YAMLs abaixo seguem o schema canon (`docs/schemas/card.md` linhas 80-223). Os arquivos satélites (`templates/*`, `validators/*`, `agent-contributions/*`, `README.md`) ficam como TODO de implementação — o spec declara intenção; o conteúdo concreto vem na phase de implementação dispatch-by-dispatch.

### 2.1 `cards/retrofit-client/card.yaml`

```yaml
# cards/retrofit-client/card.yaml
# ──────────────────────────────────────────────────────────────────────────
# Schema version: 1
# Retrofit2 HTTP client. Provider clássico de `http-client` em projetos
# Android-only ou Android-side de KMP onde Ktor multiplatform não é
# escolhido. Android-only é semântica derivada das signals (todas batem em
# arquivos Android-side), não declaração de campo.
# ──────────────────────────────────────────────────────────────────────────

schema-version: 1


# ── IDENTITY ──────────────────────────────────────────────────────────────
identity:
  name:         retrofit-client
  version:      1.0.0
  description:  "Retrofit2 HTTP client para Android / Android-side de KMP. Provider clássico de http-client quando Ktor multiplatform não é a escolha."
  category:     network
  maturity:     stable
  maintainer:   feature-forge-core
  created-at:   2026-06-02
  last-updated: 2026-06-02
  license:      MIT


# ── CAPABILITIES ──────────────────────────────────────────────────────────
provides:
  - http-client


# ── DEPENDENCIES ──────────────────────────────────────────────────────────
# kotlinx-serialization-json aparece como capability requerida porque
# converter padrão moderno usa kotlinx.serialization; quando o projeto
# usa Moshi/Gson, esses signals derivados ficam pra implementação
# parametrizar via config-defaults.
requires:
  - kotlin-language
  - serialization-json


# ── CONFLICTS ─────────────────────────────────────────────────────────────
conflicts-with:
  - ktor-client


# ── CONTRIBUTIONS ─────────────────────────────────────────────────────────
# TODO impl: preencher templates, validators, agent-prompts concretos.
# Spec declara intenção; conteúdo vem dispatch-by-dispatch.
contributes:
  templates: []
  validators: []
  agent-prompts: []
  config-defaults: {}


# ── DETECTION ─────────────────────────────────────────────────────────────
# Android-only é derivado: signals batem em build.gradle Android e em
# .kt com imports retrofit2. Sem campo target-platforms.
detection:
  signals:
    - type:       dependency
      file:       "**/build.gradle*"
      contains:   "com.squareup.retrofit2:retrofit"
      confidence: 0.5

    - type:       file-content
      glob:       "**/*.kt"
      contains:   "@retrofit2.http"
      confidence: 0.3

    - type:       file-content
      glob:       "**/*.kt"
      contains:   "import retrofit2"
      confidence: 0.2

  threshold: 0.6

  alternative-cards:
    - ktor-client


# ── DOCUMENTATION ─────────────────────────────────────────────────────────
documentation:
  readme:     README.md
  rules-link: "architecture_android"
```

### 2.2 `cards/shared-preferences-prefs/card.yaml`

```yaml
# cards/shared-preferences-prefs/card.yaml
# ──────────────────────────────────────────────────────────────────────────
# Schema version: 1
# SharedPreferences (Android). Provider legacy de `local-prefs-storage`.
# legacy-marker: true → quando coexistir com datastore-prefs detectado, init
# surfaca 3-caminhos (manter legacy / migrar / coexistir transição).
# Android-only é semântica derivada das signals.
# ──────────────────────────────────────────────────────────────────────────

schema-version: 1


# ── IDENTITY ──────────────────────────────────────────────────────────────
identity:
  name:         shared-preferences-prefs
  version:      1.0.0
  description:  "SharedPreferences (Android) como provider legacy de local-prefs-storage. Coexiste com datastore-prefs; init surfaca 3-caminhos quando ambos detectados."
  category:     storage
  maturity:     stable
  maintainer:   feature-forge-core
  created-at:   2026-06-02
  last-updated: 2026-06-02
  license:      MIT


# ── LEGACY MARKER ─────────────────────────────────────────────────────────
# Campo top-level opcional, aditivo ao schema canon (ver seção
# "Schema bump aditivo" abaixo).
legacy-marker: true


# ── CAPABILITIES ──────────────────────────────────────────────────────────
provides:
  - local-prefs-storage


# ── DEPENDENCIES ──────────────────────────────────────────────────────────
requires:
  - kotlin-language


# ── CONFLICTS ─────────────────────────────────────────────────────────────
# Coexistência é permitida (label auxiliar) mas init surfaca 3-caminhos
# quando ambos detectados — comportamento dirigido por legacy-marker, não
# por conflict hard.
conflicts-with:
  - datastore-prefs


# ── CONTRIBUTIONS ─────────────────────────────────────────────────────────
# TODO impl: preencher templates, validators, agent-prompts concretos.
contributes:
  templates: []
  validators: []
  agent-prompts: []
  config-defaults: {}


# ── DETECTION ─────────────────────────────────────────────────────────────
# Confidence por signal calibrada ligeiramente menor que datastore-prefs
# equivalente — reflete que evidência de SharedPreferences em codebase
# moderno é tipicamente legacy detectado, não escolha ativa. Threshold
# canônico 0.6 idêntico aos demais cards. Calibração via signal confidence
# individual, não via "budget" agregado fora do schema.
detection:
  signals:
    - type:       file-content
      glob:       "**/*.kt"
      contains:   "getSharedPreferences("
      confidence: 0.4

    - type:       file-content
      glob:       "**/*.kt"
      contains:   "PreferenceManager.getDefaultSharedPreferences"
      confidence: 0.3

    - type:       file-content
      glob:       "**/*.kt"
      contains:   "import android.content.SharedPreferences"
      confidence: 0.2

  threshold: 0.6

  alternative-cards:
    - datastore-prefs


# ── DOCUMENTATION ─────────────────────────────────────────────────────────
documentation:
  readme:     README.md
  rules-link: "architecture_android"
```

**Catálogo de capability-labels não muda.** `http-client` e `local-prefs-storage` já existem em v1.1; os dois novos cards são providers adicionais das mesmas labels (canon ganha alternativas, não invented labels novas).

**Threshold canônico (0.6) idêntico aos dois.** A calibração do "isso é legacy detectado, não escolha ativa" pra SharedPreferences se faz via **signal confidence individual** (cada signal SharedPrefs ganha valores ligeiramente menores que DataStore equivalente — detalhe fica pra implementação afinar contra o piloto). Sem campo agregado fora do schema; o schema canon já tem `threshold` + per-signal `confidence` suficientes pra modelar a diferença.

**Sem campo `target-platforms` no schema.** Plataforma é semântica derivada das signals (Retrofit signals só batem em arquivos Android-side; SharedPreferences idem). Adicionar campo declarativo redundante violaria reuso (mandamento #3) e o princípio "never invents" do `docs/design/00-vision.md §What feature-forge is NOT` — se a info já está nas signals, declarar de novo é invenção paralela.

## Schema bump aditivo — `legacy-marker`

Esta entrega adiciona **um único campo novo** ao schema canon de cards: `legacy-marker: bool` (opcional, default `false`), top-level no `card.yaml`.

**Justificativa de design:**

- **Top-level, não dentro de `identity`** — `legacy-marker` é flag de UX (dispara 3-caminhos no init quando coexiste com provider moderno da mesma capability), não metadata identitário (nome, versão, autor). Aninhar em `identity` mistura camadas conceituais distintas.
- **Campo opcional aditivo** — cards existentes (todos os 20 v1.1) continuam válidos sem mexer em nada. Forward-compat preserved.
- **`schema-version` permanece 1** — adição de campo opcional aditivo NÃO bumpa schema-version. Bump fica reservado pra mudanças que quebram leitores antigos (remoção de campo, mudança de tipo, novo required field). Esta é a política canônica de schema versioning e está alinhada com `docs/schemas/card.md`.

**Semântica operacional:**

- `legacy-marker: true` → init Step 7.5 lê esse flag. Quando 2+ cards proveem a mesma capability label e ao menos um tem `legacy-marker: true`, init dispara prompt 3-caminhos antes de materializar o plan (manter legacy / migrar pro moderno / coexistir explicitamente).
- `legacy-marker: false` ou ausente → comportamento default, cards coexistem normalmente segundo regras de `conflicts-with` declaradas.

**Doc-sync obrigatório no PR:**

- `docs/schemas/card.md` ganha entrada formal documentando o campo (seção entre `identity` e `provides`, ou logo após `identity`).
- `CHANGELOG.md` lista o campo em `### Added` (aditivo, não breaking).
- Validador `validate_card_yaml` aceita o campo opcional e passa-o intacto pro loader (sem agir sobre o valor — quem age é o init Step 7.5).

## Seção 3 — Loader cascade

A função `load_all_cards` passa a unir canon (snapshot) + local (live). Não há merge por nome — conflito é hard fail.

```python
# engine/cards/loader.py (assinatura conceitual)

def load_all_cards(project_root: Path) -> dict[str, Card]:
    """
    Carrega catálogo completo de cards na ordem cascade.

    Ordem:
      1. Canon: lê snapshot em <project>/.claude/inventory/cards/
         (gravado por forge init/reconfigure)
      2. Local: lê live <project>/.claude/cards/local/<name>/card.yaml

    Regras:
      - Conflito de nome canon×local → CardConflictError (hard fail)
      - Cada card recebe tag .origin = "canon" | "local"
      - Local com canonical=true → ValidationError (rejeitado no validator)
      - Local com provides ∈ reservadas → ValidationError (promoção exige ADR)

    Side-effects:
      - Grava local-cards-manifest.yaml listando locais detectados
        (versionado pra CI auditar)

    Edge cases:
      - .claude/cards/local/ inexistente: silent (canon-only)
      - <name>/ vazio (sem card.yaml): warning + skip
      - card.yaml malformado: ValidationError com path + linha
    """
    canon = _load_canon_snapshot(project_root)
    local = _load_local_overlay(project_root)

    conflicts = set(canon) & set(local)
    if conflicts:
        raise CardConflictError(
            f"Nomes em colisão canon×local: {sorted(conflicts)}. "
            f"Renomeie o card local ou abra ADR pra promoção ao canon."
        )

    for card in canon.values():
        card.origin = "canon"
    for card in local.values():
        card.origin = "local"

    _write_manifest(project_root, local)
    return {**canon, **local}
```

**Ordem da cascade é deliberada** — canon primeiro porque é o conjunto auditado (snapshot imutável até próximo `forge reconfigure`); local segundo porque é a extensão controlada pelo time. Inverter a ordem permitiria override silencioso, que viola Decision 4 (Approach A).

A tag `.origin` é load-bearing pra downstream: `forge graph` mostra origin no output, validators discriminam canon vs local em mensagens de erro, e o snapshotter sabe que locais não entram no snapshot canon.

## Seção 4 — Capability labels overlay

Local pode estender o catálogo de labels, mas não pode redefinir nem ativar reservada. Schema enxuto:

```yaml
# .claude/inventory/capability-labels.local.yaml
schema_version: 1
added:
  - name: feature-flag-remote
    description: >
      Capability de feature-flag remoto. Adicionado pelo time pra
      cobrir LaunchDarkly + Firebase Remote Config sem precisar
      promoção ao canon.
    target-platforms: [android, ios]
  - name: analytics-events-bus
    description: >
      Event bus interno pra fan-out de analytics events.
    target-platforms: [android, ios, kmp]

# PROIBIDO no schema (validator rejeita):
#   overrides: [...]            ← não pode redefinir canon label
#   reserved-promotions: [...]  ← promoção exige ADR no canon, não overlay
```

Loader de catálogo dentro do validator:

```python
# validators/_common.py — adição

def load_catalog(project_root: Path) -> CapabilityCatalog:
    """
    Catálogo efetivo = canon ∪ local (overlay).

    Guards:
      - Local label ∈ reservadas → ValidationError
        (promoção exige ADR + revisita decisão N do catálogo)
      - Local label ∈ active canon → ValidationError (colisão)
      - Local com chaves não-permitidas (overrides, reserved-promotions)
        → ValidationError
    """
    canon = _load_canon_catalog(project_root)
    local = _load_local_catalog(project_root)

    for label in local.added:
        if label.name in canon.reserved:
            raise ValidationError(
                f"Label local '{label.name}' está reservada no canon. "
                f"Promoção exige ADR + revisita decisão do catálogo."
            )
        if label.name in canon.active:
            raise ValidationError(
                f"Label local '{label.name}' colide com canon ativo. "
                f"Renomeie no overlay ou remova do canon (revisita)."
            )

    return CapabilityCatalog(
        canon=canon,
        local=local,
        active=canon.active | {l.name for l in local.added},
        reserved=canon.reserved,
    )
```

**Doc-sync:** `capability-labels.md` ganha seção curta "Local overlay" apontando regras (sem overrides, sem promoção). Detalhe profundo aqui, ponteiro lá — voz mentor calmo, sem duplicação.

## Seção 5 — Reconfigure UX

`forge reconfigure` ganha submenu novo `11) card-local` com 3 opções e fluxo de prompts mentor-calmo PT-BR.

### 5.1 Submenu

```
Reconfigure menu
  ...
  11) card-local — gerenciar cards locais do projeto
       1. Listar cards locais existentes
       2. Adicionar card local (criar do skeleton)
       3. Remover card local
       0. Voltar
  ...
```

### 5.2 Fluxo "adicionar do skeleton"

Prompts sequenciais, todos com validação inline:

```
Nome do card (kebab-case, sem espaços):
> hilt-di

Qual capability este card provê?
  Catálogo ativo: koin-di, retrofit-client, datastore-prefs, ...
  Reservadas (não-disponíveis aqui): hilt-di, apollo-graphql-client, ...
> di-framework

⚠️  'di-framework' não está no catálogo. Adicionar como label local?
  [s/N] s

Conflicts-with (lista cards canon/local separados por vírgula, vazio se nenhum):
> koin-di

Target platforms (android,ios,kmp,web — múltiplos separados por vírgula):
> android

—————————————————————————
Vou criar card local com:
  name:           hilt-di
  provides:       [di-framework]   (label local adicionada)
  conflicts-with: [koin-di]
  target:         [android]
  legacy-marker:  false

Três caminhos:
  1) Criar e abrir card.yaml pra preenchimento de signals
  2) Criar com signals.yaml vazio (preenchimento depois)
  3) Cancelar e voltar ao menu

Escolha [1-3]:
> 1
—————————————————————————

Card criado em .claude/cards/local/hilt-di/.
Abrindo card.yaml para edição de signals...
```

### 5.3 Skeleton minimal

O skeleton local espelha a estrutura canon, mas só materializa o que é **obrigatório no schema** (`card.yaml` + `README.md` são `Required files` em `docs/schemas/card.md`) mais o subdiretório `detection/` (porque signals são o coração do overlay — sem signal, card local nunca ativa):

```
.claude/cards/local/<name>/
├── card.yaml        (preenchido pelos prompts do reconfigure)
├── README.md        (skeleton placeholder explicando o card e linkando convenções do time)
└── detection/
    └── signals.yaml (vazio com comentário "preencher após init detection rodar e mapear sinais reais do projeto")
```

Os subdirs opcionais (`templates/`, `validators/`, `agent-contributions/`, `hooks/`, `examples/`) NÃO são criados como stubs vazios — viram dirs sob demanda quando o time efetivamente adiciona conteúdo. Esta decisão sustenta a tríade:

- **YAGNI** — templates e agent-contributions vazios são overhead se o card local cobre uma necessidade tática enquanto o time não tem capacidade de escrever templates novos. Stub vazio em `.gitkeep` polui árvore e induz commit ruidoso de "removeu .gitkeep, adicionou conteúdo".
- **Discovery** — `README.md` skeleton documenta os dirs opcionais por nome ("se quiser contribuir templates ao feature package, crie `templates/` aqui com fragmentos no padrão `docs/schemas/card.md`"). Discovery por linguagem, não por placeholder.
- **Reversibility** — remover card local cria `.bak` do diretório inteiro; minimal facilita reversão sem ter que reconciliar dirs vazios que ninguém usou.

### 5.4 Pós-criação

- `validate_card_yaml.py` roda no card recém-criado (catch malformação imediata).
- Warning explícito se `signals.yaml` ficou vazio: "Card criado sem signals — detection ignora até preencher".
- Atomic commit via `gsd-executor` se reconfigure foi dispatchado por orchestrator-mantenedor.
- Entrada em `.claude/state/history.jsonl` (audit padrão de reconfigure).

## Seção 6 — Init fail-safe 3-caminhos (Step 7.5)

Step novo entre detecção (Step 7) e materialização do plan (Step 8). Roda quando signals órfãos sobram após cascade de detection.

```python
# engine/init.py — adição

def _check_orphan_signals(ctx: InitContext) -> list[OrphanSignal]:
    """
    Após detection, lista signals que bateram em labels mas não em cards.

    Considera:
      - Catálogo efetivo (canon ∪ local overlay)
      - Reservadas (sinaliza edge-case especial)
    """
    ...


def _surface_three_paths(orphans: list[OrphanSignal], ctx: InitContext) -> InitDecision:
    """
    Apresenta 3-caminhos ao usuário em prompt mentor-calmo PT-BR.

    Edge case: se orphan aponta label reservada, caminho 1 muda de
    'criar card local agora' pra 'abrir ADR pra promoção ao canon'.
    """
    ...
```

**Template canônico do prompt** (transcrição literal, voz mentor calmo PT-BR):

```
🛑  Stack ambígua — signals sem card correspondente

Detectei sinais que apontam pra capabilities sem provider declarado:

  · Signal "import dagger.hilt.android.HiltAndroidApp" (3 ocorrências)
    → capability "di-framework" (label local? ausente no catálogo)
  · Signal "io.reactivex.rxjava3.core.Observable" (12 ocorrências)
    → capability "async-streams" (label local? ausente no catálogo)

Onde:
  Detection cascade rodou mas não encontrou card canon nem local
  pra estes signals.

Por que importa:
  Materializar o plan sem provider declarado deixa essas capabilities
  como "comportamento inventado" — viola o princípio "never invents"
  (`docs/design/00-vision.md §What feature-forge is NOT`) e quebra o
  contrato com validate_no_invented_behavior na Fase 5b.

Três caminhos pra resolver:

  1) Criar card local agora (recomendado pra stack atual)
     Chama reconfigure inline pra criar card(s) local(is) cobrindo
     os signals órfãos. Após criação, init reentra no Step 7
     (detection) com catálogo expandido.

  2) Ignorar nesta init (registra decisão consciente)
     Grava .claude/inventory/ignored-signals.yaml versionado listando
     os signals + razão. Validators downstream respeitam o ignore.
     Reversível: removendo a entrada, signals voltam a ser órfãos.

  3) Abortar init
     Exit code 8 (distinto de 5/7/130). Nenhum arquivo materializado.
     Use quando o time precisa decidir arquitetura antes de seguir.

Escolha [1-3]:
```

**Edge case — orphan em label reservada:**

```
... (mesmo cabeçalho) ...

  · Signal "import dagger.hilt.android.HiltAndroidApp" (3 ocorrências)
    → capability "hilt-di" (label RESERVADA no catálogo canon)

Por que importa:
  'hilt-di' é label reservada — está no roadmap do catálogo canon mas
  ainda sem card oficial. Local overlay não pode ativar reservada
  (promoção exige ADR).

Três caminhos pra resolver:

  1) Abrir ADR pra promoção ao canon (recomendado)
     Cria entrada em docs/design/01-decisions.md "Revisita roadmap
     do catálogo — promove hilt-di ao canon" e suspende init até
     PR de promoção rodar.

  2) Ignorar nesta init (registra decisão consciente)
     (idem caminho 2 acima)

  3) Abortar init
     (idem caminho 3 acima)
```

**Caminhos sem auto-fix.** Escolha é humana — 3-caminhos é gate (Discipline §1), não decision tree.

## Seção 7 — Validators

Mudanças cirúrgicas em dois validators existentes; nada novo standalone.

### 7.1 `validators/validate_card_yaml.py` — patches

- **Detecta canon vs local via path** (sem campo no YAML): `cards/<name>/card.yaml` → canon; `.claude/cards/local/<name>/card.yaml` → local. Loader tagga `card.origin` em memória (Seção 3); validator usa o path direto pra discriminar mensagens. Distinção não vive no conteúdo do YAML — vive no filesystem.
- **Cross-check de colisão de nome:** se mesmo `identity.name` existe em ambos paths (canon e local), hard fail apontando os dois paths concretos.
- **Cross-check `provides` ∉ reservadas** (já existia pra canon; passa a aplicar pra local também).
- **Novo campo `legacy-marker: bool` aceito** (top-level, opcional, default `false`). Validator passa-o intacto pro loader — é metadata pro init Step 7.5 calibrar 3-caminhos; validator não age sobre o valor.

### 7.2 `validators/validate_capability_labels.py` — patches

- **Parse `.claude/inventory/capability-labels.local.yaml`** se existir.
- **Catálogo efetivo = canon ∪ local** (chamada via `_common.load_catalog`).
- **Guards inline:**
  - Local label ∈ canon reservadas → fail "promoção exige ADR".
  - Local label ∈ canon active → fail "colisão de nome".
  - Local YAML com `overrides:` ou `reserved-promotions:` → fail "chaves não-permitidas".

### 7.3 Cascade order

`forge verify` ordena 14 validators; ordem atual intacta. Apenas validators 2 (`validate_card_yaml`) e 3 (`validate_capability_labels`) ficam overlay-aware. Demais consomem catálogo via `load_catalog`, então ganham overlay-awareness "de graça".

### 7.4 NÃO criado: `validate_local_overlay.py` standalone

Tentei propor inicialmente; reconheci como SRP-decoy. Lógica do overlay é atravessada por dois validators existentes (yaml + labels) — extrair pra um terceiro fragmenta sem benefício. Reuse antes de criar (mandamento #3).

### 7.5 Doc-sync downstream

`docs/design/07-discipline.md §2` (validator cascade) ganha nota curta: "validate_card_yaml e validate_capability_labels são overlay-aware desde v1.X — catálogo efetivo é canon ∪ local."

## Seção 8 — Tests + doc-sync

### 8.1 Tests novos (~25-30 testes, ~600 LOC)

| Arquivo | LOC | Cobre |
|---|---|---|
| `tests/unit/test_cards_loader_local.py` | ~150 | happy union / conflict canon×local / dir vazio / card.yaml malformado / origin tag correta |
| `tests/unit/test_validate_card_yaml_local.py` | ~120 | discriminação canon/local via path / `canonical=true` rejeitado em local / `provides` reservada rejeitado / colisão de nome / `legacy-marker` aceito |
| `tests/unit/test_validate_capability_labels_overlay.py` | ~100 | união canon ∪ local / promoção reservada rejeitada / colisão active rejeitada / overlay vazio (canon-only) / YAML malformado |
| `tests/unit/test_init_orphan_signals.py` | ~150 | caminho 1 (criar local + reentry) / caminho 2 (ignored-signals.yaml gravado) / caminho 3 (exit 8) / edge reservada (caminho 1 vira ADR) / reprompt em escolha inválida |
| `tests/unit/test_reconfigure_card_local.py` | ~80 | adicionar / listar / remover (com `.bak`) / colisão de nome em criação |
| `tests/integration/test_e2e_local_card_pilot.py` | ~200 | fluxo end-to-end Retrofit signal detectado → orphan → reconfigure inline → re-match → `forge verify` verde (marker `integration`) |

### 8.2 Tests modificados

- `tests/unit/test_cards_loader.py` — adapta pra cascade canon+local (manter casos canon-only verdes).
- `tests/unit/test_init_happy.py` — confirma que init sem orphans não dispara Step 7.5.

### 8.3 Baseline

367 (v1.1.0) → ~488-493 após Gap 5 (assumindo testes pré-existentes ao branch atual já em 463). Zero regressão tolerada — qualquer test que cai exige reproduzir local antes de mexer.

### 8.4 Doc-sync — matriz canônica

| Arquivo | O que muda |
|---|---|
| `CHANGELOG.md` | `### Added` — overlay mecanismo + 2 cards canon + Step 7.5 + capability-labels local |
| `docs/design/01-decisions.md` | ADR nova "Decisão N: Card local overlay (Approach A)" — append na tabela, sem deletar nada |
| `docs/design/04-pending.md` | risca Gap 5 (caminho oficial entregue); anota gaps parcialmente destravados (9, 14) |
| `docs/design/05-filesystem-layout.md` | adiciona `.claude/cards/local/`, `.claude/inventory/capability-labels.local.yaml`, `local-cards-manifest.yaml`, `ignored-signals.yaml` |
| `docs/design/07-discipline.md §2` | nota curta sobre validators overlay-aware |
| `docs/design/08-session-handoff.md` | Última atualização + Estado refletindo entrega |
| `docs/schemas/card.md` | seção "Where cards live" expandida (canon + local) + campo `legacy-marker` formalizado |
| `docs/schemas/capability-labels.md` | seção "Local overlay" curta + regras (sem overrides, sem promoção) |
| `README.md §Stats` | 20 cards canon → 22; menção breve ao overlay |

### 8.5 Smoke pós-impl

1. `bash .claude/bootstrap.sh` — idempotente, exit 0.
2. SMOKE-CHECKLIST.md 5/5 — confirma rules system ainda vivo.
3. `forge --version` — CLI vivo.
4. `forge verify` — cascade verde no próprio repo da forge.
5. `forge doctor` — health check 12 categorias verde.
6. `pytest` — full suite verde, count = baseline + ~25-30.

## Resumo

| Componente | LOC estimado |
|---|---|
| `cards/retrofit-client/` (card.yaml + README + detection/signals.yaml + templates/validators/agent-contributions stubs) | ~150-200 |
| `cards/shared-preferences-prefs/` (idem, com legacy-marker) | ~150-200 |
| Loader cascade (`engine/cards/loader.py` patches) | ~120 |
| Capability labels overlay (`validators/_common.py` + validator patches) | ~100 |
| Reconfigure submenu card-local | ~180 |
| Init Step 7.5 (orphan signals + 3-caminhos) | ~200 |
| Validator patches (`validate_card_yaml`, `validate_capability_labels`) | ~150 |
| Tests novos (~25-30 testes) | ~600 |
| Doc-sync (9 arquivos, agora incluindo schema bump de `legacy-marker` em card.md) | ~260 |
| **Total** | **~1910 LOC** |

Estimativa por card canon (~150-200 LOC) reflete a estrutura diretório-completo real: `card.yaml` completo (~80-100 LOC com comentários no padrão koin-annotations), `README.md` substantivo (~40-60 LOC), `detection/signals.yaml` (~20-30 LOC), stubs ou TODOs declarados para `templates/`, `validators/`, `agent-contributions/`. O delta vs estimativa anterior (+250 LOC totais) é honestidade arquitetural — single-file YAML era ficção do spec antigo.

**Princípios load-bearing preservados:**

- 27 decisions intactas; 1 ADR adicionada (Approach A do overlay).
- Discipline §1 (3-caminhos) aplicada no Step 7.5.
- Discipline §2 (fail-fast cascade) intacta — validators 2 e 3 viram overlay-aware sem mudar a ordem.
- Discipline §4 (`.bak` retention) aplicada na remoção de card local.
- Decision 9 (card.yaml fonte canônica), Decision 10 (snapshot copy), Decision 22 (no runtime deps) — todas preservadas.

**Gaps parcialmente destravados:**

- **Gap 9** (catálogo evolutivo): overlay dá caminho oficial pra times anteciparem labels que ainda não foram promovidas.
- **Gap 14** (preset coverage): preset canônico errado fica mitigável via card local enquanto preset novo não é shipado.

**Gaps independentes (não tocados por este design):**

- **Gap 6** (multi-dev mesma feature) — out-of-scope explícito.
- **Gap 16** (forge audit-rules) — anotado pra v1.2+.

## Próximos passos pós-spec

1. **User review do spec escrito** — checa fidelidade ao brainstorm + pontos não cobertos.
2. **Transição via `superpowers:writing-plans`** — produz plano executável task-by-task com critérios de sucesso testáveis.
3. **Implementação dispatcher-by-dispatcher** — orchestrator-mantenedor → `gsd-executor` por componente (cards canon → loader → validators → reconfigure → init Step 7.5 → tests → doc-sync).
4. **Verification + doc-sync no commit final** — `pytest` verde, `forge verify` verde, smoke checklist 5/5, matriz doc-sync §8.4 completa.
