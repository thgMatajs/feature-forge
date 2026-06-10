# Schema — `.claude/state/forge-pending.json` + `forge-response.json`

The **intent protocol** is how the engine asks for input without ever
reading stdin directly. The chokepoint in `engine/ui/question.py` emits
an intent JSON, raises a sentinel exception, and the top-level handler
in `engine/cli.py` exits **2** (paused-for-input). The caller — either
the Claude Code host or `engine.ui.tty_bridge` in TTY fallback mode —
resolves the input, writes a response JSON, and re-invokes the command.

Why file-based: zero new runtime dependency (Decision 22), survives the
non-TTY context where `bash("forge ...")` runs through host tool calls,
and keeps the API surface of `question.py` (`ask`, `ask_text`,
`ask_multi`, `confirm`, `ask_three_paths`) bit-identical for the 108
callsites across 10 engine modules. (Canonical grep methodology:
`grep -rEn "question\.(ask|ask_text|ask_multi|confirm|ask_three_paths)" engine/`.
Earlier docs cited 106 / 125 with different criteria; 108 reconciliated
by W2 review LO-003.)

Authoritative design contract:
[`docs/superpowers/specs/drift-1-intent-protocol.md`](../superpowers/specs/drift-1-intent-protocol.md).

## File locations

Both files live under `.claude/state/` inside the project root:

```
<project-root>/
  .claude/
    state/
      forge-pending.json    # written by engine, read by caller
      forge-response.json   # written by caller, read by engine
```

A single global pair (sub-Q **Sa** locked): no per-command or
per-feature variants. The engine asserts via `intent-id` matching that
a response belongs to the prompt it was written for.

Atomicity: both writers use the same `tempfile + os.replace` strategy
that `engine.utils.yaml_io.write_yaml(atomic=True)` uses. No reader ever
observes a partial file.

---

## Pending file — `forge-pending.json`

Emitted by the engine when `question.ask*` is called and no matching
response is on disk. The engine then raises `PausedForInputError` and
`engine/cli.py::main()` returns exit code 2.

### Fields

| Campo | Tipo | Sempre? | Significado |
|---|---|---|---|
| `schema-version` | int | sim | `1` inicial — bump on breaking change |
| `intent-id` | str (uuid4) | sim | Identifica este prompt; a response deve referenciar |
| `command` | str | sim | Subcomando em execução (ex.: `init`, `reconfigure`) |
| `command-args` | list[str] | sim | argv passado pro comando (pra re-invocação fiel) |
| `kind` | str | sim | `ask` \| `ask_text` \| `ask_multi` \| `confirm` \| `ask_three_paths` |
| `question` | str | sim | Texto da pergunta (já formatado pelo engine) |
| `options` | dict[str,str] | quando `kind in {ask, ask_multi, confirm, ask_three_paths}` | `{key: human_label}` |
| `default` | str \| null | optional | Default key (apenas `ask`/`ask_text`) |
| `allow-pause` | bool | sim | Se `false`, tokens de pause são rejeitados |
| `validator-hint` | str \| null | optional | Apenas `ask_text`. Entra no hash do `intent-id` pra dois prompts iguais com validators diferentes não colidirem (MD-001 do W2 review) |
| `min-selected` | int | optional | Apenas `ask_multi` |
| `paths-detail` | list[dict] | optional | Apenas `ask_three_paths`. 3 entradas `{key, label, motive}` — host usa pra renderizar o bloco 3-caminhos canônico (discipline §1). HI-001 do W2 review |
| `created-at` | str (ISO-8601 UTC) | sim | Timestamp da pausa |
| `pid` | int | sim | PID do processo Python que pausou (debug) |
| `checkpoint-path` | str \| null | optional | Path do checkpoint da subcommand-em-execução |

### Examples per kind

**`ask` (single-select):**

```json
{
  "schema-version": 1,
  "intent-id": "7f0e2d11-3a8b-4c92-9e1a-5b6c7d8e9f10",
  "command": "init",
  "command-args": [],
  "kind": "ask",
  "question": "Qual preset usar pra este projeto?",
  "options": {
    "kmp-mobile": "Android + iOS + KMP shared",
    "android-only": "Android nativo"
  },
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
  "intent-id": "0d8e3a02-1f4b-4d12-8c5a-3b9c1d2e3f04",
  "command": "reconfigure",
  "command-args": [],
  "kind": "ask_text",
  "question": "Caminho do diretório dos cards locais (relativo ao project root):",
  "default": ".claude/cards/local",
  "allow-pause": true,
  "validator-hint": "Deve ser path relativo, sem `..`",
  "created-at": "2026-06-10T18:50:01Z",
  "pid": 84210,
  "checkpoint-path": ".claude/.reconfigure-checkpoint.yaml"
}
```

**`ask_multi` (multi-select):**

```json
{
  "schema-version": 1,
  "intent-id": "2b5a7c91-d4e3-4a02-9f12-6c0b8a9d1e2f",
  "command": "evolve",
  "command-args": [],
  "kind": "ask_multi",
  "question": "Quais propostas aceitar nesta rodada?",
  "options": {
    "p1": "Adicionar gate cyclomatic-complexity",
    "p2": "Promover validator `check_no_behavior_change` pra mandatório",
    "p3": "Refactor pra extrair helper de diff"
  },
  "min-selected": 1,
  "allow-pause": true,
  "created-at": "2026-06-10T19:01:42Z",
  "pid": 84210,
  "checkpoint-path": ".claude/.evolve-checkpoint.yaml"
}
```

**`confirm`:**

```json
{
  "schema-version": 1,
  "intent-id": "9a1b3c20-7e4d-4f01-8a92-2b3c4d5e6f70",
  "command": "undo",
  "command-args": ["feature-x"],
  "kind": "confirm",
  "question": "Tem certeza que quer abortar a feature 'feature-x' inteira?",
  "options": {"s": "sim", "n": "não"},
  "default": "n",
  "allow-pause": false,
  "created-at": "2026-06-10T19:15:00Z",
  "pid": 84210,
  "checkpoint-path": null
}
```

**`ask_three_paths`:**

```json
{
  "schema-version": 1,
  "intent-id": "5e7f9a02-3b1d-4c80-9a23-4d5e6f7a8b9c",
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
  "created-at": "2026-06-10T19:20:30Z",
  "pid": 84210,
  "checkpoint-path": ".claude/.verify-checkpoint.yaml"
}
```

O host renderiza o bloco 3-caminhos canônico (discipline §1) usando os
campos `label` + `motive` de `paths-detail`. Sem esse campo, o renderer
do host ficaria anêmico — só com `options` (label) e sem o "motivo
provável" exigido pelo template de gate-resolution.

---

## Response file — `forge-response.json`

Written by the caller (Claude Code host via `AskUserQuestion`, or
`engine.ui.tty_bridge` after stdin prompt). Consumed by the engine at
the start of the re-invocation.

### Fields

| Campo | Tipo | Sempre? | Significado |
|---|---|---|---|
| `schema-version` | int | sim | `1` |
| `intent-id` | str | sim | Deve bater com o `intent-id` do pending; senão engine raise |
| `kind` | str | sim | Mesmo do pending (echo, double-check) |
| `value` | str \| list[str] \| bool | sim quando não `paused`/`cancelled` | Resposta. `list[str]` apenas pra `ask_multi`; `bool` apenas pra `confirm` |
| `paused` | bool | optional | `true` se user disse `para`/`pausa` (substitui `value`) |
| `cancelled` | bool | optional | `true` se user explicitamente cancelou (exit 130 next) |
| `answered-at` | str (ISO-8601 UTC) | sim | Timestamp |

### Examples

**Resposta a `ask`:**

```json
{
  "schema-version": 1,
  "intent-id": "7f0e2d11-3a8b-4c92-9e1a-5b6c7d8e9f10",
  "kind": "ask",
  "value": "kmp-mobile",
  "answered-at": "2026-06-10T18:42:18Z"
}
```

**Resposta a `ask_multi`:**

```json
{
  "schema-version": 1,
  "intent-id": "2b5a7c91-d4e3-4a02-9f12-6c0b8a9d1e2f",
  "kind": "ask_multi",
  "value": ["p1", "p3"],
  "answered-at": "2026-06-10T19:02:10Z"
}
```

**Resposta a `confirm`:**

```json
{
  "schema-version": 1,
  "intent-id": "9a1b3c20-7e4d-4f01-8a92-2b3c4d5e6f70",
  "kind": "confirm",
  "value": false,
  "answered-at": "2026-06-10T19:15:09Z"
}
```

**Pausa explícita (user disse `para`):**

```json
{
  "schema-version": 1,
  "intent-id": "7f0e2d11-3a8b-4c92-9e1a-5b6c7d8e9f10",
  "kind": "ask",
  "paused": true,
  "answered-at": "2026-06-10T18:42:30Z"
}
```

**Cancelamento explícito:**

```json
{
  "schema-version": 1,
  "intent-id": "7f0e2d11-3a8b-4c92-9e1a-5b6c7d8e9f10",
  "kind": "ask",
  "cancelled": true,
  "answered-at": "2026-06-10T18:43:00Z"
}
```

---

## Lifecycle

1. Engine emite `forge-pending.json` → raise `PausedForInputError` →
   top-level handler exit 2.
2. Caller lê pending, escreve response. (Pending segue intacto até a
   engine consumir — o caller NÃO deleta pending.)
3. Engine re-invocada lê AMBOS arquivos. Valida `intent-id` match.
4. Se válido: aplica `value`, deleta `forge-pending.json` E
   `forge-response.json`, segue execução.
5. Se inválido (intent-id mismatch, schema mismatch, response sem
   pending correspondente): emite mensagem clara e exita 1. NÃO deleta
   — opera como pista forense.

### Race detection

Antes de escrever `forge-pending.json`, a engine checa se já existe
pending com `intent-id` diferente do que vai escrever:

- `created-at` > 10 minutos atrás → stale, deleta + segue.
- `created-at` recente (≤ 10 min) → raise erro claro: "outra invocação
  ativa em PID X, aguarde ou delete `.claude/state/forge-pending.json`".
  Exit 1.

Lock file via `fcntl.flock` foi considerado e deferido pra v1.2.x —
adicionar só se race aparecer em produção. Acompanha em
`docs/design/04-pending.md`.

---

## Exit code contract

A introdução do exit code **2** é o sinal canônico de "pausa aguardando
input". Documento completo em
[`docs/design/06-command-surface.md`](../design/06-command-surface.md).

| Exit | Significado | Sentinel | Quem emite |
|---|---|---|---|
| **0** | Comando completou com sucesso | — | `engine/cli.py::main()` |
| **1** | Erro fatal (raise não capturado, response mismatch, schema invalid) | qualquer exception não-listada | `engine/cli.py::main()` ou subcommand handler |
| **2** | Engine emitiu pending e está aguardando primeira response | `PausedForInputError` | `engine/cli.py::main()` |
| **2** | Host enviou response com `paused: true` e o prompt permite pause | `UserPausedError` (CR-003 do W2 review) | `engine/cli.py::main()` |
| **130** | User cancelou via Ctrl+C em TTY | `KeyboardInterrupt` | Decision 27 |
| **130** | Host enviou response com `cancelled: true` | `UserCancelledError` (CR-001 do W2 review) | `engine/cli.py::main()` |

POSIX nota: exit 2 às vezes é usado por shells pra "misuse of shell
builtins". `forge` não é shell builtin — o conflito é nominal.

---

## Links

- Spec canônico: [`docs/superpowers/specs/drift-1-intent-protocol.md`](../superpowers/specs/drift-1-intent-protocol.md)
- PLAN de implementação: [`docs/superpowers/plans/drift-1-intent-protocol.md`](../superpowers/plans/drift-1-intent-protocol.md)
- Pending entry: [`docs/design/04-pending.md`](../design/04-pending.md) — DRIFT-1
- Decisões load-bearing: Decision 22 (no runtime deps), Decision 10
  (zero flags), Decision 19 (Python + Bash + YAML), Decision 27 (pause
  vs abort)
