---
# Front-matter canônico — preenchido pelo feature-intake-agent.
# Slug do feature (kebab-case). Resolvido pelo planning-conductor antes do dispatch.
feature-slug: "{{feature_slug}}"
# Identidade do agent autor.
generated-by: "feature-intake-agent"
# ISO-8601 UTC timestamp do momento da escrita.
generated-at: "{{generated_at_iso8601}}"
# Versão do schema do template; bump quando estrutura mudar.
schema-version: 1
# Subtype canônico — fixo em "bugfix" para esta variante.
# Ver docs/design/07-discipline.md §8 (Non-product feature track).
subtype: "bugfix"
# Origem do material que alimentou o intake.
# Valores aceitos: ticket | text | screenshot | mixed
source-type: "{{source_type}}"
# Referência verificável da origem (link do ticket, hash do screenshot, etc.).
# Use "none" quando não houver.
source-ref: "{{source_ref_or_none}}"
# Resultado da Wave B sub-question (Gap 1, Cena 2.5).
# true  → bug toca UI/comportamento observável → Wave B roda
# false → bug é logic-only (data/lógica/concorrência) → Wave B skipada
wave_b_required: "{{wave_b_required_bool}}"
---

<!--
  feature-intake.md — Wave A (bugfix variant) · feature-intake-agent
  --------------------------------------------------------------------
  Documento curto (1 página) que abre o pacote de BUGFIX.
  Discipline §8 — restaurar comportamento correto. Bug com repro
  conhecido, root-cause analisável, fix-shaped (atomic commit).

  Voz: mentor-calmo. Frases curtas. Sem marketing.
  Idioma: PT-BR se a fonte estiver em PT-BR; senão EN.

  Drop intencional vs variante de produto:
    - "What this feature delivers" (assume user value novo) → substituído
      por "Problem statement" (descreve o bug)
    - "Why now" (motivação de produto) → cabe em §Problem statement
    - "Scope OUT" (feature pequena) → bugfix tem escopo = o próprio bug
    - "Scope IN" como deliverables → substituído por §Fix scope

  Regra absoluta: campo ausente → null OU open question; nunca inventar.
  Mais regra absoluta: §Reproduction steps é MANDATORY. Sem repro o bug
  não é planável — conductor drilla até concretizar OU rotea como
  open-question bloqueante.

  Se durante o intake o agente perceber que o bug é de feature-shape
  (vai exigir N tasks de comportamento novo), ele PARA e levanta no
  conductor — a feature deveria virar subtype=product.
-->

# Bugfix — {{human_readable_feature_name}}

<!--
  Cabeçalho com slug · ticket · owner · platforms · severity · subtype literal.
-->
> slug: {{feature_slug}} · ticket: {{ticket_id_or_none}} · owner: {{owner_or_null}} · platforms: {{active_platforms_comma_separated}} · severity: {{severity_p0_p1_p2_p3}} · subtype: bugfix

## Source of truth

<!--
  Cite a fonte exatamente como ela existe nos inputs. Nunca fabricar.
  - ticket: link literal ou "none" (alta-confiança bugfix tem ticket)
  - description origin: ticket | user-paste | user-elicitation
  - Screenshots existem quando bug é visual; quando logic-only, pode
    ser 0 — captura é evidência, não input pra vision analysis.
-->
- ticket: {{ticket_link_or_none}}
- screenshots: {{screenshots_count}} file(s) — {{screenshots_relative_paths_csv_or_none}}
- description origin: {{description_origin}}
- affected versions: {{affected_versions_csv_or_unknown}}
- related commits: {{related_commits_csv_or_none}}

<!--
  MEM-CONTEXT (W-ROUTE 6c) — gotchas/convenções relevantes do acervo de memória
  (`mem find`), injetadas pelo engine ANTES do dispatch. Quando vazio (mem
  indisponível ou sem hits), a linha abaixo fica em branco — sem ruído. NÃO é
  fonte da verdade; é dica de contexto pro autor consultar.
-->
{{mem_context_hint}}

## Problem statement

<!--
  Um parágrafo descrevendo o bug. Exemplos:
    - "Validador de nome de bonsai aceita strings só de espaço como vazio
      válido — usuário consegue criar bonsai com nome ' '."
    - "Quando user clica em 'Salvar' sem nome, app crasha com NPE em
      BonsaiFormViewModel.save() — falta null check no campo name."
    - "Push notification de lembrete dispara duas vezes em iOS 17.4+
      porque o registro do UNUserNotificationCenter é feito 2x quando
      app é foregrounded após force-quit."

  Sem termos vagos ("não funciona direito"). Sem promessas de fix
  ("vamos corrigir"). Apenas o bug, descrito objetivamente.
-->
{{bug_description_paragraph}}

## Reproduction steps

<!--
  Lista NUMERADA de steps que levam ao bug. MANDATORY — sem repro, o
  bug não é planável (discipline §8). Cada step deve ser executável
  por outra pessoa sem ambiguidade.

  Bom exemplo:
    1. Abra o app, faça login com usuário test@test.com
    2. Toque no FAB de criar bonsai
    3. Deixe o campo "Nome" vazio
    4. Toque em "Salvar"
    5. Observe: app crasha (esperado: snackbar de validação)

  Mau exemplo:
    - "user tenta criar bonsai e dá erro"
    - "às vezes acontece"

  Se "às vezes acontece" for genuíno (race, flake, ambiente-específico),
  descreva as condições conhecidas que aumentam a frequência:
    "Repro frequência ~20%. Aumenta para 90% quando: rede 3G ou pior,
     app foregrounded por <2min, último insert foi <500ms atrás."
-->
1. {{step_1}}
2. {{step_2}}
3. {{step_3}}
{{...}}

## Expected vs actual behavior

<!--
  Dois sub-blocos lado-a-lado. Cada um é uma única frase declarativa.
  Sem rationale, sem speculation — só observação.

  Expected: o que deveria acontecer (vindo do AC do ticket, ou da
  documentação do produto, ou do common sense da feature).
  Actual: o que acontece de fato hoje (observado durante repro).
-->

**Expected:** {{expected_behavior_sentence}}

**Actual:** {{actual_behavior_sentence}}

## Root-cause hypothesis

<!--
  Um parágrafo curto: por que o bug existe?
  Inclui um campo `confidence` (0-1) — quão certo está o agent.

  Exemplos:
    - confidence: 0.9 — "BonsaiFormErrorCode enum não inclui caso
      FIELD_WHITESPACE_ONLY; validator aceita silentemente."
    - confidence: 0.65 — "Provável race entre observerOf(...).flow e
      ViewModel state restoration durante config change — mas preciso
      validar com log dirigido."
    - confidence: 0.0 — "Root cause unknown — registered as Q-NNN.
      Bug é planável pq repro é estável; investigação faz parte do
      implement."

  Confidence < 0.5 NÃO bloqueia bugfix planning (diferente de
  reproduction-known, que bloqueia). Mas trigga conductor a marcar a
  task com `validations: [investigate_root_cause_first]`.

  Se durante o implement o root-cause real for descoberto e diferente
  do hipotético, retrospective-agent captura — 5-whys precisa do
  causa REAL, não do palpite inicial.
-->
- confidence: {{root_cause_confidence_0_to_1}}
- hypothesis: {{root_cause_hypothesis_paragraph}}

## Fix scope

<!--
  Lista CONCRETA de paths que provavelmente serão tocados. Cada path
  com o tipo de mudança esperada. Estimativa, não garantia — Wave C
  pode refinar.

  Tipos canônicos:
    - update:    arquivo terá conteúdo editado (mais comum em bugfix)
    - create:    novo arquivo introduzido (raro; só pra extrair fix
                 helper)
    - delete:    arquivo removido (raríssimo em bugfix)
    - add-test:  arquivo de teste novo pra regression test (ver
                 §Validation strategy)

  Granularidade: arquivos individuais quando possível. Quando o fix
  é "trocar nome de função em N call sites", listar:
    "{N} call sites em feature/bonsai/{...}/ (update)"

  Restrição: bugfix PODE adicionar test files (diferente de refactor).
  Listar add-test entries aqui é normal e esperado — a regression
  test prova que o bug existia + foi corrigido.
-->
- {{file_or_group_1}} ({{update_create_delete_add_test}})
- {{file_or_group_2}} ({{update_create_delete_add_test}})

## Regression risk

<!--
  Avaliação de risco que o fix introduza regressão em outro fluxo.
  Estrutura: severity + bullets concretos do que pode quebrar.

  Severity:
    - low:    fix é localizado, não toca path crítico, regression test
              cobre o caso
    - medium: fix toca shared logic que outros call sites usam, mas
              comportamento dos outros é teoricamente preservado
    - high:   fix toca contrato que múltiplos consumers leem, paridade
              cross-platform afetada, ou path com state machine
              complexo

  Cada bullet deve nomear concretamente o que pode regredir + como
  validar:
    - "Validação de outros campos (email, telefone) pode mudar porque
      compartilham trim() helper agora — validar com tests existentes
      de auth.register"
    - "ViewModel state pode ficar dessincronizado se save() falha
      depois do StateUI.Processing emitido — validar com test
      de save-error-path"

  Esta seção alimenta §13 do tech-spec (Risks & open questions).
-->
- severity: {{regression_severity_low_medium_high}}
- risks:
  - {{risk_bullet_1}}
  - {{risk_bullet_2}}

## Validation strategy

<!--
  Como saber que o bug realmente sumiu.
  Estrutura: repro pass + ≥1 regression test.

  Mandatory:
    - Re-rodar §Reproduction steps depois do fix → deve produzir
      §Expected behavior em vez de §Actual behavior.
    - ≥1 regression test que falharia ANTES do fix e passa DEPOIS.
      O test cobre o caso específico do bug — não substituir por test
      "feliz" genérico.

  Opcional:
    - Smoke test cross-platform (quando platforms.active > 1 e o fix
      é shared)
    - Visual regression (quando o bug é visual)
    - Load test (quando o bug é de performance ou concorrência)

  Refactor com strategy de validação fraca é refactor cego; bugfix
  com strategy de validação fraca é bugfix cego. Não passa
  readiness=ready.
-->
{{validation_paragraph}}

## Known constraints

<!--
  Restrições específicas do bugfix com fonte citável:
    - (platforms.active: ...) bugfix pode estar isolado a uma plataforma
    - (memory-L2: P-NNN) padrão estabelecido que o fix segue
    - (card: ...) card default que o fix respeita
    - (rule: ...) regra do projeto que motivou o caso correto
    - (severity: P0) constraint de tempo (hotfix sai hoje)
-->
- {{constraint_1_with_source_citation}}
- {{constraint_2_with_source_citation}}

## Links

<!--
  Referências externas verificáveis.
  - ticket: link absoluto do bug tracker
  - related-commits: SHAs ou links de PRs relacionados
  - logs/crashes: links para crashlytics, sentry, etc.
  - affected-versions: versões do app onde o bug foi observado
-->
- ticket: {{ticket_link_or_none}}
- related commits: {{related_commits_csv_or_none}}
- crash report: {{crashlytics_or_sentry_link_or_none}}
- affected versions: {{affected_versions_csv_or_unknown}}

## Open intake questions

<!--
  SOMENTE bloqueadores pra escrever o intake DO BUGFIX.

  Questões válidas:
    - reproduction-known: false → drill-down do conductor antes da
      Wave A; se chegou aqui sem repro, registrar Q-NNN bloqueante.
    - root-cause confidence < 0.3 E o bug é complexo (concorrência,
      heisenbug) → marcar Q-NNN não-bloqueante, fix começa por
      investigação dirigida
    - expected behavior unclear (ticket sem AC) → bloqueante; sem
      saber o que ESPERAVA acontecer, fix vai inventar

  Se não houver perguntas, deixar a frase:
    "Nenhuma open question registrada nesta fase."
-->

> Reconciled into `open-questions.yaml` with `phase_lock: intake`.

- Q-{{NNN}}: {{question_text}} — {{why_it_blocks_intake}}
- Q-{{NNN}}: {{...}}
