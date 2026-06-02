# Gap 5 — Card Local Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar Gap 5 do `docs/design/04-pending.md` na forma híbrida aprovada — dois cards canon novos (`retrofit-client` + `shared-preferences-prefs`) somados ao mecanismo overlay completo (`.claude/cards/local/<name>/` versionado no projeto consumidor, com loader cascade canon ∪ local, validators overlay-aware, submenu novo em `forge reconfigure`, e Step 7.5 no init com 3-caminhos pra signals órfãos). Approach A (cascade simples, sem merge): conflito de nome canon×local é hard fail; local só adiciona.

**Architecture:** Schema canon ganha campo aditivo `legacy-marker: bool` (top-level, opcional). `engine/cards/loader.py` ganha cascade canon (snapshot) + local (live read em `.claude/cards/local/`) com `CardConflictError` e tag `card.origin`. `validators/_common.py` ganha `load_catalog(project_root)` unindo `capability-labels.yaml` (canon) + `capability-labels.local.yaml` (overlay). `engine/reconfigure.py` ganha opção 11 `card-local`. `engine/init.py` ganha Step 7.5 com 3-caminhos mentor-calmo PT-BR.

**Tech Stack:** Python 3.10+, PyYAML, pytest (markers: `integration`, `e2e`), schemas em `docs/schemas/*.md`, voz mentor calmo PT-BR conforme `docs/design/07-discipline.md §5`.

**Source spec:** `docs/superpowers/specs/2026-06-02-gap5-card-local-overlay-design.md`.

---

## File Structure

### Created (12 paths)

```
cards/retrofit-client/
├── card.yaml
├── README.md
├── detection/signals.yaml
├── templates/.gitkeep
├── validators/.gitkeep
└── agent-contributions/.gitkeep

cards/shared-preferences-prefs/
├── card.yaml
├── README.md
├── detection/signals.yaml
├── templates/.gitkeep
├── validators/.gitkeep
└── agent-contributions/.gitkeep

tests/unit/test_card_md_schema.py
tests/unit/test_cards_loader_local.py
tests/unit/test_validate_card_yaml_local.py
tests/unit/test_validate_capability_labels_overlay.py
tests/unit/test_init_orphan_signals.py
tests/unit/test_reconfigure_card_local.py
tests/integration/test_e2e_local_card_pilot.py
```

### Modified (8 arquivos código + 9 arquivos doc)

```
docs/schemas/card.md                   # +legacy-marker field
engine/cards/loader.py                 # cascade canon ∪ local + CardConflictError + origin tag + manifest writer
engine/init.py                         # Step 7.5 (orphan signals + 3-caminhos)
engine/reconfigure.py                  # opção 11 card-local submenu
validators/_common.py                  # load_catalog(project_root) helper
validators/validate_card_yaml.py       # canon/local discrimination + legacy-marker aceito
validators/validate_capability_labels.py  # overlay-aware via load_catalog
tests/unit/test_cards_loader.py        # adapta pra cascade (canon-only continua verde)

CHANGELOG.md
docs/design/01-decisions.md
docs/design/04-pending.md
docs/design/05-filesystem-layout.md
docs/design/07-discipline.md
docs/design/08-session-handoff.md
docs/schemas/capability-labels.md
README.md
```

### Responsibilities

- **Schema bump (`docs/schemas/card.md`)**: declara `legacy-marker: bool` top-level opcional + semântica disparo no init Step 7.5.
- **Cards canon novos**: `retrofit-client` provê `http-client`; `shared-preferences-prefs` provê `local-prefs-storage` legacy. Ambos seguem anatomia diretório-completa canônica.
- **Loader cascade** (`engine/cards/loader.py`): canon primeiro, local segundo. Hard fail em colisão. Tag `card.origin = "canon" | "local"` em memória.
- **Capability overlay** (`validators/_common.py` + `validate_capability_labels.py`): union canon + local; guards de reservada-promotion e canon-collision.
- **Validators overlay-aware** (`validate_card_yaml.py`): discrimina canon/local via path resolved; aceita `legacy-marker`.
- **Reconfigure submenu** (`engine/reconfigure.py`): opção 11 `card-local` — listar, adicionar (skeleton), remover (.bak retention).
- **Init Step 7.5** (`engine/init.py`): após detection, detecta signals órfãos e apresenta 3-caminhos (criar local / ignorar / abortar). Edge: orphan em label reservada vira "abrir ADR".

---

## Fase A — Schema foundations

## Task 1: Schema bump aditivo — `legacy-marker` em `docs/schemas/card.md`

**Files:**
- Modify: `docs/schemas/card.md`
- Create: `tests/unit/test_card_md_schema.py`
- Test: `tests/unit/test_card_md_schema.py::test_card_md_documents_legacy_marker`

- [ ] **Step 1: Run target test, confirm fails**

```bash
pytest "tests/unit/test_card_md_schema.py::test_card_md_documents_legacy_marker" -v
```

Expected: ERROR (test file ainda não existe).

- [ ] **Step 2: Append `legacy-marker` ao schema annotated em `docs/schemas/card.md`**

Edit `docs/schemas/card.md`. Encontre o bloco `# ── CAPABILITIES ────...` no schema annotated (linha 115 hoje, logo após o fechamento do bloco `identity:` que termina com `license: MIT`). Insira ANTES de `# ── CAPABILITIES ────` o novo bloco:

```yaml
# ── LEGACY MARKER ─────────────────────────────────────────────────────────
# Campo top-level opcional, aditivo ao schema v1 (não bumpa schema-version).
# Quando true, sinaliza ao init Step 7.5 que este card provê uma capability
# em forma legacy — caso 2+ cards proveem a mesma label e ao menos um tem
# legacy-marker: true, o init dispara prompt 3-caminhos (manter legacy /
# migrar pro moderno / coexistir explicitamente) antes de materializar o plan.
# Default ausente = false.
legacy-marker: false
```

E adicione um parágrafo em prosa logo após a seção `## Card anatomy` (antes de `## The card.yaml schema (full annotated)`), seção nova:

```markdown
## Optional top-level `legacy-marker` (since v1.1)

`legacy-marker: bool` é campo opcional top-level (default `false`) que sinaliza
ao init que este card provê uma capability em forma legacy. Quando 2+ cards
ativos proveem a mesma capability label e ao menos um carrega
`legacy-marker: true`, init Step 7.5 surfaca prompt 3-caminhos antes de
materializar o plan (manter legacy / migrar / coexistir).

Política de versionamento: adição é aditiva, `schema-version` permanece `1`.
Cards existentes (todos os 20 v1.1) seguem válidos sem mexer. Promoção a
schema-version 2 só acontece em mudança breaking (remoção, mudança de tipo,
novo required field).

Validator (`validate_card_yaml.py`) aceita o campo intacto — quem age sobre
o valor é o init Step 7.5.
```

- [ ] **Step 3: Write the smoke test (full content)**

Create `tests/unit/test_card_md_schema.py`:

```python
"""Smoke tests — docs/schemas/card.md schema annotated.

Garante que o markdown declara o campo aditivo `legacy-marker` introduzido
pela entrega do Gap 5 (Card local overlay). Nenhum runtime check de YAML
real — apenas verifica que o doc lista o campo e a seção de política.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CARD_MD = REPO_ROOT / "docs" / "schemas" / "card.md"


def test_card_md_exists():
    assert CARD_MD.is_file(), f"expected {CARD_MD} to exist"


def test_card_md_documents_legacy_marker():
    text = CARD_MD.read_text(encoding="utf-8")
    # Bloco no schema annotated
    assert "legacy-marker: false" in text, (
        "schema annotated deve incluir o campo `legacy-marker: false` "
        "(default declarado)"
    )
    # Seção de política aditiva
    assert "Optional top-level `legacy-marker`" in text, (
        "doc deve carregar a seção explicativa do campo"
    )
    # Garante que política de schema-version é mencionada
    assert "schema-version` permanece `1`" in text or "schema-version permanece 1" in text


def test_card_md_section_order_preserved():
    """legacy-marker section vem ANTES do schema annotated, não dentro dele."""
    text = CARD_MD.read_text(encoding="utf-8")
    idx_section = text.find("## Optional top-level `legacy-marker`")
    idx_schema = text.find("## The `card.yaml` schema (full annotated)")
    assert idx_section != -1 and idx_schema != -1
    assert idx_section < idx_schema, (
        "seção `legacy-marker` deve ficar ANTES de `## The card.yaml schema`"
    )
```

- [ ] **Step 4: Run target test, confirm passes**

```bash
pytest tests/unit/test_card_md_schema.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add docs/schemas/card.md tests/unit/test_card_md_schema.py
git commit -m "feat(schema): add legacy-marker field to card.yaml schema"
```

---

## Task 2: Create `cards/retrofit-client/` canon card (full dir)

**Files:**
- Create: `cards/retrofit-client/card.yaml`
- Create: `cards/retrofit-client/README.md`
- Create: `cards/retrofit-client/detection/signals.yaml`
- Create: `cards/retrofit-client/templates/.gitkeep`
- Create: `cards/retrofit-client/validators/.gitkeep`
- Create: `cards/retrofit-client/agent-contributions/.gitkeep`
- Test: rodar `validators/validate_card_yaml.py --card retrofit-client`

- [ ] **Step 1: Confirma estado atual (card ainda não existe)**

```bash
ls cards/retrofit-client/ 2>&1 | head -3
```

Expected: `No such file or directory` ou similar.

- [ ] **Step 2: Create `cards/retrofit-client/card.yaml` (full content)**

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
# kotlinx-serialization-json é converter moderno padrão. Quando o projeto usa
# Moshi/Gson, esses signals derivados ficam pra implementação parametrizar
# via config-defaults.
requires:
  - kotlin
  - serialization-json


# ── CONFLICTS ─────────────────────────────────────────────────────────────
conflicts-with:
  - ktor-client


# ── CONTRIBUTIONS ─────────────────────────────────────────────────────────
# Stubs declarados — templates/validators/agent-prompts concretos shipam
# dispatch-by-dispatch em plano futuro. Stub aqui evita poluir o YAML com
# entradas vazias.
contributes:
  config-defaults:
    conventions.network.http-client: "retrofit"
    conventions.network.converter:   "kotlinx-serialization"


# ── DETECTION ─────────────────────────────────────────────────────────────
# Android-only é derivado: signals batem em build.gradle Android e em
# .kt com imports retrofit2. Sem campo target-platforms.
detection:
  signals:
    - type:       file-content
      glob:       "**/build.gradle*"
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

- [ ] **Step 3: Create `cards/retrofit-client/README.md` (full content)**

```markdown
# retrofit-client

Provider canônico de `http-client` baseado em Retrofit2 (`com.squareup.retrofit2`).
Cobre projetos Android-only e o lado Android de KMP quando Ktor multiplatform
não é a escolha — Android-only é semântica derivada dos signals, não campo
declarativo.

## Quando usar este card

- Projeto Android-only com REST API tradicional
- Projeto KMP onde Android usa Retrofit e iOS usa Ktor/URLSession por outro card
- Migration in-flight saindo de OkHttp puro → Retrofit + converter

## Quando NÃO usar

- Projeto KMP que escolheu Ktor multiplatform como cliente único — ative
  `ktor-client` (declarado em `conflicts-with` deste card).
- iOS-only sem lado Android.

## Convenções herdadas

- `conventions.network.http-client: retrofit`
- `conventions.network.converter: kotlinx-serialization`

Override via `forge reconfigure → conventions` quando o projeto usa Moshi/Gson.

## Detection

Card ativa quando confidence cumulativa ≥ 0.6 sobre os 3 signals declarados
em `detection/signals.yaml`. Threshold canônico — sem desvio do default v1.1.
```

- [ ] **Step 4: Create `cards/retrofit-client/detection/signals.yaml` (full content)**

```yaml
# cards/retrofit-client/detection/signals.yaml
# ──────────────────────────────────────────────────────────────────────────
# Sinais de detecção do card retrofit-client.
#
# Os signals aqui espelham `card.yaml > detection.signals` adicionando `id`
# + `rationale` por signal (campos não suportados no card.yaml — ficam aqui
# como audit trail pra evolução).
# ──────────────────────────────────────────────────────────────────────────

schema-version: 1

signals:
  - id:         retrofit-gradle-dep
    type:       file-content
    glob:       "**/build.gradle*"
    contains:   "com.squareup.retrofit2:retrofit"
    confidence: 0.5
    rationale:  "Dependência declarada em build.gradle(.kts) é evidência forte de uso ativo."

  - id:         retrofit-http-annotation
    type:       file-content
    glob:       "**/*.kt"
    contains:   "@retrofit2.http"
    confidence: 0.3
    rationale:  "Anotações @GET/@POST/@PUT/@DELETE qualificadas com namespace retrofit2.http."

  - id:         retrofit-import
    type:       file-content
    glob:       "**/*.kt"
    contains:   "import retrofit2"
    confidence: 0.2
    rationale:  "Import direto de qualquer membro de retrofit2 — confidence menor (legado pode ter import só no DTO)."

threshold: 0.6

alternative-cards:
  - ktor-client
```

- [ ] **Step 5: Create `.gitkeep` files nos subdirs opcionais**

```bash
mkdir -p cards/retrofit-client/templates cards/retrofit-client/validators cards/retrofit-client/agent-contributions
touch cards/retrofit-client/templates/.gitkeep
touch cards/retrofit-client/validators/.gitkeep
touch cards/retrofit-client/agent-contributions/.gitkeep
```

- [ ] **Step 6: Smoke-validate o card recém-criado**

```bash
python validators/validate_card_yaml.py --project-root . --card retrofit-client
```

Expected: stdout `PASS` ou exit 0. Se falhar com CARD-004 (category fora do conjunto): confira que `network` está em `_KNOWN_CATEGORIES` em `engine/cards/loader.py` (linha 38, já presente). Se falhar com CARD-006/007 sobre labels (`http-client`, `serialization-json`, `kotlin`): confirma que estão em `docs/schemas/capability-labels.md`.

- [ ] **Step 7: Commit**

```bash
git add cards/retrofit-client/
git commit -m "feat(cards): add canon card retrofit-client (http-client provider)"
```

---

## Task 3: Create `cards/shared-preferences-prefs/` canon card (full dir)

**Files:**
- Create: `cards/shared-preferences-prefs/card.yaml`
- Create: `cards/shared-preferences-prefs/README.md`
- Create: `cards/shared-preferences-prefs/detection/signals.yaml`
- Create: `cards/shared-preferences-prefs/templates/.gitkeep`
- Create: `cards/shared-preferences-prefs/validators/.gitkeep`
- Create: `cards/shared-preferences-prefs/agent-contributions/.gitkeep`

- [ ] **Step 1: Create `cards/shared-preferences-prefs/card.yaml` (full content)**

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
  category:     persistence
  maturity:     stable
  maintainer:   feature-forge-core
  created-at:   2026-06-02
  last-updated: 2026-06-02
  license:      MIT


# ── LEGACY MARKER ─────────────────────────────────────────────────────────
# Campo top-level opcional, aditivo ao schema canon (Task 1).
legacy-marker: true


# ── CAPABILITIES ──────────────────────────────────────────────────────────
provides:
  - local-prefs-storage


# ── DEPENDENCIES ──────────────────────────────────────────────────────────
requires:
  - kotlin


# ── CONFLICTS ─────────────────────────────────────────────────────────────
# Coexistência é permitida (label auxiliar) mas init surfaca 3-caminhos
# quando ambos detectados — comportamento dirigido por legacy-marker, não
# por conflict hard.
conflicts-with:
  - datastore-prefs


# ── CONTRIBUTIONS ─────────────────────────────────────────────────────────
contributes:
  config-defaults:
    conventions.persistence.prefs:       "shared-preferences"
    conventions.persistence.prefs-scope: "legacy KV — pre-DataStore feature toggles, last-shown markers"


# ── DETECTION ─────────────────────────────────────────────────────────────
# Confidence por signal calibrada ligeiramente menor que datastore-prefs
# equivalente — reflete que evidência de SharedPreferences em codebase
# moderno é tipicamente legacy detectado, não escolha ativa. Threshold
# canônico 0.6.
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

- [ ] **Step 2: Create `cards/shared-preferences-prefs/README.md` (full content)**

```markdown
# shared-preferences-prefs

Provider **legacy** de `local-prefs-storage` baseado em `android.content.SharedPreferences`.
Coexiste com `datastore-prefs` (provider canônico moderno) — mas init
Step 7.5 surfaca 3-caminhos quando ambos detectados, porque este card
carrega `legacy-marker: true`.

## Status legacy

`legacy-marker: true` significa que detection deste card por si só não é
sinal de escolha arquitetural ativa — é evidência de código pré-existente.
Recomendação para projetos novos: ative `datastore-prefs` em vez deste.
Para projetos com base instalada, este card existe para destravar `forge
init` sem mentir sobre a stack atual.

## Quando este card aparece sem o moderno

Stack é majoritariamente legacy. Caminho recomendado:

1. Aceitar o card no init (`forge init` opção "manter legacy").
2. Abrir tarefa de migração separada — feature-forge não força migração.
3. Quando migrar, rodar `forge reconfigure → remover card` (.bak retention
   7d preserva o snapshot).

## Quando coexiste com `datastore-prefs`

Init Step 7.5 surfaca:

```
Detectei dois providers de local-prefs-storage:
  · shared-preferences-prefs  (legacy)
  · datastore-prefs           (moderno)

Três caminhos:
  1) Manter ambos (transição in-flight, código novo usa DataStore)
  2) Migrar tudo pra DataStore (gera nota em TODO.md)
  3) Manter só SharedPreferences (assume escolha consciente)
```

Sem auto-fix — escolha humana.

## Detection

Threshold canônico 0.6, igual aos demais cards v1.1. Confidence individual
por signal calibrada ligeiramente menor que `datastore-prefs` equivalente —
reflete que evidência de SharedPreferences em codebase moderno é
tipicamente legacy, não escolha ativa.
```

- [ ] **Step 3: Create `cards/shared-preferences-prefs/detection/signals.yaml` (full content)**

```yaml
# cards/shared-preferences-prefs/detection/signals.yaml
# ──────────────────────────────────────────────────────────────────────────
# Sinais de detecção do card shared-preferences-prefs (LEGACY provider de
# local-prefs-storage). Confidence individual calibrada ligeiramente menor
# que datastore-prefs equivalente — vide README.md §Detection.
# ──────────────────────────────────────────────────────────────────────────

schema-version: 1

signals:
  - id:         shared-prefs-runtime-getter
    type:       file-content
    glob:       "**/*.kt"
    contains:   "getSharedPreferences("
    confidence: 0.4
    rationale:  "Chamada direta a Context.getSharedPreferences — evidência runtime forte."

  - id:         shared-prefs-default-manager
    type:       file-content
    glob:       "**/*.kt"
    contains:   "PreferenceManager.getDefaultSharedPreferences"
    confidence: 0.3
    rationale:  "API legacy de PreferenceManager — confirma uso ativo mesmo em código mais antigo."

  - id:         shared-prefs-import
    type:       file-content
    glob:       "**/*.kt"
    contains:   "import android.content.SharedPreferences"
    confidence: 0.2
    rationale:  "Import direto — confidence menor pois pode ser tipo declarado em interface sem uso runtime ativo."

threshold: 0.6

alternative-cards:
  - datastore-prefs
```

- [ ] **Step 4: Create `.gitkeep` files**

```bash
mkdir -p cards/shared-preferences-prefs/templates cards/shared-preferences-prefs/validators cards/shared-preferences-prefs/agent-contributions
touch cards/shared-preferences-prefs/templates/.gitkeep
touch cards/shared-preferences-prefs/validators/.gitkeep
touch cards/shared-preferences-prefs/agent-contributions/.gitkeep
```

- [ ] **Step 5: Smoke-validate**

```bash
python validators/validate_card_yaml.py --project-root . --card shared-preferences-prefs
```

Expected: PASS. Como `legacy-marker: true` ainda não é aceito pelo validator (Task 7), o validator pode aceitar silenciosamente (campo desconhecido top-level — loader passa intacto via `data.get("legacy-marker")` que retorna None se ausente; presença não dispara violation). Se falhar com CARD-013-WARN sobre extension-points: ignora warning, hard fail é o que importa.

- [ ] **Step 6: Commit**

```bash
git add cards/shared-preferences-prefs/
git commit -m "feat(cards): add canon card shared-preferences-prefs (legacy local-prefs-storage provider)"
```

---

## Fase B — Loader cascade

## Task 4: Loader cascade canon + local em `engine/cards/loader.py`

**Files:**
- Modify: `engine/cards/loader.py` (assinatura `load_all_cards` muda + nova exception + helpers privados)
- Modify: `engine/cards/__init__.py` (exportar `CardConflictError`)
- Create: `tests/unit/test_cards_loader_local.py`
- Test: `tests/unit/test_cards_loader_local.py` (5 testes)

- [ ] **Step 1: Run target tests, confirm fail**

```bash
pytest tests/unit/test_cards_loader_local.py -v
```

Expected: ERROR (test file ainda não existe). Esta task escreve o test PRIMEIRO (TDD) — mas a implementação vai junto no mesmo commit porque a interface (`load_all_cards(project_root)`) muda e quebra `test_cards_loader.py` se sair sem patch coordenado.

- [ ] **Step 2: Adicionar `CardConflictError` em `engine/cards/__init__.py`**

Edit `engine/cards/__init__.py`. Adicione após a declaração existente de `CardError`:

```python
class CardConflictError(CardError):
    """Raised when a canon card name collides with a local overlay card name.

    Approach A (cascade simples): conflito é hard fail. Resolução exige
    renomear o card local ou abrir ADR para promoção ao canon. NÃO há
    merge silencioso, NÃO há override.
    """
```

- [ ] **Step 3: Patch `engine/cards/loader.py` — adicionar field `origin` ao `CardManifest`**

Edit a definição do dataclass `CardManifest` (linha ~269) — adicione o novo field logo após `source_path`:

```python
@dataclass
class CardManifest:
    """Parsed `card.yaml` plus the source directory for relative file lookup."""

    name: str
    version: str
    schema_version: int
    description: str
    category: str
    maturity: str
    provides: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)
    conflicts_with: list[str] = field(default_factory=list)
    contributes: dict[str, Any] = field(default_factory=dict)
    detection: dict[str, Any] = field(default_factory=dict)
    config_defaults: dict[str, Any] = field(default_factory=dict)
    documentation: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
    source_path: Path = field(default_factory=lambda: Path("."))
    legacy_marker: bool = False
    origin: str = "canon"  # "canon" | "local" — set by load_all_cards cascade
```

- [ ] **Step 4: Patch `load_card` para parsear `legacy-marker`**

Edit `load_card` (linha ~297). No `return CardManifest(...)`, adicione o argumento:

```python
    return CardManifest(
        name=str(identity.get("name", "")),
        version=str(identity.get("version", "")),
        schema_version=int(data.get("schema-version", 1)),
        description=str(identity.get("description", "")),
        category=str(identity.get("category", "")),
        maturity=str(identity.get("maturity", "")),
        provides=list(data.get("provides") or []),
        requires=list(data.get("requires") or []),
        conflicts_with=list(data.get("conflicts-with") or []),
        contributes=dict(contributes),
        detection=dict(data.get("detection") or {}),
        config_defaults=dict(contributes.get("config-defaults") or {}),
        documentation=dict(data.get("documentation") or {}),
        raw=data,
        source_path=card_dir,
        legacy_marker=bool(data.get("legacy-marker", False)),
        origin="canon",  # default; load_all_cards reassigns based on cascade
    )
```

- [ ] **Step 5: Substituir `load_all_cards` por cascade canon ∪ local**

Edit `engine/cards/loader.py`. Remove a função `load_all_cards` atual (linha ~341-359) e substitui pelo novo bloco:

```python
def load_all_cards(cards_root: Path) -> list[CardManifest]:
    """Load every card under `cards_root/<name>/card.yaml`.

    Backward-compatible shape: when caller passes the canonical cards/ root
    directly (no `.claude/cards/local/` sibling), returns canon-only. When
    caller passes a project root that has `.claude/cards/local/`, returns
    canon ∪ local with `card.origin` tagged.

    Argument semantics (autodetect):
      - If `cards_root` itself contains `<name>/card.yaml` entries, treat it
        as a canon-only root (legacy callers: snapshot dir, canonical dir).
      - If `cards_root` looks like a project root (contains `.claude/`),
        treat it as cascade-mode: canon snapshot under
        `cards_root/.claude/cards/<name>/` + local under
        `cards_root/.claude/cards/local/<name>/`.

    Raises:
      CardConflictError: when a name appears in both canon and local layers.

    Side-effects (cascade mode only):
      Writes `<project>/.claude/inventory/local-cards-manifest.yaml`
      listing local card names + provides + conflicts-with for CI audit.
    """
    if not cards_root.is_dir():
        raise CardError(f"cards root not found: {cards_root}")

    # Autodetect: if `.claude/` exists at cards_root, treat as project-root cascade.
    project_marker = cards_root / ".claude"
    if project_marker.is_dir() and not (cards_root / "card.yaml").exists():
        return _load_with_cascade(cards_root)

    # Legacy canon-only path: cards_root holds <name>/card.yaml siblings.
    manifests: list[CardManifest] = []
    for entry in sorted(cards_root.iterdir(), key=lambda p: p.name):
        if not entry.is_dir():
            continue
        if entry.name.startswith("."):
            continue
        if not (entry / "card.yaml").is_file():
            continue
        manifest = load_card(entry)
        manifest.origin = "canon"
        manifests.append(manifest)
    return manifests


def _load_with_cascade(project_root: Path) -> list[CardManifest]:
    """Cascade load: canon snapshot first, local overlay second.

    Order is deliberate — canon is the audited set, local is the controlled
    extension. Inverting order would permit silent override (violates
    Approach A from spec).
    """
    canon_root = project_root / ".claude" / "cards"
    local_root = project_root / ".claude" / "cards" / "local"

    canon: dict[str, CardManifest] = {}
    if canon_root.is_dir():
        for entry in sorted(canon_root.iterdir(), key=lambda p: p.name):
            if not entry.is_dir():
                continue
            if entry.name.startswith("."):
                continue  # skips `.archived/`, `.git/`, etc.
            if entry.name == "local":
                continue  # the overlay dir is handled below, not a canon card
            if not (entry / "card.yaml").is_file():
                continue
            manifest = load_card(entry)
            manifest.origin = "canon"
            canon[manifest.name] = manifest

    local: dict[str, CardManifest] = {}
    if local_root.is_dir():
        for entry in sorted(local_root.iterdir(), key=lambda p: p.name):
            if not entry.is_dir():
                continue
            if entry.name.startswith("."):
                continue
            if not (entry / "card.yaml").is_file():
                # Empty local card dir: warning skip. Caller (forge doctor)
                # can surface; loader stays quiet to keep snapshot loadable.
                continue
            manifest = load_card(entry)
            manifest.origin = "local"
            local[manifest.name] = manifest

    # Hard fail on name collision — Approach A.
    conflicts = sorted(set(canon) & set(local))
    if conflicts:
        raise CardConflictError(
            f"Nomes em colisão canon×local: {conflicts}. "
            f"Renomeie o card local ou abra ADR pra promoção ao canon."
        )

    # Manifest write side-effect (cascade mode only).
    _write_local_cards_manifest(project_root, local)

    return [canon[name] for name in sorted(canon)] + [
        local[name] for name in sorted(local)
    ]
```

- [ ] **Step 6: Adicionar `_write_local_cards_manifest` (stub, real impl em Task 5)**

Adicione na seção `# ── Private helpers ─────────────────────────────...` no final do arquivo:

```python
def _write_local_cards_manifest(
    project_root: Path, local: dict[str, "CardManifest"]
) -> None:
    """Write `.claude/inventory/local-cards-manifest.yaml` for CI audit.

    Stub in Task 4 — fully implemented in Task 5. Stub no-op when local is
    empty (canon-only project = no manifest needed).
    """
    if not local:
        return
    # Task 5 expands this to write the YAML. Leave as no-op here.
    return
```

- [ ] **Step 7: Importe `CardConflictError` no topo do loader**

No topo de `engine/cards/loader.py`, ajuste a linha existente:

```python
from . import CardError, CardConflictError
```

- [ ] **Step 8: Adapt `tests/unit/test_cards_loader.py` — cascade-mode skip pra canon-only callers**

O test atual passa `forge_home / "cards" / "kmp-shared"` (uma única pasta de card, não cards root). Esse caso continua funcionando porque autodetect olha pra `.claude/` no cards_root — pasta única não tem. Test `test_load_all_cards_skips_hidden_dirs` passa `tmp_path` que também não tem `.claude/` — canon-only path roda. **Nenhuma edição necessária em `test_cards_loader.py`** se autodetect funciona; rode o suite pra confirmar:

```bash
pytest tests/unit/test_cards_loader.py -v
```

Expected: 11 passed (mesmo count anterior).

- [ ] **Step 9: Write `tests/unit/test_cards_loader_local.py` (full content)**

Create `tests/unit/test_cards_loader_local.py`:

```python
"""Unit tests — loader cascade canon ∪ local overlay.

Cobre:
  - happy union (canon + local lidos juntos)
  - conflito canon×local (CardConflictError hard fail)
  - dir local inexistente (silent canon-only)
  - dir local vazio (warning skip — não levanta)
  - card.yaml local malformado (ValidationError com path)
  - origin tag (canon=canon, local=local)
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from engine.cards import CardError, CardConflictError, loader


def _valid_card_dict(name: str = "demo-card", provides: list[str] | None = None) -> dict:
    return {
        "schema-version": 1,
        "identity": {
            "name": name,
            "version": "1.0.0",
            "description": "Demo card",
            "category": "kmp",
            "maturity": "stable",
        },
        "provides": provides or ["kotlin-multiplatform"],
        "requires": [],
        "conflicts-with": [],
    }


def _write_card_dir(card_dir: Path, data: dict) -> None:
    card_dir.mkdir(parents=True, exist_ok=True)
    (card_dir / "card.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )
    (card_dir / "README.md").write_text("# test\n", encoding="utf-8")


def _make_project(tmp_path: Path) -> Path:
    """Build a fake project root with `.claude/cards/` ready for cascade."""
    project = tmp_path / "fake-project"
    (project / ".claude" / "cards").mkdir(parents=True)
    return project


# ── Happy union ─────────────────────────────────────────────────────────────


def test_cascade_returns_canon_only_when_local_absent(tmp_path):
    project = _make_project(tmp_path)
    _write_card_dir(project / ".claude" / "cards" / "canon-a", _valid_card_dict("canon-a"))
    manifests = loader.load_all_cards(project)
    assert [m.name for m in manifests] == ["canon-a"]
    assert manifests[0].origin == "canon"


def test_cascade_unions_canon_and_local(tmp_path):
    project = _make_project(tmp_path)
    _write_card_dir(project / ".claude" / "cards" / "canon-a", _valid_card_dict("canon-a"))
    _write_card_dir(
        project / ".claude" / "cards" / "local" / "team-b",
        _valid_card_dict("team-b", provides=["kotlin-multiplatform"]),
    )
    manifests = loader.load_all_cards(project)
    names_and_origins = {(m.name, m.origin) for m in manifests}
    assert ("canon-a", "canon") in names_and_origins
    assert ("team-b", "local") in names_and_origins


# ── Conflict ────────────────────────────────────────────────────────────────


def test_cascade_hard_fails_on_canon_local_name_collision(tmp_path):
    project = _make_project(tmp_path)
    _write_card_dir(project / ".claude" / "cards" / "collide", _valid_card_dict("collide"))
    _write_card_dir(
        project / ".claude" / "cards" / "local" / "collide",
        _valid_card_dict("collide"),
    )
    with pytest.raises(CardConflictError) as exc:
        loader.load_all_cards(project)
    assert "colisão canon×local" in str(exc.value)
    assert "collide" in str(exc.value)


# ── Edge cases ──────────────────────────────────────────────────────────────


def test_cascade_silent_when_local_root_missing(tmp_path):
    """`.claude/cards/local/` ausente é canon-only, sem warning."""
    project = _make_project(tmp_path)
    _write_card_dir(project / ".claude" / "cards" / "canon-only", _valid_card_dict("canon-only"))
    # nota: local/ NÃO é criado
    manifests = loader.load_all_cards(project)
    assert [m.name for m in manifests] == ["canon-only"]


def test_cascade_skips_empty_local_dir(tmp_path):
    """Dir `local/<name>/` existe sem card.yaml → skip silencioso."""
    project = _make_project(tmp_path)
    _write_card_dir(project / ".claude" / "cards" / "canon-a", _valid_card_dict("canon-a"))
    empty_local = project / ".claude" / "cards" / "local" / "no-card"
    empty_local.mkdir(parents=True)
    # nenhum card.yaml dentro
    manifests = loader.load_all_cards(project)
    assert [m.name for m in manifests] == ["canon-a"]


def test_cascade_raises_on_malformed_local_card_yaml(tmp_path):
    project = _make_project(tmp_path)
    bad_dir = project / ".claude" / "cards" / "local" / "bad"
    bad_dir.mkdir(parents=True)
    (bad_dir / "card.yaml").write_text(
        "not: a: valid: yaml: shape: at: all", encoding="utf-8"
    )
    (bad_dir / "README.md").write_text("# bad\n", encoding="utf-8")
    with pytest.raises(CardError):
        loader.load_all_cards(project)


# ── Backward compatibility ──────────────────────────────────────────────────


def test_legacy_canon_only_root_still_works(tmp_path):
    """`load_all_cards(canon_root)` passada uma pasta sem `.claude/` permanece canon-only."""
    canon_root = tmp_path / "canon"
    canon_root.mkdir()
    _write_card_dir(canon_root / "demo", _valid_card_dict("demo"))
    manifests = loader.load_all_cards(canon_root)
    assert [m.name for m in manifests] == ["demo"]
    assert manifests[0].origin == "canon"
```

- [ ] **Step 10: Run new tests, confirm pass**

```bash
pytest tests/unit/test_cards_loader_local.py tests/unit/test_cards_loader.py -v
```

Expected: all green. Se `test_cascade_raises_on_malformed_local_card_yaml` falhar com `CardError` em vez de subclasse específica: OK — `CardConflictError` herda de `CardError`, e malformação levanta `CardError` raw, então o test pega ambos.

- [ ] **Step 11: Commit**

```bash
git add engine/cards/loader.py engine/cards/__init__.py tests/unit/test_cards_loader_local.py
git commit -m "feat(loader): cards/local overlay cascade with hard-fail on name collision"
```

---

## Task 5: `card.origin` tag + `local-cards-manifest.yaml` writer

**Files:**
- Modify: `engine/cards/loader.py` (preenche o stub `_write_local_cards_manifest`)
- Modify: `tests/unit/test_cards_loader_local.py` (adiciona 2 testes)

- [ ] **Step 1: Run target tests, confirm fail (vão ser adicionados primeiro como red)**

Vamos escrever 2 testes novos PRIMEIRO. Edit `tests/unit/test_cards_loader_local.py` e adicione no FINAL do arquivo:

```python
# ── Local-cards manifest writer ─────────────────────────────────────────────


def test_cascade_writes_local_cards_manifest_when_local_present(tmp_path):
    project = _make_project(tmp_path)
    inv_dir = project / ".claude" / "inventory"
    inv_dir.mkdir(parents=True, exist_ok=True)

    _write_card_dir(project / ".claude" / "cards" / "canon-a", _valid_card_dict("canon-a"))
    _write_card_dir(
        project / ".claude" / "cards" / "local" / "team-x",
        _valid_card_dict("team-x", provides=["kotlin-multiplatform"]),
    )

    loader.load_all_cards(project)

    manifest_path = inv_dir / "local-cards-manifest.yaml"
    assert manifest_path.is_file(), "manifest deve ser escrito quando há cards locais"
    parsed = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    assert parsed.get("schema-version") == 1
    cards_block = parsed.get("local-cards") or []
    names = {c.get("name") for c in cards_block}
    assert names == {"team-x"}
    # provides + conflicts-with devem ser preservados pro audit
    team_x = next(c for c in cards_block if c.get("name") == "team-x")
    assert team_x.get("provides") == ["kotlin-multiplatform"]


def test_cascade_skips_manifest_when_no_local(tmp_path):
    project = _make_project(tmp_path)
    inv_dir = project / ".claude" / "inventory"
    inv_dir.mkdir(parents=True, exist_ok=True)
    _write_card_dir(project / ".claude" / "cards" / "canon-only", _valid_card_dict("canon-only"))

    loader.load_all_cards(project)

    manifest_path = inv_dir / "local-cards-manifest.yaml"
    assert not manifest_path.exists(), "no-op manifest quando nenhum local card"
```

Rode:

```bash
pytest tests/unit/test_cards_loader_local.py::test_cascade_writes_local_cards_manifest_when_local_present -v
```

Expected: FAIL (writer ainda é stub).

- [ ] **Step 2: Implementar `_write_local_cards_manifest` completo em `engine/cards/loader.py`**

Substitua o stub criado na Task 4 pelo bloco completo:

```python
def _write_local_cards_manifest(
    project_root: Path, local: dict[str, "CardManifest"]
) -> None:
    """Write `.claude/inventory/local-cards-manifest.yaml` listing local cards.

    Side-effect deterministic — quando `local` é vazio (canon-only project),
    no-op e NÃO cria o arquivo (evita ruído em projetos que nunca tocaram
    overlay). Quando há cards locais, escreve YAML versionado contendo:
      - schema-version: 1
      - generated-by: feature-forge
      - local-cards: [{name, provides, conflicts-with, source}]

    Diretório `.claude/inventory/` é criado se ausente — chamada idempotente.
    O arquivo é versionado pelo time (não está em .gitignore do projeto
    consumidor) — usado por CI pra auditar quais cards locais entraram.
    """
    if not local:
        return

    inv_dir = project_root / ".claude" / "inventory"
    inv_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = inv_dir / "local-cards-manifest.yaml"

    entries: list[dict[str, Any]] = []
    for name in sorted(local):
        card = local[name]
        entries.append(
            {
                "name": card.name,
                "provides": list(card.provides),
                "conflicts-with": list(card.conflicts_with),
                "source": str(card.source_path.relative_to(project_root)),
            }
        )

    payload = {
        "schema-version": 1,
        "generated-by": "feature-forge engine.cards.loader",
        "local-cards": entries,
    }
    manifest_path.write_text(
        _yaml_lib.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
```

- [ ] **Step 3: Run targeted tests, confirm pass**

```bash
pytest tests/unit/test_cards_loader_local.py -v
```

Expected: 9 passed (7 da Task 4 + 2 novos).

- [ ] **Step 4: Run full loader suite pra garantir zero regressão**

```bash
pytest tests/unit/test_cards_loader.py tests/unit/test_cards_loader_local.py -v
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add engine/cards/loader.py tests/unit/test_cards_loader_local.py
git commit -m "feat(loader): tag card.origin + write local-cards-manifest.yaml"
```

---

## Fase C — Capability labels overlay

## Task 6: `capability-labels.local.yaml` parse + validator guards

**Files:**
- Modify: `validators/_common.py` (adiciona `load_catalog(project_root)`)
- Modify: `validators/validate_capability_labels.py` (usa `load_catalog` + guards)
- Create: `tests/unit/test_validate_capability_labels_overlay.py`

- [ ] **Step 1: Run target tests, confirm fail**

```bash
pytest tests/unit/test_validate_capability_labels_overlay.py -v
```

Expected: ERROR (file not exists).

- [ ] **Step 2: Adicionar `load_catalog` em `validators/_common.py`**

Edit `validators/_common.py`. Adicione no final do arquivo (mantém imports do arquivo intactos):

```python
# ── Capability catalog overlay loader ────────────────────────────────────────
#
# Une o catálogo canônico (parseado de docs/schemas/capability-labels.md via
# engine.cards.loader) com o overlay local em
# .claude/inventory/capability-labels.local.yaml. Guards aplicados aqui são
# fonte única — validators downstream consomem o resultado.

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml as _yaml_lib


@dataclass
class CapabilityCatalog:
    """Efectivo = canon ∪ local. `reserved` permanece sempre canon-only."""

    canon_all: frozenset[str] = field(default_factory=frozenset)
    canon_singular: frozenset[str] = field(default_factory=frozenset)
    canon_latent: frozenset[str] = field(default_factory=frozenset)
    canon_reserved: frozenset[str] = field(default_factory=frozenset)
    local_added: frozenset[str] = field(default_factory=frozenset)

    @property
    def active(self) -> frozenset[str]:
        return self.canon_all | self.local_added

    @property
    def reserved(self) -> frozenset[str]:
        return self.canon_reserved


class CatalogOverlayError(Exception):
    """Raised when capability-labels.local.yaml is malformed or violates guards."""


_FORBIDDEN_LOCAL_KEYS = {"overrides", "reserved-promotions"}


def load_catalog(project_root: Path) -> CapabilityCatalog:
    """Return canon ∪ local catalog with all guards applied.

    Guards (hard fail):
      - Local label ∈ canon.reserved → CatalogOverlayError
      - Local label ∈ canon.active → CatalogOverlayError
      - Local YAML contém chaves `overrides:` ou `reserved-promotions:` → CatalogOverlayError
      - Local YAML não-mapping → CatalogOverlayError

    Edge cases:
      - Local file ausente → catálogo canon-only (silent)
      - Local file vazio mapping → catálogo canon-only
      - Local com `added: []` → catálogo canon-only
    """
    # Import lazy pra evitar circularidade na partida dos validators.
    from engine.cards.loader import _get_catalog
    from engine.utils.paths import forge_home

    all_labels, singular, latent = _get_catalog()
    reserved = frozenset(all_labels - singular - latent)

    local_path = project_root / ".claude" / "inventory" / "capability-labels.local.yaml"
    if not local_path.is_file():
        return CapabilityCatalog(
            canon_all=all_labels,
            canon_singular=singular,
            canon_latent=latent,
            canon_reserved=reserved,
            local_added=frozenset(),
        )

    try:
        raw_text = local_path.read_text(encoding="utf-8")
        data = _yaml_lib.safe_load(raw_text) or {}
    except _yaml_lib.YAMLError as exc:
        raise CatalogOverlayError(
            f"{local_path}: YAML inválido — {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise CatalogOverlayError(
            f"{local_path}: top-level deve ser mapping, got {type(data).__name__}"
        )

    forbidden_present = sorted(set(data) & _FORBIDDEN_LOCAL_KEYS)
    if forbidden_present:
        raise CatalogOverlayError(
            f"{local_path}: chaves proibidas {forbidden_present} — "
            f"overlay não pode redefinir canon nem promover reservada. "
            f"Promoção exige ADR em docs/design/01-decisions.md."
        )

    added_raw = data.get("added") or []
    if not isinstance(added_raw, list):
        raise CatalogOverlayError(
            f"{local_path}: `added` deve ser lista, got {type(added_raw).__name__}"
        )

    added_names: set[str] = set()
    for entry in added_raw:
        if not isinstance(entry, dict):
            raise CatalogOverlayError(
                f"{local_path}: cada entrada em `added` deve ser mapping"
            )
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise CatalogOverlayError(
                f"{local_path}: cada entrada `added` precisa de `name: <str>` não-vazio"
            )
        if name in reserved:
            raise CatalogOverlayError(
                f"{local_path}: label local {name!r} está reservada no canon. "
                f"Promoção exige ADR + revisita decisão do catálogo."
            )
        if name in all_labels:
            raise CatalogOverlayError(
                f"{local_path}: label local {name!r} colide com canon ativo. "
                f"Renomeie no overlay ou remova do canon (revisita)."
            )
        added_names.add(name)

    return CapabilityCatalog(
        canon_all=all_labels,
        canon_singular=singular,
        canon_latent=latent,
        canon_reserved=reserved,
        local_added=frozenset(added_names),
    )
```

- [ ] **Step 3: Patch `validators/validate_capability_labels.py` pra usar `load_catalog`**

Edit `validators/validate_capability_labels.py`. Substitua a função `_catalog()` (linha ~56) e `_reserved_labels()` por uma única chamada a `load_catalog(project_root)`. O bloco `validate()` muda assim:

```python
from _common import (  # noqa: F401  (mantém imports existentes)
    CatalogOverlayError,
    load_catalog,
    make_paths,
    result_fail,
    result_pass,
    result_warn,
    run_cli,
)


def validate(project_root: Path, **kwargs: Any) -> dict[str, Any]:
    """Validate every card's capability-label usage against canon ∪ local catalog."""
    cards = _collect_cards(project_root)
    if not cards:
        return result_warn(
            "nenhum card.yaml encontrado pra validar",
            what_failed="empty cards dir",
            where=str(cards_dir(project_root)),
            why=["forge init ainda não rodou, ou snapshot vazio"],
        )

    try:
        catalog = load_catalog(project_root)
    except CatalogOverlayError as exc:
        return result_fail(
            "capability-labels.local.yaml inválido",
            what_failed=str(exc),
            where=".claude/inventory/capability-labels.local.yaml",
            why=[
                "Overlay tem guards: sem `overrides`, sem `reserved-promotions`,",
                "sem colisão com canon ativo, sem promoção de reservada.",
            ],
            paths=make_paths(
                "Corrigir o YAML local — remover chaves proibidas",
                "Validator rejeita overlay que tenta redefinir canon.",
                "Renomear label local para evitar colisão",
                "Active set canon tem precedência (Approach A).",
                "Abrir ADR pra promoção ao canon",
                "Promoção exige revisita do catálogo, não overlay.",
            ),
        )

    active = catalog.active
    reserved = catalog.reserved

    failures: list[str] = []
    reserved_hits: list[str] = []
    cards_checked = 0

    for card_yaml in cards:
        cards_checked += 1
        try:
            data = read_yaml_or_default(card_yaml, {}) or {}
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{card_yaml.parent.name}: YAML parse error ({exc})")
            continue
        if not isinstance(data, dict):
            failures.append(f"{card_yaml.parent.name}: top-level not mapping")
            continue

        for block_name in ("provides", "requires", "conflicts-with"):
            block = data.get(block_name) or []
            if not isinstance(block, list):
                continue
            for label in block:
                if not isinstance(label, str) or not label:
                    continue
                if label not in active:
                    failures.append(
                        f"{card_yaml.parent.name}.{block_name}: {label!r} out-of-catalog"
                    )
                elif label in reserved:
                    reserved_hits.append(
                        f"{card_yaml.parent.name}.{block_name}: {label!r} (reserved)"
                    )

    if failures:
        return result_fail(
            f"{len(failures)} label(s) out-of-catalog em {cards_checked} card(s)",
            what_failed="; ".join(failures[:3])
            + (f" (+{len(failures)-3} more)" if len(failures) > 3 else ""),
            where="cards/*/card.yaml",
            why=[
                "capability-labels.md é source-of-truth canon (CARD-006/CARD-007).",
                "Overlay pode adicionar labels via capability-labels.local.yaml.",
                "Labels fora do catálogo efetivo quebram resolução de cards.",
            ],
            paths=make_paths(
                "Adicionar a label ao docs/schemas/capability-labels.md (PR canon)",
                "Catalog evolve via 1-file change; veja seção Reserved.",
                "Adicionar a label ao .claude/inventory/capability-labels.local.yaml",
                "Overlay aceita additions com schema enxuto (`added: [...]`).",
                "Editar o card.yaml e usar label canônica equivalente",
                "Costuma haver sinônimo no catalog.",
            ),
        )

    if reserved_hits:
        return result_warn(
            f"{len(reserved_hits)} label(s) reservada(s) em uso — ainda não implementada(s)",
            what_failed="; ".join(reserved_hits[:3]),
            where="cards/*/card.yaml",
            why=["Labels reservadas são placeholder pra v1.1+"],
        )

    return result_pass(
        f"{cards_checked} card(s) com labels todas no catálogo efetivo (canon ∪ local)"
    )
```

Remove os imports antigos `_get_catalog`, `_parse_capability_catalog`, `cards_canonical_dir`, `forge_home` que ficaram órfãos — só mantenha o que ainda for usado por `_collect_cards`.

- [ ] **Step 4: Write `tests/unit/test_validate_capability_labels_overlay.py` (full content)**

Create `tests/unit/test_validate_capability_labels_overlay.py`:

```python
"""Unit tests — validate_capability_labels overlay-aware via load_catalog.

Cobre:
  - união canon ∪ local (label local válida não dispara out-of-catalog)
  - promoção reservada rejeitada (CatalogOverlayError)
  - colisão active rejeitada (CatalogOverlayError)
  - overlay vazio = canon-only silent
  - YAML malformado (CatalogOverlayError)
  - chaves proibidas (overrides / reserved-promotions)
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from _common import CatalogOverlayError, load_catalog
from engine.cards.loader import _reset_catalog_cache


def _project_with_overlay(tmp_path: Path, overlay_data: dict | str | None) -> Path:
    """Mount fake project root with `.claude/inventory/` ready for overlay testing."""
    project = tmp_path / "proj"
    inv = project / ".claude" / "inventory"
    inv.mkdir(parents=True)
    if overlay_data is None:
        return project
    overlay_path = inv / "capability-labels.local.yaml"
    if isinstance(overlay_data, str):
        # raw string mode — permite YAML malformado deliberado
        overlay_path.write_text(overlay_data, encoding="utf-8")
    else:
        overlay_path.write_text(
            yaml.safe_dump(overlay_data, sort_keys=False), encoding="utf-8"
        )
    return project


@pytest.fixture(autouse=True)
def _fresh_catalog():
    _reset_catalog_cache()
    yield
    _reset_catalog_cache()


# ── Happy paths ─────────────────────────────────────────────────────────────


def test_overlay_absent_returns_canon_only(tmp_path):
    project = _project_with_overlay(tmp_path, None)
    catalog = load_catalog(project)
    assert isinstance(catalog.active, frozenset)
    assert len(catalog.active) > 5  # canon is non-empty
    assert catalog.local_added == frozenset()


def test_overlay_adds_local_label(tmp_path):
    project = _project_with_overlay(
        tmp_path,
        {
            "schema-version": 1,
            "added": [
                {
                    "name": "feature-flag-remote",
                    "description": "LaunchDarkly + Firebase Remote Config",
                    "target-platforms": ["android", "ios"],
                }
            ],
        },
    )
    catalog = load_catalog(project)
    assert "feature-flag-remote" in catalog.active
    assert "feature-flag-remote" in catalog.local_added


def test_overlay_empty_added_is_canon_only(tmp_path):
    project = _project_with_overlay(tmp_path, {"schema-version": 1, "added": []})
    catalog = load_catalog(project)
    assert catalog.local_added == frozenset()


# ── Guards ──────────────────────────────────────────────────────────────────


def test_overlay_rejects_promotion_of_reserved_label(tmp_path):
    """Labels reservadas no canon não podem ser ativadas via overlay."""
    # Pick a reservada que já existe — `hilt-di` está em capability-labels.md
    # como reservada v1.1+. Se renomearem no canon, este test quebra (esperado).
    project = _project_with_overlay(
        tmp_path,
        {
            "schema-version": 1,
            "added": [{"name": "hilt-di", "description": "promovendo reservada"}],
        },
    )
    with pytest.raises(CatalogOverlayError) as exc:
        load_catalog(project)
    assert "reservada" in str(exc.value).lower() or "promoção" in str(exc.value).lower()


def test_overlay_rejects_collision_with_canon_active(tmp_path):
    project = _project_with_overlay(
        tmp_path,
        {
            "schema-version": 1,
            "added": [{"name": "kotlin", "description": "tentando override"}],
        },
    )
    with pytest.raises(CatalogOverlayError) as exc:
        load_catalog(project)
    assert "colide" in str(exc.value).lower() or "canon ativo" in str(exc.value).lower()


def test_overlay_rejects_forbidden_keys(tmp_path):
    project = _project_with_overlay(
        tmp_path,
        {
            "schema-version": 1,
            "added": [],
            "overrides": [{"name": "kotlin", "to": "kotlin-2"}],
        },
    )
    with pytest.raises(CatalogOverlayError) as exc:
        load_catalog(project)
    assert "overrides" in str(exc.value)


def test_overlay_rejects_reserved_promotions_key(tmp_path):
    project = _project_with_overlay(
        tmp_path,
        {
            "schema-version": 1,
            "added": [],
            "reserved-promotions": ["hilt-di"],
        },
    )
    with pytest.raises(CatalogOverlayError) as exc:
        load_catalog(project)
    assert "reserved-promotions" in str(exc.value)


def test_overlay_rejects_malformed_yaml(tmp_path):
    project = _project_with_overlay(
        tmp_path, "added: [not: a: valid: list: shape:"
    )
    with pytest.raises(CatalogOverlayError):
        load_catalog(project)


def test_overlay_rejects_non_mapping_toplevel(tmp_path):
    project = _project_with_overlay(tmp_path, "just a string")
    with pytest.raises(CatalogOverlayError) as exc:
        load_catalog(project)
    assert "mapping" in str(exc.value).lower()


def test_overlay_rejects_added_without_name(tmp_path):
    project = _project_with_overlay(
        tmp_path,
        {
            "schema-version": 1,
            "added": [{"description": "no name field"}],
        },
    )
    with pytest.raises(CatalogOverlayError) as exc:
        load_catalog(project)
    assert "name" in str(exc.value).lower()
```

- [ ] **Step 5: Run new tests, confirm pass**

```bash
pytest tests/unit/test_validate_capability_labels_overlay.py -v
```

Expected: 9 passed.

Se algum teste falhar pela razão "hilt-di não é reservada no canon": confirme em `docs/schemas/capability-labels.md`. Se a label não está mais reservada, substitua no teste por outra reservada vigente (ex.: `apollo-graphql-client`).

- [ ] **Step 6: Run validator suite pra zero regressão**

```bash
pytest tests/validators/ -v
```

Expected: all green. Se algum test antigo de `test_validate_capability_labels.py` quebrar pela refactor: ajuste pra usar `load_catalog` mock conforme novo contrato.

- [ ] **Step 7: Commit**

```bash
git add validators/_common.py validators/validate_capability_labels.py tests/unit/test_validate_capability_labels_overlay.py
git commit -m "feat(validators): capability-labels overlay aware with reservada guard"
```

---

## Fase D — Validators

## Task 7: `validate_card_yaml.py` patches (canon/local discrimination + legacy-marker)

**Files:**
- Modify: `validators/validate_card_yaml.py` (path discrimination + legacy-marker aceito + colisão cross-check)
- Modify: `engine/cards/loader.py` (`validate_card_yaml` aceita `legacy-marker` top-level)
- Create: `tests/unit/test_validate_card_yaml_local.py`

- [ ] **Step 1: Run target test, confirm fail**

```bash
pytest tests/unit/test_validate_card_yaml_local.py -v
```

Expected: ERROR (file not exists).

- [ ] **Step 2: Patch `engine/cards/loader.py::validate_card_yaml` pra aceitar `legacy-marker`**

Edit `engine/cards/loader.py`, função `validate_card_yaml` (linha ~362). Adicione APÓS o bloco de validação de `conflicts` (linha ~443) e ANTES de `contributes = manifest_dict.get("contributes") or {}`:

```python
    # ── Top-level `legacy-marker` (Gap 5 — aditivo, opcional) ────────────────
    legacy_marker = manifest_dict.get("legacy-marker", False)
    if not isinstance(legacy_marker, bool):
        violations.append(
            f"CARD-019: legacy-marker deve ser bool (true|false), got {legacy_marker!r}"
        )
```

CARD-019 é número novo aditivo — adicionar ao bloco de comentários no topo do arquivo:

```python
# CARD-019  legacy-marker, se presente, deve ser bool (opcional, default false)
```

Atualize `docs/schemas/card.md §Validation of card.yaml` tabela com a linha nova `CARD-019  legacy-marker, if present, must be bool`. (Doc-sync formal é Task 13; aqui só adicionamos a linha pra coerência do validator.)

- [ ] **Step 3: Patch `validators/validate_card_yaml.py` — discriminação canon/local via path + colisão cross-check**

Edit `validators/validate_card_yaml.py`. Substitua `_collect_cards` por uma versão que retorna `(path, origin)` tuplas:

```python
def _collect_cards(
    project_root: Path, only: str | None = None
) -> list[tuple[Path, str]]:
    """Return list of (card_yaml_path, origin) where origin ∈ {"canon", "local"}.

    Cascade:
      - canon snapshot: `<project>/.claude/cards/<name>/card.yaml` (exclui `local/` subdir)
      - local overlay: `<project>/.claude/cards/local/<name>/card.yaml`
      - fallback: canonical library `<forge_home>/cards/<name>/card.yaml` quando snapshot vazio
    """
    candidates: list[tuple[Path, str]] = []
    snapshot = cards_dir(project_root)
    if snapshot.is_dir():
        for entry in snapshot.glob("*/card.yaml"):
            # Pula a subpasta `local/` — handled separately abaixo
            if entry.parent.parent.name == "local":
                continue
            if entry.parent.name == "local":
                continue
            candidates.append((entry, "canon"))
        local_root = snapshot / "local"
        if local_root.is_dir():
            for entry in local_root.glob("*/card.yaml"):
                candidates.append((entry, "local"))
    if not candidates:
        canonical = cards_canonical_dir()
        if canonical.is_dir():
            for entry in canonical.glob("*/card.yaml"):
                candidates.append((entry, "canon"))
    if only:
        candidates = [(p, o) for p, o in candidates if p.parent.name == only]
    return sorted(candidates, key=lambda t: (t[1], t[0]))
```

E substitua o bloco principal de `validate` pra usar essa estrutura + cross-check de colisão:

```python
def validate(project_root: Path, **kwargs: Any) -> dict[str, Any]:
    """Run engine.cards.loader.validate_card_yaml against every card.

    Cross-checks adicionados:
      - Colisão canon ∩ local (hard fail, dispara antes do schema check)
      - Mensagens carregam contexto `[canon]` ou `[local]` por path
    """
    only = kwargs.get("card")
    cards = _collect_cards(project_root, only=only)
    if not cards:
        target = f"card={only!r}" if only else "any"
        return result_warn(
            f"nenhum card.yaml encontrado (filter: {target})",
            what_failed="empty cards dir",
            where=str(cards_dir(project_root)),
            why=["forge init ainda não criou snapshot, ou nome inválido em --card"],
        )

    # Cross-check: colisão de nome canon ∩ local (Approach A — hard fail).
    canon_names = {p.parent.name for p, o in cards if o == "canon"}
    local_names = {p.parent.name for p, o in cards if o == "local"}
    collisions = sorted(canon_names & local_names)
    if collisions:
        return result_fail(
            f"colisão de nome canon×local em {len(collisions)} card(s)",
            what_failed=", ".join(collisions),
            where=".claude/cards/<name>/ + .claude/cards/local/<name>/",
            why=[
                "Approach A: card local não pode ter o mesmo nome de canon ativo.",
                "Sem merge silencioso, sem override — escolha consciente exigida.",
            ],
            paths=make_paths(
                "Renomear o card local (`forge reconfigure → card-local → remover` + criar com nome novo)",
                "Mais simples — local pode ter nome qualquer fora do canon.",
                "Abrir ADR pra promoção do card local ao canon",
                "Quando a semântica está madura pra entrar no catálogo oficial.",
                "Remover o canon e manter só local (revisita decisão)",
                "Raríssimo — exige revisita do catálogo canon.",
            ),
        )

    all_violations: list[str] = []
    warnings_only: list[str] = []
    for card_yaml, origin in cards:
        data = read_yaml_or_default(card_yaml, {}) or {}
        if not isinstance(data, dict):
            all_violations.append(
                f"[{origin}] {card_yaml.parent.name}: top-level not mapping"
            )
            continue
        viols = core_validate(data, card_yaml.parent)
        for v in viols:
            label = f"[{origin}] {card_yaml.parent.name}: {v}"
            if "-WARN:" in v:
                warnings_only.append(label)
            else:
                all_violations.append(label)

    if all_violations:
        return result_fail(
            f"{len(all_violations)} violação(ões) em {len(cards)} card(s)",
            what_failed="; ".join(all_violations[:3])
            + (f" (+{len(all_violations)-3} more)" if len(all_violations) > 3 else ""),
            where="cards/*/card.yaml + .claude/cards/local/*/card.yaml",
            why=[
                "docs/schemas/card.md §Validation define CARD-001..CARD-019.",
                "Loader rejeita cards inválidos — composer/resolver não funcionam.",
                "Contexto `[canon]` ou `[local]` identifica camada do erro.",
            ],
            paths=make_paths(
                "Editar o card.yaml e corrigir cada CARD-NNN listado",
                "Mensagens contêm o código + campo exato + camada.",
                "Re-snapshot do canonical — `forge reconfigure → atualizar card`",
                "Quando o erro está em camada canon (origem oficial).",
                "Remover o card local — `forge reconfigure → card-local → remover`",
                "Quando o erro está só no overlay local.",
            ),
        )

    if warnings_only:
        return result_warn(
            f"{len(warnings_only)} warning(s) em {len(cards)} card(s)",
            what_failed="; ".join(warnings_only[:3]),
            where="cards/*/card.yaml + .claude/cards/local/*/card.yaml",
            why=["Warnings não bloqueiam — agentes sem extension-points formalizadas"],
        )

    return result_pass(
        f"{len(cards)} card(s) com schema válido (canon + local, CARD-001..019)"
    )
```

- [ ] **Step 4: Write `tests/unit/test_validate_card_yaml_local.py` (full content)**

Create `tests/unit/test_validate_card_yaml_local.py`:

```python
"""Unit tests — validate_card_yaml.py overlay-aware.

Cobre:
  - canon vs local discrimination via path resolved
  - colisão de nome canon ∩ local → hard fail
  - `legacy-marker: true` aceito (sem CARD-019)
  - `legacy-marker: "yes"` rejeitado (CARD-019, deve ser bool)
  - mensagens carregam contexto [canon] / [local]
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATORS_DIR = REPO_ROOT / "validators"
if str(VALIDATORS_DIR) not in sys.path:
    sys.path.insert(0, str(VALIDATORS_DIR))


def _valid_card_dict(name: str = "demo-card", **overrides) -> dict:
    base = {
        "schema-version": 1,
        "identity": {
            "name": name,
            "version": "1.0.0",
            "description": "Test",
            "category": "kmp",
            "maturity": "stable",
        },
        "provides": ["kotlin-multiplatform"],
        "requires": [],
        "conflicts-with": [],
    }
    base.update(overrides)
    return base


def _write_card(card_dir: Path, data: dict) -> None:
    card_dir.mkdir(parents=True, exist_ok=True)
    (card_dir / "card.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )
    (card_dir / "README.md").write_text("# test\n", encoding="utf-8")


def _build_project_with_cards(
    tmp_path: Path,
    canon: dict[str, dict] | None = None,
    local: dict[str, dict] | None = None,
) -> Path:
    project = tmp_path / "proj"
    cards_root = project / ".claude" / "cards"
    cards_root.mkdir(parents=True)
    if canon:
        for name, data in canon.items():
            _write_card(cards_root / name, data)
    if local:
        for name, data in local.items():
            _write_card(cards_root / "local" / name, data)
    return project


@pytest.fixture
def vcy_module():
    import validate_card_yaml as vcy
    return importlib.reload(vcy)


# ── Path discrimination ─────────────────────────────────────────────────────


def test_canon_card_tagged_canon_in_collection(vcy_module, tmp_path):
    project = _build_project_with_cards(
        tmp_path,
        canon={"alpha": _valid_card_dict("alpha")},
    )
    collected = vcy_module._collect_cards(project)
    origins = {(p.parent.name, o) for p, o in collected}
    assert ("alpha", "canon") in origins


def test_local_card_tagged_local_in_collection(vcy_module, tmp_path):
    project = _build_project_with_cards(
        tmp_path,
        canon={"alpha": _valid_card_dict("alpha")},
        local={"beta": _valid_card_dict("beta")},
    )
    collected = vcy_module._collect_cards(project)
    origins = {(p.parent.name, o) for p, o in collected}
    assert ("alpha", "canon") in origins
    assert ("beta", "local") in origins


# ── Colisão ─────────────────────────────────────────────────────────────────


def test_canon_local_name_collision_hard_fails(vcy_module, tmp_path):
    project = _build_project_with_cards(
        tmp_path,
        canon={"collide": _valid_card_dict("collide")},
        local={"collide": _valid_card_dict("collide")},
    )
    result = vcy_module.validate(project)
    assert result["status"] == "fail"
    assert "colisão" in (result.get("what_failed") or "").lower() or "collide" in (
        result.get("what_failed") or ""
    )


# ── legacy-marker aceito ────────────────────────────────────────────────────


def test_legacy_marker_true_accepted(vcy_module, tmp_path):
    data = _valid_card_dict("legacy-x")
    data["legacy-marker"] = True
    project = _build_project_with_cards(tmp_path, canon={"legacy-x": data})
    result = vcy_module.validate(project)
    # Pode passar (status=pass) ou warn por CARD-013-WARN; o que importa é
    # que NÃO há violação CARD-019 sobre legacy-marker.
    assert result["status"] in ("pass", "warn")
    what = (result.get("what_failed") or "")
    assert "CARD-019" not in what
    assert "legacy-marker" not in what.lower()


def test_legacy_marker_absent_accepted(vcy_module, tmp_path):
    """Default ausente = false, não dispara CARD-019."""
    project = _build_project_with_cards(
        tmp_path, canon={"plain": _valid_card_dict("plain")}
    )
    result = vcy_module.validate(project)
    assert result["status"] in ("pass", "warn")
    assert "CARD-019" not in (result.get("what_failed") or "")


def test_legacy_marker_non_bool_rejected(vcy_module, tmp_path):
    data = _valid_card_dict("bad-marker")
    data["legacy-marker"] = "yes"  # string, não bool
    project = _build_project_with_cards(tmp_path, canon={"bad-marker": data})
    result = vcy_module.validate(project)
    assert result["status"] == "fail"
    assert "CARD-019" in (result.get("what_failed") or "")


# ── Mensagens com contexto ──────────────────────────────────────────────────


def test_local_card_error_messages_carry_local_tag(vcy_module, tmp_path):
    bad_local = _valid_card_dict("bad")
    bad_local["identity"]["version"] = "not-semver"
    project = _build_project_with_cards(
        tmp_path,
        canon={"alpha": _valid_card_dict("alpha")},
        local={"bad": bad_local},
    )
    result = vcy_module.validate(project)
    assert result["status"] == "fail"
    what = result.get("what_failed") or ""
    assert "[local]" in what
    assert "CARD-003" in what
```

- [ ] **Step 5: Run new tests, confirm pass**

```bash
pytest tests/unit/test_validate_card_yaml_local.py -v
```

Expected: 7 passed.

- [ ] **Step 6: Run validator suite + loader suite pra zero regressão**

```bash
pytest tests/validators/ tests/unit/test_cards_loader.py tests/unit/test_cards_loader_local.py -v
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add validators/validate_card_yaml.py engine/cards/loader.py tests/unit/test_validate_card_yaml_local.py
git commit -m "feat(validators): card-yaml overlay aware + legacy-marker support"
```

---

## Fase E — Reconfigure UX

## Task 8: Reconfigure submenu `card-local` — listar + remover

**Files:**
- Modify: `engine/reconfigure.py` (nova opção "card-local" no `_choose_categories`; novo handler `_handle_card_local` com sub-ações listar + remover)
- Create: `tests/unit/test_reconfigure_card_local.py`

- [ ] **Step 1: Run target tests, confirm fail**

```bash
pytest tests/unit/test_reconfigure_card_local.py -v
```

Expected: ERROR.

- [ ] **Step 2: Adicionar opção `card-local` ao `_choose_categories`**

Edit `engine/reconfigure.py`, função `_choose_categories` (linha ~195). Adicione a entrada no dict `options`:

```python
def _choose_categories() -> list[str]:
    options = {
        "cards":          "add/remove/upgrade/lock/inspect",
        "card-local":     "listar/adicionar/remover cards locais (overlay)",
        "paths":          "feature-roots, tests-roots",
        "conventions":    "DI, navigation, folder layout, naming",
        "backend":        "ticketing, external-docs",
        "persona":        "comportamento do mentor",
        "memory":         "L2 distill manual, retention",
        "hooks":          "regenerar",
        "inventory":      "re-extrair DS/i18n/conventions",
        "graph":          "rebuild full",
        "cleanup-bak":    "remover .bak overdue",
        "external-deps":  "marcar dep externa como resolvida",
    }
    return question.ask_multi(
        "O que mudar? (multi-select, vazio = sair sem mudar)",
        options,
        min_selected=0,
    )
```

- [ ] **Step 3: Localize a tabela de dispatch (mesma file)**

Procure em `engine/reconfigure.py` por uma seção que mapeia `category → handler` — tipicamente um `if/elif` em torno de linha 100-180 chamando `_handle_cards`, `_handle_paths`, etc. Adicione um caso novo:

```python
    elif category == "card-local":
        _handle_card_local(project_root, current, working)
```

Se o dispatch é via dict de funções, adicione `"card-local": _handle_card_local` ao dict.

- [ ] **Step 4: Implementar `_handle_card_local` com sub-ações `list` e `remove`**

Adicione APÓS `_handle_cards` (linha ~242):

```python
def _handle_card_local(
    project_root: Path, current: dict[str, Any], working: dict[str, Any]
) -> None:
    """Submenu card-local — cobre listar, adicionar (Task 9), remover.

    Cards locais vivem em `<project>/.claude/cards/local/<name>/`. Schema
    idêntico ao canon — diferença é apenas o path. Loader cascade
    (Task 4-5) tagga `card.origin = "local"`.
    """
    del current  # working já reflete o estado vigente
    action = question.ask(
        "card-local — qual ação?",
        {
            "list":   "1. listar cards locais existentes",
            "add":    "2. adicionar card local (criar do skeleton)",
            "remove": "3. remover card local",
            "back":   "0. voltar",
        },
        default="list",
    )
    if action == "list":
        _card_local_list(project_root)
    elif action == "add":
        _card_local_add(project_root, working)
    elif action == "remove":
        _card_local_remove(project_root, working)
    # "back" = no-op


def _card_local_root(project_root: Path) -> Path:
    return project_root / ".claude" / "cards" / "local"


def _card_local_list(project_root: Path) -> None:
    """Enumera `.claude/cards/local/*/card.yaml` em tabela name+provides+conflicts."""
    root = _card_local_root(project_root)
    if not root.is_dir():
        renderer.write("Nenhum card local cadastrado neste projeto.")
        renderer.write("  → Use opção 2 (adicionar) para criar o primeiro.")
        return

    entries: list[tuple[str, list[str], list[str]]] = []
    for d in sorted(root.iterdir(), key=lambda p: p.name):
        if not d.is_dir() or d.name.startswith("."):
            continue
        if not (d / "card.yaml").is_file():
            continue
        try:
            card = load_card(d)
        except CardError as exc:
            renderer.write(renderer.colored(f"  ⚠️  {d.name} inválido: {exc}", "yellow"))
            continue
        entries.append((card.name, card.provides, card.conflicts_with))

    if not entries:
        renderer.write("Diretório `local/` existe mas está vazio.")
        return

    lines = [f"{'name':<28} provides                              conflicts-with"]
    lines.append("-" * 90)
    for name, prov, conf in entries:
        lines.append(
            f"{name:<28} {', '.join(prov)[:38]:<38} {', '.join(conf)}"
        )
    renderer.write(renderer.box(f"Cards locais ({len(entries)})", lines))


def _card_local_remove(project_root: Path, working: dict[str, Any]) -> None:
    """Remove um card local com 3-caminhos de confirmação e .bak retention."""
    del working  # remoção não muda workflow-config; só filesystem
    root = _card_local_root(project_root)
    if not root.is_dir():
        renderer.write("Nenhum card local pra remover.")
        return

    names = sorted(
        d.name
        for d in root.iterdir()
        if d.is_dir() and not d.name.startswith(".") and (d / "card.yaml").is_file()
    )
    if not names:
        renderer.write("Diretório `local/` vazio — nada a remover.")
        return

    opts = {n: f"local card `{n}`" for n in names}
    opts["cancelar"] = "voltar sem remover nada"
    picked = question.ask("Remover qual card local?", opts, default="cancelar")
    if picked == "cancelar" or picked not in names:
        renderer.write("Cancelado.")
        return

    snap_dir = root / picked
    bak_dir = root / f"{picked}.bak"

    confirmation = question.ask(
        f"Remover `{picked}` definitivo (3-caminhos)?",
        {
            "remove": f"1. mover snap → .bak ({picked}.bak, retention 7d)",
            "keep":   "2. cancelar — manter o card",
            "abort":  "3. abortar submenu inteiro",
        },
        default="remove",
    )
    if confirmation == "keep":
        renderer.write("Mantido.")
        return
    if confirmation == "abort":
        renderer.write("Abortado.")
        return

    if bak_dir.exists():
        # Discipline §4 — .bak já existe (remoção anterior do mesmo nome).
        # Sobrescrever silenciosamente perde audit; surface ao user.
        renderer.write(
            renderer.colored(
                f"⚠️  {bak_dir} já existe — remoção anterior não foi limpa. "
                "Rode `forge reconfigure → cleanup-bak` antes de tentar de novo.",
                "yellow",
            )
        )
        return

    shutil.move(str(snap_dir), str(bak_dir))
    renderer.write(renderer.colored(f"  - {picked} (snapshot → {picked}.bak)", "yellow"))

    _append_history(
        project_root,
        {
            "op": "card-local-remove",
            "name": picked,
            "bak": str(bak_dir.relative_to(project_root)),
        },
    )
```

- [ ] **Step 5: `_card_local_add` stub (real impl em Task 9)**

Adicione (será expandida em Task 9):

```python
def _card_local_add(project_root: Path, working: dict[str, Any]) -> None:
    """Criar card local do skeleton — expansão completa em Task 9."""
    del working
    renderer.write(
        "Adicionar card local: implementação completa em Task 9 do plano Gap 5."
    )
    renderer.write(f"  → diretório alvo: {_card_local_root(project_root)}")
```

- [ ] **Step 6: Imports necessários no topo de `engine/reconfigure.py`**

Confirme (ou adicione) no topo do arquivo:

```python
from .cards import CardError
from .cards.loader import load_card  # já presente? confirmar
```

`shutil` e `renderer`/`question` já estão importados — confirme rodando o file rapidamente.

- [ ] **Step 7: Write `tests/unit/test_reconfigure_card_local.py` (full content)**

Create `tests/unit/test_reconfigure_card_local.py`:

```python
"""Unit tests — reconfigure submenu card-local (listar + remover).

Cobre:
  - listar vazio (sem dir local/ ou dir vazio)
  - listar N items (renderiza tabela)
  - remover happy (snap → .bak + history)
  - remover cancel (3-caminhos opção 2 ou 3)
  - remover quando `.bak` pré-existente (surface warning, não sobrescreve)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from engine import reconfigure


def _write_local_card(project: Path, name: str, provides: list[str] | None = None) -> None:
    card_dir = project / ".claude" / "cards" / "local" / name
    card_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "schema-version": 1,
        "identity": {
            "name": name,
            "version": "1.0.0",
            "description": "Test local",
            "category": "kmp",
            "maturity": "stable",
        },
        "provides": provides or ["kotlin-multiplatform"],
        "requires": [],
        "conflicts-with": [],
    }
    (card_dir / "card.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    (card_dir / "README.md").write_text("# test\n", encoding="utf-8")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    proj = tmp_path / "p"
    (proj / ".claude" / "cards" / "local").mkdir(parents=True)
    (proj / ".claude" / "state").mkdir(parents=True)
    return proj


# ── Listar ──────────────────────────────────────────────────────────────────


def test_card_local_list_empty_dir_renders_hint(project, capsys):
    reconfigure._card_local_list(project)
    captured = capsys.readouterr()
    assert "vazio" in captured.out.lower() or "nenhum" in captured.out.lower()


def test_card_local_list_with_two_cards_renders_both(project, capsys):
    _write_local_card(project, "team-a", provides=["kotlin-multiplatform"])
    _write_local_card(project, "team-b", provides=["kotlin"])
    reconfigure._card_local_list(project)
    captured = capsys.readouterr()
    assert "team-a" in captured.out
    assert "team-b" in captured.out


# ── Remover ─────────────────────────────────────────────────────────────────


def test_card_local_remove_happy_path_moves_to_bak(project):
    _write_local_card(project, "team-x")
    with patch.object(reconfigure.question, "ask") as ask_mock, patch.object(
        reconfigure, "_append_history"
    ) as hist_mock:
        ask_mock.side_effect = ["team-x", "remove"]
        reconfigure._card_local_remove(project, working={})
    assert not (project / ".claude" / "cards" / "local" / "team-x").exists()
    assert (project / ".claude" / "cards" / "local" / "team-x.bak").is_dir()
    hist_mock.assert_called_once()
    args = hist_mock.call_args.args
    assert args[1]["op"] == "card-local-remove"
    assert args[1]["name"] == "team-x"


def test_card_local_remove_cancel_keeps_card(project):
    _write_local_card(project, "team-y")
    with patch.object(reconfigure.question, "ask") as ask_mock:
        ask_mock.side_effect = ["team-y", "keep"]
        reconfigure._card_local_remove(project, working={})
    assert (project / ".claude" / "cards" / "local" / "team-y").is_dir()
    assert not (project / ".claude" / "cards" / "local" / "team-y.bak").exists()


def test_card_local_remove_cancelar_at_first_prompt(project):
    _write_local_card(project, "team-z")
    with patch.object(reconfigure.question, "ask") as ask_mock:
        ask_mock.side_effect = ["cancelar"]
        reconfigure._card_local_remove(project, working={})
    assert (project / ".claude" / "cards" / "local" / "team-z").is_dir()


def test_card_local_remove_with_preexisting_bak_surface_warning(project, capsys):
    _write_local_card(project, "team-w")
    # cria .bak fake (simula remoção anterior não limpa)
    bak = project / ".claude" / "cards" / "local" / "team-w.bak"
    bak.mkdir()
    with patch.object(reconfigure.question, "ask") as ask_mock:
        ask_mock.side_effect = ["team-w", "remove"]
        reconfigure._card_local_remove(project, working={})
    # card original deve permanecer (não sobrescrevemos .bak)
    assert (project / ".claude" / "cards" / "local" / "team-w").is_dir()
    captured = capsys.readouterr()
    assert "já existe" in captured.out or "cleanup-bak" in captured.out


def test_card_local_remove_empty_dir_returns_early(project, capsys):
    reconfigure._card_local_remove(project, working={})
    captured = capsys.readouterr()
    assert "vazio" in captured.out.lower() or "nada a remover" in captured.out.lower()
```

- [ ] **Step 8: Run tests, confirm pass**

```bash
pytest tests/unit/test_reconfigure_card_local.py -v
```

Expected: 6 passed. Se algum teste falhar pela ausência de `renderer.box` ou ordem de prompts: ajuste o `side_effect` do mock pra refletir a ordem real implementada.

- [ ] **Step 9: Commit**

```bash
git add engine/reconfigure.py tests/unit/test_reconfigure_card_local.py
git commit -m "feat(reconfigure): card-local submenu (list + remove)"
```

---

## Task 9: Reconfigure card-local — "Adicionar do skeleton"

**Files:**
- Modify: `engine/reconfigure.py` (expande `_card_local_add` com fluxo prompted completo)
- Modify: `tests/unit/test_reconfigure_card_local.py` (adiciona 3 testes pra adicionar)

- [ ] **Step 1: Adicionar 3 testes ao final de `tests/unit/test_reconfigure_card_local.py`**

```python
# ── Adicionar (do skeleton) ─────────────────────────────────────────────────


def test_card_local_add_happy_creates_skeleton(project):
    """Adicionar happy: prompts respondidos, dir criado, validate roda."""
    with patch.object(reconfigure.question, "ask") as ask_mock, patch.object(
        reconfigure.question, "ask_text"
    ) as ask_text_mock, patch.object(
        reconfigure, "_append_history"
    ) as hist_mock:
        # ordem de prompts:
        #   ask_text("Nome do card") → "hilt-di"
        #   ask_text("Capability") → "di-framework"
        #   ask("Adicionar label local?") → "yes"
        #   ask_text("Conflicts-with") → "koin-annotations"
        #   ask_text("Target platforms") → "android"
        #   ask("Confirma 3-caminhos") → "create"
        ask_text_mock.side_effect = [
            "hilt-di",
            "di-framework",
            "koin-annotations",
            "android",
        ]
        ask_mock.side_effect = ["yes", "create"]
        reconfigure._card_local_add(project, working={})

    card_dir = project / ".claude" / "cards" / "local" / "hilt-di"
    assert card_dir.is_dir()
    assert (card_dir / "card.yaml").is_file()
    assert (card_dir / "README.md").is_file()
    assert (card_dir / "detection" / "signals.yaml").is_file()
    parsed = yaml.safe_load((card_dir / "card.yaml").read_text(encoding="utf-8"))
    assert parsed["identity"]["name"] == "hilt-di"
    assert parsed["provides"] == ["di-framework"]
    assert parsed["conflicts-with"] == ["koin-annotations"]
    assert parsed.get("legacy-marker", False) is False
    hist_mock.assert_called_once()


def test_card_local_add_name_collision_aborts(project):
    """Se nome já existe (canon OU local), prompt repete ou aborta."""
    _write_local_card(project, "existing")
    with patch.object(reconfigure.question, "ask") as ask_mock, patch.object(
        reconfigure.question, "ask_text"
    ) as ask_text_mock:
        ask_text_mock.side_effect = ["existing"]
        ask_mock.side_effect = ["abort"]
        reconfigure._card_local_add(project, working={})
    # nenhum card novo criado
    assert len(list((project / ".claude" / "cards" / "local").iterdir())) == 1


def test_card_local_add_cancel_at_confirmation(project):
    with patch.object(reconfigure.question, "ask") as ask_mock, patch.object(
        reconfigure.question, "ask_text"
    ) as ask_text_mock:
        ask_text_mock.side_effect = ["xyz", "some-cap", "", "android"]
        ask_mock.side_effect = ["yes", "cancel"]
        reconfigure._card_local_add(project, working={})
    assert not (project / ".claude" / "cards" / "local" / "xyz").exists()
```

- [ ] **Step 2: Expandir `_card_local_add` em `engine/reconfigure.py`**

Substitua o stub criado na Task 8 pelo bloco completo:

```python
import re as _re

_LOCAL_CARD_NAME_RE = _re.compile(r"^[a-z][a-z0-9-]{0,39}$")


def _card_local_add(project_root: Path, working: dict[str, Any]) -> None:
    """Cria card local do skeleton via prompts mentor-calmo.

    Skeleton minimal (espelha schema canon):
      .claude/cards/local/<name>/
      ├── card.yaml           (preenchido pelos prompts)
      ├── README.md           (skeleton placeholder)
      └── detection/signals.yaml  (vazio com comentário pra preencher depois)

    Subdirs opcionais (templates/, validators/, agent-contributions/) NÃO
    são criados como stubs — emergem sob demanda quando o time adiciona
    conteúdo (rationale em spec §5.3).
    """
    del working
    local_root = _card_local_root(project_root)
    local_root.mkdir(parents=True, exist_ok=True)

    # Existing names (canon + local) para detectar colisão.
    snapshot_root = project_root / ".claude" / "cards"
    existing_canon = {
        d.name
        for d in snapshot_root.iterdir()
        if d.is_dir() and not d.name.startswith(".") and d.name != "local"
    } if snapshot_root.is_dir() else set()
    existing_local = {
        d.name
        for d in local_root.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    }
    taken = existing_canon | existing_local

    name = question.ask_text(
        "Nome do card local (kebab-case, [a-z][a-z0-9-]{0,39}, sem espaços):"
    ).strip()
    if not _LOCAL_CARD_NAME_RE.match(name or ""):
        renderer.write(
            renderer.colored(
                f"Nome inválido: {name!r}. Cancelado.", "red"
            )
        )
        return
    if name in taken:
        renderer.write(
            renderer.colored(
                f"Nome `{name}` já existe ({'canon' if name in existing_canon else 'local'}).",
                "yellow",
            )
        )
        choice = question.ask(
            "Três caminhos:",
            {
                "rename": "1. fornecer outro nome",
                "abort":  "2. abortar adicionar",
                "list":   "3. listar cards existentes",
            },
            default="abort",
        )
        # Política simplificada: qualquer escolha != continuação encerra aqui.
        # Re-prompt completo é gap declarado pra v1.2 (anota em pending).
        if choice == "list":
            _card_local_list(project_root)
        return

    capability = question.ask_text(
        "Qual capability este card provê?\n"
        "  Veja catálogo ativo em docs/schemas/capability-labels.md\n"
        "  Reservadas (não-disponíveis aqui) exigem ADR pra promoção.\n"
        "Label:"
    ).strip()
    if not capability:
        renderer.write(renderer.colored("Capability obrigatória. Cancelado.", "red"))
        return

    add_to_overlay = question.ask(
        f"'{capability}' será gravada no card. Confirma?",
        {"yes": "1. sim, adicionar", "no": "2. cancelar"},
        default="yes",
    )
    if add_to_overlay != "yes":
        renderer.write("Cancelado.")
        return

    conflicts_raw = question.ask_text(
        "Conflicts-with (lista de cards canon/local separados por vírgula, "
        "vazio se nenhum):"
    ).strip()
    conflicts = [c.strip() for c in conflicts_raw.split(",") if c.strip()]

    platforms_raw = question.ask_text(
        "Target platforms (android,ios,kmp,web — múltiplos separados por vírgula):"
    ).strip()
    # Platforms é metadata informativa pro README do skeleton; não vai pro YAML
    # (cards não declaram target-platforms — semântica derivada de signals).
    platforms = [p.strip() for p in platforms_raw.split(",") if p.strip()] or ["android"]

    summary_lines = [
        f"name:           {name}",
        f"provides:       [{capability}]",
        f"conflicts-with: {conflicts or '[]'}",
        f"target:         {platforms}",
        "legacy-marker:  false",
    ]
    renderer.write(renderer.box("Vou criar card local com", summary_lines))

    confirm = question.ask(
        "Três caminhos:",
        {
            "create": "1. criar e abrir card.yaml para preenchimento de signals",
            "stub":   "2. criar com signals.yaml vazio (preencher depois)",
            "cancel": "3. cancelar e voltar ao menu",
        },
        default="create",
    )
    if confirm == "cancel":
        renderer.write("Cancelado.")
        return

    # Materializa skeleton.
    card_dir = local_root / name
    card_dir.mkdir(parents=True, exist_ok=True)
    detection_dir = card_dir / "detection"
    detection_dir.mkdir(parents=True, exist_ok=True)

    card_data = {
        "schema-version": 1,
        "identity": {
            "name":         name,
            "version":      "0.1.0",
            "description":  f"Local card {name} — {capability} (overlay).",
            "category":     "kmp",
            "maturity":     "experimental",
            "maintainer":   "team-local",
            "created-at":   _today_iso(),
            "last-updated": _today_iso(),
        },
        "legacy-marker": False,
        "provides":      [capability],
        "requires":      [],
        "conflicts-with": conflicts,
        "contributes": {
            "config-defaults": {},
        },
        "detection": {
            "signals":   [],
            "threshold": 0.6,
        },
        "documentation": {
            "readme": "README.md",
        },
    }
    (card_dir / "card.yaml").write_text(
        yaml.safe_dump(card_data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    (card_dir / "README.md").write_text(
        f"# {name}\n\n"
        f"Card local (overlay) provido pelo time deste projeto. Provê "
        f"`{capability}` para as plataformas: {', '.join(platforms)}.\n\n"
        f"## Detection\n\n"
        f"Signals ainda não preenchidos — edite `detection/signals.yaml` e "
        f"replique os matches em `card.yaml > detection.signals`.\n\n"
        f"## Promoção ao canon\n\n"
        f"Quando a semântica deste card estabilizar e for útil para outros "
        f"projetos, abra ADR em `docs/design/01-decisions.md` pra promoção "
        f"ao catálogo canônico.\n",
        encoding="utf-8",
    )

    (detection_dir / "signals.yaml").write_text(
        "# .claude/cards/local/{0}/detection/signals.yaml\n"
        "# ──────────────────────────────────────────────────────────────────\n"
        "# Signals do card local. Preencha após init rodar e mapear sinais\n"
        "# reais do projeto. Espelhe entries em `card.yaml > detection.signals`.\n"
        "# ──────────────────────────────────────────────────────────────────\n\n"
        "schema-version: 1\n\n"
        "signals: []\n\n"
        "threshold: 0.6\n".format(name),
        encoding="utf-8",
    )

    renderer.write(
        renderer.colored(f"  ✓ card local `{name}` criado em {card_dir.relative_to(project_root)}", "green")
    )

    # Validate imediato (catch malformação)
    try:
        manifest = load_card(card_dir)
    except CardError as exc:
        renderer.write(
            renderer.colored(f"  ⚠️  validate_card_yaml acusou: {exc}", "yellow")
        )

    # Warning se signals vazio (que é o estado padrão do skeleton)
    if confirm == "stub":
        renderer.write(
            renderer.colored(
                "  ⚠️  signals.yaml vazio — detection ignora este card "
                "até preencher signals.",
                "yellow",
            )
        )

    _append_history(
        project_root,
        {
            "op":           "card-local-add",
            "name":         name,
            "provides":     [capability],
            "conflicts-with": conflicts,
        },
    )


def _today_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).date().isoformat()
```

E confirme imports no topo de `engine/reconfigure.py`:

```python
import yaml  # já presente? adicionar se ausente
```

- [ ] **Step 3: Run tests, confirm pass**

```bash
pytest tests/unit/test_reconfigure_card_local.py -v
```

Expected: 9 passed (6 da Task 8 + 3 desta task).

- [ ] **Step 4: Commit**

```bash
git add engine/reconfigure.py tests/unit/test_reconfigure_card_local.py
git commit -m "feat(reconfigure): card-local \"create from skeleton\" flow"
```

---

## Fase F — Init Step 7.5

## Task 10: `_check_orphan_signals` helper em `engine/init.py`

**Files:**
- Modify: `engine/init.py` (novo helper `_check_orphan_signals` + dataclass `OrphanSignal`)
- Create: `tests/unit/test_init_orphan_signals.py`

- [ ] **Step 1: Run target test, confirm fail**

```bash
pytest tests/unit/test_init_orphan_signals.py -v
```

Expected: ERROR.

- [ ] **Step 2: Adicionar dataclass `OrphanSignal` + helper `_check_orphan_signals` em `engine/init.py`**

Edit `engine/init.py`. Adicione APÓS a função `_eval_detection_signals` (linha ~148):

```python
@dataclass
class OrphanSignal:
    """Signal que casou em scan mas não em nenhum card (canon ∪ local).

    Atributos:
      - signal_id: identificador (do detection/signals.yaml ou inline derivado)
      - source: arquivo onde o signal casou (relativo ao project_root)
      - suggested_capability: label que a heurística infere
      - is_reserved: True se suggested_capability ∈ canon.reserved
        (Step 7.5 muda o caminho 1 de "criar local" pra "abrir ADR")
      - hit_count: número de ocorrências (qualidade do signal)
    """

    signal_id: str
    source: str
    suggested_capability: str
    is_reserved: bool = False
    hit_count: int = 0


def _check_orphan_signals(
    project_root: Path,
    canonical_cards: list["CardManifest"],
    catalog,
) -> list[OrphanSignal]:
    """Detecta signals que bateram em scan mas não em card algum (canon ∪ local).

    Heurística:
      - Para cada card carregado, registra o set de signal contains/globs.
      - Scan independente do project_root pega imports/anotações comuns que
        sugerem capabilities ausentes (hilt-di, apollo-graphql, rxjava3).
      - Cada miss vira um OrphanSignal com suggested_capability inferida
        por lookup numa tabela `_ORPHAN_HEURISTICS` (best-effort, não exaustiva).
      - Se suggested_capability ∈ catalog.reserved → marca is_reserved=True.

    Conservador: se nenhuma heurística bate, retorna lista vazia (não inventa).
    """
    project = project_root.resolve()
    matched_in_cards: set[str] = set()
    for card in canonical_cards:
        for sig in (card.detection or {}).get("signals") or []:
            contains = (sig or {}).get("contains")
            if isinstance(contains, str) and contains:
                matched_in_cards.add(contains)

    orphans: list[OrphanSignal] = []
    for needle, suggested in _ORPHAN_HEURISTICS.items():
        if needle in matched_in_cards:
            continue
        hits = _count_needle_hits(project, needle)
        if hits == 0:
            continue
        is_reserved = suggested in catalog.reserved
        orphans.append(
            OrphanSignal(
                signal_id=f"orphan:{needle}",
                source=f"detected in {hits} file(s)",
                suggested_capability=suggested,
                is_reserved=is_reserved,
                hit_count=hits,
            )
        )
    return orphans


# Heurística mínima — needle → suggested capability. Lista enxuta, foco em
# casos comuns que motivam Gap 5. Expansão fica pra próximas waves.
_ORPHAN_HEURISTICS: dict[str, str] = {
    "@HiltAndroidApp":              "hilt-di",
    "dagger.hilt.android":          "hilt-di",
    "import com.apollographql":     "apollo-graphql-client",
    "ApolloClient(":                "apollo-graphql-client",
    "io.reactivex.rxjava3":         "rxjava3-streams",
    "io.realm.kotlin":              "realm-local",
}


def _count_needle_hits(project_root: Path, needle: str, limit: int = 50) -> int:
    """Conta arquivos .kt/.gradle* que contêm `needle`. Cap em `limit` pra
    evitar varredura cara em monorepos grandes — qualquer valor >= 1 é
    suficiente pra Step 7.5 surface.
    """
    count = 0
    patterns = ("*.kt", "build.gradle", "build.gradle.kts", "settings.gradle*")
    for pattern in patterns:
        for path in project_root.rglob(pattern):
            if any(part.startswith(".") for part in path.relative_to(project_root).parts):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if needle in text:
                count += 1
                if count >= limit:
                    return count
    return count
```

- [ ] **Step 3: Write `tests/unit/test_init_orphan_signals.py` (parte 1)**

Create `tests/unit/test_init_orphan_signals.py`:

```python
"""Unit tests — init Step 7.5: orphan signals detection + 3-caminhos.

Parte 1 (Task 10): _check_orphan_signals detection
Parte 2 (Task 11): _surface_three_paths UX
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from engine.init import (
    OrphanSignal,
    _check_orphan_signals,
    _count_needle_hits,
)


@pytest.fixture
def project_with_hilt(tmp_path: Path) -> Path:
    """Project root com 3 arquivos .kt mencionando Hilt — orphan target."""
    proj = tmp_path / "proj"
    (proj / "app" / "src" / "main" / "kotlin" / "com" / "x").mkdir(parents=True)
    src = proj / "app" / "src" / "main" / "kotlin" / "com" / "x"
    (src / "App.kt").write_text(
        "package com.x\n\nimport dagger.hilt.android.HiltAndroidApp\n\n@HiltAndroidApp\nclass App\n",
        encoding="utf-8",
    )
    (src / "Module.kt").write_text(
        "package com.x\n\nimport dagger.hilt.android.AndroidEntryPoint\n",
        encoding="utf-8",
    )
    (src / "Helper.kt").write_text(
        "package com.x\n\nimport dagger.hilt.android.qualifiers.ApplicationContext\n",
        encoding="utf-8",
    )
    return proj


class _FakeCatalog:
    def __init__(self, reserved: set[str]) -> None:
        self.reserved = frozenset(reserved)


def test_count_needle_hits_finds_three_files(project_with_hilt):
    count = _count_needle_hits(project_with_hilt, "dagger.hilt.android")
    assert count == 3


def test_count_needle_hits_zero_for_absent_pattern(project_with_hilt):
    count = _count_needle_hits(project_with_hilt, "this-string-does-not-exist")
    assert count == 0


def test_check_orphan_signals_detects_hilt_when_no_card_covers_it(project_with_hilt):
    """Hilt detected, hilt-di label is reserved (canon roadmap) → is_reserved=True."""
    catalog = _FakeCatalog(reserved={"hilt-di"})
    orphans = _check_orphan_signals(project_with_hilt, canonical_cards=[], catalog=catalog)
    hilt_orphans = [o for o in orphans if o.suggested_capability == "hilt-di"]
    assert hilt_orphans, "Hilt orphan deveria ter sido detectado"
    o = hilt_orphans[0]
    assert o.is_reserved is True
    assert o.hit_count >= 1


def test_check_orphan_signals_returns_empty_when_card_covers_needle(project_with_hilt):
    """Card existente cobre `dagger.hilt.android` no detection.signals → não vira orphan."""
    from engine.cards.loader import CardManifest

    fake_card = CardManifest(
        name="hilt-di",
        version="1.0.0",
        schema_version=1,
        description="",
        category="dependency-injection",
        maturity="stable",
        provides=["hilt-di"],
        detection={
            "signals": [
                {"type": "file-content", "glob": "**/*.kt", "contains": "dagger.hilt.android", "confidence": 0.5}
            ],
            "threshold": 0.5,
        },
    )
    catalog = _FakeCatalog(reserved=set())
    orphans = _check_orphan_signals(
        project_with_hilt, canonical_cards=[fake_card], catalog=catalog
    )
    # `dagger.hilt.android` é o needle exato cobrendo — não vira orphan.
    # `@HiltAndroidApp` ainda é outro needle distinto na heurística; depende
    # se está coberto. Aqui só queremos confirmar que o needle coberto sai.
    needles_in_orphans = {o.signal_id for o in orphans}
    assert "orphan:dagger.hilt.android" not in needles_in_orphans


def test_check_orphan_signals_marks_non_reserved_when_not_in_catalog(tmp_path):
    """Suggested capability fora de reserved → is_reserved=False."""
    proj = tmp_path / "p"
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "X.kt").write_text("import io.reactivex.rxjava3.core.Observable\n", encoding="utf-8")

    catalog = _FakeCatalog(reserved=set())  # vazio — nada é reservado
    orphans = _check_orphan_signals(proj, canonical_cards=[], catalog=catalog)
    rx = [o for o in orphans if o.suggested_capability == "rxjava3-streams"]
    assert rx and rx[0].is_reserved is False


def test_check_orphan_signals_empty_project_returns_no_orphans(tmp_path):
    proj = tmp_path / "empty"
    proj.mkdir()
    catalog = _FakeCatalog(reserved={"hilt-di"})
    orphans = _check_orphan_signals(proj, canonical_cards=[], catalog=catalog)
    assert orphans == []
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
pytest tests/unit/test_init_orphan_signals.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add engine/init.py tests/unit/test_init_orphan_signals.py
git commit -m "feat(init): detect orphan signals after cascade match"
```

---

## Task 11: Init Step 7.5 — 3-caminhos UX + reservada edge case

**Files:**
- Modify: `engine/init.py` (`_surface_three_paths` + hook entre Step 7 e Step 8)
- Modify: `tests/unit/test_init_orphan_signals.py` (adiciona testes parte 2)

- [ ] **Step 1: Adicionar testes parte 2 ao final de `tests/unit/test_init_orphan_signals.py`**

```python
# ── Parte 2 — _surface_three_paths UX ───────────────────────────────────────


from unittest.mock import patch

from engine.init import (
    InitDecision,
    _surface_three_paths,
)


@pytest.fixture
def hilt_orphan() -> OrphanSignal:
    return OrphanSignal(
        signal_id="orphan:@HiltAndroidApp",
        source="detected in 3 file(s)",
        suggested_capability="hilt-di",
        is_reserved=True,
        hit_count=3,
    )


@pytest.fixture
def rx_orphan() -> OrphanSignal:
    return OrphanSignal(
        signal_id="orphan:io.reactivex.rxjava3",
        source="detected in 12 file(s)",
        suggested_capability="async-streams",
        is_reserved=False,
        hit_count=12,
    )


def test_three_paths_caminho_1_creates_local_for_non_reserved(rx_orphan, tmp_path):
    """Caminho 1 (não-reservada): chama reconfigure card-local add inline."""
    proj = tmp_path / "p"
    (proj / ".claude").mkdir(parents=True)
    with patch("engine.init.question.ask") as ask_mock, patch(
        "engine.init._card_local_add_inline"
    ) as add_mock:
        ask_mock.return_value = "1"
        decision = _surface_three_paths([rx_orphan], project_root=proj)
    assert decision.choice == "create-local"
    add_mock.assert_called_once()


def test_three_paths_caminho_1_reserved_routes_to_adr(hilt_orphan, tmp_path):
    """Caminho 1 com reservada: NÃO cria local, oferece abrir ADR."""
    proj = tmp_path / "p"
    (proj / ".claude").mkdir(parents=True)
    with patch("engine.init.question.ask") as ask_mock:
        ask_mock.return_value = "1"
        decision = _surface_three_paths([hilt_orphan], project_root=proj)
    assert decision.choice == "adr-required"
    assert "hilt-di" in decision.note


def test_three_paths_caminho_2_writes_ignored_signals_yaml(rx_orphan, tmp_path):
    proj = tmp_path / "p"
    (proj / ".claude" / "inventory").mkdir(parents=True)
    with patch("engine.init.question.ask") as ask_mock:
        ask_mock.return_value = "2"
        decision = _surface_three_paths([rx_orphan], project_root=proj)
    assert decision.choice == "ignore"
    ignored_path = proj / ".claude" / "inventory" / "ignored-signals.yaml"
    assert ignored_path.is_file()
    parsed = yaml.safe_load(ignored_path.read_text(encoding="utf-8"))
    assert parsed.get("schema-version") == 1
    entries = parsed.get("ignored") or []
    assert any(e.get("signal_id") == "orphan:io.reactivex.rxjava3" for e in entries)


def test_three_paths_caminho_3_aborts_with_exit_8(rx_orphan, tmp_path):
    proj = tmp_path / "p"
    (proj / ".claude").mkdir(parents=True)
    with patch("engine.init.question.ask") as ask_mock:
        ask_mock.return_value = "3"
        decision = _surface_three_paths([rx_orphan], project_root=proj)
    assert decision.choice == "abort"
    assert decision.exit_code == 8


def test_three_paths_invalid_choice_reprompts_then_resolves(rx_orphan, tmp_path):
    proj = tmp_path / "p"
    (proj / ".claude" / "inventory").mkdir(parents=True)
    with patch("engine.init.question.ask") as ask_mock:
        # primeiro retorna escolha inválida, depois "2"
        ask_mock.side_effect = ["bogus", "2"]
        decision = _surface_three_paths([rx_orphan], project_root=proj)
    assert decision.choice == "ignore"
    assert ask_mock.call_count == 2


def test_three_paths_empty_orphan_list_is_no_op(tmp_path):
    proj = tmp_path / "p"
    (proj / ".claude").mkdir(parents=True)
    decision = _surface_three_paths([], project_root=proj)
    assert decision.choice == "noop"
```

- [ ] **Step 2: Implementar `InitDecision` + `_surface_three_paths` + `_card_local_add_inline` em `engine/init.py`**

Adicione APÓS `_check_orphan_signals` e antes do bloco principal `def main()` (ou seu equivalente, próximo da linha ~200):

```python
@dataclass
class InitDecision:
    """Resultado do Step 7.5 — usado pelo loop principal pra decidir next step."""

    choice: str  # "create-local" | "adr-required" | "ignore" | "abort" | "noop"
    exit_code: int = 0
    note: str = ""


def _surface_three_paths(
    orphans: list[OrphanSignal],
    project_root: Path,
) -> InitDecision:
    """Apresenta 3-caminhos canônicos pra signals órfãos.

    Edge case reservada: se TODOS os orphans apontam capability reservada,
    caminho 1 muda de "criar card local" pra "abrir ADR pra promoção".
    Quando misturado (alguns reservados, outros não), caminho 1 ainda tenta
    criar local pros não-reservados e marca ADR-required pros reservados.

    Reprompt em escolha inválida (esperado [1-3], qualquer outro reabre).
    """
    if not orphans:
        return InitDecision(choice="noop")

    all_reserved = all(o.is_reserved for o in orphans)

    # Header + listagem mentor calmo PT-BR
    renderer.write("")
    renderer.write(renderer.colored("🛑  Stack ambígua — signals sem card correspondente", "yellow"))
    renderer.write("")
    renderer.write("Detectei sinais que apontam pra capabilities sem provider declarado:")
    renderer.write("")
    for o in orphans:
        reserved_tag = " (label RESERVADA no catálogo canon)" if o.is_reserved else ""
        renderer.write(
            f"  · Signal {o.signal_id} ({o.source})"
        )
        renderer.write(
            f"    → capability {o.suggested_capability!r}{reserved_tag}"
        )
    renderer.write("")
    renderer.write("Onde:")
    renderer.write("  Detection cascade rodou mas não encontrou card canon nem local")
    renderer.write("  pra estes signals.")
    renderer.write("")
    renderer.write("Por que importa:")
    renderer.write("  Materializar o plan sem provider declarado deixa essas capabilities")
    renderer.write("  como \"comportamento inventado\" — viola o princípio \"never invents\"")
    renderer.write("  (docs/design/00-vision.md §What feature-forge is NOT) e quebra o")
    renderer.write("  contrato com validate_no_invented_behavior na Fase 5b.")
    renderer.write("")
    renderer.write("Três caminhos pra resolver:")
    renderer.write("")
    if all_reserved:
        renderer.write("  1) Abrir ADR pra promoção ao canon (recomendado)")
        renderer.write("     Cria entrada em docs/design/01-decisions.md \"Revisita roadmap")
        renderer.write("     do catálogo — promove <label> ao canon\" e suspende init até")
        renderer.write("     PR de promoção rodar.")
    else:
        renderer.write("  1) Criar card local agora (recomendado pra stack atual)")
        renderer.write("     Chama reconfigure inline pra criar card(s) local(is) cobrindo")
        renderer.write("     os signals órfãos. Após criação, init reentra no Step 7")
        renderer.write("     (detection) com catálogo expandido.")
    renderer.write("")
    renderer.write("  2) Ignorar nesta init (registra decisão consciente)")
    renderer.write("     Grava .claude/inventory/ignored-signals.yaml versionado listando")
    renderer.write("     os signals + razão. Validators downstream respeitam o ignore.")
    renderer.write("     Reversível: removendo a entrada, signals voltam a ser órfãos.")
    renderer.write("")
    renderer.write("  3) Abortar init")
    renderer.write("     Exit code 8 (distinto de 5/7/130). Nenhum arquivo materializado.")
    renderer.write("     Use quando o time precisa decidir arquitetura antes de seguir.")
    renderer.write("")

    while True:
        choice = question.ask(
            "Escolha [1-3]:",
            {"1": "1", "2": "2", "3": "3"},
            default="1",
        )
        if choice in {"1", "2", "3"}:
            break
        renderer.write(renderer.colored("Escolha inválida — esperado 1, 2 ou 3.", "yellow"))

    if choice == "1":
        if all_reserved:
            labels = ", ".join(sorted({o.suggested_capability for o in orphans}))
            return InitDecision(
                choice="adr-required",
                note=f"Labels reservadas detectadas: {labels}. Abra ADR antes de prosseguir.",
            )
        # Cria local pros não-reservados; reservados saem como note.
        non_reserved = [o for o in orphans if not o.is_reserved]
        reserved_labels = sorted({o.suggested_capability for o in orphans if o.is_reserved})
        for o in non_reserved:
            _card_local_add_inline(project_root, o)
        note = ""
        if reserved_labels:
            note = (
                f"Reservadas pendentes de ADR: {', '.join(reserved_labels)}. "
                "Criados apenas os locais não-reservados."
            )
        return InitDecision(choice="create-local", note=note)

    if choice == "2":
        _write_ignored_signals(project_root, orphans)
        return InitDecision(choice="ignore")

    # choice == "3"
    return InitDecision(choice="abort", exit_code=8)


def _card_local_add_inline(project_root: Path, orphan: OrphanSignal) -> None:
    """Cria card local minimal cobrindo um orphan signal (modo não-interativo).

    Espelha skeleton de `_card_local_add` mas pre-preenche `name`,
    `provides`, e adiciona um signal inicial baseado no orphan needle.
    Usado pelo Step 7.5 quando user escolhe caminho 1.
    """
    from .reconfigure import _LOCAL_CARD_NAME_RE  # reuse regex

    name_base = orphan.suggested_capability
    name = name_base if _LOCAL_CARD_NAME_RE.match(name_base) else "orphan-card"

    local_root = project_root / ".claude" / "cards" / "local" / name
    local_root.mkdir(parents=True, exist_ok=True)
    (local_root / "detection").mkdir(parents=True, exist_ok=True)

    needle = orphan.signal_id.removeprefix("orphan:")
    card_data = {
        "schema-version": 1,
        "identity": {
            "name": name,
            "version": "0.1.0",
            "description": f"Orphan-derived local card cobrindo {orphan.suggested_capability}.",
            "category": "kmp",
            "maturity": "experimental",
            "maintainer": "team-local-auto",
            "created-at": _today_iso_for_init(),
            "last-updated": _today_iso_for_init(),
        },
        "legacy-marker": False,
        "provides": [orphan.suggested_capability],
        "requires": [],
        "conflicts-with": [],
        "contributes": {"config-defaults": {}},
        "detection": {
            "signals": [
                {
                    "type": "file-content",
                    "glob": "**/*.kt",
                    "contains": needle,
                    "confidence": 0.5,
                }
            ],
            "threshold": 0.5,
        },
        "documentation": {"readme": "README.md"},
    }
    (local_root / "card.yaml").write_text(
        _yaml_lib.safe_dump(card_data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    (local_root / "README.md").write_text(
        f"# {name}\n\n"
        f"Card local criado automaticamente pelo init Step 7.5 a partir do "
        f"signal órfão `{needle}`. Revise threshold e signals adicionais "
        f"em `card.yaml` antes do próximo `forge verify`.\n",
        encoding="utf-8",
    )
    (local_root / "detection" / "signals.yaml").write_text(
        "schema-version: 1\nsignals: []\nthreshold: 0.5\n", encoding="utf-8"
    )


def _write_ignored_signals(project_root: Path, orphans: list[OrphanSignal]) -> None:
    """Grava `.claude/inventory/ignored-signals.yaml` versionado."""
    inv = project_root / ".claude" / "inventory"
    inv.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema-version": 1,
        "generated-by": "feature-forge init Step 7.5",
        "ignored": [
            {
                "signal_id": o.signal_id,
                "suggested_capability": o.suggested_capability,
                "source": o.source,
                "hit_count": o.hit_count,
            }
            for o in orphans
        ],
    }
    (inv / "ignored-signals.yaml").write_text(
        _yaml_lib.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _today_iso_for_init() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).date().isoformat()
```

- [ ] **Step 3: Hook Step 7.5 entre Step 7 e Step 8**

Edit `engine/init.py`. Localize o bloco `# ── Step 7 — Snapshot cards ────...` (linha ~710) e `# ── Step 8 — Merge contributions ────...` (linha ~728). Insira ENTRE eles:

```python
    checkpoint.step = "step-7-5-orphan-signals"
    checkpoint.at = _utc_now_iso()
    _save_checkpoint(checkpoint)

    # ── Step 7.5 — Orphan signal handling (Gap 5) ───────────────────────────
    from validators._common import load_catalog as _load_overlay_catalog
    try:
        overlay_catalog = _load_overlay_catalog(project_root)
    except Exception as exc:  # noqa: BLE001
        renderer.write(
            renderer.colored(
                f"warn: catálogo overlay inválido ({exc}); seguindo com canon-only", "yellow"
            )
        )
        overlay_catalog = None

    if overlay_catalog is not None:
        orphans = _check_orphan_signals(project_root, activated, overlay_catalog)
        if orphans:
            decision = _surface_three_paths(orphans, project_root=project_root)
            if decision.choice == "abort":
                return decision.exit_code
            if decision.choice == "adr-required":
                renderer.write(
                    renderer.colored(
                        f"⚠️  {decision.note} Init suspenso — re-run após promoção.",
                        "yellow",
                    )
                )
                return 7
            # "create-local" ou "ignore" → segue pra Step 8 com catálogo expandido
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
pytest tests/unit/test_init_orphan_signals.py -v
```

Expected: 12 passed (6 da Task 10 + 6 desta).

- [ ] **Step 5: Smoke — confirma que init principal ainda compila**

```bash
python -c "import engine.init; print('init imports ok')"
```

Expected: `init imports ok` sem ImportError.

- [ ] **Step 6: Commit**

```bash
git add engine/init.py tests/unit/test_init_orphan_signals.py
git commit -m "feat(init): Step 7.5 orphan-signal 3-paths with reservada edge"
```

---

## Fase G — Wrap-up

## Task 12: E2E integration test — pilot scenario com card local

**Files:**
- Create: `tests/integration/test_e2e_local_card_pilot.py`

- [ ] **Step 1: Write `tests/integration/test_e2e_local_card_pilot.py` (full content)**

Create `tests/integration/test_e2e_local_card_pilot.py`:

```python
"""E2E integration — local card overlay pilot scenario.

Reproduz o fluxo do projeto-alvo (KMP Android+iOS) onde uma stack
exótica é mitigada via card local antes do canon ter cobertura.

Cenário simulado:
  1. `tmp_project` com signal `import com.retrofit-mock.client` em build.gradle.kts
     (usamos um stub `retrofit-mock` como needle pra exercitar overlay sem
     depender do próprio card retrofit-client que está sendo shippado nesta entrega).
  2. Loader cascade não acha nenhum card cobrindo o needle.
  3. Step 7.5 detecta orphan → user escolhe caminho 1 → cria card local.
  4. Re-detection match → card local ativa.
  5. `forge verify` cascade verde.

Marker: integration (slow). Excluído da rapid CI lane.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from engine.cards import CardConflictError
from engine.cards.loader import load_all_cards

pytestmark = pytest.mark.integration


@pytest.fixture
def pilot_project(tmp_path: Path) -> Path:
    """Project com signal `retrofit-mock` que NÃO está em nenhum card canon."""
    proj = tmp_path / "pilot"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "cards").mkdir(parents=True)
    (proj / ".claude" / "inventory").mkdir(parents=True)

    # Material que dispara um signal customizado
    app_kt = proj / "app" / "src" / "main" / "kotlin" / "App.kt"
    app_kt.parent.mkdir(parents=True, exist_ok=True)
    app_kt.write_text(
        "package app\n\nimport com.retrofit_mock.client.MockClient\n", encoding="utf-8"
    )

    return proj


def _write_canon_card(project: Path, name: str, provides: list[str]) -> None:
    card_dir = project / ".claude" / "cards" / name
    card_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "schema-version": 1,
        "identity": {
            "name": name,
            "version": "1.0.0",
            "description": "Canon stub for E2E",
            "category": "kmp",
            "maturity": "stable",
        },
        "provides": provides,
        "requires": [],
        "conflicts-with": [],
        "detection": {"signals": [], "threshold": 0.5},
    }
    (card_dir / "card.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    (card_dir / "README.md").write_text("# canon\n", encoding="utf-8")


def _write_local_card_covering_mock(project: Path) -> None:
    card_dir = project / ".claude" / "cards" / "local" / "retrofit-mock-local"
    card_dir.mkdir(parents=True, exist_ok=True)
    (card_dir / "detection").mkdir(parents=True, exist_ok=True)
    data = {
        "schema-version": 1,
        "identity": {
            "name": "retrofit-mock-local",
            "version": "0.1.0",
            "description": "Local card cobrindo retrofit-mock (E2E pilot)",
            "category": "network",
            "maturity": "experimental",
        },
        "provides": ["kotlin-multiplatform"],  # label canon válida (placeholder)
        "requires": [],
        "conflicts-with": [],
        "detection": {
            "signals": [
                {
                    "type": "file-content",
                    "glob": "**/*.kt",
                    "contains": "com.retrofit_mock.client",
                    "confidence": 0.6,
                }
            ],
            "threshold": 0.5,
        },
    }
    (card_dir / "card.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    (card_dir / "README.md").write_text("# local\n", encoding="utf-8")
    (card_dir / "detection" / "signals.yaml").write_text(
        "schema-version: 1\nsignals: []\nthreshold: 0.5\n", encoding="utf-8"
    )


def test_pilot_canon_only_loads_without_local(pilot_project):
    """Sanity: canon-only sem local lê sem erro."""
    _write_canon_card(pilot_project, "kotlin-base", ["kotlin"])
    manifests = load_all_cards(pilot_project)
    names = {m.name for m in manifests}
    assert "kotlin-base" in names


def test_pilot_local_card_added_appears_in_cascade(pilot_project):
    """Após criar local, cascade retorna canon + local."""
    _write_canon_card(pilot_project, "kotlin-base", ["kotlin"])
    _write_local_card_covering_mock(pilot_project)
    manifests = load_all_cards(pilot_project)
    by_origin = {(m.name, m.origin) for m in manifests}
    assert ("kotlin-base", "canon") in by_origin
    assert ("retrofit-mock-local", "local") in by_origin


def test_pilot_local_cards_manifest_written(pilot_project):
    _write_canon_card(pilot_project, "kotlin-base", ["kotlin"])
    _write_local_card_covering_mock(pilot_project)
    load_all_cards(pilot_project)
    manifest_path = pilot_project / ".claude" / "inventory" / "local-cards-manifest.yaml"
    assert manifest_path.is_file()
    parsed = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    names = {c["name"] for c in parsed.get("local-cards") or []}
    assert "retrofit-mock-local" in names


def test_pilot_canon_local_collision_hard_fails(pilot_project):
    """Workaround Approach A: nome colidindo é hard fail."""
    _write_canon_card(pilot_project, "kotlin-base", ["kotlin"])
    # cria local com nome IGUAL ao canon → CardConflictError
    canon_root = pilot_project / ".claude" / "cards"
    collide_local = canon_root / "local" / "kotlin-base"
    collide_local.mkdir(parents=True)
    data = {
        "schema-version": 1,
        "identity": {
            "name": "kotlin-base",
            "version": "0.1.0",
            "description": "collision attempt",
            "category": "kmp",
            "maturity": "experimental",
        },
        "provides": ["kotlin"],
        "requires": [],
        "conflicts-with": [],
    }
    (collide_local / "card.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    (collide_local / "README.md").write_text("# c\n", encoding="utf-8")
    with pytest.raises(CardConflictError):
        load_all_cards(pilot_project)


def test_pilot_orphan_to_local_flow_endtoend(pilot_project, monkeypatch):
    """Fluxo completo: orphan detectado → cria local inline → re-detection cobre."""
    from engine.init import (
        _check_orphan_signals,
        _card_local_add_inline,
        OrphanSignal,
    )

    class _Cat:
        reserved = frozenset()

    # passo 1: sem cards locais nem canon cobrindo, mock orphan
    orphan = OrphanSignal(
        signal_id="orphan:com.retrofit_mock.client",
        source="detected in 1 file(s)",
        suggested_capability="kotlin-multiplatform",
        is_reserved=False,
        hit_count=1,
    )

    # passo 2: cria local inline (Step 7.5 caminho 1)
    _card_local_add_inline(pilot_project, orphan)

    created = pilot_project / ".claude" / "cards" / "local" / "kotlin-multiplatform"
    # _card_local_add_inline nomeia com a capability — confirma existência
    assert created.is_dir()
    assert (created / "card.yaml").is_file()

    # passo 3: cascade load confirma que card local entrou
    manifests = load_all_cards(pilot_project)
    by_origin = {(m.name, m.origin) for m in manifests}
    assert ("kotlin-multiplatform", "local") in by_origin
```

- [ ] **Step 2: Run integration test**

```bash
pytest tests/integration/test_e2e_local_card_pilot.py -v -m integration
```

Expected: 5 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_e2e_local_card_pilot.py
git commit -m "test(e2e): local card overlay pilot scenario"
```

---

## Task 13: Doc-sync — 9 arquivos

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/design/01-decisions.md`
- Modify: `docs/design/04-pending.md`
- Modify: `docs/design/05-filesystem-layout.md`
- Modify: `docs/design/07-discipline.md`
- Modify: `docs/design/08-session-handoff.md`
- Modify: `docs/schemas/card.md` (confirma Task 1 — adiciona linha CARD-019 na tabela)
- Modify: `docs/schemas/capability-labels.md`
- Modify: `README.md`

- [ ] **Step 1: `CHANGELOG.md` — entrada em `## [Unreleased]` `### Added`**

Adicione ao topo de `## [Unreleased]` → `### Added`:

```markdown
- **Gap 5 resolvido — Card local overlay (Approach A)** —
  `.claude/cards/local/<name>/` versionado no projeto consumidor, lido via
  loader cascade canon ∪ local com hard-fail em colisão. Valida via
  `validate_card_yaml` (canon/local discrimination por path resolved) +
  `validate_capability_labels` (overlay-aware via `validators/_common.load_catalog`).
  Reconfigure ganha submenu `card-local` (listar/adicionar/remover). Init
  ganha Step 7.5 com 3-caminhos pra signals órfãos (criar local / ignorar /
  abortar). Edge case: orphan em label reservada vira "abrir ADR".
- **Cards canon novos:** `retrofit-client` (provê `http-client`) e
  `shared-preferences-prefs` (provê `local-prefs-storage` legacy com
  `legacy-marker: true`). 20 → 22 cards canon.
- **Schema bump aditivo:** novo campo top-level opcional `legacy-marker: bool`
  no `card.yaml` (default false). `schema-version` permanece `1`.
- Nova exception `CardConflictError` em `engine.cards`.
- Nova validação `CARD-019` (legacy-marker, if present, must be bool).
```

- [ ] **Step 2: `docs/design/01-decisions.md` — ADR APPEND**

Adicione UMA LINHA NOVA à tabela de decisões (não delete linha alguma). A próxima decisão livre é N+1 onde N é a maior existente. Use o protocolo da `.claude/rules/decisions.md` — APPEND. Linha:

```markdown
| 28 | Card local overlay (Approach A) | `.claude/cards/local/<name>/` versionado no projeto consumidor. Cascade canon ∪ local com hard-fail em colisão de nome. Sem merge silencioso, sem override. `legacy-marker: bool` é campo aditivo opcional (schema-version permanece 1). Capability labels overlay vive em `.claude/inventory/capability-labels.local.yaml` com guards: sem `overrides`, sem `reserved-promotions`, sem colisão com canon ativo. | 2026-06-02 |
```

Se `01-decisions.md` usa formato diferente (lista numerada em vez de tabela), espelhe o padrão local.

- [ ] **Step 3: `docs/design/04-pending.md` — riscar Gap 5**

Localize o bloco "Gap 5 — Cenário D2: Stack fora do catálogo" e marque como resolvido. Mantenha histórico:

```markdown
### Gap 5 — Cenário D2: Stack fora do catálogo ✅ RESOLVIDO em 2026-06-02

**Status:** Entregue via plan
`docs/superpowers/plans/2026-06-02-gap5-card-local-overlay.md`. Approach A
(cascade simples). 13 tasks, ~1910 LOC.

Gaps parcialmente destravados como side-effect:
- **Gap 9** (catálogo evolutivo): overlay dá caminho oficial pra labels
  ainda não promovidas.
- **Gap 14** (preset coverage): preset canônico errado fica mitigável via
  card local enquanto preset novo não é shipado.
```

- [ ] **Step 4: `docs/design/05-filesystem-layout.md` — adicionar `.claude/cards/local/`**

Localize o bloco que descreve `.claude/cards/`. Adicione a sub-árvore:

```markdown
.claude/
├── cards/
│   ├── <canon-card-name>/        ← snapshot canon (sha256 em workflow-config)
│   └── local/                    ← overlay versionado (Gap 5)
│       └── <local-card-name>/
│           ├── card.yaml
│           ├── README.md
│           └── detection/signals.yaml
├── inventory/
│   ├── capability-labels.yaml         (snapshot canon)
│   ├── capability-labels.local.yaml   ← overlay (Gap 5)
│   ├── local-cards-manifest.yaml      ← gerado pelo loader (Gap 5)
│   └── ignored-signals.yaml           ← gerado pelo init Step 7.5 (Gap 5)
└── ...
```

- [ ] **Step 5: `docs/design/07-discipline.md §2` — nota validators overlay-aware**

Localize seção `## 2. Validator cascade — fail-fast por default`. Adicione parágrafo curto:

```markdown
**Overlay-awareness (Gap 5):** `validate_card_yaml` e `validate_capability_labels`
são overlay-aware desde 2026-06-02 — catálogo efetivo é canon ∪ local. Loader
helper `validators/_common.load_catalog(project_root)` aplica guards
(promoção-reservada, colisão-canon, chaves proibidas) numa única passada.
Validators downstream consomem o resultado sem precisar repetir guards.
```

- [ ] **Step 6: `docs/design/08-session-handoff.md` — atualizar campos canônicos**

Localize as primeiras linhas do arquivo. Edite:

```markdown
**Última atualização:** 2026-06-02 (v1.X.Y — Gap 5 card local overlay)
**Estado:** Gap 5 entregue (overlay + 2 cards canon + Step 7.5). Próximo:
revisitar Gap 9 (catálogo evolutivo) à luz do overlay.
```

E acrescente ao final de `§Conhecidos limites` (ou crie a seção se ausente):

```markdown
- **Card local re-prompt** — fluxo `_card_local_add` em colisão de nome
  oferece 3-caminhos (rename / abort / listar) mas o "rename" não reabre
  o prompt do nome — encerra a operação. Gap pra v1.2; documentado em
  `docs/design/04-pending.md`.
```

- [ ] **Step 7: `docs/schemas/card.md` — confirmar CARD-019 na tabela de Validação**

Edit `docs/schemas/card.md`. Localize a tabela `## Validation of card.yaml` (linha ~454). Adicione linha:

```text
CARD-019  legacy-marker, if present, must be bool (top-level, default false)
```

- [ ] **Step 8: `docs/schemas/capability-labels.md` — seção "Local overlay"**

Adicione no final do arquivo:

```markdown
## Local overlay (since v1.X — Gap 5)

Projetos consumidores podem estender o catálogo via
`.claude/inventory/capability-labels.local.yaml`. Schema enxuto:

```yaml
schema_version: 1
added:
  - name: feature-flag-remote
    description: >
      Capability local pra cobrir LaunchDarkly + Firebase Remote Config
      sem precisar promoção ao canon.
    target-platforms: [android, ios]
```

**Regras (validador rejeita):**

- `overrides:` proibido — overlay NÃO redefine canon
- `reserved-promotions:` proibido — promoção exige ADR no canon
- Label local ∈ canon ativo → colisão (hard fail)
- Label local ∈ canon reservadas → "promoção exige ADR"

Detalhe operacional: `validators/_common.load_catalog(project_root)` aplica
todos os guards numa única passada; validators downstream consomem o resultado.
```

- [ ] **Step 9: `README.md` — atualizar §Stats**

Edit `README.md`. Localize a seção `## Stats` (ou equivalente) e atualize:

```markdown
- Cards canônicos: 22 (era 20 em v1.1)
- Overlay de cards locais: `.claude/cards/local/<name>/` (Gap 5)
- Validators: 14 (sem mudança em count; 2 ganham overlay-awareness)
```

- [ ] **Step 10: Run full suite pra confirmar zero regressão**

```bash
pytest -m "not integration and not e2e" 2>&1 | tail -10
```

Expected: all green, count >= baseline + ~30. Se algum test falhar, vá ao test específico — não tente fix-forward acrescentando mais código aqui.

- [ ] **Step 11: Smoke-validate o repo da forge inteiro**

```bash
./bin/forge --version
forge verify 2>&1 | tail -5
```

Expected: CLI vivo, validators cascade verde. Se `forge verify` falhar com `capability-labels.local.yaml` not found: confirma que overlay é opcional (load_catalog retorna canon-only quando ausente — comportamento implementado em Task 6).

- [ ] **Step 12: Commit final**

```bash
git add CHANGELOG.md docs/design/01-decisions.md docs/design/04-pending.md \
        docs/design/05-filesystem-layout.md docs/design/07-discipline.md \
        docs/design/08-session-handoff.md docs/schemas/card.md \
        docs/schemas/capability-labels.md README.md
git commit -m "docs(sync): Gap 5 — card local overlay (9 docs synced)"
```

---

## Self-check final (não é Task, é verificação humana após Task 13)

Antes de fechar a sessão e abrir PR:

1. **Count de tests:**
   ```bash
   pytest --collect-only -q 2>/dev/null | tail -1
   ```
   Expected: >= baseline + 30 (ajuste real fica claro após Task 12).

2. **Smoke checklist 5/5:** rode `.claude/rules/SMOKE-CHECKLIST.md` manualmente.

3. **`forge doctor` verde:**
   ```bash
   forge doctor
   ```

4. **Bootstrap idempotente:**
   ```bash
   bash .claude/bootstrap.sh && bash .claude/bootstrap.sh && git status --porcelain
   ```
   Expected: segunda invocação sem diff novo.

5. **Confere o histórico:**
   ```bash
   git log --oneline -15
   ```
   Expected: 13 commits ordenados (Tasks 1→13) com mensagens canônicas
   `<tipo>(<escopo>): <descrição>`.

Se 5/5 passa, PR está pronto pra review. Se algum item falha, debug
no item específico antes de abrir review — não dispatch revisor com
gate vermelho.
