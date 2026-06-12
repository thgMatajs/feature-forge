<!--
  Template fragment contribuído por: firebase-remote-config
  Target: tech-spec.md
  Merge: append-section "Feature flags (Firebase Remote Config)"
-->

## Feature flags (Firebase Remote Config)

Esta seção é injetada pelo card `firebase-remote-config` e padroniza
naming + fetch lifecycle de flags.

### Naming canônico

| Padrão | Exemplo | Quando |
|---|---|---|
| `feature_<name>_enabled` | `feature_payments_enabled` | Toggle binário. |
| `experiment_<name>_variant` | `experiment_onboarding_variant` | A/B test. |
| `config_<scope>_<key>` | `config_pricing_max_amount` | Config tunável. |

### Fetch lifecycle

| Ambiente | `minimumFetchIntervalInSeconds` |
|---|---|
| Dev | `0` (sempre busca fresh). |
| Prod | `3600` (1h — default conservador). |

```kotlin
val rc = Firebase.remoteConfig.apply {
    setConfigSettingsAsync(remoteConfigSettings {
        minimumFetchIntervalInSeconds = if (BuildConfig.DEBUG) 0 else 3600
    })
    setDefaultsAsync(R.xml.remote_config_defaults)
}
rc.fetchAndActivate()
```

### Defaults XML

Toda flag DEVE ter default em `res/xml/remote_config_defaults.xml` —
nunca depender exclusivamente do fetch remoto (offline-safe).

### Audiences

Quando o card `firebase-analytics` está ativo, audiences definidas no
Analytics ficam disponíveis em condições de rollout do Remote Config —
configurar via Firebase Console.
