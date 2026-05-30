<!--
  Injetado em: task-contract-writer
  Extension-point: after:Allowed Files
  Card: firestore-persistence
-->

## firestore-persistence — additions para `task-contract.yaml`

Ao decompor a feature em tasks, adicionar os patterns/validações abaixo
QUANDO a task toca Firestore em **CRUD/queries one-shot/batch writes**.
(Listeners realtime → card `firestore-realtime`; rules → card
`firestore-security-rules`.)

### 1. `allowed_files` — patterns adicionais

Tasks de data layer (Firestore one-shot/CRUD) tipicamente tocam estes
paths. Listar como patterns globais — o validador `check-allowed-files`
cobre por glob.

```yaml
allowed_files:
  # Repositórios (Kotlin / shared)
  - "shared/**/data/repository/*Repository*.kt"
  - "shared/**/data/repository/*RepositoryImpl.kt"

  # DTOs Firestore
  - "shared/**/data/dto/*Response.kt"
  - "shared/**/data/dto/*Request.kt"

  # Mappers DTO ↔ Domain
  - "shared/**/data/mapper/*Mapper.kt"

  # Índices — toda query nova com compound where/orderBy
  - "firestore.indexes.json"

  # iOS: tipos espelho (se a feature usa Swift bridging extra)
  - "iosApp/**/Repositories/*.swift"
```

> NÃO inclua `firestore.rules` aqui — esse arquivo é gerenciado pelo card
> `firestore-security-rules` e ele contribui o próprio `allowed_files`
> separadamente.

### 2. `validations` — steps adicionais

```yaml
validations:
  - name: "firestore-indexes"
    command: "<validators/check-firestore-indexes.py>"
    blocks-merge: false      # warn — devs precisam ver, mas não trava merge
    runs-on: [verify-task]

  - name: "firestore-emulator-crud-tests"
    command: "npx -y firebase-tools@latest emulators:exec --only firestore '<runner>'"
    blocks-merge: true
    runs-on: [pre-commit, ci]
    description: "Testes CRUD/queries one-shot rodando contra Firestore Emulator."
```

### 3. `task-categories` — tipo extra

Adicionar a categoria `backend-e2e` quando a feature toca Firestore CRUD:

```yaml
task-categories:
  - id: backend-e2e
    description: "Testes CRUD/queries one-shot contra Firestore Emulator validando shapes, índices e mappers."
    blocks-merge: true
```

### 4. Atualização da 4-source-of-truth como task explícita

Quando a feature mexe em coleção/query/índice/regra, a task-contract precisa
incluir uma task de documentação:

```yaml
tasks:
  - id: "<feature>-data-docs"
    title: "Atualizar a 4-source-of-truth de dados"
    description: |
      Atualizar na MESMA PR:
        - docs/specs/data/firestore-data-model.md
        - docs/specs/data/query-catalog.md
        - docs/specs/data/access-matrix.md
        - docs/specs/data/security-and-threat-model.md
    allowed_files:
      - "docs/specs/data/firestore-data-model.md"
      - "docs/specs/data/query-catalog.md"
      - "docs/specs/data/access-matrix.md"
      - "docs/specs/data/security-and-threat-model.md"
    blocks-merge: true
```

A omissão dessa task quando a feature mexe em dados é red flag explícito —
o `readiness-reviewer` rejeita.

### 5. Boundary com cards complementares

Se a task envolve **listener realtime** → contribuição vem do card
`firestore-realtime` (allowed_files dele cobre paths específicos de
listener). Se envolve **edição de `firestore.rules`** → contribuição vem
do card `firestore-security-rules`. Esses cards rodam validators próprios
(coverage de rules; lifecycle de listener); este card aqui não duplica.
