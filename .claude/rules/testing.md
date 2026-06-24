# Testing — disciplina

Mandamento #2: verde antes de "pronto".

> **Counts por lane (snapshot release 1.5.0, baseline em main):** rapid 1863 / integration 204 / e2e 30.
> **Snapshot release 1.4.0 (anterior):** rapid 1569 / integration 162 / e2e 30.
> Fonte canônica: `docs/design/08-session-handoff.md` (atualizada a cada wave).
> Re-confirme com `.venv/bin/pytest -m 'not integration and not e2e' -q | tail -1`.

## Comandos canônicos

```bash
# Lane completa (default)
pytest                              # lane completa (ver handoff pra count atual)

# Lane rápida (skip integration + e2e)
pytest -m "not integration and not e2e"

# Apenas validators
pytest tests/validators/

# Apenas engine
pytest tests/engine/

# Test único (debug rápido)
pytest tests/path/test_x.py::test_func -xvs

# Apenas tests marcados integration
pytest -m integration

# Cascade de validators do projeto
forge verify

# Health check 12 categorias
forge doctor

# Smoke do CLI
./bin/forge --version
```

## Markers do projeto (em `pyproject.toml`)

- `integration` — testes que cruzam múltiplos módulos end-to-end. Podem
  precisar fixture MeoBonsai. Excluídos de rapid CI lane.
- `e2e` — subprocessam o CLI (slow). Excluídos de rapid CI lane.
- (sem marker) — unit puro. Lane default.

Quando marcar test novo:

- Cruza ≥2 módulos OU usa fixture MeoBonsai → `@pytest.mark.integration`
- Subprocess CLI → `@pytest.mark.e2e`
- Pure unit → sem marker

## Regra TDD (mandamento, não sugestão)

### Para bug fix

1. Reproduz com **regression test FALHANDO primeiro**
2. Roda: confirma FAIL
3. Implementa fix
4. Roda: confirma PASS
5. Garante que outros tests não quebraram: `pytest`
6. Commit (test + fix juntos OU test commit 1, fix commit 2 — escolha
   consistente por sessão)

### Para feature

1. Escreve happy-path test
2. Roda: confirma FAIL (function não existe)
3. Implementa minimal — só pra passar
4. Roda: PASS
5. Adiciona edge-case tests + impl iterativamente
6. Roda full suite: confirma green
7. Commit

### Para refactor

1. **NÃO adiciona test novo** (regra: refactor = sem mudança de comportamento)
2. Roda suite full ANTES do refactor: registra count + duration baseline
3. Refactor
4. Roda suite full DEPOIS: confirma mesmo count + verde
5. Roda `validators/check_no_behavior_change.py` se aplicável
6. Commit

## Fixtures conhecidos

Localização: `tests/conftest.py` + `tests/<module>/conftest.py`.

Principais (verifique `tests/conftest.py` pra lista atualizada):

- `tmp_project` — diretório temporário com estrutura mínima de projeto forge
- `mock_workflow_config` — workflow-config.yaml válido em memória
- `meobonsai_fixture` (marker `integration`) — repo fixture pra E2E
- `graph_session` — SQLite in-memory pra graph tests
- `frozen_now` — congela datetime pra testes determinísticos

Antes de criar fixture novo: `grep -rn "def fixture\|@pytest.fixture"
tests/` — talvez já exista.

## Validators são código

Novo validator em `validators/` exige:

1. Test em `tests/validators/test_<name>.py` (happy + edge cases)
2. Entrada na cascade de `forge verify` (`engine/verify.py` — verificar
   onde os validators são listados)
3. Mention em `docs/design/07-discipline.md §2` SE policy mudar (ex.: novo
   severity level)
4. Update `pyproject.toml` se introduzir marker novo

### Validators ativos (v1.3+)

15 validators no cascade. Novos desde v1.1:

- `check_no_behavior_change` (v1.1+) — gate refactor (Gap 2). Tests em
  `tests/validators/test_check_no_behavior_change_*.py`.
- `check_cyclomatic_complexity` (v1.2-dev+) — multi-language gate
  (Kotlin/Swift/TS/Python). Dispatcha pra Detekt/SwiftLint/eslint/Radon
  por linguagem; normaliza output pra `CCResult`; aplica regra `new` (cc
  > threshold) + `modified` (cc_after > cc_before). Threshold via
  precedência card `cc-gate-override` > workflow-config `cc-gate` >
  defaults built-in (kotlin=10, swift=10, ts=15, python=10).
  Override-justify via linha `CC-OVERRIDE: <file>:<func> cc=<N> — <razão>`
  no commit body (transiente, por commit). Bypass emergencial via env
  `NO_CC_GATE=1`, logado em `.claude/state/cc-gate-bypass.jsonl`.
  Tests em:
  - `tests/validators/test_check_cyclomatic_complexity.py` (validator main entry)
  - `tests/validators/test_cc_parsers_*.py` (parsers per-tool)
  - `tests/validators/test_cc_dispatch.py` (tool dispatch + availability)
  - `tests/validators/test_cc_override_justify.py` (regex + scope rules)
  - `tests/validators/test_common_cc_helpers.py` (`cc_threshold_lookup`
    + `cc_format_three_paths` em `validators/_common.py`)
  - `tests/integration/test_cc_gate_end_to_end.py` (marker `integration`,
    skip per-language quando tool nativa missing — usa `@pytest.mark.skipif`).

- `check_secrets` (v1.2-dev+, R1.1) — gate multi-tool de segurança,
  per-stage split: `gitleaks` no per-task hook de `forge implement`
  (regex-fast), `trufflehog --only-verified` na cascade de `forge verify`
  (verificação ativa). Binário (detectou = fail) — sem threshold numérico.
  Override-justify via `SECRETS-OVERRIDE: <file>:<line> kind=<token-type> —
  <razão>` no commit body; bypass emergencial via `NO_SECRETS_GATE=1` logado
  em `.claude/state/secrets-gate-bypass.jsonl`. Composto inteiro da infra
  Phase 0 (`dispatch_native_tool` / `apply_overrides` / `check_tool_available`
  / `git_staged_files` / `read_commit_body` / `result_*`).
  Tests em:
  - `tests/validators/test_check_secrets_skeleton.py` (SecretFinding + ignore-paths)
  - `tests/validators/test_check_secrets_parsers.py` (gitleaks + trufflehog parsers)
  - `tests/validators/test_check_secrets_dispatch.py` (stage selection + cmd_builders)
  - `tests/validators/test_check_secrets.py` (validate entry + override + render snapshot)
  - `tests/engine/test_verify_secrets_position.py` (cascade position após CC)
  - `tests/engine/test_implement_secrets_gate.py` (per-task hook + bypass)
  - `tests/engine/test_doctor_secrets_tools.py` (categoria `secrets-tools`)
  - `tests/integration/test_secrets_gate_end_to_end.py` (marker `integration`,
    smoke gitleaks/trufflehog reais com `@pytest.mark.skipif` quando ausentes).

## Gates de "pronto"

Você só pode reportar trabalho "concluído" se TODOS:

- [ ] `pytest` (full suite) sai com 0 falhas
- [ ] Count de tests >= baseline (snapshot 1.4.0: rapid 1569 / integration 162 / e2e 30;
      consulte `docs/design/08-session-handoff.md` pra current count)
- [ ] `forge verify` passa cascade sem hard fail
- [ ] Doc-sync executado (rule [doc-sync.md](doc-sync.md))
- [ ] Subagent reviewer assinou off (REVIEW.md sem high/critical)

Subagent que reporta "implementado" sem rodar pytest = falha de verification-
before-completion. Dispatch verification explícita SEMPRE.

## Test count regression

Se PR reduz test count, exige justificativa no commit body:

```
Removed N tests because <razão concreta>.
```

Sem isso, push-back via review. Test count protege regression detection.
