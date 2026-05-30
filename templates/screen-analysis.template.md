---
# Front-matter canônico — preenchido pelo screen-analysis-agent (Wave B).
feature-slug: "{{feature_slug}}"
generated-by: "screen-analysis-agent"
generated-at: "{{generated_at_iso8601}}"
schema-version: 1
# Refs upstream (Wave A).
prd-ref: "{{feature_prd_relative_path}}"
intake-ref: "{{feature_intake_relative_path}}"
# Fingerprint do source-pack (hashes/paths) que originou a análise.
# Permite invalidar cache se conductor mudar inputs.
source-pack-fingerprint: "{{source_pack_fingerprint}}"
---

<!--
  screen-analysis.md — Wave B · screen-analysis-agent
  --------------------------------------------------------------------
  Análise comportamental por tela, com Component UX Matrix. Maior
  fidelidade UX do pacote. Companheiro machine-readable:
  ui-state-spec.yaml (mesma pasta).

  Regras absolutas:
    1. Nunca inventar estado. Só "confirmed" se visível em screenshot
       OU explicitamente nomeado em PRD/intake. Demais → needs-elicitation.
    2. Nunca inventar componente. Toda menção precisa estar no
       inventory/design-system.yaml (status != deprecated/legacy). Caso
       contrário cai em new-components-needed.
    3. Nunca célula em branco no Component UX Matrix. Sem resolução →
       ui_detail: true + open-question id.
    4. Toda claim cita fonte: screenshot:{file} / prd:{section} /
       intake:{section} / memory-L2:{id} / inferred (sempre pareado
       com needs-elicitation).
-->

# Screen Analysis — {{feature_human_name}}

## 1. Screens overview

<!--
  Tabela inicial. Cada user story do PRD gera 1+ telas; cada screenshot
  distinto gera 1 tela. Folder layout vem de inventory.conventions.yaml
  (host/content/components split é canônico — não inventar outro).
-->

| name | file (will-be) | route key | primary purpose | source |
|------|----------------|-----------|-----------------|--------|
| {{screen_name_1}} | {{ScreenFileName}}.kt | {{RouteKeyName}} | {{purpose_one_line}} | {{source_tag_csv}} |
| {{screen_name_2}} | {{ScreenFileName}}.kt | {{RouteKeyName}} | {{purpose_one_line}} | {{source_tag_csv}} |

## 2. Per-screen detail

<!--
  Uma subseção por tela, na ordem da tabela acima.
  Cada subseção repete o esqueleto abaixo (copiar/colar por tela).
-->

### 2.{{N}} {{screen_name}}

#### Layout description

<!--
  Um parágrafo descritivo. Sem marketing. Estrutura espacial e hierarquia visual.
-->
{{layout_description_paragraph}}

#### Components used

<!--
  Tabela com cada componente detectado. id deve casar com inventory.design-system.yaml.
  status: nunca usar componente deprecated/legacy como first-class — flagar
  parity gap e propor Meo* canônico.
-->

| inventory id | name | match-confidence | new-or-existing | status |
|--------------|------|------------------|-----------------|--------|
| {{meo_card}} | MeoCard | 0.92 | existing | beta |
| {{meo_fab}}  | MeoFab  | 0.97 | existing | beta |

#### Visible states from screenshots

<!--
  SOMENTE estados confirmados em screenshots ou nomeados em PRD/intake.
-->
- {{state_name}} — source: {{screenshot:filename.png | prd:UC-N | intake:section}}

#### Missing states

<!--
  Cada estado faltante precisa de open-question com phase_lock: TASK-{slug}-ui.
  Estados base obrigatórios a checar:
    idle | loading | processed | empty | error | no-internet | feature-specific
-->
- {{missing_state_name}} — needs-elicitation — open-question: Q-{{NNN}}

#### Interactions

<!--
  Tap, swipe, long-press, focus. Capturado de screenshots; inferred precisa
  pair com needs-elicitation.
-->
- {{interaction_description}} — source: {{source_tag}}

#### Transitions IN

<!--
  De onde o usuário chega (route, deep-link, push). Cada uma cita fonte.
-->
- from: {{origin_route_or_event}} — source: {{source_tag}}

#### Transitions OUT

<!--
  Para cada action: destino + state em que o destino inicia.
  Transition inferred → needs-elicitation com phase_lock: TASK-{slug}-ui.
-->
- on: {{action_label}} → {{target_route}} (starts in: {{state_name}}) — source: {{source_tag}}

#### Component UX Matrix

<!--
  TODA célula preenchida — em branco é hard validator fail.
  9 dimensões por componente interativo (componentes só-texto ficam fora):
    1. Visual states     — default/hover(web)/pressed/disabled/loading/focused (citar inventory.api.states)
    2. Affordances       — sinal de interatividade (ripple, elevation, color shift, icon, label)
    3. Transitions       — animação entre estados (duração/easing ou inventory-default)
    4. Inline error copy — texto + i18n key (proposed-key se nova)
    5. Empty/placeholder — null se o componente não dona o estado
    6. Loading/progress  — spinner|skeleton|shimmer|none
    7. Disabled rule     — condição exata + tratamento visual
    8. Android vs iOS diff — none se paridade total
    9. Open-question marker — ui_detail: true + lista de Q-NNN ids
-->

##### {{ComponentName_1}}

| dimension | value |
|-----------|-------|
| 1. Visual states | {{value_or_ui_detail_true_with_Q_id}} |
| 2. Affordances | {{value}} |
| 3. Transitions | {{value}} |
| 4. Inline error copy | {{copy_text}} — i18n: {{existing_key_or_proposed_key}} |
| 5. Empty/placeholder | {{value_or_null}} |
| 6. Loading/progress | {{spinner_skeleton_shimmer_none}} |
| 7. Disabled rule | {{condition_and_visual_treatment}} |
| 8. Android vs iOS diff | {{none_or_description}} |
| 9. Open-question marker | ui_detail: {{true_false}}; refs: [{{Q_ids_csv}}] |

##### {{ComponentName_2}}

| dimension | value |
|-----------|-------|
| 1. Visual states | {{...}} |
| 2. Affordances | {{...}} |
| 3. Transitions | {{...}} |
| 4. Inline error copy | {{...}} |
| 5. Empty/placeholder | {{...}} |
| 6. Loading/progress | {{...}} |
| 7. Disabled rule | {{...}} |
| 8. Android vs iOS diff | {{...}} |
| 9. Open-question marker | {{...}} |

## 3. i18n key candidates

<!--
  Flat list agrupada por tela. Cada label visível em screenshot vira candidate.
  Match contra inventory/i18n.yaml:
    - existing: referenciar id do inventário
    - proposed: feature.{slug}.{screen}.{role} (append em open-questions com
      phase_lock: TASK-{slug}-ui)
  Esse agent NUNCA edita i18n.yaml — só propõe.
-->

### {{screen_name_1}}
- {{label_text}} — existing: {{key_id}}
- {{label_text}} — proposed: feature.{{slug}}.{{screen}}.{{role}} — open-question: Q-{{NNN}}

### {{screen_name_2}}
- {{...}}

## 4. Cross-screen patterns

<!--
  Reuso entre telas (ex.: mesmo MeoSnackbar em 3 telas). Máximo 2 parágrafos.
-->
{{cross_screen_paragraph_1}}

{{cross_screen_paragraph_2}}

## 5. New components needed

<!--
  Componentes detectados nos screenshots que NÃO casam com nenhum entry
  não-deprecated do inventário. Cada um com rationale + componentes
  semanticamente próximos que foram descartados.
-->
- **{{proposed_component_name}}** — rationale: {{why_no_inventory_match}}; closest-existing: {{inventory_id_csv}}

<!-- Quando vazio:
Nenhum novo componente necessário.
-->

## 6. Open questions reference

<!--
  Lista de Q-NNN ids adicionados por esse agent, agrupados por phase_lock.
  O conteúdo completo vive em open-questions.yaml.
-->

### phase_lock: TASK-{{slug}}-ui
- Q-{{NNN}}: {{question_summary}}
- Q-{{NNN}}: {{question_summary}}
