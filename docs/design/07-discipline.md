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
└ check_files_in_allowed_files.py        — não rodado (cascade parou)
```

### Exemplo de cascade com fail-fast=false

```
├ validate_feature_package.py            ✓ 124ms
├ validate_readiness.py                  🛑 218ms  FAIL (1)
├ validate_task_contract.py              ✓ 156ms
├ validate_data_contract.py              🛑 312ms  FAIL (2)
├ validate_screen_analysis.py            ✓ 245ms
├ validate_backend_e2e.py                ⚠ 482ms  (3 warnings)
├ check_no_invented_behavior.py          🛑 1.4s   FAIL (3)
└ check_files_in_allowed_files.py        ✓ 89ms

3 hard fails coletados — apresentando em ordem de aparição.
Resolva e re-rode.
```

Cada hard fail vira um bloco 3-caminhos separado. Warnings agrupam no fim.

### Referenced from

Validator cascade — Referenced from:
`docs/ux/forge-verify-roteiro.md` §Design points ("Cascade para no primeiro
fail") · `docs/ux/forge-doctor-roteiro.md` (mesma semântica de cascade) ·
`docs/schemas/workflow-config.md` §validators.fail-fast ·
`.claude/hooks/post-subagent-validate.sh` (cascade local em hook).

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
`docs/schemas/workflow-config.md` §cleanup.bak-retention-days ·
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
`docs/schemas/memory.md` §max-size-mb · `docs/schemas/workflow-config.md`
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
not-started → planning → planned → implementing → verified → done
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

## Cheat-sheet operacional

Quando você (agente, humano, future-self) estiver escrevendo roteiro novo
ou agent-prompt e bater num dos seis pontos:

| Situação | Discipline section |
|---|---|
| "Como apresento essa falha?" | §1 — 3-caminhos |
| "Continuo validando depois do erro?" | §2 — cascade fail-fast |
| "Onde fica o backup desse arquivo?" | §3 — `.bak/` retention |
| "Essa proposta já foi rejeitada?" | §4 — fingerprint algo |
| "Posso aplicar tudo de uma vez?" | §5 — single-by-single |
| "L2 está cheia, e agora?" | §6 — pause + notify |
| "Ctrl+C aqui faz o quê?" | §7 — pause = default, abort = explicit |

Quando o que você quer escrever contradiz alguma disciplina, **pare** e
abra issue. Mentor calmo é firme nas bordas — disciplina universal é
exatamente a borda que protege tudo o mais.
