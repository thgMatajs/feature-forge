# Protocolo — Piloto MeoBonsai IA-first · forge v1.5.0

> Exercício de campo: rodar o feature-forge num projeto KMP real (MeoBonsai),
> em modo IA-first, do install ao QA, transformando fricção em insumo acionável.
> Data: 2026-06-19 · forge: v1.5.0 (tip de main) · alvo: MeoBonsai (worktree sandbox)

## Objetivo

Percorrer o lifecycle completo do forge num projeto real e registrar, sem
maquiar, o que cada etapa faz de fato. O entregável é o relatório de findings
(`report.md` neste mesmo diretório) — insumo pro trabalho de correção depois.
O piloto **não corrige nada** no meio do caminho.

## Topologia

| Repo | Branch | Papel |
|---|---|---|
| MeoBonsai | `pilot/forge-v1.5.0` (worktree em `MeoBonsai-pilot`, a partir da `main`) | Sandbox de execução. Descartável. A branch de trabalho real do projeto fica intocada. |
| feature-forge | `pilot/meobonsai-report-2026-06-19` (a partir da `main`) | Segura protocolo + relatório. Vira insumo commitável/PR pro fix. |

## Jornada (lifecycle completo)

| # | Etapa | O que exercita |
|---|---|---|
| 0 | Estado limpo | Worktree da main; estado fresco, sem resíduo forge |
| 1 | Install | Como um user novo torna `forge` rodável (PATH, README) |
| 2 | Init | Discovery, detecção de stack/backend, preset, conventions, persona, ETA, hooks |
| 3 | Plan | `forge plan <slug>` no modelo AI-first (intent → CC responde via AskUserQuestion) |
| 4 | Graph | `forge graph` Q1-Q17 — reuse intelligence, inventory, blast-radius |
| 5 | Feature | Criação do artefato de feature; cards/templates ativos |
| 6 | Implement | `forge implement` no modelo AI-first |
| 7 | QA | `forge verify` (validators cascade), `forge doctor`, smoke |

## Taxonomia de findings

Cada finding registrado no `report.md` segue:

```
[ID] categoria · severidade · etapa
  Descrição (1-2 linhas)
  Repro: comando exato + estado
  Esperado vs. observado
  forge version: v1.5.0 (<commit>)
  Pointer de fix sugerido (engine/ validators/ docs/)
  Regressão? (cruza com finding do piloto anterior: Bx/Fx/Dx)
```

- **Categorias:** 🐛 bug funcional · 🧱 fricção UX/onboarding · 📄 gap de doc · 💡 melhoria
- **Severidade:** Crítica (bloqueia ou configura setup errado silencioso) · Alta · Média · Baixa
- **Driver:** CC top-level dirige o forge e fecha o loop do intent protocol
  (exit 2 → lê `forge-pending.json` → AskUserQuestion → escreve `forge-response.json`).

## A feature a forjar — data-driven

A feature exata é decidida na etapa 4 (graph/inventory): deixar o
`forge graph`/inventory dizer o que já existe e escolher algo genuinamente
ausente no Design System do MeoBonsai (candidato: um componente cross-platform
tipo `MeoBadge`/`MeoChip`), pra testar a reuse-intelligence de verdade em vez de
forçar um duplicado. Escolher a feature É parte do teste.

## Disciplina

- Só na branch/worktree `pilot/...`; nunca commitar na main do MeoBonsai nem tocar branches de feature ativas.
- Execução no MeoBonsai = direta; escrita do relatório no feature-forge = despachada (Mandamento 0).
- Sem auto-fix: bug encontrado vira finding, não correção no meio do piloto.
- Fidelidade: etapa que falhar/travar vira finding; só paro em bloqueador duro.

## Critério de sucesso do piloto

1. Percorri install→QA registrando o que cada etapa fez de fato.
2. Relatório estruturado no feature-forge com findings acionáveis + status das regressões herdadas.
3. Sei dizer se o modelo AI-first fecha o ciclo end-to-end num projeto real.

## Regressões herdadas a verificar (piloto v1.2 · 2026-06-09)

Checklist do que o piloto anterior reportou — confirmar se foi corrigido em v1.5.0:

- [ ] B1 — `FORGE_VERSION` hardcoded em `bin/forge` vs pyproject (`forge --version`)
- [ ] B2/B7 — detector de rest-stack cego (não cobria `libs.versions.toml`, `@Serializable`, Ktor); instalava firebase-stack errado silenciosamente
- [ ] B3 — `i18n keys: 0` em projeto com strings localizadas
- [ ] B4 — design-system naming pattern inferido errado
- [ ] S4/S5 — `identity.backend-choice` ↔ `backend.provider` sincronizados? Seções órfãs limpas no reconfigure?
- [ ] F1 — binário não está no PATH pós-install; README sem aviso proeminente
- [ ] F2/D6 — ETA ausente no graph build (~140s) + discovery (~90s); parece travado
- [ ] F3 — opção morta `[outro]` no menu de preset
- [ ] F6/S10 — frase de abertura varia entre runs (intencional?)
- [ ] F-reconfigure — persona "mentor calmo" some no reconfigure
- [ ] D1/D2/D3 — README não explica "card", camadas de memory L1/L2/L3, nem exemplifica reuse intelligence
- [ ] D4/D5 — README enterrava que `plan`/`implement` não usavam AI real (era Phase 6); verificar se o modelo AI-first resolveu
- [ ] D7 — hooks instalados sem listar o que cada faz / sem confirmação

## Não exercitado no piloto v1.2 (foco novo aqui)

`forge plan`, `forge graph` (Q1-Q17), `forge doctor`, `forge verify`,
`forge implement` end-to-end no modelo AI-first, cards locais, memory L1/L2.
