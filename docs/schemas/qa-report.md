# qa-report.json — schema (v1)

> Gerado por `forge qa` Phase 4 (synthesis). Validado por
> `validators/validate_qa_report.py`. Schema-version aditivo (v1 desde
> spec 2026-06-05).

Este é o artefato canônico que consolida tudo que os auditores
encontraram durante uma run de `forge qa`. Phase 4 (synthesis) coleta os
findings parciais dos auditores, calcula o veredito agregado, e
serializa o resultado em `qa-report.json` no diretório da run
(`.planning/qa/<feature>/<run-id>/qa-report.json`). Phase 5 (emit) lê
esse JSON pra decidir o que vira `proposed-evolution`.

Mantenha o doc curto e canônico — qualquer mudança aqui exige bump de
`schema_version` se for breaking (remoção de campo, mudança de tipo,
novo required). Adicionar campo opcional é não-breaking e não exige
bump.

## Top-level shape

```yaml
schema_version: 1

run:
  id: "2026-06-05T14-32-08Z-a1b2"        # ISO timestamp + sufixo random
  scope:
    type: "feature" | "screen" | "task" | "paranoid"
    target: "<slug ou id>"
  config_snapshot: {...}                  # qa: section da workflow-config
  started_at: "2026-06-05T14:32:08Z"
  finished_at: "2026-06-05T14:35:22Z"
  duration_s: 194

verdict: "BLOCK" | "FLAG" | "PASS"

summary:
  total_findings: 12
  by_severity:
    critical: 1
    high: 2
    medium: 4
    low: 3
    info: 2
  by_vector:
    spec-vs-spec: 3
    coverage: 4
    chaos: 3
    validator-claim: 2

findings:
  - <qa-finding schema — ver qa-finding.md>
```

## Field semantics

- `schema_version`: integer, atualmente `1`. Bump somente em mudança
  breaking (remoção de campo, mudança de tipo, novo required).
- `run.id`: formato `YYYY-MM-DDTHH-MM-SSZ-<4-char-hex>`. Unicidade
  garantida pelo sufixo random — colisão na mesma timestamp resolvida
  pelo hex.
- `run.scope.type`: enum estrito `{"feature", "screen", "task", "paranoid"}`.
- `run.scope.target`: identificador do alvo dentro do escopo (slug da
  feature, id da screen, id da task; pra `paranoid`, fica `"*"` ou nome
  do módulo varrido).
- `run.config_snapshot`: cópia literal da seção `qa:` da
  workflow-config no momento da run — permite reproduzir o veredito
  mesmo se a config evoluir depois.
- `run.started_at` / `run.finished_at`: timestamps ISO-8601 em UTC
  (`Z` suffix obrigatório).
- `run.duration_s`: inteiro, segundos. Deve bater com
  `finished_at - started_at` arredondado.
- `verdict`: enum estrito `{"BLOCK", "FLAG", "PASS"}`. Calculado via
  rubric §5.4 do spec — `BLOCK if critical >= 1 or high >= 3`,
  `FLAG if high in {1,2} or medium >= 3`, `PASS otherwise`.
- `summary.total_findings`: inteiro, igual a `len(findings)`.
- `summary.by_severity`: keys obrigatórias `critical / high / medium /
  low / info`; soma deve igualar `total_findings`.
- `summary.by_vector`: keys obrigatórias `spec-vs-spec / coverage /
  chaos / validator-claim`; cards via `qa-extensions` podem adicionar
  keys extras com nome do auditor.
- `findings`: lista de objetos no shape de `qa-finding.md`. Ordem
  canônica: severity desc (critical → info), depois vector asc
  alfabético, depois `created_at` asc.

## Reuso

- Decisão 25 fingerprint canonical-form: cada finding carrega
  `fingerprint` próprio (ver `qa-finding.md`); report agregado não
  recalcula nem deduplica — fingerprint vive no nível do finding.
- Decisão 27 pause: report parcial é serializado a cada phase end via
  `checkpoint.json` paralelo, permitindo resume sem perda de progresso.

## Cross-refs

- Schema individual de finding: `docs/schemas/qa-finding.md`
- Card extension: `docs/schemas/qa-extensions.md`
- Spec fonte: `docs/superpowers/specs/2026-06-05-forge-qa-design.md` §6.1
- Rubric de verdict: spec §5.4
