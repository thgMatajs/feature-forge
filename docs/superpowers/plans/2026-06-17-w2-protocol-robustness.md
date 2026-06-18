# W2: Protocol Robustness Implementation Plan

For agentic workers — this plan is dispatched task-by-task to `gsd-executor`.
Each task is self-contained, carries explicit allowed-files, a testable
success criterion, and complete code (no placeholders, no "similar to Task
N"). Read the Global Constraints once before starting; they apply to every
task.

**Goal:** Endurecer o protocolo de execução do `forge` fechando 4 findings
verificados da auditoria consolidada (`docs/reports/auditoria-consolidada-2026-06-17.md`
§3.1/§3.2) e tratar 1 finding como falso-positivo documentado: **C2 DEAD-VERIFY**
(delegator pre-commit aponta pra path legado → gate vira no-op em consumidores),
**C3 EXIT-2-COLLISION** (recontrato estrito: exit 2 = SÓ pausa; colapsa a escada
3/4/5/6/7/8 em `exit 1` + tag `[FORGE-ERR:<TAG>]` em stderr), **C4 CONC-1**
(tempfile fixo + janela TOCTOU corrompem state em processos paralelos), **A3
ENV-1** (env agêntico vazado pra subprocessos → adapter errado → hang) e **A4
REPLAY** (narrow: card-removal muta `.bak` antes do confirm; WRITE-path é
falso-positivo confirmado).

**Architecture:** Cada finding é uma fatia vertical isolada. A ordem de execução
respeita dependência real: **C2 → C4 → A3 → A4 → C3**. Racional:

- C2, C4, A3, A4 são correções localizadas que não tocam a tabela de exit codes.
- C3 vem por último porque é a maior superfície (toca 7 handlers + cli.py + doc
  canônico) e porque o recontrato precisa enxergar os exit-sites já estáveis das
  outras tasks. Em particular, C3 vai re-mapear o `return 2` de `init.py:1117`
  (abort) — então é melhor que A4 (que NÃO toca init) já tenha rodado e
  estabilizado o módulo.
- C2 cria nenhuma dependência sobre as demais; poderia rodar a qualquer momento,
  mas abre a fila por ser a mais cirúrgica (1 arquivo de hook + 1 teste de
  integração).

A centralização canônica de C3 vive em `engine/ui/exit_codes.py` — o módulo que
já é fonte única dos códigos 0/1/2/130. Adicionamos ali as constantes de TAG +
um helper `fail_with_tag(tag, message=None) -> int` que escreve
`[FORGE-ERR:<TAG>]` em stderr e retorna `EXIT_ERROR` (1). Cada exit-site não-pausa
passa a chamar esse helper em vez de `return <N>`.

**Tech Stack:** Python 3.13 (core), Bash (delegator hook), pytest (`.venv/bin/pytest`
canônico), `fcntl`/`msvcrt` (lock cross-process, padrão já em `engine/memory/l1.py`),
`uuid`/`os.getpid` (tempfile namespacing).

---

## Global Constraints

Aplicam-se a TODAS as tasks. O subagente confirma cada uma antes de reportar
"pronto".

1. **Mandamento 0 (subagent-driven):** o orquestrador NÃO edita; o subagente
   `gsd-executor` executa. Você (subagente) faz commit atômico ao final de cada
   task com mensagem canônica `<tipo>(w2): <descrição>`.
2. **Voz mentor calmo** em qualquer artefato gerado ao usuário (mensagens de
   erro, docstrings de contrato, comentários load-bearing). PT neutro. Sem voz
   corporativa, sem emoji decorativo, sem hedging ("vou tentar", "considere").
   As mensagens de erro com tag seguem o padrão 3-caminhos quando o erro for um
   gate (lock, readiness, wave-incomplete).
3. **`.venv/bin/pytest` é canônico.** O system pytest NÃO tem `json5` + deps e
   gera false-fail. Rode SEMPRE `.venv/bin/pytest` a partir da raiz do worktree.
4. **Baseline verde:** rapid **1708** / integration **175** / e2e **30**, 0
   falhas. Toda task que adiciona teste eleva o count; nenhuma task pode reduzir
   o count sem justificativa explícita no commit body (regra de
   `.claude/rules/testing.md §Test count regression`). Confirme o count após
   cada task com `.venv/bin/pytest -m 'not integration and not e2e' -q | tail -1`.
5. **Decisões locked preservadas.** Este plano NÃO toca
   `docs/design/01-decisions.md` — nenhuma decisão locked é revisitada. Decisão
   27 (pause=`deferred` resumable / abort=2-step) e o contrato de exit codes
   DRIFT-1 são honrados, não contrariados: C3 ESTREITA o uso do exit 2 ao que a
   Decisão 27 sempre quis dizer (pausa), removendo o overload acidental. Se
   alguma mudança parecer exigir revisitar uma locked, **PARE e reporte ao
   orquestrador** — não improvise.
6. **Clean-break pré-produção OK.** feature-forge não tem adotante real em v1.4
   (status pré-produção — `docs/design/08-session-handoff.md`). Mudança de
   contrato de exit code (C3) é clean-break aceitável: não há migrator, não há
   caller externo a preservar. O único caller dos exit codes hoje é o próprio
   host/driver (SKILL.md/AGENTS.md), atualizado na mesma wave se necessário.
7. **Reuse-first (Mandamento 3).** Antes de criar helper, o plano JÁ fez o scout:
   C3 reusa `engine/ui/exit_codes.py` (não cria módulo novo); C4 reusa o padrão
   `_file_lock` de `engine/memory/l1.py:133-185`; A3 reusa
   `engine/_sandbox/env.py::build_safe_env` como precedente de allowlist e o
   key-set canônico de `tests/unit/test_cli_upgrade_wired.py:19-20`. Não duplique.
8. **Escopo contido (Mandamento 4).** Só toque os arquivos listados em
   **Files:** de cada task. Doc-sync é a Task 6 dedicada — NÃO faça doc-sync
   inline nas tasks de código (evita conflito de escrita no CHANGELOG entre
   tasks). A exceção é a tabela de exit codes em
   `docs/design/06-command-surface.md`, que é parte integral de C3 (Task 5) e
   não da Task 6.

---

## Task 1 — C2 DEAD-VERIFY: delegator pre-commit checa ambos os paths (legado + sub-namespace)

**Files:**
- `hooks/git-pre-commit` (Modify — linha 13)
- `tests/integration/test_git_pre_commit_delegator.py` (Create)

**Interfaces:**
- Consumes: `git rev-parse --show-toplevel` (project root); o hook interno de
  validação (`pre-commit-feature-forge.sh`) em um de dois locais.
- Produces: delegação correta pro hook de validação em consumidores E no repo
  maintainer; nenhuma mudança de assinatura — `git-pre-commit` continua a
  receber `"$@"` e sempre exitar 0 quando o delegate falta.

### Contexto do bug (scout confirmado)

`hooks/git-pre-commit:13` hardcoda:

```bash
HOOK="$PROJECT_ROOT/.claude/hooks/pre-commit-feature-forge.sh"
```

A cadeia REAL diverge por contexto:

- **Repo maintainer (este repo):** `.git/hooks/pre-commit` → symlink
  `../../hooks/git-pre-commit` (instalado por `.claude/bootstrap.sh`) →
  resolve `$PROJECT_ROOT/.claude/hooks/pre-commit-feature-forge.sh`, que
  **EXISTE** (path legado, é onde o maintainer hook vive). O hard-block do
  Mandamento #1 funciona AQUI.
- **Consumidor (via `forge init`):** `engine/init.py::_install_git_hooks`
  (init.py:679-759) escreve um wrapper `.git/hooks/pre-commit` que faz
  `exec "{forge_hook}"` onde `forge_hook = forge_hooks_dir(project_root) /
  "git-pre-commit"` = `.claude/forge/hooks/git-pre-commit` (cópia do delegator).
  Essa cópia checa `$PROJECT_ROOT/.claude/hooks/pre-commit-feature-forge.sh`,
  que **NÃO EXISTE** num consumidor — o `forge init` copiou o validador pra
  `.claude/forge/hooks/pre-commit-feature-forge.sh` (init.py:641-676,
  `_install_hooks` → `forge_hooks_dir`). `[[ -x "$HOOK" ]]` falso → `exit 0` →
  gate é no-op silencioso. **DEAD-VERIFY.**

### Decisão de design (justificada)

O delegator deve checar **ambos** os paths, sub-namespace primeiro, legado
depois:

1. `$PROJECT_ROOT/.claude/forge/hooks/pre-commit-feature-forge.sh` (canônico
   v1.3+, onde `forge init` instala em consumidores).
2. `$PROJECT_ROOT/.claude/hooks/pre-commit-feature-forge.sh` (legado, onde o
   maintainer hook deste repo vive).

**Por que ambos e não "detectar qual existe e migrar":** o delegator é um
script Bash sem estado, executado em cada commit; migração de path é
responsabilidade do `forge init`/`bootstrap`, não do hook. Checar ambos é
idempotente, preserva o hard-block deste repo (legado existe), e ativa o gate
em consumidores (sub-namespace existe) — sem tocar `init.py` nem `bootstrap.sh`.
A precedência sub-namespace→legado alinha com a precedência canônica de config
(`engine/utils/paths.py::active_config_path`: primário → legado).

### Steps

- [ ] **Step 1.1 — Escrever o teste de integração PRIMEIRO (RED).** Este teste
  exercita a cadeia REAL do delegator (não stuba o hook interno em local
  arbitrário, que foi exatamente a cegueira de
  `tests/integration/test_claude_rules_system.py:111-142`). Crie
  `tests/integration/test_git_pre_commit_delegator.py`:

```python
"""C2 DEAD-VERIFY regression — o delegator git-pre-commit deve achar o hook
de validação tanto no sub-namespace (.claude/forge/hooks/) quanto no path
legado (.claude/hooks/).

Bug original: hooks/git-pre-commit:13 hardcodava só o path legado, então em
consumidores (onde forge init instala em .claude/forge/hooks/) o gate virava
no-op silencioso — exatamente o oposto do contrato fail-closed do Mandamento #1.

Diferente de test_claude_rules_system.py, que copia o hook INTERNO pra um
local arbitrário e o roda direto: aqui rodamos o DELEGATOR (git-pre-commit)
apontando pro hook instalado, exercitando a resolução de path real.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
DELEGATOR = REPO_ROOT / "hooks" / "git-pre-commit"
VALIDATOR = REPO_ROOT / ".claude" / "hooks" / "pre-commit-feature-forge.sh"


def _fake_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "consumer"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@x"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
    # Stage uma edição de 01-decisions.md SEM ceremony — o validador deve
    # hard-block (exit 1). É o cenário que prova "o gate rodou".
    (repo / "docs" / "design").mkdir(parents=True)
    (repo / "docs" / "design" / "01-decisions.md").write_text("# fake\n+change\n")
    (repo / "CHANGELOG.md").write_text("# Changelog\n## Unreleased\n- sem ceremony\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    return repo


def _install_validator(repo: Path, subdir: str) -> None:
    """Copia o validador interno pra <repo>/<subdir>/pre-commit-feature-forge.sh."""
    dst_dir = repo / subdir
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / "pre-commit-feature-forge.sh"
    shutil.copy(VALIDATOR, dst)
    os.chmod(dst, 0o755)


def _run_delegator(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(DELEGATOR)],
        cwd=repo,
        capture_output=True,
        text=True,
    )


def test_delegator_finds_validator_in_subnamespace(tmp_path):
    """Consumidor real: validador em .claude/forge/hooks/ → gate roda → block."""
    repo = _fake_repo(tmp_path)
    _install_validator(repo, ".claude/forge/hooks")
    result = _run_delegator(repo)
    assert result.returncode == 1, (
        f"gate deveria ter bloqueado via sub-namespace; rc={result.returncode}, "
        f"stderr={result.stderr!r}"
    )
    assert "Revisita decisão" in result.stderr or "BLOCK" in result.stderr


def test_delegator_finds_validator_in_legacy_path(tmp_path):
    """Maintainer repo: validador em .claude/hooks/ → gate roda → block."""
    repo = _fake_repo(tmp_path)
    _install_validator(repo, ".claude/hooks")
    result = _run_delegator(repo)
    assert result.returncode == 1, (
        f"gate deveria ter bloqueado via path legado; rc={result.returncode}, "
        f"stderr={result.stderr!r}"
    )
    assert "Revisita decisão" in result.stderr or "BLOCK" in result.stderr


def test_delegator_noop_when_no_validator_installed(tmp_path):
    """Sem validador em nenhum dos dois paths → no-op, exit 0 (contrato)."""
    repo = _fake_repo(tmp_path)
    result = _run_delegator(repo)
    assert result.returncode == 0, (
        f"delegator deveria ser no-op (exit 0) quando o delegate falta; "
        f"rc={result.returncode}, stderr={result.stderr!r}"
    )
```

- [ ] **Step 1.2 — Rodar o teste, confirmar RED.**

```bash
.venv/bin/pytest tests/integration/test_git_pre_commit_delegator.py -q
```

Expected: `test_delegator_finds_validator_in_subnamespace` FALHA (rc=0 em vez
de 1, porque o delegator ainda só olha o legado). Os outros dois passam (legado
+ no-op já funcionam). Confirme que a falha é exatamente o caso sub-namespace.

- [ ] **Step 1.3 — Corrigir o delegator (GREEN).** Substitua o bloco fixo de
  `hooks/git-pre-commit` (linhas 12-18) por checagem de ambos os paths,
  sub-namespace primeiro:

```bash
PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

# C2 DEAD-VERIFY fix: o validador pode viver em dois lugares dependendo de
# como o forge foi instalado. Checa o sub-namespace canônico (.claude/forge/
# hooks/, onde `forge init` instala em consumidores) ANTES do path legado
# (.claude/hooks/, onde o hook deste repo maintainer vive). A precedência
# espelha engine/utils/paths.py::active_config_path (primário → legado).
HOOK_PRIMARY="$PROJECT_ROOT/.claude/forge/hooks/pre-commit-feature-forge.sh"
HOOK_LEGACY="$PROJECT_ROOT/.claude/hooks/pre-commit-feature-forge.sh"

if [[ -x "$HOOK_PRIMARY" ]]; then
    exec "$HOOK_PRIMARY" "$@"
elif [[ -x "$HOOK_LEGACY" ]]; then
    exec "$HOOK_LEGACY" "$@"
fi
exit 0
```

- [ ] **Step 1.4 — Rodar o teste, confirmar GREEN.**

```bash
.venv/bin/pytest tests/integration/test_git_pre_commit_delegator.py -q
```

Expected: 3 passed.

- [ ] **Step 1.5 — Sintaxe Bash + suite rápida não regrediu.**

```bash
bash -n hooks/git-pre-commit && echo "bash syntax OK"
.venv/bin/pytest -m 'not integration and not e2e' -q | tail -1
```

Expected: `bash syntax OK`; rapid count >= 1708, 0 falhas.

- [ ] **Step 1.6 — Commit atômico:** `fix(w2): C2 DEAD-VERIFY — delegator pre-commit checa sub-namespace + legado`

**Anti-padrões (NÃO fazer):** não tocar `engine/init.py` nem `.claude/bootstrap.sh`
(migração de path é deles, não do hook); não remover o fallback legado (quebra
o hard-block deste repo); não stubar o validador num local arbitrário (replica a
cegueira do teste antigo).

---

## Task 2 — C4 CONC-1 (parte A): tempfile por-processo em json_io.write_json

**Files:**
- `engine/utils/json_io.py` (Modify — linha 106)
- `tests/integration/test_intent_state_concurrency.py` (Modify — flip de asserções)
- `tests/unit/test_json_io_atomic.py` (Modify ou Create — teste unit do sufixo)

**Interfaces:**
- Consumes: `os.getpid()` + `uuid.uuid4().hex` pra sufixo único por escritor.
- Produces: `write_json` com tempfile namespaced; nenhuma mudança de assinatura
  pública (mesmo `write_json(path, data, *, atomic, indent, mode)`); a sequência
  atômica flush→fsync→os.replace→fsync-dir é preservada.

### Contexto do bug (scout confirmado)

`engine/utils/json_io.py:106`:

```python
tmp = path.with_suffix(path.suffix + ".tmp")
```

O nome do tempfile é **fixo** (`forge-pending.json.tmp`). Dois processos forge
no mesmo root escrevendo o mesmo `forge-pending.json` compartilham o MESMO
tempfile → torn write (bytes concatenados) OU `FileNotFoundError` no `os.replace`
do escritor tardio (o tmp já foi movido). O próprio teste do projeto
(`test_concurrent_writers_document_torn_write_window`) HOJE tolera esses dois
modos de falha como "gap conhecido".

### Steps

- [ ] **Step 2.1 — Flip das asserções no teste de torn-write (RED).** Edite
  `tests/integration/test_intent_state_concurrency.py`. Em
  `test_concurrent_writers_document_torn_write_window` (linhas 156-237),
  troque a tolerância a torn-write por uma asserção forte. Substitua o corpo
  pós-join (a partir de "Read raw bytes") por:

```python
    # Read raw bytes — bypass json_io to make sure we hit the file as-is.
    pending_path = (
        project_root / ".claude" / "forge" / "state" / "forge-pending.json"
    )
    assert pending_path.is_file(), (
        "com tempfile por-processo, ao menos um writer vence o os.replace e "
        "o pending final DEVE existir (nenhum perde o tmp compartilhado)"
    )
    raw = pending_path.read_bytes()

    # C4 CONC-1 fix: tempfile por-processo elimina o torn write. O destino
    # SEMPRE parseia como JSON válido e bate EXATAMENTE com um dos payloads
    # submetidos — nunca bytes concatenados, nunca mistura de campos.
    parsed = json.loads(raw.decode("utf-8"))  # não deve levantar
    matched_any = any(parsed == candidate for candidate in payloads.values())
    assert matched_any, (
        "final pending content matches no submitted payload — "
        f"atomicidade violada. parsed={parsed!r}"
    )
```

  E no worker do MESMO teste, troque o `try/except FileNotFoundError: pass`
  (linhas 194-197) por uma escrita direta (não deve mais levantar):

```python
        barrier.wait()
        # C4 CONC-1 fix: com tempfile por-processo, write_pending NUNCA levanta
        # FileNotFoundError no os.replace — cada writer tem seu próprio tmp.
        intent_state.write_pending(payload, project_root)
```

  Faça o mesmo flip em `test_concurrent_writers_via_json_io_directly`
  (linhas 240-280): remova o `try/except FileNotFoundError`, troque a tolerância
  a `JSONDecodeError` por asserção dura:

```python
    def worker(idx: int) -> None:
        barrier.wait()
        json_io.write_json(target, payloads[idx])

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert target.is_file(), "algum writer deve vencer; destino deve existir"
    parsed = json.loads(target.read_text(encoding="utf-8"))  # não deve levantar
    assert parsed in payloads, (
        "json_io.write_json sob contenção produziu payload que nenhum writer "
        f"submeteu; parsed={parsed!r}"
    )
```

  Atualize também a docstring do módulo de teste (linhas 1-29) pra refletir que
  o gap TOCTOU/torn-write foi FECHADO (remova a prosa "lock via flock está
  DEFERRED" e "estes testes não fecham essa janela"; troque por "C4 CONC-1
  fechou o gap: tempfile por-processo + flock").

- [ ] **Step 2.2 — Rodar, confirmar RED.**

```bash
.venv/bin/pytest tests/integration/test_intent_state_concurrency.py -q
```

Expected: `test_concurrent_writers_document_torn_write_window` e/ou
`test_concurrent_writers_via_json_io_directly` FALHAM intermitentemente (torn
write ou FileNotFoundError ainda possíveis com o tempfile fixo). Rode 3x se
preciso pra ver a falha (é timing-dependent):

```bash
for i in 1 2 3; do .venv/bin/pytest tests/integration/test_intent_state_concurrency.py -q | tail -1; done
```

- [ ] **Step 2.3 — Corrigir write_json (GREEN).** Em `engine/utils/json_io.py`,
  adicione `import uuid` ao topo (junto com os imports existentes `import os`,
  `import json`) e substitua a linha 106:

```python
    # C4 CONC-1: tempfile por-processo. O nome fixo (path + ".tmp") fazia dois
    # processos forge no mesmo root colidirem no mesmo arquivo intermediário —
    # torn write OU FileNotFoundError no os.replace do escritor tardio. O sufixo
    # {pid}.{uuid} garante que cada escritor tenha seu próprio tmp; o os.replace
    # final continua sendo a fronteira atômica (last-writer-wins por syscall,
    # nunca conteúdo corrompido).
    tmp = path.with_suffix(f"{path.suffix}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
```

  O restante do bloco (linhas 107-123: `with tmp.open(...)`, `flush`, `fsync`,
  `os.replace`, `_apply_mode`, `_fsync_parent_dir`, `finally: tmp.unlink`)
  permanece inalterado — a sequência atômica está correta.

- [ ] **Step 2.4 — Rodar, confirmar GREEN (estável sob repetição).**

```bash
for i in 1 2 3 4 5; do .venv/bin/pytest tests/integration/test_intent_state_concurrency.py -q | tail -1; done
```

Expected: 3 passed em todas as 5 rodadas (sem flake).

- [ ] **Step 2.5 — Teste unit do formato do sufixo.** Adicione a
  `tests/unit/test_json_io_atomic.py` (crie o arquivo se não existir) um teste
  que valida o naming sem concorrência:

```python
"""Unit — tempfile namespacing de json_io.write_json (C4 CONC-1).

Valida que o tmp intermediário carrega pid + uuid, sem depender de timing.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

from engine.utils import json_io


def test_write_json_uses_per_process_tempfile(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    captured: dict[str, Path] = {}

    real_replace = json_io.os.replace

    def _spy_replace(src, dst):
        captured["tmp"] = Path(src)
        return real_replace(src, dst)

    monkeypatch.setattr(json_io.os, "replace", _spy_replace)
    monkeypatch.setattr(json_io.os, "getpid", lambda: 4242)

    json_io.write_json(target, {"k": "v"})

    tmp_name = captured["tmp"].name
    assert ".4242." in tmp_name, f"tmp deve carregar o pid: {tmp_name}"
    assert tmp_name.endswith(".tmp"), f"tmp deve terminar em .tmp: {tmp_name}"
    # 32 hex chars do uuid4().hex em algum ponto do nome
    assert any(
        len(part) == 32 and all(c in "0123456789abcdef" for c in part)
        for part in tmp_name.split(".")
    ), f"tmp deve carregar uuid4 hex: {tmp_name}"
    # Conteúdo final intacto
    assert json.loads(target.read_text(encoding="utf-8")) == {"k": "v"}
```

- [ ] **Step 2.6 — Rodar o teste unit + suite rápida.**

```bash
.venv/bin/pytest tests/unit/test_json_io_atomic.py -q
.venv/bin/pytest -m 'not integration and not e2e' -q | tail -1
```

Expected: passed; rapid count subiu (+1 do teste unit novo), 0 falhas.

- [ ] **Step 2.7 — Commit atômico:** `fix(w2): C4 CONC-1 (A) — tempfile por-processo em json_io.write_json`

**Anti-padrões:** não mexer na ordem flush→fsync→replace→fsync-dir (está
correta); não remover o `finally: tmp.unlink()` (limpa tmp órfão se o replace
falhar); não tocar `intent_state.detect_race` nesta task (é a Task 3).

---

## Task 3 — C4 CONC-1 (parte B): flock na seção crítica de detect_race + write_pending

**Files:**
- `engine/ui/intent_state.py` (Modify — `detect_race` em 626-725; adicionar helper `pending_lock` + `_pending_lock_path`)
- `engine/host/adapters/intent_file.py` (Modify — `_ask_loop` 291-300: envolver a seção crítica `detect_race`+`write_pending` no `pending_lock`)
- `tests/integration/test_intent_state_concurrency.py` (Modify — adicionar teste de concorrência da seção crítica REAL)

**Interfaces:**
- Consumes: `fcntl.flock(LOCK_EX)` (POSIX) / `msvcrt.locking` (Windows), no padrão
  já existente em `engine/memory/l1.py::_file_lock` (133-185).
- Produces: `detect_race` + `write_pending` executados sob lock exclusivo
  por-root NA SEÇÃO CRÍTICA REAL DE PRODUÇÃO (`IntentFileAdapter._ask_loop`),
  eliminando a janela TOCTOU (read-then-write sem lock) descrita no comentário
  "flock deferred" (intent_state.py:649-650).

### Contexto do bug (scout confirmado)

`detect_race` (intent_state.py:626-725) faz read-then-decide sem lock. A seção
crítica REAL de produção NÃO está em `question.py` — está no adapter
`engine/host/adapters/intent_file.py::_ask_loop` (linhas 291-300), que é o que
`question.ask`/`ask_multi`/`ask_text` alcançam via
`_resolve_adapter(project_root).ask(...)`. Ali o adapter chama, como duas
operações sequenciais sem lock:

```python
intent_state.detect_race(self.project_root, new_intent_id=intent_id, state_dir=self._state_dir)
intent_state.write_pending(intent, self.project_root, state_dir=self._state_dir)
```

A janela entre "li o pending e decidi que é seguro" e "escrevi o meu pending"
permite que dois processos ambos passem pelo `detect_race` (pending ausente)
antes de qualquer escrita. A docstring admite: "Lock file via `fcntl.flock` is
deferred". A Task 2 já fecha o torn-write no nível de bytes; esta task fecha a
janela TOCTOU no nível semântico (detecção de corrida confiável) APLICANDO o
lock onde o TOCTOU vive de fato.

### Decisão de design (justificada)

Reuso do padrão `_file_lock` de `l1.py` (advisory exclusive lock via `fcntl`/
`msvcrt`, no-op em plataformas sem suporte como última linha de defesa). Em vez
de duplicar, criamos um helper local mínimo em `intent_state.py` que abre um
**lock file dedicado** (`forge-pending.lock` no state dir) e segura o lock
durante a seção crítica `detect_race + write_pending`. O lock file é separado do
pending pra não interferir com o `os.replace` atômico do `write_json` (que
substitui o inode do pending — segurar lock sobre um fd que vai ser substituído
é frágil; lock file dedicado é o padrão robusto).

O context manager `pending_lock(project_root, *, state_dir=None)` é APLICADO no
caminho real do adapter (`IntentFileAdapter._ask_loop`), envolvendo o par
`detect_race`+`write_pending`. Expor o CM sem aplicá-lo deixaria C4-B (TOCTOU em
produção) aberto — por isso a aplicação é parte integral desta task, não
defense-in-depth opcional. O escopo é cirúrgico: 2 linhas no adapter (o `with`),
sem refatorar o `_ask_loop` nem tocar outros adapters. `intent_file.py` é o
ÚNICO adapter que chama `detect_race`/`write_pending` (o adapter de host nativo
do Claude Code não usa o state-race em disco — scout confirmado via
`grep -rn "detect_race\|write_pending" engine/`).

> NOTA DE ESCOPO: a fatia mínima é envolver o par `detect_race`+`write_pending`
> de `_ask_loop` (291-300) com `with intent_state.pending_lock(self.project_root,
> state_dir=self._state_dir):`. Se o scout do `_ask_loop` mostrar que o par NÃO
> é contíguo (há lógica intermediária que não pode rodar sob lock) ou que aplicar
> o lock exige reestruturar o método, PARE e reporte 3-caminhos ao orquestrador —
> não refatore o adapter. (Scout deste plano confirma que 291-300 são duas
> chamadas contíguas; a aplicação esperada é trivial.)

### Steps

- [ ] **Step 3.1 — Escrever os testes PRIMEIRO (RED): seção crítica direta +
  caminho REAL do adapter.** Adicione a
  `tests/integration/test_intent_state_concurrency.py` DOIS testes.

  **(a) Seção crítica direta sob `pending_lock`** — prova que o CM serializa
  `detect_race`+`write_pending`:

```python
def test_pending_lock_serializes_detect_race_and_write(tmp_path):
    """C4 CONC-1 (B): sob pending_lock, detect_race+write_pending viram seção
    crítica serializada — o primeiro escreve, os demais veem o pending do
    primeiro e levantam RaceDetectedError DETERMINÍSTICO (não corrida de bytes).
    """
    project_root = _project(tmp_path)
    n_threads = 6
    barrier = threading.Barrier(n_threads)
    outcomes: list[str] = []
    outcomes_lock = threading.Lock()

    def worker(idx: int) -> None:
        intent_id = f"locked-{idx:08d}-0000-4000-8000-000000000000"
        payload = _make_payload(intent_id, pid=30_000 + idx)
        barrier.wait()
        try:
            with intent_state.pending_lock(project_root):
                intent_state.detect_race(project_root, intent_id)
                intent_state.write_pending(payload, project_root)
            tag = "wrote"
        except intent_state.RaceDetectedError:
            tag = "race"
        with outcomes_lock:
            outcomes.append(tag)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
        assert not t.is_alive(), "worker hung past timeout"

    assert len(outcomes) == n_threads
    # Exatamente um writer vence; os demais veem o pending do vencedor e
    # levantam RaceDetectedError de forma DETERMINÍSTICA (sem janela TOCTOU).
    assert outcomes.count("wrote") == 1, f"esperava 1 vencedor, veio {outcomes}"
    assert outcomes.count("race") == n_threads - 1, (
        f"os demais devem detectar a corrida; veio {outcomes}"
    )
    # Pending final é válido e bate com o vencedor.
    final = intent_state.read_pending(project_root)
    assert final is not None and final["intent-id"].startswith("locked-")
```

  **(b) Caminho REAL de produção via o adapter** — prova que `_ask_loop` (a seção
  crítica de PRODUÇÃO) passa pelo lock aplicado. Sem o `with pending_lock` no
  adapter, dois `IntentFileAdapter` competindo no mesmo root podem ambos passar
  pelo `detect_race` antes de escrever (TOCTOU). Com o lock aplicado, a seção é
  serializada: o primeiro emite o pending + levanta `PausedForInputError`; o
  segundo, ao adquirir o lock, vê o pending do primeiro e levanta
  `RaceDetectedError`. Adicione no topo do módulo os imports necessários (junto
  aos existentes, sem duplicar):

```python
from engine.host.adapters.intent_file import IntentFileAdapter
from engine.host.adapter import AskKind, PausedForInputError
```

  E o teste:

```python
def test_adapter_ask_loop_serializes_via_applied_lock(tmp_path):
    """C4 CONC-1 (B) — seção crítica REAL: dois IntentFileAdapter competindo
    no mesmo root passam pelo pending_lock aplicado em _ask_loop. Sem cross-answer
    e sem torn write: exatamente um emite o pending (PausedForInputError), os
    demais detectam a corrida (RaceDetectedError). O pending final é válido e
    bate com o vencedor.
    """
    project_root = _project(tmp_path)
    n_threads = 6
    barrier = threading.Barrier(n_threads)
    outcomes: list[str] = []
    outcomes_lock = threading.Lock()

    def worker(idx: int) -> None:
        # Cada thread tem seu próprio adapter, mas todos no MESMO project_root —
        # disputam o mesmo forge-pending.json (a seção crítica real).
        adapter = IntentFileAdapter(project_root)
        barrier.wait()
        try:
            adapter.ask(
                kind=AskKind.ASK,
                question=f"probe-{idx}",
                options={"a": "alpha", "b": "beta"},
                default=None,
                allow_pause=True,
            )
            tag = "returned"  # não esperado na primeira entrada (sem response)
        except PausedForInputError:
            tag = "paused"  # emitiu o pending — venceu a corrida
        except intent_state.RaceDetectedError:
            tag = "race"  # viu o pending do vencedor sob o lock
        with outcomes_lock:
            outcomes.append(tag)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
        assert not t.is_alive(), "worker hung past timeout"

    assert len(outcomes) == n_threads
    # Exatamente um emite o pending; os demais detectam a corrida de forma
    # DETERMINÍSTICA (lock aplicado fecha o TOCTOU). Nenhuma resposta cruzada.
    assert outcomes.count("paused") == 1, (
        f"esperava 1 vencedor (PausedForInputError), veio {outcomes}"
    )
    assert outcomes.count("race") == n_threads - 1, (
        f"os demais devem ver RaceDetectedError sob o lock; veio {outcomes}"
    )
    # Pending final no disco é JSON válido (sem torn write) e bate com o vencedor.
    final = intent_state.read_pending(project_root)
    assert final is not None
    assert final["question"].startswith("probe-")
```

  > NOTA DE SCOUT (já confirmada): `IntentFileAdapter(project_root)` resolve
  > `self._state_dir = forge_state_dir(project_root)` no `__init__` e
  > `adapter.ask(...)` chega ao `_ask_loop`, que chama detect_race+write_pending
  > com `state_dir=self._state_dir`. A assinatura de `ask` aceita
  > `kind`/`question`/`options`/`default`/`allow_pause` (scout em intent_file.py:90).
  > Se a assinatura real divergir, ajuste a chamada ao contrato REAL do adapter —
  > NÃO invente kwargs.

- [ ] **Step 3.2 — Rodar, confirmar RED.**

```bash
.venv/bin/pytest tests/integration/test_intent_state_concurrency.py -q -k "pending_lock_serializes or adapter_ask_loop_serializes"
```

Expected: ambos FALHAM. O teste (a) falha com `AttributeError: module
'engine.ui.intent_state' has no attribute 'pending_lock'` (o CM ainda não
existe). O teste (b) falha porque o lock ainda NÃO está aplicado em `_ask_loop`
— sob contenção, mais de uma thread passa pelo `detect_race` antes de escrever
(`outcomes.count("paused") > 1` OU torn write), provando a janela TOCTOU aberta.
Rode 3x se preciso (timing-dependent):

```bash
for i in 1 2 3; do .venv/bin/pytest tests/integration/test_intent_state_concurrency.py::test_adapter_ask_loop_serializes_via_applied_lock -q | tail -1; done
```

- [ ] **Step 3.3 — Implementar pending_lock (GREEN).** Em
  `engine/ui/intent_state.py`, adicione no topo (junto aos imports existentes):

```python
import sys
from contextlib import contextmanager
from typing import Iterator
```

  (Use só os que ainda não estiverem importados — verifique o bloco de imports
  atual antes de adicionar duplicata.)

  Adicione o helper de path do lock, próximo a `_pending_path`:

```python
def _pending_lock_path(project_root: Path, *, state_dir: Path | None = None) -> Path:
    """Path do lock file dedicado pra seção crítica detect_race+write_pending.

    Separado do pending.json: o write_json substitui o inode do pending via
    os.replace; segurar lock sobre um fd que vai ser substituído é frágil.
    Um lock file dedicado é o padrão robusto (mesmo princípio do sentinel
    O_EXCL em engine/memory/l1.py).
    """
    base = state_dir if state_dir is not None else _state_dir(project_root)
    return base / "forge-pending.lock"
```

  > NOTA: confirme o nome do helper de state dir já usado por `_pending_path`
  > (provavelmente `_state_dir` ou `forge_state_dir`). Reuse o MESMO — não
  > introduza um segundo resolvedor de state dir. Se `_pending_path` usa
  > `forge_state_dir(project_root)` diretamente, espelhe isso.

  Adicione o context manager (espelha `engine/memory/l1.py::_file_lock`,
  advisory exclusive, no-op cross-platform):

```python
@contextmanager
def pending_lock(
    project_root: Path, *, state_dir: Path | None = None
) -> Iterator[None]:
    """Lock advisory exclusivo sobre a seção crítica detect_race+write_pending.

    C4 CONC-1 (B): fecha a janela TOCTOU em que dois processos forge ambos
    passam por detect_race (pending ausente) antes de qualquer escrita. Sob
    este lock, a sequência "checar corrida + escrever pending" é atômica
    cross-process.

    POSIX usa fcntl.flock(LOCK_EX); Windows usa msvcrt.locking. Plataformas
    sem suporte caem em no-op (o tempfile por-processo de C4(A) + os.replace
    atômico permanecem como última linha de defesa).
    """
    lock_path = _pending_lock_path(project_root, state_dir=state_dir)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "a", encoding="utf-8")
    locked_posix = False
    locked_win = False
    try:
        if sys.platform == "win32":
            try:
                import msvcrt  # type: ignore[import-not-found]

                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
                    locked_win = True
                except OSError:
                    pass
            except ImportError:
                pass
        else:
            try:
                import fcntl  # type: ignore[import-not-found]

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
                locked_posix = True
            except ImportError:
                pass
        yield
    finally:
        try:
            if locked_posix:
                import fcntl  # type: ignore[import-not-found]

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            elif locked_win:
                import msvcrt  # type: ignore[import-not-found]

                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
        except (ImportError, OSError):
            pass
        fh.close()
```

  Atualize a docstring de `detect_race` (linhas 649-650): troque "Lock file via
  ``fcntl.flock`` is deferred — see the spec §..." por:

```python
    A seção crítica ``detect_race`` + ``write_pending`` é serializada
    cross-process pelo caller real (``IntentFileAdapter._ask_loop``), que a
    envolve em ``pending_lock(project_root, state_dir=...)`` (C4 CONC-1 (B)).
    Sob o lock, dois processos forge não passam mais ambos pelo ``detect_race``
    antes de escrever. O tempfile por-processo de C4 (A) + ``os.replace``
    atômico permanecem como última linha de defesa (sem torn write mesmo se o
    lock for no-op numa plataforma sem suporte).
```

- [ ] **Step 3.4 — APLICAR o lock na seção crítica REAL (GREEN parte 2).** Em
  `engine/host/adapters/intent_file.py`, no método `_ask_loop`, envolva o par
  `detect_race`+`write_pending` (linhas 291-300) com o context manager. O
  `intent_state` já está importado no topo do módulo (intent_file.py:55 —
  `from engine.ui import intent_state`); nenhum import novo é necessário.
  Substitua:

```python
        intent_state.detect_race(
            self.project_root,
            new_intent_id=intent_id,
            state_dir=self._state_dir,
        )
        intent_state.write_pending(
            intent,
            self.project_root,
            state_dir=self._state_dir,
        )
```

  por:

```python
        # C4 CONC-1 (B): a seção crítica detect_race+write_pending roda sob
        # lock exclusivo por-root. Fecha a janela TOCTOU em que dois processos
        # forge ambos passam pelo detect_race (pending ausente) antes de
        # qualquer escrita. O lock file é dedicado (forge-pending.lock), não o
        # próprio pending.json — ver intent_state.pending_lock.
        with intent_state.pending_lock(
            self.project_root, state_dir=self._state_dir
        ):
            intent_state.detect_race(
                self.project_root,
                new_intent_id=intent_id,
                state_dir=self._state_dir,
            )
            intent_state.write_pending(
                intent,
                self.project_root,
                state_dir=self._state_dir,
            )
```

  > NOTA DE ESCOPO: a edição é exatamente o `with` + reindentação das duas
  > chamadas existentes. NÃO mexa no `raise PausedForInputError` que vem logo
  > depois (301-303) — ele fica FORA do `with` (o lock só precisa cobrir
  > detect_race+write_pending; segurar o lock durante o raise é desnecessário e
  > o `finally` do CM libera ao sair do bloco). Se a reindentação tocar mais que
  > essas duas chamadas, PARE e reporte ao orquestrador.

- [ ] **Step 3.5 — Rodar, confirmar GREEN (estável).**

```bash
for i in 1 2 3 4 5; do .venv/bin/pytest tests/integration/test_intent_state_concurrency.py -q | tail -1; done
```

Expected: todas as rodadas passam — incluindo o teste direto (a)
`test_pending_lock_serializes_detect_race_and_write` E o teste do caminho REAL
(b) `test_adapter_ask_loop_serializes_via_applied_lock` (que só fica verde com o
lock aplicado em `_ask_loop`) —, sem flake.

- [ ] **Step 3.6 — Suite rápida não regrediu.**

```bash
.venv/bin/pytest -m 'not integration and not e2e' -q | tail -1
```

Expected: rapid count >= baseline, 0 falhas.

- [ ] **Step 3.7 — Commit atômico:** `fix(w2): C4 CONC-1 (B) — pending_lock aplicado na seção crítica detect_race+write_pending (IntentFileAdapter._ask_loop)`

**Anti-padrões:** não tocar `engine/ui/question.py` (não é o caller real —
`IntentFileAdapter._ask_loop` é); não estender o lock pra outros adapters (só
`intent_file.py` chama detect_race/write_pending); não segurar lock sobre o fd
do próprio pending.json (use lock file dedicado); não duplicar o resolvedor de
state dir; não envolver o `raise PausedForInputError` dentro do `with`.

---

## Task 4 — A3 ENV-1: scrub de env agêntico no boundary de spawn + pin host facilitado

**Files:**
- `engine/host/env.py` (Modify — adicionar `scrubbed_subprocess_env`)
- `engine/ingest.py` (Modify — `_handle_post_subagent_validate` spawn na linha 377 + `_handle_ci_pr_ingest` spawn na linha 442: passar env scrubbed aos validators)
- `tests/unit/test_host_env_scrub.py` (Create)

**Interfaces:**
- Consumes: `os.environ`, o key-set canônico de agentic hosts (`CLAUDECODE`,
  `FORGE_FORCE_INTENT_MODE`, `FORGE_FORCE_TTY_MODE` exatos; `OPENCODE_`, `CODEX`,
  `CURSOR_` prefixos — alinhado a `tests/unit/test_cli_upgrade_wired.py:19-20`).
- Produces: `scrubbed_subprocess_env() -> dict[str, str]` que retorna uma cópia
  de `os.environ` SEM as keys de host agêntico — pra subprocessos filhos não
  herdarem sinais que fariam um `forge` aninhado escolher o adapter errado e
  emitir marker+exit2 esperando um driver inexistente (hang).

### Contexto do bug (scout confirmado)

`engine/host/env.py::detect_claude_code/detect_opencode/detect_codex/detect_cursor`
leem keys herdadas. Um `forge` rodando como subprocess de um host agêntico
(hook `SubagentStop`/`PostToolUse` que invoca `forge ingest`, que por sua vez
spawna validators — `engine/ingest.py:377,442`) herda `CLAUDECODE=1` etc. Se
algum desses subprocessos re-invocar `forge` interativo, `detect_host` escolhe
ClaudeCodeAdapter, emite `<FORGE_INTENT/>` + exit 2, e fica esperando um driver
que aquele contexto não tem → hang.

`engine/_sandbox/env.py::build_safe_env` JÁ resolve isso pra os subprocessos da
QA sandbox + verify (é allowlist; as keys de host não estão em
`CORE_ALLOWLIST`). Mas os spawns de `engine/ingest.py` passam o env herdado
integral (não usam `build_safe_env` nem `env=`). A3 fecha esse boundary com um
scrub cirúrgico (deny-list das keys de host), sem impor a allowlist completa do
sandbox (que dropa demais pra um validator de ingest).

### Decisão de design (justificada)

Dois mecanismos, conforme o finding pede:

1. **Scrub helper** em `engine/host/env.py` (onde as keys são definidas — coesão):
   `scrubbed_subprocess_env()` retorna `os.environ` menos as keys de host. É uma
   deny-list (não allowlist) porque o objetivo é cirúrgico: remover só os sinais
   de host, preservando PATH/HOME/JAVA_HOME/etc. que um validator de ingest
   precisa. Diferente de `build_safe_env` (allowlist agressiva pra sandbox de
   QA, onde o objetivo é segurança de segredos). Os dois coexistem por terem
   objetivos distintos — documentado no docstring.
2. **Pin `host: intent-file`** já é honrado por `engine/host/detect.py:36-39`
   (`_read_config_host` lê `forge-config.yaml` `host:`). A3 não precisa de código
   novo aqui — só DOC (Task 6 cobre: documentar em
   `docs/design/06-command-surface.md`/handoff que contextos não-interativos
   devem pinar `host: intent-file`). Esta task apenas ADICIONA o scrub.

### Steps

- [ ] **Step 4.1 — Teste unit PRIMEIRO (RED).** Crie
  `tests/unit/test_host_env_scrub.py`:

```python
"""A3 ENV-1 — scrubbed_subprocess_env remove sinais de host agêntico.

Subprocessos filhos do forge (validators spawnados por ingest) não devem
herdar CLAUDECODE / OPENCODE_* / CODEX* / CURSOR_* / FORGE_FORCE_*_MODE — senão
um forge aninhado escolheria o adapter errado e penderia esperando um driver
inexistente (hang).
"""
from __future__ import annotations

from engine.host import env as host_env


_POLLUTERS = {
    "CLAUDECODE": "1",
    "FORGE_FORCE_INTENT_MODE": "1",
    "FORGE_FORCE_TTY_MODE": "1",
    "OPENCODE_VERSION": "0.9",
    "OPENCODE_SERVER_PASSWORD": "secret",
    "CODEX_CLI": "1",
    "CURSOR_AGENT": "1",
    "CURSOR_TRACE_ID": "abc",
}


def test_scrub_removes_all_agentic_keys(monkeypatch):
    for k, v in _POLLUTERS.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("JAVA_HOME", "/opt/java")

    scrubbed = host_env.scrubbed_subprocess_env()

    for k in _POLLUTERS:
        assert k not in scrubbed, f"{k} deveria ter sido removido do env"
    # Keys legítimas preservadas (deny-list cirúrgica, não allowlist).
    assert scrubbed.get("PATH") == "/usr/bin"
    assert scrubbed.get("JAVA_HOME") == "/opt/java"


def test_scrub_returns_copy_not_mutating_os_environ(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    import os

    scrubbed = host_env.scrubbed_subprocess_env()
    assert "CLAUDECODE" not in scrubbed
    # os.environ original NÃO foi mutado — só a cópia.
    assert os.environ.get("CLAUDECODE") == "1"


def test_scrubbed_env_makes_detect_fall_through(monkeypatch):
    """Prova o efeito: com env scrubbed aplicado a os.environ, nenhum
    detector de host agêntico dispara."""
    for k, v in _POLLUTERS.items():
        monkeypatch.setenv(k, v)
    scrubbed = host_env.scrubbed_subprocess_env()
    monkeypatch.setattr("os.environ", scrubbed)
    assert host_env.detect_claude_code() is False
    assert host_env.detect_opencode() is False
    assert host_env.detect_codex() is False
    assert host_env.detect_cursor() is False
```

- [ ] **Step 4.2 — Rodar, confirmar RED.**

```bash
.venv/bin/pytest tests/unit/test_host_env_scrub.py -q
```

Expected: FALHA com `AttributeError: module 'engine.host.env' has no attribute
'scrubbed_subprocess_env'`.

- [ ] **Step 4.3 — Implementar o scrub (GREEN).** Em `engine/host/env.py`,
  adicione após `detect_any_agentic`:

```python
# A3 ENV-1 — key-set canônico de sinais de host agêntico. Alinhado a
# tests/unit/test_cli_upgrade_wired.py (_SCRUB_EXACT / _SCRUB_PREFIXES) e aos
# detectores acima. EXATAS: comparação por igualdade. PREFIXES: startswith.
_SCRUB_EXACT: frozenset[str] = frozenset({
    "CLAUDECODE",
    "FORGE_FORCE_INTENT_MODE",
    "FORGE_FORCE_TTY_MODE",
})
_SCRUB_PREFIXES: tuple[str, ...] = ("OPENCODE_", "CODEX", "CURSOR_")


def _is_agentic_host_key(name: str) -> bool:
    """True se ``name`` é um sinal de host agêntico que um subprocesso filho
    NÃO deve herdar."""
    if name in _SCRUB_EXACT:
        return True
    return any(name.startswith(p) for p in _SCRUB_PREFIXES)


def scrubbed_subprocess_env() -> dict[str, str]:
    """Cópia de ``os.environ`` sem os sinais de host agêntico.

    A3 ENV-1: quando o forge spawna um subprocesso (ex.: validators via
    ``engine.ingest``), o filho não deve herdar CLAUDECODE / OPENCODE_* /
    CODEX* / CURSOR_* / FORGE_FORCE_*_MODE. Caso contrário, um ``forge``
    aninhado faria ``detect_host`` escolher um adapter agêntico, emitir o
    marker ``<FORGE_INTENT/>`` + exit 2, e esperar um driver que aquele
    contexto não tem — travando (hang).

    Deny-list cirúrgica (remove só os sinais de host) — distinta de
    ``engine._sandbox.env.build_safe_env``, que é uma allowlist agressiva pra
    a sandbox de QA (objetivo: conter segredos). Os dois coexistem por terem
    objetivos diferentes; aqui preservamos PATH/HOME/JAVA_HOME/etc. que um
    validator de ingest precisa.

    Não muta ``os.environ`` — retorna cópia.
    """
    return {k: v for k, v in os.environ.items() if not _is_agentic_host_key(k)}
```

- [ ] **Step 4.4 — Wire nos spawns de ingest.** Em `engine/ingest.py`, importe
  o helper no topo (junto aos imports de engine):

```python
from engine.host.env import scrubbed_subprocess_env
```

  Na linha 377 (dentro de `_handle_post_subagent_validate`, o loop que spawna
  validators do `_SUBAGENT_VALIDATOR_MAP`), passe `env=`:

```python
        try:
            subprocess.run(
                cmd,
                capture_output=True,
                timeout=30,
                check=False,
                env=scrubbed_subprocess_env(),  # A3 ENV-1: filho não herda host agêntico
            )
        except subprocess.TimeoutExpired:
            _warn(f"forge ingest: validator {v_name} timed out")
        except OSError as exc:  # pragma: no cover - defensive
            _warn(f"forge ingest: validator {v_name} failed to launch ({exc})")
```

  Na linha 442 (dentro de `_handle_ci_pr_ingest`, o loop sobre `_CI_VALIDATORS`),
  adicione `env=scrubbed_subprocess_env()` ao `subprocess.run([...], ...)`
  correspondente (mantenha os demais kwargs intactos — capture_output, text,
  timeout=60, check=False).

  > NOTA: leia o bloco exato de `subprocess.run` em ~442 antes de editar; adicione
  > APENAS o kwarg `env=scrubbed_subprocess_env()` preservando os outros
  > argumentos. Não toque `engine/ingest.py:214` (`subprocess.check_output` de
  > `git rev-parse` — git não é host agêntico e o scrub é irrelevante ali; manter
  > escopo cirúrgico).

- [ ] **Step 4.5 — Teste de wire que exercita os DOIS spawn-sites REAIS de ingest.**
  Os spawn-sites reais (scout confirmado) são as funções módulo-nível
  `_handle_post_subagent_validate(args, project_root)` (ingest.py:347, `subprocess.run`
  na linha 377) e `_handle_ci_pr_ingest(args, project_root)` (ingest.py:415,
  `subprocess.run` na linha 442). Ambas são diretamente chamáveis com
  `args: dict[str, str]` + `project_root: Path`. O teste captura o kwarg `env=`
  passado ao `subprocess.run` e asserta que NENHUMA key de host agêntico
  (`CLAUDECODE`, `OPENCODE_*`, `CODEX*`, `CURSOR_*`, `FORGE_FORCE_*_MODE`) sobrevive
  ao boundary. Não há fallback: o invariante só é verde se o spawn REAL rodou com
  o `env=` scrubbed. Adicione a `tests/unit/test_host_env_scrub.py`:

```python
def _install_fake_validator(validators_root, name):
    """Cria um validator stub executável no diretório que ingest resolve via
    forge_home()/validators — necessário pro `v_path.is_file()` guard passar e
    o subprocess.run ser realmente alcançado."""
    validators_root.mkdir(parents=True, exist_ok=True)
    (validators_root / f"{name}.py").write_text("print('{}')\n")


def _make_run_spy():
    """subprocess.run spy que captura o env de TODOS os spawns (lista)."""
    captured: dict[str, list] = {"envs": []}

    def _fake_run(cmd, **kwargs):
        captured["envs"].append(kwargs.get("env"))

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""

        return _R()

    return _fake_run, captured


_HOST_KEYS = ("CLAUDECODE", "OPENCODE_VERSION", "CODEX_CLI", "CURSOR_AGENT",
              "FORGE_FORCE_INTENT_MODE", "FORGE_FORCE_TTY_MODE")


def _assert_no_host_keys(env):
    assert env is not None, "ingest deve passar env= explícito ao subprocesso"
    for k in _HOST_KEYS:
        assert k not in env, f"{k} vazou pro env do subprocesso de ingest"


def test_post_subagent_validate_spawns_with_scrubbed_env(tmp_path, monkeypatch):
    """Spawn-site real ingest.py:377 (_handle_post_subagent_validate) passa
    env= sem nenhum sinal de host agêntico."""
    import subprocess

    from engine import ingest

    for k in _HOST_KEYS:
        monkeypatch.setenv(k, "1")

    # forge_home()/validators é onde _handle_post_subagent_validate resolve os
    # validators. 'feature-intake' mapeia pra ['validate_feature_package'].
    forge_root = tmp_path / "forge_home"
    _install_fake_validator(forge_root / "validators", "validate_feature_package")
    monkeypatch.setattr(ingest, "forge_home", lambda: forge_root)

    fake_run, captured = _make_run_spy()
    monkeypatch.setattr(subprocess, "run", fake_run)

    ingest._handle_post_subagent_validate(
        {"subagent": "feature-intake", "task-id": "TASK-0001"},
        tmp_path,
    )

    assert captured["envs"], "o spawn real não foi alcançado — wire não exercitado"
    for env in captured["envs"]:
        _assert_no_host_keys(env)


def test_ci_pr_ingest_spawns_with_scrubbed_env(tmp_path, monkeypatch):
    """Spawn-site real ingest.py:442 (_handle_ci_pr_ingest) passa env= sem
    nenhum sinal de host agêntico."""
    import subprocess

    from engine import ingest

    for k in _HOST_KEYS:
        monkeypatch.setenv(k, "1")

    # _CI_VALIDATORS é uma tupla fixa; instala todos pra os spawns serem
    # alcançados (cada v_path.is_file() precisa existir).
    forge_root = tmp_path / "forge_home"
    for v_name in ingest._CI_VALIDATORS:
        _install_fake_validator(forge_root / "validators", v_name)
    monkeypatch.setattr(ingest, "forge_home", lambda: forge_root)

    fake_run, captured = _make_run_spy()
    monkeypatch.setattr(subprocess, "run", fake_run)

    ingest._handle_ci_pr_ingest(
        {"feature-slug": "auth-login", "pr-number": "42"},
        tmp_path,
    )

    assert captured["envs"], "o spawn real não foi alcançado — wire não exercitado"
    for env in captured["envs"]:
        _assert_no_host_keys(env)
```

  > Os dois spawn-sites são exercitados pelas funções REAIS (não por um nome
  > inventado). Não há caminho de fallback que reduza ao "invariante mínimo
  > isolado" — se o `subprocess.run` real não for alcançado, `captured["envs"]`
  > fica vazio e o teste FALHA (não passa silenciosamente). É a anti-regressão
  > direta do C2 DEAD-VERIFY: o boundary só fica verde se o WIRE rodou.
  > NOTA DE SCOUT (já confirmada): `_handle_post_subagent_validate` e
  > `_handle_ci_pr_ingest` resolvem validators via `forge_home()/validators` e
  > exigem que o arquivo `<validator>.py` exista (`v_path.is_file()`) — por isso
  > o stub. Se a leitura do código real divergir desses nomes/assinaturas, PARE e
  > reporte ao orquestrador (não invente API).

- [ ] **Step 4.6 — Rodar, confirmar GREEN.**

```bash
.venv/bin/pytest tests/unit/test_host_env_scrub.py -q
.venv/bin/pytest -m 'not integration and not e2e' -q | tail -1
```

Expected: passed; rapid count subiu, 0 falhas.

- [ ] **Step 4.7 — Commit atômico:** `fix(w2): A3 ENV-1 — scrub de host agêntico no spawn de subprocessos do ingest`

**Anti-padrões:** não criar allowlist (cirúrgico = deny-list); não duplicar
`build_safe_env` (objetivo distinto); não tocar `engine/host/detect.py` (o pin
de config já é honrado — A3 é só scrub + doc); não scrubar o `git rev-parse` de
ingest.py:214.

---

## Task 5 — C3 EXIT-2-COLLISION: recontrato estrito (exit 2 = só pausa; escada → 1 + tag)

**Files:**
- `engine/ui/exit_codes.py` (Modify — adicionar TAGs + helper `fail_with_tag`)
- `engine/plan.py` (Modify — 1565, 1675, 1727)
- `engine/implement.py` (Modify — 1138, 1168, 1177, 1186, 1315, 1333)
- `engine/verify.py` (Modify — 183, já é 1; só padroniza tag)
- `engine/qa/__init__.py` (Modify — 380)
- `engine/upgrade.py` (Modify — 230, 249)
- `engine/evolve.py` (Modify — 363)
- `engine/raw.py` (Modify — 46, 65, 69, 73, 100, 104, 133, 137, 223; NÃO 111)
- `engine/init.py` (Modify — 1117 abort retorna 2 erroneamente)
- `engine/cli.py` (Modify — 339-401: garantir que exceções não viram 2)
- `docs/design/06-command-surface.md` (Modify — 176-208: reescrever contrato + tabela de tags)
- `tests/unit/test_exit_code_contract.py` (Create)

**Interfaces:**
- Consumes: `EXIT_OK`/`EXIT_ERROR`/`EXIT_PAUSED`/`EXIT_CANCELLED` (já em
  exit_codes.py).
- Produces: constantes de TAG + `fail_with_tag(tag: str, message: str | None = None,
  *, stream=sys.stderr) -> int` que escreve `[FORGE-ERR:<TAG>]` (+ message
  opcional) em stderr e retorna `EXIT_ERROR` (1). Cada exit-site não-pausa passa
  a chamar esse helper. Contrato final: `0`/`1`/`2`(só pausa)/`130`; `127`
  preservado como exceção POSIX documentada (editor-not-found em raw.py:111).

### Contexto do bug (scout confirmado)

Exit-sites mapeados (ler cada um antes de editar):

| Arquivo:linha | Hoje | Significado | TAG alvo |
|---|---|---|---|
| `plan.py:1565` | `return 3` | abort de subtype-stub | `ABORTED` → 1 |
| `plan.py:1675` | `return 2` | not-a-project | `PROJECT-NOT-FOUND` → 1 |
| `plan.py:1727` | `return 3` | phase-locked | `LOCKED` → 1 |
| `implement.py:1138` | `return 2` | not-a-project | `PROJECT-NOT-FOUND` → 1 |
| `implement.py:1168` | `return 4` | feature missing | `FEATURE-MISSING` → 1 |
| `implement.py:1177` | `return 5` | not ready | `NOT-READY` → 1 |
| `implement.py:1186` | `return 6` | no tasks (wave D incompleta) | `WAVE-INCOMPLETE` → 1 |
| `implement.py:1315` | `return 7` | blocked external | `BLOCKED-EXTERNAL` → 1 |
| `implement.py:1333` | `return 3` | phase-locked | `LOCKED` → 1 |
| `verify.py:183` | `return 1` | not-a-project | `PROJECT-NOT-FOUND` → 1 (já 1; só tag) |
| `qa/__init__.py:380` | `return 8 if BLOCK else 0` | qa verdict BLOCK | `QA-BLOCK` → 1 (mantém 0 no else) |
| `upgrade.py:230` | `return 4` | rollback pós checkout-fail | `UPGRADE-FAILED` → 1 |
| `upgrade.py:249` | `return 4` | rollback pós smoke-fail | `UPGRADE-FAILED` → 1 |
| `evolve.py:363` | `return 2` | not-a-project | `PROJECT-NOT-FOUND` → 1 |
| `raw.py:46,65,69,73,100,104,133,137` | `return 2` | usage/no-project/not-found | `USAGE` → 1 |
| `raw.py:223` | `return 3` | migrator stub | `USAGE` → 1 (não implementado) |
| `init.py:1117` | `return 2` | abort de resume | `ABORTED` → 1 |

**PRESERVAR:** `raw.py:111` `return 127` (editor-not-found — exceção POSIX
documentada). NÃO tocar os `return 130` (pause/cancel — Decisão 27) nem os
`return 0`/`EXIT_PAUSED`/`EXIT_CANCELLED` em cli.py.

### Decisão de design (justificada)

- Centralizar tags + helper em `exit_codes.py` (já é fonte única — Mandamento 3,
  zero módulo novo).
- `qa/__init__.py:380` é especial: retorna 8 só no BLOCK, 0 no sucesso. O
  recontrato troca o 8 por `fail_with_tag("QA-BLOCK", ...)` (→1), mantendo o 0.
  Como o `finally` de qa restaura signal handler, o helper deve ser chamado ANTES
  do return (não dentro do finally).
- A mensagem mentor-calmo existente (ex.: o `sys.stderr.write` do phase-lock em
  plan.py:1723-1726) é PRESERVADA; o tag é ADICIONADO numa linha à parte via o
  helper. Padrão: primeiro o `fail_with_tag` escreve `[FORGE-ERR:LOCKED]`, depois
  (ou antes) a mensagem 3-caminhos já existente continua. Para não duplicar
  escrita, o helper aceita `message=None` quando o site já escreveu sua própria
  prosa — nesse caso só emite o tag.

### Steps

- [ ] **Step 5.1 — Teste de contrato PRIMEIRO (RED).** Crie
  `tests/unit/test_exit_code_contract.py`. Tem duas camadas: (a) teste
  parametrizado garantindo que nenhum handler retorna 2 fora do caminho de
  pausa; (b) teste por-tag confirmando `[FORGE-ERR:<TAG>]` em stderr + exit 1.

```python
"""C3 EXIT-2-COLLISION — contrato estrito de exit codes.

Contrato final:
  0   sucesso
  1   erro (com tag machine-readable [FORGE-ERR:<TAG>] em stderr)
  2   pausa aguardando input (SÓ PausedForInputError + UserPausedError)
  130 cancelamento (KeyboardInterrupt + UserCancelledError)
  127 editor-not-found (exceção POSIX documentada, só forge raw edit-config)

Este módulo prova que a escada legada (3/4/5/6/7/8 + not-a-project=2) colapsou
em 1 + tag, e que exit 2 ficou reservado pra pausa.
"""
from __future__ import annotations

import io

import pytest

from engine.ui import exit_codes


# (a) Helper fail_with_tag emite tag + retorna 1 -----------------------------


def test_fail_with_tag_writes_tag_and_returns_one():
    buf = io.StringIO()
    rc = exit_codes.fail_with_tag("LOCKED", "feature travada", stream=buf)
    assert rc == exit_codes.EXIT_ERROR == 1
    out = buf.getvalue()
    assert "[FORGE-ERR:LOCKED]" in out
    assert "feature travada" in out


def test_fail_with_tag_message_optional():
    buf = io.StringIO()
    rc = exit_codes.fail_with_tag("PROJECT-NOT-FOUND", stream=buf)
    assert rc == 1
    assert "[FORGE-ERR:PROJECT-NOT-FOUND]" in buf.getvalue()


@pytest.mark.parametrize(
    "tag",
    [
        "PROJECT-NOT-FOUND", "LOCKED", "FEATURE-MISSING", "NOT-READY",
        "WAVE-INCOMPLETE", "BLOCKED-EXTERNAL", "QA-BLOCK", "UPGRADE-FAILED",
        "USAGE", "ABORTED",
    ],
)
def test_all_canonical_tags_emit_consistently(tag):
    buf = io.StringIO()
    rc = exit_codes.fail_with_tag(tag, stream=buf)
    assert rc == 1
    assert f"[FORGE-ERR:{tag}]" in buf.getvalue()


# (b) Nenhum handler não-pausa retorna 2 -------------------------------------


def test_no_handler_source_returns_bare_two_outside_pause():
    """Varredura estática: fora de cli.py (onde EXIT_PAUSED=2 é legítimo) e de
    raw.py:111 (127), nenhum exit-site dos handlers deve usar `return 2`/`3`/
    `4`/`5`/`6`/`7`/`8` como código de erro. Eles devem usar fail_with_tag.
    """
    import re
    from pathlib import Path

    engine_root = Path(exit_codes.__file__).resolve().parent.parent
    handlers = [
        "plan.py", "implement.py", "verify.py", "upgrade.py", "evolve.py",
        "raw.py", "init.py", "qa/__init__.py",
    ]
    offenders: list[str] = []
    bad_return = re.compile(r"return\s+([2345678])\b")
    for rel in handlers:
        path = engine_root / rel
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            m = bad_return.search(stripped)
            if m:
                offenders.append(f"{rel}:{lineno}: {stripped}")
    assert not offenders, (
        "exit-sites legados de erro ainda usam return N numérico — devem usar "
        "fail_with_tag:\n" + "\n".join(offenders)
    )
```

  > NOTA: o teste estático (b) é deliberadamente conservador — ele proíbe
  > `return 2..8` literais nos handlers. `raw.py:111` usa `return 127` (não bate
  > o pattern `[2-8]\b`). `return 130`/`return 0`/`return 1` não batem. Se algum
  > site legítimo precisar de `return <expr>` que o regex pegue por engano,
  > ajuste o handler pra usar `fail_with_tag` (é o ponto). Se houver um falso
  > positivo genuíno e inevitável, reporte ao orquestrador (não relaxe o teste
  > sem autorização).

- [ ] **Step 5.2 — Rodar, confirmar RED.**

```bash
.venv/bin/pytest tests/unit/test_exit_code_contract.py -q
```

Expected: `test_fail_with_tag_*` FALHAM (`fail_with_tag` não existe);
`test_no_handler_source_returns_bare_two_outside_pause` FALHA (lista os
~18 offenders mapeados na tabela).

- [ ] **Step 5.3 — Implementar tags + helper em exit_codes.py (GREEN parte 1).**
  Em `engine/ui/exit_codes.py`, adicione `import sys` ao topo e, após o `__all__`
  atual, adicione:

```python
import sys
from typing import TextIO

# ── C3 EXIT-2-COLLISION — tags machine-readable ───────────────────────────────
#
# A escada legada (exit 3/4/5/6/7/8 + not-a-project=2) colapsou em EXIT_ERROR
# (1) + uma tag estável em stderr no formato ``[FORGE-ERR:<TAG>]``. O host/
# driver parseia a tag pra ramificar comportamento sem depender de um código
# numérico ambíguo. Exit 2 ficou reservado SÓ pra pausa (PausedForInputError +
# UserPausedError). Exit 127 (editor-not-found) permanece como exceção POSIX
# documentada em ``forge raw edit-config``.
ERR_PROJECT_NOT_FOUND: str = "PROJECT-NOT-FOUND"
ERR_LOCKED: str = "LOCKED"
ERR_FEATURE_MISSING: str = "FEATURE-MISSING"
ERR_NOT_READY: str = "NOT-READY"
ERR_WAVE_INCOMPLETE: str = "WAVE-INCOMPLETE"
ERR_BLOCKED_EXTERNAL: str = "BLOCKED-EXTERNAL"
ERR_QA_BLOCK: str = "QA-BLOCK"
ERR_UPGRADE_FAILED: str = "UPGRADE-FAILED"
ERR_USAGE: str = "USAGE"
ERR_ABORTED: str = "ABORTED"


def fail_with_tag(
    tag: str,
    message: str | None = None,
    *,
    stream: TextIO | None = None,
) -> int:
    """Emite ``[FORGE-ERR:<tag>]`` (+ ``message``) em stderr e retorna 1.

    Fonte única do contrato C3: todo exit-site de ERRO dos handlers chama este
    helper em vez de ``return <N>``. Quando o site já escreveu sua própria prosa
    mentor-calmo (ex.: a mensagem 3-caminhos de phase-lock), passe
    ``message=None`` — o helper emite só a tag, sem duplicar a prosa.

    A tag é estável e machine-readable; o host/driver ramifica por ela.
    """
    out = stream if stream is not None else sys.stderr
    if message:
        out.write(f"[FORGE-ERR:{tag}] {message}\n")
    else:
        out.write(f"[FORGE-ERR:{tag}]\n")
    return EXIT_ERROR


__all__ = [
    "EXIT_OK", "EXIT_ERROR", "EXIT_PAUSED", "EXIT_CANCELLED",
    "ERR_PROJECT_NOT_FOUND", "ERR_LOCKED", "ERR_FEATURE_MISSING",
    "ERR_NOT_READY", "ERR_WAVE_INCOMPLETE", "ERR_BLOCKED_EXTERNAL",
    "ERR_QA_BLOCK", "ERR_UPGRADE_FAILED", "ERR_USAGE", "ERR_ABORTED",
    "fail_with_tag",
]
```

  (Substitua o `__all__` antigo de 1 linha por este — não deixe dois `__all__`.)

- [ ] **Step 5.4 — Re-mapear os exit-sites (GREEN parte 2).** Em cada handler,
  importe os símbolos necessários de `engine.ui.exit_codes` e troque os returns.
  Padrão por site (exemplos canônicos — replique a forma exata):

  **plan.py** — adicione ao import: `from engine.ui.exit_codes import fail_with_tag, ERR_ABORTED, ERR_PROJECT_NOT_FOUND, ERR_LOCKED`

  - `plan.py:1565` (`return 3` abort): o site já escreveu "Abortado. Nada mais
    escrito." via `renderer.write`. Troque por:
    ```python
    return fail_with_tag(ERR_ABORTED)
    ```
  - `plan.py:1675` (`return 2` not-a-project): o site já fez
    `sys.stderr.write(f"forge plan: {exc}\n")`. Troque o `return 2` por:
    ```python
    return fail_with_tag(ERR_PROJECT_NOT_FOUND)
    ```
  - `plan.py:1727` (`return 3` phase-locked): o site já escreveu a mensagem
    3-caminhos. Troque por:
    ```python
    return fail_with_tag(ERR_LOCKED)
    ```

  **implement.py** — import: `from engine.ui.exit_codes import fail_with_tag, ERR_PROJECT_NOT_FOUND, ERR_FEATURE_MISSING, ERR_NOT_READY, ERR_WAVE_INCOMPLETE, ERR_BLOCKED_EXTERNAL, ERR_LOCKED`
  - `1138` → `return fail_with_tag(ERR_PROJECT_NOT_FOUND)`
  - `1168` → `return fail_with_tag(ERR_FEATURE_MISSING)`
  - `1177` → `return fail_with_tag(ERR_NOT_READY)`
  - `1186` → `return fail_with_tag(ERR_WAVE_INCOMPLETE)`
  - `1315` → `return fail_with_tag(ERR_BLOCKED_EXTERNAL)` (remova o comentário
    "distinct exit code — caller scripts can switch behavior", agora a
    diferenciação é via tag)
  - `1333` → `return fail_with_tag(ERR_LOCKED)`

  **verify.py** — import: `from engine.ui.exit_codes import fail_with_tag, ERR_PROJECT_NOT_FOUND`
  - `183` (`return 1` not-a-project): já escreveu via `renderer.write(...red)`.
    Troque por `return fail_with_tag(ERR_PROJECT_NOT_FOUND)` (mantém exit 1, só
    adiciona a tag pro host parsear). NOTA: o site usa `renderer.write` (não
    stderr cru) pra a prosa; o `fail_with_tag` escreve a tag em stderr — os dois
    canais coexistem (prosa cinematográfica + tag machine-readable).

  **qa/__init__.py:380** — import: `from engine.ui.exit_codes import fail_with_tag, ERR_QA_BLOCK`. Troque:
    ```python
        if result.verdict == "BLOCK":
            return fail_with_tag(ERR_QA_BLOCK)
        return 0
    ```
    (preserva o 0 no sucesso; o `finally` de restore de signal handler roda
    normalmente — `fail_with_tag` só escreve+retorna, sem afetar o finally).

  **upgrade.py** — import: `from engine.ui.exit_codes import fail_with_tag, ERR_UPGRADE_FAILED`
  - `230` → `return fail_with_tag(ERR_UPGRADE_FAILED)`
  - `249` → `return fail_with_tag(ERR_UPGRADE_FAILED)`

  **evolve.py** — import: `from engine.ui.exit_codes import fail_with_tag, ERR_PROJECT_NOT_FOUND`
  - `363` → `return fail_with_tag(ERR_PROJECT_NOT_FOUND)`

  **raw.py** — import: `from engine.ui.exit_codes import fail_with_tag, ERR_USAGE`
  - `46, 65, 69, 73, 100, 104, 133, 137` → cada `return 2` vira
    `return fail_with_tag(ERR_USAGE)` (os sites já fazem `print(..., file=sys.stderr)`
    com a mensagem específica; o `fail_with_tag` adiciona a tag).
  - `223` (migrator stub) → `return fail_with_tag(ERR_USAGE)`.
  - **NÃO tocar `raw.py:111`** (`return 127` editor-not-found — preservado).

  **init.py:1117** — import: `from engine.ui.exit_codes import fail_with_tag, ERR_ABORTED`. O site já escreveu "Ok, abortado. O checkpoint segue intacto...". Troque `return 2` por:
    ```python
            return fail_with_tag(ERR_ABORTED)
    ```
    (este é um overload acidental do exit 2 — abort NÃO é pausa; o recontrato
    corrige.)

- [ ] **Step 5.5 — cli.py: garantir que exceções não viram 2.** Em
  `engine/cli.py:339-401`, o bloco try/except já está correto: só
  `PausedForInputError` e `UserPausedError` retornam `EXIT_PAUSED` (2);
  `RaceDetectedError`/`IntentMismatchError`/`JsonIOError` retornam 1. CONFIRME
  (leia o bloco) que nenhuma exceção não-pausa cai num path que retorne 2.
  Adicione um comentário load-bearing acima do `except PausedForInputError`
  reforçando o contrato C3:

```python
        # C3 EXIT-2-COLLISION — exit 2 é reservado ESTRITAMENTE pra pausa
        # (PausedForInputError + UserPausedError). Todos os erros dos handlers
        # colapsaram em exit 1 + tag [FORGE-ERR:<TAG>] (ver engine/ui/exit_codes.py
        # fail_with_tag). Nenhuma exceção não-pausa pode retornar 2 a partir
        # daqui.
```

  Não mude lógica em cli.py — só o comentário (a lógica já honra o contrato pós
  Task 5.4).

- [ ] **Step 5.6 — Reescrever a seção Exit codes do doc canônico.** Em
  `docs/design/06-command-surface.md:176-208`, substitua a tabela e a prosa pela
  versão do contrato estrito + tabela de tags. Justificativa textual obrigatória
  (Mandamento 4 — arquivo load-bearing): a edição é o escopo central de C3
  (recontrato de exit codes), alinhada à Decisão 27 (pausa) sem revisitá-la.
  Conteúdo:

```markdown
## Exit codes

Contrato canônico do dispatcher (`bin/forge` → `engine/cli.py::main()`).
Recontratado em W2 (protocol robustness, 2026-06-17, finding C3
EXIT-2-COLLISION): exit 2 é reservado ESTRITAMENTE pra pausa; a escada legada
(3/4/5/6/7/8 + not-a-project=2) colapsou em `exit 1` + tag machine-readable em
stderr.

| Code | Significado | Origem |
|---|---|---|
| 0 | comando completou com sucesso | handler retornou normalmente |
| 1 | erro (carrega tag `[FORGE-ERR:<TAG>]` em stderr) | todo erro de handler via `fail_with_tag` + exceções não-listadas |
| 2 | paused for input (needs response) | SÓ `PausedForInputError` (engine emitiu pending) + `UserPausedError` (response `paused: true`) |
| 127 | editor não encontrado | exceção POSIX documentada — só `forge raw edit-config` |
| 130 | user cancelou | `KeyboardInterrupt` (TTY) + `UserCancelledError` (response `cancelled: true`) |

**Tags machine-readable (exit 1).** Toda saída de erro de handler emite uma tag
estável em stderr no formato `[FORGE-ERR:<TAG>]`. O host/driver ramifica por ela
sem depender de código numérico ambíguo. Tags canônicas (fonte única:
`engine/ui/exit_codes.py`):

| TAG | Quando | Comandos |
|---|---|---|
| `PROJECT-NOT-FOUND` | fora de um projeto forge | plan, implement, verify, evolve |
| `LOCKED` | feature phase-locked por outro comando | plan, implement |
| `FEATURE-MISSING` | feature não existe (rode `forge plan` antes) | implement |
| `NOT-READY` | readiness != 'ready' (finalize Wave E) | implement |
| `WAVE-INCOMPLETE` | sem tasks (Wave D do plano incompleta) | implement |
| `BLOCKED-EXTERNAL` | task bloqueada por ticket externo | implement |
| `QA-BLOCK` | verdict do `forge qa` = BLOCK | qa |
| `UPGRADE-FAILED` | rollback após checkout/smoke falho | upgrade |
| `USAGE` | uso inválido / sem projeto / arquivo ausente | raw |
| `ABORTED` | usuário abortou um gate (subtype-stub, resume de init) | plan, init |

O host (Claude Code OR adapter intent-file) loop-reads exit code 2 + state files
(`.claude/forge/state/forge-pending.json` / `forge-response.json`) pra
continuação. Subagent invocando `forge` que receba exit 2 NÃO deve responder
sozinho — ver `.claude/rules/subagent-workflow.md §Quando subagent invoca \`forge\``.

**Exit 130 — duas rotas convergentes:**
- (a) `KeyboardInterrupt` (Ctrl+C / SIGINT) em modo TTY.
- (b) Host response `cancelled: true` (`UserCancelledError`) em modo intent.

Callers tratam identicamente — usuário desistiu (Decisão 27 cobre a rota TTY;
CR-001 do W2-DRIFT review cobre a rota intent).

Schema dos state files: `docs/schemas/intent-protocol.md`.
Spec canônico: `docs/superpowers/specs/drift-1-intent-protocol.md` §4.

POSIX nota: exit 2 às vezes é usado por shells pra "misuse of shell builtins";
`forge` não é shell builtin, então o conflito é nominal.
```

- [ ] **Step 5.7 — Rodar o contrato + suite completa.**

```bash
.venv/bin/pytest tests/unit/test_exit_code_contract.py -q
.venv/bin/pytest -m 'not integration and not e2e' -q | tail -1
```

Expected: contrato 100% verde (parametrizado + estático); rapid count subiu, 0
falhas. SE algum teste pré-existente assertava um código numérico legado (ex.:
um teste que esperava `rc == 4` pra feature-missing), ELE PRECISA migrar pra
esperar `rc == 1` + tag `[FORGE-ERR:FEATURE-MISSING]`. Esses são test-updates
legítimos do clean-break (não redução de cobertura) — atualize-os e cite no
commit body. Procure-os com:

```bash
.venv/bin/pytest -m 'not integration and not e2e' -q 2>&1 | grep -E "FAILED|assert.*== [2345678]" | head
grep -rnE "returncode == [2345678]\b|rc == [2345678]\b|== EXIT.*[3-8]" tests/ | grep -vE "127|130" | head -30
```

  Atualize cada teste que assertava código legado pra o novo contrato (1 + tag).
  Se o volume de updates passar de ~25, declare o escopo expandido no commit body
  (clean-break, spec §5) — NÃO entre em loop de BLOCKED; reporte ao orquestrador
  se a contagem surpreender (>40).

- [ ] **Step 5.8 — e2e relevante (se houver).**

```bash
RUN_E2E=1 .venv/bin/pytest tests/e2e -q -k "exit or plan or implement or upgrade or qa" | tail -5
```

Expected: 0 falhas (ou os e2e que assertavam código legado migrados junto).

- [ ] **Step 5.9 — Commit atômico:** `feat(w2): C3 EXIT-2-COLLISION — exit 2 só pausa; escada → 1 + [FORGE-ERR:<TAG>]`

**Anti-padrões:** não tocar `raw.py:111` (127 preservado); não mexer nos
`return 130`/`return 0`; não tocar `docs/design/01-decisions.md` (Decisão 27 é
honrada, não revisitada); não reduzir cobertura de teste (migrar asserções
legadas ≠ remover); não improvisar tags fora da lista canônica.

---

## Task 6 — A4 REPLAY (narrow) + doc-sync consolidado

**Files:**
- `engine/reconfigure.py` (Modify — `_cards_remove` 528-558: deferir o `shutil.move` pra pós-confirm)
- `tests/unit/test_reconfigure_cards_remove_replay.py` (Create)
- `CHANGELOG.md` (Modify — `## [Unreleased]`)
- `docs/design/08-session-handoff.md` (Modify — Última atualização + Estado)
- `docs/design/04-pending.md` (Modify — riscar DEAD-VERIFY/EXIT-2-COLLISION/CONC-1/ENV-1 fechados; anotar REPLAY-2-write como falso-positivo + REPLAY card-removal fechado)
- `README.md` (Modify — só se stats mudarem)

**Interfaces:**
- Consumes: nenhum novo; usa o fluxo de confirm já existente em
  `reconfigure.py::run` (apply-confirm em 366).
- Produces: card-removal que NÃO muta o snapshot → `.bak` até o usuário
  confirmar o apply; doc-sync de toda a wave.

### Contexto (scout confirmado) — veredito por caminho

- **REPLAY-2 WRITE path (config) — FALSO-POSITIVO confirmado.** `reconfigure.py:366-378`:
  `confirm("Aplicar essas mudanças?")` ocorre ANTES de `backup_file(config_path)`
  + `write_yaml(...)`. O cancel (366-374) retorna 0 sem escrever. A mutação de
  config é corretamente gated pelo confirm. NÃO endereçar — documentar o porquê
  em `04-pending.md`.
- **REPLAY init "resume=restart" — FALSO-POSITIVO.** `init.py:1118` "resume →
  segue sem apagar o checkpoint; o pipeline regrava no final". As re-mutações do
  pipeline (hook install, card snapshot, config write) são idempotentes
  (marker-guarded canonical-wins em `_install_ai_driver`; `shutil.copy2` overwrite
  em `_install_hooks`). Não é replay-antes-de-confirm. (O `init.py:1117` abort=2
  já foi corrigido na Task 5 como EXIT-2-COLLISION, não como REPLAY.) Documentar.
- **REPLAY card-removal — REAL, endereçar.** `_cards_remove` (528-558):
  `shutil.move(snap → .bak)` (550-553) roda DENTRO do menu loop (`_handle_cards`
  → `_cards_remove`), ANTES do apply-confirm em 366. O comentário em 300-301
  confirma "post-mutation: cards.remove já moveu .bak". Se o usuário remove um
  card e depois cancela no apply-confirm, o snapshot já virou `.bak` e o cancel
  não restaura → drift com a config → `forge verify` hard-fail.

### Decisão de design (justificada)

Deferir a mutação física (`shutil.move`) pra pós-confirm. `_cards_remove` apenas
REGISTRA a intenção de remoção (atualiza `working["cards"]["active"]` — que já
faz, 555-558) e empurra o nome pra uma lista de remoções pendentes no `working`
(ex.: `working["_pending_card_removals"]`). O `run()` aplica os `shutil.move`
SÓ depois do `confirm` passar (após linha 378, junto da escrita de config). No
cancel, nada foi movido → sem drift.

> NOTA DE ESCOPO: se o scout de `reconfigure.py::run` mostrar que aplicar os
> moves pós-confirm exige reestruturação ampla do fluxo (ex.: o `working` não
> sobrevive até o ponto de write, ou há múltiplos pontos de escrita), PARE e
> reporte 3-caminhos ao orquestrador. A fatia mínima é: registrar intenção em
> `_cards_remove`, aplicar no único ponto pós-confirm. Não refatore o menu
> inteiro.

### Steps

- [ ] **Step 6.1 — Teste PRIMEIRO (RED).** Crie
  `tests/unit/test_reconfigure_cards_remove_replay.py`. O teste prova que
  cancelar após escolher remover um card NÃO move o snapshot pra `.bak`:

```python
"""A4 REPLAY (card-removal) — cancelar o apply-confirm após escolher remover
um card NÃO deve ter movido o snapshot pra .bak.

Bug original: _cards_remove fazia shutil.move(snap → .bak) durante o menu,
antes do apply-confirm. Cancelar deixava o snapshot removido sem a config
correspondente → drift → forge verify hard-fail.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from engine import reconfigure


def _seed_card_snapshot(project_root: Path, name: str) -> Path:
    from engine.utils.paths import cards_dir

    snap = cards_dir(project_root) / name
    snap.mkdir(parents=True)
    (snap / "card.yaml").write_text(f"name: {name}\nversion: 1\n")
    return snap


def test_cards_remove_does_not_move_bak_before_confirm(tmp_path, monkeypatch):
    project_root = tmp_path
    (project_root / ".claude" / "forge").mkdir(parents=True)
    snap = _seed_card_snapshot(project_root, "telemetry")
    working = {"cards": {"active": [{"name": "telemetry"}]}}

    # Mocka as perguntas: escolhe remover 'telemetry'.
    monkeypatch.setattr(
        reconfigure.question, "ask", lambda *a, **k: "remove"
    )
    monkeypatch.setattr(
        reconfigure.question, "ask_multi", lambda *a, **k: ["telemetry"]
    )
    # resolve() sem erros de dependência (remoção permitida).
    monkeypatch.setattr(
        reconfigure, "resolve",
        lambda remaining: type("R", (), {"errors": []})(),
    )

    reconfigure._cards_remove(project_root, working)

    # INVARIANTE: o snapshot AINDA existe (move deferido pra pós-confirm);
    # working registra a intenção de remoção.
    assert snap.is_dir(), (
        "o snapshot NÃO deve ter sido movido pra .bak antes do confirm"
    )
    assert not snap.with_name("telemetry.bak").exists()
    assert "telemetry" not in [
        c["name"] for c in working["cards"]["active"]
    ], "working deve registrar a remoção (active atualizado)"
    assert "telemetry" in working.get("_pending_card_removals", [])
```

- [ ] **Step 6.2 — Rodar, confirmar RED.**

```bash
.venv/bin/pytest tests/unit/test_reconfigure_cards_remove_replay.py -q
```

Expected: FALHA — `snap.with_name("telemetry.bak").exists()` é True (move ainda
acontece) E `_pending_card_removals` não existe em `working`.

- [ ] **Step 6.3 — Deferir o move (GREEN).** Em `engine/reconfigure.py`,
  `_cards_remove` (528-558): substitua o loop de `shutil.move` por registro de
  intenção:

```python
    for name in picked:
        # A4 REPLAY: NÃO move o snapshot agora. Registra a intenção; o move
        # físico (snap → .bak) é aplicado SÓ após o apply-confirm passar (em
        # run(), pós-linha 378). Cancelar o confirm deixa o snapshot intacto —
        # sem drift entre cards/ e a config.
        working.setdefault("_pending_card_removals", []).append(name)
        renderer.write(renderer.colored(f"  - {name} (remoção pendente — aplica no confirm)", "yellow"))
    working.setdefault("cards", {})["active"] = [
        c for c in (working.get("cards") or {}).get("active") or []
        if c.get("name") not in picked
    ]
```

  Em `reconfigure.py::run`, APÓS o `write_yaml(config_path, working, atomic=True)`
  (linha 378) e ANTES do `_append_history` (381), aplique os moves pendentes:

```python
    # A4 REPLAY: aplica as remoções de card SÓ agora — pós apply-confirm
    # bem-sucedido. shutil já está importado no topo do módulo.
    pending_removals = working.pop("_pending_card_removals", [])
    if pending_removals:
        project_cards_root = cards_dir(project_root)
        for name in pending_removals:
            snap_dir = project_cards_root / name
            if snap_dir.exists():
                shutil.move(str(snap_dir), str(snap_dir.with_name(name + ".bak")))
```

  > NOTA: `working` é gravado em `write_yaml` ANTES do pop — confirme que o
  > campo interno `_pending_card_removals` não polui a config persistida. Se
  > poluir (o YAML agora carrega `_pending_card_removals`), faça o `pop` ANTES
  > do `write_yaml` e segure a lista numa var local:
  > ```python
  > pending_removals = working.pop("_pending_card_removals", [])
  > before_sha = file_sha256(config_path)
  > backup_file(config_path)
  > write_yaml(config_path, working, atomic=True)
  > # ... aplica pending_removals aqui ...
  > ```
  > Escolha a forma que NÃO persiste o campo interno na config. Decida pela
  > leitura do fluxo real e justifique no commit.

- [ ] **Step 6.4 — Rodar, confirmar GREEN + suite.**

```bash
.venv/bin/pytest tests/unit/test_reconfigure_cards_remove_replay.py -q
.venv/bin/pytest -m 'not integration and not e2e' -q | tail -1
```

Expected: passed; rapid count subiu, 0 falhas. Se algum teste pré-existente de
reconfigure assertava o move imediato, migre-o pro novo contrato (move
pós-confirm) — test-update legítimo, cite no commit.

- [ ] **Step 6.5 — Doc-sync: CHANGELOG.** Em `CHANGELOG.md`, sob `## [Unreleased]`,
  adicione (criando as subseções se faltarem):

```markdown
### Fixed (W2 — protocol robustness, 2026-06-17)

- **C2 DEAD-VERIFY** — `hooks/git-pre-commit` agora checa o validador em
  `.claude/forge/hooks/` (sub-namespace canônico de consumidores) além do path
  legado `.claude/hooks/` (repo maintainer). O gate pre-commit deixou de ser
  no-op silencioso em projetos inicializados via `forge init`. Teste de
  integração exercita a cadeia REAL do delegator
  (`tests/integration/test_git_pre_commit_delegator.py`).
- **C4 CONC-1** — `engine/utils/json_io.write_json` usa tempfile por-processo
  (`{pid}.{uuid}.tmp`) eliminando torn write / `FileNotFoundError` quando dois
  forge escrevem o mesmo state file (C4-A). `engine/ui/intent_state.pending_lock`
  (novo CM `fcntl`/`msvcrt`) é APLICADO na seção crítica real
  `detect_race`+`write_pending` de `engine/host/adapters/intent_file.py::_ask_loop`,
  fechando a janela TOCTOU em produção (C4-B). Os testes de concorrência
  (`test_intent_state_concurrency.py`) tiveram as asserções flipadas de
  "documenta o gap" para "sem torn write" e ganharam um teste do caminho real do
  adapter sob contenção.
- **A3 ENV-1** — `engine/host/env.scrubbed_subprocess_env` remove sinais de host
  agêntico (CLAUDECODE / OPENCODE_* / CODEX* / CURSOR_* / FORGE_FORCE_*_MODE) do
  env de subprocessos spawnados por `engine/ingest.py`. Um forge aninhado não
  escolhe mais o adapter errado nem pende esperando driver inexistente.
- **A4 REPLAY (card-removal)** — `forge reconfigure` defere o `shutil.move`
  (snap → `.bak`) da remoção de card pra DEPOIS do apply-confirm. Cancelar não
  deixa mais o snapshot removido sem a config correspondente.

### Changed (W2 — protocol robustness, 2026-06-17)

- **C3 EXIT-2-COLLISION (load-bearing UX/contract)** — recontrato estrito de
  exit codes: `2` é reservado SÓ pra pausa (`PausedForInputError` +
  `UserPausedError`); a escada legada (3/4/5/6/7/8 + not-a-project=2) colapsou em
  `exit 1` + tag machine-readable `[FORGE-ERR:<TAG>]` em stderr. `127`
  (editor-not-found) preservado como exceção POSIX. Tags canônicas centralizadas
  em `engine/ui/exit_codes.py` (`fail_with_tag`). Contrato + tabela de tags em
  `docs/design/06-command-surface.md §Exit codes`. Clean-break pré-produção
  (sem migrator; único caller é o driver host).
```

- [ ] **Step 6.6 — Doc-sync: handoff.** Em `docs/design/08-session-handoff.md`,
  atualize o topo:

```markdown
**Última atualização:** 2026-06-17 (W2 protocol robustness — C2/C3/C4/A3 fechados + A4 narrow)
**Estado W2 protocol robustness:** ✅ entregue sobre `feat/w2-protocol-robustness`. Quatro findings da auditoria consolidada fechados: C2 DEAD-VERIFY (delegator pre-commit checa sub-namespace + legado), C3 EXIT-2-COLLISION (exit 2 = só pausa; escada → 1 + `[FORGE-ERR:<TAG>]`), C4 CONC-1 (tempfile por-processo C4-A + flock aplicado na seção crítica real `IntentFileAdapter._ask_loop` C4-B), A3 ENV-1 (scrub de host agêntico no spawn de subprocessos do ingest). A4 REPLAY tratado narrow: card-removal defere `.bak` move pós-confirm; REPLAY-2-write (config) e init "resume=restart" confirmados falso-positivos (mutação já gated pelo confirm / re-mutação idempotente) — documentados em `04-pending.md`. Sem decisão locked tocada. Counts: confirme com `.venv/bin/pytest`. Detalhes em CHANGELOG `## [Unreleased] §Fixed/Changed (W2)`.
```

  (Preserve as entradas "Última atualização anterior" / "Estado ..." abaixo —
  append-only no topo, não delete histórico.)

- [ ] **Step 6.7 — Doc-sync: 04-pending.md.** Em `docs/design/04-pending.md`,
  no bloco "Follow-ups OUT da Wave 1 AI-first" (218-241), risque os 3 fechados e
  adicione a nota de REPLAY. Troque os 3 bullets EXIT-2-COLLISION / DEAD-VERIFY /
  CONC-1 (229-238) por versões riscadas + adicione ENV-1/REPLAY:

```markdown
- ~~**EXIT-2-COLLISION (amplo)**~~ — **FECHADO em W2** (C3). exit 2 reservado pra
  pausa; escada legada → exit 1 + `[FORGE-ERR:<TAG>]`. Ver
  `docs/design/06-command-surface.md §Exit codes` + `engine/ui/exit_codes.py`.
- ~~**DEAD-VERIFY**~~ — **FECHADO em W2** (C2). delegator `hooks/git-pre-commit`
  checa sub-namespace + legado; teste de integração exercita a cadeia real.
- ~~**CONC-1**~~ — **FECHADO em W2** (C4), ambas as partes:
  - **C4-A** (Task 2) — tempfile por-processo `{pid}.{uuid}.tmp` em
    `engine/utils/json_io.write_json` elimina o torn write / `FileNotFoundError`
    no nível de bytes.
  - **C4-B** (Task 3) — `engine/ui/intent_state.pending_lock` (flock `LOCK_EX`)
    APLICADO na seção crítica REAL `detect_race`+`write_pending` de
    `engine/host/adapters/intent_file.py::_ask_loop` — fecha a janela TOCTOU em
    produção, não só expõe o helper.
- ~~**ENV-1**~~ — **FECHADO em W2** (A3). `scrubbed_subprocess_env` no boundary de
  spawn do ingest + pin `host: intent-file` (já honrado por `detect.py`)
  documentado.

### REPLAY — veredito W2 (2026-06-17)

- **REPLAY card-removal** — **FECHADO em W2** (A4). `forge reconfigure` defere o
  `shutil.move(snap → .bak)` da remoção de card pra pós apply-confirm.
- **REPLAY-2 WRITE path (config)** — **FALSO-POSITIVO confirmado.**
  `reconfigure.py:366-378`: o `confirm("Aplicar essas mudanças?")` ocorre ANTES
  de `backup_file` + `write_yaml`; o cancel retorna 0 sem escrever. A mutação de
  config já é gated pelo confirm. Não endereçado por design.
- **REPLAY init "resume=restart"** — **FALSO-POSITIVO.** `init.py:1118` re-roda o
  pipeline, mas as mutações são idempotentes (driver install marker-guarded
  canonical-wins; hook copy overwrite). Não é replay-antes-de-confirm. (O
  `init.py:1117` abort=2 foi corrigido na Task 5 como EXIT-2-COLLISION, não
  REPLAY.)
```

- [ ] **Step 6.8 — Doc-sync: README (condicional).** Rode
  `git diff --stat feat/w2-protocol-robustness` (ou contra a base) pra ver se
  algum stat do README mudou (test count, validator count, LOC). Se o README
  cita um número de testes que mudou, atualize-o; senão, NÃO toque (Mandamento 4
  — não edite por edição). Note: README normalmente não fixa o count exato de
  testes (consulta o handoff), então provavelmente é no-op. Confirme com:

```bash
grep -nE "[0-9]{3,4} (tests|passed)|test count|LOC" README.md | head
```

- [ ] **Step 6.9 — Verificação final da wave inteira.**

```bash
.venv/bin/pytest -m 'not integration and not e2e' -q | tail -1
.venv/bin/pytest -m integration -q | tail -1
RUN_E2E=1 .venv/bin/pytest tests/e2e -q | tail -1
```

Expected: rapid > 1708 (subiu com os testes novos das tasks 1-6), integration >=
175, e2e = 30; 0 falhas em todas as lanes.

- [ ] **Step 6.10 — Commit atômico:** `fix(w2): A4 REPLAY card-removal pós-confirm + doc-sync W2 (CHANGELOG/handoff/04-pending)`

**Anti-padrões:** não refatorar o menu de reconfigure inteiro (fatia mínima:
registrar intenção + aplicar pós-confirm); não inventar fix pra REPLAY-2-write
(falso-positivo); não tocar `docs/design/01-decisions.md`; não persistir
`_pending_card_removals` na config YAML.

---

## Self-Review

**Spec coverage vs os 5 findings:**

- **C2 DEAD-VERIFY** → Task 1. Cobre o delegator (sub-namespace + legado) + teste
  de integração que exercita a cadeia REAL (não o stub arbitrário do teste antigo).
  Subtleza do repo maintainer vs consumidor scoutada e tratada (fallback legado
  preservado).
- **C3 EXIT-2-COLLISION** → Task 5. Recontrato estrito (exit 2 = só pausa);
  TODOS os 18 exit-sites mapeados (plan/implement/verify/qa/upgrade/evolve/raw/init)
  re-mapeados pra `fail_with_tag` + tag. `127` preservado. cli.py confirmado.
  Doc canônico reescrito. Teste parametrizado ("nenhum handler retorna 2 fora da
  pausa") + por-tag.
- **C4 CONC-1** → Tasks 2 (tempfile por-processo, C4-A) + 3 (flock TOCTOU
  APLICADO na seção crítica real `IntentFileAdapter._ask_loop`, C4-B). Teste
  `test_concurrent_writers_document_torn_write_window` FLIPADO de "documenta
  corrupção" pra "sem torn write"; teste novo `test_adapter_ask_loop_serializes_
  via_applied_lock` exercita o caminho de produção sob contenção (só fica verde
  com o lock aplicado). flock reusa o padrão de `l1.py`. Ambas as partes fecham
  CONC-1 — não há débito residual de TOCTOU em produção.
- **A3 ENV-1** → Task 4. Scrub no boundary de spawn do ingest + pin host
  documentado. O teste de wire exercita os DOIS spawn-sites REAIS
  (`_handle_post_subagent_validate` ingest.py:377 + `_handle_ci_pr_ingest`
  ingest.py:442) capturando o kwarg `env=` — sem fallback que reduza ao
  invariante isolado; o boundary só fica verde se o spawn real rodou. Reusa
  key-set canônico; coexiste com `build_safe_env` (objetivos distintos,
  documentado).
- **A4 REPLAY** → Task 6. Card-removal deferido pós-confirm (real); REPLAY-2-write
  e init resume=restart documentados como falso-positivo após confirmação no
  código.

**Doc-sync (Mandamento 6):** Task 6 cobre CHANGELOG (`### Fixed`/`### Changed`),
08-session-handoff.md (Última atualização + Estado), 04-pending.md (riscar 4
findings fechados + nota REPLAY), README (condicional). 06-command-surface.md
(exit codes) coberto por C3 (Task 5), não Task 6. `docs/design/01-decisions.md`
NÃO tocado — confirmado em Global Constraint 5.

**Placeholder scan:** Nenhum `TBD`/`TODO`/`FIXME`/`...` em blocos de código.
Cada step carrega código real completo. As "NOTA DE SCOUT" são instruções
explícitas de verificação pré-edição (nome real de função interna em ingest,
resolvedor de state dir em intent_state, forma do pop em reconfigure), não
placeholders — pedem leitura do código real antes de aplicar, com fallback
definido.

**Type/name consistency:** `fail_with_tag` (helper), `EXIT_*` (existentes),
`ERR_*` (constantes de tag), `scrubbed_subprocess_env` / `_is_agentic_host_key`
/ `_SCRUB_EXACT` / `_SCRUB_PREFIXES` (A3), `pending_lock` / `_pending_lock_path`
(C4-B), `_pending_card_removals` (A4) — grafia consistente entre tasks. Tags
machine-readable idênticas entre exit_codes.py, doc canônico e testes
(`PROJECT-NOT-FOUND`, `LOCKED`, `FEATURE-MISSING`, `NOT-READY`,
`WAVE-INCOMPLETE`, `BLOCKED-EXTERNAL`, `QA-BLOCK`, `UPGRADE-FAILED`, `USAGE`,
`ABORTED`).
