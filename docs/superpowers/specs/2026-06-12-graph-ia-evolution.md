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
  (Kotlin, Swift, TypeScript, Java, Objective-C), a coluna armazena o
  texto entre `{` e `}` matched (inclusive comentários, whitespace, e
  literais). Body extraction reusa `_body_text._SUPPORTED_LANGS` registry.
  XML não tem corpo textual com a mesma semântica — para símbolos XML o
  campo é `NULL` (ver §Risks & Limitations).

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
  passa com count `≥ baseline pré-impl + ~18 tests novos`
  (~7 Java + ~5 XML + ~6 ObjC). Nenhum test pré-existente é removido sem
  justificativa explícita no commit body.

- **AC-10 — `forge verify` passa cascade sem hard fails.** Validators
  canônicos rodam contra o repositório modificado e a cascade sai green.
  Doc-sync (`CHANGELOG.md` Unreleased, `08-session-handoff.md` Última
  atualização, `docs/schemas/graph.md`) está completo antes do commit
  final de release.

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
| AC-9 (pytest baseline + ~18 tests novos) | Task 10.1 |
| AC-10 (forge verify cascade green) | Task 10 (full verification + doc-sync gates) |
