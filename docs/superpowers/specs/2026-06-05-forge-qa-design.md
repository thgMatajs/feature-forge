---
title: forge qa — adversarial red-team gate (13º comando)
date: 2026-06-05
status: design-approved (awaiting implementation plan)
revisita: Decisão 9 (command surface)
---

# forge qa — adversarial red-team gate

> **Tipo:** brainstorming spec (origem: `superpowers:brainstorming`).
> **Data:** 2026-06-05.
> **Status:** design aprovado pelo usuário, aguardando `superpowers:writing-plans` pra gerar plano executável.
> **Revisita:** Decisão 9 (command surface — 12 → 13 subcomandos) + nova Decisão 30 (sandbox isolation).
> **Inspiração DNA:** skills `qa-red-team` e `fix-qa-report` do projeto meoVendedor (absorvido pattern-only, sem runtime dep — Decisão 22 preservada).

## §1. Resumo executivo

`forge qa` é o 13º comando da forge — um gate adversarial multi-agente que
audita artefatos do lifecycle (feature packages, screen contracts, task
contracts, validators) com mentalidade de red-team. Diferente de `forge
verify` (cascade determinístico de validators contra artefato passado),
`forge qa` **inventa cenários hostis**, estressa validators contra
fixtures sintéticos em sandbox, e cruza spec-vs-spec procurando
contradições semânticas que escapam de checks estruturais.

Recorte v1: 4 attack vectors universais (spec-vs-spec, chaos, coverage,
validator-claim), 4 scope targets (feature, screen, task, cross-feature
paranoid), trigger híbrido (manual + opt-in auto pós feature-done), fix
loop ortogonal via `forge evolve`, sandbox sempre via subprocess isolado
em CWD dedicado.

Caso de uso canônico (verbatim do user no brainstorm): "rodar no final
da implementação OU a qualquer momento contra feature/tela/fluxo
específico".

## §2. Motivação

`forge verify` já cobre a cascade de 15 validators contra artefatos
declarados. Por que adicionar mais uma camada?

A diferença é **fundamental, não incremental**:

| Eixo | `forge verify` | `forge qa` |
|---|---|---|
| Mentalidade | Determinística — "este artefato passa nas regras?" | Adversarial — "que cenário hostil quebraria este artefato?" |
| Input | Artefato passado pelo user (feature slug, task id) | Mesmo input + auditores que **inventam** cenários derivados |
| Execução | Single-pass cascade fail-fast | Multi-fase com agentes LLM raciocinando + sandbox subprocess |
| Falha típica detectada | Schema inválido, campo obrigatório faltando, contract incoerente | Spec coerente isoladamente mas contradiz outra spec; validator existe mas falha em fixture sintético; cobertura BDD não-exaustiva |
| Verdict | block / warning / pass | BLOCK / FLAG / PASS com severidade modulada |
| Output | Falha textual + 3-caminhos | QA-REPORT.json estruturado + proposed-evolutions delta |

`forge qa` é o lugar onde "este plano está coerente?" deixa de ser
verificação estrutural e vira interrogatório. Como o user falou: existem
bugs que só aparecem quando você tenta quebrar de propósito.

A inspiração arquitetural vem das skills `qa-red-team` e `fix-qa-report`
do meoVendedor, mas com diferença crítica: aquelas skills auditam código
de app rodando. `forge qa` não roda código de produto — audita os
**artefatos do lifecycle** (specs, contracts, validators, templates).
DNA absorvido, runtime preservado (Decisão 22).

## §3. Decisões load-bearing fechadas no brainstorm

7 decisões — 6 do brainstorm + 1 nova (sandbox isolation) que emergiu
durante a consolidação do design.

| # | Decisão | Escolha | Rationale curto |
|---|---|---|---|
| D1 | Command surface | 13º comando `forge qa` (revisita Decisão 9) | Verbo novo é semanticamente distinto de verify/doctor/evolve; encaixar em menu interno desses 3 dilui semântica e quebra discoverability. Revisita formal documentada (§13). |
| D2 | Attack vectors | 4 universais: spec-vs-spec, chaos, coverage, validator-claim | Cobre o espaço de "contradição entre specs", "validator pode mentir", "cenário hostil que ninguém pensou", "BDD não cobre estado X". Cards podem estender via `qa-extensions` (§8). |
| D3 | Scope targets | feature, screen, task, cross-feature paranoid | Mesmo recorte do `forge verify` + um modo paranoid que cruza N features (pesado, opt-in). User mantém controle granular do que estressar. |
| D4 | Trigger | hybrid: manual + opt-in auto via `qa.auto-run-on-feature-done` | Manual sempre disponível. Auto-run no retrospective é opt-in (default false) — projetos heavy-QA ligam, projetos lean ficam manual. |
| D5 | Fix loop | findings → proposed-evolutions → `forge evolve` (ortogonal) | Não inventar novo flow de aplicar findings. Reusa o gate humano de `evolve` (Decisão 26, single-by-single). |
| D6 | Chaos depth | sandbox sempre — subprocess validators contra fixtures sintéticos em CWD isolado | Auditores LLM raciocinam; quando precisa testar validator concretamente, dispara subprocess em CWD dedicado com fixture sintético gerado. Nunca toca o projeto real. |
| D7 | Sandbox isolation (= futura Decisão 30) | CWD do subprocess validator = `.planning/qa/<run_id>/fixtures/`; writes fora falham hard | Isolation guarantee contra contaminação de produção. Subprocess hardened: `cwd` setado, `os.chdir` rejeitado, paths absolutos fora do sandbox raise `SandboxBreachError`. |

D7 é nova — emergiu durante consolidação do spec. Brainstorm decidiu "sandbox sempre"; D7 formaliza o **como** do sandbox de modo que não vire afterthought na implementação.

## §4. Arquitetura macro

`forge qa` é pipeline em 6 fases sequenciais, cada uma com responsável claro.

```
forge qa {scope-args}
│
├─ Phase 0 — Ingest                                   [Python engine]
│   Resolve scope, valida acesso aos artefatos,
│   cria .planning/qa/<feature-slug>/<run_id>/ tree,
│   snapshot do estado pra reproducibility.
│
├─ Phase 1 — Static auditors (universal)              [Claude Code dispatch]
│   Lê artefatos resolvidos. Dois auditores LLM:
│     • spec-vs-spec       — cruza contratos procurando contradição
│     • coverage           — checa exaustividade de BDD/screens vs estados
│   Output: findings parciais (status=draft) em qa-report.json.
│
├─ Phase 2 — Generative auditors (universal)          [Claude Code dispatch]
│   Inventam cenários hostis. Dois auditores LLM:
│     • chaos              — gera fixtures sintéticos hostis (null, empty, malformed, race, overflow)
│     • validator-claim    — para cada validator referenciado, gera fixture que deveria falhar
│   Output: findings draft + fixture files em <run_id>/fixtures/.
│
├─ Phase 3 — Sandbox execution                        [Python engine + subprocess]
│   Para cada fixture gerado em Phase 2 que precisa execução real:
│   roda validator referenciado via subprocess(cwd=sandbox), captura
│   exit code + stdout/stderr, anexa ao finding. Budget global
│   timeout (default 60s); por-validator timeout (default 15s).
│   Output: findings com evidência sandbox (path do fixture, exit code, output).
│
├─ Phase 4 — Synthesis                                [Claude Code dispatch]
│   Auditor "qa-synthesizer" lê todos os findings draft,
│   dedup via Decisão 25 fingerprint, atribui severidade
│   per finding (rubric §5.4), calcula verdict global
│   (BLOCK/FLAG/PASS via verdict logic §5.4).
│   Output: qa-report.json final + verdict.
│
└─ Phase 5 — Emit                                     [Python engine]
    Filtra findings actionable (severity >= medium),
    dedup contra rejected-fingerprints.yaml de forge evolve,
    escreve delta em proposed-evolutions.yaml com type=qa-finding-{slug}.
    Imprime relatório cinemático ao user (§10) + retorna exit code.
```

### §4.1 Princípios load-bearing (4)

1. **Engine determinístico, agentes raciocinam.** Phase 0/3/5 são Python — scope resolution, subprocess, IO em disco. Phase 1/2/4 são LLM dispatch — onde mentalidade adversarial vive. Mistura quebra reproducibility ou quebra criatividade; mantém separado.

2. **Cards estendem, core garante baseline.** Os 4 attack vectors de D2 são **garantidos pelo core**. Cards podem adicionar auditores extras via `qa-extensions` (§8), mas nunca substituir os 4 baseline. Projetos sem cards QA-aware ainda têm cobertura mínima.

3. **Reuso da surface existente** (mandamento #3 reuse).
   - `forge evolve` já é o endpoint de fix loop (D5) — reusa o gate humano single-by-single da Decisão 26.
   - `engine/verify.py` já tem o pattern de subprocess de validators — Phase 3 reusa, não reinventa.
   - Decisão 25 fingerprint canonical-form — Phase 5 emit usa pra dedup contra rejected-fingerprints.
   - Decisão 27 pause/abort — Ctrl+C no meio de uma run salva checkpoint em `.planning/qa/<run_id>/checkpoint.json` (deferred), resume automático.

4. **Sandbox isolado** (D7).
   - Subprocess CWD = `.planning/qa/<run_id>/fixtures/`.
   - Writes pra paths absolutos fora do sandbox → `SandboxBreachError` (Python wrapper em volta do subprocess).
   - `os.chdir` rejeitado via preload guard.
   - Budget global: default 60s por run, configurável em `qa.sandbox-budget-seconds-total`.

## §5. Phase contracts (data flow detalhado)

### §5.0 Phase 0 — Ingest

**Inputs:**
- Argumentos posicionais conversacionais (scope target — feature slug, screen id, task id, ou `paranoid` keyword).
- `.claude/workflow-config.yaml` (lê `qa:` section — §9).
- Artefatos do scope resolvido:
  - feature scope → `.claude/memory/L1/<slug>/`, `docs/feature-implementation-workflow/features/<slug>/` (ou `non-product/<slug>/`).
  - screen scope → screen contract específico dentro de uma feature.
  - task scope → `tasks/TASK-NNNN.yaml`.
  - paranoid scope → todas features `state ∈ {planning, implementing, blocked-on-external, done}` (deferred/aborted excluídas).

**Ações:**
1. Resolve scope conversacionalmente (sem flag — Decisão 10). Se ambiguity, dispara 3-caminhos.
2. Valida que artefatos existem e são legíveis.
3. Gera `run_id` (timestamp UTC ISO + sufixo aleatório curto — ex: `2026-06-05T14-32-08Z-a1b2`).
4. Cria árvore: `.planning/qa/<feature-slug>/<run_id>/` com subdirs `fixtures/`, `findings/`, `audit/`.
5. Snapshot dos artefatos resolvidos em `<run_id>/snapshot/` (hardlinks ou copy — preserva reproducibility se o user editar durante a run).
6. Inicializa `qa-report.json` com header (scope, run_id, started_at, config snapshot).

**Outputs:**
- `.planning/qa/<feature-slug>/<run_id>/` populado.
- `qa-report.json` esqueleto (verdict=pending).

**Failure mode:**
- Scope ambíguo → 3-caminhos (interactive).
- Artefatos faltando → hard fail com mensagem clara (3-caminhos: rodar `forge plan` pra completar, ajustar scope, abortar).
- `.planning/qa/` sem permissão de write → hard fail com path explícito.

### §5.1 Phase 1 — Static auditors

Dois auditores universais. Cada um é um sub-agent LLM dispatched.

| Auditor | Lê | Escreve | Procura |
|---|---|---|---|
| `spec-vs-spec` | Todos os contracts do scope (data-contract-spec, navigation-spec, ui-state-spec, analytics-spec, bdd.json, screen-analysis.md) | `findings/spec-vs-spec.json` (lista de findings draft) | Campo em data-contract que BDD não menciona; rota em navigation-spec sem screen correspondente; evento em analytics-spec não disparado em nenhum scenario BDD; ui-state com transição que screen-analysis não desenha. Contradição direta entre 2+ specs. |
| `coverage` | screen-analysis.md + bdd.json + ui-state-spec.yaml | `findings/coverage.json` | Estados em ui-state-spec sem BDD scenario; screens em screen-analysis sem fluxo em BDD; transições mencionadas no analysis sem cobertura de teste; happy-path coberto mas edge-cases empty/error/loading vazios. |

**Failure mode:** auditor LLM retorna JSON inválido → 1 retry com reprompt; segunda falha → finding `qa-auditor-malformed` severity=high, run continua.

### §5.2 Phase 2 — Generative auditors

Dois auditores que **geram fixtures hostis** além de findings.

| Auditor | Lê | Escreve | Procura |
|---|---|---|---|
| `chaos` | Contracts (data, navigation, analytics, ui-state) | `findings/chaos.json` + `fixtures/chaos-*.yaml` | Cenários hostis derivados de cada contract: null em campo obrigatório, empty string em enum, payload malformado, ordem invertida em sequência, race condition descrita verbalmente. Gera fixture sintético que reproduz o cenário. |
| `validator-claim` | Lista de validators referenciados nos task contracts | `findings/validator-claim.json` + `fixtures/validator-claim-*.{yaml,py,kt,swift}` | Para cada validator declarado: lê o validator, raciocina sobre o que ele claim cobrir, gera fixture que **deveria falhar nesse validator**. Se o validator passa o fixture sintético hostil = validator está mentindo sobre cobertura. |

**Exemplos canônicos de fixtures hostis que `chaos` deve produzir:**
- Em `data-contract-spec` com campo `email: string`: fixture com `email: ""`, `email: null`, `email: "a@"`, `email: <string de 10KB>`.
- Em `navigation-spec` com rota `/reminder/{id}`: fixture com `id: "../../etc/passwd"`, `id: ""`, `id: <UUID inválido>`.
- Em `analytics-spec` com evento `tap_save`: fixture com 1000 disparos em 1s (rate-flood), disparo sem campos obrigatórios, disparo com payload null.
- Em `ui-state-spec` com transição `loading → success`: fixture com `loading → loading` (idempotente), `success → loading` (regressão), `loading` por 60s sem transição (timeout).

**Failure mode:** mesmo de §5.1 — JSON inválido = retry once + finding.

### §5.3 Phase 3 — Sandbox execution

Loop subprocess pra cada fixture gerado em Phase 2 que precisa execução real (validator-claim sempre executa; chaos executa quando o finding inclui hint `executable: true`).

**Pseudocódigo:**

```python
# engine/qa/sandbox.py

class SandboxBreachError(RuntimeError):
    """Validator subprocess tentou escapar do CWD do sandbox."""

def run_sandbox(run_dir: Path, fixtures: list[Fixture], budget_total_s: float) -> list[SandboxResult]:
    """
    Roda validators contra fixtures sintéticos em CWD isolado.

    Hardening (D7):
      - subprocess.cwd = run_dir / "fixtures"
      - Paths absolutos no fixture verificados antes do dispatch
      - os.chdir guarda via PYTHONSTARTUP preload
      - Writes fora do sandbox → SandboxBreachError

    Budget:
      - total: budget_total_s (default 60s do qa.sandbox-budget-seconds-total)
      - per-validator: qa.agent-timeout-seconds (default 15s)
      - quando total estoura: marca fixtures restantes como skipped + finding qa-budget-exhausted severity=info
    """
    sandbox_cwd = run_dir / "fixtures"
    sandbox_cwd.mkdir(parents=True, exist_ok=True)

    results = []
    started = time.monotonic()
    per_validator_timeout = config.get("qa.agent-timeout-seconds", 15.0)

    for fixture in fixtures:
        elapsed = time.monotonic() - started
        if elapsed >= budget_total_s:
            results.append(SandboxResult(fixture=fixture, status="skipped-budget"))
            continue

        remaining = min(per_validator_timeout, budget_total_s - elapsed)

        # F-1: validators forge reais usam o contrato argparse
        # `--project-root <tree>` (escaneiam a árvore), NÃO um input
        # posicional. Quando a fixture declara `tree_rel_path`, o sandbox monta
        # um mini project-tree (`sandbox_cwd/<fixture.name>`) com o arquivo do
        # contra-exemplo em `<mini-tree>/<tree_rel_path>` e invoca
        # `[python, validator, "--project-root", <mini-tree>]`. Sem isso, o
        # validator argparse rejeitaria o input posicional com exit 2 e o vetor
        # validator-claim ficaria INERTE. `tree_rel_path=None` mantém a
        # invocação posicional legada (compat com chaos/inputs estruturados).
        if fixture.tree_rel_path is not None:
            mini_tree = sandbox_cwd / fixture.name
            cmd = [sys.executable, fixture.validator_path, "--project-root", mini_tree]
        else:
            cmd = [sys.executable, fixture.validator_path, fixture.input_path]

        try:
            proc = subprocess.run(
                cmd,
                cwd=sandbox_cwd,
                capture_output=True,
                text=True,
                timeout=remaining,
                env=_hardened_env(),     # PYTHONSTARTUP=chdir-guard
            )
            results.append(SandboxResult(
                fixture=fixture,
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                duration_s=proc.elapsed,
            ))
        except subprocess.TimeoutExpired:
            results.append(SandboxResult(fixture=fixture, status="timeout"))
        except SandboxBreachError as e:
            results.append(SandboxResult(fixture=fixture, status="sandbox-breach", error=str(e)))

    return results
```

**Pattern reusa `engine/verify.py`** (mandamento #3) — esse já dispara validators via subprocess; o delta é o CWD hardening + budget tracking.

**Contrato de `Fixture` + invocação `--project-root` (F-1):** o `Fixture`
dataclass carrega `name`, `input_path`, `validator_path` e — pós-F-1 — o campo
opcional `tree_rel_path: str | None`. Validators forge reais (ex.:
`validators/validate_task_contract.py`, `cards/*/validators/check-no-suppress.py`)
expõem o contrato canônico `python3 <validator> --project-root <path>
[--scope <kind> --id <target>]`, com `cwd=project_root`: eles **escaneiam a
árvore**, não leem um input posicional. Passar a fixture como argumento
posicional (`[python, validator, input_path]`) faz o argparse sair com exit 2
sem nunca ler o arquivo — o vetor validator-claim fica INERTE. Por isso, quando
`tree_rel_path` está setado, o sandbox monta um mini project-tree em
`run_dir/fixtures/<name>/`, materializa o arquivo do contra-exemplo em
`<mini-tree>/<tree_rel_path>`, e invoca o validator com
`--project-root <mini-tree>`. O validator escaneia o tree e pega a fixture
(exit 1 = pegou; exit 0 = validator mente). `tree_rel_path=None` mantém a
invocação posicional legada (chaos / inputs estruturados).

**Hardening preservado (D7 / Decisão 30/31):** o containment check
(`_validate_paths_inside_sandbox`) passa a cobrir TAMBÉM o mini-tree e o arquivo
materializado — um `tree_rel_path` com traversal (`../../escape.kt`) resolve
fora do sandbox e dispara `SandboxBreachError` antes de qualquer subprocess. O
guard fica MAIS estrito, nunca afrouxado. CWD isolado (`run_dir/fixtures`),
chdir/fchdir guard via `sitecustomize`, env allowlist (sem PYTHONPATH herdado) e
budget/timeout permanecem intactos sob o novo contrato.

**Failure mode:** breach → finding `qa-sandbox-breach` severity=critical (sempre BLOCK), porque indica problema sério no validator dispatched. Timeout = finding severity=medium (budget pode ser ajustado).

### §5.4 Phase 4 — Synthesis

Auditor `qa-synthesizer` (Claude Code dispatch) lê todos os findings draft de Phase 1+2+3 e produz o report final.

**Ações:**
1. Lê `findings/*.json` (4 arquivos universais + N extensão).
2. Dedup via Decisão 25 fingerprint canonical-form. Findings com mesmo fingerprint colapsam em um (evidência adicional anotada).
3. Atribui severidade per finding via rubric.
4. Calcula verdict global.
5. Grava `qa-report.json` final.

**Rubric de severidade:**

| Severity | Critério |
|---|---|
| `critical` | Quebra trust gate. Ex: sandbox-breach; validator passou fixture que deveria falhar (validator mente); spec-vs-spec contradição direta (ex: BDD describes campo X, data-contract não tem campo X). |
| `high` | Cobertura faltante em path canônico. Ex: estado UI sem BDD; happy-path BDD sem edge-case error; campo obrigatório em data-contract sem validation declarada. |
| `medium` | Cobertura parcial. Ex: BDD cobre happy + error mas não loading; analytics event declarado mas só disparado em 50% dos scenarios. |
| `low` | Hint de melhoria não bloqueante. Ex: nomenclatura inconsistente entre 2 specs; descrição vaga em scenario BDD. |
| `info` | Observação operacional. Ex: budget exhausted, fixture skipped, auditor degraded. |

**Verdict logic:**

```
BLOCK if (count(critical) >= 1) or (count(high) >= 3)
FLAG  if (count(high) in {1, 2}) or (count(medium) >= 3)
PASS  otherwise
```

Verdict é informativo — NÃO bloqueia retrospective, NÃO bloqueia commit (alinha Decisão 5: code review final out-of-scope). Bloquear seria forge invadindo o papel de code review humano.

**Output:** `qa-report.json` com schema canônico (§6.1) + verdict + summary cinemático.

### §5.5 Phase 5 — Emit

Algorithm:

1. Carrega `qa-report.json` final.
2. Filtra findings com `severity >= medium` (low e info não viram proposed-evolution).
3. Para cada finding actionable:
   a. Calcula fingerprint canonical-form (Decisão 25).
   b. Lê `.claude/memory/L1/proposed-evolutions/rejected-fingerprints.yaml`.
   c. Se fingerprint em rejected → skip silencioso.
   d. Se fingerprint não em rejected → escreve entrada em `.claude/memory/L1/proposed-evolutions/proposed.yaml` com `type: qa-finding-{vector-slug}` e payload completo do finding.
4. Imprime relatório cinemático ao user (§10 Cena 8).
5. Retorna exit code:
   - `0` se verdict ∈ {PASS, FLAG}
   - `1` + `[FORGE-ERR:QA-BLOCK]` em stderr se verdict == BLOCK (via
     `fail_with_tag(ERR_QA_BLOCK)`; ver `docs/design/06-command-surface.md`).
     **Superseded:** o `8` original (alinhado ao Step 7.5 do Gap 5) foi
     trocado pela convenção `fail_with_tag` em C3 EXIT-2-COLLISION / W2 — o
     `8` colidia com o exit code reservado de outro contrato.

**Atomic write:** `proposed.yaml` é escrito via temp file + rename pra evitar corrupção se Ctrl+C mid-write.

**Failure mode:** disk full mid-write → finding loss prevented por temp file pattern; user vê warning + sugestão de cleanup.

## §6. Schemas (novos)

### §6.1 `docs/schemas/qa-report.md` — a criar

Schema canônico do `qa-report.json` gerado por Phase 4.

```yaml
schema_version: 1

run:
  id: "2026-06-05T14-32-08Z-a1b2"
  scope:
    type: "feature" | "screen" | "task" | "paranoid"
    target: "<slug ou id>"
  config_snapshot: {...}   # qa: section da workflow-config no momento da run
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
  - <qa-finding schema §6.2>
  - ...
```

### §6.2 `docs/schemas/qa-finding.md` — a criar

Shape JSON completo de um finding individual:

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

### §6.3 `docs/schemas/qa-extensions.md` — a criar

Schema do campo aditivo `qa-extensions:` em `card.yaml`:

```yaml
# Aditivo top-level em card.yaml (schema-version permanece 1)
qa-extensions:
  auditors:
    - name: "visual-fidelity"           # único cross canon ∪ local
      phase: "static" | "generative"    # restrito aos 2 grupos
      contributes:
        agents:
          - "auditor-visual-fidelity.md"  # path relativo ao card
        config-defaults:
          enabled: true
      requires:
        - "screens-defined"   # capability que precisa estar ativa
```

**Regras de validação** (enforced por `validate_qa_extensions.py` — §7):
- `name` único cross canon ∪ local (colisão = hard fail; mesma policy do Gap 5 card overlay).
- `phase ∈ {"static", "generative"}` (Phase 3 sandbox e Phase 4 synthesis são reservados ao core).
- Cada `contributes.agents` referenciado deve existir em `agent-contributions/`.
- `requires` capabilities devem estar declaradas no catálogo (canon ∪ local overlay).

**Compatibilidade com Gap 5 local overlay:** cards locais podem declarar `qa-extensions` exatamente como canônicos. Colisão de nome de auditor entre canon e local segue a mesma política de Gap 5: hard fail no loader, sem merge silencioso.

### §6.4 `docs/schemas/workflow-config.md` — editar (adicionar section `qa:`)

```yaml
qa:
  enabled: true                              # default true; false desabilita o comando inteiro
  auto-run-on-feature-done: false            # default false; true dispara qa no retrospective
  sandbox-budget-seconds-total: 60           # budget global por run
  agent-timeout-seconds: 15                  # timeout per-validator dentro do sandbox
  scope-defaults:
    paranoid-max-features: 10                # cap pra paranoid scope (evita explosão)
  extensions:
    disabled: []                             # lista de auditor names desabilitados (canon ou local)
  retention-days: 14                         # .planning/qa/<run_id>/ retidos por N dias (idem Decisão 24 .bak)
```

## §7. File layout

### §7.1 Novos arquivos

**Engine (Python):**
- `engine/qa.py` — dispatcher do comando (parsing conversacional, fan-out pra phase handlers).
- `engine/qa/ingest.py` — Phase 0.
- `engine/qa/sandbox.py` — Phase 3 (subprocess hardened).
- `engine/qa/synthesis.py` — Phase 4 (dedup + verdict logic).
- `engine/qa/emit.py` — Phase 5 (proposed-evolutions integration).
- `engine/qa/scope.py` — resolução de scope + run_id generation.

**Agents (prompts):**
- `agents/qa-conductor.md` — orchestrator das 6 phases dentro de um único `forge qa` invocation.
- `agents/qa-auditor-spec-vs-spec.md` — Phase 1.
- `agents/qa-auditor-coverage.md` — Phase 1.
- `agents/qa-auditor-chaos.md` — Phase 2.
- `agents/qa-auditor-validator-claim.md` — Phase 2.
- `agents/qa-synthesizer.md` — Phase 4.

**Validators (overlay-aware via §6.3):**
- `validators/validate_qa_report.py` — valida `qa-report.json` contra schema §6.1.
- `validators/validate_qa_finding.py` — valida shape individual de finding (§6.2).
- `validators/validate_qa_extensions.py` — valida campo `qa-extensions:` em cards.

**Templates:**
- `templates/qa-report.template.json` — esqueleto pra Phase 0 inicializar.
- `templates/qa-finding.template.json` — shape pra auditores LLM preencherem.
- `templates/qa-fixture-chaos.template.yaml` — shape pra chaos auditor gerar fixtures.
- `templates/qa-fixture-validator-claim.template.{yaml,py,kt,swift}` — shapes pra validator-claim auditor.
- `templates/agent-contributions/qa-auditor.template.md` — shape pra cards que estendem qa via `qa-extensions`.

**Schemas:**
- `docs/schemas/qa-report.md` (§6.1).
- `docs/schemas/qa-finding.md` (§6.2).
- `docs/schemas/qa-extensions.md` (§6.3).

**UX:**
- `docs/ux/forge-qa-roteiro.md` — roteiro cinemático completo (§10 é resumo).

### §7.2 Edits em arquivos existentes

| Arquivo | O que muda |
|---|---|
| `docs/design/01-decisions.md` | Append linha 29 (Revisita Decisão 9) + linha 30 (Sandbox isolation). Linha 9 histórica preservada (append-only). |
| `docs/design/06-command-surface.md` | Header `Locked at 12` → `Locked at 13 (após Revisita Decisão 9 em 2026-06-05)`. Adiciona row 13 (`forge qa`). Adiciona 3 linhas no mapeamento (rodar QA, ativar/desativar via reconfigure, aplicar findings via evolve). |
| `docs/design/07-discipline.md` | Adiciona §11 — "QA verdict não-bloqueante" (alinha §1 3-caminhos + Decisão 5 out-of-scope code review final). |
| `docs/schemas/workflow-config.md` | Adiciona section `qa:` completa (§6.4). |
| `docs/schemas/card.md` | Adiciona section curta "qa-extensions field" linkando §6.3. |
| `engine/cli.py` | Registra dispatcher do verbo `qa`. |
| `engine/verify.py` | Sem mudança — `forge qa` reusa o pattern de subprocess, mas não modifica verify. |
| `engine/cards/loader.py` | Validate de `qa-extensions:` no card.yaml; cross-check de colisão de auditor name canon ∪ local. |
| `engine/implement.py` | Hook no retrospective phase (Phase 6) — se `qa.auto-run-on-feature-done: true`, dispara `forge qa` pre-retrospective (§12). |
| `engine/reconfigure.py` | Adiciona menu `[ ] qa` com 3 opções: ativar/desativar comando, ligar/desligar auto-run, ajustar budgets. |
| `engine/init.py` | Adiciona Step QA (após Step 7.5 do Gap 5) — pergunta se time quer QA ativo + auto-run on/off. |
| `agents/retrospective-agent.md` | Doc-sync: menciona que QA pode rodar antes do retrospective se opt-in. |
| `pyproject.toml` | Sem mudança — markers `integration` e `e2e` existentes cobrem os testes novos. |
| `bin/forge` | Adiciona `qa` ao dispatcher bash. |
| `CHANGELOG.md` | `### Added` — forge qa (13º comando) + cards qa-extensions + 3 schemas novos. `### Changed (load-bearing)` — "Revisita decisão 9: 12 → 13 subcomandos — adiciona forge qa". |
| `docs/design/08-session-handoff.md` | Última atualização + Estado + linha Conhecidos limites (se aplicável). |
| `README.md §Stats` | 12 comandos → 13 comandos; mention breve ao qa. |

### §7.3 Runtime state

```
.planning/qa/
├── <feature-slug>/
│   ├── <run-id>/
│   │   ├── qa-report.json                    (Phase 4 output)
│   │   ├── checkpoint.json                   (Decisão 27 pause state)
│   │   ├── snapshot/                         (Phase 0 — artefatos congelados pra reproducibility)
│   │   │   ├── feature-prd.md
│   │   │   ├── tech-spec.md
│   │   │   ├── tasks/
│   │   │   └── ...
│   │   ├── fixtures/                         (Phase 2 + sandbox CWD em Phase 3)
│   │   │   ├── chaos-empty-email.yaml
│   │   │   ├── chaos-rate-flood-analytics.yaml
│   │   │   ├── validator-claim-data-contract-empty.yaml
│   │   │   └── ...
│   │   ├── findings/                         (Phase 1+2+3 outputs, antes do synthesis)
│   │   │   ├── spec-vs-spec.json
│   │   │   ├── coverage.json
│   │   │   ├── chaos.json
│   │   │   └── validator-claim.json
│   │   └── audit/                            (logs + agent transcripts)
│   │       ├── phase-1-spec-vs-spec.log
│   │       ├── phase-2-chaos.log
│   │       └── ...
│   └── ...
└── ...
```

Retenção (config `qa.retention-days`, default 14): `forge doctor` reporta runs overdue como warning. Limpeza via menu interativo em `forge reconfigure` (pattern idêntico ao `.bak` de Decisão 24).

### §7.4 Volume estimado

| Componente | Quantidade |
|---|---|
| Agents novos | ~6 (1 conductor + 4 auditores + 1 synthesizer) |
| Validators novos | ~3 (qa-report, qa-finding, qa-extensions) |
| Templates novos | ~5 (qa-report, qa-finding, qa-fixture-chaos, qa-fixture-validator-claim, agent-contributions qa-auditor) |
| Schemas novos | ~3 (qa-report.md, qa-finding.md, qa-extensions.md) |
| Engine modules novos | ~6 (qa.py + qa/ subpackage: ingest, sandbox, synthesis, emit, scope) |
| Engine modules editados | ~4 (cli, cards/loader, implement, reconfigure, init — conta init como edit pesado) |
| Testes novos | ~60-80 (distribuição em §15) |
| Documentação | ~3 docs design edits + 1 novo roteiro UX + CHANGELOG/handoff/README |

## §8. Card extension model (`qa-extensions`)

Campo aditivo `qa-extensions:` top-level no `card.yaml` (schema-version permanece 1 — adição aditiva, mesma política do `legacy-marker` de Gap 5).

### §8.1 Shape YAML completo (exemplo)

```yaml
# cards/screens-defined/card.yaml — exemplo de card canon estendido com qa
# ... (campos identity, provides, requires, contributes etc — já existentes)

qa-extensions:
  auditors:
    - name: "screen-state-coverage"
      phase: "static"
      contributes:
        agents:
          - "agent-contributions/qa-auditor-screen-state-coverage.md"
        config-defaults:
          enabled: true
          strictness: "strict"
      requires:
        - "screens-defined"
    - name: "screen-visual-fidelity"
      phase: "generative"
      contributes:
        agents:
          - "agent-contributions/qa-auditor-screen-visual-fidelity.md"
        config-defaults:
          enabled: false       # opt-in (DOM/snapshot pode ser pesado)
      requires:
        - "screens-defined"
```

### §8.2 Regras de validação (`validate_qa_extensions.py`)

1. **Nome único cross canon ∪ local.** Auditor `screen-state-coverage` declarado em card canon + outro card local com mesmo nome = hard fail no loader. Mesma policy de Gap 5 (Decisão 28).
2. **`phase ∈ {"static", "generative"}`.** Phase 0/3/4/5 são core-only (engine determinístico, dispatch fixo). Cards estendem só onde mentalidade adversarial vive — static (Phase 1) e generative (Phase 2).
3. **Agents referenciados existem.** Cada path em `contributes.agents` deve existir relativo ao card (`<card-dir>/agent-contributions/<file>.md`).
4. **`requires` capabilities estão no catálogo.** Mesma checagem de capability-labels canon ∪ local overlay (validators _common.load_catalog reusado, mandamento #3).
5. **`extensions.disabled` na workflow-config** desativa auditor por nome — útil pra times que querem QA mas com subset reduzido.

### §8.3 Compatibilidade com Gap 5

Cards locais (`.claude/cards/local/<name>/card.yaml`) podem declarar `qa-extensions:` exatamente como cards canon. Cascade: canon primeiro, local segundo — colisão de auditor name = hard fail (Decisão 28 Approach A).

Validate `validate_qa_extensions.py` é overlay-aware desde o início — segue o pattern de `validate_card_yaml.py` e `validate_capability_labels.py` (overlay-aware desde Gap 5, doc-sync §2 de 07-discipline).

## §9. Workflow-config schema additions

Section `qa:` completa (referenciada em §6.4):

```yaml
qa:
  enabled: true                                # default true. false desabilita o verbo
  auto-run-on-feature-done: false              # default false. true dispara qa pré-retrospective
  sandbox-budget-seconds-total: 60             # budget global; menor = QA mais rápido + menos cobertura
  agent-timeout-seconds: 15                    # per-validator subprocess timeout
  scope-defaults:
    paranoid-max-features: 10                  # cap em paranoid scope; default 10 evita explosão
  extensions:
    disabled: []                               # lista de auditor names desativados (canon ou local)
  retention-days: 14                           # .planning/qa/<run-id>/ retidos; doctor reporta overdue
```

**Onde o user configura:**

1. **`forge init` Step QA (novo).** Após Step 7.5 do Gap 5 (orphan signals), antes de materializar plan: pergunta interativa "Ativar QA red-team gate? [s/N]" e se sim, "Auto-run no feature-done? [s/N]". Defaults: enabled=true, auto-run=false.

2. **`forge reconfigure` menu `[ ] qa` (novo).** Opções:
   - 1. Ativar/desativar comando inteiro (toggle `qa.enabled`).
   - 2. Ligar/desligar auto-run on feature-done (toggle `qa.auto-run-on-feature-done`).
   - 3. Ajustar budgets (sandbox + per-validator).
   - 4. Listar/desativar auditores (mostra canon ∪ local com toggle).
   - 5. Ajustar retention.
   - 0. Voltar.

3. **`forge doctor` checa coerência.** Warning se `qa.enabled: false` AND `qa.auto-run-on-feature-done: true` (config inconsistente — auto-run nunca dispara).

## §10. UX cinemática (resumo do roteiro)

Roteiro completo virá em `docs/ux/forge-qa-roteiro.md` na fase de implementação. Aqui o resumo das 8 cenas + 3 exemplos de output canônico.

| Cena | O que mostra |
|---|---|
| 1 | Invocação + scope resolution conversacional (3-caminhos se ambíguo) |
| 2 | Phase 0 cinemático — snapshot da árvore criada + summary do scope |
| 3 | Phase 1 static auditors rodando — progress bar + findings count incremental |
| 4 | Phase 2 generative auditors — fixture generation count + sample fixture render |
| 5 | Phase 3 sandbox transitivo — validator-by-validator com exit code + duration |
| 6 | Sandbox loop output (canônico — render abaixo) |
| 7 | Phase 4 synthesis + verdict block (canônico — render abaixo) |
| 8 | Phase 5 emit handoff (canônico — render abaixo) |

### §10.1 Cena 6 — Sandbox loop output

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

### §10.2 Cena 7 — Verdict block

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

### §10.3 Cena 8 — Emit handoff

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

## §11. Persona stacking

Persona Decisão 2 (mentor calmo) **+ overlay "staff QA / red-team lead"** ativo durante a execução de `forge qa`.

### §11.1 Texto exato do overlay

Os 4 bullets que vão no preamble dos auditores Phase 1/2/4:

- **Cética por default.** "Como esse spec quebra?" antes de "esse spec funciona?". Não assume boa-fé do artefato.
- **Criativa em hipóteses.** Inventa cenário hostil que ninguém pensou. Null, empty, race, regressão, traversal, overflow, ordem invertida — combinatória completa, não só happy + erro óbvio.
- **Estrita em verdict.** Severidade é calibrada pelo dano potencial, não pela facilidade de fix. Validator que mente = critical, mesmo se o fix é regex de 5 caracteres.
- **Mas mentor no fraseado.** O finding descreve o problema com clareza pedagógica. Sem voz corporativa, sem dramatização, sem emoji decorativo. "Validator passa fixture que deveria falhar" — não "ALERTA CRÍTICO 🚨".

### §11.2 Onde declarar

Texto do overlay vai no preamble de `agents/qa-conductor.md` e é **herdado por** todos os sub-agents:
- `agents/qa-auditor-spec-vs-spec.md`
- `agents/qa-auditor-coverage.md`
- `agents/qa-auditor-chaos.md`
- `agents/qa-auditor-validator-claim.md`
- `agents/qa-synthesizer.md`

Cards que estendem QA via `qa-extensions` herdam o overlay automaticamente — pattern é declarar no agent-contribution o link `# Inherits qa-conductor overlay (mentor calmo + staff QA red-team)` no header.

## §12. Trigger integration — hook em `forge implement`

Quando `qa.auto-run-on-feature-done: true`, `engine/implement.py` no retrospective phase (Phase 6 do execution conductor) dispara `forge qa` **antes** do retrospective-agent rodar.

### §12.1 Pseudocódigo do hook

```python
# engine/implement.py — Phase 6 retrospective hook

def _maybe_run_qa_pre_retrospective(feature_slug: str, ctx: ImplementContext) -> None:
    """
    Se qa.auto-run-on-feature-done: true, dispara forge qa scope=feature
    antes do retrospective-agent. Verdict NÃO bloqueia retrospective —
    findings são apenas mais um insumo pro retrospective-agent considerar.
    """
    config = ctx.workflow_config
    if not config.get("qa.enabled", True):
        return
    if not config.get("qa.auto-run-on-feature-done", False):
        return

    # 3-caminhos antes de rodar (user pode pular nessa run específica)
    choice = ask_user_three_paths(
        prompt=(
            "qa.auto-run-on-feature-done está ativo. Rodar forge qa "
            "agora antes do retrospective?"
        ),
        paths=[
            ("Rodar agora (recomendado — feature acabou, contexto fresco)",
             "run"),
            ("Pular nesta feature (registra decisão consciente em status.json)",
             "skip"),
            ("Desativar auto-run permanentemente (toggle em qa config)",
             "disable"),
        ],
    )

    if choice == "run":
        result = run_qa_scope_feature(feature_slug)
        ctx.retrospective_inputs["qa_report"] = result.report_path
        # Verdict NÃO bloqueia — apenas anexa findings ao input do retrospective
    elif choice == "skip":
        ctx.status_log("qa-auto-run-skipped", reason="user-choice")
    elif choice == "disable":
        ctx.toggle_config("qa.auto-run-on-feature-done", False)
        ctx.status_log("qa-auto-run-disabled-by-user")
```

### §12.2 Decisão pragmática — QA verdict não bloqueia

**QA verdict (BLOCK/FLAG/PASS) NÃO bloqueia retrospective, NÃO bloqueia commit, NÃO bloqueia `forge implement` advancing.** Alinha Decisão 5 (code review final é out-of-scope da forge).

Razão: bloquear retrospective com base em verdict de QA agressivo invade o papel de code review humano (Decisão 5 explícita). Findings são insumo pro user; user decide via `forge evolve` o que aplicar (Decisão 26 single-by-single).

Esta decisão será documentada como §11 nova em `docs/design/07-discipline.md` — "QA verdict não-bloqueante" — quando a implementação rodar.

## §13. ADR — Revisita Decisão 9

Texto LITERAL pra append em `docs/design/01-decisions.md` (linha 29 nova, mantendo linha 9 histórica como append-only):

```markdown
| 29 | Revisita Decisão 9 (2026-06-05) — command surface | 13 subcomandos | Adiciona `forge qa` como 13º. Justificativa: QA red-team é semanticamente distinto de verify (cascade determinístico) / doctor (health check) / evolve (review-and-apply). Encaixar como menu interno de qualquer um dilui semântica e quebra discoverability. Linha 9 histórica preservada (locked at 12); a partir desta data, locked at 13. Veja `docs/superpowers/specs/2026-06-05-forge-qa-design.md` pra design completo. |
```

E nova Decisão 30 (sandbox isolation):

```markdown
| 30 | Sandbox isolation (forge qa Phase 3) | Subprocess CWD = `.planning/qa/<run-id>/fixtures/`; writes fora do sandbox raise SandboxBreachError; os.chdir guard via PYTHONSTARTUP preload; budget global default 60s + per-validator 15s configurável em workflow-config | Isolation guarantee contra contaminação de produção. Auditores chaos/validator-claim geram fixtures hostis que rodam validators em subprocess — sem hardening, validator malicioso ou bugado poderia escrever em paths de produção. Decisão pareada com Decisão 22 (no runtime deps em outras skills): sandbox protege a forge AGAINST cards de terceiros via qa-extensions. |
```

Texto LITERAL pra CHANGELOG.md `### Changed (load-bearing)`:

```markdown
### Changed (load-bearing)

- Revisita decisão 9: command surface 12 → 13 subcomandos — adiciona `forge qa` (adversarial red-team gate). Design completo em `docs/superpowers/specs/2026-06-05-forge-qa-design.md`. Locked at 12 histórico preservado em `docs/design/01-decisions.md` linha 9; novo lock em linha 29.
- Adiciona decisão 30: sandbox isolation pra `forge qa` Phase 3 — subprocess CWD dedicado em `.planning/qa/<run-id>/fixtures/`, SandboxBreachError em writes fora, budget global configurável.
```

## §14. Updates em `docs/design/06-command-surface.md`

3 edits no doc:

**Edit 1 — Header:** `# Command surface — locked at 12` → `# Command surface — locked at 13 (após Revisita Decisão 9 em 2026-06-05)`.

**Edit 2 — Adiciona row 13 na tabela "The 12 subcomandos":**

| # | Command | Canonical purpose |
|---|---|---|
| 13 | `forge qa` | Adversarial red-team gate. Audita artefatos do lifecycle inventando cenários hostis (4 attack vectors: spec-vs-spec, chaos, coverage, validator-claim), executa fixtures sintéticos em sandbox isolado, emite findings actionable em proposed-evolutions. Scope: feature / screen / task / paranoid (cross-feature). Trigger: manual + opt-in auto via `qa.auto-run-on-feature-done`. Verdict (BLOCK/FLAG/PASS) NÃO bloqueia retrospective nem commit — alinha Decisão 5 (code review final out-of-scope). |

(Header da tabela ganha update: "The 13 subcomandos (canonical purpose)".)

**Edit 3 — Adiciona 3 linhas na tabela "Mapeamento formal: operação → entrypoint":**

| Operação | Onde mora | Como o usuário chega lá |
|---|---|---|
| **QA: rodar audit adversarial** | `forge qa` (direto) | `forge qa` pergunta scope conversacionalmente (feature / screen / task / paranoid). Sem flag. |
| **QA: ativar/desativar comando + auto-run** | `forge reconfigure` → menu `[ ] qa` | Toggle interativo. Sem flag. |
| **QA: aplicar findings** | `forge evolve` → escolher proposta tipo `qa-finding-{vector-slug}` → "aplicar" | Reusa Decisão 26 single-by-single. QA não tem `--apply` próprio. |

## §15. Testing strategy

Distribuição estimada ~60-80 testes. Test count baseline novo: **637 (atual) + ~70 ≈ 707**.

### §15.1 Validators (rapid lane, sem marker) — ~12 testes

- `tests/validators/test_validate_qa_report.py` — happy + missing fields + schema_version drift + verdict enum + by_severity sum.
- `tests/validators/test_validate_qa_finding.py` — happy + fingerprint coerência + severity enum + evidence shape + proposed_evolution actionable bool.
- `tests/validators/test_validate_qa_extensions.py` — happy + name collision canon×local + phase enum guard + agent path missing + requires capability missing.

### §15.2 Engine unit (rapid lane) — ~25 testes

- `tests/engine/qa/test_scope.py` — feature scope / screen scope / task scope / paranoid scope / ambiguity 3-caminhos / scope missing artefato.
- `tests/engine/qa/test_run_id.py` — formato ISO + sufixo único + colisão (mesma timestamp + 2 runs paralelas, sufixo random distingue).
- `tests/engine/qa/test_sandbox.py` — happy subprocess / timeout per-validator / budget total estourado / SandboxBreachError em path absoluto fora / os.chdir guard ativo / fixture vazio.
- `tests/engine/qa/test_synthesis.py` — verdict logic (BLOCK 1 critical / BLOCK 3 high / FLAG 1 high / FLAG 3 medium / PASS) + dedup fingerprint + severity assignment.
- `tests/engine/qa/test_emit.py` — escreve proposed-evolutions / skip findings em rejected-fingerprints / temp file + rename atômico / disk full graceful.
- `tests/engine/qa/test_pre_flight.py` — workflow-config qa: parse + defaults + inconsistência (enabled=false + auto-run=true).

### §15.3 Integration (marker `integration`) — ~22 testes

- `tests/integration/test_qa_lifecycle_feature.py` — feature scope end-to-end com fixtures conhecidos (verdict esperado calibrado).
- `tests/integration/test_qa_lifecycle_task.py` — task scope end-to-end.
- `tests/integration/test_qa_cross_feature_paranoid.py` — paranoid scope com cap respeitado.
- `tests/integration/test_qa_auto_run_on_feature_done.py` — hook em implement Phase 6 dispara qa quando opt-in.
- `tests/integration/test_qa_card_extension.py` — card com `qa-extensions` carrega + auditor extra dispara.
- `tests/integration/test_qa_pause_resume.py` — Ctrl+C salva checkpoint.json + resume continua (Decisão 27).
- `tests/integration/test_qa_evolve_integration.py` — finding → proposed-evolution → `forge evolve` apply (single-by-single).

### §15.4 E2E (marker `e2e`) — ~5 testes

- `tests/e2e/test_qa_cli_smoke.py` — subprocess CLI completo: `forge qa` em fixture project, captura stdout cinemático, valida exit code, valida `qa-report.json` gerado.

### §15.5 Gates de "pronto"

- [ ] Todos validators novos ≥ 1 test happy + 1 edge.
- [ ] Sandbox breach test cobre 3 vetores (path absoluto, os.chdir, symlink traversal).
- [ ] Verdict logic test cobre os 4 thresholds (BLOCK/FLAG/PASS boundaries).
- [ ] E2E smoke verde em fixture project com verdict conhecido.
- [ ] Test count baseline = 637 + ~70 ≈ 707. PR que reduz exige justificativa per testing.md.

## §16. Edge cases endereçados

10 edge cases do brainstorm:

| # | Edge case | Comportamento |
|---|---|---|
| 1 | Feature sem screens definidas | scope=feature ainda roda; `coverage` auditor reporta finding "no screen contracts found" severity=info; `chaos` + `validator-claim` rodam normal nos contracts existentes. |
| 2 | QA em greenfield (sem features ainda) | Erro user-friendly: "Nenhuma feature em scope detectado. Rode `forge plan {slug}` antes." (sem 3-caminhos — só uma saída honesta). |
| 3 | Sandbox budget exhausted mid-run | Fixtures restantes marcados `skipped-budget`; finding `qa-budget-exhausted` severity=info; verdict continua calculado dos findings já avaliados. |
| 4 | Auditor LLM retorna JSON inválido | 1 retry com reprompt explícito ("retorne JSON estrito conforme schema X"); 2ª falha = finding `qa-auditor-malformed` severity=high; run continua. |
| 5 | Mesma falha em 3 runs consecutivos | Decisão 25 dedup absorve — fingerprint estável faz finding aparecer 1 vez em `forge evolve`; se rejected, fingerprint vira silent skip. |
| 6 | Ctrl+C mid-run | Decisão 27 — checkpoint.json salvo em `<run-id>/checkpoint.json`; resume detectado em nova invocação `forge qa`; user vê "retomando de Phase 2". |
| 7 | `qa.enabled: false` + `qa.auto-run-on-feature-done: true` | `forge doctor` reporta como warning (config inconsistente — auto-run nunca dispara). User pode reconciliar via `forge reconfigure → qa`. |
| 8 | Card overlay declara `qa-extensions` com nome de auditor colidindo com canon | Hard fail no loader (Gap 5 policy, Decisão 28). Mensagem aponta path canon + path local. |
| 9 | Subprocess validator entra em loop infinito | Per-validator timeout (default 15s, configurável) garante kill; finding severity=medium "validator timeout — possível loop"; budget global preserva o resto da run. |
| 10 | Disk full mid-Phase 2 (geração de fixtures) | Temp file + rename atômico; falha de write captura `OSError`; finding `qa-fixture-write-failed` severity=high; outras phases continuam (synthesis trabalha com findings parciais). |

## §17. Out-of-scope explícito v1 (deferred to v1.x / v2)

6 escopos deliberadamente excluídos. Cada um vira gap em `docs/design/04-pending.md` durante a implementação:

1. **Visual fidelity / a11y DOM auditors.** Auditor que faz snapshot de DOM/UI e compara com design-spec foge do recorte v1 (audit de artefatos textuais). Vem como card opt-in em v1.x (`qa-extensions: auditors: [{name: visual-fidelity, ...}]`). Card terá heavy deps (puppeteer/playwright) e expõe matiz "QA visual" que merece release dedicado.

2. **Convergence loop automatizado.** v1 = manual: user roda `forge qa` → revê findings em `forge evolve` apply → re-roda `forge qa` pra ver se sumiu. Loop automático "qa → evolve apply → qa" é tentação YAGNI — `forge evolve` é single-by-single (Decisão 26), tirar o gate humano do meio quebra a disciplina.

3. **CI / non-interactive mode.** Decisão 10 vale — sem flags, sem `--ci`, sem `--quiet`. CI integration é pattern emergente em v1.x quando alguém pedir; até lá, `forge qa` é puramente conversacional.

4. **Cross-project audit.** Inventory + memory são per-project (Decisão 14). Auditar correlações cross-project (ex: 2 projetos compartilham backend e o spec deles diverge) está fora do scope da skill standalone.

5. **Diff-aware mode.** v1 sempre audita o scope completo. "Auditar só o que mudou desde o último run" é otimização de performance que ainda não tem dado pra justificar (sem baseline de runtime real). v1.x considera quando user reportar `forge qa` lento.

6. **Custom rubric per project.** Rubric (§5.4) é hardcoded em v1. Permitir overrides do threshold BLOCK/FLAG/PASS via workflow-config abre porta pra "we don't fail on critical" — anti-pattern. Rubric fixa é guard-rail intencional.

## §18. Implementation plan handoff

Após aprovação deste spec:

1. **User review** — confere fidelidade ao brainstorm + pontos não cobertos.
2. **Invocar `superpowers:writing-plans`** com este doc como input pra produzir `docs/superpowers/plans/2026-06-05-forge-qa.md` — plano executável task-by-task com critérios de sucesso testáveis.
3. **Implementação dispatcher-by-dispatcher** — orchestrator-mantenedor → `gsd-executor` por componente, ordem sugerida:
   - Schemas novos (qa-report, qa-finding, qa-extensions).
   - Validators novos (3).
   - Engine modules (qa.py + qa/ subpackage).
   - Agents (qa-conductor + 4 auditores + synthesizer).
   - Templates (5 novos).
   - Edits em engine existentes (cli, cards/loader, implement, reconfigure, init).
   - Edits em docs design (06, 07 §11 nova, 01 ADR Decisão 29+30).
   - workflow-config.md schema bump.
   - card.md schema cross-link com qa-extensions.
   - Tests (validators → unit → integration → e2e).
   - Doc-sync (CHANGELOG, handoff, README, 04-pending gaps).
   - Roteiro UX completo (`docs/ux/forge-qa-roteiro.md`).
4. **NÃO implementar nada** até o plan estar aprovado.

## §19. Cross-refs

**Internal — load-bearing:**

- **Decisão 5** (out-of-scope: code review final) — QA verdict não bloqueia retrospective/commit (§12.2).
- **Decisão 9** (command surface) — revisitada em §13; locked at 12 → locked at 13.
- **Decisão 10** (zero flags) — `forge qa` é puramente conversacional, sem `--scope` / `--paranoid` / `--ci`.
- **Decisão 22** (no runtime deps) — preservada. Inspiração DNA das skills meoVendedor `qa-red-team` + `fix-qa-report` é pattern only.
- **Decisão 24** (`.bak` retention 7d) — pattern aplicado a `qa.retention-days` (default 14 — runs QA são mais ruidosas que `.bak`, retention maior).
- **Decisão 25** (fingerprint canonical-form) — usado em Phase 5 emit pra dedup contra `rejected-fingerprints.yaml` (§5.5).
- **Decisão 26** (single-by-single em evolve) — fix loop de QA reusa o gate humano (§D5, §10.3 Cena 8).
- **Decisão 27** (pause vs abort) — interrupted runs salvam checkpoint.json + resume automático (§16 edge 6).
- **Decisão 28** (card local overlay — Gap 5) — `qa-extensions` overlay-aware desde o início (§8.3).
- **Decisão 30 (nova)** — sandbox isolation (§13).

**Internal — disciplines:**

- **§1 (3-caminhos)** — aplicada em scope resolution (§5.0), auto-run prompt (§12), pause resume.
- **§2 (validator cascade fail-fast)** — preservada. QA não muda cascade de `forge verify`. Mas Phase 3 sandbox usa pattern de subprocess de `engine/verify.py` (reuso, mandamento #3).
- **§4 (`.bak` retention)** — pattern aplicado a `qa.retention-days`.
- **§7 (pause vs abort)** — Decisão 27 explicitamente reusada (§16 edge 6).

**Internal — gaps relacionados:**

- **Gap 5 (card local overlay)** — compatibilidade `qa-extensions` overlay (§8.3).
- **Gap 9 (extension feature)** — extension features auditáveis exatamente como product standalone; scope=feature funciona via `extends-feature` field do hypothesis (sem código novo).

**External — DNA inspiracional:**

- Skill `qa-red-team` do meoVendedor — atitude adversarial + 4 categorias de attack vector. Pattern absorvido (Decisão 22).
- Skill `fix-qa-report` do meoVendedor — fix loop estruturado. Adaptado pra reusar `forge evolve` em vez de inventar (Decisão 26 + mandamento #3).

**Internal — engine entrypoints:**

- `engine/verify.py` — pattern subprocess de validators reusado em `engine/qa/sandbox.py` (mandamento #3).
- `forge evolve` (engine/evolve.py) — fix loop endpoint (§5.5, §10.3).
- `forge plan` (engine/plan.py) — pattern engine + Claude Code agent dispatch reusado em `engine/qa.py` + Phase 1/2/4 auditores.
- `forge implement` (engine/implement.py) — hook no retrospective phase pra auto-run opt-in (§12).
- `forge reconfigure` (engine/reconfigure.py) — menu `[ ] qa` novo (§9).
- `forge init` (engine/init.py) — Step QA novo após Step 7.5 do Gap 5 (§9).
- `forge doctor` (engine/doctor.py) — health check de coerência da config qa (§9, §16 edge 7).

---

**Próximo step:** invocar `superpowers:writing-plans` com este spec como input para produzir plano executável task-by-task.
