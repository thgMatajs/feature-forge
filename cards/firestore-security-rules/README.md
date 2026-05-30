# Card `firestore-security-rules`

> Categoria: `backend` · Maturidade: `stable` · Provê `firestore-rules-guarded`

Cobertura formal de **Firestore security rules** como camada de autorização
declarativa do projeto. É um dos três splits do antigo `firebase-firestore`
(Fase 3.5):

- `firestore-persistence` → CRUD documents, queries, batch writes.
- `firestore-realtime` → snapshot listeners, `Flow<List<T>>` realtime.
- **`firestore-security-rules`** (este card) → rules + tests + coverage.

O card é **complementar**, não conflitante: convive com qualquer outro
card que adicione camada extra de autorização (Cloud Functions, custom
claims, App Check). Não duplica responsabilidades dos outros dois splits.

---

## Filosofia

Security rules NÃO são afterthought. Toda feature que mexe em collection
Firestore precisa:

1. Atualizar `firestore.rules` na mesma PR que introduz acesso à collection.
2. Atualizar `docs/specs/data/access-matrix.md` — quem pode ler/escrever
   cada path, sob quais condições.
3. Cobrir as rules com testes via `firebase-rules-unit-testing` (allow/deny
   matrix por path + operação).
4. Validar localmente contra o emulator antes do push.
5. Versionar o roll-out (sem deploy direto em prod sem CI).

O validator `check-firestore-rules-coverage` bloqueia commit se alguma
collection da feature aparece em data-contract sem rule equivalente.
O validator `check-firestore-rules-tests` bloqueia se rule existe sem teste.

---

## 4-source-of-truth do MeoBonsai (referência viva)

Para features Firestore, os 4 documentos abaixo (que vivem em
`docs/specs/data/` do projeto consumidor) são **source of truth** —
qualquer mudança de schema, query ou rule atualiza os 4 na mesma PR:

| Documento | Conteúdo |
|---|---|
| `firestore-data-model.md` | Estrutura de collections, sub-collections, shapes de documento. |
| `query-catalog.md` | Catálogo de queries usadas (filtros, ordenação, índices). |
| `access-matrix.md` | Quem (auth.uid, custom claims) pode ler/escrever cada path, sob quais condições. |
| `security-and-threat-model.md` | Threats considerados (escalation, enumeration, IDOR, exfil), mitigações declaradas. |

Este card injeta prompts nos agents (`contract-planner-agent`,
`tech-spec-agent`, `task-contract-writer`) que **forçam** referência cruzada
a esses 4 docs sempre que a feature toca Firestore.

---

## O que este card declara

| Item | Valor |
|---|---|
| `provides` | `firestore-rules-guarded` |
| `requires` | `persistence-server` (provido por `firestore-persistence`) |
| `conflicts-with` | — (capability auxiliar, sem exclusividade) |
| `config-defaults` | `conventions.security.firestore-rules-source: firestore.rules`, `conventions.security.rules-test-framework: firebase-rules-unit-testing` |
| Detecção (threshold 0.4) | `firestore.rules` existe (0.5) **OU** combinação de `rules_version` no arquivo (0.2) + `firebase/` dir (0.1) + `firestore.indexes.json` (0.2) |

---

## Quando este card ativa

`forge init` ativa automaticamente quando o repositório já tem
`firestore.rules`. Threshold é baixo (0.4) propositalmente — é melhor
ativar e pedir confirmação do que silenciar a camada de segurança.

Para projetos que vão introduzir Firestore pela primeira vez, ativar via
`forge reconfigure` → "adicionar card" → `firestore-security-rules`. O
resolver bloqueia se `firestore-persistence` (provedor de
`persistence-server`) não estiver ativo.

---

## Convenções deste card

### 1. Uma rule por collection mexida

Toda collection que aparece em `data-contract-spec.yaml >
firestore-collections` precisa ter bloco `match` correspondente em
`firestore.rules`. Naming consistente:

```
match /databases/{database}/documents {
  match /bonsais/{bonsaiId} {
    allow read:   if request.auth != null && resource.data.ownerUid == request.auth.uid;
    allow create: if request.auth != null && request.resource.data.ownerUid == request.auth.uid;
    allow update: if request.auth != null && resource.data.ownerUid == request.auth.uid
                  && request.resource.data.ownerUid == resource.data.ownerUid;
    allow delete: if request.auth != null && resource.data.ownerUid == request.auth.uid;
  }
}
```

### 2. Operações granulares (não use `read`/`write` aberto sem justificativa)

Preferir `get`/`list` e `create`/`update`/`delete` separados. `read`
genérico só quando intenção é "qualquer leitura autorizada" — e mesmo
assim precisa de justificativa em `access-matrix.md`.

### 3. Ownership path-based ou via campo `ownerUid`

Duas formas canônicas:

| Padrão | Quando usar |
|---|---|
| **Path-based** | Documento vive em sub-collection escopada por uid: `users/{uid}/bonsais/{bonsaiId}` → rule autoriza com `uid == request.auth.uid`. |
| **Field-based** | Documento top-level com `ownerUid` no body: `bonsais/{bonsaiId}` → rule autoriza com `resource.data.ownerUid == request.auth.uid`. |

Sempre documentar no `access-matrix.md` qual padrão a feature escolheu —
mistura silenciosa é fonte recorrente de bug de autorização.

### 4. Testes obrigatórios (firebase-rules-unit-testing)

Toda rule precisa de teste em `firestore-rules.test.ts` (ou equivalente
Kotlin/Swift, se o projeto preferir) cobrindo no mínimo:

- 1 caso `allow` por operação declarada (get/list/create/update/delete).
- 1 caso `deny` por threat declarado em `security-and-threat-model.md`
  (ex.: usuário autenticado tentando ler doc de outro uid).
- 1 caso `deny` anônimo (sem `request.auth`).

Suite roda no emulator (`:8080`) iniciado por
`scripts/firebase-emulator.sh` no MeoBonsai (ou equivalente local).

### 5. Deploy via Firebase CLI (sem console manual)

```
npx -y firebase-tools@latest deploy --only firestore:rules,firestore:indexes
```

Deploy manual via console Firebase é **proibido** — quebra reproducibility
e versionamento. CI roda o comando acima após merge no branch principal,
com smoke tests em `bonsai-meo-dev` antes de prod.

### 6. Rules diff = code review obrigatório

PRs que alteram `firestore.rules` exigem revisão explícita do diff de
rules — não só "approved by passing CI". O hook `post-edit-firestore-rules`
roda a suite de testes localmente antes do commit (Phase 5).

---

## Contribuições deste card

### Templates

| Target artifact | Section | Merge |
|---|---|---|
| `tech-spec.md` | `Security Rules — Firestore` | append-section |
| `test-strategy.yaml` | `firestore-rules-tests` (top-level) | merge-keys |

### Validators

| Validator | Lifecycle | Severity |
|---|---|---|
| `check-firestore-rules-coverage.py` | `verify-task`, `forge-doctor` | error (stub Phase 5) |
| `check-firestore-rules-tests.py` | `verify-task` | error (stub Phase 5) |

### Agent prompts

| Agent | Extension-point |
|---|---|
| `contract-planner-agent` | `section:Data Contract` |
| `tech-spec-agent` | `section:Data layer` |
| `task-contract-writer` | `after:Allowed Files` |

### Hooks

| Hook | Eventos | Glob |
|---|---|---|
| `post-edit-firestore-rules.sh` | `post-edit` | `**/firestore.rules` |

Stub Phase 5: hook vai re-rodar a suite `firebase-rules-unit-testing` em
emulator quando `firestore.rules` for editado, falhando o commit se algum
teste quebrar.

### Config defaults

```yaml
conventions:
  security:
    firestore-rules-source: firestore.rules
    rules-test-framework:   firebase-rules-unit-testing
```

---

## Dev environment

| Ambiente | Endpoint | Notas |
|---|---|---|
| Emulator local | `localhost:8080` (Firestore) | Iniciado por `scripts/firebase-emulator.sh`; suite de rules tests roda aqui. |
| Firebase real dev | projeto `bonsai-meo-dev` | Preferível para QA próximo de produção (ver memória do MeoBonsai). |
| Prod | projeto `bonsai-meo` | Sem deploy direto durante desenvolvimento — só via CI após merge. |

---

## Como este card interage com outros

| Outro card | Interação |
|---|---|
| `firestore-persistence` | Pré-requisito declarado em `requires`. Toda collection citada em `firestore-collections` do data-contract precisa ter rule equivalente neste card. |
| `firestore-realtime` | Listeners também são autorizados pelas rules — `list` operation cobre `addSnapshotListener` em query. |
| `firebase-auth` | Rules dependem de `request.auth.uid` e custom claims (se firebase-auth ativo). Custom claim names declarados em `access-matrix.md`. |
| `firebase-storage` | Storage tem rules próprias (`storage.rules`) — não confundir. Cards independentes; conventions distintas (`storage-rules-source` vs `firestore-rules-source`). |

---

## Anti-patterns deste card

| Anti-pattern | Por quê |
|---|---|
| `allow read, write: if true;` em produção | Open access — qualquer um lê/escreve. Bloquear no `check-firestore-rules-tests`. |
| `allow read: if request.auth != null;` sem ownership | Qualquer usuário logado lê doc de outro — IDOR clássico. Use `resource.data.ownerUid == request.auth.uid`. |
| Rule em uma collection nova sem update de `access-matrix.md` | Source of truth desincronizado — futuras features quebram. |
| `firestore.rules` editado direto no console Firebase | Quebra versionamento + reproducibility. Sempre via PR + CI deploy. |
| Suite de rules tests rodando só em CI, nunca local | Iteração lenta + commits "fix rules" repetidos. Rodar local via emulator. |
| `match /{document=**}` no topo sem rule restritiva abaixo | Catch-all permissivo — acidente de copy/paste comum. |
| Rule referenciando `get(/databases/.../X)` sem cache awareness | Cada `get()` conta como leitura paga + limita performance. Preferir field-based ownership. |

---

## Lifecycle

- **Install**: `forge init` (auto, threshold 0.4) ou `forge reconfigure` →
  "adicionar card". Resolver erra se `persistence-server` não estiver provido.
- **Update**: `forge reconfigure` → "atualizar card do canonical".
- **Remove**: só possível se nenhuma feature ativa referencia rules — na
  prática, raramente removido após introduzido.

Edição manual de qualquer arquivo deste card no snapshot
(`.claude/cards/firestore-security-rules/`) é local. Para propagar,
edite o canonical em
`~/Documents/feature-forge/cards/firestore-security-rules/` e re-instale
via `forge reconfigure`.
