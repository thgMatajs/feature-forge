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
# Subtype canônico — fixo em "refactor" para esta variante.
# Ver docs/design/07-discipline.md §8 (Non-product feature track).
subtype: "refactor"
# Origem do material que alimentou o intake.
# Valores aceitos: ticket | text | screenshot | mixed
source-type: "{{source_type}}"
# Referência verificável da origem (link do ticket, hash do screenshot, etc.).
# Use "none" quando não houver.
source-ref: "{{source_ref_or_none}}"
---

<!--
  feature-intake.md — Wave A (refactor variant) · feature-intake-agent
  --------------------------------------------------------------------
  Documento curto (1 página) que abre o pacote de REFACTOR.
  Discipline §8 — comportamento inalterado por design, sem PRD natural,
  sem screen-analysis, sem analytics nova.

  Voz: mentor-calmo. Frases curtas. Sem marketing.
  Idioma: PT-BR se a fonte estiver em PT-BR; senão EN.

  Drop intencional vs variante de produto:
    - "What this feature delivers" (assume user value) → substituído por
      "Problem" (descreve o erro técnico atual)
    - "Why now" (motivação de produto) → cabe em §Problem.context
    - "Scope IN" como user-value → substituído por §Files affected

  Regra absoluta: campo ausente → null OU open question; nunca inventar.
  Mais regra absoluta: se durante o intake o agente perceber que o trabalho
  REALMENTE muda comportamento, ele PARA e levanta no conductor — a feature
  deveria virar subtype=product, não refactor.
-->

# Refactor — {{human_readable_feature_name}}

<!--
  Cabeçalho com slug · owner · platforms · subtype literal.
-->
> slug: {{feature_slug}} · owner: {{owner_or_null}} · platforms: {{active_platforms_comma_separated}} · subtype: refactor

## Source of truth

<!--
  Cite a fonte exatamente como ela existe nos inputs. Nunca fabricar.
  - ticket: link literal ou "none"
  - description origin: ticket | user-paste | user-elicitation
  - Screenshots existem só quando refactor toca componente visual que precisa
    documentar localização anterior → mantém o campo, costuma ser 0.
-->
- ticket: {{ticket_link_or_none}}
- screenshots: {{screenshots_count}} file(s) — {{screenshots_relative_paths_csv_or_none}}
- description origin: {{description_origin}}

<!--
  MEM-CONTEXT (W-ROUTE 6c) — gotchas/convenções relevantes do acervo de memória
  (`mem find`), injetadas pelo engine ANTES do dispatch. Quando vazio (mem
  indisponível ou sem hits), a linha abaixo fica em branco — sem ruído. NÃO é
  fonte da verdade; é dica de contexto pro autor consultar.
-->
{{mem_context_hint}}

## Problem

<!--
  Um parágrafo descrevendo a deficiência técnica atual. Exemplos:
    - "MeoButton vive em organisms/ mas é atom (zero composição) — quebra
      Atomic Design e dificulta busca por desenvolvedores novos."
    - "Pacote feature/bonsai/ui/list/ não segue a convenção
      {Screen}Screen.kt + Content + Components — refactor para alinhar."
    - "Nav2 (NavHost/composable) ainda em feature/auth — projeto inteiro
      migrado para Nav3 menos esse leftover."

  Sem termos de valor de usuário. Sem promessas de melhoria de UX.
  Refactor é technical debt; descreva o débito.
-->
{{technical_debt_paragraph}}

## Root cause

<!--
  Um parágrafo curto: por que esse estado existe hoje?
    - "Adicionado em 2024 antes do Atomic Design ser convenção do projeto."
    - "Migração Nav2→Nav3 concluiu em 90% do app; auth ficou de fora pq
      tinha PR aberto e mergeou após a migração."

  Se desconhecido, deixar "Root cause unknown — registered as Q-NNN" e
  abrir open question com phase_lock: intake.
-->
{{root_cause_paragraph_or_unknown}}

## Files affected

<!--
  Lista CONCRETA de paths que vão ser tocados. Cada path é um bullet
  com o tipo de mudança.

  Tipos canônicos:
    - move:    arquivo muda de local
    - rename:  arquivo muda de nome (e talvez de local)
    - delete:  arquivo será removido
    - update:  conteúdo do arquivo é editado (referências, imports, etc.)
    - create:  novo arquivo é introduzido (raro em refactor; só pra
               consolidar duplicação)

  Granularidade: arquivos individuais, não diretórios genéricos.
  Em refactor que toca >20 arquivos, agrupar por padrão e explicitar:
    "feature/bonsai/ui/list/ → feature/bonsai/list/ (12 arquivos move)"

  Restrição: NÃO listar arquivos de teste aqui — refactor por definição
  não muda testes. Se você está prestes a listar test files, PARE e
  reavalie se isso é realmente refactor ou disfarce de mudança de
  comportamento.
-->
- {{file_or_group_1}} ({{move_rename_delete_update_create}})
- {{file_or_group_2}} ({{move_rename_delete_update_create}})

## Architecture: before → after

<!--
  Mini-diagrama OU duas listas curtas: estado atual vs estado pretendido.
  Capturar arquitetura, NÃO comportamento.

  Exemplo (boundary refactor):
    Before:
      • androidApp/core/designsystem/molecules/MeoButton.kt
    After:
      • androidApp/core/designsystem/atoms/MeoButton.kt
      • import path atualizado em N consumers

  Exemplo (package refactor):
    Before: feature/bonsai/ui/list/{BonsaiListScreen.kt, ...}
    After:  feature/bonsai/list/{BonsaiListScreen.kt, BonsaiListContent.kt,
            BonsaiListComponents.kt, BonsaiListMappers.kt}
-->

Before:
- {{before_state_bullet_1}}

After:
- {{after_state_bullet_1}}

## No-behavior-change attestation

<!--
  Bloco OBRIGATÓRIO. Discipline §8 — refactor preserva comportamento
  observável. Esta seção é a declaração explícita disso, lida pelo
  validator check_no_behavior_change durante Wave E e pelo
  task-contract-writer ao montar allowed_files.

  Marque YES nas afirmações que se aplicam. NÃO marcar YES sem certeza —
  cada YES é assinado pelo agente.

  Se alguma afirmação for NO, o refactor talvez não seja refactor.
  Conductor deve receber sinal para reavaliar subtype.
-->

- [ ] No new analytics events introduced
- [ ] No new UI state introduced
- [ ] No new navigation route introduced
- [ ] No new persistence schema introduced
- [ ] No new validation rule introduced
- [ ] No new permission/auth check introduced
- [ ] No existing test file modified (additive tests for safety net are OK
      but should be listed in Wave D task contracts, not here)
- [ ] No new public API exposed in shared module

If any of the above cannot be checked, this is not a refactor — escalate
back to planning-conductor and reconsider subtype.

## Known constraints

<!--
  Restrições específicas do refactor com fonte citável:
    - (platforms.active: ...) refactor pode tocar Android-only
    - (memory-L2: P-NNN) padrão estabelecido do projeto que o refactor
      vai trazer para conformidade
    - (card: ...) card default que o refactor segue
    - (inventory: ...) inventário DS exige reuse → refactor consolida
    - (rule: ...) regra do projeto que motivou o refactor
-->
- {{constraint_1_with_source_citation}}
- {{constraint_2_with_source_citation}}

## Validation strategy

<!--
  Um parágrafo: como o agente HUMANO vai validar que o comportamento
  está realmente inalterado depois do refactor?

  Exemplos:
    - "Rodar suite completa (Android + iOS + KMP common) — todas passando
      antes e depois."
    - "Smoke test manual no Android emulator: navegação bonsai list →
      detail → edit → list."
    - "Visual regression test no Web (Playwright) cobre as 3 telas
      tocadas."

  Refactor sem strategy de validação é refactor cego — não passa
  readiness=ready.
-->
{{validation_paragraph}}

## Open intake questions

<!--
  SOMENTE bloqueadores pra escrever o intake DO REFACTOR.

  Questões válidas:
    - root cause unknown
    - lista de arquivos afetados incompleta (ticket cita "etc" e não tem
      como inferir o resto)
    - inputs contraditórios (ticket pede "refactor" mas descreve mudança
      de comportamento → escalate subtype reconsideration)

  Se não houver perguntas, deixar a frase:
    "Nenhuma open question registrada nesta fase."
-->

> Reconciled into `open-questions.yaml` with `phase_lock: intake`.

- Q-{{NNN}}: {{question_text}} — {{why_it_blocks_intake}}
- Q-{{NNN}}: {{...}}
