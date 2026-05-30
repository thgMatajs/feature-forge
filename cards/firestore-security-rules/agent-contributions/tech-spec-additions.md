<!--
  Fragment injetado no `tech-spec-agent` no extension-point
  `section:Data layer`. Ativo quando o card `firestore-security-rules`
  está presente em workflow-config.yaml > cards.active.

  Objetivo: forçar o tech-spec.md a descrever Security Strategy de forma
  uniforme entre features Firestore — rule por path, testes via emulator
  + firebase-rules-unit-testing, deploy via Firebase CLI, integração com
  CI. Coordenado com firestore-persistence (que cobre query design) e
  firestore-realtime (que cobre listeners).
-->

## Card contribution — `firestore-security-rules` (Security Strategy)

A feature usa Firestore. O tech-spec precisa descrever explicitamente
**a estratégia de autorização declarativa** via security rules.
Os pilares abaixo são obrigatórios; nenhum é opcional.

### 1. Rule por path (mapping explícito)

Tabela na tech-spec listando **toda collection mexida** pela feature,
com:

| Collection | Path | Operações | Ownership | Rule ref |
|---|---|---|---|---|
| bonsais | `bonsais/{bonsaiId}` | get, list, create, update, delete | field-based (`ownerUid`) | `firestore.rules#bonsais` |

Se a feature toca 5 collections, a tabela tem 5 linhas — não agregar.

### 2. Padrão canônico de bloco `match` (por collection)

```
match /databases/{database}/documents {
  match /bonsais/{bonsaiId} {
    function isAuthed() {
      return request.auth != null;
    }
    function isOwner() {
      return isAuthed()
          && resource.data.ownerUid == request.auth.uid;
    }
    function isCreatingAsOwner() {
      return isAuthed()
          && request.resource.data.ownerUid == request.auth.uid;
    }
    function preservesOwner() {
      return request.resource.data.ownerUid == resource.data.ownerUid;
    }

    allow get:    if isOwner();
    allow list:   if isAuthed();   // cliente DEVE filtrar por ownerUid (vide query-catalog.md)
    allow create: if isCreatingAsOwner();
    allow update: if isOwner() && preservesOwner();
    allow delete: if isOwner();
  }
}
```

Helpers (`isAuthed`, `isOwner`, etc.) — promover para função global
quando reutilizadas em 3+ collections. Sem 3 ocorrências, manter local
no bloco.

### 3. Testes (firebase-rules-unit-testing) — coverage matrix

Toda rule precisa de teste em `tests/firestore-rules/`. Cobertura mínima
por collection:

- 1 `allow` por operação declarada (get/list/create/update/delete).
- 1 `deny` cross-user (auth.uid != ownerUid) por operação read/update.
- 1 `deny` anônimo (auth == null) por operação.
- 1 `deny` por threat declarado em `security-and-threat-model.md`.
- 1 `deny` update tentando mudar `ownerUid` (preserves-owner invariant).

Suíte canônica (TypeScript):

```typescript
import { initializeTestEnvironment, assertSucceeds, assertFails } from '@firebase/rules-unit-testing';
import { doc, getDoc, setDoc, updateDoc } from 'firebase/firestore';

describe('bonsais rules', () => {
  let env;

  beforeAll(async () => {
    env = await initializeTestEnvironment({
      projectId: 'bonsai-meo-test',
      firestore: { host: 'localhost', port: 8080 },
    });
  });

  afterAll(async () => { await env.cleanup(); });

  test('owner can read own bonsai', async () => {
    const alice = env.authenticatedContext('alice').firestore();
    await env.withSecurityRulesDisabled(async (ctx) => {
      await setDoc(doc(ctx.firestore(), 'bonsais/b1'), { ownerUid: 'alice' });
    });
    await assertSucceeds(getDoc(doc(alice, 'bonsais/b1')));
  });

  test('non-owner cannot read', async () => {
    const bob = env.authenticatedContext('bob').firestore();
    await assertFails(getDoc(doc(bob, 'bonsais/b1')));
  });

  test('cannot reassign ownerUid', async () => {
    const alice = env.authenticatedContext('alice').firestore();
    await assertFails(updateDoc(doc(alice, 'bonsais/b1'), { ownerUid: 'bob' }));
  });
});
```

Cobertura completa documentada em `test-strategy.yaml > firestore-rules-tests`
— ver fragment desse card.

### 4. Deploy strategy

```
npx -y firebase-tools@latest deploy --only firestore:rules,firestore:indexes
```

- **Proibido** deploy manual via console Firebase.
- CI roda após merge em `main`:
  1. Suite de rules tests no emulator (verde obrigatório).
  2. Deploy em `bonsai-meo-dev`.
  3. Smoke test pós-deploy (canary doc).
  4. Em tag de release, deploy em `bonsai-meo` (prod).

Mudanças breaking (mudar `read` aberto para ownership; mudar `ownership-pattern`)
exigem plano de roll-out documentado em `open-questions.md`.

### 5. Cross-doc updates obrigatórios (mesma PR)

| Doc | Quando atualizar |
|---|---|
| `firestore.rules` | Toda mudança em path/operação. |
| `docs/specs/data/access-matrix.md` | Toda linha de actor × path × op afetada. |
| `docs/specs/data/security-and-threat-model.md` | Todo threat coberto/descoberto. |
| `docs/specs/data/firestore-data-model.md` | Schema novo ou modificado. |
| `docs/specs/data/query-catalog.md` | Query nova com `list` requirements. |
| `firestore.indexes.json` | Composite index novo (para `list` com múltiplos `where`/`orderBy`). |

Validator `check-firestore-rules-coverage` valida cross-references em CI.

### 6. Threat checklist (security-and-threat-model.md)

Para cada collection mexida, enumerar pelo menos os 4 threats clássicos:

| Threat | Mitigação típica |
|---|---|
| **IDOR (read)** | `resource.data.ownerUid == request.auth.uid` no `allow get`. |
| **Escalation via update** | `preservesOwner()` no `allow update`; nunca permitir mudar `ownerUid`. |
| **Enumeration via list** | Cliente DEVE filtrar por `ownerUid`; rule `allow list: if isAuthed();` confia no filtro porque `list` sem filtro = exfil. |
| **Exfil via export** | Custom Audit no Firebase + alertas (fora do escopo deste card; documentar em threat-model). |

Cada threat tem 1 entrada em `security-and-threat-model.md` + 1 caso
`deny` na suite de testes.

### 7. Threading / performance

- Rules não rodam no cliente — sem impact em main thread.
- `get(/databases/.../X)` dentro de rule conta como leitura paga +
  serializa. **Evitar** em rule hot-path; preferir field-based
  ownership (lê doc 1× via `resource.data.ownerUid`).

### 8. Hook local (post-edit)

`hooks/post-edit-firestore-rules.sh` (Phase 5) re-roda
`firebase-rules-unit-testing` contra emulator quando `firestore.rules` é
editado. Commit bloqueado se algum teste quebra.

### 9. Integração com outros cards

| Card | Interação |
|---|---|
| `firestore-persistence` | Pré-requisito (`requires: persistence-server`). Cada collection do data-contract aparece em rules. |
| `firestore-realtime` | Listener (`addSnapshotListener`) usa `allow list`; teste cobre listener + filtro `where`. |
| `firebase-auth` | Rules referenciam `request.auth.uid` e custom claims; ambos declarados em `access-matrix.md`. |
| `firebase-storage` | Storage tem rules separadas (`storage.rules`) — não confundir. |
