<!--
  Fragment injetado no `contract-planner-agent` no extension-point
  `section:Data Contract`. Ativo quando o card `firestore-security-rules`
  está presente em workflow-config.yaml > cards.active.

  Objetivo: garantir que toda feature que toca Firestore produza um bloco
  `firestore-collections` no data-contract-spec.yaml com cobertura de rules
  declarada explicitamente, e que os 4 docs do MeoBonsai
  (firestore-data-model, query-catalog, access-matrix, security-and-threat-model)
  sejam atualizados na mesma PR.
-->

## Card contribution — `firestore-security-rules`

Quando a feature toca Firestore (leitura ou escrita em qualquer
collection), o `data-contract-spec.yaml` precisa declarar **cobertura
formal de security rules**. Não é opcional, não é "depois" — é parte
do contrato de dados.

### 1. Inventário obrigatório por collection

Para cada collection (top-level ou sub-collection) mexida pela feature,
emita entrada em `firestore-collections`:

```yaml
firestore-collections:
  - id:               bonsais
    path:             "bonsais/{bonsaiId}"
    operations:       [get, list, create, update, delete]
    ownership-pattern: field-based       # OU path-based
    ownership-field:   "ownerUid"        # quando field-based
    rule-ref:          "firestore.rules#bonsais"
    access-matrix-ref: "docs/specs/data/access-matrix.md#bonsais"
    threat-model-ref:  "docs/specs/data/security-and-threat-model.md#bonsai-collection"
    list-query-filter-required: "where('ownerUid', '==', request.auth.uid)"
```

Operações granulares: `get`, `list`, `create`, `update`, `delete`. **Não
use `read`/`write` aberto** sem justificativa documentada em
`access-matrix.md` — o validator `check-firestore-rules-coverage` reporta
ambiguidade.

### 2. Source of truth — 4-doc cross-reference

Toda mudança em collection Firestore exige atualização sincronizada dos
4 docs do MeoBonsai (ou equivalentes do projeto consumidor):

| Doc | O que atualizar |
|---|---|
| `firestore-data-model.md` | Schema do documento (campos, tipos, sub-collections). |
| `query-catalog.md` | Queries usadas (incluindo filtros obrigatórios para passar nas rules). |
| `access-matrix.md` | Linha por path: actor × operação × condição. |
| `security-and-threat-model.md` | Threats considerados (IDOR, escalation, enumeration, exfil) + mitigações. |

Cada entrada de `firestore-collections` **DEVE** referenciar os 4 docs
(via `*-ref` field). PR sem updates sincronizados é bloqueada por
`check-firestore-rules-coverage`.

### 3. Padrão de ownership (escolher um por collection)

| Padrão | Quando |
|---|---|
| **Path-based** | Doc vive em sub-collection escopada por uid (`users/{uid}/...`). Rule: `request.auth.uid == uid`. |
| **Field-based** | Doc top-level com `ownerUid` no body. Rule: `resource.data.ownerUid == request.auth.uid`. |

**Não misturar dentro da mesma collection.** Se a feature precisa de
ambos (raro), levantar em `open-questions.md` antes de planejar.

### 4. List queries — filtro obrigatório no cliente

Rules **não conseguem** inspecionar o `where` do query — a defesa contra
exfil é exigir que o cliente filtre por `ownerUid`. Declare o filtro
obrigatório em `list-query-filter-required` e referencie em
`query-catalog.md`. Teste de rules valida que query sem filtro **falha**.

### 5. Custom claims (se aplicável)

Se a feature usa custom claims (admin, moderator, etc.):

```yaml
firestore-collections:
  - id:           moderation-queue
    path:         "moderation/{itemId}"
    operations:   [get, list, update]
    custom-claims-required:
      - "role == 'moderator'"
      - "OR role == 'admin'"
    access-matrix-ref: "..."
```

Claims declarados em `access-matrix.md` — nada de claim mágico sem doc.

### Pegadinhas a flagar em `open-questions.md`

- Collection mexida sem `ownership-pattern` definido? → pergunte path-based
  ou field-based; **não invente**.
- Operação `list` sem `list-query-filter-required`? → como o cliente
  filtra? Sem filtro = exfil.
- Mudança de rules existente que pode quebrar usuários ativos? → plano
  de roll-out (feature flag, dual-write, etc.).
- Cross-user read autorizado (ex.: foto compartilhada)? → como autorizar?
  signed URL? campo de allowlist no doc? Cloud Function?
- Custom claim novo não declarado em `access-matrix.md`? → pare. Custom
  claim sem doc é débito permanente.

### Default behavior quando este card não está ativo

Se o card `firestore-security-rules` está fora do projeto, o
`contract-planner-agent` não exige `firestore-collections[].rule-ref` —
mas avisa que a feature pode estar abrindo path sem autorização. Para
projetos Firestore-based, ativar o card é fortemente recomendado.
