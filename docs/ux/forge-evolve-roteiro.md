# `forge evolve` — roteiro end-to-end

The cinematic UX of `forge evolve`. The **self-evolution gate**: the engine
proposes, the user decides. Every L2 promotion, template patch, agent reminder,
or new card suggestion flows through this command. Mentor calmo presents
trade-offs without judgment. Rejection is a permanent answer when the user
wants it to be.

## Context

- Reads `.claude/proposed-evolutions.yaml` (queue written by retrospective-agent
  after each `feature-done`)
- Writes approved changes into `.claude/memory/L2-project.yaml`, templates
  under `.claude/cards/<name>/`, agent prompts, etc.
- Logs every decision (apply/reject/defer) to `.claude/memory/history.jsonl`
- Logs permanent rejections to `.claude/rejected-evolutions.yaml` so the engine
  never re-proposes the same idea
- Respects the **active feature lock** (same rule as `forge reconfigure`)

---

## Cena 1 — Entrada (0.0–1.5s)

```
$ forge evolve

   ╭──────────────────────────────────────────╮
   │  feature-forge · evolve                  │
   │  Self-evolution gate.                    │
   ╰──────────────────────────────────────────╯

Vou te mostrar o que aprendi desde a última rodada.
Você decide o que vira regra, o que fica pra próxima,
e o que nunca mais quero te propor.
```

**Note:** opening line names the philosophy in one breath — the engine learns,
the user decides. No emojis on entry. Calm.

---

## Cena 2 — Pre-flight (1.5–2.5s)

```
[0:01] Checando estado...
       ├ proposed-evolutions.yaml             ✓ found
       ├ active feature lock                  ✓ none active
       ├ rejected-evolutions.yaml             ✓ found (12 entries skipped)
       └ L2 size                              0.31 MB (under 0.5 MB limit)
```

**Note:** if an L1 with `state ∈ {planning, implementing, verifying}` is
detected, evolve refuses with the canonical lock message (see schemas/memory.md
§ "L1 as a lock mechanism"). Same words, same tone — consistency matters.

If `proposed-evolutions.yaml` is missing or empty, jump to **Variação A — Empty
queue** below.

---

## Cena 3 — Overview da fila (2.5–4s)

The skill **shows the whole queue first** before going proposal-by-proposal.
This gives the user a sense of scope before committing to the loop.

```
[0:03] 🧠 Propostas pendentes (7)

       ╭──────┬────────────────────────────────┬────────┬───────┬──────────╮
       │  ID  │ Tipo                           │ Conf.  │ Trig. │ Origem   │
       ├──────┼────────────────────────────────┼────────┼───────┼──────────┤
       │ P-001│ L1 → L2 promotion              │ 0.95   │  4    │ retro    │
       │ P-002│ template patch (tech-spec)     │ 0.88   │  3    │ retro    │
       │ P-003│ L1 → L2 promotion              │ 0.92   │  4    │ retro    │
       │ P-004│ new card suggestion            │ 0.71   │  3    │ retro    │
       │ P-005│ question elimination           │ 0.83   │  5    │ retro    │
       │ P-006│ agent prompt addition          │ 0.66   │  2    │ retro    │
       │ P-007│ convention refinement          │ 0.74   │  3    │ retro    │
       ╰──────┴────────────────────────────────┴────────┴───────┴──────────╯

       Última feature que alimentou a fila: lembrete-rega (2026-05-27)
       
       Vou abrir uma por uma. Em cada uma você decide:
         Aplicar · Rejeitar · Adiar · Editar-e-aplicar
       
       Pronto pra começar?  [enter pra seguir]
```

**Note:** `Trig.` = how many features triggered the proposal (provenance count).
Above 3 is the natural "pattern threshold" mentioned in memory schema. The user
sees confidence and provenance side-by-side — mentor calmo never hides numbers.

---

## Cena 4 — Proposta cinematográfica (4s–...)

Each proposal is revealed step by step. No bulk dump. The reveal IS the
mentorship.

### P-001 — L1 → L2 promotion (high confidence)

```
[0:05] ─── P-001 ─── L1 → L2 promotion ────────────────────────────────────

       💡 Padrão detectado
       
          "outbox queue for offline-write features"
       
       🧠 Evidência
       
          Features que usam:
            ●  bonsai-form        (2026-04-22)
            ●  register           (2026-05-10)
            ●  lembrete-rega      (2026-05-27)
            ●  water-tracker      (2026-05-15)
          
          Confidence: 0.95
          Provenance: 4 features (limiar de promoção: 3)

       📄 Diff proposto — .claude/memory/L2-project.yaml
       
          patterns:
       +    - id: P-007
       +      name: "outbox queue for offline-write features"
       +      detected-in: [bonsai-form, register, lembrete-rega, water-tracker]
       +      description: |
       +        Features que permitem criação offline usam outbox queue com
       +        retry, não optimistic-with-rollback. Conflito resolvido com
       +        last-write-wins (ver DF-003).
       +      confidence: 0.95
       +      promoted-to-rule: false

       ✨ Impacto
       
          ├ planning-conductor passa a ler este padrão como L2 default
          ├ próximas features com `persistence: firestore` + offline write
          │   recebem hipótese pré-formada (sem perguntar)
          └ economiza ≈ 1 rodada de elicitation por feature similar
       
       O que fazer com P-001?
       
         a) Aplicar
         b) Rejeitar
         c) Adiar
         d) Editar antes de aplicar
       
       > _
```

**Note:** four blocks — pattern, evidence, diff, impact — each earning the
next. User can stop reading at any block and still decide soundly.

---

## Cena 5 — Aplicação (sob "a) Aplicar")

```
[0:08] ⚡ Aplicando P-001
       ├ backup .claude/memory/L2-project.yaml → .L2-project.yaml.bak
       ├ inserindo pattern P-007                              ✓
       ├ rebuild de índices de leitura do conductor           ✓
       ├ history.jsonl                                        +1 evento
       └ removendo P-001 da fila proposed-evolutions.yaml     ✓
       
       ✓ Aplicado. Próximas features já se beneficiam.
```

**Note:** every apply is a transaction: backup → mutate → verify → drop from
queue. If any step fails, the next cena fires.

### Variação — Apply fails (file conflict)

```
[0:08] ⚡ Aplicando P-001
       ├ backup .claude/memory/L2-project.yaml                ✓
       ├ inserindo pattern P-007                              ⚠ conflict
       │   reason: pattern id P-007 já existe (diferente conteúdo)
       └ rollback                                             ✓
       
       🛑 Não consegui aplicar P-001 com segurança.
       
          Conflito: já existe um P-007 em L2 com conteúdo diferente.
          Provavelmente uma rodada anterior aplicou parte da mudança.
       
       Posso:
         a) Re-numerar a proposta como P-008 e aplicar
         b) Mostrar o diff dos dois P-007 lado a lado
         c) Adiar essa proposta pra você inspecionar manualmente
       
       > _
```

**Note:** rollback is non-optional. Partial apply corrupts L2 reads silently —
worse than no apply.

---

## Cena 6 — Rejeição (sob "b) Rejeitar")

```
[0:09] ─── P-001 ─── rejeitar ────────────────────────────────────────────

       Antes de marcar, preciso saber:
       
         a) Rejeitar permanente — nunca mais propor isso
         b) Rejeitar só esta rodada — talvez na próxima eu reconsidere
         c) Voltar atrás (deixar pra decidir agora)
       
       > a
       
[0:10] Marcando P-001 como rejeitada permanente.
       ├ adicionando entrada em .claude/rejected-evolutions.yaml      ✓
       │   id: P-001
       │   rejected-at: 2026-05-28T16:42:00Z
       │   reason: "user permanent rejection"
       │   pattern-fingerprint: sha256(name + description)
       ├ removendo P-001 da fila proposed-evolutions.yaml             ✓
       └ history.jsonl                                                +1 evento
       
       ✓ Não vou propor isso de novo. Mesmo que apareça em mais features,
         o engine vai pular essa sugestão.
```

**Note:** the fingerprint (sha256 of name + description) is what blocks future
re-proposal — not the ID, since retrospective-agent re-IDs proposals each run.
Mentor calmo: rejection is a real, durable choice, not a temporary mute.

---

## Cena 7 — Adiamento (sob "c) Adiar")

```
[0:11] Adiando P-001.
       ├ proposed-evolutions.yaml — entrada mantida           ✓
       └ history.jsonl                                        +1 evento
       
       ✓ Próximo `forge evolve` vai te perguntar de novo.
         Se quiser revisar antes, abre .claude/proposed-evolutions.yaml.
```

**Note:** defer is the soft option. No fingerprint, no log of rejection — only
a "seen, not decided" marker.

---

## Cena 8 — Editar-e-aplicar (sob "d) Editar antes de aplicar")

```
[0:11] ─── P-001 ─── editar antes de aplicar ──────────────────────────────

       Vou abrir a proposta no seu editor ($EDITOR=nvim).
       Edite o YAML e salve. Volto aqui pra mostrar o diff final.
       
       ⠋ esperando você fechar o editor...
       
       ✓ editor fechado.
       
       📄 Diff entre o original e a sua versão
       
          patterns:
              - id: P-007
                name: "outbox queue for offline-write features"
                detected-in: [bonsai-form, register, lembrete-rega, water-tracker]
                description: |
       -          Features que permitem criação offline usam outbox queue com
       -          retry, não optimistic-with-rollback.
       +          Features que permitem criação offline usam outbox queue
       +          (capacity 64, retry exponencial 1s/2s/4s) com last-write-wins
       +          na resolução. NUNCA optimistic-with-rollback neste projeto.
                confidence: 0.95
       +        promoted-to-rule: true
       
       Confirma? Aplico a versão editada.
       
         a) Aplicar a versão editada
         b) Voltar pra proposta original
         c) Cancelar e adiar
       
       > _
```

### Variação — Editor não disponível

```
[0:11] $EDITOR não está setado.
       Posso te mostrar a proposta inline pra você ditar mudanças,
       ou adiar.
       
         a) Editar inline (linha-a-linha, eu pergunto cada campo)
         b) Adiar
       
       > _
```

**Note:** inline edit is the fallback. Verbose but never blocks.

---

## Cena 9 — Próxima proposta no loop

After each decision, fade-out + reveal next:

```
       ─────────────────────────────────────────────────────────────────────
       
[0:13] Próxima proposta: P-002  (template patch · confidence 0.88)
       
       ...
```

### P-002 — Template patch (cinematic)

```
[0:13] ─── P-002 ─── template patch ──────────────────────────────────────

       💡 Patch proposto
       
          Template alvo: cards/firebase-firestore/templates/firestore-tech-spec.md
          Seção alvo:    "Backend Permissions"
          Modo:          append-section
       
       🧠 Por que
       
          Em 3 features (auth, register, bonsai-form) o agente tech-spec
          teve que perguntar de novo sobre regras de Firestore porque o
          template não cobria "permissions" explicitamente.
       
       📄 Diff proposto
       
          + ### Backend Permissions
          +
          + - Quem pode ler:   <user-id matches> | <claim required> | <public>
          + - Quem pode criar: <self-only> | <admin-only> | <anyone-authed>
          + - Quem pode editar: <owner-only> | <admin-only>
          + - Quem pode deletar: <owner-only> | <admin-only> | <soft-delete>
          + - Rule file:        firestore.rules § <path>
          + - Test coverage:    rules-unit-test § <test-id>
       
       ✨ Impacto
       
          ├ próxima feature com firestore recebe a seção pronta
          ├ tech-spec-agent passa a coletar essas respostas no questionário
          └ não invalida tech-specs já escritos (não regrava retroativamente)
       
       O que fazer com P-002?
       
         a) Aplicar    b) Rejeitar    c) Adiar    d) Editar
       
       > _
```

**Note:** template patches are reversible — the snapshot in `.claude/cards/`
gets a `.bak` before mutation. Old feature packages are untouched (per
schemas/card.md § "Card was removed, contribution lingers").

---

## Cena 10 — Variação: nova proposta de card (P-004)

```
[0:18] ─── P-004 ─── new card suggestion ─────────────────────────────────

       💡 Capability candidata a cardificação
       
          Nome proposto:  push-deep-link-routing
          Provides:       deep-link, push-routing
          Requires:       nav3 (Android) | swiftui-navigation (iOS)
       
       🧠 Por que
       
          Em 3 features (lembrete-rega, register, bonsai-form) o time
          implementou deep link de push notification de forma muito
          parecida, sempre adicionando boilerplate em 2 lugares
          (AndroidManifest + AppDelegate).
       
       📄 Estrutura proposta
       
          cards/push-deep-link-routing/
            card.yaml                 (manifest)
            README.md                 (a ser preenchido)
            templates/
              tech-spec-section.md    (esqueleto)
            agent-contributions/
              tech-spec-additions.md  (esqueleto)
            detection/
              signals.yaml            (heurísticas iniciais)
       
       ⚠ Card novo é compromisso de manutenção.
       
          Sugiro: ao invés de criar o card inteiro agora, posso só
          *registrar a intenção* em L2 como promotion-candidate. Quando
          aparecer numa 4ª feature, eu reabro essa proposta com mais
          evidência.
       
       O que fazer com P-004?
       
         a) Criar o card agora (recomendado se você tem tempo de manter)
         b) Registrar como promotion-candidate (mais conservador)
         c) Rejeitar
         d) Adiar
       
       > _
```

**Note:** mentor calmo on card creation — refuses to lean into the user. New
cards = new maintenance surface. Option (b) is the safer default and the skill
says so.

---

## Cena 11 — Variação: question elimination (P-005)

```
[0:22] ─── P-005 ─── question elimination ────────────────────────────────

       💡 Pergunta candidata a virar default
       
          Pergunta:       "Em que ambiente Firebase você desenvolve?"
          Onde aparece:   forge plan (round 1 elicitation)
          Resposta dada:  bonsai-meo-dev  (5/5 features)

       🧠 Provenance
       
          ●  auth                bonsai-meo-dev
          ●  bonsai-form         bonsai-meo-dev
          ●  register            bonsai-meo-dev
          ●  lembrete-rega       bonsai-meo-dev
          ●  water-tracker       bonsai-meo-dev
       
       📄 Mudança proposta
       
          .claude/memory/L2-project.yaml:
            decisions-frozen:
       +      - id: DF-004
       +        decision: "Firebase dev project: bonsai-meo-dev"
       +        locked-since: 2026-05-28
       +        by: question-elimination-via-evolve
       
          .claude/workflow-config.yaml:
            elicitation.skip-questions:
       +      - id: Q-firebase-env
       +        because: DF-004
       
       ✨ Impacto
       
          A próxima feature não vai mais te perguntar Q-firebase-env.
          Se um dia mudar o ambiente, basta rodar `forge reconfigure`.
       
       O que fazer com P-005?
       
         a) Aplicar    b) Rejeitar    c) Adiar    d) Editar
       
       > _
```

**Note:** question elimination is reversible by design — frozen decisions can
be unfrozen via `forge reconfigure`. The skill says this aloud so the user
doesn't feel locked in.

---

## Cena 12 — Variação: conflicting proposals

When two proposals propose contrary changes, the skill **bundles them** before
asking — never applies one and then the other in silence.

```
[0:26] ⚠ Conflito detectado entre P-006 e P-007
       
       Ambas tocam o mesmo arquivo de prompts do tech-spec-agent.
       
       ┌─ P-006 (confidence 0.66) ────────────────────────────────────────┐
       │ "Sempre verificar se AppRoute já existe antes de criar nova rota"│
       │                                                                  │
       │ extension-point: section:Navigation Strategy                     │
       │ proposed text: 6 linhas                                          │
       └──────────────────────────────────────────────────────────────────┘
       
       ┌─ P-007 (confidence 0.74) ────────────────────────────────────────┐
       │ "Centralizar definição de AppRoute em shared:core/navigation/"   │
       │                                                                  │
       │ extension-point: section:Navigation Strategy                     │
       │ proposed text: 4 linhas                                          │
       └──────────────────────────────────────────────────────────────────┘
       
       Posso:
         a) Mesclar as duas em uma só (eu proponho o texto, você revisa)
         b) Aplicar só P-007 (maior confidence, escopo mais amplo)
         c) Aplicar só P-006
         d) Rejeitar ambas
         e) Adiar ambas
       
       > _
```

**Note:** mentor calmo on conflict — names the trade-off (confidence vs scope),
suggests the merge, never picks for the user.

---

## Cena 13 — Variação: proposta stale (arquivo sumiu)

```
[0:28] ⚠ P-008 referencia um arquivo que não existe mais.
       
          Target: cards/firebase-storage/templates/storage-tech-spec.md
          Status: arquivo não encontrado
          
          Provável causa: card foi removido via `forge reconfigure` (menu
          cards → "remover card") depois que esta proposta foi enfileirada.
       
       Vou marcar P-008 como auto-rejeitada (stale) e seguir.
       Você pode revisar depois em rejected-evolutions.yaml.
       
       ✓ P-008 movida para rejected-evolutions.yaml com motivo "stale".
```

**Note:** auto-reject is the only place evolve decides without user input —
because there's literally nothing to apply. Logged with a distinct reason
("stale") so the user can audit.

---

## Cena 14 — Sumário final (após todas as propostas)

```
[0:32] ✨ Rodada concluída
       
       ╭───────────────────────── evolve · sumário ──────────────────────────╮
       │                                                                     │
       │   ✓ Aplicadas             3                                         │
       │       P-001  L1 → L2 promotion                                      │
       │       P-002  template patch (tech-spec)                             │
       │       P-005  question elimination                                   │
       │                                                                     │
       │   ✗ Rejeitadas            2                                         │
       │       P-004  new card suggestion           (permanente)             │
       │       P-008  template patch                (auto: stale)            │
       │                                                                     │
       │   ⏸ Adiadas               1                                         │
       │       P-006  agent prompt addition                                  │
       │                                                                     │
       │   ✱ Mescladas             1                                         │
       │       P-003 + P-007  agent prompt addition (Navigation Strategy)    │
       │                                                                     │
       ╰─────────────────────────────────────────────────────────────────────╯
       
       Estado pós-rodada:
         L2 patterns:           +1 (total 8)
         L2 decisions-frozen:   +1 (total 4)
         Templates patcheados:  1
         Cards novos:           0
         Skip-questions:        +1 (total 3)
       
       💡 Sugestão:
          rode `forge plan <slug>` pra usar as novidades —
          a próxima feature já vai sentir.
       
       Pronto.
```

**Note:** the summary mirrors the overview from Cena 3, closing the loop. The
"💡 Sugestão" line is intentional — mentor calmo nudges forward without
demanding.

---

## Variação A — Empty queue

```
[0:02] 🧠 Nada pra evoluir agora.
       
       Última retrospectiva:  2026-05-22 (feature `lembrete-rega`)
       Tempo desde:           6 dias
       Próxima alimentação:   quando a próxima feature completar
       
       Se você esperava ver propostas e a fila está vazia, pode ser que:
         ├ a retrospectiva ainda não rodou nessa feature
         │   (verifica `.claude/memory/L1/<slug>/status.json` — state == done?)
         ├ a retrospectiva rodou mas não detectou nada acima de
         │   confidence 0.5 (limiar mínimo pra enfileirar)
         └ um `forge undo` apagou propostas recentes
       
       💡 Pra forçar uma retrospectiva manual:
          (não recomendado — retro automática é mais limpa)
          edita `.claude/memory/L1/<slug>/status.json` se necessário.
       
       Sem nada pra fazer aqui. Volto depois.
```

**Note:** mentor calmo on emptiness — explains why, gives audit pointers, never
fabricates work.

---

## Variação B — High-confidence stack (tudo > 0.9)

After Cena 3, before Cena 4:

```
[0:04] 🧠 Todas as 7 propostas estão acima de 0.9 de confidence.
       
       Tem evidência forte em todas. Posso te perguntar uma por uma
       como sempre, ou aplicar em lote e te mostrar o sumário.
       
         a) Uma por uma (recomendado se você quer revisar)
         b) Aplicar em lote (recomendado se você confia na detecção)
         c) Aplicar em lote SÓ as que não envolvem novos cards
            (mais conservador)
       
       > _
```

**Note:** batch apply only offered when ALL proposals exceed the high
threshold. Mentor calmo names the trade-off — confidence is not certainty.

---

## Variação C — Low-confidence stack (tudo < 0.7)

```
[0:04] 🧠 Todas as 7 propostas estão abaixo de 0.7 de confidence.
       
       A evidência ainda é fraca. Recomendo:
       
         ├ revisar uma por uma (mas adiar quando tiver dúvida)
         └ deixar mais 1-2 features rodarem antes da próxima evolve;
           o engine vai consolidar provenance e a confidence sobe sozinha
       
       Quer abrir mesmo assim?
       
         a) Sim, vou revisar uma por uma
         b) Adiar tudo (mantém a fila)
         c) Sair sem mexer
       
       > _
```

**Note:** mentor calmo says "no" — or rather, suggests no. The user can still
push through, but the skill is honest about the signal.

---

## Edge cases que o roteiro precisa cobrir

| # | Cenário | Comportamento |
|---|---|---|
| 1 | Active feature lock | Recusa com mensagem canônica de `memory.md` § lock |
| 2 | Apply falha mid-flight | Rollback + opções de re-tentar (Cena 5 variação) |
| 3 | User rejeitou antes, proposta similar reaparece | Engine checa `rejected-evolutions.yaml` por fingerprint e SKIPPA antes da Cena 3 |
| 4 | `$EDITOR` não setado | Fallback inline (Cena 8 variação) |
| 5 | Empty queue mas user esperava itens | Variação A explica por que e como auditar |
| 6 | Proposta stale (arquivo sumiu) | Auto-reject com reason "stale" (Cena 13) |
| 7 | L2 ultrapassa max-size-mb durante apply | Pausa o apply, sugere `memory-distiller` antes de seguir |
| 8 | Duas propostas conflitantes | Cena 12 bundle + merge/pick |
| 9 | User Ctrl+C no meio do loop | Estado da fila preservado; já-aplicadas ficam aplicadas; não-aplicadas permanecem como pendentes |
| 10 | rejected-evolutions.yaml corrompido | evolve avisa, oferece backup vazio, segue (não bloqueia) |

---

## Design points que este roteiro cristaliza

| Decisão implícita | Implicação prática |
|---|---|
| Overview antes do loop | Usuário sabe o escopo antes de entrar no fluxo |
| Cada proposta tem 4 blocos | Padrão, evidência, diff, impacto — sempre nessa ordem |
| Apply é transacional | Backup → mutate → verify → drop, com rollback |
| Reject tem 3 graus | Permanente · só esta rodada · cancelar |
| Permanent reject usa fingerprint | Bloqueia re-proposta mesmo com ID novo |
| Edit-then-apply abre `$EDITOR` | Com fallback inline; nunca bloqueia |
| Sumário final espelha overview | Loop fechado, sensação de "rodada completa" |
| Mentor calmo nunca decide | Mesmo em high-confidence stack, oferece opção manual |
| Auto-reject só pra stale | Único lugar onde o engine decide sem perguntar |
| Tom: didático sem moralizar | Apresenta trade-off, não pune escolha |

---

## Total de tempo

Rodada média (5-8 propostas): 30s a 3min, dominada pelo tempo de leitura
humana. I/O do engine (backup, apply, log) é sub-segundo cada.

## Próximos passos depois desta rodada

```
forge plan <slug>          começar feature nova usando as novidades
forge memory L2            inspecionar L2 pós-evolve
forge undo                 desfazer a última proposta aplicada
```
