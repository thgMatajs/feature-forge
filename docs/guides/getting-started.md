<!-- generated-by: gsd-doc-writer -->

# Primeiros passos com feature-forge

> **Nível:** iniciante  
> **Tempo de leitura:** 10 min  
> **O que você terá ao final:** `forge init` rodando no seu projeto mobile, com graph,
> cards e memória do time prontos pra uso.

---

## Sumário

- [O que é feature-forge?](#o-que-é-feature-forge)
- [Pré-requisitos](#pré-requisitos)
- [Instalação](#instalação)
- [Quickstart em 3 passos](#quickstart-em-3-passos)
- [O que o forge init faz no seu projeto](#o-que-o-forge-init-faz-no-seu-projeto)
- [Como um time de 10 devs adota](#como-um-time-de-10-devs-adota)
- [O que é o graph?](#o-que-é-o-graph)
- [Por que cada dev tem seu próprio graph.db](#por-que-cada-dev-tem-seu-próprio-graphdb)
- [Próximos passos](#próximos-passos)

---

## O que é feature-forge?

feature-forge é uma **CLI skill** que orquestra o ciclo de vida completo de
features mobile — do intake à implementação, verificação e retrospective. Ele
não escreve código por você (ainda — o Apply Mode automatizado é v1.2+). O que
ele faz é **estruturar o caos**: transforma uma ideia vaga ("preciso de tela de
login") em artefatos rastreáveis — PRD, specs, tasks, contratos de teste — e
guia a execução task por task com gates de qualidade.

Pense como um **maestro de features**: você continua escrevendo código, mas
nunca mais vai começar uma tarefa sem saber exatamente o que precisa ser feito,
quais arquivos tocar, e como validar que ficou pronto.

Fora da caixa ele atende qualquer stack mobile: KMP, Android nativo (Compose),
iOS nativo (SwiftUI), Web (React). Backend-agnóstico — Firebase, REST, GraphQL,
local-only.

---

## Pré-requisitos

| Requisito | Versão mínima | Pra quê |
|---|---|---|
| Python | 3.11+ | Engine principal (CLI, parsers, validators) |
| git | 2.30+ | Clone, hooks, detecção de mudanças |
| pip | 21+ | Instalação de dependências (pyyaml, pathspec) |
| brew (macOS) | — | Dependências opcionais (gitleaks, trufflehog para `check_secrets`) |

Sistema operacional: macOS (testado) ou Linux. Windows via WSL2 funciona mas
não é o alvo principal.

---

## Instalação

### Via clone do repositório (recomendado)

```bash
git clone <repo-url> ~/Documents/feature-forge
export FORGE_HOME=~/Documents/feature-forge
export PATH="$FORGE_HOME/bin:$PATH"
cd ~/Documents/feature-forge
pip install -e .   # instala em modo editável — dependências locais (pyyaml, pathspec)
forge --version
# → forge 1.2.0
```

Para persistir no shell, adicione as duas linhas de `export` ao seu `~/.zshrc`
ou `~/.bashrc`.

A única dependência externa do Python é `pyyaml>=6.0` e `pathspec>=0.12` —
instaladas automaticamente pelo `pip install -e .`.

---

## Quickstart em 3 passos

### Passo 1: Inicie o forge no seu projeto

```bash
cd ~/code/seu-app-mobile
forge init
```

O init é **interativo e sem flags**. Ele vai:

1. Detectar se o projeto é greenfield (novo) ou brownfield (já existe)
2. Escanear o codebase em busca de cards compatíveis (Firebase, REST, KMP, etc.)
3. Propor o preset `kmp-mobile` com 8 cards canônicos
4. Perguntar quais bundles de backend você quer (firebase-full, rest-with-firebase-telemetry, local-only, custom)
5. Resolver dependências e conflitos entre cards automaticamente
6. Extrair inventário do design system, i18n e convenções do projeto
7. Construir o **graph** do codebase (SQLite — ~10s em projetos de porte médio)
8. Escrever `.claude/workflow-config.yaml` com tudo configurado

### Passo 2: Verifique o status

```bash
forge status
```

Mostra um board com:

- Projeto — preset, cards ativos, última reconfiguração
- Features ativas — slugs, status, tempo desde última ação
- Memória — tamanho L2, contagem L1 ativas/arquivadas
- Evoluções pendentes — propostas de melhoria aguardando revisão
- Atividade recente — últimos 5 eventos

### Passo 3: Rode um health check

```bash
forge doctor
```

Varre 14 categorias de saúde da instalação: config, cards, inventory, memória,
graph, hooks, conectividade. Mostra o que está verde e o que precisa atenção.

> ⏱ Os 3 passos levam menos de 5 minutos. Do zero a um projeto instrumentado.

---

## O que o forge init faz no seu projeto

Depois do `forge init`, seu projeto ganha uma estrutura nova dentro de
`.claude/`:

```
{seu-projeto}/
└── .claude/
    ├── workflow-config.yaml      ← VERSIONADO. Config principal: cards ativos,
    │                               paths, bundles, convenções. Toda mutação
    │                               pós-init passa por `forge reconfigure`.
    ├── cards/                    ← VERSIONADO. Snapshots dos cards canônicos
    │   ├── firebase-auth.yaml      + possíveis cards locais. Cada card tem
    │   ├── compose-ui.yaml         seu YAML com requires/conflicts/templates.
    │   └── local/                ← Cards personalizados do time (não sobrescritos)
    ├── inventory/                ← VERSIONADO. Extratos do código-fonte:
    │   ├── design-system.yaml      componentes de UI, chaves de i18n,
    │   ├── i18n.yaml               convenções de código. Re-extraível via
    │   └── conventions.yaml        `forge reconfigure`.
    ├── graph.db                  ← GITIGNADO. Banco SQLite com o grafo do
    │                               codebase (Q1-Q17). Cada dev tem o seu.
    ├── memory/
    │   ├── L1/                   ← GITIGNADO. Memória por feature em
    │   │   └── archived/           andamento (WIP). Apenas archived/
    │   │                           é versionado (histórico de features).
    │   └── L2-project.yaml       ← VERSIONADO. Memória do time: decisões,
    │                               aprendizados, padrões consolidados.
    ├── hooks/                    ← VERSIONADO. Git hooks que o forge instala
    │   └── post-edit-detect-duplications.sh  (opt-in)
    └── proposed-evolutions.yaml  ← VERSIONADO. Propostas de melhoria do
                                    retrospective automático.
```

**O que é versionado vs gitignorado:**

| Arquivo | Versionado? | Motivo |
|---|---|---|
| `workflow-config.yaml` | Sim | Fonte da verdade da configuração |
| `cards/` | Sim | Reprodutibilidade — todo dev tem os mesmos cards |
| `inventory/` | Sim | Time compartilha o mesmo catálogo de DS/i18n |
| `memory/L2-project.yaml` | Sim | Conhecimento acumulado do time |
| `graph.db` | **Não** | Rebuildável, muda por dev, causaria conflito |
| `memory/L1/` | **Não** | WIP de features ativas — gitignored |
| `memory/L1/archived/` | Sim | Histórico de features concluídas |

---

## Como um time de 10 devs adota

### Dev 1: setup inicial

```bash
cd ~/code/seu-app
forge init
# → responde as perguntas interativas
# → .claude/ é criado com tudo
git add .claude/workflow-config.yaml .claude/cards/ .claude/inventory/ .claude/memory/L2-project.yaml
git commit -m "chore: init feature-forge workflow"
git push
```

### Devs 2 a 10: apenas reconfigure

```bash
git pull
# → .claude/ (versionado) já está no disco
forge reconfigure
# → escolhe "rebuild graph" no menu
# → graph.db é construído localmente
# → pronto
```

O `forge reconfigure` detecta que o `workflow-config.yaml` já existe e pergunta
se você quer rebuildar o graph local. Leva 10 segundos.

### Fluxograma do bootstrap

```
Dev 1                          Dev 2..10
─────                          ─────────
forge init                     git pull
  │                              │
  ▼                              ▼
Escaneia código               .claude/ já existe
  │                              │
  ▼                              ▼
Propõe cards + bundles        forge reconfigure
  │                              │
  ▼                              ▼
Resolve dependências          Menu → "rebuild graph"
  │                              │
  ▼                              ▼
Extrai inventory              graph.db local (10s)
  │
  ▼
Constrói graph.db
  │
  ▼
Commit + Push ──────────────► git pull por todos
```

---

## O que é o graph?

O **graph** é um catálogo pesquisável do seu código, armazenado em SQLite
(`.claude/graph.db`). Ele não substitui seu editor — ele dá à IA (Claude Code)
um mapa rápido do codebase sem precisar ler arquivo por arquivo.

O graph responde a 17 queries canônicas (Q1–Q17):

| Query | Label | O que responde |
|---|---|---|
| Q1 | `similar-features` | Features com estrutura similar à atual |
| Q2 | `blast-radius` | Arquivos impactados por uma mudança |
| Q3 | `orphan-files` | Arquivos sem referência no grafo |
| Q4 | `symbols` | Símbolos definidos em arquivos |
| Q5 | `ds-used-in` | Componentes de Design System em uso |
| Q6 | `i18n-used-in` | Chaves i18n em uso |
| Q7 | `routes` | Rotas e navegação do projeto |
| Q8 | `di-deps` | Dependências de injeção |
| Q9 | `tests-for` | Testes associados a um arquivo de produção |
| Q10 | `commits` | Histórico de commits de um arquivo |
| Q11 | `reusable-helpers` | Helpers reutilizáveis candidatos |
| Q12 | `dup-within-module` | **Reuse intelligence**: duplicatas dentro do módulo |
| Q13 | `dup-cross-module` | Duplicatas entre módulos |
| Q14 | `kmp-migration` | Candidatos a migração KMP |
| Q15 | `near-duplicates` | Near-duplicates |
| Q16 | `redundant-platform` | Plataforma-redundante (Android vs iOS) |
| Q17 | `dup-ts-helpers` | Helpers TypeScript duplicados |

O build do graph é **determinístico** — mesmo código sempre produz o mesmo
graph. Ele usa parsers baseados em regex (não AST real — decisão consciente
v1) para extrair símbolos, dependências e similaridades.

---

## Por que cada dev tem seu próprio graph.db

O `graph.db` é **gitignorado** por design. Três motivos:

1. **Rebuildável** — `forge reconfigure` reconstrói em segundos. Nunca é fonte
   única de verdade.
2. **Sem conflito de merge** — se dois devs tocam os mesmos arquivos, o graph
   de cada um reflete o estado local. Versionar causaria conflito a cada PR.
3. **Compartilhamento pelo versionado** — o que importa pro time
   (`workflow-config.yaml`, `cards/`, `inventory/`, `memory/L2/`) está tudo
   versionado. O graph é só um cache de consulta rápida.

---

## Próximos passos

Agora que o forge está rodando no seu projeto:

| Guia | O que cobre |
|---|---|
| [Comandos do dia a dia](daily-workflow.md) | `forge plan`, `forge implement`, `forge verify`, `forge status` e mais |
| [Lifecycle de uma feature](feature-lifecycle.md) | Fluxo completo: intake → PRD → specs → tech-spec → tasks → implement → verify → retrospective |
| [O que cada arquivo no .claude/ significa](dot-claude-reference.md) | Referência rápida de cada arquivo e diretório que o forge cria |

Dúvidas rápidas: `forge doctor` diagnostica problemas de instalação, e
`forge status` mostra o que está acontecendo no projeto agora.
