# Native Quality Gates — Design (fronteira engine → binário externo)

> **Status:** discovery-first. Esta é a Task B1 da Onda 1b — uma *decisão de
> design*, não código. Ela fixa onde os gates nativos (ktlint/detekt/swiftlint)
> rodam, como o binário é descoberto, qual o isolamento, e como o resultado
> vira veredito. As tasks de implementação (B2+) só são escritas depois desta
> spec ser revisada e aprovada — escrevê-las antes seria especular sobre uma
> decisão ainda não tomada.
>
> **Voz:** mentor calmo. O objetivo é fechar um buraco real do piloto sem
> afrouxar uma garantia que custou caro pra estabelecer (Decisão 30/31).

---

## Contexto — o gap que o piloto expôs

O piloto MeoBonsai (`docs/reports/2026-06-25-piloto-meobonsai-gaps.md` §Tema 6)
mostrou que **os quality gates nativos do projeto pegaram problemas reais que o
forge não pegou**. ktlint, detekt e swiftlint são parte do contrato de
qualidade de um projeto Kotlin/Swift maduro; o forge gera o andaime e os
contratos, mas nunca roda esses linters — então um problema que o linter nativo
acusaria passa pelo verde do forge.

Há uma razão arquitetural pra esse buraco existir: **o engine hoje não executa
comandos do projeto consumidor**. O único lugar onde o forge roda código de
terceiros é o sandbox de validators na Phase 3 do `forge qa` — e esse sandbox é
deliberadamente Python-only e hermético (Decisão 30/31). Gates nativos são
binários externos; não cabem nesse sandbox sem reabrir uma decisão de segurança.

Por isso esta spec existe antes do código: há ≥3 perguntas de design não-triviais
a resolver. Cada seção abaixo resolve uma; onde há ambiguidade legítima,
apresento exatamente três caminhos com prós e contras e registro a escolha.

---

## 1. Onde os gates rodam

A pergunta de fronteira: dado que o sandbox de validators (Decisão 30) é
Python-only, onde mora a execução de um binário externo como `ktlint`?

### Caminho A — Comando próprio (`forge verify` estendido ou step novo)

O engine descobre e invoca os binários nativos diretamente, num caminho de
execução **separado** do sandbox de validators. Reusa o pattern subprocess que
`engine/verify.py` já tem (`[exe, args...]` + `capture_output` + `timeout`),
mas o `exe` é o linter nativo (ou o gradle wrapper), não `sys.executable`.

- **Prós:** encaixa no comando que o usuário já associa a "checar qualidade"
  (`forge verify`); um só lugar pra descobrir/invocar/mapear; não infla o
  contrato de cards.
- **Contras:** acopla `verify` a toolchains que ele hoje ignora; precisa de um
  esquema de skip-se-ausente robusto pra não quebrar projetos sem o linter.

### Caminho B — Card-declared

Cada card que produz código de uma stack (ex.: `compose-screens`) declara seu
gate nativo no `card.yaml`:

```yaml
native-gates:
  - tool: ktlint
    discover: gradle-wrapper   # ./gradlew ktlintCheck
    optional: true
```

O engine lê os `native-gates` dos cards ativos e os roda.

- **Prós:** o gate vive junto da stack que ele protege (coesão); cards de
  terceiros podem trazer o próprio gate sem tocar o core; naturalmente opt-in.
- **Contras:** mais superfície de contrato (`card.yaml` schema + validação);
  exige que todo card relevante declare o gate, senão o buraco persiste;
  descoberta do binário fica espalhada por N cards.

### Caminho C — Vetor qa novo, com runner separado do sandbox

Um vetor de `forge qa` (estilo Phase 3, mas executando binário externo num
runner **separado** do sandbox de validators). É preciso explicitar por que
NÃO reusa o sandbox de validators: a Decisão 30 garante CWD isolado +
`os.chdir` guard via `sitecustomize.py` + budget, projetado pra **scripts
Python** (`[sys.executable, validator, ...]`). Um binário externo (gradle,
ktlint nativo) não passa por esse interpretador, então o `sitecustomize.py`
preload **não se aplica** — o guard de chdir e o hermetismo do sandbox de
validators simplesmente não cobrem o processo. Reusar o sandbox daria uma
falsa sensação de isolamento.

- **Prós:** o output naturalmente vira finding (reusa o schema qa-finding,
  dedup, verdict); coerente com o framing "qa acha problemas".
- **Contras:** mistura dois modelos de execução muito diferentes (Python
  hermético vs binário externo do projeto) sob o mesmo comando; o isolamento
  do binário externo é um problema NOVO que o qa não tem hoje.

### Decisão: **Caminho A — comando próprio, separado do sandbox de validators.**

**Rationale:** o gate nativo é, conceitualmente, "rodar a ferramenta de
qualidade que o projeto já tem" — isso é parentesco direto com `forge verify`,
não com o red-team adversarial do qa. Manter a execução de binário externo num
caminho próprio (não no sandbox de validators) preserva a Decisão 30 intacta: o
sandbox de validators segue Python-only e hermético; o gate nativo é uma
fronteira de execução **nova e explícita**, com suas próprias garantias (§3).
O Caminho B é uma boa evolução futura (cards trazendo o próprio gate), mas como
primeiro nível adiciona superfície de contrato antes de provarmos o valor — fica
como follow-on. O Caminho C foi descartado porque colaria dois modelos de
isolamento incompatíveis sob o mesmo teto.

---

## 2. Como o binário é descoberto

Um gate só pode rodar se o forge achar o binário — e o consumidor pode
legitimamente não tê-lo instalado. A descoberta precisa de uma ordem de
preferência e de um comportamento de ausência que **não quebre** o projeto.

Ordem de descoberta (primeiro que resolver vence):

1. **Gradle/SwiftPM wrapper no projeto** — `./gradlew ktlintCheck`,
   `./gradlew detekt`, ou o invocador equivalente de swiftlint. É a forma mais
   confiável: o wrapper fixa a versão e não depende do PATH global. Preferido.
2. **Caminho declarado em config** — uma chave em `forge-config.yaml`
   (ex.: `native-gates.ktlint.bin: /path/to/ktlint`) pra projetos que rodam o
   linter fora do build tool.
3. **`which <tool>` no PATH** — fallback last-resort. Frágil (versão não fixada),
   mas cobre setups simples.

**Comportamento quando ausente:** **skip com aviso mentor-calmo, NÃO fail.** O
consumidor pode não ter ktlint instalado, e isso não é um erro do forge nem da
feature. A mensagem nomeia o gate, diz que foi pulado e como habilitá-lo:

> "Gate nativo `ktlint` não encontrado (nem `./gradlew ktlintCheck`, nem
> `native-gates.ktlint.bin`, nem no PATH). Pulei este gate — a feature não foi
> reprovada por isso. Pra habilitá-lo, instale o ktlint ou aponte o binário em
> `forge-config.yaml`."

Skip-se-ausente é **requisito**, não conveniência: um gate que falha por
ausência transformaria o forge em refém da toolchain de cada consumidor.

---

## 3. Isolamento / segurança (a fronteira nova vs Decisão 30)

O sandbox de validators (Decisão 30/31) **não se aplica** a binários externos —
ele protege a execução de **scripts Python** via CWD isolado + `os.chdir` guard
por `sitecustomize.py` preload + budget. Um gradle/ktlint não passa pelo
interpretador Python do forge, então nada desse hardening cobre o processo.

Rodar um binário externo é, portanto, uma **fronteira de execução nova**. Esta
spec declara as garantias que essa fronteira DEVE ter — e sinaliza que isso é
candidato a uma **nova Decisão** no `docs/design/01-decisions.md` (Decisão 33?),
seguindo o ritual de revisita. **Esta spec NÃO afrouxa a Decisão 30** — ela é
sobre um caminho de execução diferente; a 30 segue valendo integralmente pro
sandbox de validators.

Garantias requeridas da fronteira de gate nativo:

- **Read-only sobre o working tree.** O gate roda no working tree do projeto
  (precisa ver os arquivos reais — diferente do snapshot do qa). O forge invoca
  o linter em **modo check, nunca modo fix** (ver §5 non-goals): `ktlintCheck`,
  não `ktlintFormat`; `detekt` sem `--auto-correct`; `swiftlint lint`, não
  `swiftlint --fix`. A garantia "não escreve" vem de escolher o subcomando de
  check — é responsabilidade da spec listar o subcomando read-only de cada tool
  e nunca expor o de auto-fix.
- **Env reduzido.** Espelha o `env` reduzido que `engine/verify.py` já monta pra
  subprocess de validator — não vazar segredos do ambiente do forge pro linter.
- **Timeout / budget.** Cada gate tem timeout próprio (gradle pode ser lento;
  sugestão de default generoso, ex.: 120s, configurável). Estouro = o gate vira
  `degraded` (não `fail`), com aviso — espelha a filosofia de "verde inerte" do
  Tema 6: um gate que não terminou não deve nem reprovar nem fingir que passou.
- **Sem rede declarada como requisito.** O primeiro nível não assume rede; se um
  gradle wrapper baixar dependências, isso é responsabilidade do build do
  consumidor, fora do escopo do gate.

**Sinal pro ritual de decisão:** se a implementação confirmar que essa fronteira
precisa de garantias formais (ex.: um wrapper de subprocess dedicado pra
binários externos, distinto do de validators), abrir Decisão 33 via o ritual
"Revisita/Nova decisão" — append em `01-decisions.md` + entrada no CHANGELOG. A
spec sinaliza; não decide a 33 de lado.

---

## 4. Como o resultado vira finding / veredito

ktlint, detekt e swiftlint emitem formatos diferentes: texto plano, SARIF,
checkstyle-XML, JSON. O mapping output → veredito precisa ser definido por tool.

- **Formato de saída preferido:** quando o tool suporta, pedir saída estruturada
  (ktlint `--reporter=json`, detekt SARIF, swiftlint `--reporter json`). Parsear
  estruturado é mais robusto que regex sobre texto.
- **Mapping pro contrato existente:** o resultado entra no **veredito do
  `verify`** (Caminho A da §1), não do qa. Cada violação reportada pelo linter
  vira uma linha no sumário do verify, agrupada por tool. A spec define os
  thresholds: por padrão, **violações do linter NÃO reprovam o verify** no
  primeiro nível — elas aparecem como `warning`/informativo. Subir pra `fail`
  (gate com dentes) é uma decisão de produto por-projeto, configurável, e
  deliberadamente NÃO é o default inicial (consistente com a lição do Tema 6 de
  não criar verde — ou vermelho — inerte/barulhento).
- **`degraded` é cidadão de primeira classe.** Gate ausente (§2) ou estourado
  (§3) → `degraded`, distinto de `pass` e `fail`. O sumário do verify nomeia o
  porquê. Isso ataca diretamente o "verde inerte" do Tema 6: o usuário vê que o
  gate não rodou, em vez de um falso verde.

---

## 5. Non-goals

- **Não auto-fixar.** Nada de `ktlint -F` / `ktlintFormat` / `detekt
  --auto-correct` / `swiftlint --fix`. O forge reporta, o usuário corrige. Rodar
  só os subcomandos de check é o que garante o read-only da §3.
- **Não instalar o binário.** Se o linter não está presente, skip-se-ausente
  (§2). O forge não baixa nem instala toolchain do consumidor.
- **Não rodar a suite de testes do projeto.** Isso é verificação runtime, coberta
  pela spec irmã `2026-06-30-runtime-visual-verification-design.md` (1b-C) — não
  aqui.
- **Não cobrir toolchains não-detectadas no init.** O primeiro nível mira as
  stacks que o `forge init`/detection já reconhece (Kotlin/Android, Swift/iOS).
  Stacks fora disso ficam pra expansão.
- **Não reabrir a Decisão 30.** O sandbox de validators segue Python-only e
  hermético; o gate nativo é fronteira separada (§3).

---

## 6. Faseamento

- **Nível 1 (mínimo viável):** UM gate, descoberto via gradle wrapper, com
  skip-se-ausente e resultado informativo (não-reprovante). Candidato natural:
  **ktlint via `./gradlew ktlintCheck`** — foi um dos linters que pegou problema
  real no piloto, e o wrapper torna a descoberta confiável. Mapping de saída
  estruturada → sumário do verify. Critério de "funcionou": num projeto com
  violações conhecidas, o gate as lista; num projeto sem ktlint, pula com aviso
  e não reprova.
- **Nível 2:** detekt (mesma stack Kotlin, SARIF) + tornar o threshold
  configurável (warning → fail opt-in por projeto).
- **Nível 3:** swiftlint (stack iOS) — fecha o trio do Tema 6.
- **Critério antes de subir nível:** o nível anterior provou valor num consumidor
  real (pilotar contra projeto real, não só repo standalone) sem gerar ruído que
  o usuário aprende a ignorar.

> **Tasks B2+ (implementação) são deliberadamente NÃO definidas aqui.** Elas
> dependem desta spec ser revisada e do Caminho A ser confirmado pelo reviewer.
> Após aprovação, um plano de execução curto e TDD (descoberta do binário →
> invocação em modo check → mapping output → finding/sumário → skip-se-ausente →
> degraded) é escrito contra esta spec. Definir B2 agora seria adivinhar sobre
> uma decisão ainda em revisão — anti-padrão de plano.

---

## Cross-refs

- Report do piloto: `docs/reports/2026-06-25-piloto-meobonsai-gaps.md` §Tema 6.
- Decisão 30/31 (sandbox isolation, Python-only): `docs/design/01-decisions.md`.
- Pattern subprocess reusável: `engine/verify.py` (`[exe, args]` +
  `capture_output` + `timeout` + env reduzido).
- Por que NÃO reusar o sandbox de validators: `engine/qa/sandbox.py`
  (hardening Python-only via `sitecustomize.py` preload — não cobre binário
  externo).
- Spec irmã (runtime/visual): `2026-06-30-runtime-visual-verification-design.md`.
