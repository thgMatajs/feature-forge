<!--
  Injetado em: task-contract-writer
  Extension-point: after:Allowed Files
  Card: kmp-shared
-->

## kmp-shared — task split por camada e `allowed_files`

O shared module exige split de tarefas por camada (Data → Domain →
Presentation), nessa ordem. Cada TASK fica isolada em sua camada — não
misture mapper com ViewModel no mesmo TASK.

### Ordem canônica de tarefas para uma feature no shared

1. **DTO + Service** — `dto/`, `service/` (sem mapper ainda).
2. **Domain models + Repository interface** — `domain/model/`, `domain/repository/`.
3. **Mapper + RepositoryImpl** — `data/mapper/`, `data/repository/`.
4. **UseCases** — `domain/usecase/` (um TASK por UseCase quando >3 UseCases).
5. **UI Model + ViewModel** — `presentation/model/`, `presentation/viewmodel/`.
6. **DI wiring** — `di/{Feature}Module.kt` ou `di/{Feature}Factory.kt`.

A ordem é determinística: cada TASK depende apenas das camadas anteriores.

### `allowed_files` patterns por tipo de TASK

Inclua **apenas** o pattern correspondente à camada do TASK. Não permita
que um TASK de Data toque arquivos de Presentation.

```yaml
# TASK de Data layer (DTO + Service + Mapper + RepositoryImpl)
allowed_files:
  - "shared/feature/{slug}/src/commonMain/kotlin/**/data/**/*.kt"
  - "shared/feature/{slug}/src/commonTest/kotlin/**/data/**/*.kt"

# TASK de Domain layer
allowed_files:
  - "shared/feature/{slug}/src/commonMain/kotlin/**/domain/**/*.kt"
  - "shared/feature/{slug}/src/commonTest/kotlin/**/domain/**/*.kt"

# TASK de Presentation layer
allowed_files:
  - "shared/feature/{slug}/src/commonMain/kotlin/**/presentation/**/*.kt"
  - "shared/feature/{slug}/src/commonTest/kotlin/**/presentation/**/*.kt"

# TASK de DI wiring
allowed_files:
  - "shared/feature/{slug}/src/commonMain/kotlin/**/di/**/*.kt"
```

### Bloqueios automáticos

- TASK que declara `category: shared-data` mas inclui `**/presentation/**`
  em `allowed_files` → reject.
- TASK que cria arquivo fora do pacote da feature (`shared/feature/{slug}/`)
  sem promoção explícita em §14 do tech-spec (Cross-feature reusability) →
  reject. Promoção para `shared/core/` exige TASK dedicado.
- TASK de ViewModel sem TASK de UseCase prévio na mesma `task-breakdown` →
  reject (presentation não pode existir sem domain).
