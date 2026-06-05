# Cyclomatic Complexity Gate — Design Spec

> Data: 2026-06-03 · Status: aprovado (brainstorm)
> Próximo passo: writing-plans → implementation
> Voz: mentor calmo · Escopo: v1.2 (sem revisitar decisões locked)

## Sumário executivo

feature-forge tem 14 validators que cobrem escopo, contracts, behavior e
artefatos. Falta uma borda: complexidade ciclomática (CC) de código
implementado. Hoje, um agente pode aplicar `forge implement` numa task,
gerar uma função com `cc=24` e passar por todo o cascade — o gate
estrutural não existe. Resultado: débito técnico entra via subagent
sem fricção, e o orchestrator-mantenedor só descobre em review humano.

Este spec consolida o design de um novo gate — `check_cyclomatic_complexity`
— que roda em dois pontos: cascade de `forge verify` (gate de feature
inteira pré-merge) e per-task em `forge implement` (gate por commit
atômico). O gate usa ferramenta nativa por linguagem (Detekt/SwiftLint/
eslint-complexity/Radon), separa funções novas das modificadas (regra
delta: modificada não piora), resolve threshold via precedência card >
workflow-config > defaults, e emite a mensagem canônica 3-caminhos
quando bloqueia (refactor / override-justify-no-commit / split-task).

Escopo: v1.2. Validator único multi-language em
`validators/check_cyclomatic_complexity.py`, ~350-450 LOC. Sem revisitar
decisões locked. Sem novo card, sem novo template, sem novo comando.

## Resumo das decisões do brainstorm

Seis decisões locked durante o brainstorm de 2026-06-03 — cinco via
`AskUserQuestion` (ambiguidades), uma arquitetural (estrutura do
validator). Tabela canônica:

| Eixo | Decisão | Alternativas rejeitadas |
|---|---|---|
| Lifecycle | Combo — roda em `forge verify` cascade **e** per-task em `forge implement` | Só verify (perde sinal por task) · só implement (perde gate pré-merge agregado) |
| Cálculo CC | Ferramenta nativa por linguagem (Detekt · SwiftLint · eslint-complexity · Radon) | Parser Python custom (reinventa roda) · uma única tool cross-language (não existe com qualidade) |
| Escopo | Diff + delta combinado — novas funções obedecem N absoluto; modificadas não pioram | Só diff absoluto (penaliza funções legacy intocadas) · só delta (funções novas com cc=30 passam) |
| Threshold N | `workflow-config.yaml` com defaults por linguagem + override per-card | Hardcoded constante (não respeita projeto) · flag CLI (viola Decision 10) |
| On-fail | 3-caminhos — Refactor / Override-justify-no-commit / Split-task | Auto-fail rígido (sem escape válido pra DSL/state machine) · whitelist persistente (cria débito invisível) |
| Arquitetura | Validator único multi-language (`validators/check_cyclomatic_complexity.py` ~350-450 LOC) | 4 validators (um por linguagem — quadruplica boilerplate de cascade) · plugin system (overengineering pra v1.2) |

Nenhuma destas decisões toca as 8 load-bearing — confirmado em §5
abaixo. Nenhuma exige "Revisita decisão N" no CHANGELOG.

## Seção 1 — Componentes e arquivos novos

Mapa completo de arquivos tocados na implementação. Lista exaustiva,
sem ambiguidade — `writing-plans` consome isso direto.

### Novos arquivos

- `validators/check_cyclomatic_complexity.py` (NOVO, ~350-450 LOC) —
  validator principal, multi-language.
- `engine/_cc_configs/detekt.yml` (NOVO) — config interno Detekt
  forge-managed.
- `engine/_cc_configs/swiftlint.yml` (NOVO) — config interno SwiftLint
  forge-managed.
- `engine/_cc_configs/eslint.json` (NOVO) — config interno eslint
  forge-managed.
- `engine/_cc_configs/radon.cfg` (NOVO) — config interno Radon
  forge-managed.
- `tests/validators/test_check_cyclomatic_complexity.py` (NOVO) —
  unit tests do validator.
- `tests/integration/test_cc_gate_end_to_end.py` (NOVO) — integration
  tests cascade + per-task.

### Arquivos modificados (append, sem reescrita)

- `validators/_common.py` (APPEND) — helpers `cc_threshold_lookup` e
  `cc_format_three_paths`.
- `engine/verify.py` (APPEND) — registra novo validator na cascade,
  após `check_no_invented_behavior`.
- `engine/implement.py` (APPEND) — invoca validator pós-Apply Mode,
  entre review e commit.
- `engine/doctor.py` (APPEND) — nova categoria `cc-gate-tools` na
  health check (12 → 13 categorias).
- `docs/schemas/workflow-config.md` (APPEND) — documenta bloco
  `cc-gate:` (defaults + ignore-paths + enabled).
- `docs/schemas/card.md` (APPEND) — documenta campo opt-in
  `cc-gate-override`.
- `cards/<card-name>/card.yaml` (OPT-IN, schema only) — não toca cards
  existentes; documenta o campo pra adoção futura.
- `docs/design/04-pending.md` (APPEND) — registra 5 risks/open
  questions deferidos (listados em §5).
- `docs/design/07-discipline.md` (APPEND) — §2 cascade ganha entrada
  do novo validator após `check_no_invented_behavior`.
- `CHANGELOG.md` (Unreleased ### Added) — entrada do gate.
- `README.md` (Stats) — validators 14→15, tests ~+20.
- `docs/design/08-session-handoff.md` (Última atualização) — refletir
  shipping do gate.

### O que NÃO muda

- Sem novo card. Nenhum dos 20 cards canônicos é tocado pela
  implementação.
- Sem novo template. Nenhum dos 18 templates é tocado.
- Sem mudar `engine/cli.py` — sem comando novo, sem flag nova,
  Decision 10 preservada.
- Sem nova decisão locked. Cada um dos 6 eixos do brainstorm encaixa
  em decisões já existentes (Decision 23 cascade, Decision 22 zero
  runtime dep, Decision 10 zero flags, Decision 19 Python core).
- Sem mexer em `agents/*.md`. Subagent não precisa saber do gate —
  validator roda no engine.

## Seção 2 — Data flow + threshold resolution

### Pipeline interno do validator (11 passos)

Quando `check_cyclomatic_complexity.run(context)` é invocado (por
cascade ou per-task), executa em ordem:

```
┌──────────────────────────────────────────────────────────────────┐
│ 1. Coleta staged files                                           │
│    git diff --cached --name-only (ou diff vs HEAD em verify)     │
│                                                                  │
│ 2. Filtra por extensão suportada                                 │
│    .kt .swift .ts .tsx .py                                       │
│    Demais → ignorados silenciosos                                │
│                                                                  │
│ 3. Para cada arquivo: extrai linhas tocadas                      │
│    Hunks do diff (start_line, end_line por hunk)                 │
│                                                                  │
│ 4. Resolve threshold por linguagem                               │
│    Precedência: card cc-gate-override > workflow-config > default│
│                                                                  │
│ 5. Detecta cards ativos da feature                               │
│    Lê feature_dir/cards/ pra saber quais cards aplicam           │
│                                                                  │
│ 6. Aplica override per-card se houver match                      │
│    Card especifica { language: { threshold, justification } }    │
│                                                                  │
│ 7. Agrupa arquivos por linguagem → invoca tool por grupo         │
│    Detekt p/ todos .kt juntos; SwiftLint p/ todos .swift; etc.   │
│                                                                  │
│ 8. Cada tool emite JSON; normaliza pra CCResult comum            │
│    (file, function, line_start, line_end, cc, lang, status,     │
│     cc_before)                                                  │
│                                                                  │
│ 9. Classifica cada função: new | modified | unchanged            │
│    Match via diff hunks ∩ função range                           │
│                                                                  │
│ 10. Aplica regra de fail                                         │
│     · new      → fail se cc > N                                  │
│     · modified → fail se cc_after > cc_before                    │
│     · unchanged → ignorada (não está no diff)                    │
│                                                                  │
│ 11. Se ≥1 fail → emite 3-caminhos + retorna result_fail          │
│     Senão → retorna result_pass                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Threshold lookup (pseudocódigo)

Precedência **card > workflow-config > defaults**. Card vence porque
representa contexto específico (ex.: card de Composable Compose com
DSL aninhado tem CC inflacionado por design). Workflow-config vence
default porque representa decisão do projeto. Defaults só pra projeto
sem nada configurado.

```python
DEFAULTS = {"kotlin": 10, "swift": 10, "ts": 15, "python": 10}

def cc_threshold_lookup(language: str,
                        active_cards: list[CardYaml],
                        workflow_config: dict) -> int:
    # 1. Card override — primeiro card com match wins (determinístico)
    for card in active_cards:
        override = card.get("cc-gate-override", {}).get(language)
        if override and "threshold" in override:
            return int(override["threshold"])

    # 2. Workflow-config — bloco cc-gate
    cc_block = workflow_config.get("cc-gate", {})
    if language in cc_block:
        return int(cc_block[language])

    # 3. Default por linguagem
    return DEFAULTS[language]
```

Múltiplos cards conflitando: **primeiro card com override wins**
(ordem determinística do listing). Não é "max" nem "min" — é "primeiro",
porque card listing tem semântica de prioridade declarada pelo
usuário. Documentado em `cc-gate-override` schema.

### Shape de `workflow-config.yaml` — bloco `cc-gate`

```yaml
cc-gate:
  enabled: true
  kotlin: 10
  swift: 10
  ts: 15
  python: 10
  ignore-paths:
    - "src/test/.*"
    - ".*\\.generated\\..*"
```

Notas:
- `enabled: false` desliga o validator inteiro (warn, não fail). Útil
  pra projeto migrando ou em estágio inicial.
- Threshold por linguagem é inteiro positivo. Valor 0 ou negativo →
  validator interpreta como `degraded` (config errada).
- `ignore-paths` é lista de regexes Python (`re.search`). Aplicada
  após filtro de extensão.

### Shape de card override

```yaml
# em cards/<card-name>/card.yaml
cc-gate-override:
  kotlin:
    threshold: 15
    justification: "Composable functions com DSL aninhado inflacionam CC"
```

`justification` é **obrigatória** quando override é declarado. Sem
justification → validator emite warning ("override sem rationale —
adicione justification ou remova"). Auditável via grep nos cards.

### Detecção new vs modified

A regra delta exige saber `cc_before` quando função foi modificada.
Mecânica:

- Pra cada função detectada no estado staged, validator executa tool
  uma segunda vez sobre o blob de `HEAD`.
- Match por **nome + assinatura** (parâmetros tipados onde a linguagem
  suporta). Sem match em `HEAD` → função é `new`.
- Match em `HEAD` → função é `modified` (mesmo se range de linhas
  mudou — body pode ter crescido sem cruzar o threshold).
- Rename detection: `git diff -M80%` (similarity > 80%) → trata
  `cc_before` como CC da função no path antigo. Match ambíguo
  (similarity 60-80%) → trata como `new` (conservador — pior dos
  mundos é forçar refactor desnecessário, melhor que deixar passar
  regressão).

Funções deletadas no diff: ignoradas (sem cc_after pra comparar).

## Seção 3 — Tool dispatch e normalização

### As 4 tools nativas

| Linguagem | Tool | Comando exato | Output |
|---|---|---|---|
| Kotlin | Detekt | `detekt --input <files> --config engine/_cc_configs/detekt.yml --report json:<tmp>` | JSON com `CyclomaticComplexMethod` issues |
| Swift | SwiftLint | `swiftlint --reporter json --config engine/_cc_configs/swiftlint.yml <files>` | JSON com regra `cyclomatic_complexity` |
| TS/JS | eslint | `eslint --rule 'complexity: [error, {max: <N>}]' --format json <files>` | JSON `messages[]` da regra `complexity` |
| Python | Radon | `radon cc -j -n F <files>` | JSON per-function CC |

Notas por tool:

- **Detekt** — config interno `detekt.yml` desabilita todas as regras
  exceto `CyclomaticComplexMethod`. Threshold é passado via CLI args
  (não estático no config) porque varia por feature/card.
- **SwiftLint** — config interno `swiftlint.yml` segue mesma lógica:
  só a regra `cyclomatic_complexity` ativa. Threshold via CLI flag
  (`--strict` + override em `included_rules`).
- **eslint** — não usa config-file, usa `--rule` inline. Mais simples;
  não interfere com config eslint do projeto consumidor.
- **Radon** — JSON output já tem CC por função; sem threshold built-in
  (validator compara em Python depois).

### Struct comum normalizada

Tools emitem formatos diferentes. Validator normaliza pra:

```python
@dataclass(frozen=True)
class CCResult:
    file: str           # path relativo ao repo
    function: str       # nome + assinatura quando disponível
    line_start: int     # 1-indexed
    line_end: int
    cc: int             # cyclomatic complexity do estado staged
    language: str       # "kotlin" | "swift" | "ts" | "python"
    status: str         # "new" | "modified" | "unchanged"
    cc_before: int | None  # None se status="new"
```

Parsers individuais (um por tool) em
`validators/check_cyclomatic_complexity.py` convertem do shape nativo
de cada tool pra `CCResult`. Lista de `CCResult` é o input universal
do step 10 (aplicação da regra).

### Configs internos `engine/_cc_configs/`

Decisão deliberada: configs ficam **dentro do engine**, não em
`.claude/` do projeto consumidor. Justificativa:

- Forge controla o contrato do gate. Projeto consumidor não deve
  customizar regras de Detekt direto — customiza threshold via
  `workflow-config.yaml`.
- Versionamento: ao atualizar Detekt, o config interno é atualizado
  junto (parte da release do forge). Não vira `.bak` no projeto.
- Decision 22 (zero runtime deps) preservada: configs são arquivos
  estáticos, não código.

Threshold passado via CLI args **sempre** (não embutido no config),
porque varia per-feature via card override.

**Nota mecânica (post-review 2026-06-04):** Detekt e SwiftLint não aceitam
threshold de CC via CLI flag. O contrato "threshold dinâmico sempre" é
honrado via **tempfile-render**: validator substitui `__CC_THRESHOLD__`
no template em tempo de execução e passa o tempfile com `--config`. Para
eslint, threshold continua via `--rule` inline. Para Radon, threshold é
filtrado em Python pós-output.

### Trust-but-verify de tool availability

Tools nativas são instaladas pelo dev local (Detekt via brew/SDKMAN,
SwiftLint via brew, eslint via npm, Radon via pip). Forge **não
instala**. Estratégia quando tool falta:

| Contexto | Tool missing → comportamento |
|---|---|
| `forge verify` cascade | `result_warn` — não fail. Cascade segue. |
| `forge doctor` | Nova categoria `cc-gate-tools` reporta status + instruções de install |
| `forge implement` per-task | Mesma lógica `result_warn` — não bloqueia commit |

Por que tool missing ≠ violation: dev sem swiftlint não consegue
mexer em código Kotlin sem instalar swiftlint — péssima UX. Forge
avisa via `forge doctor` que falta ferramenta pra cobertura completa,
mas não bloqueia produtividade em linguagens que o dev tem.

`forge doctor` na nova categoria `cc-gate-tools` mostra:

```
cc-gate-tools
  · detekt        ✓ found  (1.23.6)
  · swiftlint     — não encontrado
                  install: brew install swiftlint
  · eslint        ✓ found  (8.57.0)
  · radon         ✓ found  (6.0.1)
```

### Edge cases enumerados

- **Arquivo gerado** — `ignore-paths` regex captura (`.*\.generated\..*`,
  `build/`, `node_modules/`, etc.). Default não inclui patterns de
  geração automática; projeto consumidor declara explicitamente.
- **Test files** (`src/test/`, `tests/`, `__tests__/`) — ignorados
  por default via pattern embutido. CC alto em teste é ruído (cada
  cenário vira branch).
- **Lambda/closure inline** — range-based. Lambda dentro de função
  pertence ao escopo da função pai pra fins de `new vs modified`. Tool
  nativa já agrega na contagem da função pai.
- **Rename detection > 80% similarity** — `cc_before` puxado do path
  antigo (descrito em §2). Ambíguo (60-80%) → `new`.
- **Output não-JSON-parseável** — tool crashou, projeto com config
  bug, ou versão incompatível. Validator captura stderr, emite
  `result_warn` com mensagem ("Detekt 1.23.6 falhou em foo.kt — stderr:
  <snippet>"), não bloqueia. `forge doctor` flag versão.
- **Função com `// suppress: cc`** (comentário inline) — v1.2 NÃO
  suporta inline suppress. Decisão deliberada: override-no-commit
  no commit body é o único escape, mantém auditabilidade. Inline
  suppress vira whitelist invisível espalhada pelo código.

## Seção 4 — 3-caminhos on-fail + integração per-task

### Mensagem 3-caminhos canônica

Quando o validator detecta ≥1 fail, emite a mensagem seguindo o
template canônico de `.claude/rules/disciplines.md §1`. Exemplo literal:

```
🛑 Cyclomatic Complexity gate

O que falhou:
  3 funções excederam o threshold permitido.

Onde:
  · app/auth/LoginViewModel.kt:42 — handleLogin()        cc=14  (limite: 10)
  · app/auth/LoginViewModel.kt:88 — validateForm()       cc=11  (limite: 10) [new]
  · ios/Auth/LoginCoordinator.swift:67 — performLogin()  cc=12  ↑ de cc=9 [modified]

Por que importa:
  · Funções com CC alto são mais difíceis de testar, revisar e evoluir.
  · Threshold vigente: kotlin=10, swift=10 (workflow-config.yaml)
  · Decision 23 — cascade fail-fast; este é o primeiro hard fail.

Três caminhos pra resolver:

  1) Refatorar
     Quebra a função em helpers menores. Tipicamente: extrair branches
     condicionais, validações, ou loops em métodos privados nomeados.
     Re-rodar `forge verify` confirma.

  2) Override-justify (commit body)
     Se a complexidade é genuinamente irredutível (state machine, parser,
     DSL), adicionar ao commit body — EXATAMENTE este formato:

         CC-OVERRIDE: <file>:<func> cc=<N> — <razão concreta>

     Validator detecta a linha no commit body e libera APENAS este commit.
     Auditável via `git log --grep='CC-OVERRIDE'`. NÃO é whitelist persistente.

  3) Split-task
     Dividir a task atual em sub-tasks menores. Tipicamente o sintoma é
     "task fez coisa demais" — split via `forge implement` reabrindo
     task-breakdown.

Sem auto-fix aqui — escolha humana.
```

Notas de render:
- Anotação `[new]` aparece após cc quando função não existe em `HEAD`.
- Anotação `↑ de cc=N` aparece para funções `modified` que pioraram.
- Funções `modified` que não pioraram (cc_after ≤ cc_before) não
  aparecem — não são fail.
- Threshold vigente listado por linguagem afetada (não toda
  configuração).

### Mecânica do override-justify

O caminho 2 é o único escape válido. Funcionamento estrito:

1. Validator inspeciona `git log -1 --format=%B HEAD` (em `forge
   verify`) ou `COMMIT_EDITMSG` (em hook pré-commit interno do
   `forge implement`).
2. Procura linhas que casam o regex:
   ```
   ^CC-OVERRIDE:\s+(?P<file>\S+):(?P<func>\S+)\s+cc=(?P<cc>\d+)\s+—\s+(?P<reason>.+)$
   ```
3. Para cada fail detectado, verifica se há override casando
   `<file>:<func>` no commit body. Match → fail vira `info` (logado,
   não bloqueia).
4. Override é **por commit, por função, por arquivo**. Não cobre outras
   funções, não cobre outros commits, não vira whitelist persistente.
5. Falta o `— <texto>` (razão concreta) → override **não conta**.
   Validator emite warning "CC-OVERRIDE sem razão — adicione texto
   após —". Mantém o fail.
6. Auditável: `git log --all --grep='CC-OVERRIDE'` lista todo histórico
   de override. Futuro `forge graph` query (Q18 ou superior, deferido
   pra v1.3+) pode tabular taxa de override por área do código.

Override **não** é flag CLI. Vive no commit body. Decisão deliberada:
- Flag seria atalho pra burlar gate sem fricção.
- Commit body força o dev a articular razão concreta, e fica visível
  em review.
- Auditoria não precisa de tooling extra (`git log --grep` resolve).

### Per-task hook em `forge implement`

Posição no pipeline atual do `forge implement`:

```
┌──────────────────────────────────────────────────────────┐
│  forge implement <slug>                                  │
│    ↓                                                     │
│  Plan Mode (task contract → subagent)                    │
│    ↓                                                     │
│  Apply Mode (subagent escreve diff)                      │
│    ↓                                                     │
│  Review (post-subagent-validate hook + validators)       │
│    ↓                                                     │
│  ╔════════════════════════════════════════════╗          │
│  ║  CC GATE (novo — entre review e commit)    ║          │
│  ║  check_cyclomatic_complexity sobre staged  ║          │
│  ║  Pass → segue · Fail → 3-caminhos + halt   ║          │
│  ╚════════════════════════════════════════════╝          │
│    ↓                                                     │
│  Commit atômico                                          │
└──────────────────────────────────────────────────────────┘
```

Implementação:
- `engine/implement.py` chama
  `validators.check_cyclomatic_complexity.run(context)` **como função
  Python**, não subprocess. Evita boot do interpretador a cada task.
- Context inclui: feature_dir, active_cards (lidos de
  `feature_dir/cards/`), workflow_config (já carregado), staged files
  (calculados na hora).
- Bypass via env var `NO_CC_GATE=1` — emergência única (build CI
  quebrando por bug no validator, dev precisando shippar fix urgente).
  Logado em `.claude/state/cc-gate-bypass.jsonl` pra auditoria. **Não
  é** o caminho normal de override — pra isso existe o CC-OVERRIDE no
  commit body.

### Cascade em `forge verify`

Nova entrada na lista de validators de `engine/verify.py`, posicionada
**após** `check_no_invented_behavior`. Ambos são "anti-pattern gates"
(detectam algo errado no código vs. validators de schema/artefato).
Posicionar juntos preserva ordem semântica do cascade.

Decision 23 (fail-fast por default) mantida — se algum validator
anterior falhar, `check_cyclomatic_complexity` **nem roda**. Isso é
intencional:
- Validators anteriores cobrem corretness mais básica (artefato
  faltando, scope violation, behavior invented).
- CC gate é menos crítico que esses — bloquear antes de resolver os
  mais fundamentais é ruído.
- Quando cascade chega no CC, o resto do feature já está coerente.

Override `validators.fail-fast: false` em `workflow-config.yaml` faz
o cascade rodar todos os validators e coletar todos os fails (descrito
em `07-discipline.md §2`). Comportamento preservado.

## Seção 5 — Testing, doc-sync, decisões load-bearing, risks

### Testing strategy

Duas camadas: unit tests (validator em isolamento) + integration tests
(cascade + per-task end-to-end).

#### Unit tests — `tests/validators/test_check_cyclomatic_complexity.py`

| Cenário | O que valida |
|---|---|
| Threshold lookup só default | Sem workflow-config e sem card → retorna `DEFAULTS[language]` |
| Threshold lookup workflow-config | Workflow-config presente → override default |
| Threshold lookup per-card | Card com `cc-gate-override` → override workflow-config |
| Múltiplos cards conflitantes | Primeiro card com override vence (determinístico) |
| Detecção new vs modified | Função em `HEAD` sem mudança → `unchanged`; com mudança no diff → `modified`; sem em `HEAD` → `new` |
| Delta rule | Função `modified` com cc_after > cc_before → fail; com cc_after ≤ cc_before → pass |
| Threshold rule | Função `new` com cc > N → fail; com cc ≤ N → pass |
| Override válido | `CC-OVERRIDE: file.kt:func cc=14 — razão` no commit body → fail vira info |
| Override malformado | Falta `— <texto>` → override não conta, warning emitido |
| Override cobre só função declarada | Outras funções no mesmo commit não são cobertas pelo override |
| Tool missing → warn | Tool não instalada → `result_warn`, não fail |
| Tool crash → warn | Tool retorna stderr/non-JSON → `result_warn` com snippet |
| ignore-paths regex | Arquivo em `src/test/.*` → ignorado, não conta |
| 3-caminhos format snapshot | Output exato bate com template canônico (regression test) |

#### Integration tests — `tests/integration/test_cc_gate_end_to_end.py`

| Cenário | O que valida |
|---|---|
| `forge verify` cascade posição correta | Validator roda após `check_no_invented_behavior`, antes dos seguintes |
| `forge verify` fail-fast | Validator anterior falha → CC não roda; logged como `—` |
| `forge implement` per-task fail bloqueia commit | Subagent gerou função cc > N → CC gate bloqueia, commit não acontece |
| `forge implement` per-task override permite commit | Subagent gerou função cc > N + commit body tem CC-OVERRIDE válido → commit passa |
| Smoke per-language | Pra cada uma das 4 tools: executa pipeline completo com fixture de alta-CC, espera fail. Skip se tool não está instalada no ambiente de teste (marker `@pytest.mark.skipif`) |

#### Fixtures novos — `tests/fixtures/cc_gate/`

- `kotlin_high_cc.kt` — função com 12 branches/loops, cc esperado > 10
- `kotlin_low_cc.kt` — função baseline cc=3
- `swift_high_cc.swift` — paralelo Kotlin
- `ts_high_cc.ts` — paralelo
- `python_high_cc.py` — paralelo
- `workflow-config-with-cc.yaml` — config com bloco `cc-gate:` completo
- `card-with-cc-override.yaml` — card com `cc-gate-override` válido
- `card-with-cc-override-no-justification.yaml` — card sem justification
  (cenário de warning)

#### Baseline target

Baseline atual da branch (snapshot na hora do `writing-plans` —
exatamente quando o plan for escrito, rodar `pytest --collect-only -q
| tail -1` no worktree). Estimativa: ~387 tests pós-implementação (~14
unit + ~6 integration somados ao baseline atual).

> Nota operacional: o número 367 que aparece em alguns docs do projeto
> é baseline de v1.1.0 stale. A implementação deste gate ancora no
> baseline observado na branch no momento do plan — não em número
> hardcoded.

### Doc-sync (Mandamento #6)

Lista exaustiva dos 8 documentos a sincronizar **no mesmo branch** que
implementa o gate. Sem sync = violação mandamento 6.

| Doc | Mudança |
|---|---|
| `CHANGELOG.md` | `## [Unreleased] ### Added` — "Cyclomatic Complexity gate (`check_cyclomatic_complexity`) — multi-language, runs in `forge verify` cascade and `forge implement` per-task. Threshold via workflow-config + card override. 3-caminhos on fail." |
| `docs/design/08-session-handoff.md` | Última atualização: data; Estado: "v1.2 — CC gate shipping"; tabela `\| Categoria \| Status \|` ganha linha "CC gate" |
| `README.md` | Stats: validators 14→15, tests baseline → baseline+~20 |
| `docs/schemas/workflow-config.md` | Append bloco `cc-gate:` documentado |
| `docs/schemas/card.md` | Append campo `cc-gate-override` (opt-in) |
| `docs/design/07-discipline.md` | §2 cascade — adiciona linha do novo validator após `check_no_invented_behavior` |
| `docs/design/04-pending.md` | Marca gaps fechados N/A (este gate não fechou pending existente); registra 5 novos gaps deferidos (listados abaixo) |
| `.claude/rules/testing.md` | Mention do validator novo em §"Validators são código" |

### Decisões load-bearing — confirmação de NÃO impacto

As 8 decisões load-bearing (de `.claude/rules/decisions.md`) ficam
intactas. Tabela de auditoria:

| # | Decisão | Status | Razão |
|---|---|---|---|
| 14 | Config scope = um workflow-config por sub-projeto | OK | Bloco `cc-gate:` vive dentro do workflow-config já existente — não cria novo arquivo de config |
| 15 | Versioning model = snapshot copy local | OK | Validator é parte do forge engine, viaja no snapshot — sem runtime dep |
| 18 | Skill location = standalone repo | OK | Sem impacto em location |
| 19 | Language = Python core + Bash dispatcher + YAML/MD | OK | Validator em Python, configs em YAML/JSON estáticos, sem nova linguagem |
| 20 | Persistence = SQLite + arquivos | OK | Gate não persiste estado próprio; lê staged diff + workflow-config + cards |
| 22 | No runtime deps em outras skills | OK | Tools nativas (Detekt/SwiftLint/eslint/Radon) são tools do projeto consumidor, não skills do forge — equivalentes semânticos a "tools de teste" (pytest) já assumidos |
| 23 | Validator cascade = fail-fast | OK | Gate **respeita** Decision 23: posicionado após `check_no_invented_behavior`, gate anterior falha → CC não roda |
| 27 | Pause = `deferred`; abort = 2-step | OK | Gate não introduz estado novo de feature; respeita pause/abort existentes |

**Conclusão:** nenhuma "Revisita decisão N" no CHANGELOG. Nenhum
hard-block do pre-commit hook do projeto será triggered por este
shipping.

### Risks / open questions deferidos

Cinco itens a registrar em `docs/design/04-pending.md` na hora do
shipping. Cada um é decisão consciente de não-fazer-em-v1.2, com
critério pra reentrar:

1. **Whitelist persistente de overrides** — hoje override é por commit
   no body. Eventualmente projetos grandes podem querer "essa função
   tem cc=20 e é assim porque é parser" como anotação permanente. v1.2
   recusa pra evitar débito invisível. Reentrar se ≥3 projetos
   consumidores pedirem em retro.
2. **Cognitive Complexity (Sonar) — métrica alternativa** — CC é
   métrica clássica mas Cognitive Complexity (Campbell, SonarSource)
   reflete melhor leitura humana. Trocar tooling é trabalho não-trivial
   (cada tool nativa tem variação) — deferido pra v1.3+ se sinal
   empírico justificar.
3. **CC trending em `forge graph`** — adicionar query Q18+ que tabula
   CC por área do código e mostra trend ao longo do histórico. Útil
   pra retrospective. Deferido pra v1.3+ junto com expansão geral do
   graph.
4. **Auto-suggest refactor LLM-powered** (Phase 6) — quando gate
   bloqueia, mostrar sugestão concreta de como refatorar (LLM analisa
   função, propõe split). Fora de escopo v1.2 porque toca subagent
   orchestration de forma não-trivial.
5. **Per-function threshold inline annotation** — `// cc-threshold:
   20` no código. **Rejeitado em favor de override-no-commit**: inline
   espalha exceções pelo código, dificulta auditoria, vira whitelist
   invisível. Documentar a rejeição explicitamente no pending pra não
   reaparecer em retrospective.

### Critério de aceitação v1

Checklist de 12 items que o `writing-plans` consome direto. Cada item
testável.

1. [ ] `validators/check_cyclomatic_complexity.py` existe, 350-450 LOC,
       passa `ruff check` e `pytest tests/validators/test_check_cyclomatic_complexity.py`.
2. [ ] `validators/_common.py` tem helpers `cc_threshold_lookup` e
       `cc_format_three_paths`, ambos com unit test.
3. [ ] `engine/verify.py` registra o validator na cascade após
       `check_no_invented_behavior`; teste de integração confirma
       posição.
4. [ ] `engine/implement.py` invoca o validator entre review e commit;
       teste de integração confirma bloqueio pré-commit.
5. [ ] `engine/doctor.py` reporta categoria `cc-gate-tools` com status
       de cada tool e instruções de install pras missing.
6. [ ] `engine/_cc_configs/{detekt.yml,swiftlint.yml,eslint.json,radon.cfg}`
       existem e são consumidos pelas tools com sucesso em fixtures.
7. [ ] `docs/schemas/workflow-config.md` documenta bloco `cc-gate:`
       com exemplo completo.
8. [ ] `docs/schemas/card.md` documenta `cc-gate-override` opt-in com
       requisito de `justification`.
9. [ ] 3-caminhos render bate snapshot test — formato canônico de
       `.claude/rules/disciplines.md §1`.
10. [ ] Override-justify regex casa exemplos válidos, rejeita
        malformados; cobertura de unit test ≥ 5 cenários.
11. [ ] `pytest` (suite completa) verde; test count ≥ baseline+~20.
12. [ ] Doc-sync 8 docs (lista em §5) completos; `forge verify` no
        próprio repo passa cascade sem hard fail.

## Apêndice — Próximos passos

Após este spec, o orchestrator-mantenedor invocará
`superpowers:writing-plans` pra produzir o implementation plan em
`docs/superpowers/plans/`. Plan terá:

- Decomposição em tasks atômicas (estimativa: ~8-12 tasks).
- Ordem de dispatch (validator core → configs → integração verify →
  integração implement → doctor → docs).
- Context-pack canônico pra cada task (ARQUIVOS PERMITIDOS, ANTI-PADRÕES,
  CRITÉRIO DE SUCESSO).

Quem executa serão `gsd-executor` (impl) → `gsd-code-reviewer` →
`gsd-code-fixer` em loop. Trust-but-verify do orchestrator entre cada
dispatch. Verification-before-completion (pytest + `forge verify` no
próprio repo) antes do commit final.

Este spec é fonte de verdade. Em conflito entre spec e plan, **spec
vence** (e plan precisa ser corrigido). Em conflito entre spec e
implementação, implementação vence apenas se acompanhada de retorno
ao spec pra atualização — sem silent drift.
