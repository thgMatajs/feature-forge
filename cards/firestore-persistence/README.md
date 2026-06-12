# firestore-persistence

> Card de backend que declara **Cloud Firestore** como camada de persistência
> server-side para operações **CRUD one-shot**, **queries custom** e
> **batch writes**. Realtime listeners e security rules ficam em cards
> separados (`firestore-realtime` e `firestore-security-rules`).

- **Capabilities providas**: `persistence-server`, `api-contract-firebase-sdk`
- **Capabilities requeridas**: (nenhuma — card de backend é raiz; usa o SDK
  Firebase diretamente)
- **Conflitos**: `persistence-server` (singular — só um backend server-side
  principal por projeto)
- **Categoria**: `backend`
- **Maturity**: `stable`

Persistência **local** (Room, SQLite, SwiftData) **não** conflita —
capability diferente (`persistence-local`). É comum ter Firestore como
source-of-truth remoto + cache local.

---

## 1. Por que esse card existe (e por que foi splittado)

Cloud Firestore era originalmente representado pelo card monolítico
`firebase-firestore`, que cobria CRUD + listeners realtime + security rules
+ índices + threat model num único bundle. Durante a Fase 3.5 do
feature-forge, esse card foi **splittado em três** para refletir três
preocupações independentes:

| Card | Capability principal | Foco |
|---|---|---|
| `firestore-persistence` (este) | `persistence-server`, `api-contract-firebase-sdk` | CRUD documents, queries one-shot, batch writes, mapeamento de erro, índices |
| `firestore-realtime` | `realtime-stream` | Snapshot listeners, lifecycle de Flow callback, backpressure |
| `firestore-security-rules` | `firestore-rules-guarded` | Cobertura de `firestore.rules`, emulator rules-tests, threat model |

A separação permite que um projeto use Firestore apenas como **persistência
write-once** (sem listeners) sem importar peso conceitual de realtime, ou
adote regras de segurança custom sem reativar listeners. Os três cards
compõem livremente.

Para tratar Firestore como backend de produção, a feature precisa, em toda
PR, manter atualizados quatro artefatos canônicos de dados (no MeoBonsai
eles vivem em `docs/specs/data/`):

| Artefato | Responsabilidade |
|---|---|
| `firestore-data-model.md` | Shape de cada coleção/document: campos, tipos, nullability, ownership |
| `query-catalog.md` | Lista de TODAS as queries em uso + os índices que cada uma exige |
| `access-matrix.md` | Quem (claim/role) pode `create/read/update/delete` em cada coleção |
| `security-and-threat-model.md` | STRIDE, claims esperadas, abuso por deep-link, abuso por listener |

Esses quatro arquivos formam a **4-source-of-truth de dados** do projeto.
A regra é: **qualquer feature que mexe em coleção, query, índice ou regra
de segurança atualiza esses quatro arquivos na MESMA PR** — sem exceção.
Este card materializa essa regra para a parte CRUD/queries; o card
`firestore-security-rules` materializa para a parte de rules.

---

## 2. O que esse card contribui

### Templates (fragments mesclados em documentos da feature)

| Target | Section | Merge | Fonte |
|---|---|---|---|
| `data-contract-spec.yaml` | `firestore-collections` | `merge-keys` | `templates/firestore-persistence-data-contract.yaml` |
| `tech-spec.md` | `Data layer` | `append-section` | `templates/firestore-persistence-tech-spec.md` |

### Agent prompts (injeções em extension-points conhecidos)

| Agent | Extension-point | Conteúdo |
|---|---|---|
| `contract-planner-agent` | `section:firestore-collections` | Como descrever coleções, operações CRUD one-shot, queries custom, batch writes, índices, refs de security rules por scenario BDD; obrigatoriedade da 4-source-of-truth |
| `tech-spec-agent` | `section:Data layer` | Repository pattern, FirebaseFirestore injection via Koin, error mapping (`FirebaseFirestoreException` → domain), cache strategy, threading, índices |
| `task-contract-writer` | `after:Allowed Files` | `allowed_files` (repositories, DTOs, `firestore.indexes.json`) + validations (índices, emulator CRUD) + task de docs |

### Validators (stubs Phase 5)

| Nome | Runs-on | Severity | Stub |
|---|---|---|---|
| `check-firestore-indexes` | `verify-task` | `warn` | `validators/check-firestore-indexes.py` |

> Cobertura de rules (`check-firestore-rules-coverage`) e listeners
> (lifecycle/backpressure) ficam nos cards complementares.

### Config defaults

```yaml
conventions.backend.persistence: "firebase-firestore"
conventions.testing.backend-e2e: "firestore-emulator"
```

---

## 3. Detecção

Threshold cumulativo **0.5**. Sinais detalhados em `detection/signals.yaml`.

- `**/build.gradle*` contém `firebase-firestore` (0.5)
- `**/Package.swift` ou `**/Podfile` contém `FirebaseFirestore` (0.3)
- `**/firestore.indexes.json` existe (0.2)
- `**/google-services.json` existe (0.2)

Qualquer combinação ≥ 0.5 → auto-ativa. Entre 0.3 e 0.5 → confirma com o
usuário no `forge init`.

> Note que **a presença de `firestore.rules` não é sinal deste card** —
> esse arquivo dispara o card `firestore-security-rules`. Da mesma forma,
> uso de `snapshotListener`/`addSnapshotListener` dispara o card
> `firestore-realtime`.

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
   pontos de exposição.

Esses quatro arquivos são **referência viva** — o card os trata como
contrato do produto, não como documentação opcional.

---

## 5. Como o card flui no pipeline

```
Wave A (PRD)                — não toca aqui
Wave B (screen-analysis)    — não toca aqui
Wave C (contract-planner)   — injeta seção firestore-collections em data-contract-spec
                              (CRUD + queries one-shot + batch writes)
Wave D (tech-spec)          — injeta Data layer (repository + Koin + error mapping +
                              cache + índices) em tech-spec.md
Wave E (task-contract)      — injeta allowed-files (DTOs, repos, indexes.json) +
                              validators (check-firestore-indexes) + task de docs
Phase 5 (verify / commit)   — validator check-firestore-indexes roda (severity: warn)
```

Cards complementares (`firestore-realtime`, `firestore-security-rules`)
injetam suas próprias subseções no mesmo `tech-spec.md` quando ativos —
o engine merge resolve a ordem alfabeticamente.

---

## 6. Limites e não-objetivos

- **Não cobre realtime listeners** — card `firestore-realtime` cuida disso
  (lifecycle de `callbackFlow`, `WhileSubscribed`, backpressure).
- **Não cobre security rules** — card `firestore-security-rules` cuida
  (`firestore.rules`, emulator rules-tests, threat model).
- **Não cobre Firebase Auth, Storage, Crashlytics, RemoteConfig** — cada
  um é card próprio (`firebase-auth`, `firebase-storage`, `firebase-crashlytics`).
- **Não cobre persistência local** (`persistence-local` → cards
  `room-kmp`, `swiftdata`, etc.). Cache offline-first é composição de dois
  cards.
- **Não opina sobre backend custom** — REST/GraphQL/gRPC têm cards próprios
  (`rest-api-contract`, `ktor-client`).
- **Não gera código** — declara contribuições; geração é responsabilidade
  da fase de implementação a partir dos artefatos.

---

## 7. Referência cruzada — MeoBonsai

O projeto que originou este card mantém a 4-source-of-truth viva em:

- `.claude/rules/architecture.md` — §"Firebase Data Model Source of Truth"
- `docs/specs/data/firestore-data-model.md`
- `docs/specs/data/query-catalog.md`
- `docs/specs/data/access-matrix.md`
- `docs/specs/data/security-and-threat-model.md`

Esses caminhos são exemplos reais — a regra é: **a feature que mexe em
dados atualiza esses quatro arquivos na MESMA PR**, sem exceção. Os
validators Phase 5 vão materializar essa regra programaticamente (este
card cobre índices; o card `firestore-security-rules` cobre coverage de
rules).
