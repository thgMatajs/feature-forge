# W-GRAPH: Graph-First for Consumers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax.

**Goal:** Tornar o `.claude/graph.db` descobrível e usável por projetos CONSUMIDORES. Hoje o `forge init` constrói o graph (Step 11, `engine/init.py:1543`) mas nunca ensina o consumidor a usá-lo — o grafo nasce órfão (NO-ONBOARDING, auditoria-consolidada §5/§6 P1). Esta wave adiciona três camadas ADITIVAS — uma instrução persistente em disco, um lembrete no session hook, e uma skill de referência — sem tocar a construção do grafo nem o renderer.

**Architecture:** As três camadas são puramente aditivas e não alteram nenhum comportamento existente. Camada 1 e 3 são dois arquivos `.md` escritos por um novo step de `forge init` (após o Step 11.6, antes do checkpoint `step-12-write-config` em `engine/init.py:1611`), usando `ensure_dir(forge_dir(project_root))` — o sub-namespace canônico `.claude/forge/` (Spec §2, `engine/utils/paths.py:241`). Camada 2 vive no shell hook `hooks/session-start-drift-check.sh` (NÃO no engine): é uma decisão de design deliberada — manter o lembrete no shell preserva a natureza aditiva e não colide com trabalho futuro no renderer host-aware. O hook é self-contained e host-aware (emoji se TTY e sem `$CLAUDECODE`, senão prefixo ASCII `[graph]`), guarda atrás de `[ -f "$PROJECT_ROOT/.claude/graph.db" ]`, e escreve em stderr (a sessão sempre começa, exit 0).

**Tech Stack:** Python 3.13 + Bash dispatcher + YAML/MD specs; pytest (`.venv/bin/pytest`). Arquivos gerados são Markdown com voz mentor calmo.

## Global Constraints

- **Test runner:** `.venv/bin/pytest` (NUNCA o pytest do sistema — só o `.venv` da worktree tem json5+deps e aponta pro `engine/` da worktree; system pytest dá false fails contra o source errado).
- **Baseline atual:** rapid **1708** / integration **175** / e2e **30**; counts não caem sem justificativa. Re-confirme com `.venv/bin/pytest -m "not integration and not e2e" -q | tail -1`.
- **Mandamento 0:** cada task é executada por subagente — cada uma carrega Files permitidos + critério de sucesso testável + anti-padrões.
- **Decisão 22 (load-bearing):** zero runtime deps em outras skills. Os arquivos `.md` gerados (`GRAPH-FIRST.md`, `graph-skill.md`) são instruções de comportamento pro host — o `engine/` NÃO os importa. A skill de referência ensina o host a invocar `forge graph --json`, não vira import.
- **Voz mentor calmo** nos artefatos gerados. `forge verify` sem hard fail. Doc-sync no fim (Task 4).
- **Reuso (Mandamento 3):** `forge_dir`/`ensure_dir`/`graph_db_path` já existem (`engine/utils/paths.py:235-294`) e já estão importados em `engine/init.py:74-84` — wire, não reescreve. O catálogo de queries (`q1`..`q17`, `r`) já vive em `engine/graph_cli.py:270-289` (`_HANDLERS`) — os arquivos `.md` espelham os labels canônicos de lá, não inventam queries novas.

---

### Task 1: Escrever os dois `.md` no `forge init` (Camadas 1 + 3)

Adicionar um novo step no `_run_pipeline` de `engine/init.py` (após o Step 11.6, antes do checkpoint `step-12-write-config` em `engine/init.py:1611`) que escreve `.claude/forge/GRAPH-FIRST.md` (instrução persistente) e `.claude/forge/graph-skill.md` (skill de referência). Ambos via `ensure_dir(forge_dir(project_root))`.

**Reuse-check (grep engine/ + leitura):** `forge_dir`/`ensure_dir`/`graph_db_path` já existem em `engine/utils/paths.py` e já estão importados em `engine/init.py:74-84` (confirmado: linha 1644 já usa `ensure_dir(forge_dir(project_root))`, linha 1586 usa `forge_hooks_dir`). O catálogo de queries é o `_HANDLERS` de `engine/graph_cli.py:270-289` — os labels nos `.md` (similar-features, blast-radius, orphan-files, symbols, routes, di-deps, tests-for, reusable-helpers, dup-within-module, dup-cross-module, kmp-migration, reuse-findings) são cópia verbatim dos labels de lá. Nenhum helper novo de path ou query é criado — só duas constantes de texto + um helper de escrita.

**Files:**
- Modify `engine/init.py` — adicionar dois module-level string constants (`_GRAPH_FIRST_MD` e `_GRAPH_SKILL_MD`) perto dos outros templates de texto + um helper `_write_graph_docs(project_root: Path) -> tuple[Path, Path]` + um novo step que o chama dentro de `_run_pipeline`, inserido logo após o bloco do Step 11.6 (após `engine/init.py:1609`, antes do `checkpoint.step = "step-12-write-config"` em `engine/init.py:1611`).
- Create `tests/integration/test_init_graph_docs.py`

**Interfaces:**
- Produces `engine.init._write_graph_docs(project_root: Path) -> tuple[Path, Path]` — escreve `GRAPH-FIRST.md` e `graph-skill.md` em `.claude/forge/`, retornando os dois paths (na ordem `(graph_first, graph_skill)`). Idempotente: re-escreve o conteúdo canônico (canonical wins) — não anexa.
- Consumes `engine.utils.paths.forge_dir(project_root: Path) -> Path` (existente, `engine/utils/paths.py:241`).
- Consumes `engine.utils.paths.ensure_dir(path: Path) -> Path` (existente, `engine/utils/paths.py:235`).
- Produces `engine.init._GRAPH_FIRST_MD: str` — conteúdo verbatim do `.claude/forge/GRAPH-FIRST.md`.
- Produces `engine.init._GRAPH_SKILL_MD: str` — conteúdo verbatim do `.claude/forge/graph-skill.md`.

#### Step 1.1 — Teste de integração falhando

- [ ] Escrever `tests/integration/test_init_graph_docs.py`:

```python
"""Graph-first docs escritos por forge init (W-GRAPH Camadas 1+3).

Cobre: forge init escreve .claude/forge/GRAPH-FIRST.md + graph-skill.md com
markers de conteúdo esperados; idempotência (canonical wins, sem append).

Refs: docs/reports/auditoria-consolidada-2026-06-17.md §5/§6 (NO-ONBOARDING P1)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import init as forge_init


pytestmark = pytest.mark.integration


def test_write_graph_docs_creates_both_files(tmp_forge_project: Path) -> None:
    graph_first, graph_skill = forge_init._write_graph_docs(tmp_forge_project)
    assert graph_first == tmp_forge_project / ".claude" / "forge" / "GRAPH-FIRST.md"
    assert graph_skill == tmp_forge_project / ".claude" / "forge" / "graph-skill.md"
    assert graph_first.is_file()
    assert graph_skill.is_file()


def test_graph_first_has_expected_markers(tmp_forge_project: Path) -> None:
    graph_first, _ = forge_init._write_graph_docs(tmp_forge_project)
    body = graph_first.read_text(encoding="utf-8")
    # Regra graph-first + quick-start das 5 queries de orientação.
    assert "graph first" in body.lower()
    assert "forge graph --json" in body
    for query in ("q1", "q2", "q3", "q4", "q8"):
        assert query in body, query


def test_graph_skill_has_task_query_table(tmp_forge_project: Path) -> None:
    _, graph_skill = forge_init._write_graph_docs(tmp_forge_project)
    body = graph_skill.read_text(encoding="utf-8")
    # Tabela tarefa→query→exemplo cobrindo o catálogo + a seção "quando NÃO usar".
    for query in ("q1", "q2", "q3", "q4", "q7", "q8", "q9", "q11", "q12", "q13", "q14"):
        assert query in body, query
    assert "reuse-findings" in body  # alias `r`
    assert "quando NÃO usar" in body.lower() or "quando não usar" in body.lower()
    # Os três casos de "leia o source direto".
    assert "Grep" in body
    assert "Read" in body


def test_write_graph_docs_idempotent(tmp_forge_project: Path) -> None:
    graph_first, graph_skill = forge_init._write_graph_docs(tmp_forge_project)
    first_a = graph_first.read_text(encoding="utf-8")
    first_b = graph_skill.read_text(encoding="utf-8")
    forge_init._write_graph_docs(tmp_forge_project)  # 2ª escrita
    assert graph_first.read_text(encoding="utf-8") == first_a  # sem append/clobber divergente
    assert graph_skill.read_text(encoding="utf-8") == first_b
```

- [ ] Rodar e ver FAIL (função não existe):

```bash
.venv/bin/pytest tests/integration/test_init_graph_docs.py -q
```

Esperado: `AttributeError: module 'engine.init' has no attribute '_write_graph_docs'` → todos os casos em ERROR.

#### Step 1.2 — Adicionar `_GRAPH_FIRST_MD` (conteúdo verbatim da Camada 1)

- [ ] Em `engine/init.py`, adicionar o module-level string constant abaixo (perto dos outros templates de texto do módulo, antes do `_run_pipeline`). Conteúdo COMPLETO do `.claude/forge/GRAPH-FIRST.md`:

```python
_GRAPH_FIRST_MD = """\
# Graph-first — consulte o grafo antes de ler o source

> Instalado por `forge init`. Voz: mentor calmo.

Este projeto tem um codebase graph em `.claude/graph.db` (SQLite, WAL mode)
com símbolos, imports, body-text e dependências. **Antes de ler arquivos
fonte pra entender o projeto, consulte o grafo** — ele responde em uma
chamada o que custaria várias leituras de arquivo, e protege seu contexto.

## A regra

1. Vai mexer/entender uma área do código? Pergunte ao grafo primeiro.
2. O grafo respondeu com o que você precisava? Use a resposta — não abra o
   arquivo "só pra confirmar".
3. O grafo não cobre o que você precisa (string literal exata, contexto
   multi-linha, arquivo pedido explicitamente)? Aí sim leia o source.

A skill de referência completa — tabela tarefa→query→exemplo — está em
`.claude/forge/graph-skill.md`.

## Quick-start (as 5 queries de orientação)

Todas as queries rodam em modo non-interactive com `forge graph --json <query>`:

```bash
# q1 — features similares por slug (antes de criar uma feature nova)
forge graph --json q1 <slug>

# q2 — blast radius de um ou mais arquivos (o que quebra se eu mexer aqui?)
forge graph --json q2 path/to/File.kt [outro/Arquivo.swift ...]

# q3 — arquivos órfãos (sem referências de entrada)
forge graph --json q3

# q4 — símbolos de um módulo (o que esse módulo expõe?)
forge graph --json q4 <module>

# q8 — dependências de DI de uma classe (o que essa classe injeta?)
forge graph --json q8 <ClassName>
```

`<query>` aceita as três formas: numérica (`1`..`17`, `r`), com prefixo
(`q1`..`q17`, `qr`), ou o label textual (`orphan-files`, `blast-radius`, …).
O catálogo completo está em `.claude/forge/graph-skill.md`.

## Quando NÃO usar o grafo

- Precisa do texto exato de uma string literal ou comentário → use `Grep`.
- Precisa de contexto de múltiplas linhas em torno de um símbolo → use `Read`.
- O usuário pediu explicitamente "leia o arquivo X" → leia o arquivo.

Fora desses três casos: **grafo primeiro.**
"""
```

#### Step 1.3 — Adicionar `_GRAPH_SKILL_MD` (conteúdo verbatim da Camada 3)

- [ ] Em `engine/init.py`, adicionar o segundo module-level string constant (logo após `_GRAPH_FIRST_MD`). Conteúdo COMPLETO do `.claude/forge/graph-skill.md`:

```python
_GRAPH_SKILL_MD = """\
# Graph skill — tarefa → query → exemplo

> Instalado por `forge init`. Voz: mentor calmo. Referência das 17 graph
> queries canônicas + o alias combinado `r`.

O grafo (`.claude/graph.db`) responde perguntas estruturais sobre o código
sem você abrir os arquivos. Toda query roda em modo non-interactive:

```bash
forge graph --json <query> [args...]
```

`<query>` aceita três grafias equivalentes:

- **Numérica:** `1`..`17`, `r`
- **Prefixo:** `q1`..`q17`, `qr`
- **Label textual:** `orphan-files`, `blast-radius`, `symbols`, …

## Tabela tarefa → query → exemplo

| Quero… | Query | Exemplo |
|---|---|---|
| Ver se já existe feature parecida | `q1` (similar-features) | `forge graph --json q1 lembrete-de-rega` |
| Saber o que quebra se eu mexer aqui | `q2` (blast-radius) | `forge graph --json q2 app/src/Login.kt` |
| Achar arquivos órfãos (dead code candidato) | `q3` (orphan-files) | `forge graph --json q3` |
| Listar símbolos de um módulo | `q4` (symbols) | `forge graph --json q4 :feature:auth` |
| Achar rotas de uma feature | `q7` (routes) | `forge graph --json q7 checkout` |
| Ver dependências de DI de uma classe | `q8` (di-deps) | `forge graph --json q8 LoginViewModel` |
| Achar os testes que cobrem um arquivo | `q9` (tests-for) | `forge graph --json q9 app/src/Login.kt` |
| Achar helper reusável antes de criar um | `q11` (reusable-helpers) | `forge graph --json q11` |
| Ver duplicação dentro do mesmo módulo | `q12` (dup-within-module) | `forge graph --json q12` |
| Ver duplicação entre módulos | `q13` (dup-cross-module) | `forge graph --json q13` |
| Ver candidatos a migração KMP | `q14` (kmp-migration) | `forge graph --json q14` |
| Ver todos os achados de reuso combinados | `r` (reuse-findings) | `forge graph --json r` |

## Reuso antes de criar (Mandamento 3)

Antes de escrever helper/função novo, rode `q11` (reusable-helpers) e `r`
(reuse-findings combinado, cobre `q12`/`q13`/`q14`). Se o grafo aponta um
equivalente, use-o; se aponta near-duplicate, decida entre consolidar,
promover pra shared, ou criar novo com justificativa.

## Quando NÃO usar o grafo

O grafo é estrutural — ele sabe quem chama quem, quem expõe o quê, e onde
há duplicação. Ele NÃO substitui ler o source quando:

- **String literal exata** — precisa do texto cru de uma mensagem,
  comentário ou constante? Use `Grep`.
- **Contexto multi-linha** — precisa entender o corpo de uma função, várias
  linhas em torno de um símbolo? Use `Read`.
- **Arquivo pedido explicitamente** — o usuário disse "leia o arquivo X"?
  Leia o arquivo X.

Fora desses três: **grafo primeiro** — é mais rápido e barato em contexto.
"""
```

#### Step 1.4 — Impl `_write_graph_docs` + wire no `_run_pipeline`

- [ ] Em `engine/init.py`, adicionar o helper de escrita (perto dos outros helpers de install do módulo, antes do `_run_pipeline`):

```python
def _write_graph_docs(project_root: Path) -> tuple[Path, Path]:
    """Escreve os docs graph-first no sub-namespace `.claude/forge/`.

    Camadas 1 + 3 (W-GRAPH): GRAPH-FIRST.md ensina a regra "consulte o grafo
    antes de ler o source"; graph-skill.md é a referência tarefa→query→exemplo.
    Canonical wins — re-escreve o conteúdo a cada init (idempotente).
    """
    forge_root = ensure_dir(forge_dir(project_root))
    graph_first = forge_root / "GRAPH-FIRST.md"
    graph_skill = forge_root / "graph-skill.md"
    graph_first.write_text(_GRAPH_FIRST_MD, encoding="utf-8")
    graph_skill.write_text(_GRAPH_SKILL_MD, encoding="utf-8")
    return graph_first, graph_skill
```

- [ ] Em `_run_pipeline`, inserir o novo step **logo após o bloco do Step 11.6** (após o `renderer.write(...)` que fecha em `engine/init.py:1609`) e **antes** do `checkpoint.step = "step-12-write-config"` (`engine/init.py:1611`):

```python
    # ── Step 11.7 — Graph-first docs (W-GRAPH) ──────────────────────────────
    # Ensina o consumidor a usar o graph.db recém-construído (Steps 11/11.5).
    # Sem este step, o grafo nasce órfão (NO-ONBOARDING, auditoria §5/§6 P1).
    graph_first, _graph_skill = _write_graph_docs(project_root)
    renderer.write(
        f"  · graph-first docs em `{graph_first.parent.relative_to(project_root)}/` "
        "(GRAPH-FIRST.md + graph-skill.md)"
    )
```

- [ ] Rodar e ver PASS:

```bash
.venv/bin/pytest tests/integration/test_init_graph_docs.py -q
```

Esperado: 4 passed.

#### Step 1.5 — Regression guard + commit

- [ ] Confirmar que o resto da suite de init não regrediu (o step é aditivo):

```bash
.venv/bin/pytest tests/integration/ -k init -q | tail -3
```

Esperado: 0 failed (os testes de init greenfield/brownfield/settings continuam verdes).

- [ ] Confirmar a lane rápida intacta:

```bash
.venv/bin/pytest -m "not integration and not e2e" -q | tail -1
```

Esperado: `1708 passed` (ou mais), 0 failed.

- [ ] Commit atômico:

```bash
git add engine/init.py tests/integration/test_init_graph_docs.py
git commit -m "feat(init): graph-first docs pro consumidor (W-GRAPH Camadas 1+3)"
```

**Anti-padrões (NÃO fazer):**
- Não tocar o Step 11 (build do grafo) nem o Step 11.5/11.6 — o novo step é aditivo, vem depois.
- Não importar nada de skills/agents no `engine/` (Decisão 22) — os `.md` são instruções pro host, não imports.
- Não inventar queries fora do `_HANDLERS` de `engine/graph_cli.py:270-289` — os labels nos `.md` espelham os de lá.
- Não fazer doc-sync aqui (é a Task 4).
- Não tocar `hooks/` nesta task (é a Task 2).

---

### Task 2: Lembrete graph-first no session hook (Camada 2)

Editar `hooks/session-start-drift-check.sh` pra imprimir 2-3 linhas (após a chamada de `forge ingest`) sobre o `graph.db` disponível + `forge graph --json <query>` + a regra graph-first. Host-aware e self-contained no shell, guardado por `[ -f "$PROJECT_ROOT/.claude/graph.db" ]`, saída em stderr, exit 0 preservado.

**Reuse-check:** o hook já resolve `PROJECT_ROOT` via `git rev-parse --show-toplevel` (`hooks/session-start-drift-check.sh:16`) e já tem a guarda de projeto-forge (`[[ ! -d "$PROJECT_ROOT/.claude" ]]`, linha 17). O lembrete reusa `$PROJECT_ROOT`, adiciona só a guarda do `graph.db` + a detecção de TTY. Nenhum helper de engine envolvido (decisão de design: fica no shell pra ser aditivo e não colidir com o renderer host-aware futuro).

**Files:**
- Modify `hooks/session-start-drift-check.sh` — inserir o bloco do lembrete entre a chamada de `forge ingest` (`hooks/session-start-drift-check.sh:22-23`) e o `exit 0` final (`hooks/session-start-drift-check.sh:24`).
- Create `tests/integration/test_session_start_graph_reminder.py`

**Interfaces:** N/A (shell hook — sem símbolo Python). O contrato observável é: emite 2-3 linhas em stderr quando `.claude/graph.db` existe; silêncio quando não existe; exit 0 sempre.

#### Step 2.1 — Teste de integração falhando

- [ ] Escrever `tests/integration/test_session_start_graph_reminder.py`. Cobre dois ângulos: (a) o conteúdo instalado do script tem as linhas-chave; (b) invocação real do hook via bash com `graph.db` presente/ausente:

```python
"""Lembrete graph-first no session hook (W-GRAPH Camada 2).

Cobre: o hook instalado contém o bloco do lembrete (string assert no
conteúdo); invocação real via bash emite o lembrete em stderr quando
.claude/graph.db existe e fica silencioso quando não existe; exit 0 sempre.

Refs: docs/reports/auditoria-consolidada-2026-06-17.md §6 P1 (NO-ONBOARDING)
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration

# FORGE_HOME desta worktree — o hook canônico vive aqui.
_HOOK = Path(__file__).resolve().parents[2] / "hooks" / "session-start-drift-check.sh"


def test_hook_source_has_graph_reminder_block() -> None:
    body = _HOOK.read_text(encoding="utf-8")
    # Guarda do graph.db + comando + regra graph-first + prefixo ASCII fallback.
    assert ".claude/graph.db" in body
    assert "forge graph --json" in body
    assert "[graph]" in body  # prefixo ASCII (host não-TTY / CLAUDECODE)


def _run_hook(project_root: Path) -> subprocess.CompletedProcess[str]:
    # FORGE_BIN aponta pra um stub que não faz nada (isola o lembrete do ingest
    # real); CLAUDECODE força o branch ASCII (determinístico, sem depender de TTY).
    stub = project_root / "forge-stub.sh"
    stub.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    stub.chmod(0o755)
    env = {
        "PATH": "/usr/bin:/bin",
        "FORGE_BIN": str(stub),
        "CLAUDECODE": "1",
    }
    return subprocess.run(
        ["bash", str(_HOOK)],
        capture_output=True,
        text=True,
        cwd=project_root,
        env=env,
    )


def test_hook_emits_reminder_when_graph_db_present(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "graph.db").write_text("", encoding="utf-8")
    result = _run_hook(tmp_path)
    assert result.returncode == 0
    assert "[graph]" in result.stderr
    assert "forge graph --json" in result.stderr


def test_hook_silent_when_graph_db_absent(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".claude").mkdir()  # projeto forge, mas sem graph.db
    result = _run_hook(tmp_path)
    assert result.returncode == 0
    assert "[graph]" not in result.stderr
```

- [ ] Rodar e ver FAIL (bloco ainda não existe no script):

```bash
.venv/bin/pytest tests/integration/test_session_start_graph_reminder.py -q
```

Esperado: `test_hook_source_has_graph_reminder_block` e `test_hook_emits_reminder_when_graph_db_present` FALHAM (string `[graph]` ausente; stderr sem o lembrete); `test_hook_silent_when_graph_db_absent` já passa (silêncio é o estado atual).

#### Step 2.2 — Impl do bloco do lembrete no hook

- [ ] Em `hooks/session-start-drift-check.sh`, inserir o bloco abaixo **entre** a chamada de `forge ingest` (que termina em `hooks/session-start-drift-check.sh:23`) e o `exit 0` final (`hooks/session-start-drift-check.sh:24`). O conteúdo COMPLETO a inserir:

```bash
# ── Graph-first reminder (W-GRAPH Camada 2) ──────────────────────────────────
# Lembra o host que o graph.db está disponível e como consultá-lo. Self-contained
# no shell (aditivo, não colide com o renderer host-aware). Saída em stderr; a
# sessão sempre começa. Silencioso quando o grafo ainda não foi construído.
if [[ -f "$PROJECT_ROOT/.claude/graph.db" ]]; then
    # Host-aware: emoji só em TTY interativo fora do Claude Code; senão ASCII.
    if [[ -t 1 && -z "${CLAUDECODE:-}" ]]; then
        _g_prefix="🔎 graph"
    else
        _g_prefix="[graph]"
    fi
    {
        echo "$_g_prefix codebase graph disponível em .claude/graph.db — consulte antes de ler o source."
        echo "$_g_prefix queries: forge graph --json <q1 similar | q2 blast-radius | q3 orphans | q4 symbols | q8 di-deps>"
        echo "$_g_prefix referência completa: .claude/forge/graph-skill.md"
    } >&2
fi
```

- [ ] Validar a sintaxe do shell (não deve ter erro):

```bash
bash -n hooks/session-start-drift-check.sh
```

Esperado: sem output (sintaxe OK).

- [ ] Rodar e ver PASS:

```bash
.venv/bin/pytest tests/integration/test_session_start_graph_reminder.py -q
```

Esperado: 3 passed.

#### Step 2.3 — Regression guard + commit

- [ ] Confirmar que os testes de hook existentes não regrediram:

```bash
.venv/bin/pytest tests/integration/ -k hook -q | tail -3
```

Esperado: 0 failed (o `test_git_hook_delegator` e companhia continuam verdes — o bloco é aditivo e guardado).

- [ ] Commit atômico:

```bash
git add hooks/session-start-drift-check.sh tests/integration/test_session_start_graph_reminder.py
git commit -m "feat(hooks): lembrete graph-first no session-start hook (W-GRAPH Camada 2)"
```

**Anti-padrões (NÃO fazer):**
- Não mover o lembrete pro engine — a decisão de design é mantê-lo no shell (aditivo, sem colidir com o renderer).
- Não remover a guarda `[[ -f "$PROJECT_ROOT/.claude/graph.db" ]]` — sem ela o hook fala de um grafo que não existe.
- Não trocar o `exit 0` final nem mexer no `set -euo pipefail` / na chamada de ingest.
- Não escrever em stdout — o contrato do hook é stderr (a sessão sempre começa).
- Não fazer doc-sync aqui (é a Task 4).

---

### Task 3: Smoke da integração das três camadas

Garantir, num único teste de integração, que após `_write_graph_docs` os dois arquivos coexistem com o hook e que o `graph-skill.md` referenciado pelo hook (`.claude/forge/graph-skill.md`) é exatamente o que o init escreve — fechando a costura Camada 2 ↔ Camada 3.

**Reuse-check:** reusa `forge_init._write_graph_docs` (Task 1) e o conteúdo `_GRAPH_SKILL_MD` (Task 1). Sem novos símbolos de produção — só um teste de costura.

**Files:**
- Modify `tests/integration/test_init_graph_docs.py` — adicionar um teste de costura (mesmo arquivo da Task 1, não cria arquivo novo).

**Interfaces:** N/A (teste-only).

#### Step 3.1 — Teste de costura Camada 2 ↔ Camada 3

- [ ] Adicionar ao fim de `tests/integration/test_init_graph_docs.py` (o arquivo já existe da Task 1):

```python
def test_skill_file_path_matches_hook_reference(tmp_forge_project: Path) -> None:
    """A costura Camada 2 ↔ 3: o path que o hook cita é o que o init escreve.

    O hook (Camada 2) imprime 'referência completa: .claude/forge/graph-skill.md'.
    Este teste garante que esse path é exatamente onde o init grava o arquivo —
    sem essa amarração, o hook apontaria pra um arquivo inexistente.
    """
    _, graph_skill = forge_init._write_graph_docs(tmp_forge_project)
    rel = graph_skill.relative_to(tmp_forge_project)
    assert rel.as_posix() == ".claude/forge/graph-skill.md"
    # O conteúdo escrito é o constant canônico (não um stub divergente).
    assert graph_skill.read_text(encoding="utf-8") == forge_init._GRAPH_SKILL_MD
```

- [ ] Rodar e ver PASS:

```bash
.venv/bin/pytest tests/integration/test_init_graph_docs.py -q
```

Esperado: 5 passed (os 4 da Task 1 + este).

#### Step 3.2 — Commit

- [ ] Commit atômico:

```bash
git add tests/integration/test_init_graph_docs.py
git commit -m "test(init): costura Camada 2↔3 — path do graph-skill.md bate com o hook (W-GRAPH)"
```

**Anti-padrões (NÃO fazer):**
- Não criar um arquivo de teste novo — estender o da Task 1.
- Não duplicar a string do hook no teste Python (o teste do hook em si vive na Task 2); aqui só amarramos o path.
- Não fazer doc-sync aqui (é a Task 4).

---

### Task 4: Doc-sync (Mandamento 6) — por último

Sincronizar CHANGELOG + handoff + pending. Reflete o que as Tasks 1-3 entregaram. README só se stats mudaram (não mudam — nenhum card/template/validator/comando novo).

**Files:**
- Modify `CHANGELOG.md` — `## [Unreleased]`: `### Added` (graph-first docs no init + lembrete no session hook).
- Modify `docs/design/08-session-handoff.md` — `**Última atualização:**` = 2026-06-17 + `**Estado:**` reflete W-GRAPH.
- Modify `docs/design/04-pending.md` — registrar o gap "graph órfão pra consumidores" (NO-ONBOARDING, auditoria §5/§6 P1) como **fechado nesta wave** numa entrada nova; ele NÃO está tracked com ID próprio em 04-pending (vem da auditoria), então NÃO usar strike-through de item inexistente.

**Interfaces:** N/A (doc-only).

#### Step 4.1 — CHANGELOG

- [ ] Em `CHANGELOG.md` sob `## [Unreleased]`, na seção `### Added` (criar a seção se não existir sob Unreleased):

```markdown
### Added
- Graph-first pro consumidor (W-GRAPH): `forge init` agora escreve
  `.claude/forge/GRAPH-FIRST.md` (regra "consulte o grafo antes de ler o
  source" + quick-start das queries q1/q2/q3/q4/q8) e
  `.claude/forge/graph-skill.md` (tabela tarefa→query→exemplo cobrindo o
  catálogo `q1`..`q17`+`r`, aliases aceitos, e a seção "quando NÃO usar o
  grafo"). Fecha o NO-ONBOARDING do grafo — antes o `forge init` construía o
  `graph.db` mas nunca ensinava o consumidor a usá-lo (grafo órfão).
- Lembrete graph-first no `hooks/session-start-drift-check.sh`: quando
  `.claude/graph.db` existe, o hook emite 2-3 linhas em stderr lembrando que
  o grafo está disponível + como consultá-lo. Host-aware (emoji em TTY, `[graph]`
  ASCII fora) e guardado pela presença do grafo.
```

#### Step 4.2 — Handoff + pending

- [ ] `docs/design/08-session-handoff.md`: atualizar `**Última atualização:** 2026-06-17 (W-GRAPH — graph-first pro consumidor)` e `**Estado:**` refletindo que o grafo agora é descobrível/usável pelo consumidor (3 camadas aditivas: doc persistente, lembrete no session hook, skill de referência). Adicionar linha na tabela de categorias se houver pattern de wave; senão só atualizar os dois campos canônicos.

- [ ] `docs/design/04-pending.md`: o gap "graph órfão pra consumidores" (NO-ONBOARDING, da `docs/reports/auditoria-consolidada-2026-06-17.md` §5/§6 P1 item 6 "SessionStart pointer") NÃO está tracked com ID próprio em 04-pending — registrá-lo numa **entrada nova "Fechados nesta wave (W-GRAPH)"** descrevendo o que era (init constrói o grafo mas não ensina o consumidor → grafo órfão) + onde foi resolvido (Camada 1 `GRAPH-FIRST.md` Task 1; Camada 2 lembrete no session hook Task 2; Camada 3 `graph-skill.md` Task 1). NÃO usar strike-through de item inexistente.

#### Step 4.3 — Verify + commit

- [ ] Rodar a lane rápida + integração + verify:

```bash
.venv/bin/pytest -m "not integration and not e2e" -q | tail -1
.venv/bin/pytest -m integration -q | tail -1
./bin/forge verify
```

Esperado: rapid ≥ 1708, integration ≥ 175 (subiu com os testes das Tasks 1-3), 0 failed; `forge verify` sem hard fail.

- [ ] Commit atômico:

```bash
git add CHANGELOG.md docs/design/08-session-handoff.md docs/design/04-pending.md
git commit -m "docs(sync): W-GRAPH graph-first pro consumidor — CHANGELOG + handoff + pending"
```

**Anti-padrões (NÃO fazer):**
- Não tocar `docs/design/01-decisions.md` (nenhuma decisão revisitada — wave aditiva).
- Não atualizar README stats (nenhum card/template/validator/comando novo — só dois artefatos de init e um bloco de hook).
- Não usar strike-through de um item de 04-pending que não existe com ID próprio — registrar como entrada nova de "fechados nesta wave".

---

## Self-Review

**Spec coverage (objetivo → tasks):** não há spec formal — esta wave deriva de `docs/reports/auditoria-consolidada-2026-06-17.md` §5/§6 (NO-ONBOARDING, P1 item 6). Cobertura das três camadas declaradas no Goal:
- Camada 1 (instrução persistente `GRAPH-FIRST.md` via novo step no init após `init.py:1609`) → Task 1. ✅
- Camada 2 (lembrete no `session-start-drift-check.sh`, host-aware, stderr, guardado por `graph.db`) → Task 2. ✅
- Camada 3 (skill de referência `graph-skill.md`, tabela tarefa→query→exemplo, aliases, "quando NÃO usar") → Task 1 (mesmo step) + costura Task 3. ✅
- Doc-sync (Mandamento 6) → Task 4. ✅
- Testing (Mandamento 2): integração do init escreve os dois `.md` com markers (Task 1); shell hook via bash + JSON sintético + conteúdo instalado (Task 2); costura Camada 2↔3 (Task 3). `.venv/bin/pytest` canônico em todos os steps. ✅

**Decisão 22 (load-bearing) preservada:** os `.md` gerados são instruções de comportamento pro host; o `engine/` não importa nada deles. O Step 11.7 só escreve texto via `write_text` — zero runtime dep nova. Anti-padrão explícito na Task 1. ✅

**Reuso (Mandamento 3):** `forge_dir`/`ensure_dir`/`graph_db_path` reusados (já importados em `engine/init.py:74-84`; `init.py:1644` já usa `ensure_dir(forge_dir(...))`). O catálogo de queries é o `_HANDLERS` de `engine/graph_cli.py:270-289` — os labels nos `.md` são cópia verbatim (similar-features, blast-radius, orphan-files, symbols, routes, di-deps, tests-for, reusable-helpers, dup-within-module, dup-cross-module, kmp-migration, reuse-findings), sem inventar query nova. O hook reusa `$PROJECT_ROOT` e a guarda de projeto-forge já existentes. Nenhum helper de path/query novo. ✅

**Escopo contido (Mandamento 4):** wave aditiva — não toca o build do grafo (Steps 11/11.5/11.6), não toca o renderer, não toca `01-decisions.md`, não adiciona comando novo. Os itens OUT da auditoria (DEAD-VERIFY, EXIT-2-COLLISION, CONC-1, TOKEN-BLIND, MCP) ficam fora desta wave por escopo — não é procrastinação, são gaps de waves próprias declaradas no roadmap §6. ✅

**Placeholder scan:** nenhum `TBD`/`TODO`/`FIXME` no plano. Os `<query>`, `<slug>`, `<module>`, `<ClassName>`, `path/to/File.kt` que aparecem são verbatim dentro do conteúdo dos arquivos `.md` sendo CRIADOS (sintaxe de exemplo de comando pro consumidor) — não placeholders do plano. ✅

**Type/name consistency:** `_write_graph_docs`, `_GRAPH_FIRST_MD`, `_GRAPH_SKILL_MD` (em `engine.init`); arquivos `GRAPH-FIRST.md` e `graph-skill.md` em `.claude/forge/`; prefixo ASCII `[graph]` no hook — grafia consistente entre Goal, Architecture, todas as tasks, e o Self-Review. O path `.claude/forge/graph-skill.md` citado pelo hook (Task 2) é o mesmo amarrado pela costura da Task 3. ✅

**Dependências:** Task 3 depende da Task 1 (reusa `_write_graph_docs` + `_GRAPH_SKILL_MD`). Task 2 é independente da Task 1 (arquivos disjuntos: `hooks/` vs `engine/init.py`) mas a costura Task 3 amarra as duas — por isso Task 3 vem depois de 1 e 2. Task 4 (doc-sync) por último, reflete 1-3. ✅
