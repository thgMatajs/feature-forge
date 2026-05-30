<!--
  Fragment injetado no `task-contract-writer` no extension-point
  `after:Allowed Files`. Ativo quando o card `firestore-security-rules`
  está presente em workflow-config.yaml > cards.active.

  Objetivo: garantir que toda task que toque rules de Firestore liste
  explicitamente os arquivos permitidos (firestore.rules, indexes, 4-docs)
  e inclua os validators de coverage + tests como gates.
-->

## Card contribution — `firestore-security-rules` (Task allowed_files + gates)

Quando uma task altera ou introduz acesso a collection Firestore,
o `task-contract.yaml` deve obedecer o template abaixo.

### Allowed files (patterns concretos)

Anexe os patterns abaixo ao `task.allowed_files`. Liste paths
**concretos**, não wildcards — a task só pode tocar o que está listado.

```yaml
task:
  allowed_files:
    # Security rules + indexes (sempre que toca collection)
    - "firestore.rules"
    - "firestore.indexes.json"

    # 4-source-of-truth do projeto (atualização sincronizada obrigatória)
    - "docs/specs/data/firestore-data-model.md"
    - "docs/specs/data/query-catalog.md"
    - "docs/specs/data/access-matrix.md"
    - "docs/specs/data/security-and-threat-model.md"

    # Suite de testes de rules
    - "tests/firestore-rules/firestore-rules.test.ts"
    # OU equivalente Kotlin/Swift:
    # - "tests/firestore-rules/FirestoreRulesTest.kt"
    # - "iosApp/tests/FirestoreRulesTests.swift"

    # Helpers de teste (fixtures, factories de doc)
    - "tests/firestore-rules/fixtures/{Feature}Fixtures.ts"

    # Data contract da feature (referencia rule-ref em cada collection)
    - "features/{name}/data-contract-spec.yaml"
```

### Forbidden patterns

```yaml
task:
  forbidden_patterns:
    - description: "Rule open-access (`allow read, write: if true;`) em produção."
      match-glob: "firestore.rules"
      regex-must-not-contain: "allow\\s+(read|write|get|list|create|update|delete)[^;]*if\\s+true\\s*;"

    - description: "Rule de read autorizando apenas com `request.auth != null` (sem ownership)."
      match-glob: "firestore.rules"
      regex-must-not-contain: "allow\\s+(read|get|list)\\s*:\\s*if\\s+request\\.auth\\s*!=\\s*null\\s*;"
      exceptions:
        # `list` pode autorizar com apenas auth desde que cliente filtre por ownerUid
        # (documentado em query-catalog.md). Excecionar com comentário acima da rule.

    - description: "Update permitindo mudar `ownerUid` (preserves-owner invariant)."
      match-glob: "firestore.rules"
      regex-must-not-contain: "allow\\s+update[^}]*;\\s*//\\s*owner-mutable"
      # Marcador `// owner-mutable` é proibido — sinaliza tentativa explícita de
      # permitir mudança de ownership, o que nunca deveria passar review.

    - description: "Deploy de rules invocado via script ad-hoc (sem firebase-tools versionado)."
      match-glob: "**/*.{sh,ts,js,kt}"
      regex-must-not-contain: "firebase\\s+deploy\\s+--only\\s+firestore"
      exceptions:
        - ".github/workflows/**"
        - "scripts/ci/**"
```

### Validations (gates)

Toda task que toca rules precisa rodar os validators como gates:

```yaml
task:
  validations:
    - id:       firestore-rules-coverage
      command:  "python3 .claude/cards/firestore-security-rules/validators/check-firestore-rules-coverage.py --feature {name}"
      runs-on:  [verify-task]
      severity: error
      description: "Toda collection mexida em data-contract precisa ter rule equivalente em firestore.rules."

    - id:       firestore-rules-tests
      command:  "python3 .claude/cards/firestore-security-rules/validators/check-firestore-rules-tests.py"
      runs-on:  [verify-task]
      severity: error
      description: "Toda rule precisa ter teste correspondente em firebase-rules-unit-testing (allow + deny matrix)."

    - id:       firestore-rules-emulator-tests
      command:  "npx -y firebase-tools@latest emulators:exec --only firestore 'npm test -- firestore-rules'"
      runs-on:  [verify-task]
      severity: error
      description: "Suite de rules tests precisa passar contra emulator local."
```

### Task categories (sugestão de breakdown)

| Categoria | Quando criar | Exemplo |
|---|---|---|
| `firestore-rules-update` | Mudança em rule existente OU rule nova | `T-NNN — firestore.rules para bonsai collection` |
| `firestore-rules-tests`  | Suite nova ou casos novos para rule existente | `T-NNN — rules tests bonsai (allow/deny matrix)` |
| `access-matrix-update`   | Atualização sincronizada dos 4 docs | `T-NNN — access-matrix + threat-model para bonsai` |
| `firestore-indexes`      | Composite index novo (acompanha `list` query nova) | `T-NNN — composite index bonsais by ownerUid + createdAt` |

Cada categoria vira task separada — **não juntar rules + tests + docs
numa task só.** Cada uma tem allowed_files e gates próprios.

### Gates obrigatórios

```yaml
task:
  gates:
    - firestore-rules-coverage         # error — sempre
    - firestore-rules-tests            # error — sempre
    - firestore-rules-emulator-tests   # error — sempre que a task toca firestore.rules
    - access-matrix-sync               # error — toda mudança em rules atualiza access-matrix.md
    - validate-koin-modules            # se card koin-annotations ativo
    - detekt                           # se a task tocar shared/**/*.kt
```

### Cross-doc invariants

Toda PR que toca `firestore.rules` **DEVE** ter diff em:

1. `firestore.rules`
2. `docs/specs/data/access-matrix.md`
3. `tests/firestore-rules/*.test.ts` (ou equivalente)

PR sem os 3 é bloqueada por `firestore-rules-coverage`. Excecionar
apenas em refactor puro (renomear helper) e justificar no commit
message.
