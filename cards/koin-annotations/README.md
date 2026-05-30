# Card — `koin-annotations`

> **Categoria:** `dependency-injection` · **Maturidade:** `stable`
> **Provides:** `dependency-injection`, `kmp-di`, `android-di`
> **Requires:** `kotlin`
> **Conflicts-with:** _(vide FOLLOWUP)_

DI canônica para projetos **Kotlin Multiplatform + Android** baseada em
[Koin Annotations](https://insert-koin.io/docs/reference/koin-annotations/start)
(KSP). Substitui a DSL imperativa `module { ... }` por declaração
anotada em build-time. iOS e Web não rodam Koin runtime (JVM-only) e
consomem cada feature via factory functions `create{ClassName}()`.

---

## Por que este card existe

A regra de DI deste projeto é **uma só estratégia, anotações apenas**:

- `@Module` + `@ComponentScan("pkg.raiz")` por módulo Gradle
- `@Single` para Service, Repository, Mapper, Analytics
- `@Factory` para UseCase, RouteEntry, mappers stateful
- `@KoinViewModel` apenas em código Android (`composeApp`, `androidApp:feature:*`)
- DSL `module { ... }` **proibida em produção** — só em `commonTest`/`androidUnitTest`
- iOS/Web: factory functions `create{ClassName}()` em `di/{Feature}Factory.kt`

O card empacota essa convenção em contribuições que o forge injeta nos
agentes (`tech-spec-agent`, `task-contract-writer`), nos templates de
documento (`tech-spec.md`, `task-contract.yaml`) e em um validador que
roda em `pre-commit` / `verify-task`.

---

## Capacidades

| Capability             | Significado                                                 |
|------------------------|-------------------------------------------------------------|
| `dependency-injection` | Estratégia geral de DI do projeto                           |
| `kmp-di`               | DI específica para shared layer KMP                         |
| `android-di`           | DI específica para módulos Android                          |

Este card é **exclusivo** dessas capacidades. Quando os cards `hilt-di` e
`koin-dsl` forem adicionados ao catálogo v1, devem ser declarados aqui em
`conflicts-with`. Hoje o catálogo não os possui — ver FOLLOWUP abaixo.

---

## Contribuições

### Templates

| Target              | Section                          | Merge mode         | Arquivo                                  |
|---------------------|----------------------------------|--------------------|------------------------------------------|
| `tech-spec.md`      | `DI Strategy`                    | `append-section`   | `templates/di-tech-spec-section.md`      |
| `task-contract.yaml`| `allowed-files-koin-modules`     | `merge-keys`       | `templates/koin-allowed-files.yaml`      |

### Agent prompts

| Agent                  | Extension point             | Arquivo                                          |
|------------------------|-----------------------------|--------------------------------------------------|
| `tech-spec-agent`      | `section:Shared (KMP) layer`| `agent-contributions/tech-spec-additions.md`     |
| `task-contract-writer` | `after:Allowed Files`       | `agent-contributions/task-writer-additions.md`   |

### Validators

| Nome                       | Runs-on                  | Severidade | Descrição                                                 |
|----------------------------|--------------------------|------------|-----------------------------------------------------------|
| `validate-koin-modules`    | `pre-commit`, `verify-task` | `error`  | Pareia `@Module` ↔ `@ComponentScan` e bane DSL em produção |

### Config defaults

| Chave                               | Valor                                       |
|-------------------------------------|---------------------------------------------|
| `conventions.di-pattern`            | `koin-annotations`                          |
| `conventions.di.ios-pattern`        | `factory-function create{ClassName}()`      |
| `conventions.di.web-pattern`        | `factory-function create{ClassName}()`      |

---

## Detecção

`forge init` ativa este card automaticamente quando a soma de confidence
dos sinais abaixo atinge **0.6**:

| Sinal                                    | Confidence |
|------------------------------------------|------------|
| `**/*.kt` contém `@Module`               | 0.4        |
| `**/*.kt` contém `@ComponentScan`        | 0.4        |
| `**/build.gradle*` contém `koin-annotations` | 0.5    |
| `**/*.kt` contém `@KoinViewModel`        | 0.2        |

Detecção alternativa: `koin-dsl` (se aparecer `single { ... }` sem
anotações) e `hilt-di` (se aparecer `@HiltAndroidApp`).

---

## Estrutura física no projeto

Quando o card está ativo, espera-se a seguinte estrutura para cada feature
shared module:

```
shared/feature/{name}/src/commonMain/kotlin/.../feature/{name}/di/
├── {Feature}Module.kt    # @Module @ComponentScan("...feature.{name}")
└── {Feature}Factory.kt   # object com factory functions create{ClassName}()
```

Exemplo mínimo de `{Feature}Module.kt`:

```kotlin
package io.gentalha.code.meobonsai.feature.auth.di

import org.koin.core.annotation.ComponentScan
import org.koin.core.annotation.Module

@Module
@ComponentScan("io.gentalha.code.meobonsai.feature.auth")
class AuthModule
```

Exemplo de `{Feature}Factory.kt` (consumido por iOS):

```kotlin
object AuthFactory {
    fun createLoginViewModel(networkMonitor: NetworkMonitor): LoginViewModel {
        val service = AuthServiceImpl()
        val repository = AuthRepositoryImpl(service)
        val useCase = LoginUserUseCase(repository)
        return LoginViewModel(useCase, networkMonitor)
    }
}
```

---

## Regras invioláveis (enforced pelo validator)

1. `@Module` sem `@ComponentScan` no mesmo arquivo → `error`
2. `module { ... }` DSL em qualquer source set de produção
   (`commonMain`, `androidMain`, `iosMain`, `jvmMain`, `jsMain`, `main`) → `error`
3. _(roadmap)_ `@KoinViewModel` em `commonMain` → futuro `error`
4. _(roadmap)_ `org.koin.*` em código Swift/TS → futuro `error`

Os itens 3 e 4 estão marcados como `TODO Phase 5` no validator stub
(`validators/check-koin-modules.py`).

---

## Como o card é consumido em um feature package

Durante `forge plan` → Wave A–D, o conductor invoca agentes nesta ordem:

1. **`tech-spec-agent`** lê o fragment injetado em `section:Shared (KMP) layer`
   e produz a subseção **DI Strategy** com tabela de componentes, anotações,
   arquivos e plataformas consumidoras.
2. **`task-contract-writer`** lê o fragment em `after:Allowed Files` e:
   - lista `*Module.kt` e `*Factory.kt` concretos em `allowed_files`
   - anexa as validations `koin-module-componentscan-pair` e
     `koin-dsl-banned-in-production` à task
3. **`forge verify`** executa o validator `validate-koin-modules` antes de
   marcar a task como concluída.

---

## Relacionamento com regras do projeto

O card alinha-se a `.claude/rules/architecture_kmp.md` (§DI — Koin Annotations
APENAS) e `.claude/rules/architecture_android.md` (§DI). Mudanças no
canonical do card devem ser propagadas para as regras (ou vice-versa) na
mesma PR — ver `documentation.rules-link`.

---

## FOLLOWUPs

- **`conflicts-with` vazio hoje.** O catálogo v1 ainda não declara labels
  para `hilt-di` nem `koin-dsl`. Quando esses cards forem criados, adicionar
  aqui:
  ```yaml
  conflicts-with:
    - hilt-di
    - koin-dsl
    - manual-di
  ```
- **Validator stub.** A versão atual usa busca textual com regex. Phase 5
  deve migrar para parsing AST (tree-sitter Kotlin ou `kotlinc -Xfir`) para
  cobrir corretamente comentários, strings literais e `@ComponentScan`
  sem string literal.
- **Cobertura de `@KoinViewModel`/`org.koin.*` cross-platform.** Hoje o
  validator não detecta `@KoinViewModel` em `commonMain` nem `org.koin.*`
  em Swift/TS. Adicionar nas próximas iterações.

---

## Histórico

| Versão | Data       | Mudança                                                |
|--------|------------|--------------------------------------------------------|
| 1.0.0  | 2026-05-29 | Card inicial. Contribuições para tech-spec + task-writer. |
