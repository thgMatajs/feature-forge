---
# implementation-readiness-review.md — Wave E · readiness-reviewer.
# --------------------------------------------------------------------
# Última gate antes de `forge implement`. Auditor goal-backward que decide
# se o feature package está pronto. Verdict: ready | partial | blocked.
# Consumido por:
#   - planning-conductor — decide se emite o closing block readiness=ready
#   - execution-conductor (forge implement) — refuses to start se != ready
#
# Regras absolutas:
#   1. NUNCA inventa verdict. Toda ✓/✗ cita path:line ou artifact:field.
#   2. NUNCA "looks good" — usar contadores concretos (14/14, 7/7).
#   3. Cada blocker oferece exatamente 3 caminhos (07-discipline.md §1).
#   4. Fail-fast em Phase 2 (cascade de validators) — primeira block-severity
#      para; warnings coletadas inline.
#   5. Strictness explícita: strict (14 docs) | standard (10) | lean (5).
#      Mismatch entre count e label = discipline violation reportada.

feature_slug: "{{feature_slug}}"
generated_by: "readiness-reviewer"
generated_at: "{{generated_at_iso8601}}"
schema_version: 1

# ---- Refs upstream --------------------------------------------------------
intake_ref: "{{feature_intake_relative_path}}"
prd_ref: "{{feature_prd_relative_path}}"
screen_analysis_ref: "{{screen_analysis_relative_path}}"
ui_state_spec_ref: "{{ui_state_spec_relative_path}}"
bdd_ref: "{{bdd_relative_path}}"
navigation_spec_ref: "{{navigation_spec_relative_path}}"
data_contract_ref: "{{data_contract_relative_path}}"
analytics_spec_ref: "{{analytics_spec_relative_path}}"
test_strategy_ref: "{{test_strategy_relative_path}}"
tech_spec_ref: "{{tech_spec_relative_path}}"
task_breakdown_ref: "{{task_breakdown_relative_path}}"
open_questions_ref: "{{open_questions_relative_path}}"

# ---- Verdict --------------------------------------------------------------
# Set pelo agent depois de Phase 6.
verdict: "{{ready|partial|blocked}}"
strictness: "{{strict|standard|lean}}"
reviewed_at: "{{iso8601_utc}}"
reviewer: "readiness-reviewer"
---

# Implementation Readiness Review — {{feature_slug}}

> **Verdict:** `{{ready|partial|blocked}}` · **Strictness:** `{{strict|standard|lean}}`
> Reviewed at {{iso8601_utc}} by `readiness-reviewer`.
> Hard-gates: `readiness-must-be-ready` (this report IS the gate) · `no-files-outside-allowed-files` · `validations-must-pass` · `completion-evidence-required` · `no-invented-behavior`.

## 1. Required artifacts checklist

<!--
  Marca [✓] / [✗] por artifact. count_present / count_target deve casar com
  a strictness (14/14 | 10/10 | 5/5). Mismatch entre workflow-config count e
  label vira discipline violation em §7.
-->

| # | Artifact | Present | Validator |
|---|---|---|---|
| 1 | `feature-intake.md` | `[✓|✗]` | `pass|fail|n/a` |
| 2 | `feature-prd.md` | `[✓|✗]` | `pass|fail|n/a` |
| 3 | `screen-analysis.md` | `[✓|✗]` | `pass|fail|n/a` |
| 4 | `bdd.md` | `[✓|✗]` | `pass|fail|n/a` |
| 5 | `bdd.json` | `[✓|✗]` | `pass|fail|n/a` |
| 6 | `ui-state-spec.yaml` | `[✓|✗]` | `pass|fail|n/a` |
| 7 | `navigation-spec.yaml` | `[✓|✗]` | `pass|fail|n/a` |
| 8 | `data-contract-spec.yaml` | `[✓|✗]` | `pass|fail|n/a` |
| 9 | `analytics-spec.yaml` | `[✓|✗]` | `pass|fail|n/a` |
| 10 | `test-strategy.yaml` | `[✓|✗]` | `pass|fail|n/a` |
| 11 | `tech-spec.md` | `[✓|✗]` | `pass|fail|n/a` |
| 12 | `task-breakdown.yaml` | `[✓|✗]` | `pass|fail|n/a` |
| 13 | `tasks/TASK-*.yaml` | `[✓|✗]` | `pass|fail|n/a` |
| 14 | `plan-feature-handoff.json` | `[✓|✗]` | `pass|fail|n/a` |

Meta-artifacts (required em todos níveis, fora do count):

- `open-questions.yaml` — `[✓|✗]` · blocking entries: `{{N}}`
- `evals/evals.json` — `[✓|✗]` (template only; populated post-implement)

**Counts:** `{{count_present}}/{{count_target}}` ({{strictness}}).

## 2. Per-artifact validator pass

<!--
  Fail-fast cascade: primeira block-severity falha PARA o resto e marca "—".
  Warning-severity coletadas inline. Comando exato registrado na coluna.
-->

| Validator | Command | Result | Notes |
|---|---|---|---|
| `validate_feature_package.py` | `python3 .claude/scripts/validate_feature_package.py {{feature_slug}}` | `pass|fail|—` | {{notes}} |
| `validate_readiness.py` | `python3 .claude/scripts/validate_readiness.py {{feature_slug}}` | `pass|fail|—` | {{notes}} |
| `validate_task_contract.py` | `python3 .claude/scripts/validate_task_contract.py {{feature_slug}}/tasks/TASK-*.yaml` | `pass|fail|—` | {{notes}} |
| `validate_data_contract.py` | `python3 .claude/scripts/validate_data_contract.py {{feature_slug}}` | `pass|fail|—` | {{notes}} |
| `validate_screen_analysis.py` | `python3 .claude/scripts/validate_screen_analysis.py {{feature_slug}}` | `pass|fail|—` | {{notes}} |
| `validate_backend_e2e.py` | `python3 .claude/scripts/validate_backend_e2e.py {{feature_slug}}` | `pass|fail|—|skip` | só roda se data_origins.api.exists |

**Failures:** `{{count_block_severity}}` block-severity · `{{count_warning}}` warning-severity.

## 3. Goal-backward audit

<!--
  Para cada user story do feature-prd.md §User Stories, traçar:
    US-NN → bdd:Scenario → ui-state-spec.screen.state → navigation:entry
         → data-contract:entity (se aplicável) → tech-spec:section
         → tasks/TASK-NNNN.yaml → test-strategy:test-id
  Link ausente = ✗ MISSING + virar entry em §9.
-->

| Story | BDD scenario | Screen state | Nav entry | Data entity | Tech-spec | TASK | Test |
|---|---|---|---|---|---|---|---|
| US-{{NN}} | SC-{{NNN}} | `{{screen.state}}` | `{{nav_entry}}` | `{{EntityName}}` | `{{section}}` | `TASK-{{NNNN}}` | `MAN-{{NN}}` |

**Broken chains:** `{{count_broken_chains}}`.

## 4. Open questions audit

<!--
  Lê open-questions.yaml. Classifica em 3 buckets:
    - blocking: true       → verdict cannot be ready
    - phase_lock: TASK-X   → conditional-ready (essa TASK pode parar)
    - neither              → informational, verdict pode ser ready/partial
-->

- **Blocking (`blocking: true`):** `{{N}}` — list:
  - {{Q_id}} — `{{topic}}` · artifact:field `{{ref}}`
- **Phase-locked:** `{{N}}` — list:
  - {{Q_id}} — phase_lock `{{TASK_NNNN}}` · `{{topic}}`
- **Informational (non-blocking):** `{{N}}`

## 5. Hard gates check

<!--
  Verbatim copy de workflow.hard-gates — cada gate auditado aqui exceto
  readiness-must-be-ready (este relatório É essa gate).
-->

| Gate | Audit | Evidence |
|---|---|---|
| `readiness-must-be-ready` | DEFERRED (this report IS the gate) | — |
| `no-files-outside-allowed-files` | `pass|fail` | overlap check across `tasks/TASK-*.yaml.allowed_files` |
| `validations-must-pass` | `pass|fail` | every TASK declares `validation_steps.commands` non-empty |
| `completion-evidence-required` | `pass|fail` | every TASK declares the 4 canonical `evidence_required` fields |
| `no-invented-behavior` | `pass|fail` | grep scan for forbidden phrases (TBD/TODO/FIXME/lorem) |

## 6. Card consistency check

<!--
  Cada card ativo com contributes.templates.target: X deve ter contribuído.
  Conflict (2 cards replace-section mesma section) = block.
-->

- Cards ativos com `contributes.templates.target`: {{list}}
- Targets aplicados: {{✓ N | ✗ M missing}}
- Conflict markers detectados: `{{count}}`

## 7. Discipline violations

<!--
  - 3-caminhos: toda gate-violation example precisa de exatamente 3 paths
  - Invented commands: grep -rEn 'forge [a-z-]+' deve casar canonical command list
  - Flags em commands citados: forge plan --strict é violation (zero flags)
  - Forbidden phrases: TBD/TODO/FIXME/XXX/???/sample/foo/bar/lorem/placeholder
-->

- 3-caminhos compliance: `{{✓ all gate-blocks have 3 paths | ✗ N malformed}}`
- Invented `forge` commands detected: `{{count}}`
- Flags em commands citados: `{{count}}`
- Forbidden phrases (block-severity em contracts): `{{count}}`
- Forbidden phrases (warning em narrative): `{{count}}`

**Violations summary:** `{{count_block_severity}}` block · `{{count_warning}}` warning.

## 8. Verdict rationale

<!--
  Um parágrafo. Cita findings específicos. Sem prosa genérica.
  Exemplo: "14/14 artifacts present; all validators green; 7/7 user stories
  trace forward to TASK + test; 0 blocking open questions; 0 discipline
  violations. Verdict: ready."
-->

{{paragraph_with_concrete_findings}}

## 9. If blocked — what's needed to unblock

<!--
  Para cada blocker, emitir o 3-caminhos block canônico (07-discipline.md §1):
    🛑 ID — TITLE
    Onde: artifact:field
    Por que importa: ...
    Três caminhos pra resolver:
      A (fix forward) — motivo provável: ...
      B (revert)      — motivo provável: ...
      C (split)       — motivo provável: ...
-->

```
🛑 B-{{NNN}} — {{blocker_title}}

   Onde: {{artifact}}:{{field}}
   Por que importa: {{why}}

   Três caminhos pra resolver:
     A (fix forward) — {{motivo_provavel_A}}
                       Ação: {{action_A}}
     B (revert)      — {{motivo_provavel_B}}
                       Ação: {{action_B}}
     C (split)       — {{motivo_provavel_C}}
                       Ação: {{action_C}}
```

<!--
  Bloco repetido por blocker. Quando verdict=ready, omitir esta seção
  inteira (sem bloco vazio).
-->

---

<!--
  ----------------------------------------------------------------
  Verdict bloco YAML — machine-readable. Consumido por:
    - planning-conductor: decide o closing format
    - execution-conductor: refuses to start se status != ready
  ----------------------------------------------------------------
-->

```yaml
readiness_verdict:
  status: "{{ready|partial|blocked}}"
  artifacts_checked: 0
  validator_failures: 0
  goal_backward_broken_chains: 0
  blocking_open_questions: 0
  discipline_violations: 0
  blockers: []                                       # ex.: ["B-001"]
  warnings: []                                       # ex.: ["W-002"]
  unblock_steps: []                                  # cada entry referencia 3-caminhos do §9
```
