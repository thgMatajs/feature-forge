# feature-forge v1.3 — pilot-ready foundation

**Data:** 2026-06-16
**Status:** design (pre-W0)
**Versão alvo:** v1.3.0
**Persona-âncora:** Marina (PRIMÁRIA, [`01-personas.md`](../../product/01-personas.md) Camada A)
**Onda produto:** parte 1 da Onda 1 ([`03-roadmap.md`](../../product/03-roadmap.md) §2 — "Autopilot completo" v1.3 → v1.4)
**Branch precondition (W0):** `feat/v1.3-pilot-ready` criada a partir de `main` 100% sincronizada com `origin/main` via `git pull --ff-only`

---

## §1 — Goal + Escopo

### Goal de v1.3 ("pilot-ready foundation")

Forge instala em 1 comando, sobrevive em projetos brownfield denso (MeoBonsai-class — `.claude/` com skills/agents/hooks/settings.json pré-existentes), e roda com UX fluida sob Claude Code + opencode aproveitando as tools nativas de cada harness — sem perder a opção de TTY humano.

### Escopo IN

- **A.** Bug-fix wave — 3 críticos do relatório de compatibilidade MeoBonsai (checkpoint × intent-id mismatch, stale `forge-response.json` poisoning, piped stdin ignorado) + 4 usabilidade (exit codes inconsistentes, WARN noise em `--help`, box-drawing Unicode em non-TTY, `forge qa` API inconsistente).
- **B.** Host-aware execution — detecção híbrida (auto-detect via env vars CLAUDECODE/OPENCODE_*/CODEX_*/CURSOR_* + override via campo `host:` em forge-config.yaml); adapters dedicados pra Claude Code e opencode; fallback intent-file pra harnesses desconhecidos; adapter TTY pra humano em terminal real.
- **C.** Brownfield-safe init — migração de tudo que forge escreve pra sub-namespace `.claude/forge/`; `.claude/settings.json` append-only merge (preserva entries do user); git hooks via delegator chained (forge hook é wrapper que executa hook existente do user + hook forge em sequência).
- **D.** Install/upgrade CLI — `curl -fsSL https://raw.githubusercontent.com/thgMatajs/feature-forge/main/scripts/install.sh | bash` (clone + bootstrap + symlink + PATH detection via 3-caminhos) + comando `forge upgrade` (git pull + venv refresh + smoke + rollback gracioso em falha).

### Escopo OUT (deliberado, vai pra v1.4+)

- **Apply Mode autopilot** (Onda 1 canônica — LLM/sub-agent invocation real, pre-commit reviewer-agent, atomic commit auto, retro auto-trigger) → v1.4
- **Adapters codex/cursor/aider/continue.dev** → v1.4+ (fallback intent_file cobre por enquanto)
- **Tree-sitter / AST parsers** → Onda 2 (v1.5+)
- **Multi-dev opcional** → Onda 2
- **Marketplace pública / hosted service / IDE plugin nativo** → anti-roadmap permanente (§6 do roadmap-produto)

### Anti-goals explícitos

- v1.3 NÃO automatiza decisão de produto (princípio non-negociável, Decision 22).
- v1.3 NÃO substitui peer review humano (Diego, Camada C).
- v1.3 NÃO publica forge em registry runtime (anti-roadmap §6 — "Skill auto-installer cross-project").
- v1.3 NÃO modifica `CLAUDE.md` do projeto consumidor sob nenhuma circunstância — sub-namespace `.claude/forge/` isola.

---

## §2 — Arquitetura de alto nível

### Diagrama de camadas

```
┌─ Host layer (NOVO) ────────────────────────────────────────────┐
│  engine/host/                                                  │
│    detect.py        — auto-detect via env vars + config        │
│    adapter.py       — protocol abstrato (ABC HostAdapter)      │
│    registry.py      — mapa HostName → Adapter class            │
│    env.py           — env var helpers (CLAUDECODE, OPENCODE_*) │
│    adapters/                                                   │
│      claude_code.py — in-process via AskUserQuestion shape     │
│      opencode.py    — in-process via opencode tool API (W2.T0) │
│      tty.py         — stdin direto (humano em terminal real)   │
│      intent_file.py — pending.json/response.json (fallback)    │
└────────────────────────────────────────────────────────────────┘
            │
            ▼
┌─ Engine layer (REFATORADO) ───────────────────────────────────┐
│  engine/ui/question.py — ponto único de pergunta              │
│    ↳ resolve adapter via host.registry.get_adapter()          │
│    ↳ dispatcha pra adapter.ask(...)                           │
│    ↳ adapter retorna resposta DIRETA (sem pending/response    │
│      visíveis ao user em hosts agentic conhecidos)            │
└───────────────────────────────────────────────────────────────┘
            │
            ▼
┌─ Filesystem (NOVO LAYOUT no projeto consumidor) ──────────────┐
│  .claude/forge/                                                │
│    forge-config.yaml         ← renomeado de workflow-config    │
│    state/                    ← era .claude/state/              │
│      forge-pending.json      (só pra adapter intent_file)      │
│      forge-response.json     (idem)                            │
│      drift-warned.json                                         │
│      forge-intent-log.jsonl  (idempotência re-entry)           │
│    cards/local/              ← era .claude/cards/local/        │
│    hooks/                    ← era .claude/hooks/              │
│      pre-commit-feature-forge.sh                               │
│      ... (todos os hooks forge owned)                          │
│  .claude/settings.json       ← APPEND-ONLY entries forge       │
│  .claude/skills/             ← INTOCADO (user-managed)         │
│  .claude/agents/             ← INTOCADO (user-managed)         │
│  .claude/settings.local.json ← INTOCADO (user-managed)         │
└────────────────────────────────────────────────────────────────┘
            │
            ▼
┌─ Install layout (~/.local/share/feature-forge/) ──────────────┐
│  ~/.local/share/feature-forge/                                 │
│    bin/forge → engine/cli.py wrapper                           │
│    engine/ ...                                                 │
│    .venv/                                                      │
│    .git/                                                       │
│  ~/.local/bin/forge → ~/.local/share/feature-forge/bin/forge   │
│                                                                │
│  scripts/install.sh (hosted GitHub raw)                        │
│  engine/upgrade.py + forge upgrade handler                     │
└────────────────────────────────────────────────────────────────┘
```

### 4 mudanças load-bearing

1. **Novo módulo `engine/host/`** — abstrai como forge fala com o usuário; ponto único de extensão pra harnesses futuros.
2. **Sub-namespace `.claude/forge/`** — todo state/config do forge migra; isolamento de namespace contra colisão brownfield.
3. **`engine/ui/question.py` refatora pra delegar a adapter** — adapter pode ou não escrever pending.json (só `intent_file` fallback usa).
4. **Install layout em `~/.local/share/feature-forge/` (XDG default)** — sai do "user precisa clonar manualmente em `~/Documents/`".

### Decisões locked impactadas

- **Decisão 18** (skill location `~/Documents/feature-forge/`) → **Revisita**. Histórico preservado (Mandamento #1). Append entry "Revisita decisão 18: skill location → `~/.local/share/feature-forge/` (XDG default) — convenção universal pra ferramentas instaladas via script". Histórico antigo permanece marcado como "(superseded by row N — 2026-06-XX)".
- **Decisão 22** (no runtime deps em outras skills) — **PRESERVADA**. `forge upgrade` é `git pull` do próprio repo, não fetch de skill registry.
- **Decisão 23** (validator cascade fail-fast) — **PRESERVADA**.
- **Decisão 27** (pause vs abort 2-step) — **PRESERVADA** mas reforçada: pause em adapter `intent_file` emite pending.json; em adapters in-process (claude_code, opencode), emite via tool retornando sentinel `PausedForInputError`.

---

## §3 — Componentes detalhados por subsistema

### A. Bug-fix wave (~5 componentes)

| Fix | Arquivo | LOC |
|---|---|---|
| Exit codes unificados (todos pre-init → exit 1; intent-pause → exit 2; user cancel → exit 130) | `engine/cli.py` + cada handler que diverge | S |
| Suprimir `[WARN] failed to clear intent log` em `--help` e em comandos sem init | `engine/cli.py::main()` finally | S |
| ASCII fallback non-TTY em box-drawing — detect `sys.stdout.isatty()` e degradar pra `+---+` quando não-TTY | `engine/ui/renderer.py` | S |
| `forge qa` sem args com mensagem mentor-calmo + 3-caminhos (não ValueError stack trace) | `engine/qa/` entry | S |
| Piped stdin: humano em terminal usando `echo "1" \| forge cmd` documentado como DEPRECATED em v1.3 — adapter `tty.py` só lê stdin se isatty; agentic flows usam adapter dedicado | docs + `engine/host/adapters/tty.py` | S |

Total A: 5 fixes pequenos, ~300 LOC líquido.

### B. Host-aware execution (~6 componentes novos)

Layout do módulo:

```
engine/host/
  __init__.py
  detect.py              # detect_host(project_root) -> HostName
  adapter.py             # protocol abstrato: class HostAdapter (ABC)
  registry.py            # mapa HostName -> Adapter class; get_adapter()
  env.py                 # env var helpers (CLAUDECODE, OPENCODE_*, etc.)
  adapters/
    __init__.py
    claude_code.py       # in-process via AskUserQuestion shape
    opencode.py          # in-process via opencode tool API (W2.T0)
    tty.py               # stdin/stdout direto (humano)
    intent_file.py       # pending.json/response.json (fallback DRIFT-1 atual)
```

`HostAdapter` protocol (ABC):

```python
class HostAdapter(Protocol):
    name: HostName  # "claude-code" | "opencode" | "tty" | "intent-file"

    def ask(self, *, kind: AskKind, question: str, options: dict,
            default: str | None, allow_pause: bool) -> AskResult: ...
    def ask_text(self, *, prompt: str, default: str | None) -> str: ...
    def ask_multi(self, *, question: str, options: dict,
                  min: int = 0, max: int | None = None) -> list[str]: ...
    def emit_progress(self, *, step: str, total: int, current: int) -> None: ...
    def emit_warn(self, *, message: str) -> None: ...
```

`detect.py` lookup precedence: `forge-config.yaml host:` (override) → env var scan → fallback `intent-file` (assume agentic não-conhecido). Cache resultado no process via `functools.lru_cache`.

Total B: ~1000 LOC novo + refactor de `engine/ui/question.py` (~400 LOC do código atual de intent protocol vira só o adapter `intent_file.py`).

### C. Brownfield-safe init + sub-namespace (~4 componentes)

1. **`engine/init.py` Step refactor (hooks install)** — Step 12 ganha lógica de delegator chained: se já existe `.git/hooks/pre-commit`, forge cria `.claude/forge/hooks/pre-commit-feature-forge.sh` E modifica `.git/hooks/pre-commit` pra ser script wrapper que executa ambos em sequência (existing → forge). Detect via `file` command — se hook existente não é text/script, fallback warn + instala forge hook como sibling sem chain (user precisa chain manual).

2. **`engine/init.py` paths refactor** — todas as funções `_write_workflow_config`, `_install_hooks`, `_init_cards_local`, etc. passam a apontar pra `.claude/forge/<subpath>`. Helper `_forge_root(project_root)` centraliza.

3. **`engine/utils/paths.py`** — adicionar `forge_dir(project_root)`, `forge_config_path(project_root)`, `forge_state_dir(project_root)`. Refatorar todos os 50+ callsites em engine/ e validators/ pra usar esses helpers (substitui hardcoded `.claude/` paths).

4. **`settings.json` append-only merge** — função `_merge_settings_json(existing, forge_additions)` que faz append em arrays (`hooks.PreToolUse`, `hooks.PostToolUse`, `hooks.SessionStart`) sem sobrescrever entries pré-existentes. Parser tolerante a JSON com comentários (json5 lib ou regex-based) com fallback 3-caminhos em parse-fail.

Total C: ~600 LOC refactor + ~200 LOC novo.

### D. Install/upgrade CLI (~3 componentes)

#### D.1 — `scripts/install.sh` (hosted GitHub raw)

URL canônica: `https://raw.githubusercontent.com/thgMatajs/feature-forge/main/scripts/install.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

# 1. Pré-requisitos
#    - bash, git, python3 >= 3.10
#    - detect via command -v + python3 --version

# 2. FORGE_HOME via XDG_DATA_HOME ou ~/.local/share/feature-forge

# 3. Conflict detection do nome 'forge'
#    - command -v forge → se existe, 3-caminhos:
#      A) prosseguir e ofuscar (renomeia/move existente, instala forge)
#      B) install com nome alternativo `forge-cli`
#      C) abortar

# 4. Clone --depth=1 --branch v1.3.0 <repo> $FORGE_HOME
#    (ou main se primeiro release)

# 5. Setup venv:
#    python3 -m venv $FORGE_HOME/.venv
#    $FORGE_HOME/.venv/bin/pip install -r $FORGE_HOME/requirements.txt

# 6. Symlink: $FORGE_HOME/bin/forge → ~/.local/bin/forge
#    mkdir -p ~/.local/bin
#    ln -sf $FORGE_HOME/bin/forge ~/.local/bin/forge

# 7. PATH setup (CRÍTICO — install incompleto sem isso)
if ! echo ":$PATH:" | grep -q ":$HOME/.local/bin:"; then
  USER_SHELL=$(basename "${SHELL:-/bin/bash}")
  case "$USER_SHELL" in
    zsh)  RC_FILE="$HOME/.zshrc" ; PATH_LINE='export PATH="$HOME/.local/bin:$PATH"' ;;
    bash) RC_FILE="$HOME/.bashrc"; PATH_LINE='export PATH="$HOME/.local/bin:$PATH"' ;;
    fish) RC_FILE="$HOME/.config/fish/config.fish" ; PATH_LINE='fish_add_path $HOME/.local/bin' ;;
    *)    RC_FILE="" ; PATH_LINE='export PATH="$HOME/.local/bin:$PATH"' ;;
  esac
  
  # 3-caminhos mentor-calmo:
  # A) Adicionar automaticamente em $RC_FILE (marker guarded)
  # B) Mostrar a linha — user adiciona manual
  # C) Abortar install (exit 130)
fi

# 8. Smoke: forge --version
# 9. Mensagem: "instalado. próximo: cd <seu-projeto> && forge init"
```

Total: ~180 LOC bash (com PATH detection + 3-caminhos).

#### D.2 — `engine/upgrade.py` + handler `forge upgrade`

```python
def run_upgrade(*, force: bool = False) -> int:
    forge_home = detect_forge_home()
    
    # 1. cd $FORGE_HOME && git fetch origin
    # 2. Compara HEAD local vs origin/main (ou tag latest)
    # 3. Se igual → "já no latest", exit 0
    # 4. Se há commits locais não-pushed → 3-caminhos:
    #    A) stash + pull + pop / B) abort / C) force pull (perde locals)
    # 5. git pull
    # 6. .venv/bin/pip install -r requirements.txt --upgrade
    # 7. Smoke: forge --version retorna nova versão
    # 8. Se smoke falha → git reset --hard <prev-head> + venv rollback + warn
    # 9. Mensagem: "atualizado v1.3.X → v1.3.Y"
```

Total: ~150 LOC.

#### D.3 — SEM migrator v1.2 → v1.3 (clean break, pre-production status)

Decidido: não há contrato de upgrade pra projetos consumidores que rodaram v1.2 experimental. CHANGELOG declara explicitamente. `forge upgrade` em v1.2 install detecta layout antigo e emite mensagem mentor-calmo "v1.2 era experimental; pra v1.3 limpa o `.claude/` antigo e roda `forge init` de novo. Backup automático em `.claude.bak.pre-v1.3/`."

Total D: ~330 LOC (vs ~450 com migrator — cortou ~120 LOC).

### Resumo de esforço

| Subsistema | LOC novo | LOC refactor | Tests novos |
|---|---|---|---|
| A. Bug-fixes | 300 | 200 | 30 |
| B. Host-aware | 1000 | 400 | 80 |
| C. Brownfield | 200 | 600 | 50 |
| D. Install/upgrade | 330 | 50 | 40 |
| **Total v1.3** | **~1830** | **~1250** | **~200** |

---

## §4 — Data flow: como roda um `forge plan` em v1.3

### Sequência canônica (Claude Code rodando forge)

```
1. User invoca `forge plan IN-42100` (via /forge plan ou bash direto em CC terminal)
2. bin/forge dispatcher → engine/cli.py::main()
   ↳ ENV: CLAUDECODE=1 herdado de Claude Code
3. engine.host.detect.detect_host(project_root):
   - lê .claude/forge/forge-config.yaml → host: (não setado, default)
   - scan env vars: CLAUDECODE=1 → match
   - retorna HostName.CLAUDE_CODE
   - cache: process-local até exit
4. engine.cli resolve handler → engine/plan.py::run()
5. plan.py chama engine.ui.question.ask(...):
   - question.ask resolve adapter atual via host.registry
   - adapter = ClaudeCodeAdapter()
6. ClaudeCodeAdapter.ask(kind=ASK, question="Tipo da feature?", options={...}):
   - escreve intent estruturado em stdout (linha marker)
   - exit code 2 (pause)
   - CC harness consome stdout, dispatcha AskUserQuestion
   - user responde via UI nativa do CC
   - CC re-invoca forge com resposta cacheada em .claude/forge/state/
   - forge re-executa, adapter detecta resposta via intent-log
   - .ask() retorna AskResult(value="product")
7. plan.py recebe resposta, segue Wave A → ... → Wave E
8. status.json updated → forge exit 0
```

### Sequência canônica (TTY humano em terminal real)

```
1. User invoca ./bin/forge plan IN-42100 em terminal real
2. host.detect:
   - forge-config host: vazio
   - env: CLAUDECODE não setado, OPENCODE_* idem, etc.
   - sys.stdin.isatty() = True
   - retorna HostName.TTY
3. plan.py chama question.ask(...) → resolve TtyAdapter
4. TtyAdapter.ask(...) renderiza box-drawing Unicode (TTY suporta),
   lê stdin diretamente (interactive prompt), retorna AskResult
5. Sem pending.json, sem intent file, sem exit 2 — fluxo síncrono
```

### Sequência canônica (opencode)

```
1. opencode invoca forge plan IN-42100
   ↳ ENV: OPENCODE_VERSION=X.Y herdado
2. host.detect → HostName.OPENCODE
3. OpencodeAdapter.ask(...) usa tool API do opencode
   (shape final a investigar em W2.T0 — assumir similar a CC até confirmar)
```

### Sequência canônica (harness desconhecido — fallback)

```
1. Harness invoca forge plan IN-42100
   ↳ não há env var conhecida, sys.stdin não-isatty
2. host.detect → HostName.INTENT_FILE
3. IntentFileAdapter.ask(...) — protocolo DRIFT-1 atual:
   - escreve .claude/forge/state/forge-pending.json
   - exit code 2
   - harness implementa loop (lê pending, pergunta user do jeito dele,
     escreve response.json, re-invoca forge)
```

### Por que isso resolve os 3 bugs críticos do relatório

| Bug | Resolução em v1.3 |
|---|---|
| #1 — checkpoint × intent-id mismatch | ClaudeCodeAdapter usa AskUserQuestion shape direto; intent-id continua existindo internamente mas é gerenciado dentro do adapter via intent-log (já feito em PR #11 — Phase A W7.2 pitfall fix). Re-invocações idempotentes. |
| #2 — Stale response.json poisons subsequent commands | `engine/cli.py finally` limpa `state/` no exit normal; cada handler chama `clear_intent_state()` no startup como guard adicional. IntentFileAdapter já tem cache de consumed-intent-log. |
| #3 — Piped stdin ignored | TtyAdapter só lê stdin se isatty; non-TTY humano (CI, pipes) é caso de uso 2º class → documentado, com mensagem clara apontando wrapper agentic. |

---

## §5 — Setup limpo (sem migrator)

### Não há migration path v1.2 → v1.3. Clean break.

**Justificativa**: feature-forge é pré-produção. Nenhum projeto real adotou v1.2 ainda — MeoBonsai foi experimento controlado. Memory `project_pre_production_status` confirma: "migration/legacy concerns NÃO se aplicam a redesigns".

### Cenários de install

- **Fresh install**: `curl -fsSL <github-raw-URL>/scripts/install.sh | bash` → clone last release tag pra `~/.local/share/feature-forge/` + symlink em `~/.local/bin/forge` + PATH setup com 3-caminhos + smoke.
- **Re-init em projeto experimental v1.2**: `rm -rf .claude/forge .claude/workflow-config.yaml .claude/state .claude/cards/local .claude/hooks/forge-*.sh` + `forge init` do zero.
- **`forge upgrade` em v1.3+ futuro**: continua relevante pra v1.3.0 → v1.3.1, v1.3 → v1.4. Pra v1.2 → v1.3, não há contrato.

### Implicações no escopo

- ❌ CORTADO: migrator v1.2 → v1.3 em `engine/raw.py` (~200 LOC + tests). Não vamos escrever.
- ✅ MANTIDO: `scripts/install.sh` (~180 LOC bash)
- ✅ MANTIDO: `forge upgrade` (~150 LOC) — útil pra futuras versões a partir de v1.3
- ✅ DOC: CHANGELOG `## [v1.3.0]` declara explicitamente "**clean-slate release** — projetos experimentais em v1.2 devem ser re-inicializados; v1.3 é a primeira versão pré-piloto consolidada"
- ✅ DOC: 04-pending ganha entrada "v1.2 não tem migrator; deliberado — pre-production status"

---

## §6 — Estratégia de execução em waves (Approach A — vertical slice)

### W0.0 — Branch precondition (antes de qualquer commit em W0)

```bash
git checkout main
git fetch origin
git pull --ff-only origin main   # bloqueia se main local divergiu
git checkout -b feat/v1.3-pilot-ready
git push -u origin feat/v1.3-pilot-ready   # estabelece tracking
```

### Waves

| Wave | Conteúdo | LOC | Demo entregável |
|---|---|---|---|
| **W0** | Foundation + CC vertical slice: `engine/host/` + adapters `claude_code` + `intent_file` (rename DRIFT-1). `engine/utils/paths.py` ganha helpers de sub-namespace. Refactor ~50 callsites. Schema doc rename `workflow-config.md` → `forge-config.md`. | ~900 | `forge init` greenfield + `forge plan <slug>` Wave A funcionando no novo layout sob Claude Code |
| **W1** | Brownfield-safe init: detect `.claude/` denso, delegator chained pra git hooks, settings.json append-only merge. Regression: CLAUDE.md do consumidor inalterado (checksum sha256). | ~500 | Smoke MeoBonsai-class fixture: `forge init` em fixture com `.claude/skills` + `.claude/agents` + `.claude/hooks` plantados, zero user-file tocado |
| **W2** | W2.T0: investigação opencode tool API (1 dia dedicado). W2.T1+: opencode adapter + TTY adapter polish + ASCII fallback non-TTY em `engine/ui/renderer.py`. | ~600 | `forge plan` end-to-end em 3 hosts: Claude Code, opencode (ou fallback intent_file se R1 confirma incompatibilidade), TTY humano |
| **W3** | Bug-fix sprint: exit codes unificados nos 13 handlers, suprimir WARN em `--help`, `forge qa` CLI consistency, piped-stdin documentation. | ~400 | Smoke regression: 7 bugs do relatório fechados |
| **W4** | Install/upgrade CLI: `scripts/install.sh` (com PATH setup + 3-caminhos + alias conflict detection) + `engine/upgrade.py` + handler `forge upgrade`. | ~330 | One-liner install funciona em mac/linux limpos; `forge upgrade` git-pull cycle verde |
| **W5** | Smoke pilot fixture (MeoBonsai-class clonado + roda forge init + plan + verify end-to-end) + doc-sync (CHANGELOG v1.3.0 + 08-session-handoff + README rewrite + Revisita Decisão 18) + release prep (tag v1.3.0). | ~100 + docs | v1.3.0 tagged, ready pra piloto real |

**Total: 6 waves, ~2830 LOC + docs, ~200 tests novos. Estimativa rough: 3-5 sessões de trabalho dedicadas.**

### Branch + PR strategy

- **Uma branch**: `feat/v1.3-pilot-ready` criada a partir de `main` no início da W0 (após `git pull --ff-only`)
- **Commits atômicos por sub-task dentro de cada wave** — review/fix loops geram histórico granular
- **Doc-sync mini ao fim de cada wave** (CHANGELOG `[Unreleased]` ganha entrada, handoff atualizado)
- **Um PR no final**: mega-PR `feat/v1.3-pilot-ready → main` quando W5 fechar
- Memory `feedback_branch_per_implementation` + `feedback_single_branch_for_phased_work` honrados

### Trade-offs do Approach A

- Risco arquitetural front-loaded — se W0 expor que a abstração está errada, descobre na primeira wave (custo de pivot baixo)
- W2-W5 são extensões/polish do que W0+W1 estabeleceram (cada wave é shippable em isolamento)
- W2 (opencode) é o maior unknown — W2.T0 é research dedicada; fallback pra intent_file se shape opencode não casar

---

## §7 — Testing strategy + gates

### Pirâmide de testes por wave

| Layer | Cobre | Gate | Marker |
|---|---|---|---|
| **Unit** | Funções isoladas (host detect, adapter dispatch, path helpers, settings merge) | `pytest tests/unit/` verde + count baseline mantido | (sem marker) |
| **Integration** | Cross-module flows (init → forge-config emit → host detect → adapter resolve) | `pytest -m integration` verde | `@pytest.mark.integration` |
| **E2E (subprocess)** | Forge CLI invocado como subprocess; valida stdout/stderr/exit-code; cobre `intent_file` adapter e TTY adapter via pty fixture | `RUN_E2E=1 pytest -m e2e` verde | `@pytest.mark.e2e` |

### Tests novos esperados por wave

| Wave | Unit | Integration | E2E | Total |
|---|---|---|---|---|
| W0 | 40 | 8 | 3 | 51 |
| W1 | 15 | 12 | 4 | 31 |
| W2 | 30 | 6 | 5 | 41 |
| W3 | 20 | 3 | 4 | 27 |
| W4 | 20 | 4 | 6 | 30 |
| W5 | — | — | 5 (pilot smoke) | 5 |
| **Total** | **125** | **33** | **27** | **185** |

Baseline atual: ~1353 tests no main. Esperado pós-v1.3: ~1538 tests.

### Gates "verde antes de pronto" por wave

```bash
pytest -m "not integration and not e2e" -q   # rapid lane
pytest -m integration -q                      # integration lane
RUN_E2E=1 pytest -m e2e -q                    # e2e lane
forge verify --quiet                          # validators cascade
./bin/forge --version                         # smoke CLI
./bin/forge doctor                            # health check
```

Todas verde → commit. Qualquer vermelha → re-dispatch fix.

### Specific high-risk tests (obrigatórios)

1. **Settings.json merge preserva ordem + comments** — fixture com settings.json complexo (10 hook entries), merge forge adições, assert outros 9 entries permanecem byte-idêntico.
2. **Git delegator chained idempotente** — install forge, re-install (re-init), confirmar `.git/hooks/pre-commit` ainda chama user-hook + forge hook exatamente uma vez cada.
3. **Adapter resolution cache survives re-entry** — `detect_host()` duas vezes no mesmo process retorna mesmo resultado sem re-scan env.
4. **Intent-file adapter compat com DRIFT-1 schema atual** — pending.json shape bate com `docs/schemas/intent-protocol.md`.
5. **Greenfield init com `.claude/` ausente** vs **brownfield init com `.claude/` populated** — dois e2e separados, asserts diferentes.
6. **Migrator de v1.2 NÃO existe** — assert explícito que tentativa de migrar v1.2 retorna erro mentor-calmo apontando re-init. Negative test pra ancorar pre-production design.
7. **`forge upgrade` smoke fail → rollback automático** — smoke `forge --version` falha injetadamente; assert `git reset --hard <prev>` rodou + estado preservado.
8. **CLAUDE.md do consumidor inalterado** — fixture com CLAUDE.md populated, sha256 antes/depois do `forge init` idênticos.

### Code review gates por wave

- Post-impl: `gsd-code-reviewer` com prompt zero-tolerance (11 dimensões padrão: bugs, security, performance, concurrency, gaps, edge cases, code smells, doc accuracy, AC coverage, risks mitigation, residual findings)
- Findings high/critical → `gsd-code-fixer` loop até REVIEW.md sem high/critical
- Memory `feedback_zero_tolerance_code_review` honrada

### Pilot smoke (W5)

```bash
# 1. Limpa tudo
rm -rf /tmp/forge-pilot-v1.3
mkdir /tmp/forge-pilot-v1.3
cd /tmp/forge-pilot-v1.3

# 2. Install via curl one-liner
curl -fsSL <github-raw-URL>/scripts/install.sh | bash
forge --version  # → v1.3.0

# 3. Clone MeoBonsai fixture (brownfield denso)
git clone <fixture-repo> meobonsai-pilot
cd meobonsai-pilot

# 4. Confirma .claude/ pré-existente
ls .claude/skills/ .claude/agents/ .claude/hooks/ .claude/settings.json
SKILLS_BEFORE=$(find .claude/skills -type f | wc -l)

# 5. forge init em modo agentic
CLAUDECODE=1 forge init

# 6. Asserts pós-init
test -d .claude/forge
test -f .claude/forge/forge-config.yaml
SKILLS_AFTER=$(find .claude/skills -type f | wc -l)
test "$SKILLS_BEFORE" -eq "$SKILLS_AFTER"

# 7. forge plan + verify
forge plan IN-test-feature
forge verify

# 8. forge upgrade no-op
forge upgrade  # → "já no latest"
```

---

## §8 — Risks + Success criteria + Open questions

### Risks (e mitigações)

| # | Risco | Prob | Imp | Mitigação |
|---|---|:---:|:---:|---|
| R1 | **opencode tool API shape desconhecida** | M | A | W2.T0: 1 dia de research dedicado. Fallback: opencode usa adapter `intent_file` (perde "leverage all tools" pra opencode mas v1.3 ainda ship). |
| R2 | **Refactor de 50+ callsites de paths cruza load-bearing files** | A | A | Helper `forge_config_path()` centraliza; refactor mecânico via grep+replace dispatched como sub-task atômica. Review zero-tolerance pra cada batch. |
| R3 | **Settings.json append-only merge pode corromper user JSON em edge cases (comments, trailing commas)** | M | A | Parser tolerante (json5 lib ou regex-based) com fallback 3-caminhos em parse-fail. |
| R4 | **Git hook delegator chain quebra se user-hook é binário não-script** | B | M | Detect via `file` head -c 4; fallback "instala como sibling, user chain manual". |
| R5 | **install.sh requer python3 >= 3.10** — Ubuntu 20.04 fica de fora | M | M | Detect python version no install.sh, abortar com mensagem clara apontando pyenv. Documenta prereq no README. |
| R6 | **Curl one-liner pattern polêmico** (pipe to bash de URL externa) | M | B | Documentar paranoid path no README; install.sh emite "abort com Ctrl+C nos primeiros 3s" no start (sleep 3). |
| R7 | **Migrator NÃO existe (clean break)** — usuário experimental em v1.2 reclama | B | B | CHANGELOG declara "clean-slate"; `forge upgrade` em v1.2 install detecta layout antigo e emite mensagem mentor-calmo apontando re-init. |
| R8 | **Claude Code AskUserQuestion shape muda entre versões** | M | A | Adapter smoke fixture com mock do shape esperado. CI roda contra Claude Code versions canon documentadas em handoff. |
| R9 | **Brownfield fixture MeoBonsai-class fica desatualizada** | B | B | Fixture é sintética minimal (5 skills + 3 agents + 2 hooks como markers), não copy do MeoBonsai real. |

### Success criteria ("v1.3 done")

1. `curl -fsSL <github-raw-URL>/scripts/install.sh | bash` instala fresh em macOS limpo + Linux limpo → `forge --version` mostra `v1.3.0` em terminal novo, sem intervenção manual além das 3-caminhos do install.sh.
2. `forge init` em MeoBonsai-class fixture (`.claude/` com 5 skills + 3 agents + 2 hooks + settings.json populated) completa sem tocar nada além de `.claude/forge/` → diff `find .claude -type f -newer <init-start>` mostra apenas paths sob `.claude/forge/`.
3. `forge plan IN-test` end-to-end sob Claude Code (CLAUDECODE=1) — Wave A→E completa sem `forge-pending.json`/`forge-response.json` visíveis ao user; perguntas aparecem via AskUserQuestion nativa.
4. `forge plan IN-test` end-to-end sob opencode — Wave A→E completa via adapter opencode ou fallback intent_file (decisão dependente de R1 — fallback aceitável com nota explícita em CHANGELOG se opencode incompatível).
5. `forge plan IN-test` end-to-end em terminal humano (sem env vars agentic) — Wave A→E via TTY adapter, prompts interativos clássicos, sem pending.json.
6. Os 3 bugs críticos do relatório fechados com regression tests verdes (#1, #2, #3).
7. 4 bugs usabilidade do relatório fechados (U1 exit codes, U2 WARN ausente em --help, U3 ASCII fallback, U4 forge qa 3-caminhos sem traceback).
8. `forge upgrade` ciclo verde num install v1.3.0 → v1.3.1 simulado (tag falsa) — git pull + venv refresh + smoke + sem rollback.
9. Test suite cresce de ~1353 → ~1538 sem regressão (zero falhas novas, rapid + integration + e2e + validators todas verdes).
10. Doc-sync completo: CHANGELOG v1.3.0 + 08-session-handoff + README rewrite + docs/design/01-decisions (Revisita Decisão 18 — XDG install path) + 04-pending atualizado + docs/schemas/forge-config.md renomeado + 05-filesystem-layout refletindo sub-namespace.

### Open questions

| # | Status | Resolução |
|---|---|---|
| Q1 (opencode tool API) | DEFERRED | W2.T0 — sub-task de research dedicada de 1 dia |
| Q2 (install.sh URL) | RESOLVED | GitHub raw — `https://raw.githubusercontent.com/thgMatajs/feature-forge/main/scripts/install.sh` |
| Q3 (forge-config.yaml schema-version) | RESOLVED | Bump pra `"1.3"` (clean break alinhado) |
| Q4 (CLAUDE.md persona conflito) | RESOLVED | Conflito é fantasma — forge nunca toca CLAUDE.md do consumidor; smoke test em W1 confirma checksum inalterado |
| Q5 (alias conflict `forge`) | RESOLVED | install.sh detecta via `command -v forge` + 3-caminhos (prosseguir ofuscando / install como `forge-cli` / abortar) |

---

## §9 — Decisões impactadas

### Revisita Decisão 18 — skill location

**Antes** (locked, 2026-05-29): "Skill location = standalone repo em `~/Documents/feature-forge/`".

**Depois** (Revisita v1.3, 2026-06-16): "Skill location = standalone repo em `~/.local/share/feature-forge/` (XDG default; cai pra `$XDG_DATA_HOME/feature-forge/` se setado)".

**Justificativa**: padrão XDG é convenção universal pra ferramentas instaladas via script. `~/Documents/` é diretório de usuário pra documentos pessoais — colocar tool source ali confunde organização de arquivos e quebra expectativa de muitos shells/launchers que esperam `~/.local/share/` pra tool data.

**Histórico preservado**: linha antiga da Decisão 18 marcada como "(superseded by row N — 2026-06-16)" em `docs/design/01-decisions.md`; CHANGELOG `### Changed (load-bearing)` ganha entrada "Revisita decisão 18: skill location → `~/.local/share/feature-forge/` (XDG default) — convenção universal pra ferramentas instaladas via script".

### Decisões preservadas (não tocadas)

- **D22** (no runtime deps em outras skills) — `forge upgrade` é git pull do próprio repo, não fetch de skill registry.
- **D23** (validator cascade fail-fast) — comportamento preservado.
- **D27** (pause vs abort 2-step) — preservada e reforçada via adapter pattern.

---

## §10 — Cross-refs

- **Roadmap-produto Onda 1**: [`docs/product/03-roadmap.md`](../../product/03-roadmap.md) §2 — v1.3 é parte 1 da Onda 1 ("pilot-ready foundation"); v1.4 entrega Apply Mode autopilot (parte 2).
- **Decisões locked**: [`docs/design/01-decisions.md`](../../design/01-decisions.md) — D18 (Revisita), D22 (preservada), D23 (preservada), D27 (preservada).
- **Pending gaps**: [`docs/design/04-pending.md`](../../design/04-pending.md) — entradas novas pós-spec sobre clean-break + W2.T0 opencode research.
- **Filesystem layout atual**: [`docs/design/05-filesystem-layout.md`](../../design/05-filesystem-layout.md) — refletirá sub-namespace `.claude/forge/` quando W0 fechar.
- **DRIFT-1 schema atual (preservado em intent_file adapter)**: [`docs/schemas/intent-protocol.md`](../../schemas/intent-protocol.md).
- **Relatórios externos que motivaram o design**:
  - `/Users/thg.inchurch/Documents/feature-forge-experimentos/RELATORIO-1-COMPATIBILIDADE.md` (compatibilidade MeoBonsai)
  - `/Users/thg.inchurch/Documents/feature-forge-experimentos/DOC-2-BLUEPRINT-LLM-FIRST.md` (blueprint LLM-first)

### Anti-roadmap honrado

- Nenhum item de v1.3 entra em conflito com `docs/product/03-roadmap.md` §6 anti-roadmap. Especificamente:
  - `forge upgrade` é `git pull` (D22 preservada) — NÃO é "skill auto-installer cross-project".
  - Sem hosted service, sem marketplace pública, sem IDE plugin nativo, sem multi-target watchOS/Wear OS/tvOS.
