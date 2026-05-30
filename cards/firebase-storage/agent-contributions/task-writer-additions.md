<!--
  Fragment injetado no `task-contract-writer` no extension-point
  `after:Allowed Files`. Ativo quando o card `firebase-storage` está
  presente em workflow-config.yaml > cards.active.

  Objetivo: garantir que toda task que toque Storage liste explicitamente
  os paths permitidos (repositories, services, storage.rules) e inclua a
  validação `check-storage-rules-coverage` em `gates`.
-->

## Card contribution — `firebase-storage` (Task allowed_files + gates)

Quando uma task envolve upload/download/delete em Firebase Storage, o
`task-contract.yaml` deve obedecer o template abaixo.

### Allowed files (patterns concretos)

Anexe os patterns abaixo ao `task.allowed_files`. Liste paths **concretos**,
não wildcards — a task só pode tocar o que está listado.

```yaml
task:
  allowed_files:
    # Repository + Service (shared)
    - "shared/feature/{name}/src/commonMain/kotlin/.../data/storage/{Feature}StorageService.kt"
    - "shared/feature/{name}/src/commonMain/kotlin/.../data/storage/{Feature}StorageServiceImpl.kt"
    - "shared/feature/{name}/src/commonMain/kotlin/.../data/repository/{Feature}StorageRepositoryImpl.kt"
    - "shared/feature/{name}/src/commonMain/kotlin/.../domain/repository/{Feature}StorageRepository.kt"

    # Use cases que orquestram upload/download
    - "shared/feature/{name}/src/commonMain/kotlin/.../domain/usecase/Upload{Asset}UseCase.kt"
    - "shared/feature/{name}/src/commonMain/kotlin/.../domain/usecase/Get{Asset}UseCase.kt"

    # Sealed class de error
    - "shared/feature/{name}/src/commonMain/kotlin/.../domain/model/StorageError.kt"

    # Image compression shim (expect/actual)
    - "shared/core/src/commonMain/kotlin/.../core/platform/ImageCompressor.kt"
    - "shared/core/src/androidMain/kotlin/.../core/platform/ImageCompressor.android.kt"
    - "shared/core/src/iosMain/kotlin/.../core/platform/ImageCompressor.ios.kt"

    # Security rules
    - "storage.rules"

    # Testes
    - "shared/feature/{name}/src/commonTest/kotlin/.../data/storage/{Feature}StorageServiceFake.kt"
    - "shared/feature/{name}/src/commonTest/kotlin/.../data/repository/{Feature}StorageRepositoryImplTest.kt"
```

### Forbidden patterns

```yaml
task:
  forbidden_patterns:
    - description: "Import direto do SDK Firebase Storage fora de data/storage/."
      match-glob: "**/src/{commonMain,androidMain,iosMain}/**/*.kt"
      regex-must-not-contain: "com\\.google\\.firebase\\.storage"
      exceptions:
        - "**/data/storage/**"

    - description: "Path literal sem `{userId}` no primeiro segmento."
      match-glob: "**/src/commonMain/**/*.kt"
      regex-must-not-contain: "(?i)(\\.reference|StorageReference)\\([\"'](?!\\$\\{?(uid|userId)).*[\"']\\)"

    - description: "useEmulator() em código de release."
      match-glob: "**/src/{commonMain,androidMain,iosMain}/**/*.kt"
      regex-must-not-contain: "useEmulator\\(.*\\)"
      exceptions:
        - "**/src/*/kotlin/.../data/storage/*ServiceImpl.kt"  # init { if (isDebug) ... }
```

### Validations (gates)

Toda task que toca Storage precisa rodar o validator de coverage como gate:

```yaml
task:
  validations:
    - id:       storage-rules-coverage
      command:  "python3 .claude/cards/firebase-storage/validators/check-storage-rules-coverage.py --feature {name}"
      runs-on:  [verify-task]
      severity: error
      description: "Todo path de Storage usado em código deve ter rule equivalente em storage.rules."

    - id:       storage-paths-match-data-contract
      command:  "python3 .claude/cards/firebase-storage/validators/check-storage-rules-coverage.py --feature {name} --strict"
      runs-on:  [verify-task]
      severity: warn
      description: "Paths em storage.rules que não estão declarados em data-contract-spec.yaml emitem warning."
```

### Task categories (sugestão de breakdown)

| Categoria  | Quando criar | Exemplo |
|---|---|---|
| `storage-service`    | Wrapper SDK + fake test | `T-NNN — BonsaiStorageService + Fake` |
| `storage-repository` | Repository + compression + error mapping | `T-NNN — BonsaiStorageRepositoryImpl` |
| `storage-rules`      | Atualização de `storage.rules` + emulator tests | `T-NNN — storage.rules para bonsai photos` |
| `image-compressor`   | Apenas quando feature usa imagem **e** o shim ainda não existe | `T-NNN — ImageCompressor (expect/actual)` |

Cada categoria vira uma task separada — não juntar Service+Rules numa só.

### Gates obrigatórios

```yaml
task:
  gates:
    - storage-rules-coverage     # error — sempre que toca storage.rules ou repository
    - validate-koin-modules      # se o card koin-annotations também ativo
    - swift-style                # se a task tocar iosApp/**
    - detekt                     # se a task tocar shared/**/*.kt
```
