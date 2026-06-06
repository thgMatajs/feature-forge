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
# Origem do material que alimentou o intake.
# Valores aceitos: ticket | text | screenshot | mixed
source-type: "{{source_type}}"
# Referência verificável da origem (link do ticket, hash do screenshot, etc.).
# Use "none" quando não houver.
source-ref: "{{source_ref_or_none}}"
---

<!--
  feature-intake.md — Wave A · feature-intake-agent
  --------------------------------------------------------------------
  Documento curto (1–2 páginas) que abre o pacote do feature.
  Captura identidade, fonte da verdade, escopo IN/OUT, restrições
  conhecidas e questões abertas exclusivas do intake.

  Voz: mentor-calmo. Frases curtas. Sem marketing.
  Idioma: PT-BR se a fonte estiver em PT-BR; senão EN.

  Não decidir produto, não analisar telas, não falar de arquitetura.
  Esses domínios pertencem a outros sub-agents (PRD, screen-analysis,
  tech-spec). Aqui é só o "quem/o quê/por quê/escopo" inicial.

  Regra absoluta: campo ausente → null OU open question; nunca inventar.
-->

# {{human_readable_feature_name}}

<!--
  Cabeçalho de uma linha com slug · owner · plataformas ativas.
  - owner vem do assignee do ticket; "null" se desconhecido.
  - platforms vem de workflow-config.platforms.active (sem filtro pelo ticket).
-->
> slug: {{feature_slug}} · owner: {{owner_or_null}} · platforms: {{active_platforms_comma_separated}}

## Source of truth

<!--
  Cite a fonte exatamente como ela existe nos inputs. Nunca fabricar.
  - ticket: link literal ou "none"
  - screenshots: contagem + paths relativos (sob features/{slug}/screenshots/)
  - description origin: ticket | user-paste | user-elicitation
-->
- ticket: {{ticket_link_or_none}}
- screenshots: {{screenshots_count}} file(s) — {{screenshots_relative_paths_csv}}
- description origin: {{description_origin}}

<!--
  EXTENSION-CONTEXT-BLOCK (Gap 9 — extends-feature mechanic)
  ----------------------------------------------------------
  Renderize a seção `## Extension context` ABAIXO SOMENTE quando
  hypothesis.yaml.extends-feature != null (feature derivada de uma pai
  já em estado `done`).

  Convenção de renderização:
    - Se extends-feature == null → REMOVA o bloco inteiro entre os
      marcadores `EXTENSION-CONTEXT-BLOCK BEGIN` e
      `EXTENSION-CONTEXT-BLOCK END` (incluindo os marcadores). Feature
      standalone fica exatamente como antes do Gap 9 — sem ruído.
    - Se extends-feature != null → MANTENHA a seção, preencha os 4
      campos abaixo, e remova apenas os marcadores `BEGIN/END`.

  Campos:
    · Parent feature  — slug da pai (igual a hypothesis.yaml.extends-feature)
    · Parent shipped  — valor de .claude/memory/L1/{parent}/status.json.shipped-at
    · Scope of this extension — delta intent declarado pelo user (1-2 frases)
    · Reuse from parent — lista explícita do que herdamos (contracts, screens,
                          helpers, naming conventions). Sem invenção.
    · Out-of-scope vs parent — non-goals explícitos pra evitar re-extension
                                redundante. Sem invenção.

  Voz: mentor calmo. Sem emoji. Sem marketing. Conciso.
  feature-intake-agent: instruções de preenchimento em
  `agents/feature-intake-agent.md §Extension block (Gap 9)`.
-->

<!-- EXTENSION-CONTEXT-BLOCK BEGIN -->
## Extension context

- Parent feature: {{parent_feature_slug}}
- Parent shipped: {{parent_shipped_at_iso8601}}
- Scope of this extension: {{extension_scope_delta}}
- Reuse from parent: {{reuse_from_parent_csv}}
- Out-of-scope vs parent: {{out_of_scope_vs_parent_csv}}
<!-- EXTENSION-CONTEXT-BLOCK END -->

## What this feature delivers

<!--
  Um parágrafo. Mudança user-facing.
  Sem termos técnicos, sem implementação. Só o resultado pro usuário.
-->
{{user_facing_change_paragraph}}

## Why now

<!--
  Um parágrafo. Gatilho a partir do ticket/conversa.
  Linkar contexto de produto mais amplo SOMENTE se estiver explícito nos
  inputs — nunca inferir.
-->
{{trigger_and_context_paragraph}}

## Scope IN

<!--
  Lista de entregáveis concretos detectados nos inputs.
  Ordem de prioridade pra extração:
    1. Acceptance criteria do ticket (cada AC → 1 bullet normalizado)
    2. Bullets da description que afirmam um entregável
    3. Lista de screenshots — granularidade "screen X existe"
    4. resolved-decisions vindos da Fase 3 do conductor
-->
- {{in_scope_deliverable_1}}
- {{in_scope_deliverable_2}}
- {{...}}

## Scope OUT

<!--
  Itens explicitamente fora. Ordem de prioridade:
    1. Menções literais "out of scope" / "não está no escopo"
    2. Ausência em screenshots quando ticket cita feature-flag/v2/futuro
    3. resolved-decisions taggeadas out-of-scope

  Se NENHUMA fonte separar IN vs OUT, manter o marker abaixo e abrir Q-NNN.
  NÃO inventar fronteira.
-->
- {{out_of_scope_item_1}}
- {{out_of_scope_item_2}}

<!--
  Variante alternativa quando inputs não separam IN/OUT (mover para cima
  da lista, substituindo bullets, se aplicável):

  > No explicit out-of-scope boundary detected in inputs. See Q-NNN.
-->

## Known constraints

<!--
  Bullets de restrições conhecidas. Cada uma deve citar a fonte:
    - (platforms.active: …) restrições de plataforma do workflow-config
    - (memory-L2: D-NNN) decisões congeladas que afetam o feature
    - (card: …) card default que se aplica
    - (inventory: …) regras de inventário (DS reuse obrigatório, i18n SoT)
  Restrição sem fonte citável NÃO é restrição — derrubar.
-->
- {{constraint_1_with_source_citation}}
- {{constraint_2_with_source_citation}}

## Open intake questions

<!--
  SOMENTE bloqueadores pra escrever o intake.
  NÃO produto (→ feature-prd-agent).
  NÃO arquitetura (→ tech-spec-agent).
  NÃO análise visual (→ screen-analysis-agent).

  Questões válidas aqui:
    - ticket sem AC e sem description → escopo unclear
    - owner desconhecido sem pre-resolução
    - inputs contraditórios afetando o escopo
    - human name ausente em todas as fontes

  Cada pergunta é reconciliada em open-questions.yaml com
  phase_lock: intake (append, nunca overwrite).

  Se não houver perguntas, deixar essa seção com a frase
  "Nenhuma open question registrada nesta fase." e NÃO tocar
  em open-questions.yaml.
-->

> Reconciled into `open-questions.yaml` with `phase_lock: intake`.

- Q-{{NNN}}: {{question_text}} — {{why_it_blocks_intake}}
- Q-{{NNN}}: {{...}}
