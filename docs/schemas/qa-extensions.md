# `qa-extensions` — campo aditivo em `card.yaml`

> Documenta o campo top-level **opcional** `qa-extensions:` que cards (canon
> ou locais) usam pra contribuir auditores ao verbo `forge qa`. Adição é
> aditiva — `schema-version` permanece `1`, mesma política do
> `legacy-marker` (Gap 5).
>
> Voz: mentor calmo. Fonte canônica: `docs/superpowers/specs/2026-06-05-forge-qa-design.md` §6.3 + §8.

---

## Posição no schema

`qa-extensions:` é campo top-level opcional em `card.yaml`, paralelo a
`identity`, `provides`, `requires`, `legacy-marker` etc. Sua presença
**não** bumpa `schema-version` — segue valendo `schema-version: 1`. Cards
existentes (canon e locais) que não declaram `qa-extensions` continuam
válidos sem mexer.

Promoção a `schema-version: 2` só aconteceria em mudança breaking
(remoção de campo, mudança de tipo, novo required). Acréscimo aditivo
como este NÃO conta. É a mesma regra que regeu a entrada de
`legacy-marker` em v1.1 — ver `card.md §Optional top-level legacy-marker`.

---

## Shape YAML (exemplo canônico)

```yaml
# cards/<card-name>/card.yaml — trecho top-level
# (campos identity, provides, requires, contributes já existentes acima)

qa-extensions:
  auditors:
    - name: "visual-fidelity"               # único cross canon ∪ local
      phase: "static"                       # enum strict: "static" | "generative"
      contributes:
        agents:
          - "auditor-visual-fidelity.md"   # path relativo ao diretório do card
        config-defaults:
          enabled: true                    # vira default em workflow-config qa.extensions.<name>
      requires:
        - "screens-defined"                # capability que precisa estar ativa no overlay
```

Múltiplos auditores num único card são permitidos — ver §8.1 do spec pra
exemplo de card canon (`screens-defined`) estendendo com dois auditores
(um `static`, um `generative`).

---

## Field semantics

### `auditors[]`

Lista (array YAML) de auditores que este card adiciona ao pool de QA. Cada
entrada é um objeto com as chaves abaixo. Lista vazia (`auditors: []`) é
permitida mas inútil — equivalente a não declarar o campo.

### `name` (string, required)

Identificador único do auditor **cross canon ∪ local**. É a chave que o
`forge qa` usa pra reportar findings, pra `qa.extensions.disabled`
desativar por nome, e pra cascade detection de colisão. Convenção: slug
`[a-z0-9-]+`, descritivo do vetor adversarial (ex.: `visual-fidelity`,
`screen-state-coverage`, `analytics-event-coverage`).

Colisão de `name` entre dois cards quaisquer (canon×canon, canon×local,
local×local) é **hard fail** no loader — ver §Compatibilidade Gap 5 abaixo.

### `phase` (string enum, required)

Enum estrito com exatamente dois valores permitidos:

- `"static"` — auditor roda na Phase 1 (análise estática de specs/código
  congelados em snapshot). Sem subprocess, sem fixtures geradas.
- `"generative"` — auditor roda na Phase 2 (geração de fixtures
  adversariais que serão executadas no sandbox da Phase 3).

Qualquer outro valor (ex.: `"sandbox"`, `"synthesis"`, `"ingest"`,
`"emit"`) é rejeitado. **Phase 0 (ingest), Phase 3 (sandbox), Phase 4
(synthesis) e Phase 5 (emit) são reservadas ao core** — engine
determinístico, dispatch fixo, sem contribuição externa. Cards estendem
**apenas** onde mentalidade adversarial vive.

### `contributes.agents[]` (list of strings, required)

Lista de prompts de agente (arquivos `.md`) que materializam este
auditor. Cada entrada é um path **relativo ao diretório do card**.
Convenção: prompts vivem em `<card-dir>/agent-contributions/<file>.md`,
seguindo o pattern já usado por `legacy-marker` e overlay Gap 5.

Cada arquivo referenciado **deve existir** — validator faz check de
existência. Ausência = hard fail.

### `contributes.config-defaults` (object, optional)

Mapa chave-valor que injeta defaults em `workflow-config.yaml` sob
`qa.extensions.<auditor-name>`. Exemplo: se o card declara

```yaml
config-defaults:
  enabled: true
  strictness: "strict"
```

…então `forge init` materializa em `workflow-config.yaml`:

```yaml
qa:
  extensions:
    <auditor-name>:
      enabled: true
      strictness: "strict"
```

Time pode sobrescrever via `forge reconfigure`. Defaults são apenas
sementes — não impõem comportamento runtime.

### `requires[]` (list of strings, required se não-vazio)

Lista de **capability labels** que precisam estar declaradas no catálogo
ativo (canon ∪ local overlay) pra que este auditor possa rodar. Mesma
semântica de `requires:` no top-level do card — usa o catálogo
canônico de `docs/schemas/capability-labels.md` cruzado com
`.claude/inventory/capability-labels.local.yaml` (Gap 5 overlay).

Se uma capability requerida não está ativa no projeto consumidor, o
auditor é silenciosamente pulado em `forge qa` (sem erro — falta de
capability ≠ falha de QA). Pode declarar `requires: []` se o auditor não
depende de nada além do snapshot.

---

## Regras de validação (`validate_qa_extensions.py`)

São **cinco regras**, enforced pelo validator overlay-aware
`validate_qa_extensions.py` (carregado pela cascade default de
`forge verify` e pelo `engine/cards/loader.py` no startup).

### Regra 1 — `name` único cross canon ∪ local

Colisão de `name` entre dois cards quaisquer = **hard fail** no loader.
Mesma policy do Gap 5 (Decisão 28, Approach A): cascade canon ∪ local
sem merge silencioso, sem override.

A mensagem de erro do hard fail aponta ambos os paths — canon **e** local
(ou os dois canon / os dois local) — pra que o operador veja imediatamente
quem está em conflito:

```
🛑 qa-extensions name collision: "visual-fidelity"
   canon: cards/screens-defined/card.yaml (linha 42)
   local: .claude/cards/local/custom-screens/card.yaml (linha 28)
```

Sem auto-resolve, sem prompt de merge. Operador decide qual fica via
edit de um dos cards (renomear ou remover o auditor duplicado).

### Regra 2 — `phase ∈ {"static", "generative"}`

Enum estrito. Qualquer outro valor = hard fail no validator com mensagem
listando os dois valores aceitos. Phase 0/3/4/5 são core-only — não
podem ser estendidas por cards.

### Regra 3 — `contributes.agents` referenciados existem

Cada path declarado em `contributes.agents[]` deve resolver pra arquivo
existente relativo ao diretório do card. Convenção:
`<card-dir>/agent-contributions/<file>.md`.

Ausência de qualquer arquivo referenciado = hard fail. Não é warning —
auditor sem prompt é auditor inutilizável.

### Regra 4 — `requires` capabilities existem no catálogo

Cada capability label em `requires[]` deve estar declarada no catálogo
canônico (`docs/schemas/capability-labels.md`) **ou** no overlay local
(`.claude/inventory/capability-labels.local.yaml`, Gap 5). Mesma checagem
que `validate_capability_labels.py` já faz pra `requires:` top-level do
card — helper compartilhado em `validators/_common.py` (mandamento de
reuso #3).

Label desconhecida = hard fail no validator com mensagem indicando se a
label é parecida com alguma existente (sugestão de typo) ou se precisa
ser promovida ao catálogo via ADR.

### Regra 5 — `qa.extensions.disabled` desativa por nome (sem erro)

Em `workflow-config.yaml`, a lista `qa.extensions.disabled: [<nome>, ...]`
permite ao time desativar auditores específicos por nome — útil pra
contextos onde QA roda mas com subset reduzido (ex.: time decide pular
`visual-fidelity` em PRs de backend).

Auditor desativado **não dispara erro** — fica registrado em
`.planning/qa/<run-id>/audit/skipped.log` com motivo `"disabled in
workflow-config"`. Esta regra é a única das cinco que **não** é hard fail:
é toggle runtime, não validação de shape.

---

## Compatibilidade Gap 5 (Decisão 28)

Cards locais (`.claude/cards/local/<name>/card.yaml`) podem declarar
`qa-extensions:` **exatamente como cards canon**. O loader trata os dois
de forma simétrica: cascade canon primeiro, local segundo, com **hard
fail em colisão de `name`** — sem merge silencioso, sem override.

Esta é a mesma política Approach A da Decisão 28 que já rege capability
labels overlay e `legacy-marker`. Em uma frase:

> Colisão de nome de auditor entre canon e local = **hard fail no
> loader**, sem auto-resolve, sem prompt — operador renomeia ou remove
> manualmente.

O validator `validate_qa_extensions.py` nasce overlay-aware: segue o
pattern de `validate_card_yaml.py` e `validate_capability_labels.py`,
overlay-aware desde Gap 5 (registrado em `docs/design/07-discipline.md
§2`).

---

## env-needs (opcional, since v1.2 — QA-11)

Lista de env vars que o card declara precisar no subprocess do sandbox.

```yaml
qa-extensions:
  env-needs:
    - GITHUB_TOKEN      # bate pattern sensitive → exige grant
    - JAVA_HOME         # non-sensitive → passa direto
```

### Semântica

- Cada item é o nome literal da env var (case-sensitive no lookup).
- Vars **non-sensitive** (não batem `SENSITIVE_PATTERN` —
  `TOKEN|SECRET|PASSWORD|AUTH|CREDENTIAL|API_KEY|PRIVATE_KEY`,
  case-insensitive) são injetadas direto no subprocess sem prompt.
- Vars **sensitive** disparam prompt 3-caminhos pro user no momento de
  `forge init` ou `forge reconfigure` (não no momento de `forge qa`).
- Grant é persistido em `workflow-config.qa.sensitive-env-grants` —
  per-projeto, não per-card. Mesma var declarada por 2 cards = prompt
  único pro user.

### Regras de validação (validator: validate_qa_extensions.py)

| Regra | Comportamento |
|---|---|
| Tipo deve ser `list[str]` | shape errado → `QAExtensionsValidationError` |
| Item non-string | raise com índice + tipo recebido |
| Item vazio ou com whitespace interno | raise |
| Var sensitive sem grant | NÃO rejeita em load-time; runtime (init/reconfigure) dispara grant |

### Cross-refs

- Grant flow: `engine/cards/grant.py`
- Storage: `docs/schemas/workflow-config.md §qa.sensitive-env-grants`
- Spec: `docs/superpowers/specs/2026-06-08-qa-sandbox-env-hardening-design.md`

---

## Cross-refs

| Tópico | Arquivo |
|---|---|
| Schema base do card (campos identity / provides / etc.) | [`card.md`](card.md) |
| Pattern de campo aditivo (precedente do `legacy-marker`) | [`card.md` §Optional top-level legacy-marker](card.md) |
| Section `qa:` em workflow-config (inclui `qa.extensions.disabled`) | [`workflow-config.md` §qa](workflow-config.md) |
| Validator que enforça as 5 regras | `validators/validate_qa_extensions.py` |
| Catálogo canônico de capability labels (cruzado pela Regra 4) | [`capability-labels.md`](capability-labels.md) |
| Decisão 28 — Gap 5 overlay policy (origem do hard-fail em colisão) | [`docs/design/01-decisions.md` §Decisão 28](../design/01-decisions.md) |
| Overlay do conductor que carrega contribuições (§11) | `agents/qa-conductor.md` |
| Spec canônica do verbo `forge qa` (fonte deste schema) | `docs/superpowers/specs/2026-06-05-forge-qa-design.md` §6.3 + §8 |
