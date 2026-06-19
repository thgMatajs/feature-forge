# Universal disciplines

Este documento consolida **seis disciplinas universais** que todo agente,
roteiro, validador e script da feature-forge deve respeitar. Elas não são
features — são contratos de comportamento. Quando um roteiro contradisser
algo aqui, o roteiro está errado.

A motivação é simples: a engine tem muitos pontos de decisão (gates,
elicitations, validadores, mutações de memória), e sem disciplina universal
cada agente improvisa sua própria semântica. Improvisar quebra duas coisas:
a previsibilidade pro usuário e a auditabilidade da engine. Os seis pontos
abaixo são as bordas onde a improvisação acontecia com mais frequência.

Voz: mentor calmo — firme nos contratos, didático nos exemplos.

---

## 1. The "3-caminhos" pattern (gate-resolution universal)

**Regra absoluta:** em qualquer gate — falha de validador, violação de
escopo, artefato faltando, ambiguidade não resolvida, contradição entre
contracts — o agente apresenta **exatamente 3 caminhos** de resolução.
Nunca 2, nunca 4, nunca "consulte a documentação."

### As 3 famílias

```
┌────────────────────────────────────────────────────────────────┐
│  Caminho A — Fix forward                                       │
│  Atualiza o artefato/contract que cobre o caso.                │
│  Mais provável quando o problema é incompletude do plano.      │
├────────────────────────────────────────────────────────────────┤
│  Caminho B — Revert                                            │
│  Desfaz a tentativa, mantém o escopo atual.                    │
│  Mais provável quando o problema é desvio acidental.           │
├────────────────────────────────────────────────────────────────┤
│  Caminho C — Split / escalate                                  │
│  Vira nova task, registra Finding, ou abre ticket pra review.  │
│  Mais provável quando o problema é escopo legítimo mas tardio. │
└────────────────────────────────────────────────────────────────┘
```

Cada caminho tem um **arquétipo de motivo** — o agente cita o motivo provável
quando apresenta os caminhos. Mentor calmo nunca empurra um caminho. Sugere
qual é o "mais provável" dado o contexto, mas a decisão é humana.

### Por que exatamente 3

- **Dois** é falso dicotômico: "fix ou revert" empurra o usuário pra escolher
  entre estender escopo ou perder trabalho. Falta a saída honesta de
  "isso é uma task nova."
- **Quatro+** dilui. O usuário começa a pesar trade-offs cognitivos em vez
  de decidir. A engine perde o poder de mentoring.
- **Três** cobre o espaço semântico real (corrigir / desfazer / adiar) e
  cabe num menu interativo simples.

### Quando não há 3 caminhos genuínos

Se um gate só tem 2 caminhos honestos (ex.: input obrigatório faltando — só
"fornecer" ou "abortar"), o agente **escala pra abort** em vez de inventar
um terceiro caminho fake. Inventar caminho falso é pior que admitir que o
gate é binário.

Casos assim devem ser raros. Se aparecer recorrentemente em um agente, é
sinal de que o gate está mal-modelado e precisa virar um item de
`forge evolve`.

### Como apresentar

Formato canônico (já estabelecido em `forge-verify-roteiro.md` e
`forge-implement-roteiro.md`):

```
🛑 {nome-do-gate}

O que falhou:
  {explicação em 1-2 linhas}

Onde:
  {arquivo:linha ou artefato:campo}

Por que importa:
  · {regra violada}
  · {contract referenciado}
  · {consequência se passar}

Três caminhos pra resolver:

  1) {Caminho A — fix forward}
     {motivo provável}

  2) {Caminho B — revert}
     {motivo provável}

  3) {Caminho C — split / escalate}
     {motivo provável}

Sem auto-fix aqui — escolha humana.
```

### Exemplos vivos do projeto

**Exemplo 1 — Out-of-scope edit em Apply Mode** (de
`forge-implement-roteiro.md` §Cena 6):

```
Três caminhos legítimos:

  • Atualizar o Task Contract pra incluir Reminder.kt
    (se a mudança REALMENTE pertence a esta task — revisamos o spec)
  • Reverter a tentativa
    (esquece o campo novo nesta task)
  • Split numa task nova
    (registro como TASK-0008 e implementamos depois)
```

A → atualizar contract. B → reverter. C → split em nova task.

**Exemplo 2 — `check_no_invented_behavior` falhou** (de
`forge-verify-roteiro.md` §Cena 4):

```
Três caminhos pra resolver:

  1) Remover a linha 93 — evento não fazia parte da task.
  2) Adicionar o evento ao analytics-spec.yaml + re-verificar.
  3) Se o evento É necessário e estava implícito no ticket,
     abre o ticket pra revisão — sem plan amend, eu bloqueio.
```

A → adicionar ao spec (fix forward). B → remover linha (revert). C →
escalar pro ticket (escalate).

**Exemplo 3 — Dependência não satisfeita** (de
`forge-implement-roteiro.md` §Edge case 2):

```
Caminhos:
  • Implementar TASK-0004 primeiro (recomendado)
  • Revisar o task-breakdown se a dependência mudou
    (não rode forge plan de novo — usa forge evolve no contract)
  • Forçar mesmo assim → recuso. no-invented-behavior gate.
```

A → fazer o pré-requisito (fix forward). B → revisar o contrato de
dependência (revert no plano). C → forçar (escalate explicitamente
recusado — mentor calmo é firme).

### Referenced from

3-caminhos pattern — Referenced from:
`agents/planning-conductor.md` §When to push back ·
`docs/ux/forge-plan-roteiro.md` §Cena 9 elicitation drill-down ·
`docs/ux/forge-implement-roteiro.md` §Cena 6 out-of-scope + §Edge cases 2/3/7 ·
`docs/ux/forge-verify-roteiro.md` §Cena 4 drill-down hard-fail ·
`docs/ux/forge-doctor-roteiro.md` (todo gate de saúde reprovado) ·
`docs/ux/forge-evolve-roteiro.md` (rejeição de proposta = caminho C implícito) ·
`docs/ux/forge-reconfigure-roteiro.md` (conflito de cards = 3 caminhos).

---

## 2. Validator cascade policy

**Decisão:** a cascade **para no primeiro erro hard**, continua passando por
warnings. Esta regra vale pra `forge verify`, `forge doctor`, validators no
hook `post-subagent-validate`, e qualquer ponto que rode N validadores em
sequência.

### Semântica formal

| Severidade | Comportamento da cascade |
|---|---|
| `block` / `error` | Para imediatamente. Validadores seguintes mostram `—`. |
| `warning` | Continua. Coleta no buffer. |
| `info` | Continua. Coleta no buffer. |
| `degraded` (validador interno broken) | Continua. Marca verify como degradado. |

Ao final:
- Se houve hard fail → mostra apenas o fail (com 3-caminhos) + `—` nos
  validadores não rodados. Não mistura com warnings agrupadas.
- Se passou todos os hard → mostra warnings agrupadas em **uma única seção**
  antes do verdict.

### Override

`workflow-config.yaml` aceita:

```yaml
validators:
  fail-fast: true   # default
```

Quando `false`, a cascade coleta **todos os erros** antes de parar. Útil em
dois cenários reais:

1. **Primeiro verify após refactor grande** — usuário quer ver o panorama
   completo de problemas, não corrigir um por um descobrindo o próximo só
   depois de re-rodar.
2. **Pre-merge gate em CI** — quando a feature vai todo o cascade em modo
   batch e o agente humano não está em loop interativo.

Esse override é declarado no workflow-config, não via flag. Mantém
decisão 10 (zero flags).

### Exemplo de cascade com fail-fast=true (default)

```
├ validate_feature_package.py            ✓ 124ms
├ validate_readiness.py                  ✓ 218ms
├ validate_task_contract.py              ✓ 156ms
├ validate_data_contract.py              ✓ 312ms
├ validate_screen_analysis.py            ✓ 245ms
├ validate_backend_e2e.py                ✓ 482ms
│
├ check_no_invented_behavior.py          🛑 1.4s  FAIL
│
├ check_cyclomatic_complexity.py         — não rodado (cascade parou)
├ check_secrets.py                        — não rodado (cascade parou)
└ check_files_in_allowed_files.py        — não rodado (cascade parou)
```

### Posicionamento de `check_cyclomatic_complexity` (v1.2-dev+)

Novo gate (`check_cyclomatic_complexity`) entra na cascade **após**
`check_no_invented_behavior`. Justificativa: ambos são "anti-pattern
gates" (detectam algo errado no código vs. validators de schema/artefato),
e o CC gate é **menos crítico** que os anteriores — quando a cascade
chega no CC, o resto do feature já está coerente. Decision 23 (fail-fast)
preservada: validator anterior falha → CC nem roda; logged como `—` no
output.

Características operacionais do gate:

- **Multi-language** — um único validator dispatcha pra Detekt (Kotlin),
  SwiftLint (Swift), eslint (TS/JS), Radon (Python). Tools não-instaladas
  → `result_warn`, não bloqueia (UX: dev sem swiftlint não trava em
  Kotlin). `forge doctor § cc-gate-tools` reporta status + instruções.
- **Regra dupla** — função `new` (não existe em HEAD) obedece threshold
  absoluto; função `modified` aplica delta (`cc_after > cc_before` =
  fail, mesmo abaixo do threshold). Funções `unchanged` ignoradas.
- **Threshold lookup** — precedência card `cc-gate-override` >
  workflow-config `cc-gate` > defaults built-in. Tudo documentado em
  `docs/schemas/forge-config.md § cc-gate` + `docs/schemas/card.md §
  cc-gate-override`.
- **Override-justify por commit** — `CC-OVERRIDE: <file>:<func> cc=<N>
  — <razão>` no commit body silencia fail **só pra aquele commit**.
  Auditável via `git log --grep='CC-OVERRIDE'`. NÃO é whitelist
  persistente — pra isso existe override per-card.
- **Bypass de emergência** — env var `NO_CC_GATE=1`, logado em
  `.claude/state/cc-gate-bypass.jsonl`. Distinto do override-justify,
  que é por commit; bypass é por execução, raro e auditável.
- **3-caminhos on-fail** — render canônico conforme §1 acima
  (refactor / override-justify / split-task). Sem auto-fix.

Per-task em `forge implement` o gate roda como hook interno **entre**
review e commit — bloqueia o atomic commit se há fail sem override válido
no commit body já redigido. Cascade em `forge verify` roda standalone
sobre diff staged ou diff vs HEAD.

### Posicionamento de `check_secrets` (v1.2-dev+, R1.1)

Novo gate (`check_secrets`) entra na cascade **após**
`check_cyclomatic_complexity` — mesma família "anti-pattern gate", agora de
segurança. Ordem é deliberada: CC roda em ~segundos por feature, enquanto a
verificação ativa do trufflehog (cascade) pode demorar contra origens
externas; falhar antes em CC poupa esse tempo. Decision 23 (fail-fast)
preservada: gate anterior falha → secrets nem roda.

Características operacionais:

- **Per-stage tool split** — `gitleaks` (regex-based, ~100ms) roda no
  per-task hook de `forge implement` (stage="per_task"); `trufflehog
  --only-verified` roda na cascade de `forge verify` (stage="cascade"). As
  duas cobrem perfis complementares: gitleaks pega o token sintaticamente
  plausível antes do commit, trufflehog confirma se está ativo na origem
  antes do merge.
- **Binário, não-numérico** — secrets é detectou/não-detectou; sem threshold
  por linguagem. Hard-fail sempre quando um finding sobrevive. Tool missing
  → `result_warn` (não bloqueia), igual ao CC gate.
- **Override-justify por commit** — `SECRETS-OVERRIDE: <file>:<line>
  kind=<token-type> — <razão>` no commit body silencia o finding `(file,
  line, kind)` **só pra aquele commit**. Auditável via
  `git log --grep='SECRETS-OVERRIDE'`. Sem whitelist persistente — decisão
  deliberada (força o dev a articular razão visível em review).
- **Bypass de emergência** — env var `NO_SECRETS_GATE=1`, logado em
  `.claude/state/secrets-gate-bypass.jsonl`. Distinto do override-justify.
- **3-caminhos on-fail** — render canônico conforme §1 (remover+rotacionar /
  override-justify / marcar como fixture). Sem auto-fix.

Composto inteiro da infra Phase 0 (`dispatch_native_tool`, `apply_overrides`,
`check_tool_available`, `git_staged_files`, `read_commit_body`, `result_*`) —
2º consumer da extração, sem helper duplicado. Detalhe de config em
`docs/schemas/forge-config.md § secrets-gate`.

### Exemplo de cascade com fail-fast=false

```
├ validate_feature_package.py            ✓ 124ms
├ validate_readiness.py                  🛑 218ms  FAIL (1)
├ validate_task_contract.py              ✓ 156ms
├ validate_data_contract.py              🛑 312ms  FAIL (2)
├ validate_screen_analysis.py            ✓ 245ms
├ validate_backend_e2e.py                ⚠ 482ms  (3 warnings)
├ check_no_invented_behavior.py          🛑 1.4s   FAIL (3)
├ check_cyclomatic_complexity.py         🛑 2.1s   FAIL (4)
├ check_secrets.py                        ✓ 1.8s
└ check_files_in_allowed_files.py        ✓ 89ms

4 hard fails coletados — apresentando em ordem de aparição.
Resolva e re-rode.
```

Cada hard fail vira um bloco 3-caminhos separado. Warnings agrupam no fim.

### Referenced from

Validator cascade — Referenced from:
`docs/ux/forge-verify-roteiro.md` §Design points ("Cascade para no primeiro
fail") · `docs/ux/forge-doctor-roteiro.md` (mesma semântica de cascade) ·
`docs/schemas/forge-config.md` §validators.fail-fast ·
`.claude/hooks/post-subagent-validate.sh` (cascade local em hook).

### Overlay-awareness (Gap 5, 2026-06-02)

`validate_card_yaml` e `validate_capability_labels` são overlay-aware desde
2026-06-02 — catálogo efetivo é canon ∪ local. Loader helper
`validators/_common.load_catalog(project_root)` aplica guards
(promoção-reservada, colisão-canon, chaves proibidas) numa única passada.
Validators downstream consomem o resultado sem precisar repetir guards.

---

## 3. `.bak/` retention policy

Várias operações deixam backups no disco: `forge reconfigure` antes de
aplicar diff em workflow-config, card upgrade do canonical, distillation
de L2, schema migrations. Sem política, esses `.bak` viram lixo silencioso.

### Regras

1. **Localização canônica** — `.bak` mora **ao lado do arquivo original**,
   sufixo literal. Nunca em pasta separada `backups/`.
   - `.claude/workflow-config.yaml.bak`
   - `.claude/memory/L2-project.yaml.bak`
   - `.claude/cards/{name}/card.yaml.bak`
   - `.claude/cards/{name}/templates/X.md.bak`

2. **Retenção default: 7 dias.** Configurável em workflow-config:

   ```yaml
   cleanup:
     bak-retention-days: 7   # default
   ```

3. **`forge doctor` checa retenção.** Inclui um check `bak-files-overdue`
   que lista `.bak` mais antigos que a retenção. Mostra no relatório de
   doctor como **warning**, nunca como block.

4. **Nunca auto-deleta.** O usuário confirma via menu em
   `forge reconfigure` → opção "limpar bak antigos". A opção mostra a
   lista, pede confirmação, e só então remove.

5. **`.bak` recém-criado é hands-off.** Backups com idade < 24h nunca
   aparecem em sugestão de limpeza, mesmo se a retenção fosse curta. Dá
   espaço pro usuário rodar `forge undo` confiando que o backup tá lá.

### Quando NÃO criar .bak

Operações read-only nunca criam backup. Operações que afetam arquivos
gerados (i18n locales, templates re-render) também não — esses são
re-deriváveis. `.bak` só pra arquivos onde o usuário editou conteúdo
manualmente e perderia trabalho.

### Referenced from

`.bak/` retention — Referenced from:
`docs/ux/forge-reconfigure-roteiro.md` (apply diff cria `.bak`) ·
`docs/ux/forge-doctor-roteiro.md` (check `bak-files-overdue`) ·
`docs/schemas/forge-config.md` §cleanup.bak-retention-days ·
`docs/ux/forge-evolve-roteiro.md` (card upgrade cria `.bak`).

---

## 4. Fingerprint algorithm for rejected proposals

`forge evolve` precisa lembrar quais propostas o usuário já rejeitou pra
não re-propor o mesmo conteúdo em retrospectivas futuras. Sem isso, cada
feature traz de volta o mesmo "promover esse helper pra L2?" que o
usuário já recusou três vezes.

A pergunta: como definir "mesma proposta" sem ser frágil (timestamp
mudou, cosmetic edit no description) nem ser permissivo demais
(conteúdo realmente novo passa batido)?

### Algoritmo

```
canonical-form(p) = json-stringify-sorted({
  "type": p.type,
  "name": p.name-or-id-stripped,
  "description-normalized": casefold(NFC(strip-whitespace(p.description))),
  "provenance-set": sorted-array(p.provenance.feature-slugs)
})
fingerprint = sha256(canonical-form(p))
```

NFC normalization + Unicode casefold ensures fingerprints are stable across
visually-identical-but-byte-different text (e.g., precomposed vs decomposed
accents, mixed case). Implementation must use the same Unicode database
version across runs — pinned at the feature-forge version.

### Decisões de design

| Componente | Por quê |
|---|---|
| `type` | Distingue "promover helper" de "criar card novo" — mesmas palavras, intenções diferentes. |
| `name-or-id-stripped` | ID sequencial (P-001, P-002) é ignorado — só o nome semântico importa. |
| `description-normalized` | Lowercase + whitespace strip absorve edits cosméticos (vírgula, espaço duplo, capitalização). |
| `provenance-set` | Conjunto ordenado de slugs onde a proposta apareceu. Mesmo padrão emergindo em features novas continua mesmo fingerprint. |
| `sha256` | Determinístico, colisão-resistente, curto o suficiente pra index. |

### O que muda o fingerprint (intencionalmente)

- Mudou o `type` → fingerprint nova.
- Mudou o `name` → fingerprint nova (renomear conta como proposta nova).
- Reescreveu o `description` substantivamente → fingerprint nova
  (lowercase + whitespace não absorve mudança de conteúdo).
- Novas features na provenance — espera, isto NÃO muda fingerprint, porque
  o set é dos slugs presentes. Adicionar slug nova só **aumenta confiança**
  na proposta, não a redefine.

Espera — releitura: se `provenance-set` cresce, o set sorted muda. Então
fingerprint MUDA. Decisão consciente: quando a proposta volta com **nova
evidência** (mais features mostrando o padrão), é uma proposta nova
suficientemente pra reapresentar ao usuário, com a evidência adicional
exibida. Se isso virar ruidoso na prática, ajusta na v2 pra
`provenance-cardinality-bucket` (ex.: 1, 2-3, 4-7, 8+) em vez do set
completo.

### Storage

`.claude/memory/L1/proposed-evolutions/rejected-fingerprints.yaml`:

```yaml
rejected:
  - fingerprint: 7a3f...c2e1
    rejected-at: 2026-05-12T14:30:00Z
    user-reason: "ainda não vejo padrão claro"
    proposal-summary: "Promote ResultExtensions to shared/core/util/"
  - fingerprint: b91d...07a4
    rejected-at: 2026-05-22T09:11:00Z
    user-reason: "decide depois"
    proposal-summary: "Add card autocomplete-cross-feature"
```

`forge evolve` consulta antes de apresentar cada proposta. Se hit →
skip silencioso (não polui UX com "essa você já rejeitou"). Se a evidência
mudou e fingerprint nova → apresenta normalmente.

### Referenced from

Fingerprint algo — Referenced from:
`docs/ux/forge-evolve-roteiro.md` §rejection persistence ·
`agents/retrospective-agent.md` (gera fingerprint antes de propor) ·
`docs/schemas/memory.md` §L1.proposed-evolutions.rejected-fingerprints.

---

## 5. Batch-apply policy: single-by-single only

**Decisão:** `forge evolve` aplica propostas **uma a uma**, sempre. Nunca
batch, nunca `--yes-to-all`, nunca shortcut de alta confiança.

### Rationale

A engine nunca decide sem usuário (princípio do `00-vision.md`). Batch-apply
parece economia de tempo, mas é uma porta dos fundos pra engine substituir
julgamento humano em N decisões simultâneas. Mesmo proposta com
confidence=0.95, o "0.05 de incerteza" pode ser justamente o pedaço que
o usuário enxerga e a engine não.

Outra forma de ver: o valor de `forge evolve` **é** o gate humano. Tirar
o gate humano de N propostas com um único OK é tirar o valor da feature.

### UX accommodation

Pra runs com muitas propostas em alta confidence (cenário real depois de
feature grande), o roteiro **acelera a apresentação**, mas mantém a
confirmação per-proposta:

```
[1:12] Proposta P-001 · confidence 0.95
       Promover ResultExtensions pra shared/core/util/
       
       Evidência: usada em 4 features (lembrete-rega, bonsai-form,
                  task-create, auth-login)
       
       Diff:
         +shared/core/util/ResultExtensions.kt
         -shared/feature/lembrete-rega/.../ResultExt.kt
         -shared/feature/bonsai-form/.../ResultExt.kt
         (...)
       
       [a]plicar  [r]ejeitar  [d]epois  [v]er-detalhe
> a

[1:14] ✓ Aplicado. Próxima.

[1:14] Proposta P-002 · confidence 0.92
       (...)
```

Cada `a` é uma decisão consciente. Mentor calmo apresenta rápido, mas
**nunca** apresenta `[a]plicar todas`.

### O que não existe (deliberadamente)

- ❌ `forge evolve --batch`
- ❌ `forge evolve --yes-to-all`
- ❌ Menu interativo "aplicar todas as restantes"
- ❌ Threshold de confidence pra auto-apply
- ❌ "Cards" de N propostas aplicadas como grupo

### Referenced from

No-batch-apply — Referenced from:
`docs/ux/forge-evolve-roteiro.md` §apply loop · `agents/retrospective-agent.md`
(propostas são unitárias por design) · `docs/design/00-vision.md`
("user is in the loop on all memory mutations").

---

## 6. L2 overflow durante evolve apply

L2 tem `max-size-mb` em workflow-config (default ~512KB). Quando uma
proposta aprovada pelo `forge evolve` adicionaria conteúdo a L2 e
ultrapassaria o limite, a engine precisa decidir: distillar
automaticamente, falhar, ou pausar?

### Decisão: pause + notify

Auto-distill durante apply **quebra contexto pendente** — o usuário
está no meio de aprovar propostas, e distillation muda L2 sob seus pés.
Pode invalidar a proposta P-003 que ele estava revisando porque o
conteúdo que ela referenciava foi distilado.

Em vez disso:

1. Apply detecta que a próxima aprovação ultrapassaria `max-size-mb`.
2. Pausa **antes** de aplicar. Estado da run é serializado em
   `.claude/.evolve-checkpoint.yaml` com `status: deferred-l2-full`.
3. Notifica o usuário:

   ```
   [2:34] 🛑 L2 cheia
          
          L2-project.yaml: 498 KB / 512 KB (97%)
          Próxima aprovação adicionaria ~22 KB.
          
          Auto-distill **não roda aqui** — você está no meio de aprovar
          propostas e mudar L2 sob seus pés invalidaria as próximas.
          
          Caminhos:
            • forge memory → "distill L2"   (depois retoma evolve)
            • forge evolve (retoma)         (após distill manual)
            • Pausar e revisar depois       (estado salvo)
          
          O que prefere?
   ```

4. Usuário roda `forge memory` → distill, depois retorna a `forge evolve`,
   que detecta `.evolve-checkpoint.yaml` e auto-resume da proposta
   pendente.

### Por que não auto-distill silenciosamente

- Quebra contexto do usuário (acima).
- Distillation é mutação de memória → precisa do mesmo gate humano que
  toda mutação de memória (princípio do `00-vision.md`).
- Se distillation falhar (raro mas possível), o erro fica escondido no
  meio de `forge evolve` — má UX.

### Por que não falhar hard

Forçar o usuário a abortar e re-rodar perde o checkpoint das propostas
já revisadas na sessão. Pausa + retoma preserva trabalho.

### Caso degenerado: L2 já está cheia ao iniciar evolve

`forge evolve` detecta no início e bloqueia com mesma mensagem antes de
apresentar qualquer proposta. Sem checkpoint a salvar, retomada é
imediata após distill.

### Referenced from

L2 overflow — Referenced from:
`docs/ux/forge-evolve-roteiro.md` §pre-flight L2 check ·
`docs/ux/forge-doctor-roteiro.md` §memory size check ·
`docs/schemas/memory.md` §max-size-mb · `docs/schemas/forge-config.md`
§memory.l2.max-size-mb.

---

## 7. Ctrl+C / "para" mid-loop semantics

Usuário interrompe no meio de `forge plan`, `forge implement`, `forge evolve`,
`forge reconfigure` (qualquer comando que tenha loop interativo). Existem
**duas** semânticas distintas e elas precisam estar separadas:

### Pause (default)

Ctrl+C **ou** digitar `para` interrompe o loop e **salva como deferred**:

- A proposta / task / elicitation **em curso** vira `state: deferred` em
  `status.json` (não `aborted`).
- Timestamps `last-action-at` preservados — auditável.
- Estado dos artefatos parciais escrito em disco antes de sair (não há
  perda de progresso).
- Mensagem de saída:

  ```
  Pausei aqui. Estado salvo em .claude/memory/L1/{slug}/status.json
  
  Pra retomar: forge {plan|implement|evolve} {slug}
  ```

- Próxima execução do mesmo comando detecta `state: deferred` e auto-resume
  exatamente onde parou (sem perguntar "do you want to resume?" — o resume
  É o default; ambiguidade só surge se usuário quer recomeçar do zero,
  e nesse caso é `forge undo` quem aborta).

### Abort (explícito)

Pra **terminar** uma feature/run definitivamente (não pausar), o usuário
roda `forge undo` interativamente e escolhe a opção "abort feature
entirely":

- Marca `state: aborted` em `status.json` com `aborted-reason`.
- Não auto-resume mais.
- Artefatos parciais permanecem no disco (pra inspeção / debugging) mas
  não bloqueiam um `forge plan {slug-novo}`.
- Comando que tentar resumir uma feature `aborted` mostra:

  ```
  Feature {slug} está marcada como aborted (2026-05-15, motivo: "decidimos
  não fazer essa feature agora").
  
  Caminhos:
    • forge plan {slug} — re-abrir do zero (preserva artefatos como histórico)
    • forge undo → "delete feature artifacts" — limpa do disco
    • Esquece, sair daqui
  ```

### Diferença em uma frase

- **Pause** = transient, auto-resumable, default em Ctrl+C / "para".
- **Abort** = terminal, explicit, só via `forge undo` interativo.

### Por que `para` não aborta

"Para" parece final, mas no contexto de loops longos (planning com waves,
implement com Plan→Apply→Verify), o usuário frequentemente quer pausar
pra pensar, tomar café, dormir, voltar amanhã. Tratar `para` como abort
perde trabalho de horas. Pause é o default seguro.

Pra abort de verdade, o usuário sai do flow pause e roda `forge undo`
explicitamente. Dois passos pra ação destrutiva — disciplina.

### Estado intermediário não existe

Não há `state: paused` separado de `deferred`. Não há `state: aborting`
em transição. Os estados de feature são:

```
not-started → planning → planned → implementing → done
                ↓             ↓           ↓
             deferred ←─ deferred ←─ deferred       (pausa)
                                ↓
                             aborted                 (terminal)
```

Deferred é uma anotação ortogonal ("trabalho parou aqui"), não um estado
de pipeline. Estado de pipeline continua sendo o último marco atingido.

### Referenced from

Pause vs abort — Referenced from:
`agents/planning-conductor.md` §When to abort · `docs/ux/forge-plan-roteiro.md`
§pause behavior · `docs/ux/forge-implement-roteiro.md` §Cena 6 + edge cases ·
`docs/ux/forge-evolve-roteiro.md` §interrupt mid-apply ·
`docs/schemas/memory.md` §status.json.state.

---

## 8. Non-product feature track (subtypes)

Forge nasceu modelando features de produto — telas, contratos, eventos de
analytics. Stress test 2026-05-29 (cenários A3/A4) mostrou que isso quebra
em três classes legítimas de trabalho mobile, e o stress test seguinte
(cenário A1, 2026-05-30) adicionou uma quarta:

- **Refactor** — comportamento inalterado por design. Mover `MeoButton` de
  `organisms/` para `atoms/`, renomear pacote, migrar de Nav2 para Nav3 em
  uma feature já implementada. Sem PRD natural, sem screen-analysis (zero
  mudança visual), sem analytics nova.
- **Bugfix** — restaurar comportamento correto. Bug com reprodução
  conhecida, root-cause analisável, fix localizado, atomic commit. NÃO
  é "feature pequena" (essas continuam product) — é o caso onde existe
  um comportamento documentado-ou-esperado que está quebrado e precisa
  voltar a funcionar. Frequentemente urgente (P0/P1, hotfix, ticket de
  produção), o que torna especialmente importante cortar cerimônia
  desproporcional sem sacrificar disciplina.
- **Spike** — investigação técnica. Comportamento ainda desconhecido,
  output esperado é findings/decisão, não código de produção. Forçar Wave
  B faria conductor inventar PRD.
- **Chore** — atualização de dependência, bump de versão, cleanup. Mesma
  classe: sem produto, sem comportamento novo.

Forçar essas três classes pelo pipeline default viola **dois princípios
load-bearing simultaneamente**:

1. `00-vision §What feature-forge is NOT` ("never invents") — sub-agents
   produzem 5 specs vazias ou artificiais.
2. `agents/planning-conductor.md §Discipline 3` ("Never invent") —
   conductor é obrigado a inventar PRD/screen-analysis pra alimentar Waves
   B e C.

A remediação é um **guarda-chuva non-product-feature track** com 4 subtipos
(`refactor`, `bugfix`, `spike`, `chore`). Subtype é detectado conversacionalmente
em Cena 2.5 do `forge-plan-roteiro.md` (zero flag — Decision 10 preservada),
persistido em `status.json.subtype` e em `hypothesis.yaml.subtype`, e o
conductor branch o wave dispatch a partir dele.

### Subtype semantics (v1.0)

| Subtype | Waves | Artifacts produzidos | Validators extras |
|---|---|---|---|
| `product` (default) | A · B · C · D · E | 16 artefatos canônicos | (cascade padrão) |
| `refactor` | A · C · D · E (Wave B **skipped**) | intake (refactor variant) · tech-spec parcial (§§ 2 + 3-7 modified-layers + 14) · task-breakdown · TASK-NNNN · readiness · handoff | `check_no_behavior_change` em Wave E |
| `bugfix` | A · (**B conditional**) · C · D · E | intake (bugfix variant) · Wave B artifacts iff UI/behavioral · tech-spec focado (§§ 1 · 2 · 3-7 touched-layers · 13 · 14) · task-breakdown (1 task default) · TASK-NNNN · readiness · handoff · 5-whys retro template | (cascade padrão; o fix muda comportamento por definição — `check_no_behavior_change` não se aplica) |
| `spike` | Stub em v1.0 — conductor surfaces 3-caminhos | n/a | n/a |
| `chore` | Stub em v1.0 — conductor surfaces 3-caminhos | n/a | n/a |

### Refactor — comportamento detalhado (única subtype completa em v1.0)

**Wave A — `feature-intake.md` (refactor variant)**

O intake usa `templates/feature-intake-refactor.template.md` (drop das
seções "user value", "business outcome", "target persona") e ganha duas
seções dedicadas:

- §Problem — o que está errado hoje (acoplamento, naming, location)
- §Files affected — paths concretos a serem tocados
- §No-behavior-change attestation — declaração explícita "este refactor
  não muda comportamento observável"

Não há `feature-prd.md` no refactor variant. PRD pressupõe valor de
usuário; refactor por definição não muda o que o usuário vê.

**Wave B — SKIPPED integralmente**

Nenhum dos artefatos behaviorais faz sentido em refactor:
- `screen-analysis.md` — sem mudança visual, nada pra analisar
- `bdd.md` / `bdd.json` — sem comportamento novo, scenarios vazios
- `ui-state-spec.yaml` — UI state inalterado
- `navigation-spec.yaml` — rotas inalteradas
- `data-contract-spec.yaml` — schema inalterado
- `analytics-spec.yaml` — sem eventos novos
- `test-strategy.yaml` — strategy = "rodar tests existentes, comportamento
  inalterado" (capturado na própria readiness)

Forçar esses artefatos forçaria conductor a inventar, violando discipline
3 da planning-conductor.

**Wave C — `tech-spec.md` (refactor variant)**

Renderiza apenas:
- §2 Architecture overview — **antes/depois** explícito
- §§ 3-7 — só as layers que mudam (geralmente uma única layer; se o
  refactor toca 3 layers, o intake já levantou flag)
- §14 Cross-feature reusability — preserve, pode emergir oportunidade
- §§ 8-13 (state mgmt, side effects, dispatchers, observability, tests,
  risks) — **omitidas**. State machine não muda em refactor; observability
  fica intacta por design.

**Wave D — `task-breakdown.yaml` + `tasks/TASK-NNNN.yaml`**

Task contracts com `allowed_files` precisos. Refactor geralmente vira 1-3
tasks (extrair, atualizar referências, validar). Cada task declara
explicitamente `validations: [check_no_behavior_change]` em adição às
validações padrão.

**Wave E — readiness-reviewer aceita Wave B skipada quando `subtype=refactor`**

O readiness-reviewer's checklist sub-section "Wave B artifacts present"
torna-se opcional condicional: a checagem renderiza "n/a (subtype=refactor)"
em vez de falhar.

### O novo validator `check_no_behavior_change`

Em Wave E (e novamente em `forge verify` durante implement), quando
`status.json.subtype == "refactor"`, a cascade roda `check_no_behavior_change`:

- Lê `git diff --cached --name-only` (ou diff da feature contra HEAD em
  modo verify).
- Marca como **fail** se algum arquivo de teste funcional na scope da
  feature está sendo modificado/adicionado.
- Modificar teste em refactor é sinal forte de mudança comportamental
  disfarçada — "ajustei o teste pra passar com o novo código" é
  literalmente a definição de mudança comportamental.
- Adicionar novo teste pra cobertura adicional é OK (e útil), mas em
  v1.0 conservadoramente todo touch em test files levanta 3-caminhos:
  - A) Confirmar attestation — extender allowed_files declarando que
    estes tests precisaram mudar e por quê
  - B) Reverter mudança de teste
  - C) Split — virar feature subtype `product` se o refactor de fato
    muda comportamento

### Bugfix — comportamento detalhado (Gap 1, 2026-05-30)

**Quando bugfix subtype se aplica**

Bugfix existe pra um caso preciso: um único bug, root-causable, fix-shaped.
Critérios de detecção:

- Reprodução concreta (steps OU vídeo OU log) — não "tem algo estranho"
- Comportamento esperado é articulável — "deveria mostrar X, mostra Y"
- Fix se encaixa em um atomic commit OU 1-2 tasks correlatas
- Frequentemente trackeado em ticket de produção (IN-NNNNN, PD-NNNN,
  BACKEND-NNNN style)

**Não é bugfix:**

- "Feature pequena" (1-2 tasks) que adiciona comportamento novo →
  product (naturally small). Não há mecanismo especial pra A2 (small
  feature); a plan IS small porque a feature IS small.
- "Bug" sem reprodução e sem comportamento esperado claro → ainda não
  é um bugfix; é uma investigação. Conductor drilla pra concretizar OU
  rota como product (com pesquisa) OU como spike (quando v1.1+ chegar).
- Refactor que descobriu bug embutido → escalate para conductor
  reavaliar subtype; pode virar bugfix OU product dependendo da
  profundidade.

**Distinção formal de refactor:**

| Eixo | Refactor | Bugfix |
|---|---|---|
| Mudança de comportamento | Proibida por design | **Inerente** — de quebrado para correto |
| Wave B | Skipped sempre | **Conditional** (UI/behavioral → run; logic-only → skip) |
| Tests existentes | Não toca (gate `check_no_behavior_change`) | **Pode tocar** — testes provam que o bug existia + agora não existe |
| Atestation block | "No-behavior-change" no intake | "Reproduction steps" + "Expected vs actual" no intake |
| Retrospective | Surface de promoção de helpers | **5-whys obrigatório** — root cause depth, não fix shape |

**Wave A — `feature-intake.md` (bugfix variant)**

O intake usa `templates/feature-intake-bugfix.template.md` com seções
específicas pra bug:

- §Problem statement (1 parágrafo — o que está quebrado)
- §Reproduction steps (numerados, MANDATORY — sem repro o bug não é
  planável)
- §Expected vs actual behavior (lado a lado)
- §Root-cause hypothesis (com confidence; "unknown" é válido mas trigga
  drill-down do conductor antes da Wave B)
- §Fix scope (estimativa de arquivos afetados)
- §Regression risk (o que pode quebrar se o fix introduzir efeito
  colateral)
- §Validation strategy (como saber que o bug realmente sumiu — repro
  passa pra "comportamento esperado" + testes regressão)
- §Links (ticket id, related commits, affected versions)

Diferente de product: sem "user value paragraph", sem "scope OUT"
(bugfix é fix de bug, escopo é o próprio bug), sem "why now" (porque
está quebrado).

**Wave B — conditional**

Conductor pergunta UMA vez em Cena 2.5 (após confirmação do subtype):

> "Esse bug envolve mudança de UI ou de comportamento observável?
>  (sim → Wave B roda; não → logic-only, Wave B skipada)"

Critérios pra "sim":

- Bug visual (layout quebrado, copy errada, estado UI travado)
- Bug de navegação (rota quebrada, back-stack errado)
- Bug de comportamento user-facing (validação faltando, mensagem de
  erro errada, fluxo interrompido)
- Novo evento de analytics seria útil pra detecção (raro, mas válido)

Critérios pra "não":

- Bug puramente de lógica (cálculo errado, condição invertida, off-by-one)
- Bug de dados (mapping errado, schema parse falho, timezone)
- Bug de concorrência (race, deadlock, retry storm)
- Bug de infraestrutura (config, build, deploy)

**Decisão clave:** se "sim", a Wave B completa roda. Não tem variante
"meia Wave B". O bug touched contract → todo o contrato precisa estar
respeitado pelo fix. Mentor calmo: "se touching UI, vou querer todos os
estados modelados — caso contrário, fix vai introduzir regressão num
estado que ninguém pensou."

**Wave C — `tech-spec.md` (bugfix variant)**

Renderiza:

- §1 Feature summary — pulled do intake §Problem + §Reproduction
- §2 Architecture overview — só o **antes** (estado atual com bug) +
  **depois** (estado corrigido); paralelo a refactor mas com foco no
  ponto exato da mudança
- §§ 3-7 — só as layers tocadas pelo fix (igual a refactor)
- §13 Risks & open questions — **expandido** com "Regression risks"
  vindos do intake §Regression risk
- §14 Cross-feature reusability — preservado (bugfix pode surfacing
  refactor candidates)
- §§ 8-12 — **omitidas por default**. Bugfix raramente introduz nova
  state machine, novo side effect, novo observability. Exceção: §11
  Observability **renderiza quando o fix introduz analytics novo** (raro
  mas válido — "vou logar quando esse bug acontecer pra detectar
  regressão futura").

**Wave D — `task-breakdown.yaml` + `tasks/TASK-NNNN.yaml`**

Default: **1 task**. Bug → 1 fix → 1 atomic commit é o shape natural.
Conductor pode propor split quando:

- Fix toca shared + Android + iOS (3 plataformas → 3 tasks paralelas)
- Fix tem step preparatório (refactor pré-fix) + step de fix em si
- Dev pede split explicitamente

Cada task contract:
- `allowed_files` preciso
- `validations: [check_files_in_allowed_files, validate_task_contract]`
  (cascade padrão; `check_no_behavior_change` NÃO se aplica)
- Reference ao bug ticket no `metadata.bug_ticket` se existir

**Wave E — `readiness-reviewer`**

Readiness relaxada quando Wave B foi skipada:

- Não pede screen-analysis presente (skipada por design)
- Não pede contracts presentes (skipada por design)
- Pede: intake completo com §Reproduction + §Expected vs actual +
  §Validation strategy
- Pede: tech-spec mínimo (§1 + §2 + ≥1 layer + §13)
- Pede: task-contract com allowed_files

Verdict `ready` quando todas as checks acima passam. `partial` quando
§Root-cause é unknown — bug pode entrar implement mas a hipótese de
causa fica como open-question pra resolver durante o fix.

**Phase 6 retrospective — 5-whys (Gap 1 mandatory)**

Bugfix retrospective tem maior valor de aprendizado de todos os subtipos:
o bug existiu, o fix foi escrito, agora a pergunta é "o que **impediria**
esse bug de ter existido?". Retrospective-agent (Phase 6 do conductor)
emite proposed-evolutions baseado no 5-whys:

```
1. Why did this bug occur?
   → {root cause direta — do intake §Root-cause hypothesis confirmed}

2. Why did the root cause happen?
   → {causa estrutural — faltou validação? typing? teste?}

3. Why did that structural cause exist?
   → {causa processual — review pulou esse caso? convenção não cobria?}

4. Why is the process gap there?
   → {causa cultural — pressão de release? documentação missing?}

5. Why is THAT the culture/cause?
   → {causa fundadora — opcional; pode chegar em "trade-off válido"}
```

Output esperado:
- ≥1 proposta concreta pra L2 (pattern, rule, validator novo)
- 0 propostas vazias ("seja mais cuidadoso" não é uma proposta)

Diferente de refactor retrospective (que surface CFR candidates) e
product retrospective (que surface naming patterns / arquitetural
patterns), bugfix retrospective surface **gates** — "o que poderia ter
pegado isso antes?"

### Filesystem layout

`docs/feature-implementation-workflow/non-product/{slug}/` paralelo a
`features/{slug}/`. Mesmo `.claude/memory/L1/{slug}/` para `L1`. Sub-tree
de status, history, dispatch-log, verify-log idênticos. Bugfix usa o
mesmo `non-product/{slug}/` que refactor — decisão deliberada: bugfix
também é "não é nova product behavior", é "restaurar product behavior
correto", então pertence ao mesmo guarda-chuva non-product.

### Spike e chore em v1.0 — stub via 3-caminhos

Quando Cena 2.5 detecta keywords de spike (`POC`, `viabilidade`, `spike`,
`exploração`) ou chore (`bump`, `atualizar dependência`, `cleanup`,
`limpeza`), conductor confirma o subtype e em seguida emite:

```
🛑 Subtype '{subtype}' ainda não tem implementação completa em v1.0.

   v1.0 ship `refactor` por completo. `spike` e `chore` estão
   programados pra v1.1+ — sem improviso aqui.

   Três caminhos:

     1) Tratar como feature padrão (subtype=product)
        Você terá Waves B/C completas — sub-agentes vão pedir
        contexto que pode parecer artificial pro caso. Faz sentido
        quando o spike/chore tem dimensão de comportamento real
        (ex.: chore com flag rollout).

     2) Esperar v1.1+
        Pause aqui. Eu marco status como deferred e quando
        v1.1+ chegar o subtype completo, retomamos.

     3) Abortar
        Sai do forge plan, faz o trabalho fora do pipeline. Não
        viola disciplina; só não fica trackeado.

   Voz humana decide.
```

Spike+chore stub é um dos itens da lista de **residuais TODO** que
04-pending.md documenta no fechamento da Gap 2 — não vão silentes pra
backlog, são explicitamente parte do roadmap v1.1+.

### Subtype detection (resumida — completa em forge-plan-roteiro.md §Cena 2.5)

Cena 2 source-inquiry parseia keywords da resposta livre do usuário:

| Keyword/padrão | Subtype provável |
|---|---|
| `mover X de Y`, `renomear`, `extrair`, `refactor`, `reorganizar`, `sem mudança visual`, `comportamento inalterado` | refactor |
| `bugfix`, `hotfix`, `P0`, `P1`, `crítico`, `crítica`, `bug `, `fix `, `falha`, `quebrado`, `não funciona`, `regression`, ticket pattern (`IN-NNNNN`, `PD-NNNN`, `BACKEND-NNNN`) | bugfix |
| `spike`, `POC`, `viabilidade`, `prototipar`, `investigar se`, `exploração` | spike |
| `bump`, `atualizar dependência`, `update {dep}`, `cleanup`, `limpeza`, `chore` | chore |
| (nada match) | product (default) |

Ticket pattern é alto-confiança: regex `[A-Z]{2,6}-\d{2,6}` na entrada
livre frequentemente indica bug rastreado em sistema externo. Conductor
ainda confirma — mas o default da pergunta vira "isso parece bugfix"
em vez de "isso parece product".

Detection é **inference, não imposição**: conductor confirma com pergunta
de uma linha ("isso parece refactor — confirma?") e aceita user override
("não, é product"). Cena 2.5 mostra o flow completo com voz mentor-calmo.

### O que esta discipline NÃO faz

- Não invalida nenhuma das 27 decisões locked.
- Não introduz comando novo (`forge refactor` não existe — `forge plan`
  com subtype detectado em Cena 2.5).
- Não adiciona flag (`--subtype=refactor` não existe — conversational).
- Não cria estado novo de feature (subtype é dimensão ortogonal ao state
  enum existente).
- Não obriga refactor a virar product — usuário sempre pode dizer "não,
  é product" e Wave B roda normalmente.

### Referenced from

Non-product feature track — Referenced from:
`docs/schemas/memory.md §status.json subtype field` ·
`docs/design/05-filesystem-layout.md §non-product/{slug}/` ·
`agents/planning-conductor.md §Phase 1 + §Phase 4 wave dispatch branching + §Phase 6 5-whys retrospective` ·
`agents/tech-spec-agent.md §Document structure conditional render` ·
`docs/ux/forge-plan-roteiro.md §Cena 2.5 Subtype detection` ·
`engine/plan.py _initialize_status + _dispatch_waves_for_subtype` ·
`validators/check_no_behavior_change.py` ·
`templates/feature-intake-refactor.template.md` ·
`templates/feature-intake-bugfix.template.md`.

---

## 9. External dependencies (`blocked-on-external`)

Mobile features routinely depend on work outside the repository: a backend
endpoint behind another team, a legal copy review, a Figma asset still in
revision. Stress test 2026-05-30 (cenário B3) confirmed forge had no
first-class way to model this. Feature would sit in `state: implementing`
with `current-task: null`, dev would open `forge implement`, pick a task,
hit the dependency, lose time discovering it.

The remediation is a **new feature lifecycle state** plus a **per-task
declaration** of external dependencies — both file-driven, both
recomputable from disk, both auditable.

`blocked-on-external` is the engine-driven sibling of `deferred`
(human-driven pause from §7). The two are **deliberately separate**: a
human pause uses one exit path (resume by re-running the command); an
external dependency uses a different exit path (mark the ticket as
resolved interactively via `forge reconfigure`). Conflating them would
make resume ambiguous.

### When the gate triggers

`engine/implement.py` refuses to start a task that has at least one
`depends-on-external` entry with `blocking: true` and `resolved-at: null`.
On the first refusal of a session, it also flips the feature-level state
in `status.json` from `implementing` (or `planning`) → `blocked-on-external`,
so `forge status` and downstream commands see the same signal.

### When the gate releases

The user runs `forge reconfigure` and picks "marcar dep externa como
resolvida". The interactive prompt asks for the ticket id, locates every
`depends-on-external` entry referencing that ticket across all task
contracts in the feature, fills `resolved-at` with the current UTC
timestamp, and re-evaluates the feature state. When zero blocking deps
remain unresolved, the feature flips back to its previous lifecycle state
(`implementing` if at least one task was in-flight, otherwise `planning`).

### Why manual unblock (v1.0)

MCP polling — Jira webhook → `forge ingest --event
external-dep-resolved` → auto-flip — is the obvious v1.1+ extension. It
is **out of scope for v1.0** for two reasons:

1. **Trust gate.** Marking a ticket resolved is a state mutation that
   downstream commands trust. A misfired webhook (Jira ticket reopened,
   integration desync) would lie to `forge implement` about safety to
   proceed. Manual confirmation via `forge reconfigure` keeps the
   human in the loop on every mutation (00-vision §"The user decides").
2. **Surface stability.** v1.0 already has 12 commands + 1 hidden
   ingest entrypoint. Adding `--event external-dep-resolved` to the
   ingest routing table requires designing failure modes (auth, retry,
   idempotency) that aren't load-bearing for the v1.0 ship. Better to
   ship the schema + manual flow first, then layer the polling on
   top once the manual flow is validated.

The stub surface is documented in `docs/lifecycle/memory-and-graph.md`
under "Out of scope for v1" so the v1.1+ path is explicit.

### Three-caminhos at the gate

When `forge implement` refuses, the user sees the canonical block from §1:

```
🛑 Task bloqueada por dependência externa

O que falhou:
  TASK-{NNNN} depende de {ticket} ({integration}) — ainda não resolvido.

Onde:
  tasks/TASK-{NNNN}.yaml.depends_on_external[0]

Por que importa:
  · Hard-gate readiness-must-be-ready exige dependências resolvidas
  · execution-conductor recusa começar com `resolved-at: null`
  · Continuar sem isso vira invented behavior contra um endpoint que
    ainda não existe — bug latente

Três caminhos pra resolver:

  1) Marcar dependência como resolvida agora
     forge reconfigure → "marcar dep externa como resolvida"
     (use quando o ticket externo já fechou e você sabe disso)

  2) Pegar outra task que não dependa de {ticket}
     forge implement {slug} pula a bloqueada e pega a próxima
     livre — útil quando há tasks paralelas na breakdown

  3) Pausar a feature inteira
     deferred — você volta quando o ticket fechar; status fica
     auditável em forge status

Sem auto-fix aqui — escolha humana.
```

Path A flips a single ticket. Path B reroute around the block. Path C
escalates to a longer pause. Three honest exits.

### Subtype interaction (§8) — no conflict

`subtype` (what kind of feature: product / refactor / spike / chore) and
`state` (where in lifecycle, including `blocked-on-external`) are
**orthogonal dimensions**. Both live in status.json. A refactor feature
can wait on an external linter rule upgrade ticket — refactor +
blocked-on-external. The `check_no_behavior_change` gate runs only when
subtype=refactor; the external-dep gate runs regardless of subtype.

### Pause-vs-abort interaction (§7) — preserved

`blocked-on-external` does NOT replace `deferred` / `aborted`. The user
can still type `para` (→ `deferred`) or `forge undo` → "abort feature
entirely" (→ `aborted`) on a blocked feature. The blocked state is what
the engine sets autonomously; pause/abort remains the explicit human
override.

### `forge status` board

`forge status` separates **In-flight** (planning/implementing without
external blocks), **Blocked** (state=blocked-on-external), **Deferred**
(state=deferred), **Done** (state=done). The Blocked section lists each
ticket and integration alongside the feature slug so the user knows what
to chase externally:

```
blocked on external
  · lembrete-rega         BACKEND-1284 (jira)
                          desde 2026-05-30 · 1 task bloqueada
  · bonsai-detail-share   DESIGN-44 (manual)
                          desde 2026-05-29 · 2 tasks bloqueadas
```

### Partial-ready (readiness-reviewer extension)

When some tasks in a feature have external blocks but the non-blocked
subset has its own valid coverage (every Wave A-D artifact present, all
contracts pass, BDD scenarios trace forward for the non-blocked tasks),
the readiness-reviewer emits **`ready-with-blocks`** — a new partial
verdict distinguishing "subset is shippable now" from the legacy
"partial" (which meant "phase-locked open questions"). Treatment:

| Verdict | Meaning | `forge implement` behavior |
|---|---|---|
| `ready` | All tasks ready, zero blockers | Picks next task normally |
| `ready-with-blocks` | Non-blocked subset complete; ≥1 task blocked on external | Picks next non-blocked task; refuses blocked ones with 3-caminhos |
| `partial` | Phase-locked open questions remain | Same as today — conductor flags |
| `blocked` | Required artifact missing OR validator fail OR blocking OQ | Refuse implement |

`ready-with-blocks` is **opt-in via task-contract declaration** — it
never triggers without an explicit `depends-on-external` entry. Forge
does not infer external blockers from natural language.

### What's NOT in v1.0

- ❌ Auto-promote `ready-with-blocks` → `ready` when external deps
  resolve. User confirms manually via `forge reconfigure`.
- ❌ MCP polling for ticket state. Stubbed under
  `docs/lifecycle/memory-and-graph.md §Out of scope for v1`.
- ❌ `forge implement --force` bypass. Decision 10 (zero flags).
- ❌ Per-ticket TTL or auto-stale warnings. v1.1+ when there's data
  to know what "stale" means in practice.

### Referenced from

External dependencies — Referenced from:
`docs/schemas/memory.md §state.blocked-on-external` ·
`templates/task-contract.template.yaml §depends_on_external` ·
`agents/planning-conductor.md §Phase 2 external-dep elicitation` ·
`agents/task-contract-writer.md §depends_on_external rendering` ·
`agents/readiness-reviewer.md §ready-with-blocks verdict` ·
`docs/ux/forge-plan-roteiro.md §Cena external-dep detection` ·
`docs/ux/forge-implement-roteiro.md §blocked task refusal` ·
`docs/ux/forge-reconfigure-roteiro.md §marcar dep externa como resolvida` ·
`engine/memory/l1.py is_blocked + blocking_deps` ·
`engine/implement.py blocked refusal` ·
`engine/status.py blocked section` ·
`engine/reconfigure.py mark-external-dep-resolved menu` ·
`validators/validate_task_contract.py depends_on_external schema`.

---

## 10. Extension feature

Feature done que ganha escopo correlato — variant, módulo paralelo,
integração paralela — não cabe como feature standalone (perde herança do
contexto da pai) nem como refactor (refactor não muda comportamento;
extension ADICIONA). Stress test 2026-05-29 (cenário C2) mapeou o caso;
revisita 2026-06-03 separou a mecânica `extends-feature` do escopo
multi-target (watchOS/Wear/TV — out-of-scope permanente, documentado em
`docs/design/04-pending.md §Gap 9`).

A remediação é um **pattern leve de feature derivada**: novo slug derivado
+ campo aditivo `extends-feature: {parent-slug}` no L1 status + bloco
§Extension context no intake + caminho explícito em Cena 1 do
`forge plan`. Zero comando novo (Decision 9 preservada), zero flag
(Decision 10), zero card novo (Decision 28 — overlay não requerido).
Extension = `subtype: product` com parent linkado — `_VALID_SUBTYPES`
permanece em 5 valores (`product | refactor | bugfix | spike | chore`).

### Quando aplica

- Feature `state: done` ganha escopo novo correlato e o user pede pra
  reaproveitar contexto (contracts, screens baseline, naming
  conventions) sem polluir o L1 da feature original.
- Casos canônicos: variant operacional (parent shippa onboarding; extension
  adiciona onboarding-empresarial paralelo), módulo paralelo (parent
  shippa lembrete-rega; extension adiciona lembrete-rega-notificacao),
  integração paralela (parent shippa weather-integration via OpenWeather;
  extension adiciona weather-integration-fallback via WeatherAPI).

NÃO usar pra:

- Refactor (use §8 refactor subtype — comportamento inalterado por design).
- Bugfix (use §8 bugfix subtype — restauração de comportamento existente).
- Feature standalone nova (sem dependência semântica de outra feature
  done — parte do zero, `extends-feature: null`).

### Distinção formal vs outros tipos

| Eixo | Refactor (§8) | Bugfix (§8) | Extension (§10) | Standalone product |
|---|---|---|---|---|
| Mudança de comportamento | Proibida por design | Inerente (de quebrado → correto) | **Aditiva** (preserva baseline da pai + adiciona delta) | Comportamento novo de zero |
| Parent context | n/a (feature mesma) | n/a (feature mesma) | **Herdado** via `extends-feature` (contracts, screens baseline, naming) | n/a (sem parent) |
| Retro strategy | Surface CFR candidates | 5-whys obrigatório (Gap 1) | **"O que herdei vs adicionei"** (sem 5-whys) | Naming/arquitetural patterns |
| Wave A discovery | Refactor variant (Problem + Files + No-behavior attestation) | Bugfix variant (Reproduction + Expected vs actual + Validation) | **Product variant + §Extension context block** (parent slug + scope of extension + reuse from parent + out-of-scope vs parent) | Product variant default |

### Wave dispatch semantics

- **Wave A — intake**: usa `templates/feature-intake.template.md`
  (product padrão) com bloco condicional §Extension context renderizado
  quando `extends-feature != null`. Conductor não re-elicita user value /
  business outcome / persona — herda da pai e foca no delta.
- **Wave B — screens + contracts**: focado SÓ no delta. Screens já
  cobertas pela pai são referenciadas como baseline, não re-modeladas.
  Contracts (data-contract-spec, analytics-spec) ganham apenas as
  entries novas; entries herdadas são referenciadas explicitamente.
- **Wave C — tech-spec**: §1-§7 herdadas como referência ("ver
  `parent/tech-spec.md §2 Architecture overview`"); apenas o delta novo
  é renderizado em detalhe. §14 Cross-feature reusability ganha
  evidência forte (extension É um caso de reuso explícito).
- **Wave D — task-breakdown + TASK contracts**: `allowed_files` herda
  baseline da pai (read-only references quando aplicável) + adiciona
  paths novos da extension. Cada task declara explicitamente quais
  arquivos da pai são apenas referenciados (read-only) vs estendidos
  (read+write com cuidado de não regredir behavior da pai).
- **Wave E — readiness**: aceita extension variant com checklist
  focado em "delta coberto" (intake §Extension context completo +
  contracts delta-only + task contracts com baseline herdado declarado).

### Phase 6 retrospective — herança vs adição

5-whys (§8 bugfix) não se aplica em extension — extension não conserta
bug, expande feature done. Retrospective foca em **"o que herdei
literalmente vs o que precisei adicionar"** com 4 perguntas:

1. **Que artefatos da pai foram herdados literalmente?** (contracts,
   screens, helpers, types, naming) — sinal positivo de reuso real.
2. **Que artefatos precisaram de delta mínimo?** (extender contract com
   1 campo, adicionar 1 screen variant) — sinal de extensibility natural.
3. **Que artefatos foram criados do zero apesar de extension?** — sinal
   suspeito; vale interrogar se a pai foi modelada com extensibility
   insuficiente OU se a extension é genuinamente ortogonal.
4. **Que sinais sugerem que parent + extension deveriam ser refatorados
   pra shared base?** — proposed-evolution candidate; quando 2+
   extensions de uma mesma pai compartilham N delta similar, promover a
   base é candidato natural pra L2.

Output esperado: ≥1 proposta concreta pra L2 OU justificativa
explícita de "nada a promover — extension foi delta puro". Diferente de
refactor/bugfix retrospective, extension retrospective também alimenta
`forge graph` Q14/Q15 (near-duplicate detection entre parent + extension).

### Filesystem layout

Extension feature vive em `.claude/memory/L1/{parent-slug}-{descriptive-suffix}/`
— **NÃO** em `non-product/{slug}/` (que é o guarda-chuva de refactor +
bugfix em §8). Razão: extension é product-derived (gera valor de
usuário novo, ainda que correlato), segue o pipeline product. O slug
derivado é convencionalmente `{parent}-{suffix-descritivo}` (ex.:
`lembrete-rega-notificacao`, `weather-integration-fallback`) — conductor
sugere `{parent}-extension` como default na Cena 1, user customiza pra
descritivo real.

`docs/feature-implementation-workflow/features/{parent-slug}-{suffix}/`
paralelo a qualquer outra product feature. Sub-tree de status, history,
dispatch-log, verify-log idêntico ao product padrão.

### Hypothesis schema

`hypothesis.yaml` da extension ganha 2 campos aditivos quando
`extends-feature != null`:

```yaml
extends-feature: lembrete-rega
extension-scope: "Adicionar canal de notificação WhatsApp paralelo ao push existente"
```

`extension-scope` é string curta (1 linha) descrevendo o delta — usada
por `validate_extension_feature.py` pra detecção de dedupe (EXT-004:
múltiplas extensions com mesmo parent + mesmo scope = redundância).

### Cross-link com §8, §9, e Gap 5

- **§8 (subtype non-product)** — extension NÃO é um 6º subtype.
  `_VALID_SUBTYPES` permanece em 5; extension é `product` com parent
  linkado via campo aditivo. Refactor/bugfix de uma extension funcionam
  exatamente como em product standalone (subtype é dimensão ortogonal a
  extends-feature).
- **§9 (external deps)** — extension pode ter dep externa exatamente
  como product standalone. `blocked-on-external` opera ortogonal a
  `extends-feature` (uma extension waiting on backend é válida; o gate
  do `forge implement` segue §9 normal).
- **Gap 5 (card local overlay)** — extensions pra plataforma exótica
  (web, hipotético desktop) seguem o caminho oficial via overlay local
  + extension feature, NÃO via card canon novo. Gap 9 NÃO usa overlay
  no escopo final — extension mechanic é desacoplada de multi-target.

### Cheat-sheet operacional

| Trigger | Ação |
|---|---|
| User pediu pra adicionar X a feature done | Cena 1 oferece 4º caminho "Estender" — slug derivado + `extends-feature: {parent}` no L1 |

### Referenced from

Extension feature — Referenced from:
`docs/schemas/memory.md §status.json extends-feature + parent-feature fields + MEM-L1-008` ·
`engine/memory/l1.py L1State.extends_feature + parent_state + list_extensions_of` ·
`engine/plan.py Cena 1 4º caminho detection + parent context import` ·
`templates/feature-intake.template.md §Extension context conditional block` ·
`docs/ux/forge-plan-roteiro.md §Cena 1 4º caminho Estender` ·
`agents/planning-conductor.md §Phase 1 step 5 extension context import + §Phase 4 wave dispatch (extension variant) + §Phase 6 retrospective (herança vs adição)` ·
`agents/feature-intake-agent.md §Extension context elicitation` ·
`agents/tech-spec-agent.md §context pack extends-feature + parent-baseline references` ·
`agents/retrospective-agent.md §Extension retrospective semantics` ·
`validators/validate_extension_feature.py EXT-001..EXT-004`.

---

## §11 — QA verdict não-bloqueante (since v1.2)

`forge qa` emite verdict BLOCK / FLAG / PASS (rubric em
`docs/superpowers/specs/2026-06-05-forge-qa-design.md §5.4`). **O verdict
não bloqueia retrospective, não bloqueia commit, não bloqueia `forge
implement` advancing.**

Razão: bloquear retrospective com base em verdict de QA agressivo invade
o papel de code review humano (Decisão 5 explícita: code review final é
out-of-scope da forge). Findings são insumo pro user; user decide via
`forge evolve` o que aplicar (Decisão 26 single-by-single).

Esta disciplina alinha:

- **Decisão 5** — out-of-scope code review final.
- **Decisão 26** — single-by-single em evolve (gate humano).
- **§1 (3-caminhos)** — auto-run hook em implement Phase 6 apresenta
  run/skip/disable, não força execução.

Onde o verdict importa:

- Exit code `8` quando BLOCK (distinto de `0` para PASS/FLAG) sinaliza ao
  user/CI o severity — mas não é leitura forçada.
- `forge evolve` consome findings actionable (severity >= medium) via
  proposed-evolutions, **único caminho de ação derivada**.

---

## Cheat-sheet operacional

Quando você (agente, humano, future-self) estiver escrevendo roteiro novo
ou agent-prompt e bater num dos sete pontos:

| Situação | Discipline section |
|---|---|
| "Como apresento essa falha?" | §1 — 3-caminhos |
| "Continuo validando depois do erro?" | §2 — cascade fail-fast |
| "Onde fica o backup desse arquivo?" | §3 — `.bak/` retention |
| "Essa proposta já foi rejeitada?" | §4 — fingerprint algo |
| "Posso aplicar tudo de uma vez?" | §5 — single-by-single |
| "L2 está cheia, e agora?" | §6 — pause + notify |
| "Ctrl+C aqui faz o quê?" | §7 — pause = default, abort = explicit |
| "Esta feature é refactor/spike/chore?" | §8 — non-product feature track |
| "Esperando endpoint do backend — pode rodar a task?" | §9 — external dependencies |
| "User pediu pra adicionar X a feature done?" | §10 — extension feature |
| "`forge qa` cuspiu BLOCK — bloqueia o retrospective?" | §11 — QA verdict não-bloqueante |

Quando o que você quer escrever contradiz alguma disciplina, **pare** e
abra issue. Mentor calmo é firme nas bordas — disciplina universal é
exatamente a borda que protege tudo o mais.
