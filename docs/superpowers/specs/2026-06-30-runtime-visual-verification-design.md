# Runtime / Visual Verification — Design (1º nível pragmático)

> **Status:** spec de decisão de produto. Esta é a Task C1 da Onda 1b — o
> deliverable é *este documento*, não código. O item mais amplo e vago do Tema
> 6: o que "primeiro nível pragmático de verificação runtime/visual" significa é
> uma decisão de produto, não uma tarefa de implementação. A Onda 1 (§Riscos)
> recomendou explicitamente transformar isso numa spec própria em vez de "boil
> the ocean".
>
> **Voz:** mentor calmo. A spec enuncia caminhos com prós e contras; deixa
> deliberadamente em aberto o que exige decisão de produto, sem fingir que já
> decidiu.

---

## 1. O problema concreto (do piloto)

O piloto MeoBonsai (`docs/reports/2026-06-25-piloto-meobonsai-gaps.md` §Tema 6)
expôs uma assimetria: o forge gera contratos e andaime, e verifica artefatos
**estáticos** (specs, validators) — mas **nunca verifica que o app roda ou que
se parece com o esperado**. No piloto, a confirmação de que a feature de fato
funcionava veio de fora do forge: o desenvolvedor bateu o screenshot e rodou os
172 testes (130 bonsai + 42 home) **manualmente**, no terminal e no
device/emulador. Nenhum dos 14 comandos do forge tocou execução.

Por que importa: o verde estático comunica uma garantia que não cobre "o app
sobe e renderiza". Para um fluxo 100% IA-first, o forge precisaria fechar ao
menos um nível de verificação de execução — caso contrário a etapa mais decisiva
("isso roda?") fica permanentemente fora do loop.

Esta spec não resolve o problema inteiro. Ela define o **primeiro degrau**
pragmático e o critério pra subir os próximos.

---

## 2. O que "1º nível pragmático" significa — três caminhos

"Verificação runtime/visual" é um guarda-chuva grande. O primeiro nível pode
significar coisas de custo e cobertura muito diferentes. Apresento os três
caminhos com prós e contras; **a escolha do nível inicial é decisão de produto**
e fica enunciada aqui pra o user/produto bater o martelo — a spec não a força.

### Caminho A — Build-only ("o app compila?")

Roda o build do projeto: `./gradlew assembleDebug` (Android), `xcodebuild`
(iOS), ou o equivalente da stack. Sem rodar o app, sem device.

- **Prós:** o mais barato dos três; pega o erro mais comum e mais barato de
  corrigir cedo (código que nem compila); não precisa de emulador/device nem de
  baseline; determinístico.
- **Contras:** "compila" está longe de "funciona" — não pega crash em runtime,
  tela em branco, ou regressão de comportamento. É o piso, não o teto.

### Caminho B — Smoke test ("o app sobe e passa 1 assert mínimo?")

Roda um teste de fumaça mínimo: launch do app + 1 assert (ex.: a tela inicial
renderiza um elemento-âncora). Pode reusar o test runner nativo do projeto.

- **Prós:** prova que o app **sobe**, não só compila; pega crash de
  inicialização e wiring quebrado (DI, navegação raiz); custo moderado.
- **Contras:** precisa de um runner de teste configurado e (em mobile) de
  emulador/device — toolchain pesada; o "1 assert" precisa ser escolhido com
  cuidado pra não virar teste frágil ou inerte.

### Caminho C — Screenshot diff ("a tela se parece com o baseline?")

Captura uma tela e compara com uma baseline aprovada.

- **Prós:** é o único que ataca o **visual** diretamente — pega regressão de
  layout/render que build e smoke não veem; alinhado com o "bater o screenshot"
  manual do piloto.
- **Contras:** o mais caro e o mais frágil; exige gerência de baselines
  (aprovar, versionar, lidar com diffs de fonte/DPI/anti-aliasing cross-machine);
  falso-positivo é comum e corrói confiança. Prematuro como primeiro nível.

### Recomendação (não-vinculante) e enquadramento

A spec **recomenda Caminho A (build-only) como Nível 1**, por ser o degrau de
melhor custo-benefício pra começar a fechar o loop sem toolchain pesada nem
gerência de baseline — mas registra que a decisão final é de produto. Caminho B
é o Nível 2 natural; Caminho C entra só quando build+smoke já provaram valor e
houver apetite pra investir em gerência de baseline visual.

---

## 3. Non-goals

- **Não substituir a suite de testes do consumidor.** O nível 1 é um smoke de
  confiança, não cobertura. O projeto continua dono dos seus testes.
- **Não CI completo.** Nada de matriz de devices, paralelismo, ou pipeline de
  release. Isso é responsabilidade do CI do consumidor.
- **Não cobrir todos os screens.** O primeiro nível mira um caminho mínimo (o
  build, ou o launch + 1 tela), não a feature inteira.
- **Não emular dispositivo se o consumidor não tem toolchain.** Skip-se-ausente
  é requisito (espelha o gate nativo da spec irmã): sem emulador/SDK, o passo
  vira `degraded`, não `fail`.
- **Não escolher prematuramente o nível** quando isso é decisão de produto — a
  §2 enuncia os caminhos; o produto decide.

---

## 4. Fronteira de execução vs Decisão 30 (e reuso de 1b-B)

Como os gates nativos (1b-B), a verificação runtime roda **binário/toolchain do
consumidor** (gradle, xcodebuild, test runner, emulador). Logo, **a mesma
fronteira de execução nova** se aplica: o sandbox de validators (Decisão 30/31)
é Python-only e hermético e **não cobre** esses binários externos.

**Reuso deliberado:** se a spec de native quality gates
(`2026-06-30-native-quality-gates-design.md`) já estabelece a fronteira "engine
roda comando externo do projeto" — com suas garantias (read-only onde aplicável,
env reduzido, timeout/budget, skip-se-ausente, `degraded` como cidadão de
primeira classe, e o sinal pro ritual de nova Decisão) — **esta spec reusa essa
fronteira em vez de inventar outra.** A verificação runtime é mais um consumidor
do mesmo caminho de execução externo, não um segundo modelo paralelo.

Diferença relevante a registrar: ao contrário do linter em modo check (que é
read-only), um build/smoke **escreve** artefatos (binários, caches de build) no
working tree ou em diretórios de build do projeto. Isso é esperado e legítimo
(é o build do próprio projeto), mas a fronteira deve documentar onde esses
artefatos caem e que o forge não os versiona nem os limpa por conta própria.
**Esta spec NÃO afrouxa a Decisão 30** — reforça que runtime é fronteira externa
separada, candidata à mesma nova Decisão que 1b-B sinaliza.

---

## 5. Faseamento

- **Nível 1 (build-only, opt-in):** `./gradlew assembleDebug` / `xcodebuild`
  conforme a stack detectada no init, com skip-se-ausente e resultado
  informativo. Critério de "vale a pena": num projeto que compila, passa rápido
  e silencioso; num projeto com erro de compilação, aponta o erro de forma
  acionável; num projeto sem toolchain, pula com aviso (`degraded`).
- **Nível 2 (smoke test):** launch + 1 assert mínimo, reusando o runner nativo.
  Só depois que o build-only se provou num consumidor real.
- **Nível 3 (screenshot diff):** captura + baseline, com toda a gerência que
  isso implica. Só com apetite explícito de produto e build+smoke maduros.
- **Critério geral antes de subir nível:** o nível anterior provou valor num
  consumidor real (pilotar contra projeto real, não repo standalone) sem gerar
  ruído que o usuário aprende a ignorar. Cada nível só se justifica se o anterior
  estiver verde-com-substância.

---

## 6. Onde encaixa no lifecycle

Três possibilidades, enunciadas sem decidir prematuramente o que exige decisão
de produto:

- **Comando próprio** (ex.: `forge run-check` / `forge smoke`) — explícito e
  separado, o usuário invoca quando quer.
- **Step do `verify`** — junto da verificação estática, fechando "estático +
  runtime" num só veredito. Coerente com a fronteira de execução externa que
  1b-B já abriria em `verify` (Caminho A da spec irmã).
- **Pós-`implement`** — opt-in, logo após o host implementar uma task, pra
  feedback de execução cedo no loop.

**Sinal, não decisão:** a escolha do ponto de encaixe depende de como 1b-B
materializar a fronteira de execução externa (provavelmente em `verify`). Se
1b-B colocar gates nativos em `verify`, o caminho de menor atrito é a
verificação runtime ser outro step do mesmo `verify` — mas isso se confirma na
implementação, depois de 1b-B aprovada. A spec sinaliza a afinidade; não amarra.

---

## Cross-refs

- Report do piloto: `docs/reports/2026-06-25-piloto-meobonsai-gaps.md` §Tema 6.
- Spec irmã (fronteira de execução externa, reusada aqui):
  `2026-06-30-native-quality-gates-design.md`.
- Decisão 30/31 (sandbox isolation, Python-only — não cobre binário externo):
  `docs/design/01-decisions.md`.
