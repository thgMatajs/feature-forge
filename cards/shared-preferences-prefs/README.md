# shared-preferences-prefs

Provider **legacy** de `local-prefs-storage` baseado em `android.content.SharedPreferences`.
Coexiste com `datastore-prefs` (provider canônico moderno) — mas init
Step 7.5 surfaca 3-caminhos quando ambos detectados, porque este card
carrega `legacy-marker: true`.

## Status legacy

`legacy-marker: true` significa que detection deste card por si só não é
sinal de escolha arquitetural ativa — é evidência de código pré-existente.
Recomendação para projetos novos: ative `datastore-prefs` em vez deste.
Para projetos com base instalada, este card existe para destravar `forge
init` sem mentir sobre a stack atual.

## Quando este card aparece sem o moderno

Stack é majoritariamente legacy. Caminho recomendado:

1. Aceitar o card no init (`forge init` opção "manter legacy").
2. Abrir tarefa de migração separada — feature-forge não força migração.
3. Quando migrar, rodar `forge reconfigure → remover card` (.bak retention
   7d preserva o snapshot).

## Quando coexiste com `datastore-prefs`

Init Step 7.5 surfaca:

```
Detectei dois providers de local-prefs-storage:
  · shared-preferences-prefs  (legacy)
  · datastore-prefs           (moderno)

Três caminhos:
  1) Manter ambos (transição in-flight, código novo usa DataStore)
  2) Migrar tudo pra DataStore (gera nota em TODO.md)
  3) Manter só SharedPreferences (assume escolha consciente)
```

Sem auto-fix — escolha humana.

## Detection

Threshold canônico 0.6, igual aos demais cards v1.1. Confidence individual
por signal calibrada ligeiramente menor que `datastore-prefs` equivalente —
reflete que evidência de SharedPreferences em codebase moderno é
tipicamente legacy, não escolha ativa.
