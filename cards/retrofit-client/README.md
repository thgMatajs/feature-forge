# retrofit-client

Provider canônico de `http-client` baseado em Retrofit2 (`com.squareup.retrofit2`).
Cobre projetos Android-only e o lado Android de KMP quando Ktor multiplatform
não é a escolha — Android-only é semântica derivada dos signals, não campo
declarativo.

## Quando usar este card

- Projeto Android-only com REST API tradicional
- Projeto KMP onde Android usa Retrofit e iOS usa Ktor/URLSession por outro card
- Migration in-flight saindo de OkHttp puro → Retrofit + converter

## Quando NÃO usar

- Projeto KMP que escolheu Ktor multiplatform como cliente único — ative
  `ktor-client` (declarado em `conflicts-with` deste card).
- iOS-only sem lado Android.

## Convenções herdadas

- `conventions.network.http-client: retrofit`
- `conventions.network.converter: kotlinx-serialization`

Override via `forge reconfigure → conventions` quando o projeto usa Moshi/Gson.

## Detection

Card ativa quando confidence cumulativa ≥ 0.6 sobre os 3 signals declarados
em `detection/signals.yaml`. Threshold canônico — sem desvio do default v1.1.
