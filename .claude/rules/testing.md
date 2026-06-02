# Testing — disciplina

Mandamento #2: verde antes de "pronto". 367 tests passing é estado-base.

## Comandos canônicos

```bash
# Lane completa (default)
pytest

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

## Gates de "pronto"

Você só pode reportar trabalho "concluído" se TODOS:

- [ ] `pytest` (full suite) sai com 0 falhas
- [ ] Count de tests >= baseline (367 em v1.1.0; consulte
      `docs/design/08-session-handoff.md` pra current count)
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
