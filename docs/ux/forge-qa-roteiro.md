# `forge qa` — roteiro end-to-end

The cinematic UX of `forge qa`. Adversarial red-team gate. Rede de
auditores que inventa cenários hostis, executa fixtures sintéticos em
sandbox isolado, e emite findings actionable em proposed-evolutions.
Sibling document a `forge-verify-roteiro.md` e `forge-implement-roteiro.md`
— mesmo estilo, densidade comparável. Mais longo que verify porque há
diálogo de scope-resolution e 6 phases observáveis.

Spec canônico: `docs/superpowers/specs/2026-06-05-forge-qa-design.md`.

## Context

- **Não é read-only.** Escreve em `.planning/qa/<feature-slug>/<run-id>/`
  (artifacts, fixtures, findings) + append em `proposed-evolutions.yaml`.
  Mas **NÃO toca código de produção** — Phase 3 roda validators em
  subprocess sandbox isolado (Decisão 30).
- **Verdict (BLOCK / FLAG / PASS) NÃO bloqueia retrospective, NÃO bloqueia
  commit.** Disciplina §11 alinhada com Decisão 5 (code review final
  out-of-scope).
- **4 attack vectors:** spec-vs-spec · coverage · chaos · validator-claim.
- **Persona stacking:** mentor calmo + overlay "staff QA / red-team lead"
  (cético por default, criativo em hipóteses, estrito em verdict, mentor
  no fraseado — spec §11).
- **Trigger:** manual (`forge qa`) + opt-in auto (hook em
  `forge implement` Phase 6 quando `qa.auto-run-on-feature-done: true`).
- **Total budget:** 2–8min (red-team é caro por design — invenção criativa
  toma tempo). Phase 3 cap default 60s global + 15s per-validator.

---

## Modos de invocação

```text
forge qa                              # sem arg — pergunta scope conversacional
forge qa lembrete-rega                # feature-scope direto (slug)
forge qa .                            # feature corrente (alias)
```

Sem flags (Decisão 10). Scope (`feature` / `screen` / `task` / `paranoid`)
é colhido conversacionalmente, sempre com 3-caminhos quando ambíguo.

---

## Cena 1 — Invocação + scope resolution conversacional (0–8s)

O usuário entra sem arg. O conductor abre o canvas, identifica candidatos
no L1, e pergunta. Mentor calmo + red-team overlay já ativo no fraseado.

```
$ forge qa

   ╭──────────────────────────────────────────╮
   │  feature-forge · qa                      │
   │  Red-team gate. Cético por default.      │
   ╰──────────────────────────────────────────╯

[0:00] Olhando o terreno...
       ├ features ativas                      lembrete-rega · receita-mae
       ├ feature mais recente                 lembrete-rega  (last commit 12m)
       ├ qa runs anteriores                   0 pra lembrete-rega
       └ qa-extensions ativos                 0 cards (canon-only)

[0:02] Em qual escopo eu rodo o ataque?

         1) feature lembrete-rega   — recém-acabou, contexto fresco
            ~3-5min · auditoria full nos 4 attack vectors

         2) feature receita-mae     — done há 3 dias, talvez fixture stale
            ~3-5min · idem

         3) paranoid (cross-feature) — varre TUDO ativo + done últimas 2 semanas
            ~8-12min · útil antes de release

       Sem default. Você escolhe.

> 1

[0:08] OK — feature lembrete-rega, escopo full.
       Run id: 2026-06-05T14-32-08Z-a1b2
       Vou rodar os 4 vectors em paralelo (spec-vs-spec + coverage primeiro,
       chaos + validator-claim depois). Sandbox isolado pra fixtures.
```

**Note:** o 3º caminho (`paranoid`) é o "escalate" do template 3-caminhos
universal (§1 disciplina). Não é flag, é opção de menu. A persona
red-team aparece no "cético por default" do header e em "rodar o ataque"
— linguagem deliberada, sem decoração.

Se houvesse uma única feature ativa, conductor pula o prompt e segue
direto pro Cena 2 (low-friction path). Multi-feature ou nenhum-feature →
diálogo expande.

---

## Cena 2 — Phase 0 cinemático (árvore + scope summary) (8–14s)

Antes de qualquer auditor rodar, o conductor cria a árvore do run e
mostra o que está em mira. Transparência — se algo dá ruim na metade, o
usuário sabe onde inspecionar.

```
[0:08] Phase 0 — Setup
       
       Criando árvore do run:
         .planning/qa/lembrete-rega/2026-06-05T14-32-08Z-a1b2/
           ├ audit/        (findings raw por vector)
           ├ fixtures/     (synthetic — sandbox CWD em Phase 3)
           ├ logs/         (subprocess stdout/stderr)
           └ report.yaml   (final — após Phase 4 synthesis)
       
       Em mira:
         feature        lembrete-rega
         tasks          TASK-0001 .. TASK-0007  (7 tasks, todas applied)
         specs          7 docs (data-contract, analytics, ui-state, ...)
         validators     8 ativos (cascade do workflow.hard-gates)
         qa-extensions  0 (canon-only nesta run)
       
       Budget: 60s global · 15s per-validator (Phase 3 cap)
       Retention: 14 dias (limpa via forge reconfigure → qa)
```

**Note:** snapshot da árvore vai pra `logs/setup.txt` também — auditável.
O "Em mira" é o vector de ataque listado pro red-team: especs que vão ser
contestados, validators que vão ser desafiados. Quando `qa-extensions > 0`,
aparece linha extra com lista de cards + agent overlay herdado.

---

## Cena 3 — Phase 1 static auditors (14s–1min)

Spec-vs-spec + coverage rodam em paralelo (são static — só leem
artefatos). Findings incrementais aparecem em real-time com progress.

```
[0:14] Phase 1 — Static auditors (paralelo)

       ├ spec-vs-spec                         🔍 rodando
       │   Cruzando 7 specs entre si: data-contract × analytics × ui-state...
       │   findings incrementais: 1 · 2 · 3
       │
       └ coverage                             🔍 rodando
           Comparando happy-paths × edge-cases × negative-paths declarados...
           findings incrementais: 2 · 4

[0:48] Phase 1 — done (34s)
       
       spec-vs-spec     · 3 findings (1 high · 2 medium)
       coverage         · 4 findings (1 high · 3 medium)
       
       Mais detalhe no Phase 4 synthesis. Phase 2 começando agora.
```

**Note:** static auditors são determinísticos — não inventam fixtures,
só leem o que já existe. "spec × spec" cruza N×(N-1)/2 pares; "coverage"
cruza tipos de path declarados vs branches que validators conseguem
testar. Findings raw vão em `audit/{vector}.yaml`; síntese pondera
duplicatas no Phase 4.

Mentor calmo na frase "Mais detalhe no Phase 4 synthesis" — sem entupir
o terminal com findings cru, prepara o leitor pro relatório final.

---

## Cena 4 — Phase 2 generative auditors (1min–2min)

Chaos + validator-claim são generative — inventam fixtures hostis. Output
mostra contagem de fixtures + um sample render pra dar concretude ao que
está sendo gerado.

```
[0:48] Phase 2 — Generative auditors (paralelo)

       ├ chaos                                ⚡ gerando fixtures
       │   Vetores: null · empty · race · regressão · traversal · overflow
       │   fixtures gerados: 12 · 18 · 24
       │
       └ validator-claim                      ⚡ gerando fixtures
           Hipótese: "validator X passa fixture que deveria falhar"
           fixtures gerados: 4 · 8

[1:32] Phase 2 — done (44s)
       
       chaos            · 24 fixtures · 6 vetores cobertos
       validator-claim  · 8 fixtures · 4 validators contestados
       
       Sample (chaos-empty-email.yaml):
         vector:      empty
         target:      data-contract-spec
         payload:
           email:     ""          # ← deveria falhar contract
           name:      "Maria"
         expected:    rejection
         claim:       "validate_data_contract.py aceita email vazio"
       
       Próximo: Phase 3 executa todos no sandbox.
```

**Note:** sample render é o "concretude" — o usuário entende QUE TIPO de
ataque está sendo gerado sem precisar abrir 32 arquivos. Persona red-team
no campo `claim`: a hipótese hostil escrita como afirmação testável, não
como pergunta. "validate_data_contract aceita email vazio" é desafio
direto ao trust gate.

Fixtures vivem em `fixtures/chaos-*.yaml` e `fixtures/validator-claim-*.yaml`.
Sandbox CWD do Phase 3 vai ser esse diretório (Decisão 30 — isolation
guarantee).

---

## Cena 5 — Phase 3 sandbox transitivo (2min–3min)

Cada fixture é executado pelo validator alvo em subprocess isolado. CWD =
sandbox dir; writes fora raise `SandboxBreachError`. Output mostra
validator-by-validator com exit code + duration. Render canônico vem na
Cena 6.

```
[1:32] Phase 3 — Sandbox execution (rodando 32 fixtures)
       
       Budget: 60s global · 15s per-validator
       CWD subprocess: .planning/qa/lembrete-rega/.../fixtures/
       
       Streaming validator-by-validator... (render completo abaixo)
```

**Note:** Phase 3 é o coração do trust gate. Validator que **passa**
fixture que **deveria falhar** = critical (validator mentindo invalida
confiança downstream). Validator que **falha** fixture chaos = ok (gate
funcionando). Sandbox breach = critical infrastructural — fixture
malicioso conseguiu escapar do CWD jailing.

Decisão 30 explicitada aqui: o jailing é via `os.chdir` guard injetado
via `PYTHONSTARTUP` preload no subprocess. Validator não tem como
escrever em `engine/` ou `cards/` mesmo se tentar.

---

## Cena 6 — Sandbox loop output (canônico)

Render literal do spec §10.1. Aparece após Phase 3 terminar — não em
streaming linha-a-linha (custo de TTY churn alto pra 30+ validators), mas
em bloco coerente quando o loop fecha.

```
Phase 3 — Sandbox execution (budget: 60s / per-validator: 15s)
────────────────────────────────────────────────────────────────

 fixture                                                    validator                          exit  time
 ──────────────────────────────────────────────────────────────────────────────────────────────────────
 chaos-empty-email.yaml                                     validate_data_contract.py            0   0.14s ⚠
 chaos-rate-flood-analytics.yaml                            validate_analytics_spec.py           1   0.31s ✓
 chaos-payload-malformed-bonsai-form.yaml                   validate_data_contract.py            1   0.22s ✓
 validator-claim-data-contract-empty-email.yaml             validate_data_contract.py            0   0.14s 🛑
 validator-claim-nav-traversal-id.yaml                      validate_navigation_spec.py          1   0.18s ✓
 validator-claim-analytics-missing-required.yaml            validate_analytics_spec.py           0   0.16s 🛑
 chaos-ui-state-regression-success-to-loading.yaml          validate_ui_state_spec.py            1   0.41s ✓
 ...

 8 fixtures executados · 6 ok · 2 validator-mentes · 0 timeout · 0 sandbox-breach
 budget restante: 47.8s / 60s
```

**Note:** os 3 símbolos finais carregam semântica:
- `✓` (exit 1, comportamento esperado) = validator rejeitou fixture
  hostil corretamente. Gate funcionando.
- `⚠` (exit 0, mas era chaos) = validator passou fixture que talvez
  devesse rejeitar. Suspeita, eleva pra revisão na Phase 4.
- `🛑` (exit 0, mas era validator-claim) = validator-mente. Critical
  direto. Trust gate broken.

A linha `budget restante` é load-bearing: se ficar negativa, Phase 3
trunca e marca os fixtures não executados como `not-evaluated` (vão pro
finding `coverage-budget-truncated`, severity medium — pro user saber
que o time orçado não cobriu tudo).

---

## Cena 7 — Verdict block (canônico)

Render literal do spec §10.2. Phase 4 synthesis pondera findings raw,
deduplica via fingerprint (Decisão 25), calcula verdict via rubric (spec
§5.4: critical >= 1 → BLOCK; high >= 3 → BLOCK; senão high >= 1 → FLAG;
senão PASS).

```
═══════════════════════════════════════════════════════════════
  forge qa — verdict
═══════════════════════════════════════════════════════════════

  scope:     feature lembrete-rega
  run:       2026-06-05T14-32-08Z-a1b2
  duration:  3min 14s

  ┌──────────────────────────────────────────────────────────┐
  │                                                          │
  │                     verdict: 🛑 BLOCK                     │
  │                                                          │
  └──────────────────────────────────────────────────────────┘

  findings por severidade:
    critical  · 1   ← validator-claim: data-contract aceita email vazio
    high      · 2   ← spec-vs-spec: 1 · coverage: 1
    medium    · 4
    low       · 3
    info      · 2

  findings por vector:
    spec-vs-spec     ·  3
    coverage         ·  4
    chaos            ·  3
    validator-claim  ·  2

  por que BLOCK:
    · 1 finding critical (regra: critical >= 1 → BLOCK)
    · validator que mente sobre cobertura é trust gate broken — o resto
      da forge confia em validators pra cascade hard-fail; um validator
      mentindo invalida confiança downstream

  Sem auto-fix aqui — escolha humana via forge evolve.
```

**Note:** o verdict box segue padrão visual de `forge verify` Cena 6 — o
usuário reconhece o "veredito cinemático" sem precisar aprender vocab
novo. A diferença carregada: aqui o BLOCK **não bloqueia retrospective**
nem commit (§11 disciplina). Exit code 8 vai pro CI/CD saber o severity,
mas o user é quem decide o próximo passo.

"Sem auto-fix aqui — escolha humana via forge evolve" é o handshake
explícito com Decisão 26 (single-by-single). Não é mensagem genérica; é
ponteiro pro próximo verbo.

A frase "validator que mente sobre cobertura é trust gate broken" mostra
a persona red-team estrita: o severity (critical) está calibrado pelo
**dano** (trust gate quebrado), não pela facilidade de fix (que pode ser
trivial — regex de 5 chars).

---

## Cena 8 — Emit handoff (canônico)

Render literal do spec §10.3. Phase 5 emit grava findings actionable em
`proposed-evolutions.yaml`, silencia duplicatas via fingerprint, e dá
handoff pro user.

```
Phase 5 — Emit
────────────────────────────────────────────────────────────────

 7 findings actionable (severity >= medium) →
   · 5 escritos em proposed-evolutions.yaml
   · 2 silenciados (fingerprint já em rejected-fingerprints — Decisão 25)

 Próximos passos:

   forge evolve            review e apply finding-by-finding (Decisão 26)
   forge qa --help         (não existe — use forge qa pra re-rodar)
   .planning/qa/lembrete-rega/2026-06-05T14-32-08Z-a1b2/
                           inspect raw artifacts (audit, fixtures, findings)

 retention: 14 dias · cleanup via forge reconfigure → menu qa → opção 5

────────────────────────────────────────────────────────────────
 exit code: 8  (BLOCK)
```

**Note:** o handoff é o último ato pedagógico. 4 elementos load-bearing:

1. **Filtro severity >= medium** — info e low não viram proposta (ruído).
   Critical, high, medium viram. Calibração da rubric pra evitar inundar
   `proposed-evolutions.yaml`.
2. **Silenciamento por fingerprint** — Decisão 25 textual. Se finding já
   foi rejeitado antes com mesmo content-hash, não re-aparece. User não
   é assediado pelo mesmo finding em runs sucessivas.
3. **3 próximos-passos** — não 2, não 4 (template universal §1
   3-caminhos): apply via evolve · re-rodar qa · inspect raw. O segundo
   é explicitamente "não tem flag — re-rode o comando" (Decisão 10).
4. **Exit code 8 distinto de 0** — pra CI/CD distinguir PASS/FLAG (exit
   0) de BLOCK (exit 8). User humano não lê exit code; pipeline lê.

A linha "retention: 14 dias" é doctor-friendly — `forge doctor` reporta
qa runs overdue, e o cleanup mora dentro de `forge reconfigure → qa`
(Decisão 24 — `.bak` retention pattern reaplicado).

---

## Edge cases (resumo — detalhe completo no spec §6)

1. **Sandbox breach detectado** — fixture conseguiu escrever fora do CWD.
   Phase 3 aborta IMEDIATAMENTE, marca finding `sandbox-breach` critical,
   verdict force BLOCK. Não tem auto-recovery — bug infraestrutural exige
   investigação humana.
2. **Budget esgotado mid-Phase-3** — fixtures não executados marcados
   `not-evaluated`, gera finding `coverage-budget-truncated` (medium).
   User decide: aumenta budget em workflow-config ou aceita partial.
3. **`qa-extensions` colide com canon** — hard-fail no Phase 0 antes de
   gastar budget. Mensagem 3-caminhos: rename extension · disable
   extension · revisitar capability label.
4. **Feature sem L1 (nunca rodou implement)** — `forge qa` recusa com
   "feature ainda não tem fixtures naturais — rode `forge plan` +
   `forge implement` primeiro".
5. **Nenhuma feature ativa nem done recente** — mensagem clara: "Sem
   feature pra atacar. `forge plan` cria uma; volte aqui depois."

---

## Cross-refs

- **Decisão 9 (revisita 2026-06-05)** — `forge qa` como 13º subcomando.
  Veja `docs/design/01-decisions.md` linha 29.
- **Decisão 30** — sandbox isolation Phase 3. Linha 30 do mesmo doc.
- **Disciplina §11** — verdict não-bloqueante.
  `docs/design/07-discipline.md §11`.
- **Spec completo** — `docs/superpowers/specs/2026-06-05-forge-qa-design.md`.
- **Sibling roteiros** — `forge-verify-roteiro.md` (cascade
  determinístico) e `forge-evolve-roteiro.md` (consumo dos findings).

Mentor calmo é firme nas bordas — `forge qa` é o ataque ritualizado, mas
ele entrega findings ao **gate humano** (evolve). A forge nunca aplica
sozinha o que red-team encontrou. Esse é o contrato.
