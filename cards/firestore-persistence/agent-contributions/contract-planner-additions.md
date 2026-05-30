<!--
  Injetado em: contract-planner-agent
  Extension-point: section:firestore-collections
  Card: firestore-persistence
-->

## firestore-persistence — instruções para `data-contract-spec.yaml`

O bloco `firestore-collections:` é o **contrato de dados** desta feature
para operações **CRUD one-shot, queries custom e batch writes**. Listeners
realtime (snapshot) são responsabilidade do card `firestore-realtime` —
se a feature usa listener, esse outro card injeta sua própria subseção.
Security rules ficam em `firestore-security-rules`.

Não inferir, não fabricar — extrair do PRD/screen-analysis e perguntar ao
usuário quando faltar.

### Regras de preenchimento

1. **Uma entrada por coleção tocada** — leitura, escrita ou query one-shot.
   Coleção que a feature apenas "usa o doc já existente em memória" também
   conta (precisa de rule de read).
2. **`doc-shape.fields` tem que estar completo** — nome, type, nullable,
   owned-by (server/user/admin), sensitivity (public/user-private/privileged).
   Campo sem owned-by → bloqueia, força elicitation.
3. **`operations[]` cobre create/read/update/delete one-shot usados pela
   feature** — omitir uma operação por desconhecimento é erro. Cada operação:
   - `actor`: role/claim/uid esperado em `request.auth`
   - `bdd-ref`: scenario id no `bdd.md` que exercita esta op
   - `security-rules-ref`: bloco em `firestore.rules` que cobre essa op
     (validado pelo card `firestore-security-rules`)
4. **`queries[]` lista TODA query custom one-shot** — filtros compostos,
   `orderBy + where`. Cada query referencia um índice (existente ou a criar)
   em `firestore.indexes.json`. Queries com listener → não entram aqui;
   entram no bloco contribuído por `firestore-realtime`.
5. **`batch-writes`** — declarar quando a feature usa `WriteBatch` (até 500
   ops) ou `runTransaction` (read-modify-write atômico) entre múltiplos
   documentos. Justificar atomicidade.

### Cross-references obrigatórias com a 4-source-of-truth

Para cada coleção, o bloco `cross-references` aponta para a âncora da entrada
correspondente em:

- `docs/specs/data/firestore-data-model.md`
- `docs/specs/data/query-catalog.md`
- `docs/specs/data/access-matrix.md`
- `docs/specs/data/security-and-threat-model.md`

Esses quatro documentos são **referência viva** do projeto. Se a feature
mexe em coleção/query/índice/regra e algum desses arquivos não tem entrada
correspondente, isso é **bloqueio**: registrar como
`needs-elicitation: true` no `open-questions.md` e parar — o tech-spec não
pode prosseguir sem essas âncoras.

### Sinalize no `notes` quando aplicável

- Coleção mexida sem entrada em `access-matrix.md` → bloqueia tech-spec.
- Query custom sem índice declarado → bloqueia o contrato (validator
  `check-firestore-indexes` é warn na build, mas missing entry no contrato
  é erro de planning).
- Batch/transaction sem justificativa de atomicidade → red flag (pode ser
  N writes independentes acidentalmente "embrulhados").
- Coleção referenciada por listener → confirmar que o card
  `firestore-realtime` está ativo e que a query foi declarada no bloco
  realtime, não aqui.

### Mini-exemplo de bloco preenchido (CRUD one-shot)

```yaml
firestore-collections:
  - name: "users/{uid}/bonsais"
    description: "Coleção privada por usuário dos bonsais cadastrados."
    doc-shape:
      fields:
        id:         { type: string,    nullable: false, owned-by: server, sensitivity: public }
        owner_uid:  { type: string,    nullable: false, owned-by: server, sensitivity: user-private }
        species:    { type: string,    nullable: true,  owned-by: user,   sensitivity: public }
        created_at: { type: timestamp, nullable: false, owned-by: server, sensitivity: public }
    operations:
      - { op: create, actor: "auth.uid", bdd-ref: "bonsai_create_happy",
          security-rules-ref: "firestore.rules:match /users/{uid}/bonsais/{id}.create" }
      - { op: read,   actor: "auth.uid == uid", bdd-ref: "bonsai_detail_load",
          security-rules-ref: "firestore.rules:match /users/{uid}/bonsais/{id}.read" }
    queries:
      - id: "list-by-owner-recent"
        where:    [{ field: owner_uid, op: "==", value: "auth.uid" }]
        order-by: [{ field: created_at, direction: desc }]
        limit: 50
        index-ref: "users-bonsais-owner-created"
        bdd-ref: "bonsai_list_initial_load"
    batch-writes:
      uses-batch: false
      uses-transaction: false
    cross-references:
      data-model-doc:    "docs/specs/data/firestore-data-model.md#users-bonsais"
      query-catalog-doc: "docs/specs/data/query-catalog.md#list-by-owner-recent"
      access-matrix-doc: "docs/specs/data/access-matrix.md#users-bonsais"
      threat-model-doc:  "docs/specs/data/security-and-threat-model.md#users-bonsais"
```
