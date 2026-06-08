# Changelog

Todas as mudanças notáveis no feature-forge.

Formato baseado em [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versionamento: [SemVer](https://semver.org/lang/pt-BR/spec/v2.0.0.html).

## [Unreleased]

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
