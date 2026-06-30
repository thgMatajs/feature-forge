# Plano — Fase 0 (Fundação) da campanha AI-first

> **Plano executável**, derivado de `superpowers:writing-plans`.
> **Spec upstream:** `docs/superpowers/specs/2026-06-30-aifirst-pendencias-campaign-design.md` §"Fase 0 — Fundação".
> **Spec irmã (fronteira de execução externa):** `docs/superpowers/specs/2026-06-30-native-quality-gates-design.md` (§1 Caminho A, §2 descoberta, §3 isolamento, §5 non-goals).
> **Branch:** `feat/aifirst-pendencias`.
> **Voz:** mentor calmo — firme nos gates, didático nos exemplos.
> **Status:** pré-implementação (aguarda plan-auditor antes do handoff ao `gsd-executor`).
> **Data:** 2026-06-30.

---

## Goal

Deixar a fundação pronta pra Fase 1 (Tema 6 — gates nativos + build-only) sem
afrouxar nenhuma garantia que custou caro. Três entregas serial-dependentes:

1. **0a** — Abrir a **Decisão 33** (fronteira de execução externa, distinta do
   sandbox de validators da Decisão 30) via o ritual de *nova decisão*, e
   estender o hook de cerimônia pra aceitar "nova decisão" (hoje só aceita
   "revisita decisão" — sem isso o commit da 33 trava no HARD BLOCK).
2. **0b** — Um helper **genérico** de fronteira de execução externa
   (`engine/external_exec.py`), TDD, que a Fase 1 (A1 ktlint, A2 build-only)
   reusa. Nada tool-específico aqui.
3. **0c** — **Investigar** (não fixar cego) a divergência dos dois write-paths
   do verify-log, e bater o martelo via 3-caminhos com base no que o teste
   observar.

A Fase 0 é **serial** (0a → 0b → 0c não têm dependência de código entre si, mas
rodam em sequência na mesma branch; 0c toca `verify.py`, que a Fase 1 estende, e
por isso precisa estar limpo antes). **Este plano NÃO planeja a Fase 1.**

## Architecture

- **0a** é uma mudança de *processo + documento load-bearing* (hook + decisão),
  não de engine de produto. O hook `.claude/hooks/pre-commit-feature-forge.sh`
  faz HARD BLOCK quando `docs/design/01-decisions.md` é staged sem a cerimônia
  no CHANGELOG staged. Hoje a cerimônia reconhecida é só "revisita decisão" — a
  Decisão 33 é **nova**, então o regex precisa aceitar também "nova decisão".
- **0b** materializa a **fronteira de execução externa** da spec irmã (§1
  Caminho A): um caminho de subprocess **separado** do sandbox de validators
  (Decisão 30). Espelha o pattern de `engine/verify.py::_invoke_validator`
  (`subprocess.run` com `check=False`, `capture_output=True`, `text=True`,
  `timeout`, `env=build_safe_env(...)`, `cwd=project_root`) e **melhora** o
  pattern cru de `engine/upgrade.py::_git_fetch/_git_checkout` (que hoje roda
  `git` sem env custom, sem timeout, com `check=True`). O helper é **genérico**:
  só sabe rodar `argv` e resolver candidatos de invocação — zero conhecimento de
  ktlint/gradle (isso é Fase 1, §6 Nível 1 da spec irmã).
- **0c** é uma investigação de drift entre dois write-paths do verify-log que
  (pelo scout) apontam pro **mesmo arquivo** mas têm validação assimétrica.

## Tech Stack

- Python 3 (stdlib: `subprocess`, `shutil`, `pathlib`, `dataclasses`, `time`).
- `engine._sandbox.env.build_safe_env(*, extras, allow_sensitive=False)` pro env
  reduzido (allowlist `PATH/HOME/USER/LOGNAME/LANG/LC_*/TZ/TMPDIR/TEMP/TMP/PYTHONHASHSEED`).
- `pytest` — **`.venv/bin/pytest` é o CANÔNICO** (tem json5 + deps; o system
  pytest gera false-fail). Testes novos vivem em `tests/engine/`.
- Sem dependências novas. Decisão 22 (zero runtime deps em outras skills) intacta.

## Global Constraints

- **`.venv/bin/pytest` é o pytest canônico.** Lane rápida:
  `.venv/bin/pytest -m "not integration and not e2e"`. NUNCA o system pytest.
- **Worktree isolado com venv próprio.** A impl roda via `gsd-executor` em
  worktree. **Gate anti-trap (obrigatório antes de rodar qualquer teste):**
  confirmar que o engine importado vem da worktree, não do repo principal
  (editable-install aponta pro repo principal):
  ```bash
  .venv/bin/python -c "import engine, pathlib; p=pathlib.Path(engine.__file__).resolve(); cwd=pathlib.Path('.').resolve(); assert str(p).startswith(str(cwd)), f'engine vem de FORA da worktree: {p}'; print('OK engine:', p)"
  ```
  Se falhar: criar `.venv` local na worktree e `pip install -e .` antes de seguir.
- **Voz mentor calmo** em toda mensagem/aviso/docstring gerada (avisos de skip,
  texto de decisão, mensagem do hook). Sem voz corporativa, sem emoji decorativo.
- **Doc-sync no mesmo commit** ao tocar `engine/`/`hooks/`/`docs/`: cada task
  que toca código vivo ou hook atualiza `CHANGELOG.md` (`[Unreleased]`) no MESMO
  commit. (O pre-commit emite SOFT WARNING se faltar.)
- **Decisão 33 (ritual nova decisão):** append-only em `01-decisions.md` (nunca
  deletar linha), texto literal "Nova decisão 33:" no CHANGELOG sob
  `### Changed (load-bearing)`, e "Nova decisão 33" no commit body da task 0a.
- **Commit por task** (3 commits no total). A Fase 0 NÃO faz push — o
  orquestrador faz o checkpoint de merge/push. `gh auth = thgMatajs` é verificado
  pelo orquestrador antes de qualquer push (drift thgPacheco↔thgMatajs reincide).
- **Escopo contido (Mandamento #4):** editar só os arquivos listados por task.
  Sem refactor não-solicitado em `verify.py`/`l1.py` além do que 0c decidir.
- **TDD é mandamento (#2):** feature começa com happy-path FALHANDO; cada step de
  impl roda o teste e o vê passar antes do commit.

### Arquivos permitidos por task (whitelist de edit)

- **0a:** `.claude/hooks/pre-commit-feature-forge.sh`, `docs/design/01-decisions.md`,
  `CHANGELOG.md`. (+ teste do hook em `tests/hooks/` — ver step 0a.2.)
- **0b:** `engine/external_exec.py` (novo), `tests/engine/test_external_exec.py`
  (novo), `CHANGELOG.md`.
- **0c:** `tests/engine/test_verify_log_write_paths.py` (novo); depois,
  **condicionalmente** (Caminho A) `engine/verify.py` + `tests/engine/test_verify_log_consolidation.py`,
  **ou** (Caminho B) docstrings de `engine/verify.py::_write_verify_log_entry`
  e `engine/memory/l1.py::append_verify_log`; `CHANGELOG.md`.

---

## Estado do código (scout verificado 2026-06-30 — não re-explorar)

Registrado pra o executor não re-scoutar. Linhas conferidas nesta data.

- **Hook de cerimônia** — `.claude/hooks/pre-commit-feature-forge.sh:24`:
  ```bash
  if ! echo "$CHANGELOG_DIFF" | grep -qiE 'revisita decisão|revisit decision'; then
  ```
  HARD BLOCK (exit 1) quando `01-decisions.md` é staged sem casar esse regex no
  diff staged de `CHANGELOG.md`. A mensagem de block (heredoc L25-37) cita só
  `'Revisita decisão N: ...'` como cerimônia.
- **Decisões** — `docs/design/01-decisions.md`: tabela Markdown
  `| # | Decision | Choice | Rationale |`. Última linha hoje = **32** (revisita
  da Decisão 10, interaction mode). Próxima = **33**. Decisões 30/31 = sandbox
  isolation Python-only via `sitecustomize.py` preload.
- **CHANGELOG.md** — tem `## [Unreleased]` com `### Added`. **NÃO tem**
  `### Changed (load-bearing)` ainda — 0a cria a subseção.
- **Env reduzido** — `engine/_sandbox/env.py:72`:
  `build_safe_env(*, extras: Iterable[str] = (), allow_sensitive: bool = False) -> dict[str, str]`.
  Retorna `(CORE_ALLOWLIST ∪ extras) ∩ os.environ`. `extras` com var sensitive
  (bate `SENSITIVE_PATTERN`) sem `allow_sensitive=True` → `ValueError`.
  `CORE_ALLOWLIST` (env.py:22-30) = `PATH, HOME, USER, LOGNAME, LANG, LC_ALL,
  LC_CTYPE, TZ, TMPDIR, TEMP, TMP, PYTHONHASHSEED`. Consumidores autorizados
  listados no docstring do módulo incluem `engine.verify`; **adicionar
  `engine.external_exec` à lista de consumidores autorizados** (doc-only, mesmo
  módulo) é parte de 0b.
- **Pattern subprocess de validator** — `engine/verify.py:1018-1026`:
  ```python
  proc = subprocess.run(
      cmd, check=False, capture_output=True, text=True, timeout=60,
      env=build_safe_env(extras=("JAVA_HOME", "ANDROID_HOME", "GRADLE_USER_HOME")),
      cwd=str(project_root),
  )
  ```
  `TimeoutExpired` → `status="degraded"`; `OSError` → `status="degraded"`.
- **Pattern subprocess de binário externo já existente** — `engine/upgrade.py:39-50,76-87`:
  `_git_fetch`/`_git_checkout` rodam `git` com `cwd=forge_home, check=True,
  capture_output=True` — **SEM env custom, SEM timeout, estourando exceção**. 0b
  melhora esse pattern (env reduzido + timeout + `check=False` + classificação).
- **verify-log — dois write-paths:**
  - `engine/verify.py:654` `_write_verify_log_entry(project_root, *, feature_slug,
    scope_type, scope_id, validators, result, hard_fails, warnings_list) -> None`.
    Monta `entry` com `"scope": {"type": scope_type, "id": scope_id}` (**dict**) e
    `"warnings": list(warnings_list)` (**list**), serializa via `json.dumps(...)`
    DIRETO (verify.py:687) e escreve em
    `lifecycle_root(project_root) / feature_slug / "verify-log.jsonl"` (verify.py:684).
    **NÃO passa por `append_verify_log` — bypassa toda a validação.**
  - `engine/memory/l1.py:941` `append_verify_log(feature_slug, project_root,
    entry: dict) -> None`. VALIDA: `scope` ∈ `_VERIFY_SCOPES={"task","feature","inferred"}`
    (l1.py:932) — **espera string, não dict**; `result` ∈ `_VERIFY_RESULTS=
    {"pass","warn","incomplete","degraded","fail"}` (l1.py:938); se
    `result=="degraded"`, exige `isinstance(warnings, int) and warnings >= 1`
    (l1.py:1001-1006) — **espera int, não list**. Levanta `MemoryError` em
    violação. Escreve em `_l1_dir(project_root, feature_slug) / _VERIFY_FILE`
    (l1.py:1008), onde `_VERIFY_FILE="verify-log.jsonl"` (l1.py:37) e
    `_l1_dir = memory_l1_path = lifecycle_root(project_root) / feature_slug`
    (l1.py:123-124, paths.py:141-143).
  - **Conclusão do scout:** os dois caminhos escrevem no **MESMO arquivo**
    (`lifecycle_root(root)/slug/verify-log.jsonl`). O caminho de `verify.py`
    produz `scope` como dict e `warnings` como list — formas que `append_verify_log`
    **rejeitaria** (`scope` dict ∉ `_VERIFY_SCOPES`; `warnings` list falha o
    `isinstance(..., int)` quando degraded). Isso é o **Caminho A** (drift real)
    como hipótese provável — mas 0c deve **confirmar empiricamente** antes de
    fixar. (Detalhe: o scope da spec foi anotado como "scope dict/string" —
    `verify.py` grava `scope` como objeto `{type,id}` enquanto a validação espera
    o `type` cru como string; consolidar exige mapear o dict → forma validável.)
- **Testes de verify** vivem em `tests/engine/test_verify_*.py`. Adicionar os
  testes novos nesse diretório.

---

## Task 0a — Decisão 33 + extensão do hook de cerimônia

**Objetivo:** abrir a Decisão 33 (fronteira de execução externa) seguindo o
ritual de nova decisão, e estender o hook pra que ele aceite "nova decisão" como
cerimônia válida (sem deixar de bloquear o caso sem-cerimônia).

**Por que o hook PRIMEIRO:** a Decisão 33 é nova (não revisita). Com o regex
atual (`'revisita decisão|revisit decision'`), o commit que staga
`01-decisions.md` + um CHANGELOG dizendo "Nova decisão 33" travaria no HARD
BLOCK. Estender o hook antes destrava o próprio commit desta task.

**Foco do reviewer (anote no handoff):** (a) o hook ainda bloqueia o commit
sem-cerimônia; (b) append-only preservado em `01-decisions.md` (linha 32 intacta,
33 só adicionada); (c) texto literal "Nova decisão 33:" presente no CHANGELOG;
(d) "Nova decisão 33" no commit body.

**Arquivos permitidos:** `.claude/hooks/pre-commit-feature-forge.sh`,
`docs/design/01-decisions.md`, `CHANGELOG.md`, `tests/hooks/test_pre_commit_ceremony.py` (novo).

### Step 0a.1 — Test do hook FALHANDO (TDD)

Crie `tests/hooks/test_pre_commit_ceremony.py`. O teste exercita o hook num repo
git temporário, stageando `docs/design/01-decisions.md` + um `CHANGELOG.md`, e
asserta os três comportamentos: (1) BLOCK sem cerimônia → exit 1; (2) PASS com
"revisita decisão" → exit 0; (3) PASS com "nova decisão" → exit 0. O caso (3)
**deve falhar** contra o hook atual (regex não casa "nova decisão").

```python
"""Gate do ritual de cerimônia no pre-commit (Decisão 33, Fase 0a).

O hook .claude/hooks/pre-commit-feature-forge.sh faz HARD BLOCK quando
docs/design/01-decisions.md é staged sem a cerimônia no CHANGELOG staged.
Cerimônia válida: 'revisita decisão' (decisão existente) OU 'nova decisão'
(decisão nova, como a 33). Mentor calmo: firme no gate, claro no porquê.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK = REPO_ROOT / ".claude" / "hooks" / "pre-commit-feature-forge.sh"


def _init_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.st"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "docs" / "design").mkdir(parents=True)
    return tmp_path


def _stage(repo: Path, decisions_body: str, changelog_body: str) -> None:
    (repo / "docs" / "design" / "01-decisions.md").write_text(decisions_body, encoding="utf-8")
    (repo / "CHANGELOG.md").write_text(changelog_body, encoding="utf-8")
    subprocess.run(
        ["git", "add", "docs/design/01-decisions.md", "CHANGELOG.md"],
        cwd=repo,
        check=True,
    )


def _run_hook(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(HOOK)],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


def test_blocks_without_ceremony(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, "| 33 | x | y | z |\n", "## [Unreleased]\n\n### Added\n- nada de cerimônia\n")
    result = _run_hook(repo)
    assert result.returncode == 1, f"esperava BLOCK, veio {result.returncode}: {result.stderr}"
    assert "BLOCK" in result.stderr


def test_passes_with_revisita(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, "| 33 | x | y | z |\n", "### Changed\n- Revisita decisão 10: foo — bar\n")
    result = _run_hook(repo)
    assert result.returncode == 0, f"esperava PASS, veio {result.returncode}: {result.stderr}"


def test_passes_with_nova_decisao(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, "| 33 | x | y | z |\n", "### Changed (load-bearing)\n- Nova decisão 33: foo — bar\n")
    result = _run_hook(repo)
    assert result.returncode == 0, f"esperava PASS pra nova decisão, veio {result.returncode}: {result.stderr}"
```

**Rodar e ver falhar** (a worktree gate primeiro):
```bash
.venv/bin/python -c "import engine, pathlib; p=pathlib.Path(engine.__file__).resolve(); cwd=pathlib.Path('.').resolve(); assert str(p).startswith(str(cwd)), p; print('OK', p)"
.venv/bin/pytest tests/hooks/test_pre_commit_ceremony.py -q
```
Esperado: `test_passes_with_nova_decisao` FALHA (exit 1 do hook); os outros dois
passam (comportamento já existente). Isso prova que o teste casa o gap.

### Step 0a.2 — Estender o regex e a mensagem do hook (impl mínima)

Em `.claude/hooks/pre-commit-feature-forge.sh`, na linha 24, troque o regex pra
aceitar também "nova decisão"/"new decision":

```bash
    if ! echo "$CHANGELOG_DIFF" | grep -qiE 'revisita decisão|revisit decision|nova decisão|new decision'; then
```

E atualize o heredoc da mensagem de BLOCK (L25-37) pra citar as duas cerimônias
válidas, em voz mentor calmo:

```bash
        cat <<'EOF' >&2

🛑 BLOCK: docs/design/01-decisions.md alterado sem cerimônia.

    Adicione entrada em CHANGELOG.md (staged) contendo UMA das cerimônias:
      'Revisita decisão N: <novo choice> — <rationale>'   (decisão existente)
      'Nova decisão N: <choice> — <rationale>'            (decisão nova)

    Por quê: decisões locked são imutáveis sem revisitar, e toda decisão nova
    precisa de registro explícito (mandamento #1). Sem silent drift.
    Override consciente: git commit --no-verify (registra que foi deliberado).

    Detalhe: .claude/rules/decisions.md

EOF
```

**Rodar e ver passar:**
```bash
.venv/bin/pytest tests/hooks/test_pre_commit_ceremony.py -q
```
Esperado: 3 passed. O caso sem-cerimônia continua bloqueando (test_blocks_without_ceremony verde).

### Step 0a.3 — Append da Decisão 33 (append-only)

Em `docs/design/01-decisions.md`, **após** a linha 32 (não deletar nada), adicione:

```
| 33 | Fronteira de execução externa (engine → binário do consumidor) | Engine pode executar binários externos do projeto consumidor (linters, build tools) via uma fronteira de execução dedicada, distinta do sandbox de validators da Decisão 30. Garantias: modo check read-only onde aplicável; env reduzido (build_safe_env); timeout por gate com estouro → degraded; skip-se-ausente; sem auto-fix; sem instalar toolchain. | A Decisão 30 (sandbox Python-only, hermético via sitecustomize.py) NÃO cobre binário externo — o preload não se aplica a um processo que não passa pelo interpretador do forge. Rodar gradle/ktlint é fronteira de execução NOVA, com garantias próprias e explícitas. A 33 NÃO afrouxa a 30: a 30 segue valendo integralmente pro sandbox de validators; a 33 é caminho separado. Dependência das duas faces do Tema 6 (gates nativos + build-only). Spec: docs/superpowers/specs/2026-06-30-native-quality-gates-design.md §3. |
```

### Step 0a.4 — Entrada no CHANGELOG (texto literal)

Em `CHANGELOG.md`, sob `## [Unreleased]`, crie a subseção `### Changed (load-bearing)`
(não existe ainda) e adicione a linha com o texto literal começando "Nova decisão 33:":

```markdown
### Changed (load-bearing)

- Nova decisão 33: o engine pode executar binários externos do projeto
  consumidor (linters, build tools) via uma fronteira de execução dedicada,
  distinta do sandbox de validators da Decisão 30. Garantias: modo check
  read-only onde aplicável; env reduzido (build_safe_env); timeout por gate com
  estouro → degraded; skip-se-ausente; sem auto-fix; sem instalar toolchain. A
  Decisão 30 segue valendo integralmente pro sandbox de validators — a 33 é
  fronteira separada, não afrouxa a 30.
```

### Step 0a.5 — Verificar e commitar a task

```bash
.venv/bin/pytest tests/hooks/test_pre_commit_ceremony.py -q
git add .claude/hooks/pre-commit-feature-forge.sh docs/design/01-decisions.md CHANGELOG.md tests/hooks/test_pre_commit_ceremony.py
git commit -m "feat(decisions): Nova decisão 33 — fronteira de execução externa + hook aceita nova decisão

Estende .claude/hooks/pre-commit-feature-forge.sh pra aceitar 'nova decisão'
como cerimônia válida (antes só 'revisita decisão'), destravando o registro de
decisões novas. Append-only da Decisão 33 em 01-decisions.md + entrada literal
no CHANGELOG sob Changed (load-bearing). Test de cerimônia cobre block-sem-,
pass-revisita-, pass-nova-decisão.

Nova decisão 33: fronteira de execução externa distinta do sandbox de validators
(Decisão 30) — não afrouxa a 30.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

**Done quando:** `tests/hooks/test_pre_commit_ceremony.py` 3 passed; o próprio
commit acima passou pelo hook (prova viva de que "nova decisão" é aceita); linha
32 intacta + 33 adicionada; "Nova decisão 33:" literal no CHANGELOG e no commit body.

---

## Task 0b — Helper de fronteira de execução externa (TDD)

**Objetivo:** um módulo novo `engine/external_exec.py` que roda binários externos
do consumidor de forma **genérica** (nada tool-específico), reusável pela Fase 1.
Espelha o env reduzido + timeout do `_invoke_validator` e melhora o pattern cru
do `upgrade.py` (env, timeout, `check=False`, classificação, skip-se-ausente).

**Interface (assinaturas verbatim — não inventar):**
- `@dataclass ExternalToolResult`: `tool: str`, `status: str` ∈
  `{"pass","fail","degraded","skipped"}`, `exit_code: int | None`, `stdout: str`,
  `stderr: str`, `duration_ms: int`, `skipped_reason: str = ""`.
- `run_external_tool(argv: list[str], project_root: Path, *, timeout: int = 120) -> ExternalToolResult`
  — `check=False`, `capture_output=True`, `text=True`,
  `env=build_safe_env(extras=("JAVA_HOME","ANDROID_HOME","GRADLE_USER_HOME"))`,
  `cwd=project_root`. `TimeoutExpired` → `status="degraded"` (NÃO exceção);
  `OSError` (binário some/não-executável) → `status="degraded"`; exit 0 → `"pass"`;
  exit ≠ 0 → `"fail"`. (Threshold/warning-vs-fail é semântica da Fase 1; aqui só o
  mapping bruto exit→status, e `degraded` só pra timeout/OSError.)
- `resolve_invocation(candidates: list[list[str] | str], project_root: Path) -> list[str] | None`
  — recebe candidatos ordenados; retorna o **primeiro** que resolve, como `argv`
  (list[str]), ou `None` (skip-se-ausente). Regras de resolução por tipo de candidato:
  - candidato `list[str]` cujo **primeiro elemento começa com `./`** (wrapper, ex.
    `["./gradlew","ktlintCheck"]`) → resolve se `(project_root / first[2:])` existe
    e é arquivo; retorna o argv como veio.
  - candidato `list[str]` cujo primeiro elemento é um **path absoluto** (vindo do
    config, ex. `["/opt/ktlint","--reporter=json"]`) → resolve se o path existe; retorna como veio.
  - candidato `str` (nome de tool, ex. `"ktlint"`) → `shutil.which(name)`; se achar,
    retorna `[resolved_path]`; senão segue pro próximo.
  - candidato `list[str]` cujo primeiro elemento é um nome simples (sem `/`) →
    `shutil.which(first)`; se achar, retorna `[resolved_path, *rest]`.
  - nenhum resolve → `None`.

**Genérico (Mandamento #4 + §6 spec irmã):** ZERO nome de tool/task hardcoded
(`ktlint`, `ktlintCheck`, `gradle` etc. NÃO aparecem em `external_exec.py`). O
helper só sabe rodar `argv` e resolver candidatos. A Fase 1 monta os candidatos.

**Arquivos permitidos:** `engine/external_exec.py` (novo),
`tests/engine/test_external_exec.py` (novo), `CHANGELOG.md`, e doc-only:
adicionar `engine.external_exec` à lista de consumidores autorizados no docstring
de `engine/_sandbox/env.py` (L3-9).

### Step 0b.1 — Testes FALHANDO (TDD)

Crie `tests/engine/test_external_exec.py`. Usa fixtures com um **stub Python**
que sai com exit code controlado (NÃO depende de gradle/ktlint real).

```python
"""Fronteira de execução externa genérica (Fase 0b).

Cobre run_external_tool (pass/fail/timeout→degraded/OSError→degraded, env
reduzido, cwd correto) e resolve_invocation (wrapper hit, path-abs hit, which
hit, none→skip). Stub Python como binário externo controlado — sem gradle/ktlint
real. Mentor calmo: o helper é genérico, sabe só rodar argv e resolver candidatos.
"""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from engine.external_exec import (
    ExternalToolResult,
    resolve_invocation,
    run_external_tool,
)


def _make_stub(path: Path, *, exit_code: int = 0, sleep: float = 0.0, echo_env: str = "") -> Path:
    """Escreve um stub Python executável que dorme, ecoa uma env var e sai com exit_code."""
    body = (
        "#!/usr/bin/env python3\n"
        "import os, sys, time\n"
        f"time.sleep({sleep})\n"
        f"v = os.environ.get({echo_env!r}, '')\n"
        "sys.stdout.write('ENV=' + v + '\\n')\n"
        "sys.stderr.write('stub-stderr\\n')\n"
        f"sys.exit({exit_code})\n"
    )
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def test_run_pass(tmp_path: Path) -> None:
    stub = _make_stub(tmp_path / "ok.py", exit_code=0)
    res = run_external_tool([sys.executable, str(stub)], tmp_path)
    assert isinstance(res, ExternalToolResult)
    assert res.status == "pass"
    assert res.exit_code == 0
    assert "stub-stderr" in res.stderr
    assert res.duration_ms >= 0


def test_run_fail(tmp_path: Path) -> None:
    stub = _make_stub(tmp_path / "bad.py", exit_code=3)
    res = run_external_tool([sys.executable, str(stub)], tmp_path)
    assert res.status == "fail"
    assert res.exit_code == 3


def test_run_timeout_is_degraded(tmp_path: Path) -> None:
    stub = _make_stub(tmp_path / "slow.py", exit_code=0, sleep=2.0)
    res = run_external_tool([sys.executable, str(stub)], tmp_path, timeout=1)
    assert res.status == "degraded"
    assert res.exit_code is None
    assert "timeout" in res.skipped_reason.lower() or "timeout" in res.stderr.lower()


def test_run_oserror_is_degraded(tmp_path: Path) -> None:
    res = run_external_tool([str(tmp_path / "nao-existe-binario")], tmp_path)
    assert res.status == "degraded"
    assert res.exit_code is None


def test_env_is_reduced(tmp_path: Path) -> None:
    # Var sensitive NÃO pode vazar pro subprocess; var fora da allowlist também não.
    os.environ["MY_API_KEY"] = "leak-me"
    os.environ["RANDOM_NON_ALLOWLISTED"] = "also-leak"
    try:
        stub_secret = _make_stub(tmp_path / "echo_secret.py", echo_env="MY_API_KEY")
        res = run_external_tool([sys.executable, str(stub_secret)], tmp_path)
        assert res.status == "pass"
        assert "leak-me" not in res.stdout
        assert res.stdout.strip() == "ENV="
        stub_other = _make_stub(tmp_path / "echo_other.py", echo_env="RANDOM_NON_ALLOWLISTED")
        res2 = run_external_tool([sys.executable, str(stub_other)], tmp_path)
        assert "also-leak" not in res2.stdout
    finally:
        os.environ.pop("MY_API_KEY", None)
        os.environ.pop("RANDOM_NON_ALLOWLISTED", None)


def test_cwd_is_project_root(tmp_path: Path) -> None:
    # O stub imprime o cwd; deve ser o project_root passado.
    stub = tmp_path / "pwd.py"
    stub.write_text(
        "#!/usr/bin/env python3\nimport os,sys\nsys.stdout.write(os.getcwd())\n",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    sub = tmp_path / "subdir"
    sub.mkdir()
    res = run_external_tool([sys.executable, str(stub)], sub)
    assert Path(res.stdout.strip()).resolve() == sub.resolve()


def test_resolve_wrapper_hit(tmp_path: Path) -> None:
    (tmp_path / "gradlew").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    argv = resolve_invocation([["./gradlew", "someTask"]], tmp_path)
    assert argv == ["./gradlew", "someTask"]


def test_resolve_wrapper_miss_falls_through(tmp_path: Path) -> None:
    # Wrapper ausente, mas path absoluto existente como 2º candidato vence.
    real = _make_stub(tmp_path / "real-bin.py")
    argv = resolve_invocation(
        [["./gradlew", "x"], [str(real), "--flag"]],
        tmp_path,
    )
    assert argv == [str(real), "--flag"]


def test_resolve_config_abs_path_hit(tmp_path: Path) -> None:
    real = _make_stub(tmp_path / "cfg-bin.py")
    argv = resolve_invocation([[str(real), "--reporter=json"]], tmp_path)
    assert argv == [str(real), "--reporter=json"]


def test_resolve_which_hit(tmp_path: Path) -> None:
    # "python3" (ou o executável atual) existe no PATH → which resolve.
    name = Path(sys.executable).name
    argv = resolve_invocation([name], tmp_path)
    assert argv is not None
    assert Path(argv[0]).name == name


def test_resolve_none_when_all_absent(tmp_path: Path) -> None:
    argv = resolve_invocation(
        [["./nope-wrapper", "t"], ["/definitivamente/nao/existe"], "binario-fantasma-xyz"],
        tmp_path,
    )
    assert argv is None
```

**Rodar e ver falhar** (worktree gate primeiro):
```bash
.venv/bin/python -c "import engine, pathlib; p=pathlib.Path(engine.__file__).resolve(); cwd=pathlib.Path('.').resolve(); assert str(p).startswith(str(cwd)), p; print('OK', p)"
.venv/bin/pytest tests/engine/test_external_exec.py -q
```
Esperado: `ImportError` / `ModuleNotFoundError` (módulo não existe) → todos falham (RED).

### Step 0b.2 — Implementação mínima

Crie `engine/external_exec.py`:

```python
"""Fronteira de execução externa — engine → binário do projeto consumidor.

Decisão 33: caminho de execução dedicado pra binários externos (linters, build
tools), DISTINTO do sandbox de validators da Decisão 30. O sandbox de validators
é Python-only e hermético (sitecustomize.py preload); um binário externo não
passa pelo interpretador do forge, então esse hardening não o cobre. Aqui as
garantias são próprias e explícitas: env reduzido (build_safe_env), timeout com
estouro → degraded, skip-se-ausente (resolve_invocation → None), check=False
(classifica, não estoura), sem auto-fix, sem instalar toolchain.

GENÉRICO por design: este módulo só sabe rodar um argv e resolver candidatos de
invocação. Nada tool-específico (ktlint/gradle/swiftlint) vive aqui — isso é
responsabilidade dos callers (Fase 1, Tema 6).

Spec: docs/superpowers/specs/2026-06-30-native-quality-gates-design.md §3.
Pattern espelhado: engine/verify.py::_invoke_validator (env reduzido + timeout).
"""
from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from engine._sandbox.env import build_safe_env

# Mesmas extras do subprocess de validator (engine/verify.py:1024): toolchain
# Java/Android/Gradle precisa dessas pra rodar; nenhuma é sensitive.
_EXTERNAL_ENV_EXTRAS: tuple[str, ...] = ("JAVA_HOME", "ANDROID_HOME", "GRADLE_USER_HOME")

_DEFAULT_TIMEOUT = 120


@dataclass
class ExternalToolResult:
    """Resultado bruto de um binário externo. A semântica de veredito
    (warning vs fail, threshold por-projeto) é do caller (Fase 1)."""

    tool: str
    status: str  # "pass" | "fail" | "degraded" | "skipped"
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    skipped_reason: str = ""


def run_external_tool(
    argv: list[str],
    project_root: Path,
    *,
    timeout: int = _DEFAULT_TIMEOUT,
) -> ExternalToolResult:
    """Roda ``argv`` como binário externo no working tree do projeto.

    - ``check=False``: nunca estoura por exit code; classifica.
    - exit 0 → ``pass``; exit ≠ 0 → ``fail`` (mapping bruto; threshold é do caller).
    - ``TimeoutExpired`` → ``degraded`` (não estoura): um gate que não terminou
      nem reprova nem finge passar (filosofia "verde inerte" do Tema 6).
    - ``OSError`` (binário some/não-executável) → ``degraded``.
    - env reduzido via ``build_safe_env`` (não vaza segredos pro linter).
    - ``cwd = project_root`` (o gate vê os arquivos reais — read-only por contrato
      do caller, que escolhe só subcomandos de check; ver Decisão 33).
    """
    tool = argv[0] if argv else ""
    started = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=build_safe_env(extras=_EXTERNAL_ENV_EXTRAS),
            cwd=str(project_root),
        )
    except subprocess.TimeoutExpired:
        duration_ms = int((time.monotonic() - started) * 1000)
        return ExternalToolResult(
            tool=tool,
            status="degraded",
            exit_code=None,
            stdout="",
            stderr="",
            duration_ms=duration_ms,
            skipped_reason=f"timeout (>{timeout}s) — o gate não terminou; classifiquei como degraded, não fail",
        )
    except OSError as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        return ExternalToolResult(
            tool=tool,
            status="degraded",
            exit_code=None,
            stdout="",
            stderr=str(exc),
            duration_ms=duration_ms,
            skipped_reason=f"não consegui executar {tool!r}: {exc}",
        )

    duration_ms = int((time.monotonic() - started) * 1000)
    status = "pass" if proc.returncode == 0 else "fail"
    return ExternalToolResult(
        tool=tool,
        status=status,
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        duration_ms=duration_ms,
    )


def resolve_invocation(
    candidates: list[list[str] | str],
    project_root: Path,
) -> list[str] | None:
    """Resolve o primeiro candidato de invocação que existe, como argv.

    Candidatos em ordem de preferência (primeiro que resolver vence):

    - ``list[str]`` com primeiro elemento ``./...`` (wrapper relativo ao projeto,
      ex. ``["./gradlew", "task"]``) → resolve se ``project_root / first[2:]``
      é arquivo; retorna o argv inalterado.
    - ``list[str]`` com primeiro elemento path absoluto (ex. config bin) → resolve
      se o path existe; retorna inalterado.
    - ``list[str]`` com primeiro elemento nome simples → ``shutil.which``; se achar,
      retorna ``[resolved, *rest]``.
    - ``str`` (nome de tool) → ``shutil.which``; se achar, retorna ``[resolved]``.

    Nenhum resolve → ``None`` (skip-se-ausente — o caller emite o aviso
    mentor-calmo; o forge não reprova por ausência de toolchain).
    """
    for cand in candidates:
        argv = [cand] if isinstance(cand, str) else list(cand)
        if not argv:
            continue
        first = argv[0]
        if first.startswith("./"):
            if (project_root / first[2:]).is_file():
                return argv
            continue
        path = Path(first)
        if path.is_absolute():
            if path.exists():
                return argv
            continue
        resolved = shutil.which(first)
        if resolved:
            return [resolved, *argv[1:]]
    return None
```

E em `engine/_sandbox/env.py` (docstring do módulo, L3-9), adicione
`engine.external_exec` à lista de consumidores autorizados de `build_safe_env`:

```
- engine.external_exec  (fronteira de execução externa, Decisão 33)
```

**Rodar e ver passar:**
```bash
.venv/bin/pytest tests/engine/test_external_exec.py -q
```
Esperado: todos passam (GREEN).

### Step 0b.3 — Doc-sync + commit

Em `CHANGELOG.md`, sob `## [Unreleased] > ### Added`:

```markdown
- `engine/external_exec.py` — fronteira de execução externa genérica (Decisão
  33): `run_external_tool(argv, project_root, *, timeout)` roda binário do
  consumidor com env reduzido (`build_safe_env`), `check=False`, timeout com
  estouro → `degraded`; `resolve_invocation(candidates, project_root)` descobre
  o binário (wrapper `./...` → path de config → `which`) com skip-se-ausente
  (`None`). Base reusada pela Fase 1 (Tema 6 — gates nativos + build-only). Nada
  tool-específico mora aqui.
```

```bash
.venv/bin/pytest tests/engine/test_external_exec.py -q
git add engine/external_exec.py tests/engine/test_external_exec.py engine/_sandbox/env.py CHANGELOG.md
git commit -m "feat(external-exec): fronteira de execução externa genérica (Decisão 33)

run_external_tool + resolve_invocation: roda binário do consumidor com env
reduzido (build_safe_env), check=False, timeout→degraded, skip-se-ausente.
Espelha o env/timeout do _invoke_validator e melhora o pattern cru do upgrade.py
(que roda git sem env custom/timeout). Genérico — zero conhecimento de
ktlint/gradle (isso é Fase 1). TDD: pass/fail/timeout/oserror/env-reduzido/cwd +
resolve wrapper/config/which/none.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

**Done quando:** `tests/engine/test_external_exec.py` todos verdes; nenhum nome
de tool (ktlint/gradle/swiftlint) aparece em `external_exec.py` (grep confirma);
CHANGELOG atualizado; `engine.external_exec` listado em env.py.

---

## Task 0c — Investigação do verify-log (systematic-debugging)

**Objetivo:** confirmar EMPIRICAMENTE se os dois write-paths do verify-log
(`engine/verify.py::_write_verify_log_entry` e
`engine/memory/l1.py::append_verify_log`) escrevem no mesmo arquivo e se o
caminho do `verify.py` produz entradas que VIOLARIAM a validação do
`append_verify_log`. Depois, bater o martelo via **3-caminhos** com base no que o
teste observar — **NÃO assumir o veredito**.

Esta task é uma INVESTIGAÇÃO (`superpowers:systematic-debugging`), não um fix
cego. O scout aponta forte pro **Caminho A** (drift real), mas o implementador
**decide** a partir da observação do teste.

**Arquivos permitidos:** `tests/engine/test_verify_log_write_paths.py` (novo)
sempre; depois, condicional ao caminho (ver abaixo).

### Step 0c.1 — Teste de investigação (escrever PRIMEIRO, observar)

Crie `tests/engine/test_verify_log_write_paths.py`. O teste exercita AMBOS os
write-paths e verifica: (1) se escrevem no mesmo arquivo; (2) se a entrada que o
`verify.py` produz (scope dict + warnings list) seria REJEITADA por
`append_verify_log`.

```python
"""Investigação dos dois write-paths do verify-log (Fase 0c).

_write_verify_log_entry (engine/verify.py) serializa JSON DIRETO, sem validar.
append_verify_log (engine/memory/l1.py) VALIDA scope/result/warnings. O scout
indica que ambos escrevem no MESMO arquivo
(lifecycle_root(root)/slug/verify-log.jsonl). Este teste confirma a colisão e se
o caminho do verify.py produz entradas que append_verify_log rejeitaria.

Não assume o veredito — observa. O resultado dirige o 3-caminhos (A/B/C).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.memory.l1 import MemoryError, append_verify_log
from engine.utils.paths import lifecycle_root
from engine.verify import _write_verify_log_entry


def _read_log(root: Path, slug: str) -> list[dict]:
    p = lifecycle_root(root) / slug / "verify-log.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_both_paths_target_same_file(tmp_path: Path) -> None:
    slug = "feat-x"
    # Path 1: verify.py
    _write_verify_log_entry(
        tmp_path,
        feature_slug=slug,
        scope_type="task",
        scope_id="t1",
        validators=["v1"],
        result="pass",
        hard_fails=[],
        warnings_list=[],
    )
    log_after_verify = lifecycle_root(tmp_path) / slug / "verify-log.jsonl"
    assert log_after_verify.exists(), "verify.py deveria ter escrito o log"
    # Path 2: l1.append_verify_log com uma entrada VÁLIDA (scope string, sem degraded)
    append_verify_log(
        slug,
        tmp_path,
        {
            "verify-id": "verify-manual",
            "scope": "task",
            "validators-run": ["v2"],
            "result": "pass",
        },
    )
    entries = _read_log(tmp_path, slug)
    # Se colidem no mesmo arquivo, há 2 linhas agora.
    assert len(entries) == 2, f"esperava ambos no mesmo arquivo, vi {len(entries)}"


def test_verify_py_entry_shape_would_violate_append_validation(tmp_path: Path) -> None:
    """A entrada que verify.py monta (scope dict + warnings list) seria rejeitada
    por append_verify_log? Reconstrói a MESMA forma e passa por append_verify_log."""
    # Forma idêntica à de _write_verify_log_entry (verify.py:674-683):
    verify_shaped_entry = {
        "schema-version": 1,
        "verify-id": "verify-x",
        "at": "2026-06-30T00:00:00Z",
        "scope": {"type": "task", "id": "t1"},   # DICT, não string
        "validators-run": ["v1"],
        "result": "degraded",
        "hard-fails": [],
        "warnings": ["alguma ressalva"],          # LIST, não int
    }
    with pytest.raises(MemoryError):
        append_verify_log("feat-x", tmp_path, dict(verify_shaped_entry))
```

**Rodar e OBSERVAR** (worktree gate primeiro):
```bash
.venv/bin/python -c "import engine, pathlib; p=pathlib.Path(engine.__file__).resolve(); cwd=pathlib.Path('.').resolve(); assert str(p).startswith(str(cwd)), p; print('OK', p)"
.venv/bin/pytest tests/engine/test_verify_log_write_paths.py -q -v
```

**Interpretar a observação:**
- `test_both_paths_target_same_file` PASSA + `test_verify_py_entry_shape_would_violate_append_validation`
  PASSA → **Caminho A confirmado** (mesmo arquivo + verify.py bypassa validação que
  o rejeitaria). É o cenário provável pelo scout.
- `test_both_paths_target_same_file` FALHA (arquivos distintos) → **Caminho B**
  (sem cruzamento real).
- Qualquer observação fora dessas duas (ex.: a validação NÃO rejeita a forma do
  verify.py, ou aparece um terceiro arquivo) → **Caminho C** (escalar).

### Step 0c.2 — Bater o martelo (3-caminhos)

Apresente o veredito com base na observação. Exatamente três caminhos:

#### Caminho A — drift real (provável): consolidar via `append_verify_log` (DRY)

Quando o teste confirma mesmo-arquivo + bypass-de-validação.

**Fix:** rotear `_write_verify_log_entry` por `append_verify_log` — uma só
fronteira validada. O `verify.py` para de serializar JSON direto; mapeia seus
campos pra forma que `append_verify_log` aceita:
- `scope` dict `{"type": t, "id": i}` → o `type` cru (string) no campo validado
  `scope`, e o `id` num campo `scope-id` (preservado, não validado contra o enum);
- `warnings` (list) → manter a list pro registro humano, MAS quando
  `result=="degraded"`, passar também `warnings` como **int** (a CONTAGEM) pra
  satisfazer MEM-L1-VL-005 (`isinstance(warnings, int) and warnings >= 1`). O
  formato exato do payload final é decidido lendo a forma que `append_verify_log`
  serializa (l1.py:967-1008) e preservando os campos humanos sob chaves que não
  colidem com a validação.

**Regression test** (`tests/engine/test_verify_log_consolidation.py`, novo):
- escrever via `_write_verify_log_entry` com `result="degraded"` + ≥1 warning →
  a linha persistida agora PASSA pela validação (não levanta `MemoryError`), e
  relê com `scope` na forma validável + `scope-id` preservado;
- escrever com `result="pass"` + scope `feature` → linha válida, sem perda de info.
- O teste FALHA contra o código atual (RED) antes do fix; PASSA depois (GREEN).

Cadência: escrever o regression test → ver falhar → editar `_write_verify_log_entry`
pra delegar → ver passar → rodar a lane de verify inteira pra garantir zero regressão:
```bash
.venv/bin/pytest tests/engine/test_verify_log_consolidation.py tests/engine/test_verify_log_write_paths.py -q
.venv/bin/pytest tests/engine/ -m "not integration and not e2e" -q
```
Doc-sync: entrada no `CHANGELOG.md > [Unreleased] > ### Fixed` descrevendo a
consolidação (verify.py passa a validar o verify-log via append_verify_log,
fechando o bypass).

**Arquivos (Caminho A):** `engine/verify.py`,
`tests/engine/test_verify_log_consolidation.py`,
`tests/engine/test_verify_log_write_paths.py`, `CHANGELOG.md`.

#### Caminho B — sem cruzamento: documentar a intenção, sem mudança de comportamento

Quando o teste mostra arquivos/paths distintos (sem colisão real).

**Ação:** ajustar o teste de investigação pra refletir a realidade observada
(asserir que NÃO colidem) e adicionar docstring em AMBAS as funções
(`_write_verify_log_entry` e `append_verify_log`) explicitando o porquê de dois
caminhos (qual escreve onde, qual valida o quê) — pra o próximo leitor não
reabrir a dúvida. SEM mudança de comportamento de produção.
```bash
.venv/bin/pytest tests/engine/test_verify_log_write_paths.py -q
```
Doc-sync: entrada no `CHANGELOG.md > [Unreleased] > ### Changed` (doc-only) ou
nota no commit body. **Arquivos (Caminho B):** `engine/verify.py` (docstring),
`engine/memory/l1.py` (docstring), `tests/engine/test_verify_log_write_paths.py`,
`CHANGELOG.md`.

#### Caminho C — escalar

Se a investigação revelar algo fora do escopo da Fase 0 (ex.: a validação tem um
bug próprio, ou há um terceiro consumidor do log com outra forma, ou o fix do
Caminho A toca contratos de schema MEM-L1-VL-* que exigem decisão de produto):
PARAR, registrar o achado, e escalar ao usuário com 3-caminhos próprios (não
fix-forward cego). `systematic-debugging` exige hipótese confirmada antes do fix.

### Step 0c.3 — Commit da task

Commitar conforme o caminho batido (A inclui o fix + regression; B é doc-only; C
não commita fix, só o teste de investigação + o registro do escalonamento):

```bash
# Exemplo do Caminho A:
git add engine/verify.py tests/engine/test_verify_log_consolidation.py tests/engine/test_verify_log_write_paths.py CHANGELOG.md
git commit -m "fix(verify-log): consolida _write_verify_log_entry via append_verify_log (DRY)

Investigação (systematic-debugging) confirmou que os dois write-paths escrevem
no MESMO arquivo (lifecycle_root/slug/verify-log.jsonl) e que verify.py bypassava
a validação de append_verify_log (scope dict + warnings list seriam rejeitados).
Roteia verify.py pela fronteira validada; regression test cobre degraded+warnings
e pass+feature. Fecha o smell de validação assimétrica.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

**Done quando:** o teste de investigação documenta a realidade observada; o
caminho batido está justificado pela observação (não por suposição); se Caminho
A, a lane de verify (`tests/engine/ -m "not integration and not e2e"`) está verde
sem regressão de count; doc-sync no mesmo commit.

---

## Gates / definition of done (Fase 0)

- **Por task:** `.venv/bin/pytest` verde na lane relevante; commit único por task
  com a mensagem prescrita; doc-sync no mesmo commit ao tocar engine/hooks/docs.
- **0a:** os 3 casos do test de cerimônia verdes; o próprio commit da 0a passou
  pelo hook (prova viva); append-only + texto literal "Nova decisão 33:".
- **0b:** todos os testes de `external_exec` verdes; `external_exec.py` 100%
  genérico (grep por `ktlint|gradle|swiftlint|detekt` em `external_exec.py` → 0).
- **0c:** veredito batido a partir da observação do teste; se Caminho A, regression
  test verde + lane de verify sem regressão.
- **Fim da Fase 0 (antes de devolver ao orquestrador):** lane rápida inteira
  verde — `.venv/bin/pytest -m "not integration and not e2e" -q | tail -1` — com
  count ≥ baseline (sem regressão sem justificativa no commit body). A Fase 0 NÃO
  faz push; o orquestrador faz o checkpoint de merge/push (verificando
  `gh auth = thgMatajs`).

## Riscos & decisões em aberto

- **0c pode degradar pra doc (Caminho B)** se a investigação mostrar paths
  distintos — é resultado legítimo, não falha. O plano não força o fix.
- **Worktree + editable-install trap:** o gate `engine.__file__` é obrigatório em
  cada task antes de rodar testes; sem ele, os testes rodam contra o repo
  principal silenciosamente (false-pass).
- **O hook 0a é load-bearing** (`.claude/hooks/`): o reviewer foca em append-only,
  texto literal e no fato de o block sem-cerimônia continuar firme.

## Cross-refs

- Spec da campanha: `docs/superpowers/specs/2026-06-30-aifirst-pendencias-campaign-design.md` §4 Fase 0.
- Spec irmã (fronteira externa): `docs/superpowers/specs/2026-06-30-native-quality-gates-design.md` §1/§2/§3/§5.
- Decisões 30/31 (sandbox Python-only): `docs/design/01-decisions.md`.
- Pattern subprocess: `engine/verify.py::_invoke_validator`; pattern a melhorar: `engine/upgrade.py::_git_fetch/_git_checkout`.
- Env reduzido: `engine/_sandbox/env.py::build_safe_env`.
- verify-log: `engine/verify.py::_write_verify_log_entry` + `engine/memory/l1.py::append_verify_log`.
