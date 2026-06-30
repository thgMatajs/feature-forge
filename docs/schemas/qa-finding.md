# qa-finding — schema (v1)

> Shape canônico de um finding individual gerado pelos auditores de
> `forge qa` Phase 2 (static auditors) e Phase 3 (generative auditors).
> Consumido por Phase 4 (synthesis) pra agregar verdict e por Phase 5
> (emit) pra serializar em `proposed-evolutions`. Schema-version aditivo
> (v1 desde spec 2026-06-05).

Cada auditor escreve seu próprio `findings/<auditor>.json` (lista de
findings draft) ao terminar sua fase. `qa-synthesizer` (Phase 4) lê
todos, deduplica via fingerprint canonical-form (Decisão 25), atribui
severidade per rubric (§5.4), e consolida em `qa-report.json`. O
shape dos findings agregados no report é exatamente o documentado
aqui — sem transformação intermediária.

Mantenha o doc canônico. Adicionar campo opcional é não-breaking;
remoção, mudança de tipo ou novo required exige bump de
`schema_version` no envelope (`qa-report.md`).

## Shape canônico

```json
{
  "id": "qa-2026-06-05T14-32-08Z-a1b2-0007",
  "fingerprint": "7a3f4d2c1b9e8a0f...",
  "vector": "validator-claim",
  "severity": "critical",
  "title": "validate_data_contract.py passa fixture com email vazio",
  "description": "O validator declarado em TASK-0004.validations cobre 'email field required and non-empty', mas o fixture sintético com email='' passa sem erro (exit code 0). Validator mente sobre cobertura.",
  "scope": {
    "feature": "lembrete-rega",
    "task": "TASK-0004",
    "files": ["validators/validate_data_contract.py", "tasks/TASK-0004.yaml"]
  },
  "evidence": {
    "fixture_path": ".planning/qa/lembrete-rega/2026-06-05T14-32-08Z-a1b2/fixtures/validator-claim-data-contract-empty-email.yaml",
    "sandbox_result": {
      "exit_code": 0,
      "stdout": "...",
      "stderr": "",
      "duration_s": 0.142
    },
    "expected_exit_code": 1,
    "auditor": "validator-claim",
    "auditor_reasoning": "Validator declara em docstring 'rejects empty email' mas regex pattern não cobre string vazia."
  },
  "proposed_evolution": {
    "type": "qa-finding-validator-claim",
    "target": "validators/validate_data_contract.py",
    "summary": "Estender regex pra rejeitar email vazio + adicionar test case",
    "actionable": true
  },
  "created_at": "2026-06-05T14:33:51Z"
}
```

## Field semantics

### `id` (string, required)

Identificador único do finding dentro da run. Formato canônico:
`qa-<run-id>-<NNNN>`, onde `<run-id>` é o `run.id` do envelope
(`qa-report.md`) e `<NNNN>` é sequencial 4-dígitos atribuído pelo
synthesizer na ordem em que findings entram no report consolidado.

Formato alternativo permitido durante Phase 2/3 enquanto draft:
`<auditor-name>-<NNNN>` (ex: `validator-claim-0001`). O synthesizer
reescreve pra forma canônica `qa-<run-id>-<NNNN>` ao consolidar.

### `fingerprint` (string, required)

`sha256` hex sobre canonical-form `{type, name, normalized-description,
sorted-provenance-set}` per **Decisão 25**. Estável contra timestamps e
edits cosméticos; muda quando conteúdo ou evidência mudam — permite
re-apresentar finding quando há padrão novo, e suprimir silenciosamente
quando padrão já foi rejected pelo user.

Synthesizer usa o fingerprint pra deduplicar findings de auditores
diferentes que apontam o mesmo problema (Phase 4 dedup step). Emit
(Phase 5) consulta `rejected-fingerprints.yaml` antes de gravar em
`proposed.yaml`.

### `vector` (string enum, required)

Categoria do problema. Enum strict canônico:

- `spec-vs-spec` — contradição direta entre dois specs do mesmo nível
  (ex: BDD descreve campo X, data-contract não declara campo X).
- `impl-vs-spec` — divergência entre a implementação real (conteúdo dos
  `allowed_files` snapshotados em `snapshot/impl/`) e um spec correto (ex:
  data-contract exige validação de `email`, a impl aceita sem validar).
- `coverage` — cobertura faltante em path canônico (estado UI sem BDD,
  campo obrigatório sem validation declarada).
- `chaos` — falha exposta por fixture sintético em path não-canônico
  (input degenerado, race condition, edge numérico).
- `validator-claim` — validator passa fixture que deveria falhar (ou
  vice-versa), evidenciando que o validator mente sobre sua cobertura.

Cards via `qa-extensions` (ver `qa-extensions.md`) podem adicionar
auditores custom cujo nome vira valor de `vector` adicional —
namespace é único cross canon ∪ local, colisão é hard-fail.

### `severity` (string enum, required)

Atribuída pelo synthesizer (Phase 4) per rubric. Enum strict:

- `critical` — quebra trust gate. Sandbox-breach, validator mente,
  contradição direta entre specs do mesmo nível.
- `high` — cobertura faltante em path canônico (estado UI sem BDD,
  happy-path sem edge-case, campo obrigatório sem validation).
- `medium` — cobertura parcial (BDD cobre happy + error mas não
  loading; analytics declarado mas só disparado em parte dos
  scenarios).
- `low` — hint de melhoria não-bloqueante (nomenclatura inconsistente,
  descrição vaga).
- `info` — observação operacional (budget exhausted, fixture skipped,
  auditor degraded).

Rubric canônica vive em `docs/superpowers/specs/2026-06-05-forge-qa-design.md`
§5.4 — em conflito, o spec vence.

### `title` (string, required)

Frase curta (1 linha, idealmente ≤ 100 chars) descrevendo o problema
em termos acionáveis. Voz mentor calmo: específico, sem hedge, sem
emoji decorativo. Ex: `"validate_data_contract.py passa fixture com
email vazio"`.

### `description` (string, required)

Explicação mais longa (1-3 frases) cobrindo: o que foi observado, o
que era esperado, por que importa. Evita jargão sem contexto; quando
cita IDs (tasks, validators, screens), usa nome completo.

### `scope` (object, required)

Localização do problema no projeto:

- `feature` (string) — slug da feature dentro de `.planning/features/`.
- `screen` (string, opcional) — id da screen se aplicável.
- `task` (string, opcional) — id da task se finding é task-scoped.
- `files` (array of string, required) — paths relativos dos arquivos
  envolvidos (specs, validators, código). Lista deduplicada e
  ordenada alfabeticamente.

Pelo menos um de `screen` ou `task` é presente quando finding tem
escopo mais fino que a feature inteira. `paranoid` scope (varre tudo)
não precisa de screen/task.

### `evidence` (object, required)

Material que prova o finding. Subkeys:

- `fixture_path` (string, opcional) — path relativo do fixture
  sintético usado pra reproduzir (presente em `chaos` executável e
  `validator-claim`; ausente em `spec-vs-spec` e `coverage` puros).
- `sandbox_result` (object, opcional) — resultado da execução do
  fixture em sandbox. Presente sempre em `vector=validator-claim`;
  presente em `vector=chaos` quando o fixture é executável (chaos
  pode ser puramente descritivo). Subkeys:
  - `exit_code` (integer, required) — exit code observado.
  - `stdout` (string, required) — saída padrão capturada.
  - `stderr` (string, required) — saída de erro capturada.
  - `duration_s` (number, required) — duração em segundos da execução.
- `expected_exit_code` (integer, opcional) — exit code que o validator
  ou comando deveria ter retornado pra que o finding fosse considerado
  resolvido. Presente quando `sandbox_result` está presente.
- `auditor` (string, required) — nome do auditor que produziu o
  finding draft (ex: `validator-claim`, `chaos`, `spec-vs-spec`,
  `impl-vs-spec`, `coverage`, ou nome custom via `qa-extensions`).
- `auditor_reasoning` (string, required) — explicação do auditor
  (geralmente LLM) sobre por que o resultado observado configura
  problema. Permite revisão humana sem re-rodar o auditor.

### `proposed_evolution` (object, required)

Sugestão de fix que vira candidata a `proposed-evolution` em Phase 5
(emit). Subkeys:

- `type` (string, required) — formato canônico
  `qa-finding-{vector-slug}` (ex: `qa-finding-validator-claim`,
  `qa-finding-spec-vs-spec`, `qa-finding-coverage`,
  `qa-finding-chaos`). Pra auditores custom, slug é o nome do auditor.
- `target` (string, opcional) — path relativo do artefato a ajustar.
- `summary` (string, required) — frase curta descrevendo o fix
  sugerido. Não é o fix em si — é orientação pro user decidir em
  `forge evolve`.
- `actionable` (boolean, required) — `true` significa que o finding
  vai aparecer em `forge evolve` se `severity >= medium` e fingerprint
  não estiver em `rejected-fingerprints.yaml`. `false` significa que
  o finding é informativo (geralmente `severity = info`) e não vira
  proposta. Per **Decisão 26**, aplicação em `forge evolve` é sempre
  single-by-single — nunca batch.
- `fix_recipe` (string, opcional) — descrição mais detalhada do fix
  quando o auditor consegue ser específico (ex: regex sugerido, novo
  test case). Opcional porque nem todo auditor produz recipe; quando
  ausente, user decide o fix em `forge evolve`.

### `created_at` (string, required)

Timestamp ISO-8601 em UTC (`Z` suffix obrigatório) do momento em que
o auditor produziu o finding draft. Não muda durante synthesis — o
synthesizer preserva o timestamp original pra audit trail.

## Reuso

- **Decisão 25** fingerprint canonical-form: hash estável que sobrevive
  edits cosméticos, muda só quando conteúdo/evidência mudam. Fingerprint
  vive no nível do finding (não no report agregado).
- **Decisão 26** single-by-single em `forge evolve`: `actionable: true`
  apenas marca o finding como candidato a vir pra apresentação humana;
  não autoriza aplicação automática. User confirma um a um.
- **Decisão 27** pause/resume: findings parciais são serializados a cada
  phase end em `checkpoint.json`, permitindo `forge qa --resume` sem
  perder o que já foi auditado.

## Cross-refs

- Envelope agregado: `docs/schemas/qa-report.md`
- Card extension (auditores custom): `docs/schemas/qa-extensions.md`
- Spec fonte: `docs/superpowers/specs/2026-06-05-forge-qa-design.md` §6.2
- Rubric de severidade: spec §5.4
- Fingerprint canonical-form: `docs/design/01-decisions.md` Decisão 25
- Single-by-single em evolve: `docs/design/01-decisions.md` Decisão 26
