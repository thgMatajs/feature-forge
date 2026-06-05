# Check Secrets Gate — Design Spec (R1.1)

> Data: 2026-06-05 · Status: aprovado (brainstorm via AskUserQuestion)
> Branch: worktree-feat+gate-infra-extract (acumula sobre Phase 0)
> Voz: mentor calmo · Escopo: v1.2-dev — security baseline
> Reusa: validators/_gate_infra.py + validators/_diff.py + validators/_common.py (Phase 0)

## Sumário executivo

feature-forge fechou Phase 0 do plano estratégico de quality gates (extração da
infra reusável: `_gate_infra.py` + `_diff.py` + rename de helpers genéricos em
`_common.py`). Com a infra provada — CC gate continua verde compondo dela — a
primeira onda de gates novos começa por **segurança**, e a wave R1.1 é o
`check_secrets`: barrar secrets verificados (tokens API, credenciais cloud,
JWT signing keys) **antes** de entrarem no histórico do repositório.

Decisão arquitetural central da wave: **per-stage tool split**. `gitleaks` roda
no per-task hook de `forge implement` (rápido, ~100ms, regex-based — não
trava o fluxo iterativo do dev) e `trufflehog --only-verified` roda na cascade
de `forge verify` (mais lento, mas valida ativamente cada candidato contra a
origem). As duas tools cobrem perfis complementares: gitleaks pega o token
sintaticamente plausível antes do commit, trufflehog confirma se ele está
ativo na nuvem antes do merge. Zero false positives ativos é o contrato — o
preço é perder unverifiable (tokens privados sem endpoint público), que
permanecem fora de escopo v1.2-dev.

Escopo deste spec: v1.2-dev. Validator único em `validators/check_secrets.py`,
~150-200 LOC (fino porque compõe da infra Phase 0). Override-justify vive no
commit body via prefix `SECRETS-OVERRIDE: <file>:<line> kind=<token-type> —
<razão>` — sem allowlist persistente em arquivo, auditabilidade via git log.
Hard-fail sempre quando secret verificado bate. Tools missing → warn (mesmo
contrato do CC gate). Sem revisitar decisões locked. Sem novo card, sem novo
template, sem comando novo, sem flag CLI nova.

## Resumo das decisões do brainstorm

Cinco decisões locked durante o brainstorm de 2026-06-05 (via `AskUserQuestion`,
cada eixo discutido isoladamente). Tabela canônica:

| Eixo | Decisão | Alternativas rejeitadas |
|---|---|---|
| Tools per-stage | `gitleaks` no per-task hook (`forge implement`) · `trufflehog --only-verified` na cascade (`forge verify`) | Uma tool só (trufflehog em todo stage — lento demais pro per-task; gitleaks em todo stage — perde verificação ativa) · pre-commit usando ambas (custo somado sem ganho) |
| Verified-only no trufflehog | `--only-verified` ON (default) — zero false positives ativos | `--only-verified` OFF — pegaria unverifiable (privados), mas trade-off de FP era inaceitável pro user (ruído mata adoção) |
| Override location | **Só commit body** via prefix `SECRETS-OVERRIDE` (regex em git log) | Arquivo `.secretsallowlist` persistente (vira whitelist invisível) · flag CLI (viola Decision 10) · arquivo + commit hybrid (complica auditoria sem ganho) |
| On-fail policy | **Hard-fail sempre** — qualquer secret verificado bloqueia | Soft-warn (security não tem soft) · threshold N (não faz sentido pra binário detectou/não-detectou) |
| Tools missing | `result_warn` (não fail) — cascade segue alive | `result_fail` (penaliza dev sem tool instalada — igual ao CC gate) · skip silencioso (some o sinal de "instala isso aqui") |

Nenhuma destas decisões toca as 8 load-bearing — confirmado em §5. Nenhuma
exige "Revisita decisão N" no CHANGELOG.

## Seção 1 — Componentes e arquivos novos

Mapa completo dos arquivos tocados. Lista exaustiva — `writing-plans` consome
isso direto sem ambiguidade.

### Novos arquivos

- `validators/check_secrets.py` (NOVO, ~150-200 LOC) — validator principal.
  Fino porque toda a mecânica de dispatch + override + render 3-caminhos vem
  da infra Phase 0. O específico do gate é apenas: stage selection (per-task
  vs cascade), `cmd_builder` específico por tool, parser JSON da tool, e
  render do 3-caminhos com vocabulário de secrets.
- `tests/validators/test_check_secrets.py` (NOVO) — unit tests do validator.
- `tests/integration/test_secrets_gate_end_to_end.py` (NOVO, marker
  `integration`) — integration tests cascade + per-task.
- `tests/fixtures/secrets/gitleaks_output_sample.json` (NOVO) — fixture de
  output JSON do gitleaks (determinístico, sem rodar a tool real nos unit
  tests).
- `tests/fixtures/secrets/trufflehog_output_sample.json` (NOVO) — paralelo
  pro trufflehog (com `verified=true` em ≥1 entry).
- `tests/fixtures/secrets/file_with_secret.kt` (NOVO) — arquivo-fixture com
  token AWS-style propositalmente plausível (validado pelo regex do gitleaks
  mas com chars invalidados pra trufflehog não bater na origem real).
- `tests/fixtures/secrets/file_with_test_fixture.kt` (NOVO) — arquivo-fixture
  representando o caso de uso legítimo de `SECRETS-OVERRIDE` (commit body
  contém override-justify pra essa linha).

### Arquivos modificados (append, sem reescrita)

- `engine/verify.py` (APPEND no `_DEFAULT_VALIDATORS` — `check_secrets`
  posicionado **após** `check_cyclomatic_complexity`). Justificativa: secrets
  é gate estrutural-de-segurança, mesma "família" do CC (anti-pattern gate),
  fail-fast Decision 23 preservado.
- `engine/implement.py` (APPEND hook per-task chamando `check_secrets` no
  modo `stage="per_task"`, posicionado entre review e commit — mesma posição
  do CC gate). Bypass via env var `NO_SECRETS_GATE=1` logged em
  `.claude/state/secrets-gate-bypass.jsonl`.
- `engine/doctor.py` (APPEND nova categoria `secrets-tools` — 14ª categoria,
  reporta status de `gitleaks` e `trufflehog` + comando de install).
- `docs/schemas/workflow-config.md` (APPEND bloco `secrets-gate:` documentado
  com `enabled`, `ignore-paths`, `per_task.tool`, `cascade.tool`,
  `cascade.only_verified`).
- `docs/design/04-pending.md` (APPEND 3 gaps deferidos — `SECRETS-1` custom
  rules, `SECRETS-2` history scan, `SECRETS-3` webhook on detection).
- `docs/design/07-discipline.md` §2 (APPEND `check_secrets` na cascade após
  `check_cyclomatic_complexity`).
- `CHANGELOG.md` (Unreleased `### Added`) — entrada do gate.
- `README.md` (Stats: validators 15→16, doctor categorias 13→14).
- `docs/design/08-session-handoff.md` (Última atualização + Estado).

### O que NÃO muda

- Sem novo card. Secrets é universal — afeta qualquer feature em qualquer
  linguagem. Não é por-feature.
- Sem novo template. Nenhum dos 18 templates é tocado.
- Sem mudar `engine/cli.py` — sem comando novo, sem flag CLI nova,
  Decision 10 preservada.
- Sem revisitar decisões load-bearing. As 8 ficam intactas (auditoria em §5).
- Sem mexer em `agents/*.md`. Subagent não precisa saber do gate — validator
  roda no engine.
- Sem novo arquivo de allowlist (decisão explícita do eixo override-location).

## Seção 2 — Data flow + composição da infra Phase 0

### Pipeline interno do validator (10 passos)

Quando `check_secrets.validate(project_root, workflow_config, stage)` é
invocado (por cascade ou per-task hook), executa em ordem:

```
┌──────────────────────────────────────────────────────────────────┐
│ 1. Coleta staged files via git_staged_files (Phase 0)            │
│    Sem filtro de extensão — secrets podem estar em qualquer file │
│    (.kt, .swift, .ts, .py, .yaml, .env, Dockerfile, sh, etc.)    │
│                                                                  │
│ 2. Filtra ignore-paths (workflow-config secrets-gate.ignore-paths)│
│    Default ignore: tests/fixtures/secrets/.* (próprios fixtures) │
│    Aplicado via re.search por path relativo.                     │
│                                                                  │
│ 3. Lê commit body via read_commit_body (Phase 0)                 │
│    Best-effort: COMMIT_EDITMSG → git log -1 → "".                │
│                                                                  │
│ 4. Determina stage (per-task vs cascade)                          │
│    - stage="per_task" → TOOL = gitleaks (fast, regex-based)      │
│    - stage="cascade"  → TOOL = trufflehog --only-verified        │
│                                                                  │
│ 5. check_tool_available(TOOL) (Phase 0)                          │
│    - Tool missing → result_warn imediato. Cascade segue alive.   │
│      Mensagem inclui install hint (brew install ...).             │
│                                                                  │
│ 6. dispatch_native_tool(language="any", files, cmd_builder=...)  │
│    cmd_builder injeta args específicos da tool:                  │
│      - gitleaks: `gitleaks detect --no-git --source <staged-dir>│
│         --report-format json --report-path <tmp>`                │
│      - trufflehog: `trufflehog filesystem <files> --only-verified│
│         --json`                                                  │
│    project_root vem do caller. Sem config_template (regras       │
│    default das tools — gap SECRETS-1 cobre custom rules).         │
│                                                                  │
│ 7. Parse output via _parse_gitleaks_json ou _parse_trufflehog_json│
│    Normaliza pra SecretFinding(file, line, kind, snippet,        │
│    verified). Cada tool tem JSON shape próprio; parser local     │
│    converte pro shape comum.                                     │
│                                                                  │
│ 8. apply_overrides(findings, commit_body,                        │
│      prefix="SECRETS-OVERRIDE",                                  │
│      key_pattern=r"(?P<file>\S+):(?P<line>\d+)\s+kind=(?P<kind>\S+)", │
│      fail_key_extractor=lambda f: (f.file, str(f.line), f.kind), │
│      override_key_fields=["file", "line", "kind"],               │
│      value_converters={"line": int})                             │
│    → silenced, surviving, warnings                                │
│                                                                  │
│ 9. Se surviving não-vazio → emite 3-caminhos via render local    │
│    (vide §3, vocabulário de secrets) → result_fail.              │
│    Warnings sempre propagados via campo `why`.                   │
│                                                                  │
│ 10. Else → result_pass (ou result_warn se warnings non-empty mas │
│     surviving vazio — mantém o gate honesto sem bloquear).       │
└──────────────────────────────────────────────────────────────────┘
```

### Composição declarada da infra Phase 0

A intenção da Phase 0 é validada concretamente aqui — cada passo do pipeline
acima nomeia o helper composto:

| Passo | Helper composto | Origem |
|---|---|---|
| 1 | `git_staged_files(project_root, extensions=None)` | `_diff.py` |
| 3 | `read_commit_body(project_root)` | `_diff.py` |
| 5 | `check_tool_available(tool_bin)` | `_gate_infra.py` |
| 6 | `dispatch_native_tool(language="any", files=..., cmd_builder=..., project_root=..., tool_bin=..., benign_nonzero_codes=(1,))` | `_gate_infra.py` |
| 8 | `apply_overrides(findings, commit_body, prefix=..., key_pattern=..., fail_key_extractor=..., override_key_fields=..., value_converters=...)` | `_gate_infra.py` |
| 9, 10 | `result_fail`, `result_pass`, `result_warn`, `make_paths` | `_common.py` |

Nota sobre `benign_nonzero_codes=(1,)`: gitleaks e trufflehog usam **exit
code 1** pra sinalizar "encontrei findings" (não é crash). Sem o flag,
`dispatch_native_tool` reportaria `crashed=True` toda vez que o gate detecta
qualquer coisa. O contrato `benign_nonzero_codes` já existe na infra Phase 0
exatamente pra cobrir esse padrão (eslint usa o mesmo trick).

### Shape do workflow-config — bloco `secrets-gate`

```yaml
secrets-gate:
  enabled: true
  ignore-paths:
    - "tests/fixtures/secrets/.*"   # próprios fixtures do gate
    - ".*\\.lock$"                   # lock files (raramente têm secrets,
                                     # mas heavy regex hits acabam custando)
  per_task:
    tool: gitleaks                   # fast scan no implement hook
  cascade:
    tool: trufflehog
    only_verified: true              # apenas tokens validados ativamente
```

Notas:
- `enabled: false` → validator emite result_warn ("secrets-gate desligado em
  workflow-config — sem cobertura de secret scanning") sem fail. Usado em
  projeto migrando.
- `ignore-paths` é lista de regexes Python (`re.search`) aplicada após o
  staged set ser coletado.
- `per_task.tool` e `cascade.tool` são **fixos** em v1.2-dev (gitleaks /
  trufflehog). Documentado no schema, mas validação aceita só esses dois
  valores. Outras tools entram via gap futuro se justificado.

### Shape do `SecretFinding` (struct interno do validator)

```python
@dataclass(frozen=True)
class SecretFinding:
    file: str        # path relativo ao repo
    line: int        # 1-indexed
    kind: str        # "aws_access_key", "firebase_token", "github_pat", ...
    snippet: str     # primeiros ~40 chars do match (redacted no render)
    verified: bool   # True só quando trufflehog confirmou ativa na origem
```

Parsers individuais (um por tool) em `check_secrets.py` convertem do JSON
nativo de cada tool pro `SecretFinding`. Lista de `SecretFinding` é o input
universal do passo 8 (`apply_overrides`) e do passo 9 (render 3-caminhos).

### GATE-INFRA-1 status (não dispara ainda)

`check_secrets` **NÃO usa** `gate_threshold_lookup` — secrets é binário
(detectou = fail), não tem threshold numérico por linguagem. Logo
GATE-INFRA-1 (parametrização do `gate_threshold_lookup` pra suportar gates
não-CC) permanece YAGNI-deferred até o 2º consumer numérico (provavelmente
Cognitive Complexity em wave R2.2, que herda 80% do CC gate e VAI precisar
parametrizar). Documentar em `04-pending.md` que R1.1 confirmou: parametrização
prematura aqui seria sem caso de uso.

## Seção 3 — Render 3-caminhos canônico

Exemplo literal (modelo pra implementação — vira snapshot test):

```
🛑 Check Secrets gate

O que falhou:
  2 secrets verificados detectados em arquivos staged.

Onde:
  · app/auth/AuthRepository.kt:42 — kind=aws_access_key (verified)
  · src/config/firebase.ts:15 — kind=firebase_token (verified)

Por que importa:
  · Tokens commitados ficam no histórico mesmo após delete — rotação imediata é única mitigação.
  · trufflehog confirmou ATIVA na origem (--only-verified). Não é falso positivo.
  · Decision 23 — cascade fail-fast; check_secrets é gate hard.

Três caminhos pra resolver:

  1) Remover e rotacionar
     Apague a linha do arquivo, ROTACIONE o token na origem (revogue + emita
     novo), e use variável de ambiente / secret manager pro novo valor.
     Token já commitado vive no git history — assume comprometido.

  2) Override-justify (commit body) — apenas pra test fixtures
     Se a string é deliberadamente um fixture (test, doc exemplo), adicione
     ao commit body — EXATAMENTE este formato:

         SECRETS-OVERRIDE: <file>:<line> kind=<token-type> — <razão concreta>

     Ex: SECRETS-OVERRIDE: tests/fixtures/auth/sample.kt:23 kind=aws_access_key — test fixture, AKIA-prefix com chars inválidos

     Validator detecta a linha no commit body e libera APENAS este commit.
     Auditável via `git log --grep='SECRETS-OVERRIDE'`. NÃO é whitelist persistente.

  3) Marcar como fixture
     Mova o arquivo pra `tests/fixtures/secrets/` (já no `ignore-paths` default).
     Use chars deliberadamente inválidos no token (ex: `AKIA00000000FAKE`) pra
     trufflehog --only-verified não bater.

Sem auto-fix aqui — escolha humana.
```

Notas de render:
- Stage per_task (gitleaks) NÃO emite `(verified)` — gitleaks é regex-based,
  não verifica. O annotation no `Onde:` muda pra `kind=<tipo> (unverified — gitleaks)`.
- Stage cascade (trufflehog --only-verified) SEMPRE emite `(verified)` — por
  construção `--only-verified` filtra unverified out, então toda finding que
  chega aqui é verificada.
- `Por que importa` adapta a linha do meio conforme stage: per_task cita
  "gitleaks marcou regex-match"; cascade cita "trufflehog confirmou ATIVA na
  origem".
- O exemplo de override no caminho 2 é literal — fixtures de unit test devem
  validar que esse exato formato é aceito pelo regex.

### Mecânica do override-justify

Idêntica ao CC gate em fluxo:

1. Validator inspeciona commit body via `read_commit_body(project_root)`
   (Phase 0). Em `forge implement` per-task: lê `.git/COMMIT_EDITMSG`. Em
   `forge verify` cascade: fallback `git log -1 --format=%B HEAD`.
2. `apply_overrides(...)` da infra Phase 0 faz match via regex strict +
   loose pass (warnings em malformed). Parâmetros:
   - `prefix="SECRETS-OVERRIDE"`
   - `key_pattern=r"(?P<file>\S+):(?P<line>\d+)\s+kind=(?P<kind>\S+)"`
   - `fail_key_extractor=lambda f: (f.file, str(f.line), f.kind)` — cover
     tuple é (file, line, kind). Linha é convertida via stringify porque
     o `override_key_fields` reflete o named group cru depois do converter.
   - `override_key_fields=["file", "line", "kind"]` — mesma ordem do
     extractor.
   - `value_converters={"line": int}` — força int no campo line antes do
     match, garante que `"42"` no body bate `42` no finding.
3. Match → finding vira `silenced` (logado, não bloqueia). Sem match →
   `surviving` (bloqueia).
4. Override é **por commit, por (file, line, kind)**. Não cobre outros
   findings no mesmo commit; não cobre outros commits; não é whitelist
   persistente em arquivo.
5. Linha malformed (falta `— <razão>`) → warning emitido via mecânica D-008
   da infra (preservada). Override NÃO conta nesse caso.
6. Auditável: `git log --all --grep='SECRETS-OVERRIDE'` lista histórico
   completo. Útil pra retro ("quantos overrides aceitamos nos últimos 3
   meses?").

Override **não** é flag CLI. Vive no commit body. Decisão deliberada — força
o dev a articular razão concreta visível em review.

## Seção 4 — Integration com forge verify e forge implement

### Cascade em `forge verify`

Nova entrada após `check_cyclomatic_complexity` em `_DEFAULT_VALIDATORS` de
`engine/verify.py`. Stage="cascade" → usa trufflehog. Fail-fast Decision 23
preservado: se algum validator anterior falhar (artefato faltando, scope
violation, behavior invented, CC alto), `check_secrets` **nem roda**.

Posicionamento racional:
- CC e secrets são "anti-pattern gates" — detectam algo errado **no código**
  vs validators de schema/artefato. Posicionar juntos preserva ordem
  semântica do cascade.
- Secrets vem depois de CC porque: CC roda em ~segundos por feature (já
  validado), trufflehog cascade pode demorar (verificação ativa contra
  origens externas). Falhar antes em CC poupa o tempo do trufflehog.

Override `validators.fail-fast: false` em workflow-config faz cascade rodar
todos os validators e coletar todos os fails (comportamento existente do
`07-discipline.md §2`). Preservado sem mudança.

### Per-task hook em `forge implement`

Análogo ao CC gate hook. Posição no pipeline:

```
┌──────────────────────────────────────────────────────────┐
│  forge implement <slug>                                  │
│    ↓                                                     │
│  Plan Mode (task contract → subagent)                    │
│    ↓                                                     │
│  Apply Mode (subagent escreve diff)                      │
│    ↓                                                     │
│  Review (post-subagent-validate hook + validators)       │
│    ↓                                                     │
│  ╔════════════════════════════════════════════╗          │
│  ║  CC GATE     (existente, PR #4)            ║          │
│  ║  check_cyclomatic_complexity sobre staged  ║          │
│  ║  Pass → segue                              ║          │
│  ╠════════════════════════════════════════════╣          │
│  ║  SECRETS GATE (novo — após CC)             ║          │
│  ║  check_secrets sobre staged (gitleaks)     ║          │
│  ║  Pass → segue · Fail → 3-caminhos + halt   ║          │
│  ╚════════════════════════════════════════════╝          │
│    ↓                                                     │
│  Commit atômico                                          │
└──────────────────────────────────────────────────────────┘
```

Implementação:
- `engine/implement.py` chama
  `validators.check_secrets.validate(context, stage="per_task")` **como função
  Python**, não subprocess. Evita boot do interpretador a cada task.
- Context inclui: `project_root`, `workflow_config` (já carregado), commit
  body (caminho do COMMIT_EDITMSG já existe no contexto do hook).
- Bypass via env var `NO_SECRETS_GATE=1` — emergência única (build CI
  quebrando por bug no validator, dev precisando shippar fix urgente).
  Logged em `.claude/state/secrets-gate-bypass.jsonl` pra auditoria. **Não**
  é caminho normal de override — pra isso existe `SECRETS-OVERRIDE` no
  commit body.

Decisão deliberada: `implement.py` terá DOIS hooks distintos (CC + secrets),
ambos compostos via mesmo padrão (chamar `validate(...)` como função Python +
checar `result["status"] == "fail"`). Quando R1.2+ chegarem (deps-cve,
duplication, etc.), helper compartilhado `_run_per_task_gates(ctx, gates)`
pode emergir como refactor — mas isso é trabalho futuro, **NÃO scope desta
task**. Princípio Phase 0: extrair quando 2-3 consumers concretos
documentam o padrão.

### Doctor categoria `secrets-tools`

Nova 14ª categoria em `engine/doctor.py`. Output esperado:

```
secrets-tools
  · gitleaks      ✓ found  (8.18.4)
  · trufflehog    — não encontrado
                  install: brew install trufflehog
```

Critério de severidade: ambas missing → warn no doctor. Pelo menos uma
present → info. Doctor não fail por causa disso (mesma filosofia do CC
gate-tools).

## Seção 5 — Testing, doc-sync, decisões, risks

### Testing strategy

Duas camadas: unit tests (validator + parsers em isolamento) + integration
tests (cascade + per-task end-to-end com fixtures reais).

#### Unit tests — `tests/validators/test_check_secrets.py`

| Cenário | Asserção |
|---|---|
| `_parse_gitleaks_json` happy path | Fixture JSON `gitleaks_output_sample.json` → lista `SecretFinding` correta (file, line, kind, snippet, verified=False) |
| `_parse_trufflehog_json` happy path | Fixture JSON `trufflehog_output_sample.json` → idem com `verified=True` na entrada filtrada por `--only-verified` |
| Tool missing → warn | `check_tool_available` retorna False → `result_warn` (não fail). Mensagem inclui install hint |
| Tool crash (non-JSON output) → warn | DispatchResult com `crashed=True` → result_warn com stderr snippet |
| Override válido (per fixture file) | `SECRETS-OVERRIDE: file.kt:42 kind=aws_access_key — fixture` no commit body → finding vira silenced |
| Override malformado (sem `— <razão>`) | Warning emitido via mecânica D-008. Override não conta — finding permanece surviving |
| Override cobre só (file, line, kind) declarado | Outro finding no mesmo commit (file diferente OU line diferente OU kind diferente) NÃO é silenced pelo override |
| `ignore-paths` regex filtra | `tests/fixtures/secrets/file_with_secret.kt` no staged set → não chega no dispatch |
| Stage selection per_task → gitleaks | `cmd_builder` produz cmd com `gitleaks detect ...`, `trufflehog` ausente |
| Stage selection cascade → trufflehog | `cmd_builder` produz cmd com `trufflehog ... --only-verified --json` |
| `--only-verified` injetado quando cascade.only_verified=true | Cmd contém o flag exato |
| Workflow-config `enabled: false` → warn | result_warn "secrets-gate desligado" sem fail |
| 3-caminhos snapshot | Render literal bate template canônico (regression test) — versões per_task e cascade testadas separadamente |
| Multi-finding ordering | Findings emitidos no `Onde:` ordenados por (file, line) — determinístico |

Cobertura alvo: ≥ 12 cenários (mesma faixa do CC gate, ajustada pra ausência
de threshold/delta).

#### Integration tests — `tests/integration/test_secrets_gate_end_to_end.py` (marker `integration`)

| Cenário | Asserção |
|---|---|
| Cascade roda check_secrets após check_cyclomatic_complexity | Ordem de execução observável via mock instrumentation; CC falha → secrets não roda |
| Per-task hook bloqueia commit | Subagent simulado escreveu `file_with_secret.kt`; per-task hook detecta via gitleaks → halt antes do commit. Mensagem 3-caminhos no stderr |
| Per-task hook + override → commit passa | Mesmo setup + commit body contém `SECRETS-OVERRIDE: tests/fixtures/secrets/file_with_test_fixture.kt:N kind=aws_access_key — test fixture` → finding silenced, commit ocorre |
| `NO_SECRETS_GATE=1` bypassa per-task | Env var setado → validator pula, log entry escrito em `.claude/state/secrets-gate-bypass.jsonl` com timestamp + reason |
| Smoke gitleaks real (`skipif` missing) | `pytest.mark.skipif(not shutil.which("gitleaks"))` — roda gitleaks de verdade em fixture, espera fail com kind detectado |
| Smoke trufflehog real (`skipif` missing) | Paralelo pra trufflehog. Fixture com token AWS-style propositalmente inválido (chars FAKE) → trufflehog `--only-verified` NÃO detecta → pass. (Não dá pra testar verified=true em CI sem leak real; documentar limitação no test docstring) |

#### Fixtures novos — `tests/fixtures/secrets/`

- `gitleaks_output_sample.json` — fixture determinístico de output JSON do
  gitleaks. Estrutura real (rule, file, startLine, secret, etc.) com 2
  findings: 1 AWS access key, 1 firebase token.
- `trufflehog_output_sample.json` — paralelo, formato linha-delimitada JSON
  (trufflehog usa JSONL). 1 entry verified=true, 1 entry verified=false
  (testa filtro `--only-verified`).
- `file_with_secret.kt` — código Kotlin contendo string que casa regex de
  AWS access key (`AKIA00000000FAKE0000`). Chars FAKE garantem que trufflehog
  verified=false (não bate na AWS real).
- `file_with_test_fixture.kt` — paralelo com comentário no topo: "//
  fixture pra SECRETS-OVERRIDE test". Path correlato ao override-justify
  exemplo do integration test.

Esses fixtures vivem em `tests/fixtures/secrets/` — já no `ignore-paths`
default do workflow-config (definido no spec). Recursão de "fixture detectado
pelo próprio gate" resolvida estruturalmente.

### Doc-sync (Mandamento #6)

Lista exaustiva dos 8 documentos a sincronizar **no mesmo branch** que
implementa o gate. Padrão idêntico ao CC gate (PR #4):

| Doc | Mudança |
|---|---|
| `CHANGELOG.md` | `## [Unreleased] ### Added` — "Check Secrets gate (`check_secrets`) — per-stage split: gitleaks no `forge implement` per-task hook (fast), trufflehog `--only-verified` na cascade de `forge verify` (deep). Override via `SECRETS-OVERRIDE: <file>:<line> kind=<token-type> — <razão>` no commit body. 3-caminhos on fail." |
| `docs/design/08-session-handoff.md` | Última atualização: 2026-06-XX; Estado: "v1.2-dev — Secrets gate shipping (R1.1)"; tabela `\| Categoria \| Status \|` ganha linha "Secrets gate" |
| `README.md` | Stats: validators 15→16, doctor categorias 13→14, tests baseline → baseline+~16 |
| `docs/schemas/workflow-config.md` | Append bloco `secrets-gate:` documentado com exemplo completo (enabled, ignore-paths, per_task, cascade.only_verified) |
| `docs/design/07-discipline.md` | §2 cascade — adiciona linha do novo validator após `check_cyclomatic_complexity` |
| `docs/design/04-pending.md` | Append 3 gaps deferidos (SECRETS-1, SECRETS-2, SECRETS-3 — detalhados abaixo). Registra também GATE-INFRA-1 confirmação YAGNI até R2.2 |
| `.claude/rules/testing.md` | Mention do validator novo em §"Validators são código" |
| `.claude/rules/reuse.md` | Append exemplo concreto na seção "Infra reusável de validators" — `check_secrets` como 2º consumer da Phase 0 (prova que extração paga). Atualizar tabela API surface se precisar |

### Decisões load-bearing — confirmação de NÃO impacto

As 8 decisões load-bearing (de `.claude/rules/decisions.md`) ficam intactas.
Tabela de auditoria:

| # | Decisão | Status | Razão |
|---|---|---|---|
| 14 | Config scope = um workflow-config por sub-projeto | OK | Bloco `secrets-gate:` vive dentro do workflow-config já existente — não cria novo arquivo |
| 15 | Versioning model = snapshot copy local | OK | Validator é parte do forge engine, viaja no snapshot — sem runtime dep |
| 18 | Skill location = standalone repo | OK | Sem impacto em location |
| 19 | Language = Python core + Bash dispatcher + YAML/MD | OK | Validator em Python, parsers JSON, sem nova linguagem |
| 20 | Persistence = SQLite + arquivos | OK | Gate não persiste estado próprio; lê staged diff + workflow-config + commit body |
| 22 | No runtime deps em outras skills | OK | Tools nativas (gitleaks, trufflehog) são CLIs externas instaladas pelo dev — mesma postura semântica que Detekt/SwiftLint do CC gate. NÃO importamos secret-scanning como library Python |
| 23 | Validator cascade = fail-fast | OK | Gate **respeita** Decision 23: posicionado após `check_cyclomatic_complexity`, gate anterior falha → secrets não roda |
| 27 | Pause = `deferred`; abort = 2-step | OK | Gate não introduz estado novo de feature; respeita pause/abort existentes |

Também NÃO toca:
- Decision 10 (zero flags CLI novos)
- Decisão pra "no whitelist persistente" (override-only-in-commit-body confirma
  a postura geral do projeto)

**Conclusão:** nenhuma "Revisita decisão N" no CHANGELOG. Nenhum hard-block do
pre-commit hook do projeto será triggered por este shipping.

### Risks / open questions deferidos (3 gaps a registrar em 04-pending.md)

Cada item é decisão consciente de não-fazer-em-v1.2-dev, com critério pra
reentrar:

1. **SECRETS-1 — Custom rules per project**. gitleaks aceita regras
   customizadas via `gitleaks.toml`; trufflehog via `--config`. v1.2-dev usa
   **default ruleset** das duas tools — cobertura aceitável pra apps mobile e
   web sem inflar complexity. Adoção custom fica pra v1.3+ se ≥2 projetos
   consumidores pedirem regras específicas (ex.: token interno da empresa com
   formato proprietário). Critério reentrar: pedido empírico documentado.

2. **SECRETS-2 — History scan periódico**. Esta gate é diff-mode (apenas
   staged files no commit atual). Vazamentos no histórico (PR mergeado há 6
   meses contendo token que ainda está ativo) só pegam num `trufflehog git
   --since=6m` periódico. **Out-of-scope v1.2-dev** — vale GitHub Action
   separado no projeto consumidor (forge não orquestra CI). Critério
   reentrar: phase 5+ se forge ganhar componente de CI orchestration.

3. **SECRETS-3 — Webhook/notify on detection**. Quando secret verificado é
   detectado, o ideal seria notificar canal de segurança (Slack #security,
   email security@) automaticamente — assume comprometido até prova em
   contrário. **Out-of-scope v1.2-dev**. Pode entrar em phase 6 (LLM hookup)
   junto com auto-suggest-rotation. Critério reentrar: phase 6 quando notify
   infrastructure existir.

E o registro de confirmação:

- **GATE-INFRA-1 YAGNI confirmation**. Spec confirmou que `check_secrets` não
  precisa de `gate_threshold_lookup` (binário, não-numérico). Defer da
  parametrização permanece correto até R2.2 (Cognitive Complexity) ser
  implementado.

### Critério de aceitação v1 (checklist 10 itens)

1. [ ] `validators/check_secrets.py` existe, 150-200 LOC, passa `ruff check` e
       `pytest tests/validators/test_check_secrets.py` com ≥12 cenários verdes.
2. [ ] Validator compõe da infra Phase 0: usa `dispatch_native_tool`,
       `apply_overrides`, `check_tool_available`, `git_staged_files`,
       `read_commit_body`, `result_pass/fail/warn`. Nenhum helper desses
       é re-implementado localmente.
3. [ ] `engine/verify.py` registra `check_secrets` na cascade após
       `check_cyclomatic_complexity`; integration test confirma posição.
4. [ ] `engine/implement.py` invoca `validate(stage="per_task")` entre review
       e commit; integration test confirma bloqueio pré-commit e bypass via
       `NO_SECRETS_GATE=1`.
5. [ ] `engine/doctor.py` reporta categoria `secrets-tools` com status de
       gitleaks + trufflehog e install hints pras missing.
6. [ ] `docs/schemas/workflow-config.md` documenta bloco `secrets-gate:`
       completo com `per_task.tool`, `cascade.tool`, `cascade.only_verified`,
       `ignore-paths`.
7. [ ] 3-caminhos render bate snapshot test em duas variantes (per_task com
       "unverified — gitleaks", cascade com "verified") — formato canônico
       de `.claude/rules/disciplines.md §1`.
8. [ ] `SECRETS-OVERRIDE` regex casa exemplos válidos, rejeita malformados;
       cobertura de unit test ≥ 5 cenários (válido, sem reason, kind
       diferente, line diferente, file diferente).
9. [ ] `pytest` (suite completa) verde; test count ≥ baseline+~16.
10. [ ] Doc-sync 8 docs (lista em §5) completos; `forge verify` no próprio
        repo passa cascade sem hard fail.

## Apêndice — Próximos passos

Após R1.1 mergeado, R1.2 (`check_deps_cve` com osv-scanner) começa na
**MESMA branch** (per memory feedback `single_branch_for_phased_work` —
acumular waves R1 num único PR reduz overhead de doc-sync e mantém
coerência de release notes). Estimativa cai pra ~1d porque a infra Phase 0
está provada com 2 consumers (CC + secrets), o pattern de stage-split está
documentado, e o template de doc-sync replica idêntico.

Próximo passo imediato após este spec aprovado: `superpowers:writing-plans`
produz implementation plan em `docs/superpowers/plans/` com decomposição em
~8-10 tasks atômicas (validator core → parsers → integração verify →
integração implement → doctor → fixtures → docs). Plan vira input do
`gsd-executor` loop padrão.

Este spec é fonte de verdade. Em conflito entre spec e plan, **spec vence**
(plan precisa ser corrigido). Em conflito entre spec e implementação,
implementação vence apenas se acompanhada de retorno ao spec pra atualização
— sem silent drift.
