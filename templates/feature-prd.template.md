---
# Front-matter canônico — preenchido pelo feature-prd-agent.
feature-slug: "{{feature_slug}}"
generated-by: "feature-prd-agent"
generated-at: "{{generated_at_iso8601}}"
schema-version: 1
# Path relativo (ou link) do feature-intake.md que serviu de seed.
intake-ref: "{{intake_relative_path}}"
# Idioma primário do documento. PT-BR quando workflow-config.persona.primary-language == pt-BR.
primary-language: "{{primary_language}}"
# Métrica de cobertura: stories com source=ticket cujas AC são explícitas / total stories.
ac-coverage: {{ac_coverage_float}}
---

<!--
  feature-prd.md — Wave A · feature-prd-agent (paralelo ao feature-intake-agent)
  --------------------------------------------------------------------
  PRD escopado ao feature. NÃO é PRD de projeto — extrai a intenção
  produto SÓ para esse feature a partir de intake + ticket + memory + inventory.

  Target: 2–3 páginas. Linguagem precisa de produto. Mentor-calmo.
  Sem decisões de arquitetura, sem decisões visuais.

  Regras absolutas:
    - Nunca inventar comportamento de produto. Lacuna → `needs-elicitation`.
    - Toda story carrega `source: ticket | intake | inferred`.
    - Toda constraint cita fonte (card | memory-L2 | backend | ticket).
    - Todo success criterion tem origem em AC OU é marcado `needs-elicitation`.
    - Story count alvo: 3–7. <3 → falhar via 3-caminhos. >7 → agrupar.
-->

# {{feature_human_name}} — PRD

## 1. Feature objective

<!--
  1–2 frases. O resultado pro usuário, não a implementação.
  Origem: ticket.summary + intake's scope statement.
-->
{{feature_objective_short_paragraph}}

## 2. User stories

<!--
  3–7 stories no formato:
    Como {role}, eu quero {action}, para que {value}.

  Cada story carrega tag de source:
    source: ticket   → veio de uma AC do ticket
    source: intake   → veio de bullet/scope do intake
    source: inferred → extrapolado; emparelhar com open-question

  Heurísticas:
    - AC que é comportamento de usuário → 1 story (source: ticket)
    - AC que é regra de sistema (ex.: "deve validar email") → vira success criterion, não story
    - Sem AC mas description nomeia goal → 1 story (source: intake | inferred)
-->
- **US-{{NN}}** — Como {{role}}, eu quero {{action}}, para que {{value}}.
  - source: {{ticket_or_intake_or_inferred}}
  - ref: {{ticket_ac_id_or_intake_section_or_null}}

- **US-{{NN}}** — Como {{role}}, eu quero {{action}}, para que {{value}}.
  - source: {{...}}
  - ref: {{...}}

## 3. Success criteria

<!--
  3–5 bullets mensuráveis. Extrair verbatim das AC quando possível.
  Sem origem em AC explícita → marcar `needs-elicitation` com justificativa.
-->
- {{measurable_criterion_1}} <!-- source: ticket.AC-N | needs-elicitation -->
- {{measurable_criterion_2}}
- {{measurable_criterion_3}}

## 4. Non-goals

<!--
  2–5 bullets. Itens explicitamente fora de escopo.
  Origem: ticket "out of scope", intake's Scope OUT, memory L2 frozen-decisions
  que limitam alcance.
-->
- {{non_goal_1}}
- {{non_goal_2}}

## 5. Domain entities

<!--
  Lista de entidades de domínio referenciadas.
  Para componentes de design-system, usar o nome do inventário verbatim
  (ex.: MeoCard, MeoFab). NUNCA renomear.
  Entidades que não estão no inventário caem na subseção "new domain entities"
  com 1 linha de rationale. NÃO definir schema aqui — isso é tech-spec.
-->

### Existing (inventory hits)
- **{{entity_name_1}}** — {{one_line_role}} <!-- inventory: design-system|domain -->
- **{{entity_name_2}}** — {{one_line_role}}

### New domain entities
- **{{new_entity_1}}** — {{one_line_rationale_for_being_new}}

## 6. Constraints

<!--
  Bullets de restrições, cada uma com citação de fonte explícita:
    (card: {name}) | (memory-L2: {id}) | (backend: {key}) | (ticket)
  Constraint sem fonte citável NÃO é constraint — drop.
-->
- {{constraint_text_1}} — (card: {{card_name}})
- {{constraint_text_2}} — (memory-L2: {{l2_decision_id}})
- {{constraint_text_3}} — (backend: {{backend_key}})

## 7. Dependencies on other features

<!--
  Origem: graph query "similar-features:{slug}" (já anexada pelo conductor) +
  ticket.linkedTickets. Sem dependências → "Nenhuma identificada.".
-->
- {{dependency_1}} <!-- source: graph:similar-features | ticket:linked -->
- {{dependency_2}}

<!-- Quando vazio:
Nenhuma identificada.
-->

## 8. Risks identified

<!--
  2–5 riscos. Origem:
    - intake open-questions cujo desfecho desloca comportamento de produto
    - L2 findings que matcham keywords/módulos do feature
  Cada risco: 1 frase de causa + severity + qual artifact downstream absorve.
-->
- **R-{{NN}}** — {{risk_cause_one_sentence}}
  - severity: {{low_medium_high}}
  - absorbs-in: {{tech_spec | screen_analysis | data_contract_spec}}
  - source: {{intake_OQ_id | l2_finding_id}}

## 9. Out of PRD scope

<!--
  Lista explícita do que esse PRD adia intencionalmente para outros artefatos
  downstream (tech-spec, screen-analysis, contract-planner).
  Esse bloco NÃO é redundância com Non-goals — Non-goals = fora do produto;
  Out of PRD scope = dentro do produto mas decidido em outro doc.
-->
- {{item_deferred_to_artifact_1}} — handled by: {{tech_spec | screen_analysis | data_contract_spec | analytics_spec | test_strategy}}
- {{item_deferred_to_artifact_2}} — handled by: {{...}}

<!--
  ----------------------------------------------------------------
  Open questions PRD-level são adicionados a open-questions.yaml com
  phase_lock: prd e id no padrão OQ-PRD-NN. Não incluir lista aqui no .md;
  o conductor consolida no arquivo central.
  ----------------------------------------------------------------
-->
