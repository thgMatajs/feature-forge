# Changelog

Todas as mudanças notáveis no feature-forge.

Formato baseado em [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versionamento: [SemVer](https://semver.org/lang/pt-BR/spec/v2.0.0.html).

## [Unreleased]

(nada ainda)

## [1.4.0] - 2026-06-17

Esforço codinome v1.3-pilot-ready; shipa como 1.4.0 (1.3.0 = graph-ia, já em main).

Release piloto: host abstraction completa, adapters para os 4 contextos de
execução (Claude Code / TTY / Opencode / IntentFile), init brownfield-safe,
instalador curl one-liner, `forge upgrade`, e 7 bugs MeoBonsai fechados.
Clean-break deliberado frente a v1.2.x — projetos experimentais reinicializam.

### Added

- **`engine/host/` module** — abstração de host completa: adapter ABC
  (`HostAdapter`, `HostName`, `AskKind`, `AskResult`) + env detectors
  (`CLAUDECODE` / `OPENCODE_*` / `CODEX_*` / `CURSOR_*`) + registry +
  detecção de host com precedência config > env > TTY > fallback. Wave 0.
- **`ClaudeCodeAdapter`** — adapter in-process para Claude Code: emite
  marcador stdout `<FORGE_INTENT/>` que o host intercepta em tempo real;
  zero subprocess overhead. Wave 0.
- **`IntentFileAdapter`** — adapter DRIFT-1 fallback: escreve intent JSON em
  `.claude/forge/state/forge-pending.json`, lê response de
  `.claude/forge/state/forge-response.json`, exit 2 sinaliza pausa pro host.
  Wave 0.
- **`TtyAdapter` in-process** — `engine/host/adapters/tty.py`: lê
  `sys.stdin` diretamente (line buffered), valida resposta localmente e
  devolve `AskResult` ao engine sem subprocess. Substitui
  `engine/ui/tty_bridge.py` subprocess-loop. `engine/ui/_stdin_prompt.py`
  extrai helpers de prompt/validação reusados pelo adapter. Wave 2.
- **OPENCODE → `IntentFileAdapter` fallback (Veredito B)** — research W2.T0
  (`docs/research/opencode-tool-api.md`) documentou que opencode NÃO suporta
  adapter in-process: stdout de subprocess não é interceptado em tempo real e
  não existe env var oficial confiável. Veredito B: opencode usa
  `IntentFileAdapter` como fallback, sem execução in-process de tools.
  Spec R1 success criterion #4 atendido. Wave 2.
- **Sub-namespace `.claude/forge/`** — isola state e hooks do forge do
  `.claude/` do usuário. Novos helpers em `engine/utils/paths.py`:
  `forge_dir`, `forge_config_path`, `forge_state_dir`, `forge_cards_local_dir`,
  `forge_hooks_dir`. `engine/init.py` escreve projetos greenfield sob
  `.claude/forge/`. 50+ callsites em engine/ + validators/ migrados. Wave 0.
- **Brownfield-safe init (Wave 1)** — `_detect_brownfield` detecta
  `.claude/{skills,agents,settings.json}`. `engine.utils.settings_merge`:
  `merge_settings_json` append-only com dedup-via-deep-equal +
  `read_settings_tolerant` JSON5-tolerante (comments + trailing commas via
  lib `json5`). `engine.init._install_git_hooks` reescrito como chained
  delegator: hooks existentes do usuário migram para `<name>.user` e são
  encadeados via bash wrapper com `FORGE_DELEGATOR_MARKER`. Idempotente;
  faz upgrade de installs symlink-style antigos. Fixture sintética
  `tests/fixtures/meobonsai-class/` (5 skills + 3 agents + 2 user hooks +
  settings.json + CLAUDE.md) valida 3 regression tests + 3 brownfield
  contract tests. Nova dep: `json5>=0.9.10` em `pyproject.toml`.
  `engine.init._run_pipeline` invoca `_merge_forge_hooks_into_settings`
  pós-install de hooks: registra SessionStart → session-start-drift-check.sh;
  PostToolUse(Edit|Write|NotebookEdit) → post-edit-codebase-graph.sh;
  PostToolUse(Write) → post-write-feature-artifact.sh; SubagentStop →
  post-subagent-validate.sh. Tudo apontando para `.claude/forge/hooks/`.
- **`scripts/install.sh`** (244 LOC, bash 3.2 portável) — instalador curl
  one-liner. Clone `--depth=1` de `github.com/thgMatajs/feature-forge` em
  `FORGE_HOME` (`~/.local/share/feature-forge` — XDG default) + criação de
  venv + `pip install -e .` + symlink em `~/.local/bin/forge`. PATH detection
  marker-guarded e idempotente: detecta `~/.zshrc` / `~/.bashrc` /
  `~/.config/fish/config.fish` e oferece 3-caminhos (auto-append / manual /
  skip). Alias conflict detection: se `forge` já existe no PATH (de outro
  tool), propõe `forge-cli` como `BIN_NAME` alternativo via 3-caminhos.
  Wave 4.
- **`engine/upgrade.py`** + subcomando **`forge upgrade`** — git
  `pull --ff-only` na `FORGE_HOME` + venv refresh (`pip install -e .
  --upgrade`) + smoke (`forge --version`). Rollback automático
  (`git reset --hard prev_head`) em falha de smoke. API pública:
  `run_upgrade(*, forge_home=None, force=False) -> int`. Wired em
  `engine/cli.py` `COMMANDS` (subcomandos 13 → **14**) e em
  `_BOOTSTRAP_SKIP`. Wave 4.
- **Per-host e2e** — `tests/e2e/test_per_host_dispatch.py` (claude_code
  adapter via marker+exit2 / intent_file pending round-trip / opencode
  fallback) + `tests/e2e/test_tty_adapter_pty.py` (TtyAdapter via pty,
  stdin in-process sem subprocess). Cobertura dos 4 caminhos de detecção
  de host. Wave 2.
- **Pilot smoke e2e** — `tests/e2e/test_install_sh.bats` +
  `tests/e2e/test_install_sh.py` (PATH/alias/version scenarios; skipif bats
  ausente) + `tests/e2e/test_forge_upgrade.py` (pull cycle + rollback via
  repos git locais). Wave 4.
- **Renderer ASCII fallback non-TTY** — `engine/ui/renderer.py::write()`
  degrada box-drawing Unicode (┌┐└─│) pra ASCII (+,-,|) em contextos
  non-TTY via `_BOX_TO_ASCII` map + `to_ascii_box()` helper. Corrige bug U3:
  box-drawing virava `?` em pipes e captura de stdout em CI. Wave 2.
- **Parser fixes (PR #16 Wave A)** — Objective-C: body extraction
  brace-matched + `_mask_strings_and_comments` + categorias
  `@interface Foo (Bar)` / class extensions `@interface Foo ()` como símbolos
  próprios; P-N-018 pre-computa posições de `@end` (evita O(N²)). XML:
  prefixes fully-qualified, sanitização de IDs, perf de attributes,
  cobertura de view IDs e data-binding actions. Java: generics em assinatura,
  modifiers (default/static/synchronized/etc.), tipos de retorno
  parametrizados. Kotlin: logging consistente + docstring sobre limites regex.
  `_mask_strings_and_comments` promovido para `engine/graph/_body_text.py`
  (módulo compartilhado); `engine/graph/kinds.py` consumido por parsers
  (deixa de ser dead code).
- **Test coverage additions (PR #16)** — cobertura nova em arquivos
  preexistentes (delta full suite 1548 → 1619 = +71):
  `tests/unit/test_parser_objc.py` 14 → 25; `tests/unit/test_parser_xml.py`
  7 → 13; `tests/unit/test_parser_java.py` 9 → 19;
  `tests/engine/test_migrations.py` 2 → 5 (T-N-012);
  `tests/integration/test_multilang_graph_build.py` cobertura expandida
  (T-N-011). 84 tests em arquivos novos do PR (Java 19 + ObjC 25 + XML 13 +
  bootstrap 6 + lazy 6 + json 9 + migrations 5 + integration 1).
- **Regression suite MeoBonsai** (`752b0fd`) —
  `tests/integration/test_bug_regressions.py` cobre 7 cenários
  integration-level: 3 críticos (bug #1 intent-id mismatch, bug #2 stale
  response poisoning, bug #3 piped stdin) + 4 utilitários (U1 exit codes,
  U2 WARN, U3 ASCII fallback, U4 qa sem-args). Wave 3.

Test counts finais (pós-Wave 4): rapid **1565 passed**, integration
**162 passed**, e2e **27 passed**, 0 falhas.

### Changed

- **`validate_workflow_config.py` → `validate_forge_config.py`** — validator
  renomeado + classe `ValidateWorkflowConfig` → `ValidateForgeConfig` + schema
  bump 1.2 → 1.3. Wave 0.
- **`engine/ui/question.py` delega ao host adapter** — `ask` / `ask_multi` /
  `ask_text` delegam ao adapter registrado, preservando exception classes +
  `ask_three_paths` + `confirm`. Wave 0.
- **`bin/forge` dispatcher simplificado** — `exec python -m engine.cli`
  diretamente em todos os casos; detecção de host (TTY, ClaudeCode, opencode,
  intent-file) 100% no lado Python via `detect_host()`. Branch
  `FORGE_FORCE_TTY_MODE` removida (clean break — `tty_bridge.py` não existe
  mais). Wave 2.
- **Exit codes unificados** — `forge graph`, `forge memory`, e
  `forge reconfigure` invocados antes de `forge init` (pre-init) agora
  retornam exit 1. Contrato completo: `pre-init=1 / intent-pause=2 /
  cancel=130`. Wave 3 (bug U1).
- **`FORGE_FORCE_INTENT_MODE` movido para `detect_host`** — preserve escape-hatch
  DRIFT-1 §439 pós clean-break de `tty_bridge.py`. Wave 2.
- **`intent_state._state_dir` default migrado** — de `.claude/state/` para
  `forge_state_dir(project_root)` = `.claude/forge/state/`. Fecha 13 falhas
  de integration pré-existentes (tty_bridge + question.confirm/ask_three_paths
  lendo do path legacy enquanto adapters escrevem no sub-namespace). ~50 test
  path assertions migrados. Wave 1 follow-up.
- **Bootstrap hardening (PR #16 Wave C)** — `.claude/bootstrap.sh`: `flock -n`
  em `.claude/state/bootstrap.lock` previne race em runs simultâneos (fallback
  gracioso quando flock indisponível no macOS); captura stderr de
  `pip install -e .` em `.claude/state/pip-install.log`; log de
  `forge graph --json q3` em `.claude/state/bootstrap-graph.log`; glob
  `hooks/git-*` substitui lista hardcoded.
- **`hooks/post-edit-codebase-graph.sh` early-exit** — pula re-ingest custoso
  em `*/build/*`, `*/node_modules/*`, `*/.gradle/*`, `*/dist/*`, `*/target/*`,
  `*/DerivedData/*`, `*/.next/*`, `*/out/*` (PR #16 T-N-017).
- **Engine robustness (PR #16 Wave B)** — symlink-safe walker via `scandir`
  (substitui `rglob`) em `engine/graph/builder.py`; narrow de exceptions em
  handlers + fail-loud em invariants quebrados em `engine/cli.py`; TOCTOU
  migration race coberto por commit-after-migration em
  `engine/utils/sqlite_io.py`; overload collision em parsers Kotlin/Java
  emite warning estruturado em vez de silent overwrite.

### Changed (load-bearing)

- **Revisita decisão 18**: skill location → `~/.local/share/feature-forge/`
  (XDG default; respeita `$XDG_DATA_HOME`). Era `~/Documents/feature-forge/`.
  Razão: XDG é convenção universal pra ferramentas instaladas via script;
  `~/Documents/` confunde com o diretório de docs do usuário. Linha antiga
  preservada em `docs/design/01-decisions.md` (row 18 superseded by row
  18-v2). `scripts/install.sh` já usa o destino XDG. Wave 5.

### Fixed

- **Bug #1 — intent-id mismatch (DRIFT-1 multi-pergunta-por-ciclo)** —
  `engine/ui/intent_state.py::read_response` e `detect_race` agora tratam
  `intent-id` já presente no consumed-log como stale-leftover (resposta de
  pergunta anterior na mesma invocação), não como erro: `read_response` retorna
  `None` (caller emite novo pending), `detect_race` varre e remove o pending
  stale. Comandos multi-pergunta-por-ciclo (ex.: `forge reconfigure`
  category→submenu) funcionam sob host real sem `IntentMismatchError` espúrio.
  Mismatch genuíno e race genuíno ainda levantam `IntentMismatchError` /
  `RaceDetectedError`. Drive loop limpo em e2e reconfigure via
  `drive_intent_loop`. Refs commits 5827900/7c26377. Wave 2.
- **Bug #2 — stale response poisoning** — `read_response` verifica
  consumed-log antes de consumir response, evitando que response de
  intent-id anterior envenene ciclo seguinte. Coberto pela regression suite
  MeoBonsai (bug #2 scenario). Wave 2.
- **Bug #3 — TtyAdapter guard non-TTY com mensagem DEPRECATED** (`00dad0d`)
  — `engine/host/adapters/tty.py` detecta stdin piped (non-TTY interativo)
  e emite mensagem `DEPRECATED v1.3` orientando ao uso do harness agentic
  ou terminal real, em vez de travar aguardando input que nunca chega.
  Wave 3.
- **Bug U1 — exit codes unificados** (`edfd20c`) — ver seção Changed acima.
  Wave 3.
- **Bug U2 — WARN de cleanup suprimido em `--help`/`-h`/sem-args** (`d9d3bb5`)
  — guard `is_help` adicionado no bloco `finally` de `engine/cli.py`;
  invocações de ajuda e sem argumentos não emitem mais o aviso de cleanup de
  log. Residual: bloco `finally` captura `ProjectRootNotFoundError`
  silenciosamente em contextos pre-init (`b0fcb35`). Wave 3.
- **Bug U3 — renderer ASCII fallback** — ver seção Added acima. Wave 2.
- **Bug U4 — `forge qa` sem args apresenta 3-caminhos** (`137a993`) — guard
  adicionado em `_qa_run` antes de `resolve_scope`; ao ser invocado sem
  argumentos, exibe bloco mentor-calmo de 3-caminhos em stdout com exit 0,
  sem `ValueError` nem traceback. Wave 3.
- **e2e env scrub** — `tests/e2e/conftest.py::env_with_forge_home` faz scrub
  de variáveis agentic (`CLAUDECODE`, `OPENCODE_*`, `CODEX_*`, `CURSOR_*`)
  antes de iniciar subprocesso forge. Sem o scrub, suites rodadas dentro de
  Claude Code herdavam o env agentic e roteavam pro adapter errado — e2e
  não-determinístico dependendo do host de CI. Bug pré-existente surfaced
  durante verificação Wave 2. Wave 2.
- **`scripts/install.sh` bash 3.2 portability** (`b5d0bee`) — substituição
  `${var,,}` → `echo "$var" | tr '[:upper:]' '[:lower:]'` para
  compatibilidade com o bash 3.2 default no macOS. Wave 4.
- **`test_read_settings_tolerant_handles_comments` skipif** — pula quando lib
  `json5` ausente (system pytest fallback); os outros 4 testes de
  settings_merge funcionam com fallback stdlib `json`. Wave 1 follow-up.

### Removed

- **`engine/ui/tty_bridge.py` subprocess-loop** — substituído por
  `engine/host/adapters/tty.py` in-process (TtyAdapter). `tty_bridge`
  re-invocava o engine completo via subprocess pra cada pergunta TTY —
  model mental mais complexo, mais lento, gerava processos extras. Clean
  break; sem shim de retrocompatibilidade. Wave 2.
- **`FORGE_FORCE_TTY_MODE` branch em `bin/forge`** — env var de fallback pra
  `tty_bridge` removida junto com o módulo. `FORGE_FORCE_INTENT_MODE`
  preservado em `detect_host` (escape-hatch DRIFT-1 diferente). Wave 2.
- **`tests/e2e/test_tty_bridge_e2e.py`** e **`tests/unit/test_ui_tty_bridge.py`**
  — testes do subprocess-loop removidos. Cobertura equivalente migrada para
  `test_tty_adapter_pty.py` e `test_per_host_dispatch.py`. Wave 2.
- **Nenhum migrator v1.2→v1.3** — clean-break deliberado. Projetos
  experimentais em v1.2 reinicializam: limpar `.claude/` + `forge init`.

### Deferred (anotados em `docs/design/04-pending.md`)

- **P-N-007** (is_method_call heurística refinamento — exige parser real,
  fora do escopo regex)
- **N-004** (AC-11 escopo bootstrap-detection — policy decision pendente
  com user)
- **N-007 / N-015** (silent audit log em `.claude/state/hook-failures.jsonl`
  — cross-cutting cross-hook)
- **N-012** (migrations dentro de transaction — refactor estrutural;
  parcialmente coberto por commit-after-migration)
- **N-013** (3-state helper `_db_has_full_rebuild_marker`)
- **M-003** (perf O(N²) Java/XML — pre-compute newlines positions via
  `bisect`; ObjC já coberto por P-N-018, registrado pra v1.3.1+)
- **T-N-025** (plan-auditor severity calibration — DOC only, exige
  discussion com user antes de mexer)

## [1.3.0] — 2026-06-15

### Added (graph-ia-evolution — body column + multi-language parsers + --json + onboarding UX)

Expansão do codebase graph pra consumo direto por IA: símbolos agora
carregam `body` text, novos parsers cobrem Java/XML/ObjC, flag `--json`
habilita queries non-interactive, e onboarding UX detecta bootstrap state
ausente. 8 ondas lógicas (11 commits atômicos: plan-extension + extension-fix
+ doc-sync ficaram em commits separados das ondas principais) acumuladas em
`feat/graph-ia-evolution`.

- **`symbols.body` column** — `engine/utils/sqlite_io.py` ganha
  `_ensure_graph_body_column` (ALTER TABLE idempotente). DBs novos
  contêm `body TEXT` na criação; DBs existentes migram em-place sem
  rebuild + sem bump de `SCHEMA_VERSION`. Populado por todos os parsers
  com corpo delimitado por chaves (Kotlin/Swift/TS/Java/ObjC); NULL pra
  XML symbols. Habilita assistentes IA a inspecionar implementação direto
  do graph sem abrir o arquivo-fonte.
- **`forge graph --json <query> [args...]`** — flag non-interactive emite
  JSON parseável em stdout, sem prompts. Aceita aliases (`q1..q17`/`r`),
  numeric keys (`1..17`), ou labels textuais (`where-is-used`,
  `blast-radius`, …). Modo interactivo (`forge graph` sem `--json`)
  continua inalterado. Stderr reservado pra erros.
- **Java parser** — `engine/graph/parser_java.py` expõe
  `parse_java_file(text, path) -> JavaFileInfo`: package declaration,
  imports (incl. wildcards), classes/interfaces/enums/records (top-level
  e nested), methods/constructors com body text e reuse-intelligence
  metadata. Constructor distinguido de method via match de nome contra
  classe enclosing (heurística regex).
- **XML parser** — `engine/graph/parser_xml.py` expõe
  `parse_xml_file(text, path) -> XmlFileInfo`: view IDs (`@+id/...`),
  classes referenciadas (tag fully-qualified + atributos
  `android:name`/`class=`), data binding variables, resource keys
  (`string`/`dimen`/`color`/etc.), e expressões de binding action
  (`@{...}` com método invocado).
- **Objective-C parser** — `engine/graph/parser_objc.py` expõe
  `parse_objc_file(text, path) -> ObjcFileInfo`: `#import` e `@import`,
  `@interface`/`@protocol`/`@implementation`, methods (instance `-` e
  class `+`), properties com attributes (`nonatomic`, `strong`, …).
  Mensagens enviadas (`[obj selector]`) explicitamente NÃO geram call
  edges (non-goal v1.3).
- **Extensões `.java` / `.xml` / `.m` / `.mm` registradas** — em
  `_LANGUAGE_EXTENSIONS` (`engine/graph/builder.py`), `_GRAPH_EXTENSIONS`
  (`engine/ingest.py`), `_SUPPORTED_LANGS` (`engine/graph/_body_text.py`,
  exceto `xml` que não tem body extraction), e no `case` match de
  `hooks/post-edit-codebase-graph.sh`. Build full e incremental
  dispatcham os novos parsers via `_persist_java`/`_persist_xml`/
  `_persist_objc`.
- **CLAUDE.md AI consumption instructions** — seção `## Codebase Graph
  — IA-ready` instrui o modelo a consultar `forge graph --json <q>` antes
  de ler arquivos-fonte quando a pergunta cabe em Q1–Q17. Inclui
  exemplos canônicos por query + lista de linguagens cobertas.
- **Bootstrap state detection** — `engine/cli.py::_check_bootstrap_state`
  detecta `.git/hooks/pre-commit` symlink ausente/broken e emite friendly
  error instruindo o user a rodar `bash .claude/bootstrap.sh`. Onboarding
  UX pra novos devs num projeto que já tem forge.
- **Lazy graph auto-build** — `engine/graph_cli.py::_maybe_auto_build`
  detecta `.claude/graph.db` ausente/empty e dispara build inicial
  silenciosamente na primeira invocação de `forge graph` (~30s-2min,
  one-shot). Bootstrap script (`bash .claude/bootstrap.sh`) faz o mesmo
  build idempotentemente no setup inicial.
- **Flag `--no-auto-build`** — em `forge graph` desativa o lazy rebuild
  pra uso em CI/scripts determinísticos (espera que o DB já exista).
  Combina com `--json` pro pattern não-interativo completo.

### Changed (graph-ia-evolution)

- **`.claude/bootstrap.sh` Step 6** — após install de deps via
  `pip install -e .`, dispara build inicial do graph + inventory
  (idempotente). Sem isso, a primeira invocação de `forge graph`
  triggera lazy rebuild. Ambos caminhos convergem no mesmo state.

### Documentation (graph-ia-evolution)

- **`docs/schemas/graph.md`** — documenta a coluna `symbols.body`
  (semântica + populated-for + NULL-for + ALTER TABLE migration) e a
  flag `--json` (non-interactive JSON queries) com exemplos canônicos.
- **`docs/design/08-session-handoff.md`** — Estado v1.3.0 entregue;
  Última atualização 2026-06-15.
- **`README.md`** — §Stats bump (parser count 3 → 6, test count
  baseline + 84 tests novos em arquivos novos do PR: Java 19 + ObjC 25 +
  XML 13 + bootstrap 6 + lazy 6 + json 9 + migrations 5 + integration 1;
  full suite cresce de 1548 → 1619, +71 considerando cobertura nova em
  arquivos preexistentes — diferença é Wave A+B+C fix-pack pós-review)
  + §Command surface menciona `forge graph --json` como entrypoint
  non-interactive.
- **`docs/design/04-pending.md`** — registra v1.3.0 shipped + 6
  non-goals como follow-ups v1.4+ (tree-sitter, MCP server, ObjC call
  graph, call graph preciso, SCHEMA_VERSION bump, visualização
  gráfica). Critério explícito pra reentrada de cada um.
- **`docs/superpowers/plans/2026-06-12-graph-ia-evolution.md`** —
  extensão Task 9.5 (onboarding UX) + Step 9.6/9.7 (pending + README).

## [Unreleased — pre-1.3 carry-over]

### Changed

- **chore(gitignore)** — Adicionadas entradas faltantes pra runtime
  artifacts: `.claude/state/*.lock`, `.claude/worktrees/`, `.gsd-tmp/`,
  `.planning/*-review/` (generic), `.ultra-review/`, `docs/design/outputs/`.
  Reduz noise em `git status` pós-bootstrap.
- **chore(gitignore PR #14)** — `.planning/*` agora catch-all com whitelist
  explícita pra `det-3/`, `det-6/`, `drift-1/`. Scratch de review/audit/fix
  não polui mais o working tree.
- **`.claude/rules/orchestrator-persona.md`** — nova seção §Cleanup de
  `.planning/` ao final do trabalho — disciplina manual paralela aos `.bak`
  retention.

### Added (User-facing docs, 2026-06-12)

- **`docs/guides/getting-started.md`** — Guia de primeiros passos: onboarding completo para devs mobile, incluindo instalação, init, e adoção em time.
- **`docs/guides/daily-workflow.md`** — Guia de comandos do dia a dia: cobertura dos 13 comandos com cenários, exemplos e árvore de decisão.
- **`docs/guides/feature-lifecycle.md`** — Lifecycle de uma feature: pipeline do intake à retrospectiva, com artefatos e variações por subtipo.
- **`docs/guides/dot-claude-reference.md`** — Referência amigável dos arquivos `.claude/`: tabela versionado vs local, explicações detalhadas.
- **`docs/diagrams/bootstrap-flow.mermaid`** — Diagrama do fluxo de adoção do forge pelo time.
- **`docs/diagrams/feature-lifecycle.mermaid`** — Diagrama do pipeline completo de uma feature.
- **`docs/diagrams/command-decision-tree.mermaid`** — Diagrama de decisão: qual comando usar em cada situação.
- **`docs/diagrams/graph-query-flow.mermaid`** — Diagrama de fluxo de consulta do graph.
- **`docs/diagrams/files-versioned-vs-local.mermaid`** — Diagrama de arquivos versionados vs locais.

### Fixed (PR #14 docs review — 2026-06-15)

Aplicando findings do review independente do PR #14 (`docs/user-guides`).
Counts agora consistentes entre guides, diagrams, `CLAUDE.md` raiz e a
ground truth do `main`.

- **Counts factuais** corrigidos em todos os artefatos:
  - `forge doctor`: 14/12 → **16 categorias** (`engine/doctor.py` tem 16
    funções `_check_*`)
  - `forge verify`: 8/20/15 → **3 validators built-in + N contribuídos por
    cards ativos**; 21 validators no diretório `validators/` (era anunciado
    como 15 no `CLAUDE.md`)
  - Commands: 13 user-facing (ingest é hook interno, documentado como tal)
  - Tests: 637 → ~1531 (consulte handoff pra count atual)
- **`forge ingest`**: nova seção em `daily-workflow.md` documentando que
  é hook interno (não digitado manualmente) — fecha gap apontado em
  H-001.
- **`feature-lifecycle.md` Fase 5**: lista de gates expandida pra cobrir
  `check_no_invented_behavior`, `check_files_in_allowed_files`,
  `check_no_behavior_change` (refactor); separa gates da task do cascade
  completo do `forge verify`.
- **`feature-lifecycle.mermaid`**: Fase 6 corrigida pra `forge verify`
  (era `forge doctor`); `forge undo` movido pra subgraph TRANSVERSAL
  (não é comando de retrospectiva).
- **`files-versioned-vs-local.mermaid`**: `memory/L1/archived/` isolado
  no nó VERSIONADO; `memory/L1/ (WIP)` no LOCAL — resolve ambiguidade
  visual do nó único anterior.
- **`forge raw` (daily-workflow)**: adiciona `rebuild-templates` como 4º
  subcomando (estava omitido).
- **Q11–Q17 labels**: padronizado pra slugs canônicos em inglês entre
  `getting-started.md` (tabela), `daily-workflow.md` (menu) e
  `graph-query-flow.mermaid`.
- **Voz mentor calmo**: `shipada/shipado` → `entregue`; `Fora da caixa`
  → `Por padrão`; `Phase 6` qualificado como `Phase 6 do roadmap
  (docs/design/02-phases.md)`.
- **`CLAUDE.md` raiz**: counts em §Anatomia rápida e §Comandos úteis
  alinhados à ground truth.

### Changed (User-facing docs, 2026-06-12)

- **`README.md`** — Adicionada seção "Quick Start" com instalação e first steps + tabela "Guias do usuário" com links para os 4 guias.
- **`docs/design/08-session-handoff.md`** — Última atualização e seção de User-facing docs registrada.

### Fixed (master review PR #15 remediation — 2026-06-15)

Aplica todos os 22 findings do master review PR #15 (14 do Group A —
security/correctness + 8 do Group B — broad-except scrub + validators).
Test baseline 1350 → 1353 (3 testes novos de A-013 cobrindo o vetor de
path-traversal do guard de undo).

**Alto (A-001, A-002, A-003, B-001):**
- **A-001** (`engine/undo.py`) — `_delete_feature_artifacts_guard` agora
  rejeita também `target_resolved == project_resolved`. Sem isso, um slug
  malicioso `../../..` resolveria pra raiz e `shutil.rmtree` apagaria o
  projeto inteiro após os 2 confirms (`Path.relative_to` retorna
  `Path('.')` em equality, sem `ValueError`).
- **A-002** (`engine/undo.py`) — `_delete_feature_artifacts` agora usa
  `feature_path(..., subtype=current_subtype(...))` em vez de `feature_dir`,
  honrando o subtype enum. Features non-product (refactor/spike/chore/
  bugfix) — que vivem em `non-product/{slug}/` — voltam a ser delete-able
  via `forge undo`.
- **A-003** (`docs/design/04-pending.md`) — entrada H-02/MD-01 reforçada
  com referência explícita a A-003 e detalhamento do vetor YAML anchor
  bomb (`yaml.safe_load` sem flag nativa pra limitar aliases).
- **B-001** (`engine/status.py`) — `_render_recent_activity` agora pega
  `(MemoryError, OSError, UnicodeDecodeError)` em vez de
  `(JSONDecodeError, OSError, UnicodeDecodeError)`. `read_history` empacota
  `JSONDecodeError` em `MemoryError`, então a tupla antiga era no-op e
  JSONL corrompido crashava o status render.

**Médio (A-004, A-005, A-006, B-002, B-003):**
- **A-004** (`validators/check_secrets.py`) — detecção de colisão no
  `_rel_map` quando dois staged paths viram a mesma relativização (caso
  de projetos com symlinks). Modo conservador filtra com paths originais
  em vez de descartar silenciosamente.
- **A-005** (`validators/check_secrets.py`) — fail-loud em regex inválida
  na config `secrets-gate.ignore-paths` via `_collect_invalid_patterns` +
  `result_warn`. Antes era skip silencioso.
- **A-006** (`engine/utils/paths.py`, `engine/plan.py`) — promovido
  `_resolve_features_root` de plan.py pra paths.py (leaf real, sem dep
  de `engine.plan`). Elimina lazy import circular dentro de `feature_path`.
  Shim retrocompatível em plan.py.
- **B-002** (`engine/doctor.py`) — adiciona `CardError` à tupla de except
  em `_check_card_snapshots` + import. Race condition no
  `compute_directory_sha256` agora vira `_STATUS_FAIL` por categoria
  em vez de explodir o doctor inteiro.
- **B-003** (`engine/doctor.py`) — troca `(YamlIOError, OSError)` por
  `(yaml.YAMLError, OSError)` em `_stamp_last_doctor_run` + import yaml.
  `write_yaml` NÃO levanta `YamlIOError` (só `read_yaml` levanta) — o
  tipo real era `YAMLError` de `safe_dump`, que escapava silenciosamente.

**Baixo (A-007, A-008, A-009, A-010, B-004, B-005, B-008):**
- **A-007** (`engine/graph/builder.py`) — comment estendido do `finally`
  pra cobrir `ValueError` do guard de allowlist (sem mudança funcional).
- **A-008** (`engine/implement.py` + test) — `_topo_sort` troca
  `raise SystemExit` por nova `TaskGraphError(RuntimeError)`. SystemExit
  é `BaseException` e não era pego por `except Exception` de chamadores
  defensivos. CLI `run()` mapeia para exit code 1.
- **A-009** (`engine/verify.py`) — `run_scope` agora retorna `1` quando
  `project_root` não é diretório, espelhando o guard de `_run_validator`.
- **A-010** (`engine/persona/mentor_calmo.py`) — docstring de `set_seed`
  documenta thread-safety explicitamente.
- **B-004** (`engine/graph/builder.py`) — comments por-tipo justificando
  cada exception da tupla em `_populate_ds_components_from_inventory`.
- **B-005** (`validators/validate_workflow_config.py`) — comment
  justificando exaustividade do `OSError` em torno de `file_sha256`.
- **B-008** (`validators/validate_feature_package.py`) — `_check_cross_refs`
  reporta parse error como warn em vez de silenciar.

**Sugestão (A-011, A-012, A-013, A-014, B-006, B-007):**
- **A-011** (`engine/undo.py`) — narrow do broad-except em
  `_append_undo_log` pra `(OSError, ValueError)`, com aviso ao usuário.
- **A-012** (`engine/undo.py`) — narrow do broad-except em `_undo_evolve`
  pra `(KeyError, OSError, YamlIOError, MemoryError)`.
- **A-013** (`tests/engine/test_undo_delete_traversal.py`) — adiciona 3
  testes (target == project_root, symlink escaping project, slug literal
  `../../..`), cobrindo o vetor de A-001.
- **A-014** (`validators/check_no_invented_behavior.py`) — comment
  explícito + `noqa: E402` cobrindo `sys.path.insert` antes dos imports
  de `engine.`.
- **B-006** (`docs/design/04-pending.md`) — nota retrospectiva sobre
  scope hygiene do M-02 (parcialmente endereçado por A-008).
- **B-007** (`tests/unit/test_commands_{implement,plan,verify}.py`) —
  pin exit code in `{1, 2}` em vez de `!= 0` amplo.

### Fixed (master review remediation — final review, 2026-06-15)

- **Master review H-1** — Fix `engine/doctor.py:1308-1309` `_` redefinition
  (mypy no-redef): renomeou segundo binding para `_safe_read_yaml_ref` +
  corrigiu noqa code.
- **Master review M-1** — Atualizou `engine/graph/builder.py` para usar
  `GitIgnoreSpecPattern` (de `pathspec.patterns.gitignore.spec`) no lugar
  de `GitWildMatchPattern` (deprecated). Elimina ~1500 DeprecationWarnings
  em test runs.
- **Master review M-3** — Consolidou 3 cópias adicionais de `_utc_now_iso`
  em `engine/memory/{l1,l2,distiller}.py` para import direto de
  `engine.utils.iso.utc_now_iso`. Fecha LO-01 parcialmente (7 módulos
  restantes documentados em `04-pending.md`).
- **Master review L-1** — Atualizado campo `**Última atualização:**` do
  handoff para 2026-06-15 (refletindo final review remediation).

### Fixed (REVIEW.md remediation — Bloco 5: medium/low polish, 2026-06-12)

- **M-01** — Substituído over-mock em `tests/unit/test_commands_*.py`
  por assertions sobre exit code real.
- **M-05** — Removido `import json` interno em `_readiness_from_handoff`
  (side-effect Task 4.1 / H-03 narrow).
- **L-01 + L-04** — Removido parâmetro `project_root` dead em
  `_print_blocked_refusal` (`engine/implement.py`).
- **L-03** — Consolidado `_utc_now_iso_implement/_plan/_verify` em
  import direto de `engine.utils.iso.utc_now_iso` em `engine/implement.py`,
  `engine/plan.py`, `engine/verify.py` (5 shims, 12 callers). Shims
  similares em outros módulos (`engine/undo.py`, `engine/evolve.py`,
  `engine/reconfigure.py`, `engine/memory_cli.py`, `engine/graph_cli.py`,
  `engine/init.py`, `engine/doctor.py`) ficam fora de scope desta entrega
  — gap registrado em `04-pending.md` (LO-01 follow-up).
- **L-06** — `sys.path.insert` em `tests/conftest.py` mantido com
  comment justificando + gap aberto em `04-pending.md` pra revisitar
  quando CI pipeline oficial vier.
- **L-07** — Marker `meobonsai` registrado em `pyproject.toml`; 11 tests
  dependentes da fixture `meobonsai_root` agora carregam o marker.

### Added (REVIEW.md remediation — Bloco 3: mypy advisory, 2026-06-12)

- **H-09** — `mypy >= 1.8` adicionado em `[project.optional-dependencies]
  dev` + seção `[tool.mypy]` em advisory mode. Baseline de 17 errors
  registrado em `docs/design/04-pending.md`. CI gate não ativo nesta
  sessão (rollout incremental planejado).

### Changed (REVIEW.md remediation — Bloco 3: mypy advisory, 2026-06-12)

- **M-10** — Removido import unused `Optional` em `engine/implement.py`,
  `engine/verify.py`, `engine/status.py`, `engine/vision/screenshot.py`.
  19 usos remanescentes padronizados pra `X | None` intra-arquivo.

### Changed (REVIEW.md remediation — Bloco 2: functional bugs, 2026-06-12)

- **M-07 (dep nova)** — Adicionado `pathspec >= 0.12` em
  `[project.dependencies]` runtime. Lib pura Python implementando
  `.gitignore` semantics canonicas. Decision 19 (Python stack) e
  Decision 22 (no skill runtime deps) não afetadas — pathspec é PyPI
  lib genérica.

### Fixed (REVIEW.md remediation — Bloco 4: broad-except scrub, 2026-06-12)

- **H-03** — Narrow `except Exception` em 24 sites críticos:
  - `engine/implement.py`: 1 site (JSON read) narrowed; 3 sites preservados broad
    com `# noqa: BLE001` em validator/QA dispatch boundaries
  - `engine/verify.py`: 2 sites narrowed `(MemoryError, OSError)` em
    L1 status write/restore
  - `engine/graph/builder.py`: 1 site narrowed em inventory load
  - `engine/init.py`: 2 narrowed (overlay, FS copy) + 4 preservados em
    discovery-step heuristic scanners
  - `engine/status.py`: 1 site narrowed (L1 history JSON read)
  - `engine/doctor.py`: 2 sites narrowed (stamp write + category snapshot)
  - `validators/validate_*.py`: 18 sites narrowed em 10 validators
    (YAML reads + 1 file_sha256), `YamlIOError` adicionado aos imports

### Fixed (REVIEW.md remediation — Bloco 1: security quick wins, 2026-06-12)

- **H-01** — SQL allowlist em `_reset_domain_tables` previne wipe de tabela
  fora do conjunto canônico (`engine/graph/builder.py`).
- **H-02** — Cap de 10MB em `read_yaml` evita YAML bomb / anchor explosion
  (`engine/utils/yaml_io.py`).
- **H-04** — PRAGMA `foreign_keys = ON` em `finally` tolera erro de SQLite
  sem mascarar a exception original (`engine/graph/builder.py`).
- **H-06** — Path-traversal guard em `forge undo` delete-feature recusa
  rmtree fora do project_root (`engine/undo.py`).
- **H-07** — RNG de `mentor_calmo` isolado por call quando seed unset;
  contrato determinístico de tests preservado (`engine/persona/mentor_calmo.py`).
- **H-10 (parcial)** — Validação `project_root.is_dir()` antes do
  subprocess de validators retorna `degraded` em vez de crashar
  (`engine/verify.py`). Batch git-diff optimization fica deferred — ver
  `docs/design/04-pending.md`.
- **M-02** — Unknown task dep agora levanta `SystemExit` em
  `_topo_sort` em vez de tratar silenciosamente como satisfeita
  (`engine/implement.py`).
- **M-04** — `feature_path` consolidado em `engine/utils/paths.py`;
  `implement.py` agora encontra non-product features (refactor/spike/chore).
- **M-07 + M-08** — `pathspec` substitui parser custom de `.gitignore`;
  bracket classes, escapes, trailing space e `a/**/b` agora cobertos
  corretamente (`engine/graph/builder.py`).
- **M-09** — `validators/check_no_invented_behavior.py` reusa
  `git_staged_files` de `validators/_diff.py` (rename detection -M80%
  agora disponível).
- **M-12** — Ignore patterns em `check_secrets` âncoram em `^` —
  `src/tests/fixtures/secrets/...` não é mais false-positive ignored.

### Added (Phase B — DET-6 multi-axis backend, 2026-06-11)

- **Schema canônico multi-axis** — `docs/schemas/backend-axes.md` define
  8 axes (`data`, `auth`, `observability`, `analytics`, `storage`,
  `persistence`, `notifications`, `flags`) cada um produzindo
  `Map[axis][platform] → Cell | null`. Cell shape: `{card, status,
  migrating-to?}`. Validação enforçada via RULE-019..024 em
  `validate_workflow_config.py`. Refs: commits `c60eeb1` + `26c0822`
  (W1 foundation) + waves W5-W7 que consomem o schema.
- **6 cards novos** cobrindo 3 axes novos: `firebase-analytics`,
  `posthog-analytics` (axis analytics); `fcm`, `onesignal` (axis
  notifications); `firebase-remote-config`, `posthog-flags` (axis flags).
  Cada card com `card.yaml` + `detection/signals.yaml` + README +
  template stub. Refs: W4.1-W4.6.
- **Card sqldelight** — KMP-native persistence axis pra kmp platform.
  Pareia com `room-database` (android-only). Fecha gap W6 onde
  `firebase-full.yaml` referenciava card ainda inexistente.
- **4 starter bundles** em `presets/kmp-mobile/bundles/`:
  `firebase-full`, `rest-with-firebase-telemetry`, `local-only`, +
  sentinela `custom-from-scratch` (sem YAML — pula bundle, prompta cada
  axis). Substituem o bloco `backend-candidates:` monolítico.
- **Detection composer** — `engine/detection/composer.py` com
  `compose_backend_axes(project_root, active_cards) ->
  dict[axis][platform] -> Cell | Conflict | None`. Reusa
  `_eval_detection_signals` + `_eval_gradle_dep` de `engine/init.py`.
  Conflict.candidates ordenado determinísticamente por card_id. Refs:
  W5.1 + W5.2 + W5-fix.
- **AskUserQuestion-fronted init flow** (consumer da Phase A intent
  protocol):
  - `_handle_backend_multi_axis_brownfield` (`engine/init.py`):
    composer-driven, 3-caminhos confirm/adjust/scratch.
  - `_handle_backend_multi_axis_greenfield` (`engine/init.py`): bundle
    picker (4 opções) → opt override → per-axis prompts.
  - `_handle_backend_axes_submenu` (`engine/reconfigure.py`): tabela
    current 8 axes × N platforms, multiSelect cells, per-cell prompts
    (null/card/status/migrating-to) com validation enforçada.
- **Validator novo** — `validate_presets.py` cobre schema dos bundle
  YAMLs (axes válidos, platforms válidos, card references existentes).
  16 tests TDD. Refs: W6.3.
- **3 adapters em init.py** — `_composer_result_to_cells`,
  `_bundle_to_cells`, `_summarize_backend_cells` convertem handler
  returns pra workflow-config cell structure. Refs: W7.1+W7.2.

### Changed (Phase B — DET-6, 2026-06-11)

- **identity.category cleanup** — 9 cards migrados de `category: backend`
  ou `category: network` pros 8 axes canônicos. `firebase-auth` →
  `auth`; `auth-jwt-bearer` → `auth`; `firebase-storage` → `storage`;
  `firestore-persistence` → `data`; `firestore-realtime` → `data` (sub-
  axis "realtime" follow-up); `firestore-security-rules` → `data`
  (sub-axis "rules" follow-up); `rest-api-contract` → `data` (sub-axis
  "data-contract" follow-up); `retrofit-client` → `data`; `ktor-client`
  → `data`. CARD-004 enum em `engine/cards/loader.py` ampliado.
  Refs: W2.
- **Label refactor** — labels singulares `auth-provider`, `http-client`,
  `crash-reporting` removidos de `cards/*/card.yaml § provides`.
  Cardinalidade enforçada pelo cell shape (1 card per cell). Refs: W3.
- **Card rename** — `cards/crashlytics/` → `cards/firebase-crashlytics/`
  (paridade com `firebase-auth`, `firebase-analytics`, etc.). 25
  arquivos atualizados (incluindo 12 consumers cross-card via grep
  canary). YAML field name `crashlytics:` em contratos analytics
  mantém-se (concept independente).
- **`docs/schemas/card.md`** — CARD-004 enum revisado: `+ analytics`,
  `+ notifications`, `+ flags`; `- backend`, `- network` (granularidade
  backend-axes substitui o blob monolítico). Novo campo opcional
  `identity.platforms` + CARD-022 (platforms enum dentro do conjunto
  canônico; ID alocado pós-rebase contra `main` que já consumia
  CARD-020/021 pra DET-3). Adicionada seção "Backend axes — when
  identity.category is an axis" cross-referenciando `backend-axes.md`.
  Open-detail anchors preservados.
- **`docs/schemas/workflow-config.md`** — bloco `backend:` reescrito
  para shape multi-axis `backend.<axis>.<platform>` → cell|null.
  Removidos `identity.backend-choice` (legacy single-pick) e
  `backend.provider` string monolítico + sub-blocos provider-específicos.
  Slots RULE-010 e RULE-011 ficam reservados como audit-trail dos
  campos legacy + cross-ref pra RULE-019..024 (autoridade em
  `backend-axes.md`); sub-IDs alfanuméricos eliminados. Top-level
  table sincronizada.
- **CARD-022 renumber** — schema rule pra `identity.platforms` (W1)
  realocada de CARD-020 pra CARD-022 devido à colisão com DET-3
  (CARD-020/021 já alocados pra gradle-dep). Audit-trail em
  `docs/schemas/card.md`.

### Removed (Phase B — DET-6, 2026-06-11)

- `backend-candidates:` bloco completo em `presets/kmp-mobile/preset.yaml`
  (substituído por `bundles-dir` + `bundle-options` sentinela). Refs:
  W6.2.
- `identity.backend-choice` field em workflow-config.yaml. ConfiguratorCheckpoint
  `backend_choice` field idem. 15 referências removidas de
  `engine/init.py`. Refs: W7.4.
- `_build_backend` function legacy em `engine/init.py` (mapeava
  `backend_choice → backend.provider` enum). Substituída por adapters.
  Refs: W7.4.
- `_handle_backend` legacy em `engine/reconfigure.py` (handler antigo do
  submenu backend). Substituído por `_handle_backend_axes_submenu`.
  Refs: W7.3.
- Labels singulares `auth-provider`, `http-client`, `crash-reporting`
  de `provides`. Cardinalidade enforçada pelo schema. Refs: W3.

### Added (Phase B — DET-6 polish, 2026-06-12)

- **Test discipline gap fechado** — `tests/unit/test_validators_workflow_config.py`
  ganhou 8 tests positive/negative individuais cobrindo RULE-019..024
  (axis enum, platform check, card.card existence, status enum,
  migrating-to consistency, migrating-to card existence). Closes M-003
  do W7 cluster review.
- **Validator agora aceita local cards** — `validate_workflow_config.py`
  RULE-021 e RULE-024 reconhecem `.claude/cards/local/<name>/card.yaml`
  além do snapshot dir canônico. Alinha com behavior do reconfigure
  (Caminho B do M-001 W7 cluster review).
- **E2E coverage forge init/reconfigure** — 3 e2e tests novos
  (`test_e2e_brownfield_init.py`, `test_e2e_greenfield_init.py`,
  `test_e2e_reconfigure_backend.py`) substituem stubs pre-W7. Helpers
  compartilhados em `tests/e2e/conftest.py` (`_scaffold_minimal_project`,
  `_run_forge`, `_drive_intent_loop`). Cobertura AC-6/AC-7/AC-8 end-to-end
  no CLI level via subprocess + file-based intent protocol.
- **Consumed-intent log (Phase A protocol)** — `engine/ui/intent_state.py`
  ganhou `_log_path` + `_read_intent_log` + `_append_intent_log`.
  `read_response` agora checa log primeiro pra cached response do
  intent-id; faz handler re-entry idempotente entre subprocess
  invocations (resolve W7.2 multi-intent re-invocation pitfall).
  Schema documentado em `docs/schemas/intent-protocol.md §4`.

### Changed (Phase B — DET-6 polish, 2026-06-12)

- **`_SKIP_DIRS` semântica** — `engine/inventory/_walk_cache.py` +
  `engine/init.py` agora comparam `path.relative_to(project_root).parts`
  em vez de `path.parts` absoluto. Top-level `.claude/` continua
  filtrado em project_root; `.claude/` como PARENT do project_root
  (caso worktree) deixa de filtrar descendentes. Regression test em
  `tests/unit/test__walk_cache_worktree.py`.
- **`clear_intent_files` ganhou parâmetro `also_log`** — default `False`
  preserva log (re-entry idempotency). Caller terminal (engine/cli.py
  exit lifecycle) passa `also_log=True` para reset. SPEC §3 forensic
  preservation preservada via função separada `clear_intent_log_only`.
- **Microcopy stale removido** — `engine/init.py` gate RESOLVER-ERRORS
  label "voltar e escolher outro backend-candidate" → "voltar e ajustar
  a configuração de backend (composer/bundle)". Module docstring linhas
  1-15 atualizada pra refletir composer-driven flow (W7.4) em vez de
  legacy backend-candidate picker (Cena 6.5).
- **Test fixture categoria stale** — `tests/integration/test_e2e_local_card_pilot.py`
  linha 80 `category: "network"` → `category: "data"` (alinhamento tardio
  com DET-6 W2 migration de cards/network → cards/data).

### Fixed (Phase B — DET-6 polish, 2026-06-12)

- **W7 cluster review findings** — 1 High (stale microcopy) + 4 Medium
  (cross-validator asymmetry, type guard inconsistency, test discipline
  gap, module docstring stale) + 3 Low (comment stale, uniform-detection
  consolidation deferida, crashlytics filenames anotados). Detalhe em
  `.planning/det-6/W7-cluster-review-r1.md`.
- **`_SKIP_DIRS` worktree bug** — 2 tests que falhavam do worktree
  agora passam (`test_eval_gradle_dep::test_ac6_file_content_preserved`
  + `test_gradle_dep_card_activation::test_ac6_file_content_signal_still_active_alongside_gradle_dep`).
- **Phase A multi-intent re-invocation pitfall** — handlers que emit
  2+ intents agora sobrevivem subprocess re-invocations sem
  `IntentMismatchError`.
- **DET-6 W2 fixture cleanup tardio** — 2 tests
  (`test_pilot_local_card_added_appears_in_cascade`,
  `test_pilot_local_cards_manifest_written`) verdes pós-categoria fix.

### Changed (PR #13 review Wave B — 2026-06-12)

Refactors cross-module do review de PR #13 (DET-6 multi-axis backend).
Quebram ciclos de import, consolidam constantes duplicadas e
substituem duck-typing por isinstance dispatch:

- **Ciclo composer↔init quebrado** (review #3405252850 + #3405253600 +
  #3405256623) — `_eval_detection_signals` + helpers (`_glob_any`,
  `_eval_gradle_dep`, `_load_toml_catalog`, `_module_matches_coordinate`,
  `_scan_build_gradle_for_coordinate`, `_SKIP_DIRS`) movidos de
  `engine/init.py` para novo `engine/detection/_eval.py` (módulo neutro
  sem deps em init). Composer agora importa de `_eval` em vez de
  `engine.init` — os dois `# noqa: PLC0415` lazy imports em init.py
  removidos. `_normalize_cards_for_composer` mantido (refactor maior
  fora do escopo). 7 arquivos de test ajustados pra novos imports.
- **Shape guard no composer** (review #3405256439) — quando
  `card.detection.signals` não é list, composer agora pula o card com
  `logging.warning` em vez de silenciar via score=0 (que mascarava o
  card mal-formado no card_index).
- **`isinstance` em vez de `hasattr` pra Cell/Conflict** (review
  #3405253823) — 5 sites em init.py
  (`_detect_axis_uniformity`, `_render_axes_table` × 2,
  `_collect_confirm_selection`, `_composer_result_to_cells`) trocam
  duck-typing sobre `cell.candidates` por `isinstance(cell, Conflict)`
  / `isinstance(cell, Cell)`. Contrato explícito vinculado aos types
  importados do composer. Regression test paramétrico cobre os 5
  helpers com instâncias reais.
- **`BACKEND_AXES` shared** (review #3405254057) — tuple de 8 axes
  consolidado em `engine/detection/_axes.py`; init.py e reconfigure.py
  importam de lá. Antes, duas tuplas idênticas
  (`_BACKEND_AXES` em init, `_BACKEND_AXES_RECONFIGURE` em reconfigure)
  documentadas como "deliberate pra evitar ciclo" — ciclo nunca
  existiu, duplicação era defensiva por hábito.
- **`VALID_AXES` / `VALID_PLATFORMS` shared** (review #3405255016) —
  3 constantes consolidadas em `validators/_common.py`:
  `VALID_BACKEND_AXES`, `VALID_BUNDLE_PLATFORM_KEYS`,
  `VALID_PROJECT_PLATFORMS`. Os dois sets antes-homônimos de "platforms"
  agora têm nomes desambiguados (bundle slot keys × workflow active
  platforms — conteúdos semanticamente diferentes). Validators
  preservam aliases locais pra compat de tests/callers.

### Added (PR #13 review Wave B — 2026-06-12)

- **`engine/detection/_eval.py`** — módulo neutro pra signal evaluation.
- **`engine/detection/_axes.py`** — fonte canônica de `BACKEND_AXES`.
- **Cache `_log_cache` em `engine/ui/intent_state.py`** (review
  #3405256063) — process-level cache evita re-parse O(n) do JSONL em
  multi-intent handlers. `_append_intent_log` atualiza incrementalmente;
  `clear_intent_files(also_log=True)` + `clear_intent_log_only`
  invalidam pareado com delete on-disk. `_reset_log_cache` exposto como
  escape hatch pra testes.
- **`tests/unit/test_init_isinstance_cell_conflict.py`** — 9 regression
  tests cobrindo isinstance dispatch nos 5 sites afetados.
- **`tests/unit/test_intent_state_log_cache.py`** — 6 regression tests
  cobrindo cache hit, append incremental, invalidations, reset, mutation
  protection.

Rapid lane pós-Wave B: 1321 passed (+15 vs Wave A baseline 1306) / 11
skipped / 6 failures pré-existentes herdadas (cards_resolver_w3 × 4,
test_run_empty_args, test_no_cards_returns_pass_or_warn — não tocadas
nesta wave).

### Fixed (PR #13 review Wave A — 2026-06-12)

Remediação dos 7 fixes contidos do review de PR #13 (DET-6 multi-axis
backend). Single-file, baixo risco, sem cross-cutting:

- **`engine/cli.py` exit-cleanup refactor + observability** — substitui
  flag mutável `clear_log_on_exit` por sentinela `paused_exc:
  PausedForInputError | None` (review #3405256255); substitui bare
  `except Exception: pass` por logged best-effort no stderr (review
  #3405253379 + #3404131724). Mesma semântica, observabilidade ganhada.
- **`engine/ui/intent_state.py::_append_intent_log`** — adiciona
  `f.flush()` explícito após write pra honrar a docstring "JSONL append
  + flush is the durability contract" (review #3405254528). Regression
  test spies em `Path.open` confirma flush precede close.
- **`validators/validate_presets.py`** — unifica imports em
  `from validators._common`, remove o dual-branch `if __package__`
  hack (review #3405254868). Script mode + package mode ambos
  preservados via insert idempotente do project root em `sys.path`.
- **`validators/validate_workflow_config.py` RULE-020 cascade guard** —
  quando `platforms.active` está ausente/vazia/malformada, emite uma
  única mensagem de guidance em vez de cascatear 1 violação RULE-020
  por cell (review #3405255318). RULE-021..024 seguem rodando no
  mesmo pass. Regression test garante "platform desconhecida" não
  vaza no what-failed.
- **`docs/design/04-pending.md`** — anota gap RULE-023/024 ciclo
  `migrating-to` (review #3405255904) — detecção DFS 2-hop deferida
  pra hardening dedicated; feature menor, baixo impacto runtime.

### Changed (PR #13 review Wave A — 2026-06-12)

- **`tests/unit/test_ui_intent_state.py`** — +1 regression test
  (`test_append_intent_log_flushes_after_write`).
- **`tests/unit/test_validators_workflow_config.py`** — +1 regression
  test (`test_empty_platforms_active_emits_single_guidance_not_cascade`).

Fix 4 do review (delegação `clear_intent_log_only` →
`clear_intent_files(also_log=True)`) skipped: as semânticas divergem —
`clear_intent_log_only` preserva pending/response (SPEC §3 forensic),
`clear_intent_files(also_log=True)` apaga os três. Delegar mudaria
behavior do finally em `cli.py`. Anotado pra triage Wave B caso o
cleanup seja revisitado.

### Fixed (PR #11 master-review remediação — 2026-06-11)

Remediação completa dos 28 findings do master-review de PR #11
(`/tmp/master-review-pr-11-drift1-REVIEW.md`) em 10 commits sobre o
W6 doc-sync (`e992e01`). Cobertura: 3 Críticos + 7 Altos + 10 Médios +
5 Baixos + 3 Sugestões — todos endereçados em Wave 1 + Wave 2. Rapid
lane: 1199 passed / 11 skipped (sobe de 1151 → 1199 com +32 testes
novos cobrindo race-detection threading, schema-version mismatch,
EOFError no tty_bridge, dir fsync, chmod 0600, intent-id stability sob
mesmo prompt em comandos distintos, etc.).

Crítico:

- **#1** (`engine/cli.py main()`) — captura `RaceDetectedError`,
  `IntentMismatchError` e `JsonIOError` antes do exit 1. Mensagem
  mentor-calmo de `RaceDetectedError` agora chega ao usuário em vez de
  vazar como traceback (SPEC §3/§9). Commit `ad49c40`.
- **#2** (`engine/ui/question.py`) — `_stable_intent_id` agora inclui
  `command` + `command-args` no payload do hash. Dois `ask()`
  textualmente idênticos em comandos distintos não colidem mais. Combina
  com fix #11 (paths-detail) e #18 (confirm signature). Commit `2c49d0f`.
- **#3** (`bin/forge`) — implementa `FORGE_FORCE_TTY_MODE` (paridade com
  CHANGELOG/SPEC §7). Drift CHANGELOG↔impl fechado. Commit `cd6d616`.

Alto:

- **#4** (`engine/ui/intent_state.py`) — `read_response` valida
  `schema-version == 1` antes do intent-id check; nova exceção
  `SchemaVersionMismatchError` raise quando diverge. Future v2 deixa de
  consumir v1 silenciosamente. Commit `8eeff89`.
- **#5** (`engine/utils/checkpoint_io.py` + `engine/utils/iso.py` novos)
  — helper compartilhado consolida 30 funções (`_save_*_checkpoint`,
  `_load_*_checkpoint`, `_clear_*_checkpoint` × 10 module handlers) +
  10 cópias de `_utc_now_iso_<module>`. Shim de 1-linha por módulo
  preserva API pública dos tests; alvo de remoção registrado em
  FU-DRIFT-1-CHECKPOINT-CONSOLIDATE. Fecha Mandamento #3. Commit
  `916a062`.
- **#6** (`engine/ui/tty_bridge.py`) — `_prompt_user_via_stdin` captura
  `EOFError` (Ctrl+D, pipe quebrado) e roteia para mesmo path de cancel
  do `KeyboardInterrupt` (exit 130). Commit `6a00e1e`.
- **#7** (`engine/utils/json_io.py`) — `write_json` aplica
  `os.chmod(path, 0o600)` após `os.replace`. Pending/response files
  deixam de ser world-readable em sistemas POSIX multi-tenant. Commit
  `7d965c6`.
- **#8** (`engine/ui/question.py`) — `_stable_intent_id` promovida a
  `stable_intent_id` (símbolo público) com alias deprecated preservando
  os 13 callsites de produção sem breakage. Alvo de remoção em
  FU-DRIFT-1-DEPRECATE-INTENT-ID-ALIAS. Commit `916a062`.
- **#9** (concurrency coverage) — teste threading (5 workers via
  `threading.Barrier`) em `tests/integration/test_intent_state_concurrency.py`
  documenta TOCTOU window declarada no SPEC §9 e valida que pelo menos
  4 dos 5 saem com erro determinístico. Lock real via `fcntl.flock`
  registrado em FU-DRIFT-1-LOCK. Commit `626a4f0`.
- **#10** (`engine/utils/json_io.py`) — dir fsync POSIX após
  `os.replace` (open `path.parent` com `O_RDONLY` + `os.fsync`, skip em
  Windows). Atomic rename agora resiste a power-loss real. Commit
  `7d965c6`.

Médio:

- **#11** (`engine/ui/question.py`) — `paths-detail` entra no `extra`
  mapping do `_stable_intent_id` (ask_three_paths). Dois prompts com
  mesmo gate_name + labels mas motives diferentes não trocam mais
  responses. Commit `2c49d0f`.
- **#12** (`engine/ui/question.py`) — `_command_context()` normaliza
  fallback: quando `head` matches `r'.*\.py$'` ou `__main__`, retorna
  `("unknown", [])` em vez de "cli.py"/"__main__.py" como nome de
  comando. Commit `2c49d0f`.
- **#13** (`engine/ui/tty_bridge.py`) — `_build_response_value` para
  `kind=confirm` faz re-prompt loop (até 3 tentativas) em tokens
  inválidos antes de propagar erro. Usuário que digita "talvez"
  recebe orientação clara em vez de exit 1 críptico. Commit `6a00e1e`.
- **#14** (`engine/ui/tty_bridge.py`) — env var dead `FORGE_INTERNAL_TTY_BRIDGE`
  removida do subprocess env. Observability channel registrado em
  FU-DRIFT-1-OBS pra emergir quando log infrastructure aparecer. Commit
  `6a00e1e`.
- **#15** (SPEC + plan) — search-replace `CLAUDE_CODE_HOST` →
  `CLAUDECODE` em `docs/superpowers/specs/drift-1-intent-protocol.md`
  + `docs/superpowers/plans/drift-1-intent-protocol.md` com nota de
  rodapé "renomeado em W4-FU após verificação empírica vs Claude Code
  2.1.153". Commit `d999ced`.
- **#16** (`docs/schemas/intent-protocol.md`) — nova seção
  `## Schema evolution policy` explicita (a) bump em breaking; (b)
  reader rejeita versões desconhecidas; (c) engine + host co-bumpam;
  (d) sem v0. Commit `d999ced`.
- **#17** (`engine/ui/intent_state.py`) — `_parse_created_at` /
  `detect_race` toleram clock skew até 60s. Negative `age_seconds` >
  60s (clock inválido) trata como stale → sweep; <=60s trata como
  recém-criado. Commit `8eeff89`.
- **#18** (SPEC + question.py) — exemplo de `confirm` no SPEC §2.1
  passa a `allow-pause: true` alinhando com impl real;
  `tests/unit/test_ui_question_api_signatures.py` ganha regression test
  travando a signature pra evitar drift futuro. Commits `d999ced` +
  `2c49d0f`.
- **#19** (concurrency test) — implementado em commit `626a4f0` (ver
  finding #9 acima). Cobre o gap declarado no SPEC §9.
- **#20** (`docs/design/06-command-surface.md`) — seção Exit codes ganha
  nota explícita distinguindo as 2 rotas pra 130: (a) `KeyboardInterrupt`
  em TTY mode; (b) host response `cancelled: true` em intent mode.
  Caller pode tratar identicamente. Commit `d999ced`.

Baixo:

- **#21** — `_utc_now_iso_*` consolidado em `engine.utils.iso.utc_now_iso`
  (10 cópias → 1 helper canônico). Commit `916a062`. Nota: `engine/verify.py`
  mantém `_utc_now_iso` local com microseconds (semantically distinto
  do shared helper que trunca pra seconds) — migração registrada em
  FU-DRIFT-1-VERIFY-ISO.
- **#22** (`engine/ui/intent_state.py`) — `RaceDetectedError` ganha
  bloco 3-caminhos canônico (Mandamento #5 + Discipline §1): (a)
  aguarda outro processo; (b) `rm .claude/state/forge-pending.json` se
  sessão anterior travou; (c) `forge undo` se conflito de feature
  paralela. Combina com fix #1 (mensagem agora chega ao usuário).
  Commit `8eeff89`.
- **#23** (`engine/ui/question.py`) — stub `_read_line` que raise
  `NotImplementedError` removido. Substituído por comentário apontando
  pra `engine.ui.tty_bridge` como home canônica de stdin reading.
  Commit `2c49d0f`.
- **#24** (`tests/integration/test_intent_protocol_e2e.py`) —
  `test_race_detection_rejects_stale_concurrent` usa stale_id literal
  determinístico (`"deadbeef-0000-0000-0000-000000000000"`) em vez de
  `uuid.uuid4()`. Assertion adicional confirma que difere do engine
  determinístico. Commit `626a4f0`.
- **#25** (`tests/e2e/test_tty_bridge_e2e.py`) —
  `pytest.skip(allow_module_level=True)` no topo quando
  `sys.platform == "win32"`. Evita silently-passing-zero-assertions em
  Windows CI. Commit `626a4f0`.

Sugestão:

- **#26** (`engine/ui/intent_state.py`) — `detect_race` catch genérico
  trocado por `(JsonIOError, OSError)` específicos. Programming errors
  propagam em vez de ficar escondidos. Commit `8eeff89`.
- **#27** (`engine/ui/exit_codes.py` novo) — consolida constantes
  `EXIT_OK=0`, `EXIT_ERROR=1`, `EXIT_PAUSED=2`, `EXIT_CANCELLED=130`
  importadas por `engine/cli.py` e `engine/ui/tty_bridge.py`. Evita
  drift de duplicação local. Commit `3071fe9`.
- **#28** (`bin/forge`) — `FORGE_VERSION` dinâmico via
  `engine.__version__` (custo +20-50ms cold start aceito). Drift do
  hardcoded "1.0.0" fechado. Commit `cd6d616`.

Follow-up pós-master-review (2026-06-11):

- `engine/init.py`: `_load_checkpoint` agora valida `isinstance(data, dict)` e retorna `None` em YAML corrompido. Master-review threads #3396896063 + #3396903793 (`[Critico]`). Alinha com pattern dos 9 outros checkpoint-loaders. (commit `6dd40af`)

### Changed (PR #11 master-review remediação)

- State files (`.claude/state/forge-pending.json`,
  `.claude/state/forge-response.json`) escritos com mode `0o600` por
  default via `engine/utils/json_io.py::write_json`. Hardening de
  permissões aplicado em sistemas POSIX (Windows ignora silenciosamente).
- `engine.ui.question.stable_intent_id` agora é símbolo público; alias
  deprecated `_stable_intent_id = stable_intent_id` preservado pra
  compat dos 13 production callsites + 4 test modules. Remoção
  registrada em FU-DRIFT-1-DEPRECATE-INTENT-ID-ALIAS, target v1.3.


### Added (Phase A — DRIFT-1 intent protocol close, 2026-06-10)

Fechamento da Phase A em 6 commits W3-W6 sobre a base W2 (range total
`1b1d289..50203f3`, 21 commits). Engine deixa de ler stdin diretamente;
intent JSON emitido em `.claude/state/forge-pending.json`, response
consumida de `.claude/state/forge-response.json`, exit code 2 sinaliza
pausa pro host (Claude Code OR `tty_bridge` em fallback). AC-1..AC-9
verificados em integration + e2e pty.

- `engine/ui/tty_bridge.py` (W3.T1) — loop subprocess pra fallback TTY
  fora de contexto Claude Code. Lê pending, prompta no stdin com
  helpers per `kind`, escreve response via `intent_state.write_response`
  e re-invoca o subcomando até exit 0/1/130. Estende
  `engine/ui/intent_state.py` com `read_pending` + `write_response`.
- `bin/forge` dispatcher (W4.T1+W4-FU) — detecta TTY via `[[ -t 0 ]]`
  e contexto Claude Code via env var `CLAUDECODE` (verificado
  empiricamente vs Claude Code 2.1.153). Roteia entre intent mode
  (host loop) e tty_bridge fallback; overrides `FORGE_FORCE_INTENT_MODE`
  / `FORGE_FORCE_TTY_MODE` pra teste. Hooks audit (W4.T2) não exigiu
  patches — invocações existentes continuam funcionando.
- 15 integration tests
  (`tests/integration/test_intent_protocol_e2e.py`,
  `tests/integration/test_callsites_smoke.py`) + 3 e2e pty tests
  (`tests/e2e/test_tty_bridge_e2e.py`) cobrindo AC-1..AC-9 (W5.T1+T3+T4
  + W5.T2). Integration lane: 119 collected. E2E lane: 17 collected.
- Exit code 2 (paused-for-input) documentado em
  `docs/design/06-command-surface.md` (seção `## Exit codes` nova) —
  ladder completa 0/1/2/130 vinculada ao SPEC §4.

### Changed (Phase A — DRIFT-1 close)

- `docs/design/06-command-surface.md` ganha seção `## Exit codes`
  formalizando o contrato 0/1/2/130. Load-bearing edit justificado por
  Mandamento #6 (doc-sync): exit code contract mudou (adicionado 2).
- `.claude/rules/subagent-workflow.md` ganha subseção
  `## Quando subagent invoca \`forge\`` esclarecendo que exit 2 é
  contrato (não erro) e responsabilidade do orquestrador, não do
  subagente sozinho. Load-bearing edit justificado por Mandamento #6
  — protocolo afeta workflow de dispatch.
- README + handoff atualizados pra refletir 21 commits de Phase A na
  branch `feat/drift-1-intent-protocol`. Test count: rapid lane 1151
  passed / 11 skipped preservada (1162 collected pós-W5);
  integration 119; e2e 17; total 1298.

### Added (Phase A W2 — DRIFT-1 intent protocol chokepoint refactor, 2026-06-10)

Phase A W2 entrega o refactor do chokepoint (`engine/ui/question.py`) + integração de checkpoint em todos os 10 subcommands. 15 commits acumulados sobre o foundation W1 (commit `1b1d289`). Outcome C "init-pattern" locked em W2.T0: per-subcommand dataclass + 3 helpers + handler wiring; sem promoção a shared module enquanto pattern não se repetir 3+x.

- Três sentinels exportadas de `engine/ui/question.py`: `PausedForInputError` (intent emitido, host deve sair com exit 2), `UserCancelledError` (response com `cancelled: true` mapeia exit 130 + Ctrl+C path) e `UserPausedError` (alias direcional pra futuro tty_bridge). `PromptAbortedError` legado preservado como re-export pra back-compat.
- 10 per-subcommand checkpoint dataclasses, cada uma com 3 helpers (`_save_*`, `_load_*`, `_clear_*`) + `_*_checkpoint_path` resolver: `_InitCheckpoint`, `_PlanCheckpoint`, `_ImplementCheckpoint`, `_VerifyCheckpoint`, `_ReconfigureCheckpoint`, `_EvolveCheckpoint`, `_UndoCheckpoint`, `_MemoryCliCheckpoint`, `_GraphCliCheckpoint`, `_DoctorCheckpoint`. Cobertura per checkpoint-audit.json: 8 add-new + 2 extend (init e evolve já tinham checkpoints próprios; ganharam campo `intent_id` aditivo).
- 10 novos arquivos de teste em `tests/unit/test_engine_*_resume.py` cobrindo save → exit 2 → re-invoke → consume → resume. Rapid lane: 1046 → 1114 passed (+68 tests; 11 skipped agregam migrações legadas do stdin).
- Campo `paths-detail` no payload de `ask_three_paths` intent — host renderiza o bloco 3-caminhos completo (motive de cada caminho preservado na serialização). Fecha REVIEW CR-003.
- Schema canônico `docs/schemas/intent-protocol.md` atualizado em W2.T1+T2 (paths-detail, hash de validator_hint, contextvar argv).
- `.planning/drift-1/checkpoint-audit.json` (W2.T3a artifact) — classifica os 10 módulos antes da integração + serve de referência pros commits T3b PART A/B/C.

### Changed (Phase A W2 — chokepoint refactor)

- `engine/ui/question.py` migrado de stdin reader pra intent emitter. As 5 funções públicas (`ask`, `ask_three_paths`, `ask_yes_no`, `ask_text`, `ask_number`) preservam API surface bit-a-bit; internamente emitem intent via `intent_state` + `json_io` e levantam sentinel apropriada em vez de bloquear leitura. Hosts não-Claude-Code chamando essas funções recebem exceção em vez de prompt — comportamento documentado no SPEC §1.
- `engine/cli.py::main()` ganhou ramos exit 2 (Paused*) + exit 130 (UserCancelledError) antes do `except KeyboardInterrupt`. Ladder de exit codes documentada em SPEC §4. Argv capturado via contextvar pra re-invocação determinística pelo host.
- `engine/init.py` e `engine/evolve.py` — checkpoints existentes estendidos com campo `intent_id` aditivo (sem quebrar payloads em disco de sessões pré-W2; `intent_id=None` é fallback aceito).
- Forensic preservation honrado: invalid responses (schema fail / value fora de options) NÃO chamam `_clear_state()` antes do raise — state files permanecem em disco como pista pro host (SPEC §3 + REVIEW CR-002 fix).
- SPEC `docs/superpowers/specs/drift-1-intent-protocol.md` §2.1, §4, §5 (tabela final 10/10), §8 e AC-5 atualizados inline ao longo dos 15 commits — fonte de verdade do contrato.

### Added (DET-3 gradle-dep signal type, 2026-06-10)

- Signal type `gradle-dep` em `engine/init.py:_eval_detection_signals` — abstrai presença de coordenada Maven em catálogo `gradle/*.versions.toml` (TOML moderno, formato `module = "<group>:<artifact>"` e `group + name` split) OU em `**/build.gradle*` (legado). Card declara `type: gradle-dep` + `coordinate: <group>:<artifact>`; engine resolve onde procurar. Resolve DET-3 do pilot v1.2-dev 2026-06-10 (scanner cego pra libs.versions.toml). Helper privado `_eval_gradle_dep(project_root, coordinate)` ao lado de `_glob_any`, com curto-circuito no primeiro match e try/except silencioso pra TOML mal-formado. Plan: `docs/superpowers/plans/det-3-gradle-dep-signal.md`.
- Regra de validação CARD-020 em `engine/cards/loader.py` — `detection.signals[*].coordinate` (quando `type=gradle-dep`) deve ser `<group>:<artifact>`, sem versão sufixada, sem espaços. (ID alocado como CARD-020 porque CARD-019 já é usado por `legacy-marker`; SPEC §AC-8 autorizou "CARD-019 ou next free".)

### Changed

- 9 signals em 8 cards canônicos migrados de `file-content` em `**/build.gradle*` pra `gradle-dep` (mesma coordenada, semântica mais ampla cobrindo catálogos modernos): crashlytics, firebase-auth (base + ktx), firebase-storage, firestore-persistence, firestore-realtime, koin-annotations, kotlinx-serialization-json, ktor-client (variante ktor-client-core). Confidence preservada em cada signal — CARD-016 sanity intacta. Audit determinístico em `.planning/det-3/migration-audit.json`.
- Signals em `**/*.kt`, `**/Podfile*`, `**/Package.swift`, e prefixos de família (`androidx.compose`, `androidx.datastore`, `androidx.room`, `navigation3`, `kotlinx-serialization` sem `-json`, `io.ktor:ktor-client` sem suffix, plugin DSL `kotlin("multiplatform")`) preservados como `file-content` per SPEC §Migration policy. Backward compat de `file-content` integralmente mantida.
- `docs/schemas/card.md` §"Signal types" lista `gradle-dep` com schema completo; nota explícita sobre o vapor `dependency` (declared no schema mas nunca implementado no avaliador) — cleanup separado tracked em `04-pending.md`.
- Apresentação (`docs/presentation/feature-forge.html`) atualizada para v1.2-dev: 22 → 24 slides — adicionados slides de subtypes/bugfix e forge qa, slide verify enriquecido com os gates fortes (CC + secrets + no-behavior-change), status e roadmap reescritos (todas as fases shipadas, timeline v1.0→v1.2→autopilot). DESIGN.md sincronizado.

### Documentation

- v1.2-dev pilot 2026-06-10 capturado em `docs/design/04-pending.md` — 6 findings (DRIFT-1 conceitual primário, B1, B2, DET-3, DET-5, DET-6) + sequenciamento Phase 0 → Phase A (DRIFT-1) → Phase B (DET-6) decidido com user. UX/microcopy/persona findings do modo fallback CLI deferred até Phase A (engine emite intent estruturado pra Claude Code → strings deixam de ser responsabilidade do Python).
- DET-3 (Phase 0) marcado ✅ resolvido em `04-pending.md`. Follow-ups não-bloqueantes registrados na mesma página: (1) cleanup do vapor `dependency`, (2) `signals.yaml` schema-version bump nos cards migrados.

### Changed (load-bearing)

- Revisita decisão 30: sandbox isolation guard via sitecustomize.py (não PYTHONSTARTUP) — texto da Decisão atualizado pra refletir mecanismo real implementado em engine/qa/sandbox.py. Comportamento de isolamento idêntico; só o mecanismo nomeado mudou.

### Fixed

- Tighten CARD-020 whitespace validation to reject tab/newline in gradle-dep coordinate (M-001 from DET-3 code review; commit 475f695).

### Fixed (PR #11 master-review remediação — DET-3, 2026-06-10)

Wave 1+2 cobrindo 9 findings do master-review do PR #11 sobre o signal type `gradle-dep` (DET-3 / Phase 0). Severities variam de Alto (2) a Baixo (4); todos endereçados em 7 commits atômicos antes do merge.

- **A-1 [alto] — ktor-client primary signal migrado** — `cards/ktor-client/{card.yaml,detection/signals.yaml}`: signal primário (confidence 0.5) migrou de `file-content` substring família (`io.ktor:ktor-client`) para `gradle-dep` exato `io.ktor:ktor-client-core`. SPEC §AC-1 ("fixture TOML-only → ktor-client retorna auto-activate") agora é exercido na realidade do card, não apenas pelo helper isolado. Commit `7847e5a`.
- **A-2 [alto] — integration test cobre cards reais** — `tests/integration/test_gradle_dep_card_activation.py` (novo): carrega `cards/ktor-client/card.yaml` real e roda detection contra as 5 fixtures (`gradle-dep-{toml-only,toml-split,legacy,hybrid,negative}`), assertando score vs threshold. Sem este teste, A-1 cria falsa segurança permanente. Commit `a7d0947`.
- **M-2 [médio] — CARD-021 rejeita `type: dependency`** — `engine/cards/loader.py` ganha CARD-021 que rejeita o tipo descontinuado no load time, em vez de silenciosamente ignorá-lo. Tabela canônica de Signal types em `docs/schemas/card.md` purga `dependency` da listagem ativa e move para sub-seção "Tipos descontinuados" com referência ao sucessor (`gradle-dep`). Commit `3e4cc65`.
- **M-3 [médio] — branch defensivo morto removido** — `engine/init.py`: removido `if tomllib is not None:` que contradizia o invariante `requires-python >=3.11` (tomllib é stdlib desde 3.11). Captura FU-4 (cosmética post-review). Commits `2e13e3a` + `680a59b`.
- **M-4 [médio] — `forge doctor` warn pra catálogo fora de `gradle/`** — `engine/doctor.py` ganha check que avisa quando `**/libs.versions.toml` existe fora de `<root>/gradle/` (composite builds, `buildSrc/`). Scope preservado conforme SPEC §Non-Goals; warning ajuda diagnóstico sem expandir scanner. Commit `b2749dc`.
- **M-5 [médio] — comments filtrados em build.gradle** — `engine/init.py`: substring match no fallback build.gradle agora strippa comments Groovy/KTS (`//` line-comments + `/* */` block-comments) antes do match. Falso-positivo `// io.ktor:ktor-client-core retirado em 2024` não retorna mais True. Commit `680a59b`.
- **B-1 [baixo] — `_load_toml_catalog` cached** — `engine/init.py`: helper de parse decorado com `@functools.lru_cache(maxsize=None)` evita re-parse do mesmo `libs.versions.toml` quando N signals do mesmo card consultam. Cache key por `project_root` resolvido. Commit `680a59b`.
- **B-2 [baixo] — TOML `module` com version-suffix** — `engine/init.py`: match tolera `module = "group:artifact:version"` no TOML batendo coordinate `group:artifact` (formato inválido mas observado no wild). Match exato preservado para shape canônico; prefix-aware só para o caso version-suffix. Commit `680a59b`.
- **B-3 [baixo] — helper `parse_gradle_coordinate` extraído** — `engine/cards/_signal_shapes.py` (novo): `parse_gradle_coordinate(coord) -> tuple[group, artifact] | None` consolidado e reusado por CARD-020 (loader) + `_eval_gradle_dep` (init). Elimina drift de validação cross-módulo e prepara reuso pra futuros `pod-dep` / `npm-dep` / `swift-dep`. Commit `4a6a42d`.

### Added (PR #11 master-review — DET-3 edge case coverage, 2026-06-10)

- **S-1 cobertura de testes** — `tests/unit/test_eval_gradle_dep.py` ganha 5 edge cases: (1) BOM UTF-8 no `libs.versions.toml` silenciosamente pulado (tomllib stdlib rejeita BOM por aderir à TOML 1.0; helper engole `TOMLDecodeError` → catálogo invisível — comportamento documentado, surfaced como FU-MR-3); (2) block-table form (`[libraries.ktor-client-core]`) com chaves `module`/`group+name` split; (3) build.gradle com coordenada misturada em comentários + linha real (cobre M-5 fix); (4) variant `-ktx` em TOML-only com coordenada base — confirma assimetria documentada (FU-MR-1 trade-off); (5) catálogo customizado em path não-canônico (`dependencies.toml` fora de `gradle/`) — exercita SPEC §Non-Goals. Commit `e6305df`.

### Changed (PR #11 master-review — DET-3 assimetria documentada, 2026-06-10)

- **M-1 [médio] — Assimetria TOML-exact vs build.gradle-substring documentada** — Decisão deliberada do master-review (Caminho A): o signal `gradle-dep` faz match EXATO `group:artifact` no passo TOML (`libs.versions.toml`) e SUBSTRING no passo build.gradle (`**/build.gradle*`). Consequência observável: cards declarando coordenada base (ex.: `com.google.firebase:firebase-storage`) NÃO detectam variantes sufixadas (ex.: `-ktx`) em projetos TOML-only puros — variante seria invisível por igualdade exata. Cards devem declarar coordenadas explícitas pra cada variante quando relevante. Documentado em `docs/schemas/card.md` §Signal types nova nota de assimetria; follow-up FU-MR-1 captura trigger pro schema-version bump quando demanda do oposto (`match: prefix` opcional) emergir. Commit `c1db782`.

### Fixed (QA-11 ultra-review remediação — PR #9, 2026-06-09)

Remediação de 16 findings do ultra-review (deep.json) sobre QA-11 sandbox env hardening + QA-13. Severities variam de critical (1) a suggestion (7); todas aplicadas exceto onde indicado.

- **deep-001 [crítico]** — `engine/qa/sandbox.py::_hardened_env` não herda mais `PYTHONPATH` do parent process. A versão anterior concatenava `os.environ['PYTHONPATH']` ao `guard_dir`, permitindo que um parent hostil ou shell poluído injetasse paths de import no subprocess do sandbox. PYTHONPATH é vetor de code-execution; defense-in-depth exige drop incondicional. Callers que precisem de paths extras declaram via `extras` (que passa pelo grant flow). Test de regressão `test_hardened_env_drops_parent_pythonpath` falharia antes do fix.
- **deep-002** — `SENSITIVE_PATTERN` reescrita com boundary semantics (`(?:^|[_-])TOKEN|...(?:$|[_-])`) — elimina false-positive em `AUTHOR`, `CO_AUTHOR`, `BASE_PATHTOKEN_NAME` sem perder cobertura canônica. `AUTHORIZATION` e `AUTH(?=$|[_-])` cobertos explicitamente; `is_sensitive` passou de `.match` a `.search`.
- **deep-003** — `build_safe_env` ganha `allow_sensitive=False` default. Raise `ValueError` se `extras` contém var sensitive sem `allow_sensitive=True`. `_hardened_env` (pós-grant) passa True; callers com extras non-sensitive hardcoded (engine.verify com JAVA_HOME/ANDROID_HOME/GRADLE_USER_HOME) mantêm default seguro.
- **deep-004** — `_prompt_sensitive_grant` re-prompta até 3x antes de declarar abort e captura `EOFError` com mensagem explícita ('stdin fechado — abortando grant'). Anteriormente, qualquer input não-reconhecido (typo, '4', EOF em CI sem TTY) cancelava forge init/reconfigure silenciosamente.
- **deep-005** — `_alert_sensitive_drops` mascara nomes de vars sensitive no stderr (formato `AW********`). Em CI com log verboso, expor nomes completos como `STRIPE_LIVE_KEY` ou `OAUTH_INTERNAL_VAULT_TOKEN` era information disclosure (atacante aprende namespace de secrets do host).
- **deep-006** — `_compute_allowed_extras` ganha isinstance guard antes de `set(raw_grants)`. Shape malformado (dict, string, int) virava semantic drift silencioso: `set('GITHUB_TOKEN')` resultava em `{'G','I','T','H','U','B','_',...}` — cada char virava 'grant'. Guard duplicado consciente do já presente em `grant.py._load_existing_grants`; TODO de reuse anotado pra PR separado (extrair pra `engine/qa/_grants.py`, Mandamento #3).
- **deep-007** — magic number `0.05` em `run_sandbox` promovido a constante module-level `_MIN_REMAINING_S_FOR_SPAWN` com comentário explicando spawn overhead floor + nota de tunabilidade pra platform mais lenta.
- **deep-008** — `is_sensitive` aceita `object` e retorna `False` para non-str (fail-open) em vez de `TypeError`. Defensivo contra chamadores que esquecem `isinstance` upstream.
- **deep-009** — `evaluate_sensitive_grants` short-circuita o loop de `denied_cards` quando `denied_vars` está vazio (caminho comum em re-run sem novos prompts).
- **deep-013** — `test_core_allowlist_is_frozen` reescrito como `test_core_allowlist_is_immutable_and_contains_essentials`, asserindo a invariante de segurança real (essentials presentes, secrets ausentes) em vez da manifestação 'add raise AttributeError'.
- **deep-015** — emoji warning padronizado para `⚠` plain (sem variation selector U+FE0F) em `engine/cards/grant.py` para render consistente cross-terminal.
- **deep-016** — `extras` materializado em tupla na entrada de `build_safe_env` e `inspect_dropped` para re-iteração segura contra generators.
- **deep-017** — `_prompt_sensitive_grant` ganha `prompt_fn=input` como DI seam — tests injetam callable em vez de monkeypatch global.
- **deep-018** — `SENSITIVE_PATTERN: re.Pattern` → `re.Pattern[str]`.
- **deep-019** — `var_to_cards` em `evaluate_sensitive_grants` usa set internamente, dedup quando um mesmo card declara a mesma var duas vezes por yaml duplication user-error.
- **deep-020** — `_write_chdir_guard` aplica `chmod 0700` ao guard dir e `0600` ao `sitecustomize.py` em best-effort (Windows ignora). Em multi-tenant POSIX evita TOCTOU window entre write e subprocess spawn.
- **deep-022** — `_maybe_alert_sensitive_drops` captura `RuntimeError` adicional. `validate_qa_extensions` pode raise `RuntimeError` em catalog corrompido — sem este catch o alert layer quebrava o contrato 'NUNCA bloqueia QA run' documentado no docstring.

### Deferred (QA-11 ultra-review — fora do PR #9)

Endereçados em PRs separados por requererem refactor cross-cutting fora da whitelist do fix-loop atual:

- **deep-010** — structured warning channel (`engine/_warn.py emit_warn`) substituindo `print(..., file=sys.stderr)` em scope/qa-init/grant. Requer novo módulo e refactor cross-cutting de 3 call-sites.
- **deep-011** — normalização de `state` legacy ('aborted_by_user' → 'aborted') em `engine/qa/scope.py::_is_terminal_state`. Não está na whitelist atual.
- **deep-012** — memoização opcional de `_is_terminal_state` em `engine/qa/scope.py` para paranoid scope com muitos features. Trade-off de complexidade vs benefício; aceitar O(features) por enquanto.
- **deep-014** — plumbing de `_compute_allowed_extras` pra `engine/verify.py` substituindo o tuple hardcoded `(JAVA_HOME, ANDROID_HOME, GRADLE_USER_HOME)`. Requer propagar `workflow_config` por `_run_cascade` → `_invoke_validator` (cross-cutting). Defesa atual continua funcionando (extras hardcoded são non-sensitive).
- **deep-021** — warning em `engine/cards/loader.py` quando `env_needs[idx]` não é string. Loader não está na whitelist atual.

### Tests (QA-11 ultra-review, 2026-06-09)

- **1097 → 1113 passed** (+16 tests). Cobertura: test de regressão pra `PYTHONPATH` leak (deep-001); 9 unit tests novos pra pattern boundary semantics (deep-002 positivos + negativos); 3 tests pra defense-in-depth do `build_safe_env` (deep-003); test fail-open de `is_sensitive` para non-str (deep-008); 4 tests pra alert layer (deep-005 mask + deep-006 isinstance guard + deep-022 runtime catch); 3 tests pra grant prompt EOF + re-prompt + abort após 3 typos (deep-004); dedup de cards em var_to_cards (deep-019).

### Added (PR #8 forge qa CONF gaps + pause/resume, 2026-06-08)

- `forge qa` Phase 0 inicializa `<run>/qa-report.json` com `verdict=pending` + finaliza após Phase 5 com verdict/findings/totals + completed_at (CONF-001).
- `forge qa` Phase 0 faz snapshot dos artefatos resolvidos via hardlink (fallback copy) em `<run>/snapshot/` — preserva reprodutibilidade se user editar mid-run (CONF-002).
- `forge qa` deriva findings determinísticos de SandboxResults problemáticos via `findings_from_sandbox_results` — `sandbox-breach` (critical, always BLOCK) e `timeout` (medium) não dependem mais do LLM synthesizer pra emitir (CONF-003).
- `forge qa` pause/resume implementado via `<run>/checkpoint.json` (Decisão 27 + SDD §16 edge 6 + Gap QA-12 fechado). SIGINT salva checkpoint atomicamente; nova invocação detecta e retoma sem criar novo `run_id`. Auto-resume; corrupt checkpoint cai em 3-caminhos mentor calmo (CONF-004).
- Novo módulo `engine/qa/checkpoint.py` (`Checkpoint` dataclass, `CheckpointCorruptError`, `write_checkpoint`/`read_checkpoint`/`find_resumable_run`).
- Novo módulo `engine/qa/_common.py` (helper `utc_iso_z()` consolidado entre `__init__.py` e `checkpoint.py`).
- Novo helper `sanitize_scope_target` em `engine/qa/ingest.py` (single source of truth pra regex de path sanitization).
- `agents/qa-conductor.md` ensina conductor LLM a serializar SandboxResults em `<run>/sandbox-results.json` após Phase 3 (sem isso, CONF-003 fica dormente em produção — synthesis lê esse arquivo pra derivar findings determinísticos).

### Changed (PR #8 forge qa CONF gaps + pause/resume, 2026-06-08)

- E2E `tests/e2e/test_qa_cli_smoke.py` valida estrutura on-disk de `qa-report.json` (schema_version, run.id, run.scope, verdict ∈ {pending, PASS, FLAG, BLOCK}); disabled-path assert `qa-report.json` NÃO existe (CONF-007).
- `engine/qa/synthesis.py` `dedup_findings` alinhado com `agents/qa-synthesizer.md`: duplicates vão em `evidence.duplicates` (lista de auditor names) — `evidence_extras` removido (spec alignment).
- `engine/utils/sha256.py` promove `_normalise_description` → `normalise_description` (public API + `__all__`); alias deprecated mantido pra backward-compat.
- `engine/qa/reconfigure` `_qa_list_disable_auditors` substitui (não une) a lista de desativados — user pode re-ativar auditor já desabilitado omitindo da seleção.
- `engine/qa/sandbox.py` `_validate_paths_inside_sandbox` usa `Path.relative_to()` (robusto contra symlinks/mount points vs comparação string+os.sep anterior). Subprocess paths são `.resolve()`'d antes de `subprocess.run` pra evitar resolução relativa ao cwd do sandbox.

### Fixed (PR #8 forge qa fixes da review wave 1, 2026-06-08)

- `engine/qa/run_id.py` raise `ValueError` explícito se naive datetime é passado (antes: silenciosamente interpretado como local time pelo `astimezone`, gerando `run_id` offset incorreto).
- `engine/qa/scope.py` `_list_features_for_paranoid` filtra dirs hidden (`.DS_Store`, `.git`); `_find_screen`/`_find_task` ordenam `iterdir()` pra determinismo cross-machine.
- `engine/qa/ingest.py` `parse_qa_config` wrap `float()/int()` casts em warnings mentor-calmo + default fallback (antes: `ValueError` propagava raw traceback ao user). Sanitiza `scope.target` via whitelist `[A-Za-z0-9._-]` (preveniu path traversal).
- `engine/qa/__init__.py` `json.loads` dos findings em try/except (degradação graciosa por arquivo malformado).
- `engine/qa/emit.py` dedup por fingerprint antes de append em `proposed.yaml`; `yaml.safe_load` em try/except (OSError, YAMLError); read+merge preserva metadata pre-existente.
- `validators/validate_qa_finding.py` regex `_ID_RE` aceita uppercase (ISO 8601 T/Z); `sandbox_result=null` aceito em drafts (template default).
- `engine/reconfigure.py` `_qa_adjust_budgets` usa `float()` (preserva sub-second); rejeita valores ≤0 com mensagem mentor-calma.
- `tests/engine/qa/test_synthesis.py` `pytest.raises((AttributeError, dataclasses.FrozenInstanceError))` (antes `Exception` vacuous).

### Tests (PR #8, 2026-06-08)

- **847 → 933 passed** (+86 tests). Cobertura: 20 fixes da review wave 1, 4 CONF gaps (001/002/003/007), CONF-004 pause/resume + 4 fixes do review CONF-004, helper `utc_iso_z` em `engine/qa/_common.py`.

### Changed (PR #7 review fixes — 2026-06-08)

- **`validators/_common.py`** — `gate_threshold_lookup` aceita kwargs
  `card_override_key` / `workflow_block_key` / `defaults`;
  `format_three_paths_message` aceita kwargs `gate_title` / `why_lines` /
  `override_example` / `format_annotation`. Defaults preservam CC gate
  byte-a-byte; outros gates numéricos (Cognitive Complexity, Function
  Length) reusam direto. Fecha Gap GATE-INFRA-1 (4 PR threads, A1/A2).
- **`validators/_gate_infra.py`** — quatro robustness fixes:
  (B1) `render_config_with_placeholders` ordena placeholders por len
  desc antes de replace (evita prefix-collision); (B2) write/close em
  try/except com unlink + re-raise (sem leak de tempfile em disk-full);
  (B3) `apply_overrides` valida `override_key_fields` contra named
  groups do `key_pattern` up-front (ValueError em vez de KeyError
  tardio); (B4) `parse_overrides` adiciona `KeyError` à tupla de
  exceções do value_converter (match the docstring promise).
- **`validators/check_cyclomatic_complexity.py`** — drop dead re-exports
  `check_tool_available` / `render_config_with_placeholders` (C2).
  Tests migraram pra importar direto de `_gate_infra`.
- **`validators/_diff.py`** — (D1) `read_commit_body` resolve gitdir via
  `git rev-parse --git-dir` + fallback parse manual de `.git` file,
  suportando worktrees (`.git` é arquivo, não diretório). Antes
  silently caía pro `git log` fallback (commit prévio em pre-commit
  context). (E1) `DiffHunk.kind` promovido pra
  `Literal["add", "del", "ctx"]` (alias `HunkKind`) — sem behavior
  change em runtime.
- **`docs/design/04-pending.md`** — Gap GATE-INFRA-1 marcado como
  resolvido; novo Gap GATE-INFRA-2 (N+1 subprocess em
  `extract_diff_hunks`) registrado como deferred YAGNI até 2º consumer
  de hunks aparecer.

10 testes novos cobrindo as 4 áreas: `test_common_cc_helpers.py` (+8),
`test_gate_infra_robustness.py` (+6), `test_diff_worktree.py` (+3).
Suite total continua verde (819 passed + 19 skipped + 1 known-fail em
worktree environment).

### Changed (Phase 0 — gate-infra extraction)

- **Reusable gate infrastructure** extracted from CC gate into:
  - `validators/_gate_infra.py` — `DispatchResult`, `check_tool_available`,
    `dispatch_native_tool` (cmd_builder param), `render_config_with_placeholders`,
    `parse_overrides`, `apply_overrides` (prefix/key_pattern/extractor params).
  - `validators/_diff.py` — `DiffHunk`, `classify_range_against_hunks`,
    `extract_diff_hunks`, `git_staged_files`, `read_commit_body`.
- **Renamed in `validators/_common.py`:** `cc_threshold_lookup` →
  `gate_threshold_lookup`, `cc_format_three_paths` → `format_three_paths_message`.
  `DEFAULTS_CC` preserved (CC-specific).
- **`check_cyclomatic_complexity.py`** refactored to compose from `_gate_infra`
  + `_diff` + renamed `_common` helpers. ~1127 LOC → ~840 LOC. No behavior
  change (suite delta: -1 test, justified — removed test of internal
  `_TOOL_BIN[lang]` lookup that no longer exists post-refactor).
- **Unblocks Wave R1+** (check_secrets, check_deps_cve, check_duplication,
  check_cognitive_complexity, check_dead_code, check_arch_rules,
  check_function_length_and_nesting): gates compõem em vez de copiar a infra.

### Added

- **Plan auditor** — `.claude/rules/plan-auditor.md` define prompt
  determinístico + 12 checks com severity (2 Critical / 4 High / 3
  Medium / 3 Low) pra auditoria pós-`superpowers:writing-plans`.
  Orquestrador dispatcha `gsd-code-reviewer` com este prompt antes do
  "Execution Handoff" do SKILL.md; Critical findings bloqueiam o handoff
  até fix-dispatch resolver. Output em `.planning/plan-reviews/<plan-slug>-review-r<N>.md`
  (gitignored). Re-audit cap em 3 rodadas, override inline via
  `<!-- audit-override: C-XXX — razão -->` no topo do plano. Integração
  documentada em `CLAUDE.md` §Workflow por verbo,
  `.claude/rules/superpowers.md`, `.claude/rules/subagent-workflow.md`,
  `.claude/rules/README.md`. Spec:
  `docs/superpowers/specs/2026-06-04-plan-auditor-design.md`. Plano:
  `docs/superpowers/plans/2026-06-04-plan-auditor.md`.

  Refinements pós-smoke r1 (2026-06-04): H1 chicken-and-egg exception
  quando task cria target do plano; nova seção "Triggers que não
  dispararam" no output pra distinguir no-trigger de trigger-passou;
  M2 esclarece que anti-goals do spec contam; L2 exceção pra placeholders
  em blocos verbatim; novo verdict tier `PASS_WITH_NOTES` entre
  `PASS_WITH_WARNINGS` e `PASS` pra findings com mitigação contextual
  escrita.

  Sync r2 (2026-06-04): bloco verbatim da Task 1 do plano sincronizado
  com `.claude/rules/plan-auditor.md` atual (341 linhas, refinements
  inclusos) — endereça H-002 Caminho A do smoke r2. 5 meta-findings de
  r2 anotados em `docs/design/04-pending.md` §"Meta-findings r2
  (refinements pra plan-auditor v1.1)" como gaps deferidos pra revisita
  quando padrão recorrer em smokes futuros.

  Ultra-review r1 (2026-06-05): engine externo (`ultra-review-deep`) pegou
  11 findings que a dogfood interna de 3 rounds não viu (bias confirmação
  LLM-auditing-LLM — exatamente F-001 articulado). 10 fixes aplicados
  nesta rodada: §Verdict logic ganha critério determinístico pra
  PASS_WITH_NOTES (cita exceção ou mandamento; sem isso é WARNINGS); §Override
  mechanism trata check-ID inválido explicitamente; template `**Verdict:**`
  lista 4 tiers (incluía só 3); CLAUDE.md row "Editar schema/template"
  ganha plan-auditor (coverage consistente); linha de plan-auditor
  removida da tabela "Skills do superpowers" (Decision 22: skills ≠ rules
  locais — info preservada em §Extensão local); handoff ganha ref ao
  histórico v1.2.0 em git; §C1 valida que N é número real (não literal
  template); §H2 trigger inclui `.claude/rules/**`; subagent-workflow
  ganha cross-ref §"Loop pós-plano (plan-auditor)"; §H4 ganha nota sobre
  hooks. F-009 (README rule count) marcado como FP — README não lista
  per-rule count.

  Power-review PR #6 r3 (2026-06-05): power-review externo (mode
  `code_review`, sonnet) pegou 4 findings pendentes além dos já
  fixados (PR-001 high gap-spec, PR-002/PR-003 medium code-quality,
  PR-004 low code-quality). Endereçado em 4 commits atômicos: sync
  verbatim Task 1 ≡ rule vivo (commit `60cde77` — drift em §Verdict
  logic, §Override mechanism, H2 trigger, H4 nota hooks, C1 cond 4);
  back-port da spec inteira pós refinements r1/r2/ultra-review
  (commit `3f77879` — §Fluxo decisório 4 tiers, §Output format,
  §Integração doc-sync correcta, nota de sync ao final);
  override mechanism aceita qualquer dash separator unicode (commit
  `9282e88` — flex de `-`/`–`/`—`/`--`, propagado pro plan
  verbatim); meta-finding r2 §"Tensão snapshot-vs-vivo" ganha
  case-1 factual citando PR-001 (commit `997a21a` — contagem 1/3
  pra threshold de revisita ficar visível). Spec passa a apontar
  rule vivo como veredito; quando divergir de novo, rule vence.

### Added (PRD docs/product/, 2026-06-04)

- **`docs/product/`** — PRD consolidado do feature-forge com 4 docs (~2205 LOC totais):
  - `docs/product/00-prd.md` (583 LOC) — porta de entrada, 13 seções (Por-quê / Vision / Princípios / Escopo IN-OUT / Personas-resumo / Scenarios-resumo / Roadmap-resumo / Success criteria / Anti-personas / Cross-refs docs técnicos / Glossary 15 termos / FAQ 9 perguntas / Risks 6 + Open questions 4).
  - `docs/product/01-personas.md` (555 LOC) — 8 personas em 3 camadas: Marina (primária) + Bruno + Sub-agente Claude (dedicadas) / Carlos + Lucas + Carolina (variantes Marina) / Patricia + Diego (downstream read-only).
  - `docs/product/02-scenarios.md` (679 LOC) — 6 user journeys end-to-end (C1 Brownfield init / C2 Feature product / C3 Bugfix IN-37234 / C4 Retomar pausado / C5 Extension Gap 9 / C6 Reuse intelligence).
  - `docs/product/03-roadmap.md` (388 LOC) — 3 ondas (Autopilot v1.3-1.4 / Catálogo evolutivo v1.5-2.0 / Inteligência adaptativa v2.x) + Matriz Eisenhower + Anti-roadmap (8 items NÃO entrarão) + cross-ref bidirecional pro `docs/design/ROADMAP.md` técnico.
- Spec fonte: `docs/superpowers/specs/2026-06-04-prd-design.md` (commit `2e1a266`).
- Plan executado: `docs/superpowers/plans/2026-06-04-product-docs.md` (commit `4134744`).
- Coexistência paralela com `docs/design/` (lente arquitetura) e `docs/ux/` (roteiros) — sem mexer em load-bearing (`docs/design/00-vision.md` e `docs/design/ROADMAP.md` permanecem intactos).

### Added

- `forge qa` — 13º comando (adversarial red-team gate). 4 attack vectors
  (spec-vs-spec, chaos, coverage, validator-claim), 4 scope targets
  (feature / screen / task / paranoid), 6 phases (ingest → static →
  generative → sandbox → synthesis → emit), sandbox isolado (Decisão 30).
  Spec: `docs/superpowers/specs/2026-06-05-forge-qa-design.md`.
- Cards podem estender qa via campo aditivo `qa-extensions:` em
  `card.yaml` (schema-version permanece 1; overlay-aware Gap 5).
- Schemas novos: `docs/schemas/qa-report.md`, `docs/schemas/qa-finding.md`,
  `docs/schemas/qa-extensions.md`.
- Workflow-config ganha section `qa:` com 7 campos configuráveis.
- `forge init` Step QA novo (após Step 7.5 do Gap 5).
- `forge reconfigure` menu `[ ] qa` com 5 opções.
- `forge doctor` categoria `qa-coherence` (13ª).
- `forge implement` Phase 6 hook auto-run pré-retrospective (opt-in via
  `qa.auto-run-on-feature-done`).
- Roteiro UX: `docs/ux/forge-qa-roteiro.md` (8 cenas).
- §11 nova em `docs/design/07-discipline.md` — "QA verdict não-bloqueante".
- `engine/_sandbox/env.py` — safe env builder pra subprocess de validators
  (`build_safe_env`, `inspect_dropped`, `is_sensitive`); pure stdlib, zero
  deps em `engine.*` (QA-11).
- Campo `qa-extensions.env-needs` em cards (lista opcional de env vars
  que o card declara precisar no sandbox; QA-11).
- Campo `workflow-config.qa.sensitive-env-grants` (lista de env vars
  sensitive autorizadas explicitamente pelo user; QA-11).
- `engine/cards/grant.py` — `evaluate_sensitive_grants` + `GrantDecision`
  + `UserAbortError`. Prompt 3-caminhos mentor-calmo dispara em
  `forge init` / `forge reconfigure` quando card pede sensitive var sem
  grant prévio (QA-11).
- `engine.qa._alert_sensitive_drops` — alert mentor-calmo pré Phase 3
  quando vars sensitive serão dropadas e nenhum card as declara (QA-11).

### Added (CC gate)

- **Cyclomatic Complexity gate (`check_cyclomatic_complexity`)** — multi-language
  CC validator que roda no cascade de `forge verify` (após
  `check_no_invented_behavior`) e per-task em `forge implement` (entre review e
  commit). Threshold via precedência card `cc-gate-override` > workflow-config
  `cc-gate` > defaults (kotlin=10, swift=10, ts=15, python=10). Dispatch pra
  tools nativas: Detekt (Kotlin), SwiftLint (Swift), eslint (TS/JS), Radon
  (Python). Tools NÃO instaladas pelo forge — `forge doctor` reporta na
  categoria nova `cc-gate-tools` com instruções de install. Regra de fail:
  função `new` com `cc > threshold` OU função `modified` com `cc_after >
  cc_before`. Override-justify via `CC-OVERRIDE: <file>:<func> cc=<N> — <razão>`
  no commit body silencia fail apenas pra aquele commit (auditável via
  `git log --grep='CC-OVERRIDE'`). 3-caminhos canônico on-fail
  (refactor / override-justify / split-task). Bypass de emergência via
  `NO_CC_GATE=1` env var, logado em `.claude/state/cc-gate-bypass.jsonl`.
- Helpers `cc_threshold_lookup` + `cc_format_three_paths` em `validators/_common.py`.
- Configs internos `engine/_cc_configs/{detekt.yml,swiftlint.yml,eslint.json,radon.cfg}`
  controlados pelo forge (versionados junto da release).
- Doctor categoria `cc-gate-tools` (13ª categoria, full scope) com status
  por tool (detekt/swiftlint/eslint/radon) + instruções de install pras
  missing.
- ~63 unit + integration tests novos (`tests/validators/test_cc_*.py`,
  `tests/validators/test_check_cyclomatic_complexity.py`,
  `tests/engine/test_*_cc_*.py`, `tests/integration/test_cc_gate_end_to_end.py`).
  Suite total cresce de 630 → 693 tests collected.
- **Check Secrets gate (`check_secrets`)** — gate multi-tool que barra secrets
  em staged files, com per-stage split: `gitleaks` roda no per-task hook de
  `forge implement` (fast, regex-based, ~100ms) e `trufflehog --only-verified`
  roda na cascade de `forge verify` (deep, verificação ativa contra a origem).
  Posicionado **após** `check_cyclomatic_complexity` no cascade — fail-fast
  Decision 23 preservado. Override via `SECRETS-OVERRIDE: <file>:<line>
  kind=<token-type> — <razão>` no commit body silencia o finding `(file, line,
  kind)` apenas naquele commit (auditável via `git log --grep='SECRETS-OVERRIDE'`).
  Hard-fail sempre quando secret sobrevive; tool missing → warn (cascade segue
  alive, mesmo contrato do CC gate). Bypass de emergência via `NO_SECRETS_GATE=1`,
  logado em `.claude/state/secrets-gate-bypass.jsonl`. Composto inteiramente da
  infra Phase 0 (`dispatch_native_tool`, `apply_overrides`, `check_tool_available`,
  `git_staged_files`, `read_commit_body`, `result_*`). Doctor ganha 14ª categoria
  `secrets-tools` (gitleaks + trufflehog + install hints). Validators 15→16.
  Tests em `tests/validators/test_check_secrets*.py` +
  `tests/integration/test_secrets_gate_end_to_end.py`.

### Added (CC gate refinements — final review fixes)

- **Dynamic threshold propagation** for Detekt and SwiftLint: configs use
  `__CC_THRESHOLD__` placeholder rendered per invocation via tempfile.
  Spec §3 contract "threshold via CLI args sempre" honored — mechanism
  differs from eslint `--rule` flag because Detekt/SwiftLint don't accept
  CC threshold via CLI.
- **Radon rank filter** changed from `-n F` (rank F = CC ≥ 41) to `-n A`
  (all functions). Previous filter masked CC ∈ [11..40], making Python
  gate effectively cc=41 instead of configured threshold.
- **Canonical 3-caminhos render** now reaches the user: `cc_format_three_paths`
  output stored in `result["render"]`, consumed by `engine/implement.py:_render_cc_gate_block`.
- **Malformed override warnings** propagate from `_apply_overrides` (now
  returns 3-tuple `(silenced, surviving, warnings)`) up to the result
  dict so users see why their CC-OVERRIDE attempt didn't count.
- +8 tests novos (1 dispatch radon `-n A`, 2 dispatch threshold-via-config
  Detekt/SwiftLint, 1 validate canonical render, 1 validate warnings,
  1 helper apply_overrides warnings, 2 implement render canonical). Suite
  total: 682 passed, 17 skipped.

### Added (Gap 9 — extends-feature mechanic, 2026-06-03)

- **Gap 9 resolvido — extends-feature mechanic (re-escopado 2026-06-03)** —
  feature done pode ser estendida via novo slug derivado (e.g.,
  `lembrete-rega-watch-extension`) que herda contexto da pai via campo
  aditivo `extends-feature: {parent-slug}` no `status.json` + intake. Sem
  cards canon novos; sem mudança no enum `platforms`; sem upgrade de
  inventory schema. Pattern leve product-derived. Cobertura nova:
  - **Schema** — `docs/schemas/memory.md` ganha `extends-feature` +
    `parent-feature` em `status.json`; MEM-L1-008 atualizada com regra
    "se `extends-feature != null` → parent existe E `parent.state == done`".
    Forward-compat: status.json pré-Gap 9 carregam normais (default null).
  - **Engine** — `engine/memory/l1.py` `L1State` ganha `extends_feature` +
    `parent_feature` + helpers `parent_state()` + `list_extensions_of()`.
    `engine/plan.py` Cena 1 oferece 4º caminho **"Estender"** quando
    feature pai existe em `state=done`; context-pack import lê `status.json`,
    `hypothesis.yaml`, `data-contract-spec.yaml`, `screen-analysis.yaml`,
    `tech-spec.md`, `existing-helpers.yaml` da pai e popula o intake da
    extensão.
  - **Template** — `templates/feature-intake.template.md` ganha bloco
    condicional §Extension context (parent feature, parent shipped, scope of
    extension, reuse from parent, out-of-scope vs parent). Ausente quando
    `extends-feature` é null — standalone feature fica idêntica ao pré-Gap 9.
  - **UX** — `docs/ux/forge-plan-roteiro.md` Cena 1 ganha 4º caminho
    "Estender" com sub-cenários (happy / parent não-done / slug derivado
    duplicate / cancelar).
  - **Validator** — `validators/validate_extension_feature.py` novo:
    EXT-001 (parent existe), EXT-002 (parent.state == done), EXT-003
    (slug derivado != parent), EXT-004 (dedupe por `extension-scope`).
    3-caminhos canônico no fail (discipline §1). Inativo quando
    `extends-feature` é null (no-op pass). **Wiring na cascade `forge
    verify` deferido pra v1.x+ (W-001)** — validator existe standalone +
    coberto por testes; cascade auto-discovery (via cards/hooks) vem
    com piloto smoke. Hoje invocação é manual ou via hook custom; ver
    `docs/design/04-pending.md` Gap 9 TODO residual.
  - **Agents patched (4):** `planning-conductor` (Phase 1 step 5 extension
    import + Phase 4 wave dispatch variants A/B/D + Phase 6 retrospective
    variant + closing format), `feature-intake-agent` (extension block
    elicitation), `tech-spec-agent` (context-pack ganha `extends-feature` +
    `parent-baseline` references — sem mudança em rendering), `retrospective-
    agent` (extension variant 4 perguntas: herdei literal / delta mínimo /
    criei do zero apesar de extension / sinais pra refactor parent + extension
    pra shared base).
  - **Discipline §10 nova** em `docs/design/07-discipline.md` formaliza
    semantics + distinção formal vs refactor/bugfix/standalone (tabela
    4-eixos) + wave dispatch semantics + filesystem layout
    (`L1/{parent}-{suffix}/`, **não** `non-product/`) + hypothesis schema +
    Phase 6 retrospective (herança vs adição, sem 5-whys) + cheat-sheet
    entry + cross-link com §8 + §9 + Gap 5.
  - **Tests** — 37 novos (`tests/unit/test_extension_feature.py` cobre
    round-trip L1State + helpers + validator happy + 4 fail paths;
    `tests/unit/test_plan_extension.py` cobre Cena 1 4º caminho detection +
    sub-cenários). Suite total: 595 → 637 passing (+42 cumulativo desde
    v1.2.0: 37 Gap 9 + 5 do fix loop).
- `engine/implement.py` escreve `shipped-at` (ISO 8601 UTC) automático na
  transição `state=done` (sob o mesmo bloco que escreve
  `last_action_kind = "implement-completed"`). Suportado por `L1State.raw`
  round-trip — forward-compat com features done pre-Gap 9 (campo é
  nullable, intake renderiza `unknown` quando ausente). Fix do W-002 do
  REVIEW: extension intake rendering de `Parent shipped: {{parent_shipped_at_iso8601}}`
  passa a ser populado em vez de sempre `null`/`unknown`.

### Changed

- `docs/design/04-pending.md` Gap 9 re-escopado e fechado: watchOS / Wear OS /
  tvOS / multi-target movidos pra **"out-of-scope explícito permanente"**
  (feature-forge cobre mobile = Android + iOS + KMP). Mecânica
  `extends-feature` continua útil pra variant / sub-area / módulo paralelo.
  Sinergia com Gap 5: plataforma exótica futura entra via overlay local
  (`.claude/cards/local/`), não via canon expansion. Nenhuma decisão locked
  revisitada (Decisões 9, 10, 14, 22, 28 aceitam aditivo natural).
  Contadores atualizados (7 resolvidos / 9 acionáveis pra v1.x+).
- `docs/design/07-discipline.md` §10 header padronizado (`## 10. Extension
  feature`) alinhado ao paralelismo das §§ 1-9 (fix do I-007 do REVIEW —
  consistência estilística vs prefixo `§10` + parênteses inline).
- `engine/plan.py` `_create_extension_l1` ganha guard explícito enforçando
  `parent_status.status == "done"` (fix do W-005 do REVIEW). Defesa em
  profundidade: write-time check além do validator runtime. Custo: 4
  linhas + 1 test.
- `agents/retrospective-agent.md` extension variant agora cobre as **4
  perguntas** canônicas do discipline §10 (era 3 — faltava "sinais pra
  refactor parent + extension pra shared base"). Fix do W-003 do REVIEW.
  `agents/planning-conductor.md` template prompt for retrospective-agent
  (extension variant) idem.
- `validators/validate_extension_feature.py` remove check redundante
  `parent-feature != extends-feature` (fix do I-002 do REVIEW). Lockstep
  é garantido por `_create_extension_l1` e `write_l1_status` no write path
  — defender contra arquivo escrito à mão é overkill pra v1; os 4 codes
  EXT-001..004 do plano canônico ficam estritos.
- `CLAUDE.md` baseline de testes atualizado: `pytest (367 tests baseline)` →
  `pytest (637 tests baseline)` (fix do I-006 do REVIEW — drift pré-existente
  desde v1.1.0 + acumulado em v1.2.0 + Gap 9). Re-baselinar pra próximo
  gap saber a verdade.
- `engine/memory/l1.py`: simplifica fallback kebab/snake em `read_l1_status`
  com `dict.get(kebab, dict.get(snake))` (refactor puro, sem mudança de
  comportamento) — endereça nit gemini-code-assist no PR #3 (commit
  `7313a30`).
- `engine/qa/sandbox.py._hardened_env` agora delega base do env pra
  `build_safe_env(extras=...)` em vez de `dict(os.environ)`. Refactor
  mantém PYTHONPATH guard + FORGE_QA_SANDBOX marker (QA-11).
- `engine.verify` linha 624 — `subprocess.run` pra validator agora usa
  `env=build_safe_env()` (era default: herdar env completo do pai). Bug
  silente de leak fechado (QA-11).

### Changed (load-bearing)

- Revisita decisão 9: command surface 12 → 13 subcomandos — adiciona `forge qa` (adversarial red-team gate). Design completo em `docs/superpowers/specs/2026-06-05-forge-qa-design.md`. Locked at 12 histórico preservado em `docs/design/01-decisions.md` linha 9; novo lock em linha 29.
- Adiciona decisão 30: sandbox isolation pra `forge qa` Phase 3 — subprocess CWD dedicado em `.planning/qa/<run-id>/fixtures/`, SandboxBreachError em writes fora, budget global configurável.

### Security

- **QA-11 fechado.** Secrets do processo pai (`AWS_TOKEN`, `GITHUB_TOKEN`,
  `DB_PASSWORD`, `*_SECRET`, etc.) não vazam mais pro subprocess de
  validators rodando em `forge qa` Phase 3 sandbox nem em `forge verify`.
  Mitigação cobre dois threats: card extension malicioso (`qa-extensions.
  auditors` lendo `os.environ`) e leak acidental em validator canon
  (traceback que printa env em debug). Defesa = allowlist core
  (`CORE_ALLOWLIST` hardcoded em `engine/_sandbox/env.py`) + per-card
  opt-in declarativo + grant explícito do user pra vars sensitive.

### Fixed (PR #4 review)

- `_path_matches_ignore` agora emite warning quando regex inválida em
  `cc-gate.ignore-paths` (era silently swallowed). Pré-validação via
  helper `_compile_ignore_patterns` em `validate()`, warnings propagam
  no result dict (`cc-gate.ignore-paths: regex inválida '<pat>' (<erro>)`)
  — D-006.
- `_parse_overrides` emite warning pra `CC-OVERRIDE: ... cc=N — ` com
  reason vazia/whitespace após em-dash (era loose-skipped). Strict regex
  ganhou guard `reason.strip() == ""` pra não aceitar reason em branco;
  loose-pass inspeciona o tail após `—` — D-008.
- Warnings de `_run_tools_for_staged` agora distinguem tool ausente
  (`[<tool>] tool ausente: ...`) de tool crashada
  (`[<tool>] tool crashou: ...`) — D-009.
- `_git_staged_files` adiciona `-M80%` ao `git diff` pra rename detection
  (SDD §2 — função renomeada até 20% mudança vira `modified` no delta
  rule, não `new` + delete) — F-006.
- Test assertions tightened: `install_hints` específico pro `eslint`
  (filtra por `c.name == "eslint"` antes de checar substring),
  `next()` lookup safer em `test_verify_cc_position` (default None +
  assertion descritivo) — codereviewbot 3353045999/3353046005.
- +6 tests novos cobrindo D-006/D-008/D-009/F-006. Suite total:
  688 passed, 17 skipped, 1 falha pre-existing
  (`test_bootstrap_is_idempotent` em worktree — Gap BOOTSTRAP-1).

### Fixed (QA-11 post-review remediação)

- **QA-11 final review remediação** (commits `0563cfa` + `728aa79`):
  - **CR-01:** `conductor-handoff.json` agora inclui
    `config.allowed_env_extras` (list[str] derivada de cards' `env-needs`
    + `sensitive-env-grants`); `agents/qa-conductor.md` documenta contrato
    de consumo (`run_sandbox(extras=...)`). Sem isso, a chain card
    `env-needs` → sandbox subprocess ficava plumbing-only em produção.
  - **CR-02:** `_alert_sensitive_drops` em `engine/qa/__init__.py` tinha
    interseção invertida (`card_env_needs & (CORE ∪ granted)` — filtrava
    non-sensitive vars de cards). Substituída pela semântica correta:
    non-sensitive sempre passa; sensitive só com grant.
  - **CR-03:** `engine/cards/loader.py` agora guarda `isinstance(v, str)`
    antes de `is_sensitive(v)` — `env-needs` malformado no canon path não
    crasha mais com `TypeError` cru.
  - **IM-01:** `engine/verify.py` subprocess de validator agora passa
    `extras=("JAVA_HOME", "ANDROID_HOME", "GRADLE_USER_HOME")` — CC
    validator (detekt/swiftlint) volta a funcionar em codebases
    Kotlin/Android.
  - **IM-02:** alert layer `except Exception` estreitado pra
    `(CardError, OSError, ValueError, KeyError)` — deixa de mascarar bugs
    reais.
  - **IM-03:** `evaluate_sensitive_grants` agora ordena `cards_requesting`
    antes do join — prompt UX determinístico cross runs.
  - **IM-04:** alinhamento de calling style de `three_paths_block` entre
    `engine/qa/__init__.py` e `engine/cards/grant.py` (positional
    consistente).
- Re-review confirmou os 7 findings endereçados corretamente. Suite
  rapid lane: 896 tests verdes.

### Fixed (QA-13)

- `engine/qa/scope.py._list_features_for_paranoid` agora filtra features
  com `state ∈ {"aborted", "archived"}` (per spec §5.0). Fail-safe
  default-include pra features legacy (sem status.json) ou status.json
  malformado — paranoid quer audit broad, broken features ficam visíveis
  pra user notar gaps. Fecha pré-piloto bloqueador QA-13.

## [1.2.0] — 2026-06-03

### Added (Gap 5 — Card local overlay, 2026-06-02)

- **Gap 5 resolvido — Card local overlay (Approach A)** —
  `.claude/cards/local/<name>/` versionado no projeto consumidor, lido via
  loader cascade canon ∪ local com hard-fail em colisão. Valida via
  `validate_card_yaml` (canon/local discrimination por path resolved) +
  `validate_capability_labels` (overlay-aware via `validators/_common.load_catalog`).
  Reconfigure ganha submenu `card-local` (listar/adicionar/remover). Init
  ganha Step 7.5 com 3-caminhos pra signals órfãos (criar local / ignorar /
  abortar). Edge case: orphan em label reservada vira "abrir ADR".
- **Cards canon novos:** `retrofit-client` (provê `http-client`) e
  `shared-preferences-prefs` (provê `local-prefs-storage` legacy com
  `legacy-marker: true`). 20 → 22 cards canon.
- **Schema bump aditivo:** novo campo top-level opcional `legacy-marker: bool`
  no `card.yaml` (default false). `schema-version` permanece `1`.
- Nova exception `CardConflictError` em `engine.cards`.
- Nova validação `CARD-019` (legacy-marker, if present, must be bool).
- **Nova decisão locked 28** (Card local overlay — Approach A) registrada
  em `docs/design/01-decisions.md`. Não revisita decisão prévia — é decisão
  *adicionada*; a ceremony "revisita decisão" do hook pre-commit fica
  satisfeita por esta nota explícita pra que o commit doc-sync passe sem
  bypass (não é revisita; é decisão nova append-only).

### Fixed (Power-review PR #2 follow-ups — 2026-06-03)

- **CARD-008 conformity em `validate_capability_labels`** — `conflicts-with`
  passa a aceitar label OR card-name conforme o schema. Antes, o validator
  rejeitava o canon `shared-preferences-prefs` (que declara
  `conflicts-with: [datastore-prefs]` por card-name) — bloqueava qualquer
  consumer rodando `forge verify`.
- **Orphan signals grouping por capability** em `engine/init.py` Step 7.5
  caminho 1 — múltiplos orphans com a mesma `suggested_capability` agora
  geram UM único card local com signals consolidados (antes, o segundo
  write sobrescrevia silenciosamente o primeiro). `_card_local_add_inline`
  aceita `OrphanSignal | list[OrphanSignal]` (backward compat).
- **`_count_needle_hits` respeita `_SKIP_DIRS`** em `engine/init.py` —
  `node_modules`, `build`, `.gradle`, `Pods`, `DerivedData`, `dist` são
  filtrados no walk. Sem isso, init em monorepos travava por minutos
  varrendo deps/build artifacts.
- **Atomic write** em `_write_local_cards_manifest` (`engine/cards/loader.py`)
  via `tempfile.mkstemp` + `os.replace` — sem manifest parcial em disco se
  o processo morrer no meio do write.
- **Rollback** em `_card_local_add` (`engine/reconfigure.py`): falha de
  OSError em qualquer um dos 3 writes (card.yaml, README.md,
  detection/signals.yaml) remove o card_dir parcial e mostra erro colored.
- **OSError capture** em `validators/_common.load_catalog` e
  `validators/validate_card_yaml.validate` — antes apenas YAMLError era
  capturado; OSError vazava como traceback bruto.
- **N2/N3 init** — docstring + UX copy de Step 7.5 caminho 1 agora avisa
  honestamente que catálogo expandido só ativa no próximo `forge init`
  (re-detection inline fica pra v1.2). Anti-colisão canon adicionada em
  `_card_local_add_inline` (sufixo `-local` se nome colide com canon).
- **N4 reconfigure** — `_save_draft` surface OSError via renderer warn
  (era silently-swallowed). Reconfigure continua, mas user é avisado.
- **N12 reconfigure** — label do caminho 1 no submenu de colisão de nome
  troca "fornecer outro nome" por "ver cards existentes e voltar
  (re-prompt em v1.2)" pra honrar o contrato 3-paths (disciplina #1).
- **N10 refactor** — `_LOCAL_CARD_NAME_RE` promovido de
  `engine.reconfigure` (private) pra `engine.cards.LOCAL_CARD_NAME_RE`
  (public). Engine/init.py e engine/reconfigure.py importam da fonte
  canônica; alias antigo mantido em reconfigure pra back-compat.
- **N11 loader** — `_write_local_cards_manifest` fallback graceful pra
  paths não-subpath de project_root (`relative_to` ValueError → str
  absoluto). Raro mas observável em fixtures de teste.
- **Tests strengthened** — `test_cascade_raises_on_malformed_local_card_yaml`
  ganha assert do path/marker no erro (C9); novo
  `test_cascade_writes_local_cards_manifest_with_multiple_cards_sorted`
  cobre 2+ locals + ordem canônica (C10); dead imports limpos em
  `test_e2e_local_card_pilot.py` (N8) e `test_card_md_schema.py` (N9);
  type annotation em `_check_orphan_signals.catalog` (N5).
- **Novos testes TDD** (rapid lane 521 → 533, +12):
  - `tests/unit/test_validate_capability_labels_conflicts_with_card_name.py`
    (N1, 3 testes)
  - `tests/unit/test_init_count_needle_hits_skip_dirs.py` (C16, 5 testes)
  - 3 testes adicionais em `tests/unit/test_init_orphan_signals.py` (C14/C15)
  - 1 teste adicional em `tests/unit/test_cards_loader_local.py` (C10)
- **Graph schema_version integration test drift** — `tests/integration/test_graph_build_meobonsai.py::test_build_full_creates_meta_schema_version`
  agora trackeia `sqlite_io.SCHEMA_VERSION` dinamicamente em vez de hardcoded `"1"`.
  Drift introduzido em `65c358c` (feat: reuse-intelligence shipped novas tabelas de
  graph + bump pra "2") nunca foi refletido no integration test. Pré-existente ao
  PR #2 / Gap 5; identificado durante power-review R1.

### Fixed (PR #1 round 3 — 2026-06-02)

- `implement.run` blocked-on-external branch não chama mais
  `release_phase_lock` antes do acquire — preservava lock stale de
  outro fluxo, violando single-writer invariant. Recovery de lock
  stale fica via `forge undo` (A3; `engine/implement.py`).
- `.claude/bootstrap.sh` detecta symlinks quebrados (target ausente) e
  re-linka em vez de pular silenciosamente.
- `.claude/hooks/post-edit-doc-drift.sh` agora usa `fcntl.flock` (via
  python3 inline) ao ler-modificar-escrever os JSON state files
  (`drift-warned.json`, `drift-pending.json`) — protege contra race em
  invocações concorrentes do hook.
- `.claude/hooks/pre-tool-use-load-bearing.sh` agora usa `fcntl.flock`
  no append do audit log — sem corrupção de JSONL em invocações
  paralelas.
- `.claude/hooks/session-start-orientation.sh` removeu
  `set -euo pipefail` que violava o contrato "sempre exit 0". Errors
  internos não derrubam mais a sessão.
- `engine/doctor._check_reuse_findings` usa `contextlib.closing()` em
  vez de try/finally — conn fecha mesmo em exceções não-sqlite3
  (RuntimeError, MemoryError).
- `engine.graph.parser_kotlin._simplify_generics` ganhou ceiling de
  iteração + increment garantido — input malformed (`"List<T"` sem
  fechamento) não pode mais loopar infinitamente.
- `engine.memory.acquire_phase_lock` agora emite warning via stderr
  quando o unlink do sentinel falha após `_mirror_phase_lock_to_status`
  raise — operadores vêem o sentinel stuck em vez de o erro ser
  silenciado.
- `blocking_deps` warning wording mudou pra `corrupt YAML — failed to
  parse` (era `skipping unreadable`); test regex agora exige keyword
  específico ao invés de só checar task ID.

### Tests (R3)

- 5 novos regression tests pra R3: foreign-lock preservation,
  doctor conn-close-on-error, parser_kotlin simplify_generics
  termination (com threading watchdog), bootstrap symlink repair
  (integration), e tightened blocking_deps warning assertion.
- Total: **463 unit tests passing** (era 455 fim de R2 → +8).

### Fixed (PR #1 round 2 — 2026-06-02)

- `_fingerprint` agora usa `\x00` (NUL) como separador em vez de `|`, fechando colisão com TS union types em body text (A7; `engine/graph/duplicates.py`).
- `GROUP_CONCAT` agora usa `\x1F` como separador em vez de `,`, suportando paths com vírgulas em occurrence rows (A8; `engine/graph/duplicates.py`, `engine/graph/queries.py`).
- `blocking_deps` sobrevive a `TASK-*.yaml` corrupto — per-file try/except + stderr warning (A10; `engine/memory/l1.py`).
- `parser_kotlin` máscara strings/comments antes de `_RE_DECL.finditer`, eliminando false-positives dentro de raw strings `"""...fun fake() {...}"""` e block comments (A11; `engine/graph/parser_kotlin.py`).
- `detect_after_update` / `update_file` / `update_batch` agora fecham `conn` em todo exit path (mesma classe que C2 lock leak; `engine/graph/incremental.py`).
- RFC arrow regex tolera one-level nested parens (e.g., `({callback = (x) => x}) => <div/>`) e aceita JSX `<` como body start (`engine/graph/parser_typescript.py`). Aviso: comp count vai crescer em projetos consumidores com RFCs JSX-style.
- `_resolve_subtype` em `check_no_behavior_change` propaga exceções inesperadas (incluindo `MemoryError`) em vez de silenciar tudo; só `FileNotFoundError, OSError, ValueError, KeyError, yaml.YAMLError` fall through pra default `"product"` (`validators/check_no_behavior_change.py`).

### Changed

- `.claude/rules/orchestrator-persona.md` ganhou seção "Não-procrastinação" formalizando default "endereça agora" vs "defer com razão concreta" (5 categorias legítimas de defer). CLAUDE.md root aponta pra ela em nova seção "Mentalidade operacional". Origem: feedback de sessão 2026-06-02 no PR #1, depois que expansão de escopo R1→R2→R3 cobriu 55 commits em vez dos 15 iniciais (2026-06-02).
- `engine.memory.l1.phase_lock_held` context manager substitui o flag pattern em `engine.implement.run` — release estrutural via `__exit__` em vez de `if not lock_released: release_phase_lock(...)`. NOT REENTRANT-SAFE — documentado em docstring + test (MD-03).
- `parser_typescript._RE_RFC_ARROW`: body start lookahead expandido de `[\(\{]` para `[\(\{<]` (aceita JSX raw bodies). Subprodute: contagem de RFCs detectados vai crescer em codebases com `const X = () => <div/>`.

### Performance

- `list_reuse_findings` agora usa single JOIN em vez de N+1 query loop (A13; `engine/graph/queries.py`). 50 findings + 150 locations = 2 queries (era 51).

### Tests

- 24 novos regression tests pra round-2 fixes: fingerprint NUL, occurrence separator, blocking_deps corrupt YAML, parser_kotlin mask, incremental conn lifecycle, RFC arrow regex, phase_lock_held CM (+ reentrant contract), _resolve_subtype narrow except, A13 perf (query count instrumentation).
- 12 cobertura mínima do master review: Q12-Q17 (6 query tests), `infer_suggested_target` 6 categorias (5 do plano + duplicate-ts-helper via IN-03), Kotlin raw-string brace regression, Swift `"""` + escapes.
- Total: **508 tests passing** (unit + integration) — era 367 baseline original v1.1.0; cumulativo no PR #1.

### Documentation

- `engine/utils/sqlite_io.py` — comentário explicando trade-off de `synchronous=NORMAL` (3x faster writes, last-tx-may-be-lost on power loss, graph DB é cache recuperável via `forge reconfigure`).
- `engine/reconfigure.py` — comentário sobre `kill -9` mid-loop deixar partial state cross-file; recovery é MANUAL via `.bak` files no disco (`forge undo` NÃO cobre esse path — gap em `docs/design/04-pending.md`).
- `engine/doctor.py` — docstring de `_stamp_last_doctor_run` documenta last-write-wins em CI matrix; stamp é observabilidade informacional.
- `engine/graph/_body_text.py` — `hash_body` docstring expandido com collision math (64 bits → birthday collision ~50% @ 2^32 ~4B symbols), alternativas BLAKE3-128 (2x DB) e SHA-1 full (2.5x DB).
- `engine/memory/l1.py` — `phase_lock_held` docstring marca não-reentrante + nomeia callers atuais + aponta pra v1.1.1.

## [1.1.0] — 2026-06-01

### Released

- Released as **v1.1.0** — `engine/__version__` e `pyproject.toml` alinhados em `1.1.0` (commit `7286fa0`, C4). `forge --version` agora reporta `forge 1.1.0`.

### Added (Claude Code rules system)

- `CLAUDE.md` root + `.claude/rules/*.md` (12 operational rules) — Mandamento 0 (orchestrator-mantenedor com delegação total via Agent tool) + 6 mandamentos (decisões locked, verde antes de pronto, reuso, escopo, voz mentor calmo, doc-sync) + workflow por verbo + map dos 10 superpowers skills ativos.
- `.claude/hooks/*.sh` (4 hooks): `session-start-orientation.sh` (injeta Mandamento 0 + estado), `pre-tool-use-load-bearing.sh` (warn + audit em load-bearing edits), `post-edit-doc-drift.sh` (lembrete doc-sync once-per-file-per-session), `pre-commit-feature-forge.sh` (HARD BLOCK em `01-decisions.md` sem ceremony "Revisita decisão" + SOFT WARN em código vivo sem doc-sync).
- `.claude/settings.json` registrando os 3 hooks Claude Code (SessionStart, PreToolUse, PostToolUse).
- `.claude/bootstrap.sh` (idempotent one-time setup — symlinks `.git/hooks/`).
- `tests/integration/test_claude_rules_system.py` — 36 testes (marker `integration`).
- `docs/superpowers/specs/2026-06-01-claude-md-design.md` (brainstorm) + `docs/superpowers/plans/2026-06-01-claude-md-rules-system.md` (plan executável).

### Adicionado

#### Stress-test 2026-05-29 — 4 Gaps shipped

- **Gap 1 — Bugfix subtype** (hotfix urgency fast-path): `subtype="bugfix"` no
  `_VALID_SUBTYPES`, keyword + ticket-pattern detection (`IN-/PD-/BUG-`),
  Wave B conditional sub-question (`A·C·D·E` logic-only OR `A·B·C·D·E`
  UI-observable), template `feature-intake-bugfix.template.md`.
- **Gap 2 — Non-product feature track** (refactor only; spike + chore stubbed):
  `subtype=refactor|spike|chore`, filesystem layout `non-product/{slug}/`,
  template `feature-intake-refactor.template.md`, validator
  `check_no_behavior_change` gateando Wave E.
- **Gap 8 — `blocked-on-external` state** (orthogonal to subtype): state
  enum value, manual unblock via `forge reconfigure → external-deps`,
  preservado em retomadas.
- **Gap 18 — Reuse intelligence** (expansão completa): detecção init-time +
  incremental + 6 categorias (within-module, cross-module, redundant-platform,
  near-duplicate, kmp-migration, ts-helper) + integração com `forge plan`
  refactor subtype.

#### Reuse intelligence (Gap 18 expandido)

- **6 detection categories** em `engine/graph/duplicates.py`:
  - `duplicate-within-module` (Kotlin extension repetida em 1 módulo, conf 0.95)
  - `duplicate-cross-module` (sibling modules → smallest-common-ancestor via
    Gradle dependency closure, conf 0.85)
  - `redundant-platform-specific` (Android Kotlin idêntico a shared commonMain, conf 0.90)
  - `near-duplicate` (mesma assinatura, body_hash diferente — drift signal, conf 0.40)
  - `kmp-migration-candidate` (Swift ↔ Kotlin shared com Jaccard ≥0.4, conf 0.50–0.75)
  - `duplicate-ts-helper` (TypeScript top-level duplicado, conf 0.95)
- **Schema v2 — colunas + tabelas**:
  - `files.source_set` (commonMain / androidMain / iosMain / …)
  - `symbols.{receiver_type, body_hash, body_tokens, modifiers}`
  - `module_deps` (Gradle dependency graph parsed de cada `build.gradle(.kts)`)
  - `reuse_findings` + `reuse_finding_locations` (materialized detection output)
- **Parser overhaul** (Kotlin / Swift / TypeScript):
  - visibility agora persistida (era hardcoded "public")
  - signature normalizada (param names dropped, generics simplified)
  - body extraction brace-aware em `engine/graph/_body_text.py`
  - body_hash (SHA-1[:16]) + body_tokens (JSON) para Jaccard cross-language
  - Swift two-pass captura receiver de `extension Type { func ... }`
- **Module inference** (settings.gradle + build.gradle parsing):
  - `engine/graph/gradle_modules.py`: longest-prefix match para multi-módulo
    (KMP `:shared:feature:auth` ou Android `:androidApp:feature:bonsai`)
  - `engine/graph/gradle_deps.py`: transitive closure + smallest-common-ancestor
- **Apply flow** (`engine/graph/reuse_apply.py`):
  - 6 novos kinds em `_VALID_KINDS` do distiller
  - `apply_proposal_to_l2` dispatcha para `apply_reuse_intelligence_proposal`
  - Renderiza `templates/feature-intake-refactor.template.md` com payload
  - Escreve L1 `status.json` com `subtype="refactor"` → `forge plan {slug}`
    detecta automaticamente e pula Wave A discovery (Gap 2 integration)
- **Engine wiring**:
  - `engine/init.py` Step 11.5: `queue_proposals_from_table` após graph build
  - `engine/init.py` Step 11.6: escreve `.claude/hooks/post-edit-detect-duplications.sh`
  - `engine/reconfigure.py`: re-queue após rebuild
  - `engine/doctor.py`: `_check_reuse_findings` agregado por categoria
  - `engine/graph_cli.py`: opções 12–17 + `r` (combined) + `forge graph detect-incremental <file>` non-interactive
  - `engine/graph/incremental.py`: `detect_after_update` para hook entrypoint
- **Q11 backward-compat**: filtro `f.module = 'shared'` → `LIKE 'shared:%'`
  para multi-módulo shared.
- **Tests iniciais**: 20 unit tests em `tests/unit/test_reuse_intelligence.py`,
  cobrindo body extraction, gradle parsing, parser fields, detection completo,
  apply + status.json.
- **Schema docs**: `docs/schemas/graph.md` + `docs/schemas/proposed-evolutions.md`
  ganham seção "Reuse Intelligence (schema v2)".

### Fixed (PR #1 bloqueadores — 2026-06-01)

Round final de hardening da v1.1.0: critical (C1–C4), alta (A1, A2, A5, A6, A9, A12), review (CR-01, CR-02, MD-01, HG-01, HG-02, HG-03). Conjunto coberto por 38 novos regression tests; nenhum locked decision foi revisitado.

- **C1 + A1 — Phase lock atomic** (`engine/memory/l1.py`, commit `0b96212`): `acquire_phase_lock` fazia read-then-write em `status.json` — sob N processos racing, múltiplos passavam o check e o último writer ganhava. Sentinela `.phase-lock` via `os.open(O_CREAT | O_EXCL)` é agora o gate atômico; `status.json` continua espelhando o lock id pra read APIs. Regressão coberta com `multiprocessing.Barrier` (16 workers, um único vencedor).
- **C2 — Implement lock release em qualquer exception path** (`engine/implement.py`, commit `f0776ab`): o `try/except` da critical section só capturava `PromptAbortedError`. Qualquer outra exceção (RuntimeError, OSError, KeyError) escapava com o lock retido, forçando `forge undo` pra recuperar. Flag `lock_released` + `finally` backstop garantem release em qualquer caminho — auditável em `history.jsonl`.
- **C3 — `_reset_domain_tables` atomic + FK pragma restore** (`engine/graph/builder.py`, commit `c84779a`): rodava `PRAGMA foreign_keys = OFF` → DELETEs → `PRAGMA = ON`. Se um DELETE raise no meio, o pragma final nunca executava e a conexão silenciosamente vazava `foreign_keys=OFF` pra toda transação subsequente. `try/finally` dentro de `with conn:` garante rollback + pragma sempre restaurado.
- **C4 — Version bump 1.0.0 → 1.1.0** (`engine/__init__.py` + `pyproject.toml`, commit `7286fa0`): engine e pyproject reportavam `1.0.0` apesar do release v1.1.0 já cobrir reuse-intelligence schema v2 + 17 graph queries + Claude Code rules system. `forge --version` e `import engine.__version__` agora batem com CHANGELOG.md e session-handoff.
- **A2 — `forge plan` retorna 130 em deferred wave** (`engine/plan.py`, commit `f9e5b48`): `_run_waves_for_subtype` retornava `0` quando uma wave setava `WaveResult.deferred=True`. Caller `run` então pulava o guard `if rc != 0` e marcava a feature como `planned`, destruindo silentemente o estado pausado. Contract do docstring (`0=ok, 130=paused, other=hard gate`) restaurado.
- **A5 — Swift triple-quoted strings no brace counter** (`engine/graph/_body_text.py`, commit `426b278`): brace counter só entrava em triple-quote mode pra Kotlin. Body Swift com `"""` literal contendo `"` ímpar flipava `in_string_double` parity, e o próximo `}` era parseado como código — popping o scope da função prematuramente. Trigger estendido pra `{kotlin, swift}`.
- **A6 — Groovy DSL parens opcionais** (`engine/graph/gradle_deps.py`, commit `56fefae`): regex só cobria forma Kotlin DSL `implementation(project(":x"))` com outer parens. Groovy DSL `implementation project(":x")` (sem parens) silentemente caía fora da dependency closure. Parens externos agora opcionais, whitespace separator aceito.
- **A9 — Tie-breaker determinístico em `find_smallest_common_ancestor`** (`engine/graph/gradle_deps.py`, commit `56fefae`): tie-breaker usava `-ord(c[0])` (inspeciona só primeiro char) — produzia ordem inconsistente com o docstring que promete lexicográfico. Trocado por `key=(in_degree, c)` puro lex.
- **A12 — Root-level `test/` folder reconhecido** (`validators/check_no_behavior_change.py`, commit `a8c5ac4`): heurística `_looks_like_test_file` comparava contra segments tipo `/test/` (leading + trailing slash); paths root-level `test/MockData.kt` caíam no suffix check e eram misclassificados como production code, enfraquecendo o refactor gate. `/` prepended antes do segment match.
- **CR-01 — Implement `try/finally` cobre full critical section** (`engine/implement.py`, commit `0029c59`): C2 fechou o leak parcialmente; CR-01 estende o `try` pra cobrir o cinematic header completo (`read_l1_status`, `current_subtype`, etc.) — qualquer raise antes do dispatch também passa pelo release path agora.
- **CR-02 + MD-01 — Lex-smallest tie-breaker + Groovy closure regression** (`engine/graph/gradle_deps.py`, commit `13559e2`): docstring de `find_smallest_common_ancestor` prometia "lex-smallest among ties" mas a implementação ainda preferia ordem instável quando `in_degree` empatava. Tie-breaker `min(candidates)` puro + regression test cobrindo Groovy DSL com trailing config closure.
- **HG-01 — `_reset_domain_tables` asserta no open transaction** (`engine/graph/builder.py`, commit `3b7dcd3`): `PRAGMA foreign_keys` é no-op dentro de transação (SQLite contract). Adicionado `assert conn.in_transaction is False` no entry pra capturar uso indevido cedo, em vez de pragma silenciosamente ignorado.
- **HG-02 + HG-03 — `current_phase_lock` consulta sentinela; retry reentrant** (`engine/memory/l1.py`, commit `65b8904`): HG-02 — `current_phase_lock` lia `status.json.phase_lock`, mas o sentinela `.phase-lock` é o gate autoritativo após C1/A1. Read agora consulta sentinela primeiro, `status.json` como espelho. HG-03 — branch reentrant de `acquire_phase_lock` lia sentinela exatamente uma vez; se o read race com o writer que ainda não fez fsync, retornava empty e a reentrância falhava. Retry curto com backoff quando sentinela existe mas vazio.

### Changed

- **Doc-sync claude-rules**: corrige smoke checklist execution — hooks PreToolUse/PostToolUse confirmados em subagent context via doc oficial + side-effect persistente; veredito anterior estava furado por capturar só stderr. Veredito final: 4/5 (Check #3 corrigido pra PASS via audit log; Check #2 permanece FAIL por entrega inconsistente do PostToolUse). Gap de observabilidade anotado em `docs/design/04-pending.md`.
- `_VALID_KINDS` do `engine/memory/distiller.py` ganha 6 entries reuse-related.
- `engine/graph/queries.py` Q11 (`find_reusable_helpers`) suporta multi-módulo
  shared via `LIKE 'shared:%'`.

### Refactored

- **TS arrow dedup hoisted to loop start** (`engine/graph/_ts_parser.py`, commit `9680ea8`): pure refactor, behavior unchanged. Duplicate check sentava após body extraction + hashing + tokenization — uma função same-named sombreada por arrow posterior pagava custo full só pra ser descartada. Mover dedup pro topo do loop pula trabalho desperdiçado. Test counts inalterados (31 tests em `tests/unit/test_graph_parsers.py` + `test_reuse_intelligence.py`).

### Tests

- **+38 regression tests** cobrindo os bloqueadores + review findings — `test_memory_l1_phase_lock_atomic.py` (multiprocessing race), `test_implement_lock_release.py` (exception paths), `test_builder_reset_tables.py` (mid-stream failure), `test_plan_deferred_exit_code.py` (rc=130 contract), `test_plan_deferred_state_persisted.py` (MD-02), `test_body_text_swift_triple_quote.py` (A5), `test_gradle_deps_regressions.py` (A6 + A9), `test_check_no_behavior_change_paths.py` (A12), entre outros.
- **Total: 458 tests passing** (vs baseline original v1.1.0 = 367; +91 incluindo as 38 do round bloqueadores + 36 integration do rules system + 17 reuse-intelligence extras).

### Conhecidos limites v1.1

- **Pre-existing**: `tests/integration/test_graph_build_meobonsai.py::test_build_full_creates_meta_schema_version` assertava `meta.schema_version == "1"`, mas `engine/utils/sqlite_io.py:20` declara `SCHEMA_VERSION = "2"` desde o bump da reuse-intelligence schema. Falha não bloqueia rapid lane nem o ship v1.1.0; fix pequeno (ler `sqlite_io.SCHEMA_VERSION` em vez de hardcoded) agendado pra v1.1.1.
- `kmp-migration-candidate` confidence é shallow (token Jaccard, não AST).
  False positives possíveis — apply NUNCA auto-runs; usuário revisa.
- Hook script `.claude/hooks/post-edit-detect-duplications.sh` é escrito
  no init, mas wiring em `.claude/settings.local.json` é manual (opt-in).
- Gradle dependency parsing cobre `implementation(project(...))` e
  variantes comuns. DSL Kotlin avançado ou `includeBuild` pode falhar.

[1.2.0]: https://github.com/thgMatajs/feature-forge/releases/tag/v1.2.0
[1.1.0]: https://github.com/thgMatajs/feature-forge/releases/tag/v1.1.0

## [1.0.0] — 2026-05-29

### Adicionado

#### Fase 1 — Schemas + filesystem (espinha dorsal)

- 9 schemas canônicos (`docs/schemas/{workflow-config, card, memory, graph, inventories, proposed-evolutions, rejected-evolutions, workflow-config-history, capability-labels}.md`)
- 27 decisões locked em `docs/design/01-decisions.md`
- 7 disciplinas universais em `docs/design/07-discipline.md`
- Filesystem layout canônico em `docs/design/05-filesystem-layout.md`

#### Fase 2 — Agents + UX roteiros (cérebros)

- 10 agent prompts: planning-conductor + 9 sub-agents (feature-intake, feature-prd, screen-analysis, contract-planner, tech-spec, task-contract-writer, readiness-reviewer, retrospective, memory-distiller)
- 7 roteiros UX cinemáticos (init, plan, implement, verify, doctor, reconfigure, evolve)
- ~7.000 LOC de markdown

#### Fase 3 — Templates + cards + preset (conteúdo)

- 16 templates canônicos (feature-intake, feature-prd, screen-analysis, bdd, ui-state-spec, navigation-spec, data-contract-spec, analytics-spec, test-strategy, tech-spec, task-breakdown, task-contract, implementation-readiness-review, plan-feature-handoff, evals)
- 12 cards canônicos iniciais (kotlin-language, kmp-shared, compose-screens, swiftui-screens, koin-annotations, skie-bridge, nav3, swiftui-navigation, firebase-auth, firebase-firestore (monolítico), firebase-storage, crashlytics)
- Preset `kmp-mobile-firebase` (depois substituído pelo `kmp-mobile` na 3.5)

#### Fase 3.5 — Refactor backend-agnostic + REST coverage

- Catálogo canônico de capability labels (40 labels v1: 16 singular + 3 latente + 14 auxiliar + 5 reservada)
- `firebase-firestore` monolítico ARQUIVADO; split em `firestore-persistence` + `firestore-realtime` + `firestore-security-rules`
- 6 cards REST novos: `ktor-client`, `rest-api-contract`, `kotlinx-serialization-json`, `room-database`, `datastore-prefs`, `auth-jwt-bearer`
- Preset `kmp-mobile-firebase` ARQUIVADO; substituído por `kmp-mobile` base + 4 backend-candidates (firebase-stack / rest-stack / hybrid / local-only)
- 3 templates refatorados pra agnóstico (`data-contract-spec`, `tech-spec`, `test-strategy`)
- 29 FOLLOWUPs herdados fechados em rodada paralela de 4 sub-agents

#### Fase 4 — Python engine + Bash dispatcher (músculos)

- `bin/forge` Bash dispatcher
- Foundation: `engine/cli.py` + `engine/utils/` + `engine/ui/` + `engine/persona/`
- State: `engine/cards/` + `engine/memory/` + `engine/graph/` + `engine/inventory/`
- Integration: `engine/mcp/` + `engine/vision/`
- 13 commands handlers: init, plan, implement, verify, status, doctor, reconfigure, evolve, undo, graph_cli, memory_cli, raw, ingest
- 57 arquivos Python · ~12.880 LOC

#### Fase 5 — Hooks + validators + tests (pele e validação)

- 9 hooks (5 Claude Code + 3 git wrappers + 1 GitHub Actions workflow)
- 13 validators Python (+2 helpers) com 3-caminhos discipline + JSON tail-on-stdout contract
- Suite pytest: 266 tests (unit + integration + 13 commands smoke + validators)
- Hooks instalação automática no `forge init`

### Mudado

- **Cleanup pós-review crítico** (47 fixes em 6 sub-agents paralelos):
  - Schema drift triplo (memory.l2 key alignment + backend block real + MEM-L1-VL warn)
  - Decision 27 (Ctrl+C pause) honrada de verdade em init.py
  - Phase lock auto-release em plan + implement
  - `apply_proposal_to_l2` raise NotImplementedError nos fall-through (não mais silent drop)
  - `_handle_pre_commit` deriva slug da branch/L1 (gates voltam a bloquear)
  - CI workflow instala forge de verdade
  - Performance: `blast_radius` 250 queries → 1 (~50× speedup), `_persist_*` executemany (3-5×), walk cache compartilhado
  - JUnit5 false positive fix
  - Path traversal block em `normalize_screenshot_path`
  - BOM UTF-8 tolerância em card.yaml
  - Setext + ATX heading mix em merger
  - 13 smoke tests novos pros commands handlers

### Removido

- Preset `kmp-mobile-firebase` (movido pra `presets/.archived/kmp-mobile-firebase-pre-3.5/`)
- Card `firebase-firestore` monolítico (movido pra `cards/.archived/firebase-firestore-monolithic/`)
- Capability labels `realtime-data`, `auth-server` (renomeadas/splitadas)

### Conhecidos limites v1

Ver `docs/design/08-session-handoff.md § Conhecidos limites v1`:

- `forge implement` é stub manual (Apply Mode automatizado em Phase 6)
- `forge init` Cena 7 (Jira/ticketing) não prompted
- 9 kinds de `apply_proposal_to_l2` raise NotImplementedError
- LLM hookup real é Phase 6
- Tree-sitter / AST: regex parsers v1 por design

[1.0.0]: https://github.com/thgMatajs/feature-forge/releases/tag/v1.0.0
