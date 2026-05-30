<!--
  Template fragment contribuído por: kmp-shared
  Target: tech-spec.md
  Merge: append-section após §3 "Shared (KMP) layer"
-->

### 3.5 Cross-Platform Layer — convenções do shared

Esta subseção é injetada pelo card `kmp-shared` e padroniza decisões de
camada compartilhada. Preencha os blocos abaixo com base no PRD + data-
contract-spec; não deixe campo em branco — registre `n/a` quando não
aplicável e justifique em §13 (Risks + open questions).

#### Camadas e pacotes

```
shared/feature/{slug}/src/commonMain/kotlin/.../feature/{slug}/
├── data/          (dto, service, mapper, repository impl)
├── domain/        (model, repository interface, usecase)
├── presentation/  (viewmodel, ui model, ui events)
└── di/            ({Slug}Module.kt + {Slug}Factory.kt)
```

| Camada | Imports permitidos | Imports proibidos |
|---|---|---|
| `domain/` | kotlinx (datetime, coroutines), tipos do próprio domain | qualquer coisa de `data/`, `presentation/`, Firebase, Ktor |
| `data/` | kotlinx, domain, Firebase/Ktor/Room | `presentation/` |
| `presentation/` | kotlinx, domain | DTOs de `data/`, providers diretos |

#### Tabela de UseCases

| UseCase | Assinatura | Camada de retorno |
|---|---|---|
| `{Verb}{Noun}UseCase` | `Flow<T>` se alimenta StateUI; `suspend` se fire-and-forget | Domain |

#### Tabela de Dispatchers injetados

| Componente | Dispatcher | Justificativa |
|---|---|---|
| `{Slug}RepositoryImpl` | `Dispatchers.IO` | Firebase/Ktor/Room — I/O |
| `{Slug}Mapper` (parse grande) | `Dispatchers.Default` | CPU-bound |
| ViewModel updates | `Dispatchers.Main` (default `viewModelScope`) | UI |

#### `expect/actual` (apenas se necessário)

Liste explicitamente. Se vazio, escreva "Nenhum — feature 100% common".

#### DI wiring

- Common: `@Module @ComponentScan("...feature.{slug}")` em `di/{Slug}Module.kt`.
- iOS/Web: factory function `create{Slug}ViewModel(...)` em `di/{Slug}Factory.kt`.

#### Cenários BDD obrigatórios cobertos no shared

- [ ] Happy path
- [ ] Null/empty input (default no mapper)
- [ ] Network/IO failure → `StateUI.Error`
- [ ] Loading guard (ação durante loading não dispara repository de novo)
- [ ] Unknown/unexpected value → fallback seguro
