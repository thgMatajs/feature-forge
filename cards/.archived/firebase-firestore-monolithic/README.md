# firebase-firestore

> Card de backend que declara **Cloud Firestore** como camada de persistência
> primária + realtime data, com governança forte de **security rules**,
> **query catalog**, **access matrix** e **threat model**.

- **Capabilities providas**: `persistence-server`, `realtime-data`
- **Capabilities requeridas**: (nenhuma — card de backend é raiz)
- **Conflitos**: outros cards que provejam `persistence-server`
  (backends server-side concorrentes)
- **Categoria**: `backend`
- **Maturity**: `stable`

Persistência **local** (Room, SQLite, SwiftData) **não** conflita — capability
diferente (`persistence-local`). É comum ter Firestore como source-of-truth
remoto + cache local.

---

## 1. Por que esse card existe

Firestore é mais do que "salvar um JSON na nuvem". Para tratar Firestore como
backend de produção, a feature precisa, em toda PR, manter atualizados quatro
artefatos canônicos de dados (no MeoBonsai eles vivem em `docs/specs/data/`):

| Artefato | Responsabilidade |
|---|---|
| `firestore-data-model.md` | Shape de cada coleção/document: campos, tipos, nullability, ownership |
| `query-catalog.md` | Lista de TODAS as queries em uso + os índices que cada uma exige |
| `access-matrix.md` | Quem (claim/role) pode `create/read/update/delete` em cada coleção |
| `security-and-threat-model.md` | STRIDE, claims esperadas, abuso por deep-link, abuso por listener |

Esses quatro arquivos formam a **4-source-of-truth de dados** do projeto.
A regra é: **qualquer feature que mexe em coleção, query, índice ou regra de
segurança atualiza esses quatro arquivos na MESMA PR**. O card aplica isso via:

1. Fragmento em `data-contract-spec.yaml` que força declarar coleções, queries e
   refs de regras por scenario BDD.
2. Fragmento em `tech-spec.md` que exige descrever repository pattern, snapshot
   listeners, cache strategy e mapeamento de `FirebaseFirestoreException` →
   domain error.
3. Validators que, em Phase 5, vão bloquear PR sem cobertura de regras e
   alertar query sem índice declarado.
4. Hook em `firestore.rules` que vai reexecutar coverage do emulator.

---

## 2. O que esse card contribui

### Templates (fragments mesclados em documentos da feature)

| Target | Section | Merge | Fonte |
|---|---|---|---|
| `data-contract-spec.yaml` | `firestore-collections` | `merge-keys` | `templates/firestore-data-contract.yaml` |
| `tech-spec.md` | `Data layer` | `append-section` | `templates/firestore-tech-spec.md` |
| `test-strategy.yaml` | `backend-e2e` | `merge-keys` | `templates/firestore-e2e.yaml` |

### Agent prompts (injeções em extension-points conhecidos)

| Agent | Extension-point | Conteúdo |
|---|---|---|
| `contract-planner-agent` | `section:firestore-collections` | Como descrever coleções/docs/fields, índices, refs de security rules por scenario BDD; obrigatoriedade de atualizar a 4-source-of-truth |
| `tech-spec-agent` | `section:Data layer` | Repository pattern, snapshot listeners, cache strategy, mapeamento `FirebaseFirestoreException` → domain |
| `task-contract-writer` | `after:Allowed Files` | `allowed_files` (repositories, DTOs, `firestore.rules`, `firestore.indexes.json`) + validation steps (emulator coverage, índices vs queries) |

### Validators (stubs Phase 5)

| Nome | Runs-on | Severity | Stub |
|---|---|---|---|
| `check-firestore-rules-coverage` | `verify-task`, `forge-doctor` | `error` | `validators/check-firestore-rules-coverage.py` |
| `check-firestore-indexes` | `verify-task` | `warn` | `validators/check-firestore-indexes.py` |

### Hooks (stubs Phase 5)

| Arquivo | Evento | Glob |
|---|---|---|
| `hooks/post-edit-firestore-rules.sh` | `post-edit` | `**/firestore.rules` |

### Config defaults

```yaml
conventions.backend.persistence:                  "firebase-firestore"
conventions.observability.firestore-rules-source: "firestore.rules"
conventions.testing.backend-e2e:                  "firestore-emulator"
```

---

## 3. Detecção

Threshold cumulativo **0.5**. Sinais detalhados em `detection/signals.yaml`.

- `**/build.gradle*` contém `firebase-firestore` (0.5)
- `**/firestore.rules` existe (0.3)
- `**/Package.swift` ou `**/Podfile` contém `FirebaseFirestore` (0.3)
- `**/firestore.indexes.json` existe (0.2)
- `**/google-services.json` existe (0.2)

Qualquer combinação ≥ 0.5 → auto-ativa. Entre 0.3 e 0.5 → confirma com o
usuário no `forge init`.

---

## 4. A 4-source-of-truth de dados (obrigatória por PR)

O agent `contract-planner` e o agent `tech-spec` recebem injeções deste card
que **bloqueiam** o avanço caso a feature mexa em dados e não atualize:

1. **`docs/specs/data/firestore-data-model.md`** — shape de coleções e docs.
   Para cada entity tocada pela feature, listar campos novos/alterados,
   tipos exatos, nullability, ownership (qual UID/role detém o doc).
2. **`docs/specs/data/query-catalog.md`** — toda query custom referenciada
   pela feature. Cada query → exige declarar índice em
   `firestore.indexes.json` se for compound ou `orderBy` + `where`.
3. **`docs/specs/data/access-matrix.md`** — quem pode `create / read /
   update / delete` cada coleção. Diff explícito ao adicionar role/claim.
4. **`docs/specs/data/security-and-threat-model.md`** — STRIDE para os novos
   pontos de exposição (writes públicos, listeners abertos, deep-links,
   campos sensíveis).

Esses quatro arquivos são **referência viva** — o card os trata como contrato
do produto, não como documentação opcional.

---

## 5. Como o card flui no pipeline

```
Wave A (PRD)                — não toca aqui
Wave B (screen-analysis)    — não toca aqui
Wave C (contract-planner)   — injeta seção firestore-collections em data-contract-spec
Wave D (tech-spec)          — injeta repository + snapshot + error mapping em Data layer
Wave E (task-contract)      — injeta allowed-files (rules, indexes) + validators
Phase 5 (verify / commit)   — validators rodam, hook em firestore.rules dispara
```

---

## 6. Limites e não-objetivos

- **Não cobre Firebase Auth, Storage, Crashlytics, RemoteConfig** — cada um é
  card próprio (`firebase-auth`, `firebase-storage`, `crashlytics`).
- **Não cobre persistência local** (`persistence-local` → cards `room-kmp`,
  `swiftdata`, etc.). Cache offline-first é composição de dois cards.
- **Não opina sobre backend custom** — REST/GraphQL/gRPC têm cards próprios.
- **Não gera código** — declara contribuições; geração é responsabilidade da
  fase de implementação a partir dos artefatos.

---

## 7. Referência cruzada — MeoBonsai

O projeto que originou este card mantém a 4-source-of-truth viva em:

- `.claude/rules/architecture.md` — §"Firebase Data Model Source of Truth"
- `docs/specs/data/firestore-data-model.md`
- `docs/specs/data/query-catalog.md`
- `docs/specs/data/access-matrix.md`
- `docs/specs/data/security-and-threat-model.md`

Esses caminhos são exemplos reais — a regra é: **a feature que mexe em dados
atualiza esses quatro arquivos na MESMA PR**, sem exceção. Os validators
Phase 5 vão materializar essa regra programaticamente.
