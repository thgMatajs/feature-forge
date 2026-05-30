<!--
  Template fragment contribuído pelo card `firestore-security-rules`.
  Merge mode: append-section em tech-spec.md sob "Security Rules — Firestore".

  Ativo quando o card está em workflow-config.yaml > cards.active.
  Edição manual deste arquivo é mudança de canonical — propague via
  `forge reconfigure` → "atualizar card do canonical".
-->

## Security Rules — Firestore

A feature autoriza acesso a Firestore via **rules declarativas** em
`firestore.rules`. Toda collection mexida pela feature precisa ter rule
correspondente atualizada na **mesma PR**, com testes
(`firebase-rules-unit-testing`) e atualização sincronizada de
`docs/specs/data/access-matrix.md` + `security-and-threat-model.md`.

### 1. Inventário de paths/operações cobertos

Liste explicitamente cada path Firestore tocado pela feature e quais
operações precisam de rule. Operações granulares: `get`, `list`, `create`,
`update`, `delete`. Evitar `read` / `write` aberto sem justificativa
documentada em `access-matrix.md`.

| Collection / sub-collection | Operações | Padrão de ownership | Rule ref |
|---|---|---|---|
| `bonsais/{bonsaiId}` | get, list, create, update, delete | field-based (`ownerUid`) | `firestore.rules#bonsais` |
| `users/{uid}/sessions/{sessionId}` | get, list, create, delete | path-based (uid no path) | `firestore.rules#user-sessions` |

### 2. Padrão de ownership (escolher um por collection)

| Padrão | Quando usar | Forma da rule |
|---|---|---|
| **Path-based** | Doc vive em sub-collection escopada por uid (`users/{uid}/...`). | `allow read: if request.auth != null && request.auth.uid == uid;` |
| **Field-based** | Doc top-level com `ownerUid` no body. | `allow read: if request.auth != null && resource.data.ownerUid == request.auth.uid;` |

**Não misture os dois padrões na mesma collection.** Documente a escolha
em `access-matrix.md` — mistura silenciosa é fonte recorrente de bug de
autorização.

### 3. Forma canônica de rule por operação

```
match /databases/{database}/documents {
  match /bonsais/{bonsaiId} {
    function isOwner() {
      return request.auth != null
          && resource.data.ownerUid == request.auth.uid;
    }
    function isCreatingAsOwner() {
      return request.auth != null
          && request.resource.data.ownerUid == request.auth.uid;
    }
    function preservesOwner() {
      return request.resource.data.ownerUid == resource.data.ownerUid;
    }

    allow get:    if isOwner();
    allow list:   if request.auth != null;  // filtros adicionais no query (vide query-catalog.md)
    allow create: if isCreatingAsOwner();
    allow update: if isOwner() && preservesOwner();
    allow delete: if isOwner();
  }
}
```

Helpers (`isOwner`, `preservesOwner`, etc.) ficam **no topo do bloco
`match`** — não duplicar entre collections; promover para função global
quando reutilizada em 3+ collections.

### 4. List queries (cuidado especial)

`allow list` cobre **toda query** que retorna documentos. Para impedir
exfil, **a query precisa filtrar pelo `ownerUid`** — rules não conseguem
inspecionar o `where` do cliente, então a defesa é mandar o cliente
incluir `where("ownerUid", "==", request.auth.uid)`. Documente o filtro
obrigatório em `query-catalog.md` e teste com cliente sem o filtro
(deve falhar).

### 5. Custom claims (quando aplicável)

Se a feature usa roles via custom claims (admin, moderator), referenciar
explicitamente:

```
function isAdmin() {
  return request.auth != null
      && request.auth.token.role == 'admin';
}
```

Claims declarados em `access-matrix.md` — nada de claim mágico sem doc.

### 6. Testes (firebase-rules-unit-testing)

Suite obrigatória em `firestore-rules.test.ts` (ou `.kt` se o projeto
preferir kotlin-test + emulator). Cobertura mínima:

- 1 `allow` por operação declarada (5 cases base por collection).
- 1 `deny` por threat declarado em `security-and-threat-model.md`
  (cross-user read, escalation via update mudando `ownerUid`,
  enumeration via `list` sem filtro).
- 1 `deny` anônimo (`request.auth == null`) para cada operação.

```typescript
test('user cannot read another user bonsai', async () => {
  const alice = testEnv.authenticatedContext('alice').firestore();
  await assertFails(getDoc(doc(alice, 'bonsais/bob-bonsai')));
});
```

Suite roda contra emulator local (`:8080`) — CI executa antes do deploy
de rules. Sem teste = sem rule (validator `check-firestore-rules-tests`
bloqueia).

### 7. Deploy + roll-out

```
npx -y firebase-tools@latest deploy --only firestore:rules,firestore:indexes
```

- **Proibido** deploy manual via console Firebase — quebra versionamento.
- CI roda o comando acima após merge em `main`, com smoke tests em
  `bonsai-meo-dev` antes de promover para prod (`bonsai-meo`).
- Mudanças breaking (mudar `read` aberto para ownership) precisam de plano
  de roll-out documentado em `open-questions.md` antes do merge.

### 8. Cross-doc updates (mesma PR)

Toda mudança em `firestore.rules` exige update sincronizado de:

- `docs/specs/data/access-matrix.md` — adicionar/remover linha por path.
- `docs/specs/data/security-and-threat-model.md` — atualizar threats
  cobertos pela nova rule.
- `docs/specs/data/firestore-data-model.md` — se a collection é nova.
- `docs/specs/data/query-catalog.md` — se houver `list` com filtros novos.

PR sem esses updates é bloqueada pelo validator
`check-firestore-rules-coverage`.

### 9. Hook local (post-edit)

Sempre que o desenvolvedor edita `firestore.rules`, o hook
`post-edit-firestore-rules.sh` (Phase 5) re-roda a suite
`firebase-rules-unit-testing` contra o emulator. Falha = commit
bloqueado.
