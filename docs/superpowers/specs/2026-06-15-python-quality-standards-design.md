# Python Quality Standards — feature-forge
**Data:** 2026-06-15
**Status:** Aprovado
**Implementação:** ver `.claude/rules/plan-auditor.md` → `writing-plans` na próxima sessão

## Objetivo

Estabelecer padrões proativos de qualidade Python em duas camadas:
1. **Tooling automatizado** — bloqueia no pré-commit via ruff + mypy strict
2. **AI rules** — guia subagentes do Claude via `.claude/rules/python.md`

Motivação: evitar deslizes de código antes de o projeto crescer, não remediar depois.

---

## Seção 1 — Tooling layer

### ruff (lint + format)

Adicionado em `[tool.ruff]` e `[tool.ruff.lint]` no `pyproject.toml` existente:

```toml
[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = [
    "E", "W",   # pycodestyle errors/warnings
    "F",        # pyflakes (undefined names, unused imports)
    "I",        # isort (import sorting)
    "UP",       # pyupgrade (moderniza sintaxe py311+)
    "B",        # flake8-bugbear (bugs comuns)
    "SIM",      # flake8-simplify
    "RUF",      # ruff-specific rules
    "N",        # pep8-naming
]
ignore = [
    "E501",     # line length (ruff format cuida disso)
    "B008",     # function calls in default args (legítimo em alguns casos)
]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["N802", "N803"]   # test funcs podem ter nomes fora do padrão pep8

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

### mypy — strict com amortização

Substituir configuração atual em `[tool.mypy]`:

```toml
[tool.mypy]
python_version = "3.11"
strict = true
warn_unused_ignores = true
files = ["engine", "validators"]
# Módulos deferidos via [[tool.mypy.overrides]] abaixo.
# Código NOVO não herda ignore — arquivos criados a partir da adoção
# precisam passar strict sem exceção.
```

Módulos com erros pré-existentes recebem override individual:

```toml
[[tool.mypy.overrides]]
module = "engine.algum_modulo"
ignore_errors = true
```

Lista de módulos deferidos entra em `docs/design/04-pending.md` como gap explícito.

### Integração no pré-commit

Adicionar ao `.claude/hooks/pre-commit-feature-forge.sh` (após bloco existente de decisão locked):

```bash
# --- Python quality gates ---
if command -v ruff &>/dev/null; then
    ruff check . || { echo "🛑 ruff lint falhou — rode: ruff check --fix ." >&2; exit 1; }
    ruff format --check . || { echo "🛑 ruff format diff — rode: ruff format ." >&2; exit 1; }
else
    echo "⚠️  ruff não instalado — instale com: pip install ruff" >&2
fi

if command -v mypy &>/dev/null; then
    mypy || { echo "🛑 mypy strict falhou" >&2; exit 1; }
else
    echo "⚠️  mypy não instalado — instale com: pip install mypy" >&2
fi
```

### Dependências dev

`ruff` adicionado em `[project.optional-dependencies] dev` (mypy já está lá):

```toml
dev = [
    "pytest>=8.0",
    "pytest-cov>=4.1",
    "mypy>=1.8",
    "ruff>=0.4",
]
```

---

## Seção 2 — AI rules layer (`.claude/rules/python.md`)

Arquivo novo em `.claude/rules/python.md`. Referenciado no `README.md` do rules index.

### Bloco 1 — Formatação e estilo

- `ruff format` é lei. Nunca formatar manualmente.
- `from __future__ import annotations` em todo arquivo (padrão do projeto).
- Line length: 100 caracteres.
- Double quotes para strings.
- Sintaxe py311+: `X | Y` em vez de `Optional[X]`, `list[str]` em vez de `List[str]`.

### Bloco 2 — Tipagem

- Type hints obrigatórios em toda função pública e privada — sem exceção.
- Return type obrigatório, inclusive `-> None`.
- Sem `Any` nu — se necessário, justifica com `# type: ignore[<code>] — <razão>`.
- `TypeAlias` explícito quando tipo complexo aparece em mais de um lugar.
- Union com `|`, não com `Union[]`.

### Bloco 3 — Arquitetura e módulos

- `engine/` → handlers de comando. Handler = thin dispatcher; lógica em helpers internos do módulo.
- `validators/` → SEMPRE consulta `_gate_infra.py`, `_diff.py`, `_common.py` antes de criar helper novo (Mandamento #3 + reuse.md).
- Sem import circular: engine não importa de validators, validators não importa de engine.
- Decision 22: engine não importa de skills ou superpowers em runtime — portability load-bearing.
- `__init__.py` sem side-effects. Re-exports apenas quando necessário e explícito.

### Bloco 4 — Error handling

- `except SomeSpecificError:` sempre. Nunca `except:` nu nem `except Exception:` sem re-raise imediato.
- Regra H-03 (remediada junho 2026, 18 sites): narrow except é mandamento.
- Se contexto é relevante, log antes de re-raise: `logger.error("contexto", exc_info=True)`.
- Não silenciar exceções com `pass` — se ignorar é intencional, comentar o motivo.

### Bloco 5 — Funções e complexidade

- CC gate threshold: 10 (Python via Radon). Função acima de 10 → refatorar antes de submeter.
- Funções privadas com prefixo `_`. Públicas apenas se forem API do módulo.
- Uma responsabilidade por função. Se o nome precisa de "e" (ex: "parse_and_validate"), separe.
- Sem side-effects escondidos em funções com nome de query (`get_*`, `find_*`, `list_*`).

### Bloco 6 — Antipadrões observados (histórico)

- **Over-mock** (M-01, remediado): prefer assertions de comportamento real sobre mock de implementação interna. Mock só em boundaries externas.
- **Broad except** (H-03, remediado): 18 sites corrigidos. Não reintroduzir.
- **Constante hardcoded** (fase SKIP_DIRS): usar configuração ou parâmetro, não constante inline em função.
- **Placeholder sem issue**: sem `TODO`/`FIXME` sem referência a gap em `docs/design/04-pending.md`.
- **Subagente que toca módulo com `ignore_errors = true`**: remover o override do módulo e resolver type errors como parte da task — não deixar acumular.

---

## Seção 3 — Estratégia de migração

Ordem que protege o baseline de 1113 tests e não gera big-bang:

### Passo 1 — ruff auto-fix (zero risco)

```bash
ruff check --fix .
ruff format .
pytest   # confirma baseline verde
```

Commit: `chore(python-quality): apply ruff auto-fix to existing codebase`

Violations que ruff não auto-fixa → resolvidas manualmente no mesmo commit.

### Passo 2 — mypy amortização

```bash
mypy 2>&1 | grep "^engine\|^validators" | cut -d: -f1 | sort -u
# → lista de módulos com erros
```

Para cada módulo com erros, adicionar `[[tool.mypy.overrides]]` com `ignore_errors = true`.
Commit: `chore(python-quality): mypy strict amortization — N modules deferred`

Lista de módulos deferidos → entrada em `docs/design/04-pending.md`.

### Passo 3 — pre-commit hook + ruff no dev deps

Commit: `feat(python-quality): add ruff+mypy strict gates to pre-commit hook`

A partir deste commit: qualquer arquivo novo ou modificado passa pelo gate. Sem graça para código novo.

### Passo 4 — `.claude/rules/python.md`

Criado após passos 1-3 verdes. Referenciado no `.claude/rules/README.md`.
Commit: `docs(rules): add python.md — style, architecture, antipatterns guide`

### Regra de amortização orgânica

Quando subagente toca módulo listado em `ignore_errors = true`:
- Remove o override daquele módulo de `pyproject.toml`
- Resolve os type errors como parte da task
- Sem sprint dedicada — a lista diminui naturalmente a cada task

---

## Anti-goals

- Não adicionar regras de lint que gerem falso-positivo alto no código atual (por isso `B008` está em `ignore`)
- Não converter todo o codebase pra mypy strict em um sprint — amortização orgânica
- Não criar skill runtime de Python (Decision 22 — absorb patterns only)
- Não mudar a arquitetura de módulos — só formalizar o que já existe

---

## Critério de sucesso (pós-implementação)

- [ ] `ruff check .` sai com 0 erros no codebase pós-auto-fix
- [ ] `ruff format --check .` sai com 0 diffs
- [ ] `mypy` passa (módulos amortizados com `ignore_errors = true`)
- [ ] `pytest` mantém baseline >= 1113 tests passando
- [ ] `.claude/hooks/pre-commit-feature-forge.sh` bloqueia commit com lint error
- [ ] `.claude/rules/python.md` existe e é referenciado no `README.md` do rules index
- [ ] `docs/design/04-pending.md` tem entrada com lista de módulos mypy deferidos
