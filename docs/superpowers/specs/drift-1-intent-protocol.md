# SPEC — DRIFT-1: Intent Protocol (Engine intent-only + file-based resume)

**Status:** draft (brainstorming locked 2026-06-10 user↔orchestrator)
**Owner:** forge core
**Phase tag:** Phase A — DRIFT-1
**Created:** 2026-06-10

## Goal

Refatorar `engine/ui/question.py` (o chokepoint único de input) pra protocolo
file-based de intent estruturado, eliminando o drift entre a docstring
canônica ("local AskUserQuestion fallback") e a impl atual stdin-only —
sem mudar a API surface consumida pelos 10 módulos do engine.

## Why

`engine/ui/question.py:1` declara textualmente o design pretendido:

> "Interactive prompts — the local AskUserQuestion fallback."

A implementação atual (`sys.stdin.readline()` em :36) é stdin-only e não
sobrevive em contexto Claude Code (host não-TTY que faz `bash("forge ...")`
através de tool calls). O modo "Claude-Code-fronted" foi confirmado como
canonical pelo user em 2026-06-10. Detalhe + sequenciamento em
`docs/design/04-pending.md` §"v1.2-dev pilot 2026-06-10 — findings + phase
sequencing", entrada DRIFT-1.

O fallback CLI continua sendo modo legítimo (não é morte de stdin), só
deixa de ser o único caminho. Persona+microcopy do fallback é responsabilidade
de um `tty_bridge` Python; persona+microcopy do modo Claude-Code-fronted é
responsabilidade do orquestrador/host renderizando o intent emitido.

## Non-goals (explícito)

- **NÃO redesenha a API surface.** `ask()`, `ask_text()`, `confirm()`,
  `ask_three_paths()`, `ask_multi()` mantêm assinaturas atuais (`engine/ui/question.py`
  linhas 43, 84, 127, 158, 185). Os 108 callsites em 10 módulos do engine
  permanecem intocados — só a implementação interna do chokepoint muda.
  (Contagem canônica: `grep -rEn "question\.(ask|ask_text|ask_multi|confirm|ask_three_paths)" engine/`.
  Esta é a metodologia autoritativa; números anteriores — 106 no docstring
  do módulo, 125 em rascunhos antigos do SPEC/PLAN — foram reconciliados
  por LO-003 do W2 review.)
- **NÃO toca B1/B2/DET-5/DET-6** (Phase B — multi-axis backend redesign).
  DRIFT-1 é prerrequisito mas a refator do modelo de backend é fase
  posterior.
- **NÃO toca DET-3** (Phase 0b — scanner cego pra `libs.versions.toml`).
  Aquilo roda em branch paralela `feat/gradle-dep-signal`.
- **NÃO migra os 10 callsite modules.** O refactor é chokepoint-only. Se
  algum callsite usa stdin diretamente (não via question.py), abre-se
  follow-up gap separado.
- **NÃO adiciona MCP server.** Decision 22 (zero runtime deps em outras
  skills) permanece intacta. O protocolo é file-based + bash subprocess,
  zero dep nova.
- **NÃO mata stdin completo.** `tty_bridge` é fallback real pra terminal
  interativo + CI que rode `forge` direto. Detection automática (sem
  flag — Decision 10).
- **NÃO altera Decision 27** (pause vs abort). Ctrl+C continua mapeando
  pra exit 130; `para`/`pausa`/`quit`/`q`/`exit` tokens continuam
  reconhecidos.

## Design contract

### 1. Modelo big-picture

- **Engine intent-only.** `engine/ui/question.py` NUNCA lê stdin. Toda
  chamada a `ask()`/`ask_text()`/`confirm()`/`ask_three_paths()` que
  precise de input emite um **intent JSON** em `.claude/state/forge-pending.json`
  e raise sentinel exception capturada no top-level handler (`engine/cli.py`)
  que serializa o checkpoint atual da subcommand-em-execução e exita com
  código **2** (pause-for-input).
- **Caller loop.** O caller (orchestrator humano via Claude Code, ou
  `tty_bridge` em fallback TTY) lê `.claude/state/forge-pending.json`,
  resolve o input (via `AskUserQuestion` na host, ou stdin no tty_bridge),
  escreve `.claude/state/forge-response.json` e re-invoca o mesmo comando.
  Engine detecta response, consome, deleta ambos arquivos, retoma do
  checkpoint.
- **Loop conceptual:**

  ```
  loop:
    result = bash("forge X")
    if exit == 0: done                                  # comando completou
    if exit == 1: error                                 # falha fatal
    if exit == 2:                                       # paused for input
      intent = read(".claude/state/forge-pending.json")
      answer = AskUserQuestion(intent)                  # host renderiza
      write(".claude/state/forge-response.json", answer)
    if exit == 130: user cancelou
    continue
  ```

### 2. State file schemas

#### 2.1 `.claude/state/forge-pending.json`

Único arquivo global (sub-Q **Sa**: ÚNICO `.claude/state/forge-pending.json`,
nada per-command nem per-feature). Escrito atomicamente (mesma estratégia
de `engine.utils.yaml_io.write_yaml(... atomic=True)`).

Campos canônicos:

| Campo | Tipo | Sempre? | Significado |
|---|---|---|---|
| `schema-version` | int | sim | `1` inicial |
| `intent-id` | str (uuid4) | sim | Identifica este prompt; response deve referenciar |
| `command` | str | sim | Subcomando em execução (ex.: `init`, `reconfigure`) |
| `command-args` | list[str] | sim | argv passado pro comando (pra re-invocação fiel) |
| `kind` | str | sim | `ask` \| `ask_text` \| `ask_multi` \| `confirm` \| `ask_three_paths` |
| `question` | str | sim | Texto da pergunta (já formatado pelo engine) |
| `options` | dict[str,str] | quando `kind in {ask, ask_multi, confirm, ask_three_paths}` | `{key: human_label}` |
| `default` | str \| null | optional | Default key (apenas `ask`/`ask_text`) |
| `allow-pause` | bool | sim | Se `false`, tokens de pause são rejeitados |
| `validator-hint` | str \| null | optional | Apenas `ask_text`. Entra no hash do `intent-id` (MD-001 fix) pra dois prompts iguais com validators diferentes não colidirem |
| `min-selected` | int | optional | Apenas `ask_multi` |
| `paths-detail` | list[dict] | optional | Apenas `ask_three_paths`. Lista de 3 entradas `{key, label, motive}` — host usa pra renderizar o bloco 3-caminhos canônico (discipline §1). HI-001 fix do W2 review |
| `created-at` | str (ISO-8601 UTC) | sim | Timestamp da pausa |
| `pid` | int | sim | PID do processo Python que pausou (debug) |
| `checkpoint-path` | str \| null | optional | Path do checkpoint da subcommand-em-execução (ex.: `.claude/.init-checkpoint.yaml`) |

##### Exemplos por kind

**`ask` (single-select):**

```json
{
  "schema-version": 1,
  "intent-id": "7f0e2d11-3a8b-4c92-9e1a-5b6c7d8e9f10",
  "command": "init",
  "command-args": [],
  "kind": "ask",
  "question": "Qual preset usar pra este projeto?",
  "options": {"kmp-mobile": "Android + iOS + KMP shared", "android-only": "Android nativo"},
  "default": "kmp-mobile",
  "allow-pause": true,
  "created-at": "2026-06-10T18:42:11Z",
  "pid": 84210,
  "checkpoint-path": ".claude/.init-checkpoint.yaml"
}
```

**`ask_text` (free-text com validator):**

```json
{
  "schema-version": 1,
  "intent-id": "...",
  "command": "reconfigure",
  "command-args": [],
  "kind": "ask_text",
  "question": "Caminho do diretório dos cards locais (relativo ao project root):",
  "default": ".claude/cards/local",
  "allow-pause": true,
  "validator-hint": "Deve ser path relativo, sem `..`",
  "created-at": "...",
  "pid": 84210,
  "checkpoint-path": ".claude/.reconfigure-checkpoint.yaml"
}
```

**`confirm`:**

```json
{
  "schema-version": 1,
  "intent-id": "...",
  "command": "undo",
  "command-args": ["feature-x"],
  "kind": "confirm",
  "question": "Tem certeza que quer abortar a feature 'feature-x' inteira?",
  "options": {"s": "sim", "n": "não"},
  "default": "n",
  "allow-pause": false,
  "created-at": "...",
  "pid": 84210,
  "checkpoint-path": null
}
```

**`ask_three_paths`:**

```json
{
  "schema-version": 1,
  "intent-id": "...",
  "command": "verify",
  "command-args": [],
  "kind": "ask_three_paths",
  "question": "Qual caminho para resolver 'cc-gate-threshold-exceeded'?",
  "options": {
    "a": "Refatorar pra reduzir complexidade",
    "b": "Reverter o commit",
    "c": "Override-justify via commit body"
  },
  "paths-detail": [
    {"key": "a", "label": "Refatorar pra reduzir complexidade", "motive": "reduz risco no longo prazo, custo maior agora"},
    {"key": "b", "label": "Reverter o commit", "motive": "preserva baseline, exige re-planejamento"},
    {"key": "c", "label": "Override-justify via commit body", "motive": "destrava o gate, mas mantém débito visível"}
  ],
  "allow-pause": true,
  "created-at": "...",
  "pid": 84210,
  "checkpoint-path": ".claude/.verify-checkpoint.yaml"
}
```

#### 2.2 `.claude/state/forge-response.json`

Escrito pelo caller (host ou tty_bridge). Engine consome no início da
re-invocação.

| Campo | Tipo | Sempre? | Significado |
|---|---|---|---|
| `schema-version` | int | sim | `1` |
| `intent-id` | str | sim | Deve bater com o `intent-id` do pending; senão engine raise |
| `kind` | str | sim | Mesmo do pending (echo, double-check) |
| `value` | str \| list[str] \| bool | sim | Resposta. `list[str]` apenas pra `ask_multi`; `bool` apenas pra `confirm` |
| `paused` | bool | optional | `true` se user disse `para`/`pausa` (substitui `value`) |
| `cancelled` | bool | optional | `true` se user explicitamente cancelou (exit 130 next) |
| `answered-at` | str (ISO-8601 UTC) | sim | Timestamp |

Exemplo (resposta ao `ask` acima):

```json
{
  "schema-version": 1,
  "intent-id": "7f0e2d11-3a8b-4c92-9e1a-5b6c7d8e9f10",
  "kind": "ask",
  "value": "kmp-mobile",
  "answered-at": "2026-06-10T18:42:18Z"
}
```

Pausa explícita:

```json
{
  "schema-version": 1,
  "intent-id": "...",
  "kind": "ask",
  "paused": true,
  "answered-at": "..."
}
```

### 3. Lifecycle dos state files (sub-Q **Sb**)

AMBOS arquivos são deletados pela engine após consumir a response com
sucesso. Estado limpo entre pausas. Detalhe:

- Engine emite `forge-pending.json` → raise `PausedForInputError` → top-level
  handler exit 2.
- Caller lê pending, escreve response. (Pending segue intacto até engine
  consumir — caller NÃO deleta pending.)
- Engine re-invocada lê AMBOS arquivos. Valida `intent-id` match.
- Se válido: aplica `value`, deleta `forge-pending.json` E `forge-response.json`,
  segue execução.
- Se inválido (intent-id mismatch, schema mismatch, response sem pending
  correspondente): emite mensagem clara e exita 1. NÃO deleta — opera
  como pista forense.

### 4. Sentinel exceptions + handler

`engine/ui/question.py` expõe TRÊS sentinels distintos pro chokepoint:

```python
class PausedForInputError(Exception):
    """Engine emitiu pending e ainda não há response — exit 2."""
    intent: dict  # forge-pending.json payload

class UserPausedError(Exception):
    """Host response carregou paused: true com allow_pause=True — exit 2."""

class UserCancelledError(Exception):
    """Host response carregou cancelled: true — exit 130."""
```

Três sentinels separados (CR-001 + CR-003 do W2 review) ao invés de
reusar `PromptAbortedError` pra ambos os canais — assim `cli.main` mapeia
cada um pra exit code distinto sem ambiguidade. `PromptAbortedError` e
`NonInteractiveError` legados permanecem exportados pra backward-compat
com os 10 callsites; nenhum deles é levantado internamente pelo chokepoint
no protocolo novo.

Captura no top-level: **`engine/cli.py::main()`** (mesmo nível onde
`KeyboardInterrupt` é capturado pra Decision 27). Sequência:

1. Handler chama o subcommand normalmente.
2. Subcommand chama `question.ask(...)`.
3. Question lê `forge-response.json` (se existir e intent-id bate, consome).
   Resolução do response (na ordem checada por `_check_pause_response`):
   - `cancelled: true` → `UserCancelledError` → cli mapeia exit 130.
     Ordering MD-002: cancel vem antes de pause; se vier ambos, cancel
     vence (semântica mais forte).
   - `paused: true` + `allow_pause=True` → `UserPausedError` → cli
     mapeia exit 2.
   - `paused: true` + `allow_pause=False` → `ValueError` (pause forbidden).
     State NÃO é limpo — preserva forense conforme §3.
   - Caso válido sem flags → retorna value.
   Se NÃO existir response: escreve `forge-pending.json` + raise
   `PausedForInputError` → cli mapeia exit 2.
4. Subcommand DEVE persistir seu próprio checkpoint ANTES de invocar
   `question.*()` (já é prática hoje pra Ctrl+C — Decision 27). Isso
   significa que cada subcommand garante que o `forge-pending.json`
   campo `checkpoint-path` aponta pra estado já gravado em disco.
5. `engine/cli.py::main()` captura os sentinels e mapeia per tabela §8.
6. Caller re-invoca o mesmo comando com mesmos args.
7. Subcommand carrega seu checkpoint (já fazem isso hoje — ver
   `engine/init.py:_load_checkpoint`) e retoma. Quando chega no ponto
   que pausou, `question.ask(...)` agora encontra `forge-response.json`
   com intent-id matching, consome, retorna o valor, segue.

`cli.main` também publica `(command, command-args)` num `ContextVar`
ANTES de despachar o handler. `_command_context()` lê esse contextvar
de preferência ao `sys.argv` global — assim invocações programáticas
(`main(["plan"])` em testes/harnesses) produzem pending fiel ao argv
recebido, não ao argv do processo pai (HI-002 fix do W2 review).

### 5. Reentrancy

Cada um dos 10 callsite modules tem seu próprio checkpoint per-subcommand,
seguindo o template canônico de `_InitCheckpoint` (`engine/init.py:100-108`)
— outcome C do W2.T0 ("init-pattern", sem import de `engine.qa.checkpoint`,
respeitando Decision 22).

**Status final pós W2.T3b (10/10):**

| # | Subcomando | Checkpoint path | T3a action |
|---|---|---|---|
| 1 | `forge init` | `.claude/.init-checkpoint.yaml` | extend (já tinha; +intent_id) |
| 2 | `forge plan` | `.claude/.plan-checkpoint.yaml` | add-new |
| 3 | `forge implement` | `.claude/.implement-checkpoint.yaml` | add-new |
| 4 | `forge verify` | `.claude/.verify-checkpoint.yaml` | add-new |
| 5 | `forge reconfigure` | `.claude/.reconfigure-checkpoint.yaml` | add-new |
| 6 | `forge evolve` | `.claude/.evolve-checkpoint.yaml` | extend (payload dict já existia; +intent_id) |
| 7 | `forge undo` | `.claude/.undo-checkpoint.yaml` | add-new |
| 8 | `forge memory_cli` | `.claude/.memory_cli-checkpoint.yaml` | add-new |
| 9 | `forge graph_cli` | `.claude/.graph_cli-checkpoint.yaml` | add-new |
| 10 | `forge doctor` | `.claude/.doctor-checkpoint.yaml` | add-new |

Pattern conventions (uniformes em todos os módulos):

- **Dataclass shape:** mínimo `step` + `at` + `project_root` + `intent_id`,
  mais campos específicos do módulo (ex.: `feature_slug` em plan/implement,
  `menu_path` em reconfigure, `target_kind` em undo).
- **Save strategy:** checkpoint persistido ANTES de cada `question.ask*`
  call (ou ANTES de menu/submenu dispatch — em módulos com 16-40 callsites
  isso vira ~5-7 save sites estratégicos, não save per-prompt).
- **Clear strategy:** clear apenas em **clean completion**; pause /
  `PromptAbortedError` / `UserAbortError` DELIBERADAMENTE preserva o
  checkpoint pra forense de resume. Invalid-response paths também
  preservam (per §3 deste SPEC).

Detalhe operacional do audit T3a + decisões pré-impl: `.planning/drift-1/checkpoint-audit.json`.

> **Acceptance:** smoke test pra cada um dos 10 callsite modules confirmar
> que pause→resume retoma sem perda de input já coletado. Cobertura
> atual em `tests/unit/test_engine_*_resume.py` (10 arquivos, 30 testes:
> 3 por módulo — dataclass smoke + save/load/clear roundtrip + resume-
> from-checkpoint).

### 6. `engine/ui/tty_bridge.py` (sub-Q **Sc**)

Novo módulo Python, invocado via `python -m engine.ui.tty_bridge <command-module> <args...>`.

Responsabilidade: implementar o **caller loop** descrito em §1 para
contexto TTY puro (sem Claude Code host). Reusa:

- `engine.ui.renderer` pra render do prompt (box/cores/persona).
- `engine.persona.mentor_calmo` pra phrases (greeting, ack, pause_message,
  three_paths_block).
- Lê stdin via `sys.stdin.readline()` (resgata o código atual de
  `_read_line` em `question.py` movido pra cá).

Pseudo-código do loop:

```python
def main(command_module: str, argv: list[str]) -> int:
    while True:
        rc = subprocess.run(
            ["python", "-m", "engine.cli", command_module, *argv],
            env={**os.environ, "FORGE_INTERNAL_TTY_BRIDGE": "1"},
        ).returncode
        if rc != 2:
            return rc  # 0 success, 1 error, 130 SIGINT
        intent = read_pending(project_root)
        try:
            response = prompt_user_via_stdin(intent)  # reusa renderer
        except KeyboardInterrupt:
            return 130
        write_response(project_root, response)
```

- Env var `FORGE_INTERNAL_TTY_BRIDGE=1` marca origem; engine pode usar
  pra logging/debug, mas comportamento é idêntico.
- tty_bridge NUNCA executa lógica de subcomando — só faz subprocess +
  prompt loop. Persona ownership permanece centralizada.

### 7. `bin/forge` dispatcher (sub-Q **Sd** — bundled nesta phase)

Migration:

```bash
#!/usr/bin/env bash
set -euo pipefail
# (resolução de FORGE_HOME mantida idêntica — linhas 13-23 atuais)
PYTHON="${FORGE_PYTHON:-python3}"

# Detecção primary: env var CLAUDE_CODE_HOST setada pelo host.
# Detecção alternative: ausência de TTY no stdin/stdout.
if [[ -n "${CLAUDE_CODE_HOST:-}" ]] || [[ ! -t 0 ]] || [[ ! -t 1 ]]; then
  exec "$PYTHON" -m engine.cli "$@"          # modo intent-only
else
  exec "$PYTHON" -m engine.ui.tty_bridge engine.cli "$@"  # modo fallback TTY
fi
```

**Detection precedence (recomendada):**

1. **Primary:** `CLAUDE_CODE_HOST` env var setada (Claude Code documenta
   essa variável; se mudar, atualizar aqui). PLAN W4 confirma o nome
   exato lendo doc oficial do Claude Code antes de hardcodear; fallback
   genérico abaixo.
2. **Alternative:** `[[ ! -t 0 ]] || [[ ! -t 1 ]]` (stdin ou stdout
   não-TTY) — captura host genérico, CI, pipes, redirects.
3. **Override manual (escape hatch):** env var `FORGE_FORCE_INTENT_MODE=1`
   ou `FORGE_FORCE_TTY_MODE=1` pra usuário avançado debugar. Estes NÃO
   são flags de CLI (Decision 10 intacta) — são env vars.

### 8. Exit code contract

| Exit | Significado | Sentinel | Quem emite |
|---|---|---|---|
| **0** | Comando completou com sucesso | — | `engine/cli.py::main()` |
| **1** | Erro fatal (raise não capturado, response mismatch, schema invalid) | qualquer exception não-listada | `engine/cli.py::main()` ou subcommand handler |
| **2** | Engine emitiu pending e está aguardando primeira response | `PausedForInputError` | `engine/cli.py::main()` |
| **2** | Host enviou response com `paused: true` e o prompt permite pause | `UserPausedError` (CR-003 fix) | `engine/cli.py::main()` |
| **130** | User cancelou via Ctrl+C em TTY | `KeyboardInterrupt` | Já existia (Decision 27) |
| **130** | Host enviou response com `cancelled: true` | `UserCancelledError` (CR-001 fix) | `engine/cli.py::main()` |

Notas operacionais:

- Exit 2 é o canal canônico de "pausa, host respond e re-invoca". Duas
  rotas distintas chegam nele — engine-side (`PausedForInputError`) e
  user-action (`UserPausedError`) — mas o exit code é o mesmo porque o
  caller loop não precisa distinguir: ambos significam "preciso de input
  pra continuar".
- Exit 130 também tem duas rotas — TTY Ctrl+C e response `cancelled:true`.
  Idem motivação: caller loop trata "cancel" uniformemente.
- `PromptAbortedError` legado NÃO é capturado por `cli.main` — fica disponível
  pros 10 callsite modules como classe de exceção pra clauses `except`,
  mas o chokepoint não o levanta no protocolo intent-only.
- O exit 2 é NOVO no projeto. Não conflita com convenções POSIX que
  usariam 2 pra "misuse of shell builtins" — `forge` não é shell builtin.
  Documentado em `docs/schemas/intent-protocol.md` + `docs/design/06-command-surface.md`.

### 9. Concurrent invocation safety

Cenário: usuário invoca `forge X` duas vezes em sequência rápida (race).

- Antes de escrever `forge-pending.json`, engine checa se já existe pending
  COM intent-id diferente do que vai escrever. Se sim:
  - Se `created-at` > 10 minutos atrás → stale, deleta + segue.
  - Se recente → raise erro claro: "outra invocação ativa em PID X,
    aguarde ou delete `.claude/state/forge-pending.json`". Exit 1.
- Engine NUNCA escreve response (só lê). Não há race no caller side
  porque é responsabilidade dele orquestrar.
- Lock file simples (`.claude/state/.forge-pending.lock` via `fcntl.flock`)
  é considerado mas DEFERIDO pra v1.2.x — adicionar só se race aparecer.
  PLAN nota como follow-up.

## Acceptance criteria

| ID | Critério | Como testar |
|---|---|---|
| **AC-1** | `forge init` via bash em Claude Code (sem TTY, sem `CLAUDE_CODE_HOST` ou com — ambos) emite intent JSON ao primeiro prompt, exit 2 | Integration test em `tests/integration/test_intent_protocol_e2e.py` que invoca subprocess com stdin fechado, valida exit code 2 + presença de `.claude/state/forge-pending.json` com schema válido |
| **AC-2** | Re-invocação após response escrita retoma do checkpoint exato; arquivos `forge-pending.json` + `forge-response.json` são deletados | Mesmo integration test continua: escreve response, re-invoca, valida que retoma do step seguinte + ambos arquivos sumiram |
| **AC-3** | `forge init` em TTY puro (sem `CLAUDE_CODE_HOST`, com stdin TTY) entra em `tty_bridge` automaticamente, prompts stdin idênticos ao atual | E2E test marker `e2e` que invoca `bin/forge` via pty (`pexpect` ou `pty` stdlib) |
| **AC-4** | API `ask()`, `ask_text()`, `ask_multi()`, `confirm()`, `ask_three_paths()` mantêm assinaturas (signatures preservadas) | Unit tests pré-existentes em `tests/ui/test_question*.py` continuam verdes; novo test `test_api_signatures.py` assert no `inspect.signature(...)` de cada função |
| **AC-5** | Ctrl+C no tty mode → exit 130; token `para` em prompt allow-pause=true → response com `paused: true`, engine exit **2** limpo via `UserPausedError` (CR-003 fix do W2 review). Response com `cancelled: true` → exit **130** via `UserCancelledError` (CR-001 fix). Sem traceback em nenhum dos dois casos. | Unit + integration |
| **AC-6** | State files deletados após consumo no happy-path | Assertion explícita no integration test |
| **AC-7** | Race detectada: pending pré-existente com intent-id diferente E recente → engine exit 1 com mensagem clara, NÃO sobrescreve | Unit test em `tests/ui/test_question_intent.py` |
| **AC-8** | Os 10 callsite modules continuam funcionando (smoke per módulo) | Smoke tests existentes (init, plan, reconfigure, etc.) verdes em ambos modos |
| **AC-9** | pytest baseline (~1125 pós-Phase 0b) não regride; novos testes adicionados rodam verde | `pytest` collect + run; PLAN W6 confirma count expected |

## Open questions (pra investigar no PLAN)

1. **Nome exato da env var `CLAUDE_CODE_HOST`.** Confirmar via doc oficial
   (`https://code.claude.com/docs/...` ou via `Context7 MCP`) antes de
   hardcodear. Fallback `[[ ! -t 0 ]]` cobre caso esse nome esteja errado.
2. **`ask_multi` no protocolo.** O design contract inclui `ask_multi`
   (`engine/ui/question.py:84`) — não estava explícito no brainstorm.
   Adicionado aqui por completude; PLAN confirma se mantém ou se vira
   sintético sobre `ask`.
3. **Subcommand-level checkpoint audit.** Quais dos 10 callsite modules
   ainda NÃO têm checkpoint próprio? `engine/init.py` tem; resto precisa
   audit. Mapeado no PLAN W2-W3.
4. **Mensagem mentor-calmo pra erro de race / schema mismatch.**
   Persona precisa de phrase nova? PLAN W2 confirma.

## Anti-goals + Considerações futuras

- **MCP server pra prompts.** Considerado e rejeitado — viola Decision 22
  (no runtime deps em outras skills) e adiciona complexidade desnecessária.
  File-based é suficiente pro contrato.
- **Migração dos 10 callsite modules pra usar intent diretamente** (sem
  passar por `question.*`). Fora do escopo — refactor cosmético, sem
  benefício imediato. Follow-up gap em `04-pending.md` se algum dia
  ficar evidente.
- **Hooks que invocam `forge`** (`hooks/`, `.claude/hooks/`) podem
  precisar saber sobre exit code 2. Audit + ajuste fica em PLAN W4 doc-sync
  / W5 verification.
- **Detection mais sofisticada de host** (sentinel file, MCP handshake)
  fica como gap-fix futuro se `CLAUDE_CODE_HOST` env var virar instável.
- **Lock file via `fcntl.flock`** pra race entre invocações concurrent
  (deferido — adicionar se padrão aparecer em produção).
- **`forge raw` / `forge memory` / `forge graph` em modos read-only que
  não precisam de prompt** podem skipar todo o protocolo. Audit por
  comando no PLAN.

## Reuse-first evidence (a confirmar no PLAN)

- Checkpoint pattern: `engine/init.py:104-152` (`_InitCheckpoint`,
  `_save_checkpoint`, `_load_checkpoint`, `_clear_checkpoint`). PLAN
  generaliza pra helper compartilhado ou apenas referencia como
  precedente.
- Atomic write: `engine.utils.yaml_io.write_yaml(... atomic=True)` (já
  usado em init). Para JSON: ou novo helper `engine.utils.json_io.write_json`
  (PLAN decide) ou ad-hoc tempfile-rename.
- Renderer + persona: já modulares (`engine/ui/renderer.py`,
  `engine/persona/mentor_calmo.py`), reusados pelo `tty_bridge` sem refactor.
- Path utilities: `engine.utils.paths.claude_dir(project_root)` retorna
  `.claude/` — reusar pra resolver `.claude/state/`.

## Links

- `docs/design/04-pending.md` §"v1.2-dev pilot 2026-06-10" entrada DRIFT-1
- `docs/design/01-decisions.md` Decision 22 (no runtime deps), Decision 10
  (zero flags), Decision 19 (Python + Bash + YAML), Decision 27 (pause vs
  abort)
- `engine/ui/question.py:1` (docstring contradita pela impl atual)
- Brainstorm 2026-06-10 (user↔orchestrator) — sub-Qs Sa, Sb, Sc, Sd locked
