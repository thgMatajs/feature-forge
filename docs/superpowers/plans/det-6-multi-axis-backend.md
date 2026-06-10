# PLAN — DET-6: Multi-axis backend (8 waves)

**Spec:** [`docs/superpowers/specs/det-6-multi-axis-backend.md`](../specs/det-6-multi-axis-backend.md)
**Phase:** B — sequencial após Phase A (DRIFT-1).
**Voz:** mentor calmo.

---

## Goal

Materializar o multi-axis backend model (8 axes, platform-keyed cells, status enum, 4 bundles, 6 cards novos) em 8 waves. W1-W6 são paralelizáveis com Phase A; W7 bloqueia até Phase A entregar AskUserQuestion intent protocol; W8 fecha doc-sync + verify cascade.

## Architecture sketch

Módulos novos:

- `engine/detection/composer.py` — per-(axis, platform) composer (W5).
- `engine/detection/__init__.py` — package marker.
- `presets/kmp-mobile/bundles/` — bundle YAML files (W6).

Módulos modificados:

- `engine/init.py` — substitui `_handle_backend_candidates` (linha ~979) + adiciona orquestração do composer + bundle picker + per-axis prompts (W7).
- `engine/reconfigure.py` — substitui `_handle_backend` (linha ~1108) por submenu "backend axes" multi-cell (W7).
- `engine/cards/loader.py` — schema validations: aceita 3 categorias novas (analytics, notifications, flags); remove enforcement de labels singulares deprecated (W3).
- `engine/cards/resolver.py` — se houver lógica baseada em singular labels removidas, atualiza (W3).
- `cards/*/card.yaml` (~15-20 arquivos) — renames de `identity.category` (W2) + remove labels singulares (W3).
- `docs/schemas/card.md` — cell shape + categories enum + remove referências legacy (W1).
- `docs/schemas/workflow-config.md` — bloco `backend:` multi-axis (W1).
- `docs/schemas/backend-axes.md` — **NEW** taxonomia (W1).

Sequência canônica de waves (com dependências):

```
W1 (schemas)           ──┐
W2 (category cleanup)  ──┤
W3 (label refactor)    ──┼── paralelizáveis com Phase A (drift-1)
W4 (6 new cards)       ──┤
W5 (composer)          ──┤  (depende de W2 + W3 — categories + labels limpas)
W6 (bundles)           ──┘

W7 (init + reconfigure UX) ── BLOCKED até Phase A shippar AskUserQuestion intent

W8 (doc-sync + verify + final) ── BLOCKED até todas as anteriores
```

---

## Reuse-first evidence

Antes de propor helpers novos, evidência de reuso (consulta `forge graph` + `engine/inventory/` + grep — Mandamento #3):

1. **`engine/cards/loader.py:354`** — único consumer de `card.yaml` em runtime; extend, NÃO replace. Sub-tasks de W2/W3/W5 mexem no loader pra aceitar categorias novas + remover enforcement de labels deprecated.

2. **`engine/init.py:_eval_detection_signals` + `_eval_gradle_dep`** — parsers de signals JÁ EXISTEM. Composer (W5) compose esses parsers per-(axis, platform) — não reimplementa parsing.

3. **`engine/init.py:_handle_backend_candidates` (linha ~979)** — função monolítica que será **substituída** por orquestração composer + bundle picker. Lógica de leitura do `backend-candidates` é deletada inteira (decision-tree fundamentalmente diferente). Comportamento de "perguntar qual backend" muda de "escolher 1 bundle" para "compose 8 axes".

4. **`engine/reconfigure.py:_handle_backend`** — handler monolítico de backend swap. Será **substituído** por submenu axes-cells. Pattern de backup `.bak` + history entry + sha256 update é REUSADO (mesma disciplina dos outros handlers de reconfigure).

5. **`engine/qa/checkpoint.py`** — checkpoint pattern entre prompts em pipelines longos. Plan-auditor mencionou Phase A como reuse-first candidate; init multi-prompt flow (~5-8 perguntas no brownfield) é candidato a usar mesmo pattern se Phase A não cobrir state-between-prompts.

6. **DET-3 audit JSON pattern** (`.planning/det-3/migration-audit.json`) — mesmo pattern reusado em W2 (`.planning/det-6/category-migration-audit.json`) e W3 (`.planning/det-6/label-refactor-audit.json`). Sem inventar formato novo.

7. **Card structure** (`cards/<name>/{card.yaml,README.md,detection/signals.yaml,templates/}`) — 6 cards novos em W4 seguem **exatamente** o pattern dos 22 cards existentes. Sub-task de W4 começa lendo card existente análogo (`firebase-auth` pra `firebase-analytics`; `firestore-persistence` pra `firebase-remote-config`) e fork-and-adapt.

8. **Bundle YAML schema** — bundles novos em W6 (`presets/kmp-mobile/bundles/*.yaml`) seguem padrão consistente com `presets/kmp-mobile/preset.yaml` (schema-version, identity, defaults). Não inventa novo formato; reusa pattern existente.

9. **`validators/validate_card_yaml.py`** — wrapper CARD-001..020 existe. W2/W3/W4 confiam que esse validator pega regressions. Validator gets minor extensions em W1 pra aceitar categorias novas; lógica core preserved.

10. **AskUserQuestion (Phase A) — explicit reuse** — W7 consome o intent protocol que Phase A entrega. Não reimplementa prompt UX; consome API canônica.

---

## Wave-by-wave tasks

### W1 — Schema docs (paralelizável com Phase A)

**Goal:** docs/schemas fica fonte-de-verdade do novo modelo antes de qualquer YAML/Python tocar.

**Justificativa load-bearing:** W1 toca `docs/schemas/card.md` (whitelist load-bearing). Justificativa: schema é coluna vertebral do projeto; mudança aqui é canônica e intencional (Mandamento #4 — escopo dentro de DET-6).

#### W1.1 — Cria `docs/schemas/backend-axes.md`

- **Files:**
  - `docs/schemas/backend-axes.md` (NEW)
- **Steps:**
  1. Documenta 8 axes (data/auth/observability/analytics/storage/persistence/notifications/flags) com 1 parágrafo cada explicando boundary.
  2. Naming rationale: "auth" vs "identity" (colisão com top-level `identity:` no workflow-config).
  3. Cell object schema completo: campos `card`, `status`, `migrating-to` + tipos + obrigatoriedade.
  4. Status enum semantics: active / migrating-to / deprecated (com casos de uso explícitos).
  5. Cross-references: `docs/schemas/card.md`, `docs/schemas/workflow-config.md`.
- **AC coverage:** AC-1.
- **Verification:** `wc -l docs/schemas/backend-axes.md > 0`; manual review.

#### W1.2 — Atualiza `docs/schemas/card.md`

- **Files:**
  - `docs/schemas/card.md`
- **Steps:**
  1. CARD-004 (`identity.category must be in known categories`) — atualiza lista de categories enumerated. Adiciona: `analytics, notifications, flags`. Remove `backend` e `network` (eles foram split). Confirma preservados: `language, kmp, ui, navigation, dependency-injection, persistence, observability, auth, storage, data, testing, build, design-system, ticketing`.
  2. Adiciona seção "Backend axes — when `identity.category` is an axis" referenciando `backend-axes.md`.
  3. Adiciona campo opcional `identity.platforms: [android, ios, kmp]` ao schema (se ainda não existir) — composer consome esse campo em W5. **Open implementation detail #8** documented inline com nota "default ausente = card aplicável a todas as plataformas ativas".
- **AC coverage:** AC-1, AC-9.
- **Verification:** `validate_card_yaml.py` é re-run em todos os cards após W2 e passa.

#### W1.3 — Atualiza `docs/schemas/workflow-config.md`

- **Files:**
  - `docs/schemas/workflow-config.md`
- **Steps:**
  1. Remove referências a `identity.backend-choice`.
  2. Remove referências a `backend.provider` (string monolítico).
  3. Adiciona seção §"backend (multi-axis)" com shape completo: `backend.<axis>.<platform>` → cell-object | null.
  4. Cross-references: `backend-axes.md`, `card.md`.
- **AC coverage:** AC-2.

#### W1.4 — Anota Open implementation details inline

- **Files:**
  - `docs/schemas/card.md` (apenas comentários estruturados)
  - `docs/schemas/backend-axes.md`
- **Steps:**
  1. Pra cada Open implementation detail (1-8 listado no SPEC), adiciona comentário inline `<!-- open-detail #N: <descrição curta + default escolhido> -->` no doc relevante.
- **Verification:** `grep -c "open-detail" docs/schemas/{card,backend-axes,workflow-config}.md` ≥ 6.

---

### W2 — Category cleanup (paralelizável com Phase A)

**Goal:** todos os cards têm `identity.category` alinhado com 8 axes ou stack/tooling preservados.

**Justificativa load-bearing:** W2 toca `cards/**` (whitelist load-bearing). Justificativa: categorias são fonte-de-verdade pra detection composer (W5) — sem alinhamento, composer não funciona. Mudança canônica dentro de DET-6.

#### W2.1 — Audit current state

- **Files:**
  - `.planning/det-6/category-migration-audit.json` (NEW — auxiliar, não em FILE BUDGET; agente decide se materializa como artifact ou inline em commit body)
- **Steps:**
  1. `grep -E "^\s*category:" cards/*/card.yaml > audit-raw.txt`.
  2. Build JSON: `{ card-name: { current: <cat>, proposed: <cat>, reason: <txt> } }`.
  3. Persiste em `.planning/det-6/` pra rastreabilidade.

#### W2.2 — Rename `backend` cards by axis

- **Files (9 cards):**
  - `cards/firebase-auth/card.yaml`
  - `cards/auth-jwt-bearer/card.yaml`
  - `cards/firebase-storage/card.yaml`
  - `cards/firestore-persistence/card.yaml`
  - `cards/firestore-realtime/card.yaml`
  - `cards/firestore-security-rules/card.yaml`
  - `cards/rest-api-contract/card.yaml`
  - `cards/retrofit-client/card.yaml`
  - `cards/ktor-client/card.yaml`
- **Steps:**
  1. Pra cada card, atualiza `identity.category` conforme mapping no SPEC §"identity.category cleanup".
  2. Last-updated bump na linha `last-updated:`.
- **AC coverage:** AC-9.
- **Verification:** `grep "category: backend\|category: network" cards/*/card.yaml` retorna VAZIO.

#### W2.3 — Update `engine/cards/loader.py` schema validation

- **Files:**
  - `engine/cards/loader.py`
- **Steps:**
  1. **TDD red:** adicionar test em `tests/validators/test_cards_loader.py` que carrega card com `category: analytics` (categoria nova) — confirma FAIL antes de impl.
     - Pytest: `pytest tests/validators/test_cards_loader.py::test_loader_accepts_analytics_category -xvs`.
  2. **TDD green:** atualizar lista enumerated de categories em `engine/cards/loader.py` (CARD-004 validation) pra incluir `analytics, notifications, flags, data, auth, observability, storage, persistence`. Remove `backend, network`.
  3. Re-run test → PASS.
- **AC coverage:** AC-9.
- **Verification:** `pytest tests/validators/test_cards_loader.py` green.

#### W2.4 — Run validator cascade

- **Files:** N/A (verification step)
- **Steps:**
  1. `forge verify` (15 validators cascade).
  2. Especialmente `validate_card_yaml.py` em todos os 22 cards.
  3. Esperado: green.
- **Verification:** `forge verify` exit 0.

---

### W3 — Label refactor (paralelizável com Phase A; depende W2 logicamente — categories alinhadas antes de labels)

**Goal:** singular labels (`auth-provider`, `http-client`, `crash-reporting`) removidas das `provides:` dos cards; engine não enforça mais.

**Justificativa load-bearing:** W3 toca `cards/**` + `engine/cards/loader.py` (chokepoint). Justificativa: schema novo enforça cardinalidade per-cell, então labels singulares são redundantes; remoção é canônica.

#### W3.1 — Audit current state

- **Files:**
  - `.planning/det-6/label-refactor-audit.json` (NEW auxiliar)
- **Steps:**
  1. `grep -rn "auth-provider\|http-client\|crash-reporting\|auth-token-bearer" cards/*/card.yaml`.
  2. Identifica engine references: `grep -rn "auth-provider\|http-client\|crash-reporting" engine/`.
  3. Persiste audit JSON.
- **Verification:** audit JSON listing complete.

#### W3.2 — Remove singular labels from card.yaml files

- **Files (cards afetados — confirm via grep, lista esperada):**
  - `cards/firebase-auth/card.yaml` (remove `auth-provider`, mantém outros)
  - `cards/auth-jwt-bearer/card.yaml`
  - `cards/ktor-client/card.yaml` (remove `http-client`)
  - `cards/retrofit-client/card.yaml`
  - `cards/crashlytics/card.yaml` (remove `crash-reporting`)
- **Steps:**
  1. Pra cada card, edita `provides:` removendo a label singular.
  2. `conflicts-with:` também pode referenciar essas labels — remove referências (sem mais singular labels, sem conflito explícito).
- **AC coverage:** AC-10.
- **Verification:** `grep "auth-provider\|http-client\|crash-reporting" cards/*/card.yaml` retorna VAZIO.

#### W3.3 — Update engine

- **Files:**
  - `engine/cards/loader.py`
  - `engine/cards/resolver.py` (se houver lógica baseada em labels removidas)
  - `docs/schemas/capability-labels.md` (load-bearing — justificativa: catalog é canônico, atualizá-lo é parte do DET-6)
- **Steps:**
  1. **TDD red:** test em `tests/validators/test_cards_resolver.py` que tenta resolver projeto com 2 cards proveendo `auth-provider` (cenário legacy) — agora deve PASSAR (não há mais conflito porque label removida).
  2. **TDD green:** remove enforcement de singular labels em `engine/cards/loader.py` + `resolver.py`.
  3. Atualiza `docs/schemas/capability-labels.md` marcando `auth-provider`, `http-client`, `crash-reporting` como **removed in v1.2 — superseded by schema enforcement** (mantém histórico, não deleta inteiro — Decision 22 audit-trail).
- **AC coverage:** AC-10.
- **Verification:** `pytest tests/validators/test_cards_loader.py tests/validators/test_cards_resolver.py` green; `forge verify` green.

---

### W4 — 6 cards novos (paralelizável com Phase A; depende W1 — schema novo aceita categorias novas)

**Goal:** 6 novos cards criados com `card.yaml` + `signals.yaml` + `README.md` + templates stubs.

**Justificativa load-bearing:** W4 cria novos diretórios em `cards/**` (whitelist load-bearing). Justificativa: novas capabilities canônicas (analytics, notifications, flags) que SPEC define.

**Reuse-first evidence:** cada card é fork-and-adapt do card existente análogo (`firebase-auth` → `firebase-analytics`; `firestore-persistence` → `firebase-remote-config`; etc.). Antes de criar arquivo novo, lê o análogo + grep `cards/*/card.yaml` por padrões similares.

#### W4.1 — `firebase-analytics`

- **Files:**
  - `cards/firebase-analytics/card.yaml`
  - `cards/firebase-analytics/README.md`
  - `cards/firebase-analytics/detection/signals.yaml`
  - `cards/firebase-analytics/templates/firebase-analytics-tech-spec.md` (stub minimal)
  - `tests/validators/test_firebase_analytics_detection.py` (NEW)
  - `tests/fixtures/firebase-analytics-positive/` (fixture project NEW)
- **Steps:**
  1. **RED:** Write failing detection/validation test FIRST in
     `tests/validators/test_firebase_analytics_detection.py`:
     - Create fixture project at `tests/fixtures/firebase-analytics-positive/` com
       `build.gradle` contendo `com.google.firebase:firebase-analytics` + `google-services.json`
       stub matching signals.yaml.
     - Assert `_eval_gradle_dep(...)` retorna match esperado para o fixture.
     - Assert `validate_card_yaml("cards/firebase-analytics/card.yaml")` retorna zero
       violations (vai FALHAR — card ainda não existe).
     - Run `pytest tests/validators/test_firebase_analytics_detection.py -xvs` → confirma FAIL.
  2. Lê `cards/firebase-auth/card.yaml` como template (reuse-first).
  3. Cria `cards/firebase-analytics/card.yaml` com `identity.category: analytics`,
     `identity.platforms: [android, ios]` (KMP shared não tem analytics nativo).
     - `provides: [analytics-events]` (label NÃO singular — é descritivo apenas).
     - `requires: [firebase-platform]` (analog ao firestore).
  4. Cria `detection/signals.yaml`: `gradle-dep com.google.firebase:firebase-analytics`
     (conf 0.5) + `file-content google-services.json` (conf 0.3) + `file-content import
     com.google.firebase.analytics` (conf 0.2). Threshold 0.5.
  5. Cria README minimal: 1 parágrafo identity + link pra `docs/schemas/backend-axes.md`.
  6. Cria template stub: 1 seção `Analytics events` com placeholder.
  7. **GREEN:** Re-run `pytest tests/validators/test_firebase_analytics_detection.py -xvs`
     → confirma PASS.
- **AC coverage:** AC-4.
- **Verification:** `validate_card_yaml.py cards/firebase-analytics/` green; pytest
  passa.

#### W4.2 — `posthog-analytics`

- **Files (analog ao W4.1):**
  - `cards/posthog-analytics/card.yaml`
  - `cards/posthog-analytics/README.md`
  - `cards/posthog-analytics/detection/signals.yaml`
  - `cards/posthog-analytics/templates/posthog-analytics-tech-spec.md`
  - `tests/validators/test_posthog_analytics_detection.py` (NEW)
  - `tests/fixtures/posthog-analytics-positive/` (fixture project NEW)
- **Steps:**
  1. **RED:** Write failing detection/validation test FIRST em
     `tests/validators/test_posthog_analytics_detection.py`:
     - Cria fixture project em `tests/fixtures/posthog-analytics-positive/` com signals
       matching (`gradle-dep com.posthog:posthog-android` + `file-content import
       com.posthog.android`).
     - Assert `_eval_gradle_dep(...)` retorna match esperado.
     - Assert `validate_card_yaml("cards/posthog-analytics/card.yaml")` retorna zero
       violations (vai FALHAR).
     - Run pytest → confirma FAIL.
  2. Cria `cards/posthog-analytics/card.yaml` + `detection/signals.yaml` + README minimal +
     template stub. Categoria `analytics`, platforms `[android, ios]`, fork-and-adapt do
     `cards/firebase-analytics/` (reuse-first análogo via W4.1).
  3. Detection: `gradle-dep com.posthog:posthog-android` + `file-content import
     com.posthog.android`.
  4. **GREEN:** Re-run pytest → confirma PASS.
- **AC coverage:** AC-4.
- **Verification:** `validate_card_yaml.py cards/posthog-analytics/` green; pytest passa.

#### W4.3 — `fcm` (Firebase Cloud Messaging)

- **Files:**
  - `cards/fcm/card.yaml` (category: `notifications`, platforms: `[android, ios]`)
  - `cards/fcm/README.md`
  - `cards/fcm/detection/signals.yaml`
  - `cards/fcm/templates/fcm-tech-spec.md`
  - `tests/validators/test_fcm_detection.py` (NEW)
  - `tests/fixtures/fcm-positive/` (fixture project NEW)
- **Steps:**
  1. **RED:** Write failing detection/validation test FIRST em
     `tests/validators/test_fcm_detection.py`:
     - Cria fixture project em `tests/fixtures/fcm-positive/` com signals matching
       (`gradle-dep com.google.firebase:firebase-messaging` + `file-content
       "FirebaseMessagingService"`).
     - Assert `_eval_gradle_dep(...)` + `_eval_file_content(...)` retornam matches
       esperados.
     - Assert `validate_card_yaml("cards/fcm/card.yaml")` zero violations (vai FALHAR).
     - Run pytest → confirma FAIL.
  2. Cria `cards/fcm/card.yaml` (category `notifications`, platforms `[android, ios]`,
     `requires: [firebase-platform]`) + `detection/signals.yaml` + README minimal +
     template stub. Reuse-first análogo a `cards/firebase-auth/`.
  3. **GREEN:** Re-run pytest → confirma PASS.
- **AC coverage:** AC-4.
- **Verification:** `validate_card_yaml.py cards/fcm/` green; pytest passa.

#### W4.4 — `onesignal`

- **Files:**
  - `cards/onesignal/card.yaml` (category: `notifications`)
  - `cards/onesignal/README.md`
  - `cards/onesignal/detection/signals.yaml`
  - `cards/onesignal/templates/onesignal-tech-spec.md`
  - `tests/validators/test_onesignal_detection.py` (NEW)
  - `tests/fixtures/onesignal-positive/` (fixture project NEW)
- **Steps:**
  1. **RED:** Write failing detection/validation test FIRST em
     `tests/validators/test_onesignal_detection.py`:
     - Cria fixture project em `tests/fixtures/onesignal-positive/` com signals matching
       (`gradle-dep com.onesignal:OneSignal-Android-SDK`).
     - Assert `_eval_gradle_dep(...)` retorna match esperado.
     - Assert `validate_card_yaml("cards/onesignal/card.yaml")` zero violations (vai
       FALHAR).
     - Run pytest → confirma FAIL.
  2. Cria `cards/onesignal/card.yaml` (category `notifications`) + `detection/signals.yaml`
     + README minimal + template stub. Reuse-first análogo a `cards/fcm/` (mesma axis).
  3. **GREEN:** Re-run pytest → confirma PASS.
- **AC coverage:** AC-4.
- **Verification:** `validate_card_yaml.py cards/onesignal/` green; pytest passa.

#### W4.5 — `firebase-remote-config`

- **Files:**
  - `cards/firebase-remote-config/card.yaml` (category: `flags`)
  - `cards/firebase-remote-config/README.md`
  - `cards/firebase-remote-config/detection/signals.yaml`
  - `cards/firebase-remote-config/templates/firebase-remote-config-tech-spec.md`
  - `tests/validators/test_firebase_remote_config_detection.py` (NEW)
  - `tests/fixtures/firebase-remote-config-positive/` (fixture project NEW)
- **Steps:**
  1. **RED:** Write failing detection/validation test FIRST em
     `tests/validators/test_firebase_remote_config_detection.py`:
     - Cria fixture project em `tests/fixtures/firebase-remote-config-positive/` com
       signals matching (`gradle-dep com.google.firebase:firebase-config`).
     - Assert `_eval_gradle_dep(...)` retorna match esperado.
     - Assert `validate_card_yaml("cards/firebase-remote-config/card.yaml")` zero
       violations (vai FALHAR).
     - Run pytest → confirma FAIL.
  2. Cria `cards/firebase-remote-config/card.yaml` (category `flags`, `requires:
     [firebase-platform]`) + `detection/signals.yaml` + README minimal + template stub.
     Reuse-first análogo a `cards/firestore-persistence/`.
  3. **GREEN:** Re-run pytest → confirma PASS.
- **AC coverage:** AC-4.
- **Verification:** `validate_card_yaml.py cards/firebase-remote-config/` green; pytest
  passa.

#### W4.6 — `posthog-flags`

- **Files:**
  - `cards/posthog-flags/card.yaml` (category: `flags`)
  - `cards/posthog-flags/README.md`
  - `cards/posthog-flags/detection/signals.yaml`
  - `cards/posthog-flags/templates/posthog-flags-tech-spec.md`
  - `tests/validators/test_posthog_flags_detection.py` (NEW)
  - `tests/fixtures/posthog-flags-positive/` (fixture project NEW)
- **Steps:**
  1. **RED:** Write failing detection/validation test FIRST em
     `tests/validators/test_posthog_flags_detection.py`:
     - Cria fixture project em `tests/fixtures/posthog-flags-positive/` com signals
       matching (`gradle-dep com.posthog:posthog-android` + `file-content
       posthog.isFeatureEnabled`).
     - Assert `_eval_gradle_dep(...)` + `_eval_file_content(...)` retornam matches
       esperados.
     - Assert `validate_card_yaml("cards/posthog-flags/card.yaml")` zero violations (vai
       FALHAR).
     - Run pytest → confirma FAIL.
  2. Cria `cards/posthog-flags/card.yaml` (category `flags`) + `detection/signals.yaml`
     + README minimal + template stub. Reuse-first análogo a `cards/posthog-analytics/`
     (mesmo vendor) + `cards/firebase-remote-config/` (mesma axis).
  3. Detection: `gradle-dep com.posthog:posthog-android` + `file-content
     posthog.isFeatureEnabled`.
  4. **GREEN:** Re-run pytest → confirma PASS.
- **AC coverage:** AC-4.
- **Verification:** `validate_card_yaml.py cards/posthog-flags/` green; pytest passa.

#### W4.7 — Full validator cascade across all 6 cards

- **Files:** N/A (verification step — TDD per-card já coberto em W4.1-W4.6)
- **Steps:**
  1. Run full validator cascade across all 6 cards: `forge verify` + `validate_card_yaml.py`
     em cada um dos 6 cards novos; confirma zero violations.
  2. Run `pytest tests/validators/test_firebase_analytics_detection.py
     tests/validators/test_posthog_analytics_detection.py
     tests/validators/test_fcm_detection.py
     tests/validators/test_onesignal_detection.py
     tests/validators/test_firebase_remote_config_detection.py
     tests/validators/test_posthog_flags_detection.py` → todos green.
  3. **Open implementation detail #7 resolution:** se decidir rename `crashlytics` →
     `firebase-crashlytics`, criar como sub-task aqui (rename diretório + atualizar
     referências em `presets/kmp-mobile/preset.yaml § backend-candidates` que serão
     removidas em W6/W7 mesmo). Deviation tracking: registra no commit body.
- **Verification:** 22 + 6 = 28 cards passam validator; 6 detection tests green.

---

### W5 — Detection composer (depende W2 + W3)

**Goal:** composer module produces `Map[axis][platform] → cell | Conflict` a partir de signals.

**Justificativa load-bearing:** W5 cria módulo novo em `engine/detection/` (não load-bearing per se, mas chokepoint do init flow). Justificativa: lógica de composer é o coração do brownfield path.

#### W5.1 — Composer module skeleton

- **Files:**
  - `engine/detection/__init__.py` (NEW, empty)
  - `engine/detection/composer.py` (NEW)
- **Steps:**
  1. **TDD red:** test em `tests/engine/test_detection_composer.py::test_composer_emits_active_cell_when_single_card_above_threshold` — confirma FAIL (módulo não existe).
  2. **TDD green:** implementa `compose_backend_axes(project_root, active_cards) -> dict[axis][platform] -> Cell | Conflict | None`. Reusa `engine/init.py:_eval_detection_signals` + `_eval_gradle_dep` (import + chamada — não reimplementa).
  3. **TDD red:** test `test_composer_emits_conflict_when_two_cards_above_threshold`.
  4. **TDD green:** add ranking + conflict detection.
  5. **TDD red:** test `test_composer_emits_null_when_no_match`.
  6. **TDD green:** trivial (empty cell case).
- **AC coverage:** AC-5.
- **Verification:** `pytest tests/engine/test_detection_composer.py -xvs` green.

#### W5.2 — Integration test with fixture

- **Files:**
  - `tests/integration/test_detection_composer_mixed_setup.py` (NEW)
  - `tests/fixtures/mixed-kmp-setup/...` (fixture diretório — pseudo-projeto com retrofit em android + ktor em shared)
- **Steps:**
  1. **TDD red:** integration test que confirma composer emit `Conflict[retrofit-client, ktor-client]` para cell `(data, android)` OU emit duas cells distintas dependendo de platform-applicability.
  2. **TDD green:** ajusta composer pra resolver conflito conforme regra (rank + threshold).
- **AC coverage:** AC-5.
- **Verification:** `pytest tests/integration/test_detection_composer_mixed_setup.py` green.

---

### W6 — Starter bundles (paralelizável com Phase A; depende W1)

**Goal:** 3 arquivos YAML pros bundles + sentinel `custom-from-scratch` documentado.

**Justificativa load-bearing:** W6 cria arquivos em `presets/**` (whitelist). Justificativa: bundles são fonte-de-verdade pro greenfield path.

#### W6.1 — Cria 3 bundle YAMLs

- **Files:**
  - `presets/kmp-mobile/bundles/firebase-full.yaml` (NEW)
  - `presets/kmp-mobile/bundles/rest-with-firebase-telemetry.yaml` (NEW)
  - `presets/kmp-mobile/bundles/local-only.yaml` (NEW)
- **Steps:**
  1. Cada YAML segue shape declarado no SPEC §"Starter bundles".
  2. `name:`, `description:`, `defaults:` (map of axis → `{ all-platforms: <card> }` OR `{ android: <card>, ios: <card>, kmp: <card> }`).
- **AC coverage:** AC-3.

#### W6.2 — Atualiza `presets/kmp-mobile/preset.yaml`

- **Files:**
  - `presets/kmp-mobile/preset.yaml`
- **Steps:**
  1. Remove bloco `backend-candidates:` inteiro (linhas ~127-163).
  2. Adiciona referência `bundles-dir: ./bundles/` documentando onde os bundles vivem.
  3. Adiciona sentinela `custom-from-scratch: { description: "Skip bundle, prompt per-axis", file: null }` ou similar.
- **AC coverage:** AC-3.

#### W6.3 — Presets validator extension (se necessário)

- **Files:**
  - `validators/validate_presets.py` (ou similar — confirm via `ls validators/`)
- **Steps:**
  1. Adiciona schema check pros bundle YAMLs (campos requeridos, axes válidos).
  2. **TDD shape:** test em `tests/validators/test_validate_presets.py` cria fixture bundle inválido (axis desconhecido) — confirma FAIL antes da validator extension.
- **AC coverage:** AC-3.

---

### W7 — Init + Reconfigure UX (**BLOCKED até Phase A entregar AskUserQuestion intent protocol**)

**Goal:** init e reconfigure consomem o novo modelo via Phase A intent layer.

**Justificativa load-bearing:** W7 toca `engine/init.py` + `engine/reconfigure.py` (chokepoints). Justificativa: orchestration nova substitui handler legacy (bundle escolha) por composer + bundle picker + per-axis prompts.

**Phase A dependency explicit:** W7 não inicia antes de Phase A shippar. Sub-task W7.0
(BLOCKING) executa o gate decision com 2 caminhos determinísticos abaixo.

#### W7.0 — Phase A dependency gate (BLOCKING)

This wave requires Phase A (DRIFT-1 intent protocol) to be merged to main before
execution. Two paths:

**Path A — Phase A is merged (HAPPY PATH):**
- Proceed to W7.1 (brownfield) → W7.2 (greenfield) → W7.3 (reconfigure)
- ACs AC-6, AC-7, AC-8 fully covered via Claude-Code-fronted intent protocol
- W7.4 cleanup of legacy backend-choice runs as final cleanup

**Path B — Phase A NOT merged (FALLBACK):**
- HALT W7 execution
- Update `docs/design/04-pending.md` adding new entry: "Phase B W7 deferred pending
  Phase A merge — re-dispatch when Phase A lands"
- Skip W7.1-W7.4 entirely
- Proceed directly to W8 (doc-sync) WITH NOTE: ACs AC-6, AC-7, AC-8 marked as
  PARTIAL (schema + detection + bundles ready; UX integration deferred)
- W8 commit message + handoff explicit: "DET-6 Phase B partial ship — W7 UX
  deferred pending Phase A"

The orchestrator decides Path A or Path B BEFORE dispatching W7 implementation
agent. No autonomous gate decision by sub-agent.

- **Files:** N/A (gate decision step)
- **Steps:**
  1. Orchestrator runs gate checks:
     ```bash
     ls docs/superpowers/specs/drift-1-intent-protocol.md  # exists?
     ls docs/superpowers/plans/drift-1-intent-protocol.md  # exists?
     git log --all --oneline | grep -i "drift-1\|intent protocol"  # merged?
     grep -rn "AskUserQuestion\|intent_state" engine/ui/question.py  # API materializada?
     ```
  2. Se TODAS as checks passam → Path A (proceed W7.1-W7.4).
  3. Se QUALQUER check falha → Path B (halt + 04-pending entry + skip to W8).
  4. Decision logged in commit body or session handoff.
- **Verification:** Path decision documented before W7.1 dispatch.

#### W7.1 — Init flow brownfield

- **Files:**
  - `engine/init.py`
  - `tests/integration/test_init_brownfield_multi_axis.py` (NEW)
- **Steps:**
  1. **TDD red:** integration test simula projeto detectável (uniform Firebase) e confirma init emits AskUserQuestion intent com tabela detectada.
  2. **TDD green:** implementa `_handle_backend_multi_axis_brownfield(composer_result)`:
     - chama `compose_backend_axes()`.
     - renderiza tabela via AskUserQuestion intent (Phase A API).
     - 3 opções: confirmar / ajustar / começar do zero.
  3. Adaptive UX: detect uniformity per-axis; compactar prompt quando uniform.
- **AC coverage:** AC-6.

#### W7.2 — Init flow greenfield

- **Files:**
  - `engine/init.py` (continuação)
  - `tests/integration/test_init_greenfield_multi_axis.py` (NEW)
- **Steps:**
  1. **TDD red:** integration test sem signals detectáveis confirma init prompta bundle picker.
  2. **TDD green:** implementa `_handle_backend_multi_axis_greenfield()`:
     - carrega `presets/kmp-mobile/bundles/*.yaml`.
     - AskUserQuestion bundle picker (4 opções).
     - Se ≠ custom-from-scratch: prompt "override?" yes/no → multiSelect axes → per-axis prompts.
     - Se custom-from-scratch: salta direto pra per-axis prompts (todos os 8 axes).
- **AC coverage:** AC-7.

#### W7.3 — Reconfigure flow

- **Files:**
  - `engine/reconfigure.py`
  - `tests/integration/test_reconfigure_multi_axis.py` (NEW)
- **Steps:**
  1. **TDD red:** integration test edita cell `(data, android)` de null → card retrofit-client, confirma workflow-config escrito corretamente + .bak criado + history entry.
  2. **TDD green:** implementa `_handle_backend_axes_submenu`:
     - mostra tabela current (8 axes × N platforms).
     - multiSelect cells pra editar.
     - per cell: opções (null / pick card / change status / edit migrating-to).
     - validation: cell.card existe + status enum + migrating-to consistency.
     - backup `.bak` + history entry + sha256 update (reusa pattern).
  3. Remove `_handle_backend` legacy (handler antigo).
  4. Remove referência a `identity.backend-choice` em todo `engine/reconfigure.py`.
- **AC coverage:** AC-8.

#### W7.4 — Remove `identity.backend-choice` from engine

- **Files:**
  - `engine/init.py` (write workflow-config — remove writing `identity.backend-choice`)
  - `engine/reconfigure.py` (remove leitura)
  - `engine/cards/loader.py` (se houver referência)
  - grep cross-check
- **Steps:**
  1. `grep -rn "backend-choice" engine/` → lista todas as referências.
  2. Remove cada referência. Schema da workflow-config (W1.3) já documentou ausência.
- **AC coverage:** AC-2 (consolida).

---

### W8 — Doc-sync + verify + final

**Goal:** todos os docs sincronizados com o shipping, validators cascade green, baseline pytest verde, follow-ups anotados em 04-pending.

**Justificativa load-bearing:** W8 toca `docs/design/04-pending.md` (não load-bearing strict, mas canônico) + `CHANGELOG.md` + `README.md` + handoff. Mandamento #6.

#### W8.1 — CHANGELOG.md

- **Files:**
  - `CHANGELOG.md`
- **Steps:**
  1. Adiciona em `## [Unreleased]`:
     - `### Added` — 8 axes taxonomy, cell shape, status enum, 4 bundles, 6 new cards, detection composer, AskUserQuestion-fronted init/reconfigure (Phase A consumer).
     - `### Changed` — category cleanup (`backend`/`network` → 8 axes), label refactor (`auth-provider`/`http-client`/`crash-reporting` removidos), schema migration de `backend.provider` → `backend.<axis>.<platform>`.
     - `### Removed` — `backend-candidates` em preset.yaml, `identity.backend-choice`, singular labels deprecated.

#### W8.2 — `docs/design/08-session-handoff.md`

- **Files:**
  - `docs/design/08-session-handoff.md`
- **Steps:**
  1. **Última atualização:** YYYY-MM-DD (v1.2-dev — DET-6 multi-axis backend).
  2. **Estado:** atualiza pra refletir DET-6 shipped + B1/B2/DET-5 fechados.

#### W8.3 — `docs/design/04-pending.md`

- **Files:**
  - `docs/design/04-pending.md`
- **Steps:**
  1. Move DET-6, DET-5, B1, B2 pra seção `## Fechado em [Unreleased]`.
  2. Adiciona follow-ups novos descobertos durante design:
     - Sub-axes formal (data → transport/contract/realtime/rules).
     - 9º axis (messaging direta) — anotar como possível.
     - Card composability dentro da mesma cell além de migrating-to.
     - `firestore-realtime`/`firestore-security-rules` fate (Open implementation detail #4 e #5).
     - Validation de bundle YAMLs caso scope expanda.
- **Pending gaps coverage:** AC mapping verifica todos os items.

#### W8.4 — `README.md` stats

- **Files:**
  - `README.md`
- **Steps:**
  1. Atualiza Stats: card count (22 → 28), schemas count (+1 backend-axes.md), categories count.

#### W8.5 — `.claude/rules/reuse.md` (se padrão mudou)

- **Files:**
  - `.claude/rules/reuse.md` (load-bearing — justificativa: composer module em `engine/detection/` introduz reuso novo a documentar)
- **Steps:**
  1. Adiciona menção a `engine/detection/composer.py` como helper compartilhado pra futuras detection extensions.

#### W8.6 — Verify cascade

- **Files:** N/A
- **Steps:**
  1. `forge verify` — full cascade.
  2. `pytest` — full suite. Expected count: baseline 1113 + novos tests (~15-25 new: composer unit, integration brownfield + greenfield + reconfigure, validators bundles).
  3. `forge doctor` — 12 categorias.
- **Verification:** todos exit 0.

#### W8.7 — Smoke tests (manual checklist)

- **Files:** N/A (manual)
- **Steps:**
  1. **Brownfield smoke:** fixture com Firebase uniforme. Esperado ≤8 prompts. (depende Phase A)
  2. **Greenfield smoke:** projeto vazio + bundle `firebase-full`. Esperado 1-2 prompts. (depende Phase A)
  3. **Reconfigure smoke:** flip cell `(data, kmp)` de ktor-client → null. Confirm `.bak` + history.
  4. **Custom-from-scratch smoke:** confirm pula bundle, vai direto per-axis.
- **AC coverage:** AC-6, AC-7, AC-8 (final validation).

---

## Spec coverage table (canonical)

| AC | Wave | Tasks | Verification |
|---|---|---|---|
| AC-1 | W1 | W1.1 + W1.2 | Schema docs include cell + status + 8 axes |
| AC-2 | W1 + W7.4 | W1.3 + W7.4 | Schema doc + grep `backend-choice` empty in engine/ |
| AC-3 | W6 | W6.1 + W6.2 + W6.3 | 3 YAMLs valid + validator passes + sentinel documented |
| AC-4 | W4 | W4.1-W4.6 + W4.7 | 6 cards × CARD-001..020 green |
| AC-5 | W5 | W5.1 + W5.2 | composer unit + integration with mixed fixture |
| AC-6 | W7 | W7.1 + W8.7 (smoke) | brownfield test + manual smoke (depende Phase A) |
| AC-7 | W7 | W7.2 + W8.7 | greenfield test + manual smoke + custom-from-scratch |
| AC-8 | W7 | W7.3 | reconfigure integration test + smoke |
| AC-9 | W2 | W2.2 + W2.3 + W2.4 | grep `category: backend\|network` empty + cascade green |
| AC-10 | W3 | W3.2 + W3.3 | grep singular labels empty + tests green |

---

## Pending gaps coverage (Mandamento #2 — não-procrastinação)

Follow-ups descobertos durante design (todos anotados em W8.3):

- **Sub-axes formal** — `data` em sub-axes (transport/contract/realtime/rules). Defer v1.1+. Razão concreta: cross-cutting (toca 4 cards), brainstorm separado.
- **9º axis (messaging direta)** — chat/interactive push. Defer v1.1+. Razão: sem caso real observado.
- **`crashlytics` rename pra `firebase-crashlytics`** — Open implementation detail #7. Decisão delegada a W4.7. Razão: cosmético, cabe inline ou follow-up.
- **Custom catalog path discovery (FU-1 de DET-3)** — não fechado por DET-6. Permanece em `04-pending.md`.
- **`signals.yaml` mirror vs source-of-truth (FU-2 de DET-3)** — não fechado por DET-6. Permanece.
- **Substring match no fallback build.gradle (FU-3 de DET-3)** — não fechado. Permanece.
- **Bootstrap idempotency em worktree (FU-5 de DET-3)** — phase-independente. Permanece.

DET-6, DET-5, B1, B2 todos endereçados — movidos pra "Fechado em [Unreleased]".

---

## Phase A dependency — explicit declaration

W7 (init + reconfigure UX) é **bloqueado** até Phase A (DRIFT-1) entregar:

- `engine/ui/question.py` refatorado com TTY/env detection + protocol intent emit.
- API canônica pra Claude-Code-fronted AskUserQuestion (spec a definir em Phase A SPEC).
- Documentação em `docs/superpowers/specs/drift-1-intent-protocol.md` + `docs/superpowers/plans/drift-1-intent-protocol.md`.

W1-W6 são **paralelizáveis** com Phase A (zero touch em `engine/ui/`).

W8 (doc-sync + verify) executa após W7. Se Phase A atrasar, W7 fica em STATE.md `blocked-on-external` (DET-6 task waits for DRIFT-1 phase). Pre-W7 sub-task 0 documenta o gate explicitamente.

---

## Verification (W8 consolidado)

```bash
# Cascade
forge verify                       # 15 validators green
forge doctor                       # 12 categories green

# Tests
pytest                             # baseline 1113 + novos (~15-25)
pytest -m integration              # integration tests específicos
pytest tests/engine/test_detection_composer.py -xvs

# Card validation manual
for c in cards/*/card.yaml; do python -m validators.validate_card_yaml "$c"; done

# Schema audits
grep -rn "category: backend\|category: network" cards/  # MUST be empty
grep -rn "auth-provider\|http-client\|crash-reporting" cards/  # MUST be empty
grep -rn "backend-choice" engine/   # MUST be empty
grep -rn "backend-candidates" engine/  # MUST be empty (only in preset.yaml comments até W6.2)
```

Expected baseline pytest: 1113 + 15-25 (composer 3, brownfield 1, greenfield 1, reconfigure 1, bundles validator 2, card.yaml schema 2, label refactor 2, category cleanup 2, integration mixed 1).

---

## Out-of-scope deliberados (Mandamento #4 — escopo)

- Cards `sqldelight`, `apollo-graphql-client`, `realm-database`, `hilt-di` — labels reservadas (`capability-labels.md`) que ficam roadmap v1.1+, NÃO criadas em DET-6.
- iOS-specific persistence (`core-data`, `swift-data`) — fora do escopo v1.0.
- Backend-server cards (`spring-boot`, `ktor-server`, `firebase-functions`) — projeto é mobile-only.
- Multi-tenant workflow-config (multi-projeto compartilhando bundle) — anti-goal.
- Side-by-side multi-tenant Firebase (2 projetos Firebase ativos no mesmo app) — anti-goal v1.0.

---

## Commit strategy

Cada wave = 1+ commits atomic conforme task granularity:

- W1: 1 commit (`docs(schemas): introduce multi-axis backend taxonomy`)
- W2: 1 commit (`refactor(cards): align identity.category with 8 backend axes`)
- W3: 1 commit (`refactor(cards): remove singular labels superseded by schema enforcement`)
- W4: 6 commits (`feat(cards): add <card-name>`) or 1 batched (`feat(cards): add 6 cards for analytics/notifications/flags axes`)
- W5: 1-2 commits (composer + tests)
- W6: 1 commit (`feat(presets): add 3 starter bundles for kmp-mobile`)
- W7: 3-4 commits (init brownfield, init greenfield, reconfigure, cleanup `backend-choice`)
- W8: 1 commit (`docs(sync): det-6 changelog + handoff + pending + readme`)

Total estimate: 13-17 commits.

Final tag/release decision lives in W8 retrospective (not in this PLAN).
