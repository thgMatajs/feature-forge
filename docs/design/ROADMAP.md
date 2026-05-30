# ROADMAP — feature-forge pós-v1

> **v1 (2026-05-29):** ~370 arquivos, ~28K LOC, 266 tests, 5 fases entregues. Ver `CHANGELOG.md`.
> Este roadmap documenta o que vem depois — agrupado por **Phase** + cards/labels reservados + items de polish.

## Princípios do roadmap

- **Demand-driven** — phases entram no roadmap real quando há uso concreto que justifique. Sem roadmap inflado.
- **Incremental** — cada phase é um increment usável; não vamos pra v2 sem entregar v1.x antes.
- **Backwards-compatible** — schema migrators via `forge raw migrator-N-to-M` (Decision 9).
- **Auditável** — cada phase fechada vira entry em `CHANGELOG.md`.

---

## Phase 6 — Apply Mode automatizado (próximo major)

**Status:** planned · **Esforço estimado:** L · **Bloqueia:** dogfooding produção

Hoje `forge implement` é stub manual. Phase 6 fecha o loop:

### 6.1 LLM/sub-agent invocation real
- Integrar `engine/plan.py` + `engine/implement.py` com Anthropic SDK (ou similar) para invocar sub-agents reais durante waves
- Schema de comunicação: agent prompt + context pack → response com diff/files/artifacts
- Decisão: rodar via Claude Code Task tool (preferido) vs API direta — TBD em design phase

### 6.2 Apply Mode automatizado
- `forge implement` aplica diff gerado pelo sub-agent em vez de handoff manual
- Pre-commit review automatizado (`pre-commit-reviewer` agent)
- Out-of-scope detection real via diff vs `allowed_files` da task
- 3-caminhos quando out-of-scope: atualizar contract / revert / split nova task

### 6.3 Atomic commit + completion evidence
- `forge implement` commita com mensagem canônica `{TASK-NNNN}: {description}`
- Evidence record em `{feature}/completion-evidence/TASK-NNNN-evidence.json`
- L1 status update automático (`implementing` → `verified` → `done`)

### 6.4 Retrospective auto-trigger
- Cena 14 do roteiro: última task verificada → dispara `retrospective-agent` automaticamente
- Output: `proposed-evolutions.yaml` populado
- Usuário roda `forge evolve` para review

---

## Phase 7 — Tree-sitter / AST parsers

**Status:** planned · **Esforço:** M · **Bloqueia:** projetos com Kotlin/Swift idiomático denso

Hoje `engine/graph/parser_{kotlin,swift,typescript}.py` são regex pragmáticos. Trocar por tree-sitter quando false positives críticos aparecerem em campo:

- `tree-sitter-kotlin` + `tree-sitter-swift` + `tree-sitter-typescript`
- Manter API pública dos parsers (`parse_*_file()` retorna mesma shape)
- Migration: feature-flag em `workflow-config.parsers.engine` (`regex` | `tree-sitter`)

---

## Phase 8 — MCP real connections

**Status:** planned · **Esforço:** M · **Bloqueia:** integração com tooling externo

Hoje `engine/mcp/{jira,linear,github_issues,context7}.py` são stubs que raise NotImplementedError. Phase 8 conecta:

### 8.1 Atlassian MCP (Jira)
- Auth via OAuth/token env var
- `fetch_ticket(id) -> Ticket` (schema canônico já em `engine/mcp/types.py`)
- `list_tickets(filters) -> list[Ticket]`
- `post_comment(id, body)`

### 8.2 Linear / GitHub Issues
- Mesma shape, providers diferentes

### 8.3 Context7
- `lookup_lib(name, version)` + `query(lib, q)`
- Cache TTL conforme `workflow-config.external-docs.cache-ttl-days`
- Privacy-mode honored (refusar enviar nomes/code quando True)

---

## Phase 9 — Cards reservados v1.1+

**Status:** planned · **Esforço:** S por card · **Bloqueia:** projetos com stack alternativa

Catalog reserva 5 labels sem provider v1. Cards a criar conforme demanda:

| Label | Card | Família |
|---|---|---|
| `analytics-pipeline` | `firebase-analytics` ou `amplitude` | observability |
| `graphql-client` | `apollo-kmp` | network |
| `websocket-realtime` | `ktor-websocket` | network/realtime |
| `sse-realtime` | `sse-client` | network/realtime |
| `auth-oauth2-rest` | `oauth2-full-flow` | auth |

Cada card adiciona: `card.yaml` + README + detection signals + agent-contributions + (opcional) validators/templates.

---

## Phase 10 — Cards out-of-scope v1 (legacy support)

**Status:** demand-driven · **Esforço:** S por card

Cards que cobrem stacks legacy/alternativas — entram quando projeto real demandar:

- `hilt-di` (DI Android-only) — adicionar `dependency-injection` como capability conflitante de `koin-annotations`
- `koin-dsl` (DSL runtime Koin) — apenas se MeoBonsai rule for relaxada
- `android-xml-views` (UI legado) — `android-ui` conflitante com `compose-screens`
- `ios-ui-uikit` (UI legado iOS) — `ios-ui` conflitante com `swiftui-screens`
- `navigation2-android` — `navigation-android` conflitante com `nav3`
- `material3` — design system específico (provável out-of-scope mesmo em v2)

---

## Phase 11 — Windows support

**Status:** demand-driven · **Esforço:** M

POSIX-first foi decisão v1. Fallbacks Windows existem (`msvcrt.locking` em `l1.py`/`distiller.py`) mas não validados. Phase 11:

- Validar `_file_lock` Windows em projetos reais
- Substituir `_install_git_hooks` symlinks por `os.link()` ou cópia (Windows sem symlinks por default)
- Path handling cross-platform em hooks bash → Powershell wrappers?
- CI matrix: ubuntu + macos + windows

---

## Phase 12 — Validators expandidos

**Status:** planned · **Esforço:** M

Validators v1 cobrem o essencial mas várias regras ficaram `# TODO Phase 6`:

- **`validate_workflow_config.py`**: 10 RULEs restantes (RULE-003, 005, 007, 009, 012, 014, 015, 016, 017)
- **`validate_memory.py`**: MEM-L1-002/003/004/006/008 + MEM-L2-001/002/004/006/007
- **`validate_analytics_spec.py`** (novo): validar `analytics-spec.yaml` standalone (hoje só via `check_no_invented_behavior` grep)
- **`validate_task_contract.py`**: cross-validation layer vs type

---

## Phase 13 — Marketplace de cards user-contributed

**Status:** v2+ · **Esforço:** XL

Out-of-scope v1 explícito. Quando entrar:

- Decentralized card registry (GitHub-hosted? IPFS?)
- Card signing/verification
- Card scoring (popularity, reliability)
- `forge reconfigure → cards → install from registry`
- Versionamento semver dos cards

---

## Items de polish (não-blocking)

Items menores que não bloqueiam roadmap mas valem fixar quando aparecerem:

- **`forge init` Cena 7 (Jira/ticketing auth prompt)** — adicionar prompt opcional Cena 6.5 + Cena 7 com MCP `complete_authentication`
- **9 kinds de `apply_proposal_to_l2`** — implementar conforme uso real: `distill-l2`, `template-patch`, `agent-prompt-addition`, `new-card-suggestion`, `question-elimination`, `convention-refinement`
- **iOS pbxproj proper parser** — quando regex pragmático falhar
- **`<TBD-user>` em `hooks/ci-pr-ingest.yml`** — substituir pelo owner real do repo canonical quando ativar

---

## Phase ordering — quando cada phase é trigada

| Trigger | Phase prioritária |
|---|---|
| Primeiro projeto real consumindo `forge` | Phase 6 (Apply Mode) — sem isso, é só skill de planning |
| False positives críticos em parser regex | Phase 7 (tree-sitter) |
| Time pede integração Jira | Phase 8 (MCP real) |
| Projeto com GraphQL aparece | Phase 9 — card `apollo-kmp` |
| Projeto legacy aparece | Phase 10 — card específico |
| Windows-only dev pede onboarding | Phase 11 |
| Auditor de compliance roda | Phase 12 (validators expandidos) |
| Comunidade > 5 contribuidores externos | Phase 13 (marketplace) |

---

## Princípio final

> Roadmap é **demand-driven** — não vamos perseguir checkboxes. Cada phase entra quando há projeto real esperando. Até lá, v1 já cobre 80% do valor: planning + scaffolding + validators + memory + graph + 13 commands.

Atualizado: 2026-05-29.
