---
title: GRAPH-IA — Codebase graph evolution for AI consumption + legacy language coverage
date: 2026-06-12
status: retroactive-spec (plan já escrito, spec endereça gap de cobertura formal)
plan: docs/superpowers/plans/2026-06-12-graph-ia-evolution.md
release-target: v1.3.0
revisita: nenhuma decisão locked
---

# GRAPH-IA — Codebase graph evolution for AI consumption + legacy language coverage

> **Tipo:** retroactive spec. Plano já estava escrito; este documento formaliza
> o contrato. Origem: escopo do trabalho cresceu além de quick-fix e merece
> cobertura formal análoga aos demais specs em `docs/superpowers/specs/`.
> **Data:** 2026-06-12.
> **Plano associado:** `docs/superpowers/plans/2026-06-12-graph-ia-evolution.md`.
> **Release target:** v1.3.0 (bump menor).

## Goal

Evoluir o codebase graph do forge em duas frentes paralelas que compartilham
infraestrutura — `engine/graph/` + persistência SQLite — mas atendem
necessidades distintas:

1. **IA-ready.** Adicionar coluna `body` em `symbols` para expor texto-fonte
   cru via `forge graph` e introduzir flag `--json` no comando para consulta
   non-interactive. O modelo (Claude Code, outros assistants) passa a obter
   o corpo da função pelo graph em vez de ler o arquivo inteiro — economiza
   tokens de contexto e mantém o consumo determinístico contra o estado
   indexado.
2. **Cobertura legado.** Adicionar parsers regex-based para Java, XML
   (layouts e resources Android), e Objective-C (legado mobile). Projetos
   que misturam linguagens recebem a mesma cobertura de graph que hoje
   existe para Kotlin/Swift/TypeScript, sem aumentar a superfície de
   dependências externas (regex stdlib, sem tree-sitter).

As duas frentes saem juntas em v1.3.0 porque compartilham a mesma migration
de schema (`body` column atinge todas as linguagens) e o mesmo registro de
extensões (`_LANGUAGE_EXTENSIONS`, `_GRAPH_EXTENSIONS`, `_SUPPORTED_LANGS`).
Separá-las geraria duplicação de doc-sync e dois ciclos de release com
escopo artificialmente menor.

## Non-goals (explicitamente fora de escopo)

- **Tree-sitter parsers.** Regex suficiente para a cobertura legada
  pretendida; tree-sitter entra em release futuro quando precision exigir.
- **MCP server.** Modelo consulta via `forge graph --json` (stdout JSON).
  Servidor MCP é decisão arquitetural separada e fora deste contrato.
- **Call graph completo para Objective-C.** Parsing de `[obj selector]`
  exige tracking de tipos não disponível via regex; ObjC entrega símbolos +
  imports + protocols, sem call edges.
- **Call graph preciso para qualquer linguagem.** A precisão atual do graph
  (regex-based) é mantida; este plano não tenta aprimorá-la.
- **Bump de `SCHEMA_VERSION`.** A coluna `body` é adicionada via
  `ALTER TABLE` idempotente (`_ensure_graph_body_column`); DBs existentes
  migram em-place sem rebuild. SCHEMA_VERSION fica reservado para mudanças
  estruturais que não podem ser feitas por ALTER incremental.
- **Visualização gráfica.** Sem renderização (D3.js, mermaid, etc.).
  Consumo é via CLI + JSON.

## Acceptance Criteria

Cada AC abaixo é contrato verificável. Texto descreve o estado final
observável, não a tarefa que produz o estado. A tabela em §Coverage cruza
ACs com as tasks do plano.

- **AC-1 — `symbols.body` column existe em todos os DBs do graph.**
  Bancos novos criados pós-upgrade contêm `body TEXT` na tabela `symbols`.
  Bancos existentes (criados em versões anteriores) recebem a coluna via
  `ALTER TABLE symbols ADD COLUMN body TEXT` executado idempotentemente
  por `_ensure_graph_body_column`. Re-execução do helper em DB já migrado
  é no-op.

- **AC-2 — `symbols.body` contém texto-fonte cru com comentários
  preservados.** Para todas as linguagens com corpo delimitado por chaves
  (Kotlin, Swift, TypeScript, JavaScript, Java, Objective-C), a coluna
  armazena o texto entre `{` e `}` matched (inclusive comentários,
  whitespace, e literais). Body extraction reusa `_body_text._SUPPORTED_LANGS`
  registry. XML não tem corpo textual com a mesma semântica — para símbolos
  XML o campo é `NULL` (ver §Risks & Limitations).

  **Nota pós-fix-pack (PR #16, T-N-020):** o registry canônico após Wave A
  é `_SUPPORTED_LANGS = {kotlin, swift, typescript, javascript, java, objc}`
  (XML fora por design — body extraction brace-matched não se aplica a
  markup). Antes da Wave A, `_mask_strings_and_comments` vivia em
  `parser_objc.py` e Java/Kotlin re-implementavam variantes; P-N-004
  promoveu pra `_body_text.py` consolidando a máscara em todos os parsers.

- **AC-3 — `forge graph --json <query>` retorna JSON estruturado em stdout
  sem prompt interactivo.** A flag `--json` é reconhecida ao lado do
  argumento de query. Aliases short (`q1`..`q17`, `r`), labels textuais, e
  numeric keys (`1`..`17`) são todos válidos como identificador de query.
  Output é JSON parseável (`json.loads` válido) escrito em stdout; stderr
  reservado para erros. Modo interactivo (`forge graph` sem `--json`)
  continua disponível e inalterado.

- **AC-4 — Java parser extrai estrutura completa.** `engine/graph/parser_java.py`
  expõe `parse_java_file(text: str, path: str) -> JavaFileInfo` com:
  package declaration, imports (incluindo wildcards), classes/interfaces/
  enums/records (top-level e nested), methods/constructors com body text e
  metadata de reuse-intelligence (visibility, signature, line range).
  Constructor é distinguido de method via comparação de nome com classe
  enclosing (heurística regex, ver §Risks).

- **AC-5 — XML parser extrai símbolos Android-style.**
  `engine/graph/parser_xml.py` expõe `parse_xml_file(text: str, path: str) -> XmlFileInfo`
  com: view IDs declarados (`@+id/...`), classes referenciadas
  (tag fully-qualified e atributos `android:name`/`class=`), variáveis de
  data binding, resource keys (string/dimen/color/etc.), e expressões de
  binding action (`@{...}` com método invocado).

- **AC-6 — Objective-C parser extrai símbolos + imports, sem call graph.**
  `engine/graph/parser_objc.py` expõe `parse_objc_file(text: str, path: str) -> ObjcFileInfo`
  com: `#import` e `@import` declarations, `@interface` / `@protocol` /
  `@implementation` blocks, methods (instance `-` e class `+`),
  properties (com attributes `nonatomic`, `strong`, etc.). Mensagens
  enviadas (`[obj selector]`) explicitamente NÃO geram call edges.

- **AC-7 — Novas extensões registradas em todos os pontos de discovery.**
  `.java`, `.xml`, `.m`, `.mm` aparecem em `_LANGUAGE_EXTENSIONS`
  (`engine/graph/builder.py`), `_GRAPH_EXTENSIONS` (`engine/ingest.py`),
  `_SUPPORTED_LANGS` (`engine/graph/_body_text.py`, exceto `xml` que não
  tem body extraction), e no `case` match de
  `hooks/post-edit-codebase-graph.sh`. Build full e incremental dispatch
  os novos parsers via `_persist_java`, `_persist_xml`, `_persist_objc`.

- **AC-8 — Documentação orienta IA a consultar o graph.** `AGENTS.md` (ou
  `CLAUDE.md`, conforme decisão na execução) ganha seção dedicada
  instruindo o modelo a consultar `forge graph --json <q>` antes de ler
  arquivos-fonte quando a pergunta cabe nas queries Q1–Q17. Inclui
  exemplos canônicos de uso.

- **AC-9 — pytest baseline mantida com cobertura nova.** Suite completa
  passa com count `≥ baseline pré-impl + 84 tests novos em arquivos novos
  do PR` (Java 19 + ObjC 25 + XML 13 + bootstrap 6 + lazy 6 + json 9 +
  migrations 5 + integration 1). Nenhum test pré-existente é removido sem
  justificativa explícita no commit body.

  **Nota pós-fix-pack (PR #16 master review, 2026-06-16):** o número
  declarado originalmente nesta AC era "+35 tests novos" — contagem
  imprecisa carregada do plano. Validação `grep -c '^def test_'` nos 8
  arquivos novos do PR confirma 84 testes. Wave A+B+C fix-pack pós-review
  somou cobertura nova em arquivos preexistentes (`test_parser_objc.py`
  14 → 25, `test_parser_xml.py` 7 → 13, `test_parser_java.py` 9 → 19,
  `test_migrations.py` 2 → 5), levando a delta full suite de
  +71 (1548 → 1619). Este texto agora reflete o pin correto pós-fix-pack.

- **AC-10 — `forge verify` passa cascade sem hard fails.** Validators
  canônicos rodam contra o repositório modificado e a cascade sai green.
  Doc-sync (`CHANGELOG.md` Unreleased, `08-session-handoff.md` Última
  atualização, `docs/schemas/graph.md`) está completo antes do commit
  final de release.

- **AC-11 — Onboarding UX (bootstrap detection + lazy graph build):**
  - `bash .claude/bootstrap.sh` builda graph.db + inventory cache one-shot pós-clone (Step 6 do bootstrap)
  - `engine/cli.py` detecta `.git/hooks/pre-commit` symlink ausente/quebrado E emite friendly error com instrução "Rode: bash .claude/bootstrap.sh" (exit 1)
  - Detection skipada pra `--version`, `--help`, `doctor`, `bootstrap` subcommands (não bloqueia comandos read-only/help)
  - `forge graph` (interactive ou `--json`) detecta `graph.db` ausente/empty E auto-builda antes de executar query
  - Flag `--no-auto-build` desativa lazy build (uso CI/scripts determinísticos)
  - 8 tests novos cobrindo: detection (4) + lazy build (4)

## Risks & Limitations

- **Body column null-safety em consumers existentes.** A coluna `body`
  passa a co-existir com `body_hash` e `body_tokens` em `symbols`.
  Consumers que façam `SELECT *` recebem a nova coluna no result tuple e
  precisam tolerar a posição extra. Mitigação: queries canônicas usadas
  pelos handlers já selecionam colunas explícitas; risco residual é em
  scripts ad-hoc fora do core. Documentar a mudança em
  `docs/schemas/graph.md` reduz a chance de surpresa.

- **XML body extraction não aplicável.** Símbolos extraídos do XML
  (view IDs, class refs, binding vars, resource keys) não correspondem a
  blocos textuais brace-delimited. A coluna `body` para esses símbolos
  fica `NULL` por design. Documentado na schema doc para que consumers
  IA não infiram body ausente como bug.

- **Heurística regex para constructor Java.** Constructor é detectado por
  comparação de nome do método com o da classe enclosing. Edge cases
  conhecidos: classes aninhadas com mesmo nome do enclosing podem gerar
  falso positivo (método interpretado como constructor da inner). Casos
  são raros em Java idiomático; aceitável para v1.3 com follow-up
  ticket pra tree-sitter caso se manifeste em pilot.

- **Objective-C sem call graph.** Q4 (symbols) e Q11-Q15
  (reuse-intelligence) funcionam para ObjC, mas Q2 (blast-radius) entrega
  cobertura incompleta — referenciadores via `[obj selector]` não são
  detectados. Limitação assumida; usuário que precisa de blast-radius
  completo em ObjC continua dependendo de leitura manual.

- **`SCHEMA_VERSION` não muda.** A migration via `ALTER TABLE` mantém
  compat retroativa com DBs já em uso (formato v2). Se mudanças de
  schema futuras não couberem em ALTER incremental, o bump de
  SCHEMA_VERSION deve acontecer em release separada com rebuild
  document — fora do escopo de v1.3.

- **Bootstrap setup é per-machine, não per-clone (AC-11):** symlinks
  `.git/hooks/` não são versionados — cada dev precisa rodar
  `bash .claude/bootstrap.sh` uma vez. Detection no CLI cobre
  forgetfulness com friendly error.

- **Lazy graph build na primeira invocação é lento (AC-11):** ~30s-2min em
  projetos médios; bootstrap one-shot evita isso. CI usa `--no-auto-build`
  pra desativar o auto-build e manter scripts determinísticos.

## Coverage

Cruzamento AC × Tasks (ver `docs/superpowers/plans/2026-06-12-graph-ia-evolution.md`
para detalhe dos steps):

| AC | Coberto por |
|----|-------------|
| AC-1 (body column existe em DBs novos e migrados) | Task 1 (migration + persist + parser body field) |
| AC-2 (body = texto-fonte cru com comentários) | Task 1 + Task 9 (schema doc) |
| AC-3 (`forge graph --json` non-interactive) | Task 3 (CLI flag + smoke test) |
| AC-4 (Java parser) | Task 4 (parser + tests) |
| AC-5 (XML parser) | Task 5 (parser + tests) |
| AC-6 (ObjC parser, sem call graph) | Task 6 (parser + tests) |
| AC-7 (extensões registradas) | Task 7.1–7.9 (builder, incremental, ingest, _body_text, hook) |
| AC-8 (instrução pro modelo) | Task 8 (AGENTS.md/CLAUDE.md) |
| AC-9 (pytest baseline + 84 tests novos em arquivos novos do PR: Java 19 + ObjC 25 + XML 13 + bootstrap 6 + lazy 6 + json 9 + migrations 5 + integration 1; full suite +71 pós Wave A+B+C) | Task 10.1 |
| AC-10 (forge verify cascade green) | Task 10 (full verification + doc-sync gates) |
| AC-11 (onboarding UX — bootstrap detection + lazy graph build) | Task 9.5 |
