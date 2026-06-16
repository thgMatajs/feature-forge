<!-- generated-by: gsd-doc-writer -->
# O que cada arquivo no `.claude/` significa

Quando você roda `forge init`, ele cria uma pasta `.claude/` na raiz do seu
projeto. Esta pasta é o **coração da integração** entre o forge e o seu
código: ela guarda a configuração, os cards, a memória, o grafo de código
e os hooks que mantêm tudo sincronizado.

Este guia explica o que cada arquivo faz, por que alguns são versionados
e outros não, e o que acontece se você apagar algo.

> **Veja também:**
> - `getting-started.md` — como rodar `forge init`
> - `feature-lifecycle.md` — o pipeline completo de uma feature
> - `daily-workflow.md` — o dia-a-dia usando forge

---

## Sumário

- [Tabela principal](#tabela-principal)
- [Detalhamento de cada arquivo](#detalhamento-de-cada-arquivo)
- [Versionados vs locais — por que essa separação?](#versionados-vs-locais--por-que-essa-separação)
- [E se eu quiser versionar algo que não é versionado?](#e-se-eu-quiser-versionar-algo-que-não-é-versionado)

---

## Tabela principal

| Arquivo | O que é | Versionado? | Quando muda |
|---|---|---|---|
| `workflow-config.yaml` | Configuração principal do forge no projeto | Sim | `forge init` (cria), `forge reconfigure` (altera) |
| `cards/` | Catálogo de tecnologias do projeto (cards canônicos) | Sim | `forge reconfigure` -> menu cards |
| `cards/local/` | Cards criados pelo time (overlay local) | Sim | Time adiciona manualmente |
| `inventory/*.yaml` | Design system, i18n, convenções extraídos do código | Sim | `forge reconfigure` ou hooks automáticos |
| `graph.db` | Base de conhecimento do código (SQLite) | Não (gitignorado) | `forge init` (cria), hooks (incremental), `forge reconfigure` (rebuild) |
| `memory/L1/` | Memória por feature em andamento (WIP) | Não (gitignorado) | Durante `forge plan` e `forge implement` |
| `memory/L1/archived/` | Sumário de features concluídas | Sim | Quando feature é finalizada |
| `memory/L2-project.yaml` | Memória compartilhada do time | Sim | `forge evolve` (aceitar proposta) |
| `hooks/*.sh` | Scripts que mantêm graph e memória atualizados | Sim | `forge init` (copia), `forge reconfigure` (atualiza) |
| `proposed-evolutions.yaml` | Fila de propostas de melhoria | Sim | `forge evolve` modifica |
| `forge-version-lock.yaml` | Versão do forge usada no init | Sim | `forge upgrade` |
| `workflow-config-history.jsonl` | Histórico de reconfigurações | Sim | Cada `forge reconfigure` |
| `.gitignore` | Auto-gerenciado pelo forge | Sim | `forge init` (cria) |

---

## Detalhamento de cada arquivo

### `workflow-config.yaml`

**O que contém:** A configuração central do forge no seu projeto: cards
ativos, caminhos de features, convenções, provedores de backend,
configuração de QA, política de memória, e mais dezenas de chaves
organizadas em seções.

**Por que é versionado:** Ele descreve a configuração acordada pelo time.
Cada membro precisa da mesma configuração para que `forge plan` e
`forge implement` funcionem de forma consistente.

**Como é atualizado:** `forge init` cria a versão inicial. Depois, **todo
e qualquer** ajuste passa por `forge reconfigure` — nunca edite na mão a
menos que saiba exatamente o que está fazendo.

**Se eu apagar:** O forge não consegue mais identificar a raiz do projeto.
Comandos como `forge plan` e `forge implement` param de funcionar. Solução:
rode `forge init` novamente (ele detecta que é uma brownfield e entra em
modo de reconfiguração).

---

### `cards/`

**O que contém:** Uma cópia dos **cards canônicos** que o seu time
selecionou durante `forge init`. Cada card descreve uma tecnologia
(Retrofit, Firebase Auth, Koin, Room, Navigation 3, etc.) com:
- Schema de configuração
- Validadores associados
- Dependências e conflitos com outros cards
- Contribuições de código (templates, snippets)

**Por que é versionado:** O time precisa da mesma seleção de cards para que
os validadores rodem consistentemente em todos os ambientes.

**Como é atualizado:** `forge reconfigure` -> menu cards -> adicionar,
remover, ou atualizar cards do canonical. Se um card for atualizado no
forge, o reconfigure mostra o diff e você decide se aplica.

**Se eu apagar:** `forge doctor` vai reportar cards ausentes. Rode
`forge reconfigure` para restaurar — ele recopia do canonical.

---

### `cards/local/`

**O que contém:** Cards que **seu time criou** para tecnologias próprias
que não estão no catálogo canônico do forge. Tem o mesmo formato dos cards
canônicos, mas vivem só no seu projeto.

**Por que é versionado:** São parte do patrimônio técnico do time.

**Como é atualizado:** Manualmente — seu time adiciona arquivos YAML aqui
seguindo o schema de cards.

**Se eu apagar:** Perde os cards locais. Dá pra recriar se alguém tiver
cópia ou se estiver no git.

---

### `inventory/*.yaml`

**O que contém:** Extrações automáticas do código do seu projeto:
- `design-system.yaml` — componentes de design system detectados
- `i18n.yaml` — chaves de internacionalização
- `conventions.yaml` — convenções de código detectadas

**Por que é versionado:** São a fonte de verdade para o grafo de
conhecimento. Todo membro do time precisa da mesma base.

**Como é atualizado:** Automaticamente por hooks (pós-commit, pós-merge)
ou manualmente via `forge reconfigure` -> "re-extrair inventory".

**Se eu apagar:** O forge recria na próxima extração automática ou quando
você rodar `forge reconfigure`.

---

### `graph.db`

**O que contém:** Um banco SQLite (WAL mode) com o **grafo de conhecimento**
do seu código: classes, funções, chamadas, hierarquias, similaridade entre
arquivos, dependências entre módulos. É o que alimenta os comandos
`forge graph` (Q1–Q17, modo interativo ou `--json`) e as queries de reuso.

Em v1.3+, a tabela `symbols` ganhou a coluna `body` com o texto-fonte cru
(comentários preservados) dos símbolos com corpo — Kotlin, Swift, TS,
Java e ObjC. XML symbols ficam com `body NULL`. Isso permite que
assistentes IA inspecionem implementação direto do graph sem abrir o
arquivo-fonte. Schema canônico em `docs/schemas/graph.md §body column`.

**Por que NÃO é versionado:** Cada dev tem branches diferentes. O grafo
precisa refletir o código que está no checkout atual — versionar um SQLite
binário geraria conflitos de merge sem sentido.

**Como é atualizado:**
- `bash .claude/bootstrap.sh` — construção inicial pós-clone (idempotente)
- **Lazy auto-build** — `forge graph` detecta DB ausente/empty e dispara
  build inicial silenciosamente (~30s-2min). Bypass com `--no-auto-build`.
- `forge init` / `forge reconfigure` -> rebuild completo
- Hooks automáticos — atualizações incrementais a cada edição/commit

**Se eu apagar:** O forge simplesmente reconstrói na próxima execução de
`forge graph` (lazy auto-build), `forge status`, ou no próximo hook
pós-edit. A reconstrução leva ~30s-2min em projetos de porte médio.

---

### `memory/L1/`

**O que contém:** A memória de **features em andamento**. Cada feature
ativa tem uma subpasta com:
- `status.json` — estado atual (planning, implementing, done, blocked...)
- `hypothesis.yaml` — hipóteses e decisões iniciais
- `history.jsonl` — registro cronológico de tudo que aconteceu

**Por que NÃO é versionado:** É dado volátil de trabalho em progresso.
Cada dev pode ter features parciais em estados diferentes. Versionar WIP
polui o histórico do git com dados que mudam a cada `forge implement`.

**Como é atualizado:** Durante `forge plan` (cria status.json), durante
`forge implement` (atualiza a cada task), e durante a finalização
(transiciona para `done`).

**Se eu apagar:** Perde o estado das features em andamento. Dá pra
recomeçar com `forge plan {slug}`, mas o histórico daquela feature se
perde. **Importante:** os artefatos das features (intake, PRD, specs,
task contracts) ficam em `docs/feature-implementation-workflow/`, não
aqui — esses estão versionados e seguros.

---

### `memory/L1/archived/`

**O que contém:** Um **sumário compacto** de cada feature concluída:
decisões principais, métricas, aprendizados. É o que alimenta as queries
de reuso (Q11–Q17 do `forge graph`).

**Por que É versionado:** O sumário de features passadas é patrimônio do
time. Versionar permite buscar "já fizemos algo parecido antes?" sem
depender do checkout de cada dev.

**Como é atualizado:** Automaticamente quando uma feature transiciona
para `done` — o forge comprime o diretório L1 da feature em um arquivo
`.summary.yaml` e o move para `archived/`.

**Se eu apagar:** Perde o sumário, mas os artefatos completos da feature
(em `docs/feature-implementation-workflow/`) continuam intactos e
versionados. O `forge graph` perde as queries de reuso relacionadas a
essa feature — um rebuild do grafo não recupera o que foi apagado.

---

### `memory/L2-project.yaml`

**O que contém:** A **memória compartilhada do time** — convenções,
decisões arquiteturais, padrões que sobrevivem entre features. É escrita
pelo `retrospective-agent` e promovida via `forge evolve`.

**Por que É versionado:** É a cristalização do aprendizado coletivo. Todo
membro do time precisa enxergar as mesmas convenções.

**Como é atualizado:** Propostas são geradas automaticamente pela
retrospectiva de cada feature. Você revisa e aceita/rejeita via
`forge evolve`. Cada proposta aceita vira uma entrada no L2.

**Se eu apagar:** Perde a memória compartilhada do time. O `forge init`
cria um L2 vazio — você começa do zero.

---

### `hooks/*.sh`

**O que contém:** Scripts shell que o forge instala para manter o grafo e
a memória atualizados automaticamente. São chamados por:
- **Claude Code hooks** (pós-edição, pós-ferramenta, início de sessão)
- **Git hooks** (pre-commit, pós-commit, pre-push)
- **CI hooks** (PR aberto/mergeado, push para main)

**Por que É versionado:** Todo membro do time precisa dos mesmos hooks
para que a engenharia de conhecimento funcione.

**Como é atualizado:** `forge init` copia os hooks do canonical para
`.claude/hooks/`. `forge reconfigure` atualiza se novos hooks forem
adicionados em versões mais recentes do forge.

**Se eu apagar:** O grafo de conhecimento para de ser atualizado
automaticamente. Os comandos do forge continuam funcionando, mas as
queries de reuso (`forge graph` Q11–Q17) ficam progressivamente
desatualizadas. Solução: `forge reconfigure` reinstala.

> **Bootstrap state detection (v1.3+):** se os symlinks de git hooks em
> `.git/hooks/pre-commit` estão ausentes ou quebrados, o
> `engine/cli._check_bootstrap_state` emite um friendly error orientando
> a rodar `bash .claude/bootstrap.sh`. Subcommands read-only
> (`--version`, `doctor`, `status`, `graph`, `memory`) seguem
> funcionando sem o bootstrap pra não bloquear diagnóstico.

---

### `proposed-evolutions.yaml`

**O que contém:** A fila de **propostas de melhoria** geradas pelo
`retrospective-agent` e pelos validadores de reuso. Cada proposta sugere
uma evolução: consolidar helpers duplicados, promover descoberta pra
memória do time, ajustar configuração de card, etc.

**Por que É versionado:** As propostas representam trabalho a fazer.
Precisa estar disponível pra todos os membros do time.

**Como é atualizado:** O `retrospective-agent` adiciona propostas
automaticamente. Você revisa cada uma via `forge evolve` — ao aplicar
ou rejeitar, a proposta sai da fila.

**Se eu apagar:** Perde as propostas pendentes. Não quebra nada — o forge
apenas recomeça a acumular propostas na próxima retrospectiva.

---

### `forge-version-lock.yaml`

**O que contém:** A versão do forge que estava ativa quando `forge init`
foi executado. Usado pelo `forge doctor` para detectar drift entre a
versão do engine e a versão que o projeto espera.

**Por que É versionado:** Time todo precisa rodar a mesma versão do forge
para garantir consistência.

**Como é atualizado:** `forge init` cria. `forge upgrade` (futuro)
atualiza. Se você atualizar o forge manualmente sem rodar upgrade, o
`forge doctor` avisa sobre a divergência.

**Se eu apagar:** `forge doctor` reporta que o lock está ausente e trata
como "versão desconhecida" — não quebra nada, mas perde a proteção contra
drift de versão.

---

### `workflow-config-history.jsonl`

**O que contém:** Um registro **append-only** de toda modificação feita
no `workflow-config.yaml`. Cada linha é um JSON com timestamp, SHA256
antes/depois, e qual comando fez a mudança.

**Por que É versionado:** Auditoria. Se alguém mudou a configuração em um
branch, você consegue rastrear quando e por quê.

**Como é atualizado:** Cada execução de `forge reconfigure` adiciona uma
linha.

**Se eu apagar:** Perde o histórico de reconfigurações. Não quebra nada —
o forge simplesmente começa um novo histórico vazio.

---

### `.gitignore`

**O que contém:** Regras para manter `graph.db`, checkpoints e dados
voláteis de memória fora do git.

**Por que É versionado:** Todo membro do time precisa ignorar os mesmos
arquivos.

**Como é atualizado:** `forge init` cria. Se você precisa ajustar, edite
à vontade — o forge só toca nele durante `forge init`, nunca durante
reconfigure. O time precisa combinar as alterações.

**Se eu apagar:** `graph.db` e outros arquivos locais passam a ser
trackeados pelo git. O `forge init` recria se você rodar de novo.

---

## Versionados vs locais — por que essa separação?

O forge separa o que é **compartilhado** do que é **local** por um motivo
prático: cada dev trabalha em branches diferentes e tem features parciais
diferentes.

```
.claude/
+-- workflow-config.yaml          versionado — time compartilha
+-- cards/                        versionado — time compartilha
+-- inventory/                    versionado — time compartilha
+-- hooks/                        versionado — time compartilha
+-- memory/
|   +-- L1/
|   |   +-- minha-feature/        NÃO versionado — WIP local
|   |   +-- archived/             versionado — features passadas
|   +-- L2-project.yaml           versionado — memória do time
+-- graph.db                      NÃO versionado — depende do checkout
+-- proposed-evolutions.yaml      versionado — fila de trabalho
+-- forge-version-lock.yaml       versionado — acordo do time
+-- workflow-config-history.jsonl versionado — histórico de auditorias
```

**Linha geral:** dado **volátil** (WIP, grafo binário) não é versionado.
Dado **de acordo** (config, cards, memória consolidada) é versionado.

---

## E se eu quiser versionar algo que não é versionado?

O `forge init` cria um `.claude/.gitignore` com as regras padrão. Você
pode editá-lo à vontade — ele é versionado, e o forge nunca o sobrescreve
em `forge reconfigure`.

Se o seu time decidir que quer versionar `graph.db` ou `memory/L1/` por
algum motivo, basta remover as linhas correspondentes do `.gitignore`.

**Antes de fazer isso, considere:**

- `graph.db` é binário e muda a cada edição no código — versionar significa
  conflitos de merge frequentes
- `memory/L1/` contém estado de WIP que varia por dev — versionar significa
  que branches com features parciais vão ter dados de L1 conflitantes

Se ainda assim fizer sentido pro seu time, combinem e ajustem o
`.gitignore`. O forge não interfere.

---

## Resumo

| Característica | Versionados | Locais (gitignorados) |
|---|---|---|
| Exemplos | workflow-config.yaml, cards/, L2, hooks, inventory | graph.db, memory/L1/WIP |
| Quem vê | Todo o time | Só você |
| Protege contra perda? | Sim (git) | Não (reconstruível) |
| Conflito de merge? | Potencial (raro) | Inexistente |
| Tamanho no repo | Pequeno (YAML/JSON) | Variável (SQLite) |
| Se apagar, recupera? | Depende — alguns rodando forge init/reconfigure | Sim — reconstrução automática |
