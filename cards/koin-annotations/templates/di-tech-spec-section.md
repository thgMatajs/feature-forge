<!--
  Template fragment contribuído pelo card `koin-annotations`.
  Merge mode: append-section em tech-spec.md sob "DI Strategy".

  O agente tech-spec-agent inclui este conteúdo quando o card está ativo.
  Edição manual deste arquivo é mudança de canonical — propague via
  `forge reconfigure` → "atualizar card do canonical".
-->

## DI Strategy — Koin Annotations (KMP + Android)

A estratégia de DI desta feature usa **Koin Annotations** (KSP), nunca a DSL
imperativa `module { ... }` em código de produção. Toda a configuração é
declarada via anotações; o compilador gera o módulo Koin em build-time.

### Componentes por escopo

| Anotação            | Quando usar                                       | Escopo            |
|---------------------|---------------------------------------------------|-------------------|
| `@Single`           | Repository, Service, Mapper, Analytics            | Singleton no scope |
| `@Factory`          | UseCase, RouteEntry, mappers stateful             | Nova instância por consumidor |
| `@KoinViewModel`    | ViewModel **Android-only** (composeApp/feature)   | Lifecycle do ViewModelStoreOwner |
| `@Module`           | Classe contêiner por módulo Gradle                | Combina com `@ComponentScan` |
| `@ComponentScan`    | Diz ao KSP qual pacote varrer                     | 1 por `@Module`   |

### Estrutura física obrigatória

```
shared/feature/{name}/src/commonMain/kotlin/.../feature/{name}/di/
├── {Feature}Module.kt    # @Module @ComponentScan("...feature.{name}")
└── {Feature}Factory.kt   # factory functions create{ClassName}() para iOS/Web
```

- `{Feature}Module.kt` declara **uma única classe** com `@Module` e
  `@ComponentScan` apontando para o pacote da feature. Nada além.
- `{Feature}Factory.kt` é um `object` com funções `create{ClassName}()`
  que montam manualmente o grafo (Service → Repository → UseCase → ViewModel)
  para consumo por iOS e Web — Koin runtime é JVM-only.

### Regras invioláveis

1. **DSL `module { ... }` proibida em código de produção.** Permitida apenas em
   `commonTest`/`androidUnitTest` para isolar test doubles.
2. **`@Module` sem `@ComponentScan` é erro.** O validador
   `validate-koin-modules` bloqueia commits que violem essa regra.
3. **iOS/Web nunca importam `org.koin.*`.** Toda construção de dependência
   acontece via factory functions; Koin runtime não roda fora da JVM.
4. **`@KoinViewModel` nunca aparece em `commonMain`.** Fica em
   `androidApp/feature/{name}/` ou em source set `androidMain` se a feature
   compartilhar o ViewModel apenas com Android.
5. **Composição por módulo Gradle, não por feature lógica.** Cada Gradle
   module (`shared:feature:auth`, `shared:feature:bonsai`, ...) declara
   exatamente um `{Feature}Module` no pacote `di/`.

### Carga dos módulos

No host Android (`composeApp`):

```kotlin
startKoin {
    androidContext(this@MeoBonsaiApp)
    modules(
        AppModule().module,
        AuthModule().module,
        BonsaiFeatureModule().module,
        // ...
    )
}
```

A extension `.module` é gerada pelo KSP a partir das classes `@Module`.

### Bridge iOS / Web

iOS (`iosApp`) e Web (`webApp`) consomem a feature exclusivamente via
factory functions:

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

A factory referencia o mesmo grafo concreto consumido pelo Android, garantindo
paridade de comportamento entre plataformas.
