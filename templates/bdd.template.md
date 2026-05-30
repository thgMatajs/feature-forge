---
# Front-matter canônico — preenchido pelo contract-planner-agent (Wave B).
feature-slug: "{{feature_slug}}"
generated-by: "contract-planner-agent"
generated-at: "{{generated_at_iso8601}}"
schema-version: 1
# Refs upstream.
prd-ref: "{{feature_prd_relative_path}}"
screen-analysis-ref: "{{screen_analysis_relative_path}}"
# Espelhado em bdd.json — mesma estrutura, dois encodings.
mirror-file: "bdd.json"
---

<!--
  bdd.md — Wave B · contract-planner-agent (1 de 6 artefatos)
  --------------------------------------------------------------------
  Spec comportamental em Gherkin (Given/When/Then). Consumido por
  test scaffolders e pela gate de verification.

  Regras absolutas:
    - 1 ou mais scenarios por user story do feature-prd.md
    - 5 mandatory rule-driven scenarios (testing.md):
        happy-path | null-empty | network-failure | loading-guard | unknown-value
    - Per-state scenarios pra cada state confirmed/inferred-needs-confirmation
      do ui-state-spec.yaml. States needs-elicitation NÃO viram scenario;
      vão pra open-questions.
    - Toda scenario carrega tag de source no formato:
        @source:user-story:US-NN
        @source:mandatory-rule:{rule-id}
        @source:screen-state:{screen}:{state}
    - Sem assertion → needs-elicitation: true (NÃO inventar AC).
-->

Feature: {{feature_human_name}}

  <!--
    Background opcional. Use quando ≥2 scenarios compartilham o mesmo
    Given inicial (ex.: usuário autenticado). Caso contrário, omitir
    a seção inteira.
  -->
  Background:
    Given {{persona_condition_step}}
    And   {{additional_shared_precondition_optional}}

  # ------------------------------------------------------------------
  # Scenario PLACEHOLDER — bem comentado. Copiar para cada cenário real.
  # ------------------------------------------------------------------
  @source:user-story:US-{{NN}} @priority:{{must_should_could}}
  Scenario: {{scenario_title_human_readable}}
    # Given = preconditions visíveis ao usuário ou state inicial
    Given {{given_step_1}}
    And   {{given_step_2_optional}}
    # When = ação do usuário ou evento de sistema
    When  {{when_step_1}}
    And   {{when_step_2_optional}}
    # Then = resultado observável (UI, navegação, analytics, persistência)
    Then  {{then_step_1}}
    And   {{then_step_2_optional}}
    And   {{then_step_n_analytics_or_nav_optional}}

  # ------------------------------------------------------------------
  # Scenarios por user story do PRD.
  # Cada US-NN do feature-prd.md gera 1+ scenarios aqui.
  # ------------------------------------------------------------------

  @source:user-story:US-{{NN}}
  Scenario: {{user_story_scenario_title}}
    Given {{...}}
    When  {{...}}
    Then  {{...}}

  # ------------------------------------------------------------------
  # 5 mandatory rule-driven scenarios — sempre presentes.
  # IDs sugeridos: MAN-01..MAN-05 (alinhados com test-strategy.yaml).
  # ------------------------------------------------------------------

  @source:mandatory-rule:happy-path
  Scenario: Happy path — {{feature_short}} executa fluxo principal sem erros
    Given {{...}}
    When  {{...}}
    Then  {{...}}

  @source:mandatory-rule:null-empty-input
  Scenario: Null/empty input — defaults seguros aplicados
    Given {{...}}
    When  {{...}}
    Then  {{...}}

  @source:mandatory-rule:network-failure
  Scenario: Network/IO failure — error state + loading limpo
    Given {{...}}
    When  {{...}}
    Then  {{...}}

  @source:mandatory-rule:loading-guard
  Scenario: Loading guard — ação durante loading não dispara duplicata
    Given {{...}}
    When  {{...}}
    Then  {{...}}

  @source:mandatory-rule:unknown-value
  Scenario: Unknown/unexpected value — fallback sem crash
    Given {{...}}
    When  {{...}}
    Then  {{...}}

  # ------------------------------------------------------------------
  # Per-state scenarios — um por state `confirmed` ou
  # `inferred-needs-confirmation` em ui-state-spec.yaml.
  # States `needs-elicitation` NÃO entram aqui — vão pra open-questions.
  # ------------------------------------------------------------------

  @source:screen-state:{{screen_name}}:{{state_name}}
  Scenario: {{screen}} mostra estado {{state}} quando {{trigger}}
    Given {{...}}
    When  {{...}}
    Then  {{...}}

<!--
  ----------------------------------------------------------------
  Needs-elicitation — itens não resolvidos vão pra open-questions.md/yaml
  com id no padrão Q-CP-NN e ficam referenciados em bdd.json no bloco
  "needs-elicitation". Não listar aqui em texto livre.
  ----------------------------------------------------------------
-->
