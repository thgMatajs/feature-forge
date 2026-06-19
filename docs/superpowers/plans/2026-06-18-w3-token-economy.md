# W3: Token Economy / Machine-Legibility Implementation Plan

<!-- audit-override: C2 — plano-driven sem spec dedicado; fonte de-facto é docs/reports/auditoria-consolidada-2026-06-17.md §3.2 A1/A2 + §4 + §6 (roadmap P0 item 5), com cobertura task-a-task confirmada na review r1 (A1 → T1-T5, A2 → T2+T6). Aceitável por "Quando NÃO há spec" do plan-auditor. -->

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Each task ends with an atomic commit.

**Spec:** nenhum (plano-driven; W3 não tem spec dedicado — escopo deriva de `docs/reports/auditoria-consolidada-2026-06-17.md` §3.2 A1/A2 + §4 + §6, roadmap P0 item 5).
**Phase tag:** W3 — Token Economy / Machine-Legibility
**Branch alvo:** `feat/w3-token-economy` (base = W2 tip `e1be2fe`)
**Created:** 2026-06-18
**Voz:** mentor calmo.

---

## Goal

Tornar a camada de output do `forge` **legível por máquina** sem quebrar a UX
conversacional human-first. Hoje o `forge` é **TOKEN-BLIND** (A1): `renderer.write`
nunca consulta o host; non-TTY só troca Unicode→ASCII, mantendo o mesmo número de
linhas de prosa cinematográfica (`status` = 33 linhas / 1812 chars; `doctor` = 75
linhas / 3908 chars em projeto vazio). Só `forge graph` tem `--json`; os outros
read-commands (`status`/`doctor`/`verify`/`memory`) forçam o consumidor LLM a parsear
prosa + glyphs — caro em tokens e frágil (a Auditoria B alucinou ~75% dos achados
porque teve que inferir estrutura de prosa).

Também falta **inventário e roteamento machine-readable** (A2): não há manifesto de
comandos/args (`_print_help` é prosa apontando pra path que não resolve em XDG —
NO-MANIFEST), e `forge status` não sugere o próximo passo do workflow
(NO-WORKFLOW-ROUTER).

Este plano entrega:

1. **A1 — output-mode global host-aware:** um modo de output (`TTY`/`PLAIN`/`JSON`)
   resolvido no startup do `cli.py`, propagado via **context var** (thread-safe pro
   dispatch de validators que subprocessam), e consultado pelo chokepoint único
   `renderer.write`.
2. **A1 — `--json` nos read-commands:** `status`, `doctor`, `verify`, `memory`.
   stdout = JSON puro (`json.dumps(indent=2, default=str)`), erros → stderr, exit 0/1.
3. **A1 — `FORGE_OUTPUT=json` env** como ativador global do JSON mode pros read-commands.
4. **A2 — `forge --help --json`:** manifesto de comandos/args derivado do `COMMANDS`
   dict + metadata.
5. **A2 — `forge status --json` com `suggested_next_command`:** roteador de workflow
   (mapa estado→próximo-verbo).
6. **Revisita Decisão 10 (ceremony append-only)** — meta-flags (`--json`, `--help --json`)
   + `FORGE_OUTPUT=json` passam a ser PERMITIDOS pros read-commands; intent protocol
   inalterado pros interativos.

Endereça os findings TOKEN-BLIND, NO-MANIFEST, NO-WORKFLOW-ROUTER (consolidados como
A1 + A2 na §3.2 da auditoria) e fecha os gaps correspondentes em `04-pending.md`.

## Architecture sketch

```
┌──────────────────────────────────────────────────────────────────────────┐
│ engine/cli.py::main()                                                      │
│   1. resolve output-mode (detect_output_mode(argv, command=cmd)):         │
│        JSON SÓ resolve se cmd ∈ _JSON_CAPABLE_COMMANDS                     │
│        (status/doctor/verify/memory/graph — read-commands).               │
│        meta-flag --json em argv  ─┐  (gated no allowlist)                  │
│        FORGE_OUTPUT=json env      ├─▶ OutputMode.JSON                      │
│        else / comando interativo: isatty? ──▶ TTY  : PLAIN                 │
│   2. set context var (engine/ui/output_mode.py::set_output_mode)          │
│   3. dispatch handler(rest)                                               │
└──────────────────────────────────────────────────────────────────────────┘
        │                                          │
        │ JSON mode + read-command                 │ TTY/PLAIN mode
        ▼                                          ▼
┌────────────────────────────────┐    ┌────────────────────────────────────┐
│ handler emite estrutura → stdout│    │ handler chama renderer.write(...)   │
│ via json.dumps (modelo graph)   │    │   chokepoint consulta output-mode:  │
│ erros → stderr · exit 0/1       │    │   JSON → suprime (no-op cinematográf)│
│ UI cinematográfica SUPRIMIDA    │    │   PLAIN → strip_ansi + to_ascii_box  │
│                                 │    │   TTY → as-is (Unicode + SGR)        │
└────────────────────────────────┘    └────────────────────────────────────┘
```

**Decouple central (Decisão de design 1, baked-in):** o output-mode é **global** via
context var lida UMA vez no startup. `renderer.write` consulta esse modo (não recebe
flag por callsite). Isso significa que, em JSON mode, qualquer `renderer.write` de UI
cinematográfica vira no-op no stdout — o handler do read-command, em JSON mode, NÃO
chama os `_render_*` de prosa; ele monta a estrutura e dá um único `print(json.dumps(...))`.

**Escopo do JSON mode (Decisão de design 2, baked-in — ENFORCE via allowlist):**
`FORGE_OUTPUT=json` e o meta-flag `--json` afetam **somente read-commands**
(`status`/`doctor`/`verify`/`memory`/`graph`). Comandos INTERATIVOS
(`plan`/`implement`/`init`/`reconfigure`/`evolve`/`qa`/`undo`/`raw`) MANTÊM o intent
protocol intacto — `FORGE_OUTPUT`/`--json` NÃO alteram comportamento deles, não tocam o
marker `<FORGE_INTENT/>` nem o exit-2.

O enforcement é **estrutural, não por convenção** (a defesa anterior — "o handler
interativo simplesmente não consulta JSON mode" — cobria o `print(json.dumps(...))` mas
NÃO o silenciamento global de `renderer.write`, que vira no-op pra TODO callsite quando o
modo resolve JSON). Por isso o gatilho de JSON mode é GATED num allowlist explícito de
read-commands. `detect_output_mode` só resolve `OutputMode.JSON` quando o subcomando
despachado pertence a `_JSON_CAPABLE_COMMANDS = {"status","doctor","verify","memory","graph"}`.
Pra qualquer comando fora desse conjunto (todos os interativos), `FORGE_OUTPUT=json` no env
ou um `--json` espúrio no argv são IGNORADOS pro rendering: o modo resolve `TTY`/`PLAIN`
normalmente, a UX cinematográfica não degrada, e o intent protocol roda como sempre.

Fato técnico que sustenta isso (verificado no código pelo auditor): o marker é emitido por
`engine/host/adapters/claude_code.py` via `sys.stdout.write(marker)` DIRETO (não via
`renderer.write`) — então o no-op do chokepoint em JSON mode jamais engole o marker. O
allowlist NÃO existe pra proteger o marker (que já sobrevive); existe pra impedir a
DEGRADAÇÃO silenciosa da UX cinematográfica dos interativos sob `FORGE_OUTPUT=json` no env.

**Modelo de saída (Decisão de design 3, baked-in):** idêntico ao `forge graph --json`
(`engine/graph_cli.py::_run_json_query`): stdout SÓ JSON, `print(json.dumps(result,
indent=2, default=str))`, erros → `sys.stderr.write`, exit 0 sucesso / 1 falha. Reusa o
padrão; não duplica infra.

Módulos NOVOS:

- `engine/ui/output_mode.py` — enum `OutputMode` (`TTY`/`PLAIN`/`JSON`) + context var +
  constante `_JSON_CAPABLE_COMMANDS` (allowlist de read-commands) +
  `detect_output_mode(argv, *, command=None, stream)` + `set_output_mode`/`get_output_mode`/`reset_output_mode`.

Módulos MODIFICADOS:

- `engine/ui/renderer.py` — `write()` (linha 198) consulta `output_mode.get_output_mode()`:
  JSON → suprime; PLAIN → strip+ascii; TTY → as-is. `_is_tty` (linha 63) permanece como
  fallback quando o modo não foi setado (invocação direta de lib/teste).
- `engine/cli.py` — `main()` (linha 254) resolve + seta output-mode no startup; `_print_help`
  (linha 235) ganha branch `--help --json` (manifesto); aceita meta-flag `--json` no dispatch.
- `engine/status.py` — `run()` (linha 47) extrai estrutura ANTES da prosa + `_status_payload`
  + `_suggested_next_command`; emite JSON quando em JSON mode.
- `engine/doctor.py` — `run()` (linha 213) serializa `list[_CategoryReport]` quando em JSON mode.
- `engine/verify.py` — `run()` (linha 174) / `run_scope` serializa `list[_ValidatorResult]`
  quando em JSON mode.
- `engine/memory_cli.py` — `run()` (linha 421) emite snapshot read-only (L2 entries + L1
  statuses + L3 index) quando em JSON mode, sem entrar no menu REPL.

Docs (doc-sync, Mandamento #6 — T7):

- `docs/design/01-decisions.md` — **Revisita Decisão 10** (append-only, row 32).
- `CHANGELOG.md` — `### Added` (--json/manifesto) + `### Changed (load-bearing)` (Revisita Decisão 10).
- `docs/design/06-command-surface.md` — contract do manifesto + carve-out de meta-flags.
- `docs/design/08-session-handoff.md` — estado + counts.
- `docs/design/04-pending.md` — fecha TOKEN-BLIND / NO-MANIFEST / NO-WORKFLOW-ROUTER / A1 / A2.
- `README.md` — se stats mudarem (counts de comando/flags).

## Tech Stack

Python core (stdlib only — `contextvars`, `enum`, `json`, `sys`, `os`); zero dep nova
(Decisão 22). Tests em `tests/unit/` + `tests/e2e/` (pytest, `.venv/bin/pytest` canônico).
Sem YAML/schema novo. Sem validator novo.

---

## Reuse-first evidence (Mandamento #3)

Antes de criar qualquer helper, consultei o engine existente (grep manual — graph snapshot
offline stale pós-W2):

```bash
# JSON-emit pattern canônico já existe?
grep -rn "json.dumps" engine/ --include="*.py" | grep -v test
# → engine/graph_cli.py:452 (print(json.dumps(result, indent=2, default=str)))
#   é o TEMPLATE canônico (Decisão de design 3). Reuso o padrão, não a função
#   (graph_cli._run_json_query é específico de queries do graph).

# Output-mode / context var já existe?
grep -rn "contextvar\|ContextVar\|output_mode\|OutputMode" engine/ --include="*.py" | grep -v test
# → engine/ui/question.py: _cli_command_context (ContextVar) — PADRÃO de context var
#   já estabelecido no projeto (cli.py:312 set + finally reset). Replico o pattern
#   pro output-mode (mesma disciplina set/reset).

# Chokepoint de write único?
grep -rn "def write\b" engine/ui/renderer.py
# → engine/ui/renderer.py:198 (chokepoint único — confirmado pela auditoria §4).

# Dataclasses serializáveis já existem?
grep -rn "@dataclass" engine/doctor.py engine/verify.py
# → doctor._Check (name/status/message/remediation) + doctor._CategoryReport (title/checks)
# → verify._ValidatorResult (name/status/duration_ms/message/paths/what_failed/where/why)
#   Ambas prontas pra dataclasses.asdict — não invento estrutura paralela.
```

Decisões de reuso:

- **Context var do output-mode** segue o pattern de `_cli_command_context`
  (`engine/ui/question.py`) — set no `cli.main`, reset no `finally`. Não invento mecanismo
  de propagação novo. Thread-safe por construção (`contextvars.ContextVar`), o que cobre o
  dispatch de validators que subprocessam (Decisão de design 1).
- **JSON-emit** replica o shape exato de `graph_cli._run_json_query` (Decisão de design 3):
  `print(json.dumps(result, indent=2, default=str))` + erro→stderr + exit 0/1. Mesma forma,
  consumidor (Claude Code, scripts) já conhece o contrato do graph.
- **Serialização das dataclasses** usa `dataclasses.asdict` direto sobre `_Check`/
  `_CategoryReport`/`_ValidatorResult` — zero remodelagem.
- **`_is_tty`** (renderer:63) permanece como fallback quando o output-mode não foi setado
  (chamadas de lib/teste que não passam por `cli.main`). Não removo nem dupliquei.

Sem near-duplicate detectada que justifique consolidação extra. `forge graph` Q11 não roda
offline neste snapshot; reuso confirmado por grep manual + leitura de `renderer.py`,
`cli.py`, `graph_cli.py`, `question.py`.

---

## Global Constraints

Valem para TODAS as tasks. Subagente executor relê antes de cada commit:

- **Mandamento 0:** o orquestrador-mantenedor NÃO edita; toda mudança é via subagente
  dispatchado. (Este plano É o artefato que o subagente executa.)
- **Voz mentor calmo** em qualquer artefato/mensagem gerada (CHANGELOG, manifesto, mensagens
  de erro). Sem voz corporativa, sem emoji decorativo, sem hedging.
- **`.venv/bin/pytest` é canônico** (tem json5 + deps; system pytest gera false-fail). Sempre
  rodar de DENTRO do worktree `/Users/thg.inchurch/Documents/feature-forge/.claude/worktrees/w3`.
  Confirme `engine.__file__` dentro do worktree antes de começar.
- **Baseline de tests (snapshot W2 tip):** rapid 1729 / integration 180 / e2e 30. Cada task
  ADICIONA tests; nenhuma reduz a baseline (test-count regression exige justificativa no commit).
  Re-confirme com `.venv/bin/pytest -m 'not integration and not e2e' -q | tail -1`.
- **Decisão 22:** zero runtime dep em outras skills / pacotes novos. Stdlib only.
- **Clean-break pré-produção OK:** feature-forge sem usuários reais ainda (piloto = teste).
  Sem concerns de migration/legacy; design limpo liberado.
- **Read-commands são read-only:** `status`/`doctor`/`verify`/`memory` em JSON mode NÃO podem
  introduzir mutação. (Exceção pré-existente: `doctor` carimba `doctor.last-run`; preservar
  esse comportamento idêntico em ambos os modos.)
- **Intent protocol é intocável:** nenhuma task pode alterar o marker `<FORGE_INTENT/>`, o
  exit-2 (`EXIT_PAUSED`), ou o comportamento dos comandos interativos. JSON mode é carve-out
  read-command-only.
- **Revisita Decisão 10 é ceremony append-only (T7):** NÃO deletar a linha 10 antiga; marcar
  como superseded; APPEND row 32 nova; CHANGELOG com texto LITERAL "Revisita Decisão 10: ...";
  commit message DEVE conter "Revisita Decisão 10" (pre-commit hard-block exige). Ver
  `.claude/rules/decisions.md §protocolo`.
- **Ordem de execução:** T1 → T2 → T3 → T4 → T5 → T6 → T7. T1 é pré-requisito de T2-T6
  (infra de output-mode). T7 (ceremony + doc-sync) fecha. T2-T6 são sequenciais por
  prudência (cada um toca um read-command distinto, mas todos dependem de T1 e o manifesto
  T6 lista as flags introduzidas em T2-T5).

---

## Task 1 — output-mode infra (context var) + renderer host-aware

**Tipo:** feature (cria módulo novo + modifica chokepoint).

**Files:**
- Create: `engine/ui/output_mode.py`
- Modify: `engine/ui/renderer.py:198` (`write`)
- Modify: `engine/cli.py:254` (`main` — resolve + set + reset output-mode, gated no allowlist)
- Create: `tests/unit/test_output_mode.py`
- Create: `tests/unit/test_renderer_output_mode.py`
- Create: `tests/unit/test_output_mode_interactive_safety.py` (guard H-001 — JSON mode não vaza pro caminho interativo)

**Interfaces:**
- Produces: `engine.ui.output_mode.OutputMode` (enum TTY/PLAIN/JSON), constante `_JSON_CAPABLE_COMMANDS` (allowlist), `detect_output_mode(argv, *, command=None, stream=None) -> OutputMode`, `set_output_mode(mode) -> token`, `get_output_mode() -> OutputMode`, `reset_output_mode(token) -> None`, `is_json_mode() -> bool`.
- Consumes (renderer): `output_mode.get_output_mode()` em `renderer.write`.
- Consumes (cli): `output_mode.detect_output_mode(argv, command=cmd)` + set/reset no `main`. O `command` é o subcomando (`argv[0]`); só read-commands no allowlist resolvem JSON.

**Steps:**

- [ ] **RED** — escreve `tests/unit/test_output_mode.py` cobrindo:
  ```python
  import os
  import sys
  import io
  import pytest
  from engine.ui import output_mode as om


  def test_default_mode_is_plain_when_not_tty_and_no_env(monkeypatch):
      monkeypatch.delenv("FORGE_OUTPUT", raising=False)
      stream = io.StringIO()  # not a tty
      assert om.detect_output_mode([], stream=stream) is om.OutputMode.PLAIN


  def test_tty_stream_yields_tty_mode(monkeypatch):
      monkeypatch.delenv("FORGE_OUTPUT", raising=False)

      class _TTY(io.StringIO):
          def isatty(self):
              return True

      assert om.detect_output_mode([], stream=_TTY()) is om.OutputMode.TTY


  def test_json_meta_flag_in_argv_yields_json(monkeypatch):
      monkeypatch.delenv("FORGE_OUTPUT", raising=False)

      class _TTY(io.StringIO):
          def isatty(self):
              return True

      # --json wins even over a tty — for a read-command in the allowlist.
      assert (
          om.detect_output_mode(["status", "--json"], command="status", stream=_TTY())
          is om.OutputMode.JSON
      )


  def test_forge_output_env_yields_json(monkeypatch):
      monkeypatch.setenv("FORGE_OUTPUT", "json")
      assert (
          om.detect_output_mode(["status"], command="status", stream=io.StringIO())
          is om.OutputMode.JSON
      )


  def test_forge_output_env_unknown_value_ignored(monkeypatch):
      monkeypatch.setenv("FORGE_OUTPUT", "yaml")  # unsupported → ignored
      assert (
          om.detect_output_mode(["status"], command="status", stream=io.StringIO())
          is om.OutputMode.PLAIN
      )


  def test_json_gated_to_read_commands_allowlist(monkeypatch):
      # H-001 — Decisão de design 2 enforced structurally: FORGE_OUTPUT=json on an
      # INTERACTIVE command resolves to PLAIN/TTY, NEVER JSON. The cinematic UX of
      # plan/implement/init/... must not degrade just because the env var is set.
      monkeypatch.setenv("FORGE_OUTPUT", "json")
      for interactive in ("plan", "implement", "init", "reconfigure", "evolve", "qa", "undo", "raw"):
          assert (
              om.detect_output_mode([interactive], command=interactive, stream=io.StringIO())
              is om.OutputMode.PLAIN
          ), f"{interactive} must ignore FORGE_OUTPUT=json (interactive carve-out)"


  def test_json_meta_flag_ignored_on_interactive_command(monkeypatch):
      # A spurious --json in argv for an interactive command is ignored too.
      monkeypatch.delenv("FORGE_OUTPUT", raising=False)
      assert (
          om.detect_output_mode(["plan", "--json"], command="plan", stream=io.StringIO())
          is om.OutputMode.PLAIN
      )


  def test_all_read_commands_are_json_capable(monkeypatch):
      monkeypatch.setenv("FORGE_OUTPUT", "json")
      for read_cmd in ("status", "doctor", "verify", "memory", "graph"):
          assert (
              om.detect_output_mode([read_cmd], command=read_cmd, stream=io.StringIO())
              is om.OutputMode.JSON
          ), f"{read_cmd} is a read-command and must honour JSON mode"


  def test_no_command_falls_back_to_stream_mode(monkeypatch):
      # When command is None (e.g. bare invocation / library caller), JSON is not
      # resolved — the allowlist cannot be satisfied, so we degrade to TTY/PLAIN.
      monkeypatch.setenv("FORGE_OUTPUT", "json")
      assert om.detect_output_mode([], command=None, stream=io.StringIO()) is om.OutputMode.PLAIN


  def test_set_get_reset_roundtrip():
      token = om.set_output_mode(om.OutputMode.JSON)
      try:
          assert om.get_output_mode() is om.OutputMode.JSON
      finally:
          om.reset_output_mode(token)
      # After reset, back to the unset default (PLAIN).
      assert om.get_output_mode() is om.OutputMode.PLAIN
  ```
  Run: `.venv/bin/pytest tests/unit/test_output_mode.py -q` → MUST fail (module missing).

- [ ] **GREEN** — cria `engine/ui/output_mode.py`:
  ```python
  """Global output-mode resolution (A1 TOKEN-BLIND).

  One mode per process, resolved once at ``cli.main`` startup and propagated
  via a ``contextvars.ContextVar`` so the single chokepoint ``renderer.write``
  can consult it without per-callsite flags. Thread-safe by construction —
  covers the validator-dispatch path that subprocesses (Decisão de design 1).

  Scope (Decisão de design 2 — ENFORCED via allowlist): ``OutputMode.JSON`` is
  only ever RESOLVED for read-commands (status/doctor/verify/memory/graph). For
  interactive commands (plan/implement/init/reconfigure/evolve/qa/undo/raw) the
  mode resolution refuses to return JSON even when ``FORGE_OUTPUT=json`` is set
  or a spurious ``--json`` is in argv — it falls through to TTY/PLAIN. This is
  structural: relying on interactive handlers to "just not consult JSON mode"
  would not stop the global ``renderer.write`` no-op from silently degrading
  their cinematic UX. The allowlist removes that failure mode at the source.

  Modes:
      TTY    — interactive terminal: Unicode box-drawing + SGR colours.
      PLAIN  — non-TTY (pipe/CI/redirect): strip SGR + degrade box→ASCII.
      JSON   — machine-readable: cinematic UI suppressed; handler emits JSON.

  Mirrors the context-var discipline of ``engine.ui.question._cli_command_context``
  (set at cli.main, reset in finally).
  """

  from __future__ import annotations

  import contextvars
  import os
  import sys
  from enum import Enum
  from typing import TextIO


  class OutputMode(Enum):
      TTY = "tty"
      PLAIN = "plain"
      JSON = "json"


  # H-001 / Decisão de design 2 — JSON mode is a READ-COMMAND-ONLY carve-out.
  # Only these commands may ever resolve to OutputMode.JSON. Interactive commands
  # (plan/implement/init/reconfigure/evolve/qa/undo/raw) intentionally fall through
  # to TTY/PLAIN even under FORGE_OUTPUT=json, so the intent protocol and their
  # cinematic UX are never degraded by the global renderer.write no-op. Keep this
  # set in sync with the read-commands that gained --json (T2-T5 + pre-existing graph).
  _JSON_CAPABLE_COMMANDS: frozenset[str] = frozenset(
      {"status", "doctor", "verify", "memory", "graph"}
  )


  # Default is PLAIN: a write that happens before cli.main sets the mode
  # (library/test callers) degrades safely rather than leaking SGR/Unicode.
  _output_mode: contextvars.ContextVar[OutputMode] = contextvars.ContextVar(
      "forge_output_mode", default=OutputMode.PLAIN
  )


  def _json_requested(argv: list[str]) -> bool:
      """True when the ``--json`` meta-flag is present anywhere in argv.

      Decisão 10 revisitada: ``--json`` is a permitted meta-flag for read-commands.
      We detect it positionally without argparse (the engine deliberately avoids
      argparse — Decisão 19/10). The allowlist in ``detect_output_mode`` is what
      restricts the effect to read-commands; this only reports presence.
      """
      return "--json" in argv


  def detect_output_mode(
      argv: list[str], *, command: str | None = None, stream: TextIO | None = None
  ) -> OutputMode:
      """Resolve the process output-mode.

      ``command`` is the dispatched subcommand (``argv[0]`` at ``cli.main``). JSON
      mode is GATED on it: only read-commands in ``_JSON_CAPABLE_COMMANDS`` may
      resolve to JSON. For any other command — or when ``command`` is ``None``
      (bare/library invocation) — ``--json`` and ``FORGE_OUTPUT=json`` are ignored
      for the purpose of JSON resolution and we fall through to TTY/PLAIN. This is
      the structural enforcement of Decisão de design 2 (H-001).

      Precedence (highest first), AFTER the allowlist gate:
          1. ``--json`` meta-flag in argv          → JSON  (read-command only)
          2. ``FORGE_OUTPUT=json`` env             → JSON  (read-command only)
          3. stream.isatty()                       → TTY
          4. otherwise                             → PLAIN

      Unknown ``FORGE_OUTPUT`` values are ignored (fall through to TTY/PLAIN)
      so a typo never silently corrupts output. ``--json`` wins over a tty so a
      human can force machine output for inspection — but only for read-commands.
      """
      stream = stream if stream is not None else sys.stdout
      json_capable = command in _JSON_CAPABLE_COMMANDS
      if json_capable:
          if _json_requested(argv):
              return OutputMode.JSON
          if os.environ.get("FORGE_OUTPUT", "").strip().lower() == "json":
              return OutputMode.JSON
      # Interactive commands (or no command): JSON is never resolved — the
      # cinematic UX and intent protocol stay intact regardless of env/argv.
      if bool(getattr(stream, "isatty", lambda: False)()):
          return OutputMode.TTY
      return OutputMode.PLAIN


  def set_output_mode(mode: OutputMode) -> contextvars.Token:
      """Set the process output-mode; returns a token for ``reset_output_mode``."""
      return _output_mode.set(mode)


  def get_output_mode() -> OutputMode:
      """Return the current output-mode (PLAIN when never set)."""
      return _output_mode.get()


  def reset_output_mode(token: contextvars.Token) -> None:
      """Undo a prior ``set_output_mode`` (call in a ``finally``)."""
      _output_mode.reset(token)


  def is_json_mode() -> bool:
      """Convenience predicate read by read-command handlers."""
      return _output_mode.get() is OutputMode.JSON


  __all__ = [
      "OutputMode",
      "detect_output_mode",
      "set_output_mode",
      "get_output_mode",
      "reset_output_mode",
      "is_json_mode",
  ]
  ```
  (``_JSON_CAPABLE_COMMANDS`` é constante interna — não vai no ``__all__``; os tests a
  referenciam pelo módulo (`om._JSON_CAPABLE_COMMANDS`) quando precisam, mas o contrato
  público é o comportamento de `detect_output_mode`.)
  Run: `.venv/bin/pytest tests/unit/test_output_mode.py -q` → MUST pass.

- [ ] **RED** — escreve `tests/unit/test_renderer_output_mode.py`:
  ```python
  import io
  from engine.ui import renderer
  from engine.ui import output_mode as om


  def test_json_mode_suppresses_cinematic_write():
      stream = io.StringIO()
      token = om.set_output_mode(om.OutputMode.JSON)
      try:
          renderer.write("┌── box ──┐", stream=stream)
      finally:
          om.reset_output_mode(token)
      # In JSON mode the cinematic UI is suppressed: nothing written to stream.
      assert stream.getvalue() == ""


  def test_plain_mode_strips_and_degrades():
      stream = io.StringIO()
      token = om.set_output_mode(om.OutputMode.PLAIN)
      try:
          renderer.write("\033[1m┌─┐\033[0m", stream=stream)
      finally:
          om.reset_output_mode(token)
      out = stream.getvalue()
      assert "\033" not in out  # SGR stripped
      assert "┌" not in out and "+" in out  # box degraded to ASCII


  def test_tty_mode_preserves_unicode_and_sgr():
      stream = io.StringIO()
      token = om.set_output_mode(om.OutputMode.TTY)
      try:
          renderer.write("┌─┐", stream=stream)
      finally:
          om.reset_output_mode(token)
      assert "┌" in stream.getvalue()
  ```
  Run: `.venv/bin/pytest tests/unit/test_renderer_output_mode.py -q` → MUST fail (write não consulta output-mode ainda).

- [ ] **GREEN** — modifica `engine/ui/renderer.py::write` (linha 198). Adiciona import no topo
  (`from engine.ui import output_mode as _output_mode` — import diferido dentro da função pra
  evitar ciclo, já que `output_mode` não importa `renderer`; mas como `output_mode` é stdlib-only
  e não importa renderer, import top-level é seguro — preferir top-level). Reescreve o corpo:
  ```python
  def write(text: str, *, stream: TextIO | None = None, newline: bool = True) -> None:
      """Single canonical write path (A1 TOKEN-BLIND — output-mode aware).

      Consults the process output-mode (engine.ui.output_mode):

      - JSON  → cinematic UI is suppressed (no-op). Read-command handlers emit
                their own ``json.dumps`` payload to stdout; letting prose through
                here would corrupt that payload.
      - PLAIN → strip SGR escapes AND degrade box-drawing Unicode to ASCII.
      - TTY   → write ``text`` as-is (Unicode box-drawing + SGR preserved).

      When the mode was never set (library/test callers that bypass cli.main),
      ``get_output_mode()`` returns PLAIN and we additionally honour ``_is_tty``
      for the stream so direct-stream callers still get colour on a real tty.
      """
      stream = stream or sys.stdout
      mode = output_mode.get_output_mode()
      if mode is output_mode.OutputMode.JSON:
          return  # cinematic UI suppressed — handler owns stdout in JSON mode.
      if mode is output_mode.OutputMode.TTY:
          payload = text
      elif mode is output_mode.OutputMode.PLAIN:
          payload = to_ascii_box(strip_ansi(text))
      else:  # pragma: no cover — enum is exhaustive
          payload = text if _is_tty(stream) else to_ascii_box(strip_ansi(text))
      stream.write(payload)
      if newline:
          stream.write("\n")
      stream.flush()
  ```
  Adiciona no topo de `renderer.py` (após os imports stdlib existentes): `from engine.ui import output_mode`.
  Run: `.venv/bin/pytest tests/unit/test_renderer_output_mode.py -q` → MUST pass.

- [ ] **GREEN** — modifica `engine/cli.py::main` (linha 254) pra resolver + setar + resetar o
  output-mode no startup, antes do dispatch. Adiciona import top-level: `from engine.ui import output_mode`.
  O `command` é o subcomando despachado — `cmd` só existe APÓS `cmd, rest = argv[0], argv[1:]`
  (linha 262, dentro do caminho `argv` não-vazio). Por isso a resolução ocorre LOGO APÓS `cmd, rest`
  serem extraídos, passando `command=cmd` pra ENFORÇAR o allowlist (H-001 — Decisão de design 2):
  ```python
      cmd, rest = argv[0], argv[1:]

      # A1 TOKEN-BLIND — resolve the process output-mode ONCE at startup and
      # publish it on the context var so renderer.write (the single chokepoint)
      # and read-command handlers consult a single source of truth. ``command=cmd``
      # GATES JSON resolution to the read-command allowlist (Decisão de design 2):
      # an interactive command never resolves JSON even under FORGE_OUTPUT=json,
      # so its cinematic UX + intent protocol are never silently degraded.
      _output_mode_token = output_mode.set_output_mode(
          output_mode.detect_output_mode(argv, command=cmd)
      )
  ```
  Envolve o corpo de `main` (a partir deste ponto) num `try/finally` que faz
  `output_mode.reset_output_mode(_output_mode_token)` no finally (espelha a disciplina set/reset de
  `_cli_command_context`). O `_cli_command_context.set((cmd, list(rest)))` já existente (linha 312)
  e seu reset no finally permanecem; aninhar o reset do output-mode no mesmo finally mais externo.
  **Nota:** o bloco `if cmd in ("-h", "--help", "help")` (linha 264) roda APÓS o set — pra `--help`
  o `command` é `"--help"`, fora do allowlist, então o modo resolve TTY/PLAIN; o branch `--help --json`
  da T6 emite o manifesto via `print(json.dumps(...))` direto (não depende de JSON mode resolvido).
  Run: `.venv/bin/pytest tests/unit/test_output_mode.py tests/unit/test_renderer_output_mode.py -q` → MUST pass.

- [ ] **RED (guard H-001 — intent protocol safety)** — escreve
  `tests/unit/test_output_mode_interactive_safety.py`. É o teste de NÃO-REGRESSÃO que ancora a
  afirmação "intent protocol intocado": prova que, com `FORGE_OUTPUT=json` no env, o caminho
  interativo (a) ainda emite o marker `<FORGE_INTENT.../>` em stdout, (b) levanta/propaga o exit-2
  (`PausedForInputError` / `EXIT_PAUSED`), e (c) não degrada a UX cinematográfica do caminho
  não-JSON-capable (o modo resolve PLAIN, não JSON):
  ```python
  import io

  import pytest

  from engine.host.adapter import AskKind, PausedForInputError
  from engine.host.adapters.claude_code import ClaudeCodeAdapter
  from engine.ui import output_mode as om


  def test_interactive_command_resolves_plain_under_forge_output_json(monkeypatch):
      # (c) — under FORGE_OUTPUT=json, an interactive command resolves PLAIN/TTY,
      # never JSON: renderer.write is NOT globally suppressed for it, so its
      # cinematic UX never degrades. This is the structural allowlist guard.
      monkeypatch.setenv("FORGE_OUTPUT", "json")
      assert (
          om.detect_output_mode(["plan", "auth"], command="plan", stream=io.StringIO())
          is om.OutputMode.PLAIN
      )


  def test_marker_emitted_under_forge_output_json(tmp_path, monkeypatch, capsys):
      # (a) — the intent marker is written via sys.stdout.write DIRECTLY by the
      # claude_code adapter (engine/host/adapters/claude_code.py::_emit_marker),
      # so it survives regardless of output-mode. Force JSON mode on the context
      # var to prove the marker is NOT swallowed by the renderer.write no-op.
      monkeypatch.setenv("FORGE_OUTPUT", "json")
      token = om.set_output_mode(om.OutputMode.JSON)
      try:
          adapter = ClaudeCodeAdapter(project_root=tmp_path)
          # First entry (no response file) → emit marker, then raise PausedForInputError.
          with pytest.raises(PausedForInputError):
              adapter.ask(
                  kind=AskKind.ASK,
                  question="Continuar?",
                  options={"sim": "Sim", "nao": "Não"},
                  default=None,
                  allow_pause=True,
              )
      finally:
          om.reset_output_mode(token)
      out = capsys.readouterr().out
      assert "<FORGE_INTENT" in out  # marker survived JSON mode (direct sys.stdout.write)


  def test_exit_2_preserved_under_forge_output_json(tmp_path, monkeypatch):
      # (b) — the paused-for-input contract (exit-2 / PausedForInputError) is
      # unchanged under FORGE_OUTPUT=json. The first-entry ask path must still
      # raise PausedForInputError (the engine bubbles it up as exit code 2).
      monkeypatch.setenv("FORGE_OUTPUT", "json")
      token = om.set_output_mode(om.OutputMode.JSON)
      try:
          adapter = ClaudeCodeAdapter(project_root=tmp_path)
          with pytest.raises(PausedForInputError):
              adapter.ask(
                  kind=AskKind.ASK,
                  question="Continuar?",
                  options={"sim": "Sim", "nao": "Não"},
                  default=None,
                  allow_pause=True,
              )
      finally:
          om.reset_output_mode(token)
  ```
  **Nota de implementação pro executor:** as assinaturas acima batem com o contrato real lido em
  `engine/host/adapters/claude_code.py` (construtor `ClaudeCodeAdapter(project_root=...)`; `ask`
  kw-only com `kind`/`question`/`options` (dict)/`default`/`allow_pause`; marker via `_emit_marker`
  → `sys.stdout.write`; `PausedForInputError` importado de `engine.host.adapter`). Se o adapter
  evoluir até o GREEN, reconfirme a assinatura antes de implementar — o invariante testado NÃO muda:
  marker via `sys.stdout.write` + exit-2 sobrevivem ao JSON mode, e o allowlist resolve PLAIN pros
  interativos. Test (c) FALHA enquanto o allowlist não estiver em vigor (hoje `detect_output_mode`
  resolveria JSON pra `plan`); (a)/(b) provam que marker + exit-2 são imunes ao modo.
  Run: `.venv/bin/pytest tests/unit/test_output_mode_interactive_safety.py -q` → MUST fail antes do
  GREEN do allowlist (test (c)); após o GREEN, os 3 passam.

- [ ] **REGRESSION** — `.venv/bin/pytest -m 'not integration and not e2e' -q | tail -1` → ≥ 1729
  rapid + 0 falhas (a mudança no chokepoint não pode regredir os renderers existentes — modo PLAIN
  preserva o comportamento non-TTY anterior; modo default PLAIN cobre callers de lib/teste).

- [ ] **COMMIT:** `feat(w3): output-mode infra (context var, allowlist) + renderer host-aware + guard H-001 (A1 T1)`

---

## Task 2 — `forge status --json` + `suggested_next_command` (A1 + A2 NO-WORKFLOW-ROUTER)

**Tipo:** feature.

**Files:**
- Modify: `engine/status.py:47` (`run`) — extrai estrutura + emite JSON em JSON mode.
- Create: `tests/unit/test_status_json.py`

**Interfaces:**
- Consumes: `engine.ui.output_mode.is_json_mode`, `engine.memory.l1.read_l1_status`, `list_active_features`.
- Produces: payload JSON com chaves `project`, `active_features`, `memory`, `pending_evolutions`, `doctor`, `suggested_next_command`.

**Mapa estado→próximo-verbo (NO-WORKFLOW-ROUTER).** Estados reais em `status.py:89`
(`_IN_FLIGHT_STATES = {planning, planned, implementing, verifying}`) + `blocked-on-external`
+ `deferred` + ausência de status.json. Mapa canônico:

| Estado da feature mais recente | `suggested_next_command` |
|---|---|
| `planning` ou `planned` | `implement` |
| `implementing` | `verify` |
| `verifying` | `verify` (re-roda até verde; pós-verde → retrospectiva auto) |
| `blocked-on-external` | `reconfigure` (resolver dep externa) |
| `deferred` | `status` (retomar via resume) |
| nenhuma feature ativa | `plan` |
| status.json ausente / desconhecido | `doctor` (diagnosticar) |

**Steps:**

- [ ] **RED** — `tests/unit/test_status_json.py` cobrindo (usa `tmp_project` fixture + monkeypatch do output-mode):
  ```python
  import json
  import pytest
  from engine.ui import output_mode as om
  from engine import status


  def _run_json(capsys, project_root, monkeypatch):
      monkeypatch.chdir(project_root)
      token = om.set_output_mode(om.OutputMode.JSON)
      try:
          code = status.run([])
      finally:
          om.reset_output_mode(token)
      out = capsys.readouterr().out
      return code, json.loads(out)


  def test_status_json_emits_valid_json_with_required_keys(tmp_project, capsys, monkeypatch):
      code, payload = _run_json(capsys, tmp_project, monkeypatch)
      assert code == 0
      for key in (
          "project",
          "active_features",
          "memory",
          "pending_evolutions",
          "doctor",
          "suggested_next_command",
      ):
          assert key in payload


  def test_status_json_suggests_plan_when_no_active_features(tmp_project, capsys, monkeypatch):
      code, payload = _run_json(capsys, tmp_project, monkeypatch)
      assert payload["suggested_next_command"] == "plan"


  def test_status_json_stdout_is_pure_json(tmp_project, capsys, monkeypatch):
      _, payload = _run_json(capsys, tmp_project, monkeypatch)
      # json.loads succeeded above; assert no cinematic prose leaked.
      assert isinstance(payload, dict)
  ```
  (Se `tmp_project` não criar status.json, o caso "no active features" é o default — sugere `plan`.)
  Run: `.venv/bin/pytest tests/unit/test_status_json.py -q` → MUST fail.

- [ ] **GREEN** — modifica `engine/status.py`. Adiciona import `from engine.ui import output_mode`
  + `import json`. Refatora `run` pra extrair estrutura ANTES da prosa:
  ```python
  def run(argv: list[str]) -> int:  # noqa: ARG001 — no args by design
      try:
          project_root = find_project_root()
      except ProjectRootNotFoundError as exc:
          if output_mode.is_json_mode():
              sys.stderr.write(f"forge status: {exc}\n")
              return 1
          renderer.write(renderer.colored(str(exc), "red"))
          renderer.write("Rode `forge init` antes.")
          return 1

      config = _safe_read_yaml(active_config_path(project_root)) or {}

      if output_mode.is_json_mode():
          payload = _status_payload(project_root, config)
          print(json.dumps(payload, indent=2, default=str))
          return 0

      renderer.write("")
      renderer.write(renderer.bold("forge status"))
      renderer.write(renderer.dim("Read-only · board do projeto"))
      _render_project(project_root, config)
      _render_active_features(project_root)
      _render_memory(project_root, config)
      _render_pending_evolutions(project_root)
      _render_doctor_freshness(config)
      _render_recent_activity(project_root)
      return 0
  ```
  Adiciona `import sys` se ausente. Cria `_status_payload` + `_suggested_next_command`:
  ```python
  def _status_payload(project_root: Path, config: dict) -> dict:
      """Machine-readable snapshot of the project board (A1 + A2)."""
      identity = (config.get("identity") or {}) if isinstance(config, dict) else {}
      cards_active = (config.get("cards") or {}).get("active") or []
      features: list[dict] = []
      for slug in list_active_features(project_root):
          st = read_l1_status(slug, project_root)
          features.append(
              {
                  "slug": slug,
                  "status": (st.status if st is not None else None),
                  "last_action_kind": (st.last_action_kind if st is not None else None),
                  "last_action_at": (st.last_action_at if st is not None else None),
              }
          )
      doctor_block = (config.get("doctor") or {}) if isinstance(config, dict) else {}
      return {
          "project": {
              "name": identity.get("project-name", project_root.name),
              "slug": identity.get("project-slug", project_root.name),
              "preset": identity.get("preset"),
              "cards_active": len(cards_active),
              "forge_version": identity.get("forge-version", FORGE_VERSION),
          },
          "active_features": features,
          "memory": {
              "l1_active": len(list_active_features(project_root)),
              "l1_archived": len(list_archived_features(project_root)),
          },
          "pending_evolutions": _pending_evolutions_count(project_root),
          "doctor": {
              "last_run": doctor_block.get("last-run"),
              "last_status": doctor_block.get("last-status"),
          },
          "suggested_next_command": _suggested_next_command(features),
      }


  def _pending_evolutions_count(project_root: Path) -> int:
      path = claude_dir(project_root) / "proposed-evolutions.yaml"
      if not path.exists():
          return 0
      try:
          data = read_yaml(path)
      except YamlIOError:
          return 0
      proposals = (data or {}).get("proposals") or [] if isinstance(data, dict) else []
      return len(proposals)


  def _suggested_next_command(features: list[dict]) -> str:
      """Workflow router (A2 NO-WORKFLOW-ROUTER).

      Maps the most-recently-active feature state to the next verb. Falls back
      to ``plan`` when no feature is active and ``doctor`` for unknown state.
      """
      if not features:
          return "plan"
      # Pick the most recently active feature by last_action_at (None sorts last).
      recent = max(
          features, key=lambda f: (f.get("last_action_at") or "")
      )
      state = recent.get("status")
      mapping = {
          "planning": "implement",
          "planned": "implement",
          "implementing": "verify",
          "verifying": "verify",
          "blocked-on-external": "reconfigure",
          "deferred": "status",
      }
      return mapping.get(state, "doctor")
  ```
  Garante que `claude_dir`, `read_yaml`, `YamlIOError`, `list_archived_features` já estão importados
  (estão — usados pelos `_render_*`).
  Run: `.venv/bin/pytest tests/unit/test_status_json.py -q` → MUST pass.

- [ ] **REGRESSION** — `.venv/bin/pytest tests/unit -k status -q` + `.venv/bin/pytest -m 'not integration and not e2e' -q | tail -1` → 0 falhas, ≥ baseline.

- [ ] **COMMIT:** `feat(w3): forge status --json + suggested_next_command (A1+A2 T2)`

---

## Task 3 — `forge doctor --json`

**Tipo:** feature.

**Files:**
- Modify: `engine/doctor.py:213` (`run`) — serializa `list[_CategoryReport]` em JSON mode.
- Create: `tests/unit/test_doctor_json.py`

**Interfaces:**
- Consumes: `engine.ui.output_mode.is_json_mode`, `dataclasses.asdict`, `_Check`/`_CategoryReport`, `_render_verdict`.
- Produces: payload JSON `{scope, overall_status, exit_code, categories: [{title, worst, checks: [{name,status,message,remediation}]}]}`.

**Decisão de escopo do ask:** `doctor` tem um único prompt interativo (`scope` full/quick). Em
JSON mode (non-interactive por natureza), o ask de scope NÃO pode pausar — assume `full`
(diagnóstico completo é o esperado por um consumidor machine). Documentar isso inline. O carimbo
`doctor.last-run` (mutação read-only existente) permanece idêntico em ambos os modos.

**Steps:**

- [ ] **RED** — `tests/unit/test_doctor_json.py`:
  ```python
  import json
  from engine.ui import output_mode as om
  from engine import doctor


  def _run_json(capsys, project_root, monkeypatch):
      monkeypatch.chdir(project_root)
      token = om.set_output_mode(om.OutputMode.JSON)
      try:
          code = doctor.run([])
      finally:
          om.reset_output_mode(token)
      out = capsys.readouterr().out
      return code, json.loads(out)


  def test_doctor_json_emits_categories(tmp_project, capsys, monkeypatch):
      code, payload = _run_json(capsys, tmp_project, monkeypatch)
      assert "categories" in payload
      assert "overall_status" in payload
      assert payload["exit_code"] == code
      for cat in payload["categories"]:
          assert "title" in cat and "checks" in cat
          for chk in cat["checks"]:
              assert set(chk) >= {"name", "status", "message", "remediation"}


  def test_doctor_json_scope_is_full(tmp_project, capsys, monkeypatch):
      _, payload = _run_json(capsys, tmp_project, monkeypatch)
      assert payload["scope"] == "full"
  ```
  Run: `.venv/bin/pytest tests/unit/test_doctor_json.py -q` → MUST fail.

- [ ] **GREEN** — modifica `engine/doctor.py`. Adiciona `import json` + `from dataclasses import asdict`
  (já há `from dataclasses import dataclass` — estender) + `from engine.ui import output_mode` +
  `import sys` se ausente. No início de `run`, após resolver `project_root` e `config`, adiciona
  branch JSON que pula o ask interativo e roda scope full:
  ```python
      if output_mode.is_json_mode():
          config_path = active_config_path(project_root)
          config = _safe_read_yaml(config_path) or {}
          categories = _all_categories(project_root, config_path, config, scope="full")
          code, overall_status = _render_verdict(categories, scope="full")
          _stamp_last_doctor_run(
              project_root, config_path, config, categories,
              exit_code=code, overall_status=overall_status,
          )
          payload = {
              "scope": "full",
              "overall_status": overall_status,
              "exit_code": code,
              "categories": [
                  {
                      "title": cat.title,
                      "worst": cat.worst,
                      "checks": [asdict(c) for c in cat.checks],
                  }
                  for cat in categories
              ],
          }
          print(json.dumps(payload, indent=2, default=str))
          return code
  ```
  Extrai a montagem de categories num helper `_all_categories(project_root, config_path, config, *, scope)`
  reusado pelo caminho interativo (linha 258-281) — evita duplicar a lista de `_check_*`. O caminho
  interativo passa a chamar `_all_categories(..., scope=scope)`. **Importante:** `_render_verdict`
  hoje pode escrever via `renderer` — em JSON mode esses writes viram no-op (suprimidos pelo chokepoint),
  então é seguro chamá-lo só pra obter `(code, overall_status)`. Confirmar que `_render_verdict` não
  escreve em stdout fora do renderer (ler a função antes de implementar).
  Run: `.venv/bin/pytest tests/unit/test_doctor_json.py -q` → MUST pass.

- [ ] **REGRESSION** — `.venv/bin/pytest tests/unit -k doctor -q` + lane rápida → 0 falhas, ≥ baseline.

- [ ] **COMMIT:** `feat(w3): forge doctor --json (A1 T3)`

---

## Task 4 — `forge verify --json`

**Tipo:** feature.

**Files:**
- Modify: `engine/verify.py:174` (`run`) / `run_scope:217` — serializa `list[_ValidatorResult]` em JSON mode.
- Create: `tests/unit/test_verify_json.py`

**Interfaces:**
- Consumes: `engine.ui.output_mode.is_json_mode`, `dataclasses.asdict`, `_ValidatorResult`.
- Produces: payload JSON `{scope: {type, target}, overall, exit_code, validators: [{name,status,duration_ms,message,paths,what_failed,where,why}]}`.

**Steps:**

- [ ] **RED** — `tests/unit/test_verify_json.py`:
  ```python
  import json
  from engine.ui import output_mode as om
  from engine import verify


  def _run_json(capsys, project_root, monkeypatch, argv=None):
      monkeypatch.chdir(project_root)
      token = om.set_output_mode(om.OutputMode.JSON)
      try:
          code = verify.run(argv or [])
      finally:
          om.reset_output_mode(token)
      out = capsys.readouterr().out
      return code, json.loads(out)


  def test_verify_json_no_validators_emits_pass(tmp_project, capsys, monkeypatch):
      # Empty project → no validators registered → overall pass, empty list.
      code, payload = _run_json(capsys, tmp_project, monkeypatch)
      assert code == 0
      assert payload["overall"] == "pass"
      assert payload["validators"] == []
      assert "scope" in payload and "exit_code" in payload


  def test_verify_json_stdout_pure(tmp_project, capsys, monkeypatch):
      _, payload = _run_json(capsys, tmp_project, monkeypatch)
      assert isinstance(payload, dict)
  ```
  Run: `.venv/bin/pytest tests/unit/test_verify_json.py -q` → MUST fail.

- [ ] **GREEN** — modifica `engine/verify.py`. Adiciona `import json` + `from dataclasses import asdict`
  (já há `from dataclasses import dataclass, field`) + `from engine.ui import output_mode`. Em
  `run_scope`, quando `output_mode.is_json_mode()`, troca os blocos de `renderer.write` interativos
  por emissão JSON e suprime os `_render_*`. O ponto-chave: `results: list[_ValidatorResult]` já é
  computado em `_run_cascade` (linha 319) antes de `_render_summary`. Estrutura:
  - caminho "nenhum validator" (linha 296-316): em JSON mode, monta payload com `validators: []`,
    `overall: "pass"`, emite JSON, mantém o `_write_verify_log_entry` + `_restore_l1_status` +
    `_clear_verify_checkpoint`, retorna 0.
  - caminho com cascade: após computar `results`/`overall`/`hard_fails`/`warnings_list`, em JSON mode
    NÃO chama `_render_summary`/`_render_hard_fail_block`; emite:
    ```python
    if output_mode.is_json_mode():
        payload = {
            "scope": {"type": scope_type, "target": scope_target or None},
            "overall": overall,
            "exit_code": (1 if hard_fail is not None else 0),
            "validators": [asdict(r) for r in results],
        }
        print(json.dumps(payload, indent=2, default=str))
    ```
  Preserva a lógica de L1 status restore + verify-log + checkpoint clear idêntica (read-only +
  observabilidade não muda entre modos). O exit code final é o mesmo do caminho interativo
  (0 pass/warn, 1 hard-fail). NÃO altera o intent protocol — verify não tem pausa em JSON mode
  (non-interactive: o ask de scope só dispara em multi-feature; documentar que JSON mode assume
  scope resolvível ou retorna a mensagem de erro em stderr + exit 1).
  Run: `.venv/bin/pytest tests/unit/test_verify_json.py -q` → MUST pass.

- [ ] **REGRESSION** — `.venv/bin/pytest tests/unit -k verify -q` + lane rápida → 0 falhas, ≥ baseline.

- [ ] **COMMIT:** `feat(w3): forge verify --json (A1 T4)`

---

## Task 5 — `forge memory --json` (read-only snapshot, narrow)

**Tipo:** feature. **Escopo NARROW deliberado** (ver veredito abaixo).

**Files:**
- Modify: `engine/memory_cli.py:421` (`run`) — emite snapshot read-only em JSON mode, sem menu REPL.
- Create: `tests/unit/test_memory_json.py`

**Interfaces:**
- Consumes: `engine.ui.output_mode.is_json_mode`, `read_l2` (→ `L2Entry`), `list_active_features`/`list_archived_features`/`read_l1_status`, `read_l3_index`, `l2_size_bytes`.
- Produces: payload JSON `{l2: {size_bytes, entries: [{id,kind,confidence,title,provenance}]}, l1: {active: [{slug,status,last_action_kind}], archived: [slug]}, l3: [{title,hook}]}`.

**Veredito sobre escopo (NARROW, não full):** `forge memory` é um menu REPL interativo de 7
submenus (inspect L2 paginado, inspect L1 {slug}, inspect L3, search, forget L2 com confirm dupla,
distill L2, export). Os submenus mutáveis (forget/distill) e os interativos (search por termo,
inspect com prompt de seleção) NÃO têm contraparte machine-readable não-ambígua — exigiriam
sub-flags/args que violariam o carve-out "meta-flags only" da Decisão 10 revisitada. O subset
read-only com estrutura limpa é: **inspect L2 (lista completa de entries via `read_l2`), L1
statuses (via `read_l1_status` sobre active+archived), e L3 index (via `read_l3_index`)** — todos
já retornam estruturas limpas. `forge memory --json` emite esse **snapshot read-only dos 3 layers**.
Search/forget/distill/export ficam fora do JSON mode (export já tem seu próprio stdout pipe; os
demais são interativos por natureza). Documentado em `04-pending.md` (T7) como limitação deliberada
+ carve-out: "`forge memory --json` é snapshot read-only; mutações e busca interativa permanecem
no menu REPL — sem flag por Decisão 10".

**Steps:**

- [ ] **RED** — `tests/unit/test_memory_json.py`:
  ```python
  import json
  from engine.ui import output_mode as om
  from engine import memory_cli


  def _run_json(capsys, project_root, monkeypatch):
      monkeypatch.chdir(project_root)
      token = om.set_output_mode(om.OutputMode.JSON)
      try:
          code = memory_cli.run([])
      finally:
          om.reset_output_mode(token)
      out = capsys.readouterr().out
      return code, json.loads(out)


  def test_memory_json_emits_three_layers(tmp_project, capsys, monkeypatch):
      code, payload = _run_json(capsys, tmp_project, monkeypatch)
      assert code == 0
      assert "l2" in payload and "l1" in payload and "l3" in payload
      assert "entries" in payload["l2"] and "size_bytes" in payload["l2"]
      assert "active" in payload["l1"] and "archived" in payload["l1"]
      assert isinstance(payload["l3"], list)


  def test_memory_json_does_not_enter_menu(tmp_project, capsys, monkeypatch):
      # JSON mode must NOT call question.ask — a pure-JSON stdout proves it.
      _, payload = _run_json(capsys, tmp_project, monkeypatch)
      assert isinstance(payload, dict)
  ```
  Run: `.venv/bin/pytest tests/unit/test_memory_json.py -q` → MUST fail.

- [ ] **GREEN** — modifica `engine/memory_cli.py`. Adiciona `import json` + `from engine.ui import output_mode`
  (`import sys` já presente). No início de `run`, logo após resolver `project_root`, adiciona branch JSON
  ANTES de qualquer `renderer.write`/`question.ask`:
  ```python
      if output_mode.is_json_mode():
          payload = _memory_snapshot(project_root)
          print(json.dumps(payload, indent=2, default=str))
          return 0
  ```
  Cria `_memory_snapshot`:
  ```python
  def _memory_snapshot(project_root: Path) -> dict:
      """Read-only machine snapshot of the 3 memory layers (A1, narrow).

      Mutating submenus (forget/distill) and interactive ones (search, inspect
      with selection prompt) are intentionally excluded — they have no
      unambiguous machine contract under the meta-flags-only carve-out of
      Decisão 10 revisitada. Export keeps its own stdout-pipe path.
      """
      l2_entries = read_l2(project_root)
      l2_size = l2_size_bytes(project_root) if memory_l2_path(project_root).exists() else 0
      active = list_active_features(project_root)
      archived = list_archived_features(project_root)
      active_payload = []
      for slug in active:
          st = read_l1_status(slug, project_root)
          active_payload.append(
              {
                  "slug": slug,
                  "status": (st.status if st is not None else None),
                  "last_action_kind": (st.last_action_kind if st is not None else None),
              }
          )
      return {
          "l2": {
              "size_bytes": l2_size,
              "entries": [
                  {
                      "id": e.id,
                      "kind": e.kind,
                      "confidence": e.confidence,
                      "title": e.title,
                      "provenance": list(e.provenance) if e.provenance else [],
                  }
                  for e in l2_entries
              ],
          },
          "l1": {"active": active_payload, "archived": list(archived)},
          "l3": [
              {"title": entry["title"], "hook": entry["hook"]}
              for entry in read_l3_index()
          ],
      }
  ```
  Run: `.venv/bin/pytest tests/unit/test_memory_json.py -q` → MUST pass.

- [ ] **REGRESSION** — `.venv/bin/pytest tests/unit -k memory -q` + lane rápida → 0 falhas, ≥ baseline.

- [ ] **COMMIT:** `feat(w3): forge memory --json read-only snapshot (A1 T5, narrow)`

---

## Task 6 — `forge --help --json` manifesto (A2 NO-MANIFEST)

**Tipo:** feature.

**Files:**
- Modify: `engine/cli.py:235` (`_print_help`) + `main:254` (branch `--help --json`).
- Create: `tests/unit/test_help_json_manifest.py`

**Interfaces:**
- Consumes: `COMMANDS` dict (linha 52), `_VISIBLE_ORDER` (linha 72).
- Produces: manifesto JSON `{forge_version, commands: [{name, summary, interactive, hidden, flags: [...], args: [...]}]}`.

**Schema do manifesto.** Deriva do `COMMANDS` dict + metadata estática (tabela canônica abaixo).
Cada comando: `name`, `summary` (1 linha mentor-calmo), `interactive` (bool — read-command vs intent
protocol), `hidden` (bool — `ingest`), `flags` (lista de meta-flags permitidas), `args` (posicionais).
Read-commands (`status`/`doctor`/`verify`/`memory`/`graph`) ganham `flags: ["--json"]`; o resto `flags: []`.

| name | summary | interactive | hidden | flags | args |
|---|---|---|---|---|---|
| init | Inicializa forge no projeto (mapa cinemático) | true | false | [] | [] |
| plan | Planeja uma feature (conversacional) | true | false | [] | ["feature-slug?"] |
| implement | Implementa a feature planejada | true | false | [] | ["feature-slug?"] |
| verify | Roda o cascade de validators (read-only) | false | false | ["--json"] | ["task TASK-NNNN \| feature SLUG?"] |
| status | Board read-only do projeto | false | false | ["--json"] | [] |
| doctor | Health check read-only | false | false | ["--json"] | [] |
| reconfigure | Atualiza config com diff incremental | true | false | [] | [] |
| graph | Consulta o codebase graph | false | false | ["--json"] | ["query args"] |
| memory | Inspeciona/gerencia memory layers | false | false | ["--json"] | [] |
| evolve | Review-and-apply de proposed evolutions | true | false | [] | [] |
| undo | Reverte mutações (2-step abort) | true | false | [] | [] |
| raw | Passthrough cru | true | false | [] | ["args"] |
| qa | QA red-team (auditores hostis) | true | false | [] | ["target?"] |
| upgrade | Atualiza snapshot da forge | true | false | [] | [] |

(`ingest` é hidden — não entra no manifesto visível; opcionalmente incluído com `hidden: true`
quando um flag interno `--include-hidden` for passado, mas isso é YAGNI agora — omitir `ingest`
do manifesto, espelhando `_VISIBLE_ORDER`.)

**Steps:**

- [ ] **RED** — `tests/unit/test_help_json_manifest.py`:
  ```python
  import json
  import io
  import pytest
  from engine import cli
  from engine.ui import output_mode as om


  def test_help_json_emits_manifest(capsys, monkeypatch):
      monkeypatch.delenv("FORGE_OUTPUT", raising=False)
      code = cli.main(["--help", "--json"])
      out = capsys.readouterr().out
      manifest = json.loads(out)
      assert code == 0
      assert "forge_version" in manifest
      assert isinstance(manifest["commands"], list)
      names = {c["name"] for c in manifest["commands"]}
      # All 14 visible commands present; hidden ingest absent.
      assert "status" in names and "plan" in names
      assert "ingest" not in names
      for cmd in manifest["commands"]:
          assert set(cmd) >= {"name", "summary", "interactive", "hidden", "flags", "args"}


  def test_help_json_read_commands_advertise_json_flag(capsys, monkeypatch):
      monkeypatch.delenv("FORGE_OUTPUT", raising=False)
      cli.main(["--help", "--json"])
      manifest = json.loads(capsys.readouterr().out)
      by_name = {c["name"]: c for c in manifest["commands"]}
      assert "--json" in by_name["status"]["flags"]
      assert "--json" in by_name["doctor"]["flags"]
      assert by_name["plan"]["flags"] == []  # interactive → no meta-flags


  def test_plain_help_still_prose(capsys, monkeypatch):
      monkeypatch.delenv("FORGE_OUTPUT", raising=False)
      cli.main(["--help"])  # no --json
      out = capsys.readouterr().out
      assert "Subcomandos" in out  # prose help unchanged
  ```
  Run: `.venv/bin/pytest tests/unit/test_help_json_manifest.py -q` → MUST fail.

- [ ] **GREEN** — modifica `engine/cli.py`. Adiciona `import json` + (output_mode já importado em T1).
  Cria a tabela de metadata + emissor de manifesto:
  ```python
  # A2 NO-MANIFEST — static per-command metadata for the machine manifest.
  # Derived from COMMANDS + _VISIBLE_ORDER; read-commands advertise --json
  # (Decisão 10 revisitada — meta-flags carve-out). Voz mentor-calmo nos summaries.
  _COMMAND_META: dict[str, dict] = {
      "init":        {"summary": "Inicializa forge no projeto (mapa cinemático).", "interactive": True,  "flags": [],         "args": []},
      "plan":        {"summary": "Planeja uma feature (conversacional).",          "interactive": True,  "flags": [],         "args": ["feature-slug?"]},
      "implement":   {"summary": "Implementa a feature planejada.",                "interactive": True,  "flags": [],         "args": ["feature-slug?"]},
      "verify":      {"summary": "Roda o cascade de validators (read-only).",      "interactive": False, "flags": ["--json"], "args": ["task TASK-NNNN | feature SLUG?"]},
      "status":      {"summary": "Board read-only do projeto.",                    "interactive": False, "flags": ["--json"], "args": []},
      "doctor":      {"summary": "Health check read-only.",                        "interactive": False, "flags": ["--json"], "args": []},
      "reconfigure": {"summary": "Atualiza config com diff incremental.",          "interactive": True,  "flags": [],         "args": []},
      "graph":       {"summary": "Consulta o codebase graph.",                     "interactive": False, "flags": ["--json"], "args": ["query args"]},
      "memory":      {"summary": "Inspeciona/gerencia memory layers.",             "interactive": False, "flags": ["--json"], "args": []},
      "evolve":      {"summary": "Review-and-apply de proposed evolutions.",       "interactive": True,  "flags": [],         "args": []},
      "undo":        {"summary": "Reverte mutações (2-step abort).",               "interactive": True,  "flags": [],         "args": []},
      "raw":         {"summary": "Passthrough cru.",                               "interactive": True,  "flags": [],         "args": ["args"]},
      "qa":          {"summary": "QA red-team (auditores hostis).",                "interactive": True,  "flags": [],         "args": ["target?"]},
      "upgrade":     {"summary": "Atualiza snapshot da forge.",                    "interactive": True,  "flags": [],         "args": []},
  }


  def _print_help_json() -> None:
      """Emit the machine-readable command manifest (A2 NO-MANIFEST).

      Only visible commands (``_VISIBLE_ORDER``) are listed — the hidden
      ``ingest`` entrypoint is intentionally omitted, mirroring the prose help.
      stdout is pure JSON (graph model); a consumer parses this instead of
      inferring the surface from prose (the failure mode that made the audit's
      second LLM hallucinate ~75% of its findings).
      """
      from engine import __version__
      commands = []
      for name in _VISIBLE_ORDER:
          meta = _COMMAND_META.get(name, {})
          commands.append(
              {
                  "name": name,
                  "summary": meta.get("summary", ""),
                  "interactive": meta.get("interactive", True),
                  "hidden": False,
                  "flags": list(meta.get("flags", [])),
                  "args": list(meta.get("args", [])),
              }
          )
      manifest = {"forge_version": __version__, "commands": commands}
      print(json.dumps(manifest, indent=2, default=str))
  ```
  No `main`, no branch de help (linha 264), distingue `--json`:
  ```python
      if cmd in ("-h", "--help", "help"):
          if "--json" in rest or "--json" in argv:
              _print_help_json()
          else:
              _print_help()
          return 0
  ```
  (Como `--help --json` chega como `argv = ["--help", "--json"]`, `cmd = "--help"` e `rest = ["--json"]`.)
  Run: `.venv/bin/pytest tests/unit/test_help_json_manifest.py -q` → MUST pass.

- [ ] **REGRESSION** — `.venv/bin/pytest tests/unit -k 'cli or help' -q` + lane rápida → 0 falhas, ≥ baseline.

- [ ] **COMMIT:** `feat(w3): forge --help --json manifesto de comandos (A2 T6)`

---

## Task 7 — Revisita Decisão 10 (ceremony append-only) + doc-sync

**Tipo:** doc-only (ceremony + doc-sync). **Mandamento #1 + #6.**

**Files:**
- Modify: `docs/design/01-decisions.md` (append row 32; marca linha 10 superseded — append-only)
- Modify: `CHANGELOG.md` (`### Added` + `### Changed (load-bearing)` com texto literal "Revisita Decisão 10")
- Modify: `docs/design/06-command-surface.md` (contract do manifesto + carve-out de meta-flags)
- Modify: `docs/design/08-session-handoff.md` (Última atualização + Estado + counts)
- Modify: `docs/design/04-pending.md` (fecha TOKEN-BLIND / NO-MANIFEST / NO-WORKFLOW-ROUTER / A1 / A2 + nota narrow de memory --json)
- Modify: `README.md` (se stats de comando/flags mudarem)

**Interfaces:**
- Consumes: estado dos commits T1-T6 (flags introduzidas).
- Produces: registro canônico da revisita + carve-out documentado.

**Protocolo append-only (CRÍTICO — `.claude/rules/decisions.md §protocolo`):**

- A linha 10 antiga (`| 10 | Interaction mode | 100% conversacional, sem flags | Human-first. CI mode not in v1. |`)
  recebe sufixo `(superseded by row 32 — 2026-06-18)` no campo Decision — **NÃO deletar, NÃO mudar
  numeração das demais**.
- APPEND a row 32 nova ao final da tabela (última row hoje é 31):
  ```
  | 32 | Revisita Decisão 10 (2026-06-18) — interaction mode | Conversacional human-first by default + modo machine-readable opt-in: meta-flags (`--json`, `--help --json`) + `FORGE_OUTPUT=json` env pros read-commands (status/doctor/verify/memory/graph) | Linha 10 histórica preservada (locked at "sem flags"); a partir desta data, read-commands aceitam meta-flags opt-in. Intent protocol (marker + exit-2) inalterado pros comandos interativos (plan/implement/init/reconfigure/evolve/qa) — `FORGE_OUTPUT`/`--json` NÃO alteram comportamento deles. Destrava CI/agentic legibility (A1 TOKEN-BLIND + A2 NO-MANIFEST/NO-WORKFLOW-ROUTER da auditoria-consolidada-2026-06-17 §3.2). Carve-out: meta-flags only — flags de comportamento de domínio continuam proibidas (Decisão 10 espírito human-first preservado). |
  ```
- `CHANGELOG.md` ganha em `## [Unreleased]`:
  - `### Added`:
    - `forge status --json` / `doctor --json` / `verify --json` / `memory --json` (snapshot read-only) — output machine-readable pros read-commands.
    - `forge --help --json` — manifesto de comandos/args/flags machine-readable (A2 NO-MANIFEST).
    - `forge status --json` inclui `suggested_next_command` (workflow router, A2 NO-WORKFLOW-ROUTER).
    - `FORGE_OUTPUT=json` env + output-mode global host-aware (`engine/ui/output_mode.py`) — `renderer.write` consulta o modo (A1 TOKEN-BLIND).
  - `### Changed (load-bearing)`:
    - Texto LITERAL: `Revisita Decisão 10: conversacional human-first + meta-flags opt-in (--json, --help --json, FORGE_OUTPUT=json) pros read-commands — intent protocol inalterado pros interativos. Destrava token economy / machine-legibility (auditoria §3.2 A1/A2).`

**Nota de casing (L-001 — verificado contra o hook):** o plano usa consistentemente "Revisita
**Decisão** 10" (D maiúsculo) em decisão/CHANGELOG/commit. O hard-block do pre-commit
(`.claude/hooks/pre-commit-feature-forge.sh:24`) casa via `grep -qiE 'revisita decisão|revisit decision'`
— o flag `-i` é case-insensitive, então "Revisita Decisão 10" satisfaz o gate normalmente (o hook só
exige a frase `revisita decisão` no diff staged do CHANGELOG, não a grafia exata). Casing mantido
maiúsculo por consistência interna do plano; nenhuma ação adicional necessária.

**Steps:**

- [ ] Edita `docs/design/01-decisions.md`: marca linha 10 como superseded (append `(superseded by row 32 — 2026-06-18)`)
  + APPEND row 32 conforme acima. Não toca numeração das demais.
- [ ] Edita `CHANGELOG.md`: adiciona `### Added` + `### Changed (load-bearing)` com texto literal
  "Revisita Decisão 10" (obrigatório pro pre-commit hard-block).
- [ ] Edita `docs/design/06-command-surface.md`: adiciona seção do contrato do manifesto
  (`forge --help --json` schema: command/summary/interactive/hidden/flags/args) + documenta o
  carve-out de meta-flags da Decisão 10 revisitada (read-commands aceitam `--json`; `FORGE_OUTPUT=json`
  env; interativos inalterados). Atualiza qualquer menção a "sem flags" pra refletir o carve-out.
- [ ] Edita `docs/design/08-session-handoff.md`: `**Última atualização:** 2026-06-18 (W3 — token economy /
  machine-legibility)` + `**Estado:**` reflete A1/A2 entregues + ganha linha na tabela de categorias se
  aplicável + counts de tests atualizados (rapid +N novos tests das T1-T6).
- [ ] Edita `docs/design/04-pending.md`: risca/fecha os gaps TOKEN-BLIND, NO-MANIFEST,
  NO-WORKFLOW-ROUTER, A1, A2; adiciona nota da limitação deliberada: "`forge memory --json` é
  snapshot read-only (L2/L1/L3); search/forget/distill permanecem no menu REPL — sem sub-flags por
  carve-out meta-flags-only da Decisão 10 revisitada".
- [ ] Edita `README.md` SE as stats de comando/flags estiverem documentadas lá (verificar antes;
  se não mencionar flags, omitir — não inventar mudança de stat).
- [ ] **VERIFICAÇÃO** — `.venv/bin/pytest -m 'not integration and not e2e' -q | tail -1` → 0 falhas,
  ≥ baseline + novos tests; `forge verify` sem hard fail (rodar via subagente).
- [ ] **COMMIT** (deve conter "Revisita Decisão 10" na mensagem — pre-commit hard-block exige):
  `docs(w3): Revisita Decisão 10 — meta-flags opt-in + doc-sync token economy (T7)`

---

## Self-review final (pré-handoff)

Antes do execution-handoff, confirme:

**Cobertura A1 (TOKEN-BLIND):**
- [ ] Output-mode global via context var (T1) — `engine/ui/output_mode.py` ✓
- [ ] `renderer.write` host-aware (T1) — chokepoint consulta o modo ✓
- [ ] `FORGE_OUTPUT=json` env (T1 — `detect_output_mode`), GATED no allowlist `_JSON_CAPABLE_COMMANDS` ✓
- [ ] `--json` read-commands: status (T2) / doctor (T3) / verify (T4) / memory (T5, narrow) ✓
- [ ] `graph --json` pré-existente reusado como modelo (Decisão de design 3) ✓

**Cobertura A2 (NO-MANIFEST / NO-WORKFLOW-ROUTER):**
- [ ] `forge --help --json` manifesto (T6) ✓
- [ ] `forge status --json` → `suggested_next_command` (T2) ✓

**Ceremony (Mandamento #1):**
- [ ] T7 marca linha 10 superseded (append-only, NÃO deleta) + APPEND row 32 ✓
- [ ] CHANGELOG `### Changed (load-bearing)` com texto LITERAL "Revisita Decisão 10" ✓
- [ ] Commit T7 message contém "Revisita Decisão 10" ✓

**Doc-sync (Mandamento #6):**
- [ ] CHANGELOG + 01-decisions + 06-command-surface + 08-handoff + 04-pending (+ README condicional) — todos em T7 ✓

**Placeholder scan:** sem TBD/TODO/FIXME; `...` só dentro de blocos verbatim de arquivos a criar
(não há). Placeholders `<N>`/`feature-slug?` são args do manifesto (template do destino), não do plano.

**Type/name consistency (case-sensitive):**
- [ ] `OutputMode` / `output_mode` / `detect_output_mode` / `set_output_mode` / `get_output_mode` /
  `reset_output_mode` / `is_json_mode` — grafia idêntica em T1-T6 ✓
- [ ] `_status_payload` / `_suggested_next_command` / `_pending_evolutions_count` (T2) ✓
- [ ] `_all_categories` (T3) / `_memory_snapshot` (T5) / `_print_help_json` / `_COMMAND_META` (T6) ✓
- [ ] `suggested_next_command` (chave JSON, snake_case) consistente entre T2 e o manifesto/router ✓

**Intent protocol intocado (H-001 — enforce + guard):**
- [ ] Nenhuma task altera marker `<FORGE_INTENT/>`, `EXIT_PAUSED`, ou handlers interativos ✓
- [ ] JSON mode é carve-out read-command-only ENFORÇADO via `_JSON_CAPABLE_COMMANDS`
  (allowlist em `detect_output_mode`, gated por `command=cmd` no `cli.main` — T1) ✓
- [ ] Comando interativo sob `FORGE_OUTPUT=json` resolve PLAIN/TTY, nunca JSON (Caminho B) ✓
- [ ] Guard `tests/unit/test_output_mode_interactive_safety.py` (Caminho A) prova: (a) marker
  emitido em stdout sob JSON mode, (b) exit-2 (`PausedForInputError`) preservado, (c) interativo
  resolve PLAIN — teste de NÃO-REGRESSÃO que ancora a afirmação "intent protocol intocado" ✓

**Spec coverage (M-001 / C2):** plano-driven sem spec dedicado; override C2 no header reconhece a
fonte auditoria-consolidada §3.2/§4/§6 como spec de-facto, com cobertura task-a-task confirmada.

**Casing (L-001):** "Revisita Decisão 10" consistente interno; hook casa case-insensitive (verificado).

**Baseline:** rapid 1729 / integration 180 / e2e 30 — nenhuma task reduz; cada uma adiciona tests
(T1 agora adiciona 3 grupos: `test_output_mode.py` + `test_renderer_output_mode.py` +
`test_output_mode_interactive_safety.py`).
