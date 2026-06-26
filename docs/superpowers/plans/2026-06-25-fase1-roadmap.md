# Roadmap de execução — Fase 1 (integração mem↔forge)

> Artefato de **sequenciamento de execução**, não design. O design congelado
> e aprovado vive em `docs/superpowers/specs/2026-06-25-mem-integration-design.md`
> (§Fase 1, §Re-roteamento, §Reconciliação, §Migração, §Rename, §Rules two-tier).
> Voz: mentor calmo. Última atualização: 2026-06-25.

## O que esta fase entrega

O `mem` substitui a memória-de-conhecimento nos projetos **consumidores** do
forge. Todos os fluxos do forge re-roteiam pro mem; a state-machine de
lifecycle migra de `.claude/memory/L1/` pra `.claude/forge/state/` (Decisão #1);
o `L2-project.yaml` é migrado one-time via migrador forge-side. O acervo do
forge (graph.db de estrutura de código) e o lifecycle ficam no forge.

Acumula tudo em UMA branch (`feat/mem-integration`) e UM PR (segue a disciplina
de single-branch para trabalho faseado).

## Grafo de dependências (load-bearing)

- **W-RENAME** e **W-STATE** tocam ambas `engine/utils/paths.py` + `engine/memory/l1.py`.
  Não rodam em paralelo: RENAME primeiro (consolida o helper de path que STATE
  reaproveita), STATE depois.
- Toda operação `mem` **no consumidor** depende de **W-VENDOR** (o `forge init`
  copia o binário pra `.claude/bin/mem` e roda o scaffold).
- **W-ROUTE** é o caminho crítico: exige W-STATE (lifecycle moveu de path),
  W-VENDOR (mem presente) e W-MIGRATE (acervo populado).

```
1 W-RENAME ─┐ (serializadas: mesmo paths.py/l1.py)
2 W-STATE  ─┘
3 W-VENDOR ─── pré-requisito do lado-consumidor
4 W-MIGRATE  (precisa W-VENDOR) ← DEFERIDO 2026-06-26; sem brownfield real
5 W-RULES    (precisa W-VENDOR)
6 W-ROUTE    (precisa W-STATE + W-VENDOR + W-MIGRATE)
7 W-AGENTS   (precisa W-ROUTE: contrato find/inbox estável)
```

> **Ordem efetiva pós-deferral:** W-RENAME → W-STATE → W-VENDOR → W-RULES →
> W-ROUTE → W-AGENTS. W-MIGRATE pulado; W-RULES avança pra posição 4.
> W-ROUTE continua dependendo de W-MIGRATE no design — quando W-MIGRATE
> for implementado (brownfield trigger), re-inserir entre W-VENDOR e W-RULES.

## As 7 ondas

| Onda | O quê | Depende de | Gate de aceite | Risco |
|---|---|---|---|---|
| **1 · W-RENAME** | `docs/feature-implementation-workflow` → `docs/forge-specs`; consolida os ~11 literais hardcoded em `paths.feature_workflow_root()` (l1.py, qa/scope.py, graph/*, validators/*, init.py default config) | — | grep-gate: 0 literais `feature-implementation-workflow` sobrando (exceto `docs/superpowers/specs/`, que NÃO renomeia) + pytest verde + doc-sync (~20 docs/agents) | baixo |
| **2 · W-STATE** | L1 state-machine `.claude/memory/L1/` → `.claude/forge/state/` (Decisão #1); `memory_l2_path` deixa de ser destino de escrita; consolida path-root num helper baseado em `forge_state_dir` | W-RENAME (mesmo paths.py/l1.py) | grep-gate: 0 literais `memory/L1` + teste de path + pytest verde. **ADR-note Decisão 20** (persistência) monta aqui no CHANGELOG `### Changed` | médio (11 call-sites) |
| **3 · W-VENDOR** | `forge init` copia `engine/assets/mem/mem` → `.claude/bin/mem` (chmod 755) + roda scaffold do mem (`.claude/memory/`, gitignore `mem.db*`, índice no AGENTS.md) + pin/version | — | fresh `forge init` em fixture → mem presente + scaffold + check de drift do pin no `forge doctor`. **ADR-note Decisão 22** (dep externa vendorizada) | baixo-médio |
| **4 · W-MIGRATE** | **[DEFERIDO 2026-06-26 — YAGNI, sem brownfield]** migrador forge-side L2→mem (TDD): tabela determinística kind→type, preservação de campos sem 1:1 no corpo/tags, `--source migrate:L2:<id>`, sentinel `.migrated-from-l2`, idempotência, `--force` | W-VENDOR | fixture `L2-project.yaml` de 6 buckets → migra → `mem stats` confere; re-run sem `--force` recusa; near-dup não duplica | médio |
| **5 · W-RULES** | redução Tier-0/Tier-1 no init: lê `.claude/rules/*` + `CLAUDE.md` do consumidor, classifica cada fragmento, **PROPÕE a divisão em 3-caminhos** (G1/G2: nunca trucida rule humana em silêncio), aprovado → `mem add` do Tier-1 + enxuga núcleo + escreve RULE_INDEX (~30 linhas) | W-VENDOR | greenfield (nasce no mem) + brownfield (init lê rules existentes) em fixture; nenhuma rule humana some sem aprovação | médio |
| **6 · W-ROUTE** | re-rota os fluxos: `plan`/`implement`/`verify` (lifecycle no novo path + `mem find` por gotchas), `qa` (`mem find` por episodes; nenhum validator chama mem — determinismo), `status` (`mem stats`), `evolve` (proposals-de-conhecimento → `mem inbox add`; reuse-estrutural fica), `doctor` (categoria `mem doctor --json` + drift do pin). `forge memory` vira wrapper fino sobre o mem — **BUG-M1 reproduzido com teste VERMELHO primeiro, depois verde** (a eliminação dos 11 callsites de checkpoint-resume é a hipótese; o teste é a prova) | W-STATE + W-VENDOR + W-MIGRATE | BUG-M1 red→green; cada fluxo roteia; pytest full verde + **review holístico do diff cumulativo** (costuras cross-fluxo) | **alto** |
| **7 · W-AGENTS** | re-rota 5 conductor prompts (`memory-distiller`, `feature-prd-agent`, `planning-conductor`, `contract-planner-agent`, `retrospective-agent`): leitura→`.claude/bin/mem find`, escrita→`mem inbox add`. `memory-distiller` vira gerador de candidatos de inbox (lifecycle-specific); a captura genérica fica na skill `mem-consolidate` — não duplicar. `engine/inventory/` NÃO re-roteia (é estrutura derivada de código, fica no forge) | W-ROUTE (contrato find/inbox estável) | convention-scout contra os prompts REAIS (não o spec); sem duplicação da captura genérica | baixo |

## ADR-note (Decisões 20 e 22) — rider, não onda

A substituição da camada de memória toca o espírito das Decisões 20 (persistence)
e 22 (dependências em outras skills) mas — por análise na spec (§Tratamento das
Decisões 20 e 22) — não as contradiz. Entra como **ADR-note no CHANGELOG
`### Changed`, SEM o ritual formal de "Revisita decisão N"**:
- Decisão 20 (SQLite + arquivos): o rider monta dentro de **W-STATE** (muda onde
  o lifecycle persiste, mas mantém o princípio arquivos+SQLite — o mem.db é SQLite).
- Decisão 22 (sem dep runtime de outras skills): o rider monta dentro de
  **W-VENDOR** (o mem é vendorizado como asset pinado, snapshot fork-and-forget —
  Decisão 15 —, não import runtime; o espírito da 22 se mantém).

## Checkpoints

- **Obrigatório** no fim de W-RENAME (prova o loop impl→review→fix), W-STATE e
  W-ROUTE (as duas de maior risco).
- Nas ondas baixas (VENDOR/MIGRATE/RULES/AGENTS), com o loop já provado, execução
  pode ser autônoma — parar só em problema, block ou scope-fork.
- Cada onda: writing-plans → plan-auditor (gsd-code-reviewer) → subagent-driven-development → review → fix-loop → verde → doc-sync.

## Fora de escopo (Fase 2 / follow-on)

Enriquecimento de rules (web/init-enrich, evolve→rules, `rules-update`,
version-awareness) e extensão de schema do mem (campos nativos pra
`confidence`/`provenance`/`expires_at`). Ver spec §Fase 2 e §Fora de escopo.
