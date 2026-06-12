<!-- generated-by: gsd-doc-writer -->
# O que cada arquivo no `.claude/` significa

Quando voce roda `forge init`, ele cria uma pasta `.claude/` na raiz do seu
projeto. Esta pasta e o **coracao da integracao** entre o forge e o seu
codigo: ela guarda a configuracao, os cards, a memoria, o grafo de codigo
e os hooks que mantem tudo sincronizado.

Este guia explica o que cada arquivo faz, por que alguns sao versionados
e outros nao, e o que acontece se voce apagar algo.

> **Veja tambem:**
> - `getting-started.md` — como rodar `forge init`
> - `feature-lifecycle.md` — o pipeline completo de uma feature
> - `daily-workflow.md` — o dia-a-dia usando forge

---

## Sumario

- [Tabela principal](#tabela-principal)
- [Detalhamento de cada arquivo](#detalhamento-de-cada-arquivo)
- [Versionados vs locais — por que essa separacao?](#versionados-vs-locais--por-que-essa-separacao)
- [E se eu quiser versionar algo que nao e versionado?](#e-se-eu-quiser-versionar-algo-que-nao-e-versionado)

---

## Tabela principal

| Arquivo | O que e | Versionado? | Quando muda |
|---|---|---|---|
| `workflow-config.yaml` | Configuracao principal do forge no projeto | Sim | `forge init` (cria), `forge reconfigure` (altera) |
| `cards/` | Catalogo de tecnologias do projeto (cards canonicos) | Sim | `forge reconfigure` -> menu cards |
| `cards/local/` | Cards criados pelo time (overlay local) | Sim | Time adiciona manualmente |
| `inventory/*.yaml` | Design system, i18n, convencoes extraidos do codigo | Sim | `forge reconfigure` ou hooks automaticos |
| `graph.db` | Base de conhecimento do codigo (SQLite) | Nao (gitignorado) | `forge init` (cria), hooks (incremental), `forge reconfigure` (rebuild) |
| `memory/L1/` | Memoria por feature em andamento (WIP) | Nao (gitignorado) | Durante `forge plan` e `forge implement` |
| `memory/L1/archived/` | Sumario de features concluidas | Sim | Quando feature e finalizada |
| `memory/L2-project.yaml` | Memoria compartilhada do time | Sim | `forge evolve` (aceitar proposta) |
| `hooks/*.sh` | Scripts que mantem graph e memoria atualizados | Sim | `forge init` (copia), `forge reconfigure` (atualiza) |
| `proposed-evolutions.yaml` | Fila de propostas de melhoria | Sim | `forge evolve` modifica |
| `forge-version-lock.yaml` | Versao do forge usada no init | Sim | `forge upgrade` |
| `workflow-config-history.jsonl` | Historico de reconfiguracoes | Sim | Cada `forge reconfigure` |
| `.gitignore` | Auto-gerenciado pelo forge | Sim | `forge init` (cria) |

---

## Detalhamento de cada arquivo

### `workflow-config.yaml`

**O que contem:** A configuracao central do forge no seu projeto: cards
ativos, caminhos de features, convencoes, provedores de backend,
configuracao de QA, politica de memoria, e mais dezenas de chaves
organizadas em secoes.

**Por que e versionado:** Ele descreve a configuracao acordada pelo time.
Cada membro precisa da mesma configuracao para que `forge plan` e
`forge implement` funcionem de forma consistente.

**Como e atualizado:** `forge init` cria a versao inicial. Depois, **todo
e qualquer** ajuste passa por `forge reconfigure` — nunca edite na mao a
menos que saiba exatamente o que esta fazendo.

**Se eu apagar:** O forge nao consegue mais identificar a raiz do projeto.
Comandos como `forge plan` e `forge implement` param de funcionar. Solucao:
rode `forge init` novamente (ele detecta que e uma brownfield e entra em
modo de reconfiguracao).

---

### `cards/`

**O que contem:** Uma copia dos **cards canonicos** que o seu time
selecionou durante `forge init`. Cada card descreve uma tecnologia
(Retrofit, Firebase Auth, Koin, Room, Navigation 3, etc.) com:
- Schema de configuracao
- Validadores associados
- Dependencias e conflitos com outros cards
- Contribuicoes de codigo (templates, snippets)

**Por que e versionado:** O time precisa da mesma selecao de cards para que
os validadores rodem consistentemente em todos os ambientes.

**Como e atualizado:** `forge reconfigure` -> menu cards -> adicionar,
remover, ou atualizar cards do canonical. Se um card for atualizado no
forge, o reconfigure mostra o diff e voce decide se aplica.

**Se eu apagar:** `forge doctor` vai reportar cards ausentes. Rode
`forge reconfigure` para restaurar — ele recopia do canonical.

---

### `cards/local/`

**O que contem:** Cards que **seu time criou** para tecnologias proprias
que nao estao no catalogo canonico do forge. Tem o mesmo formato dos cards
canonicos, mas vivem so no seu projeto.

**Por que e versionado:** Sao parte do patrimonio tecnico do time.

**Como e atualizado:** Manualmente — seu time adiciona arquivos YAML aqui
seguindo o schema de cards.

**Se eu apagar:** Perde os cards locais. Da pra recriar se alguem tiver
copia ou se estiver no git.

---

### `inventory/*.yaml`

**O que contem:** Extracoes automaticas do codigo do seu projeto:
- `design-system.yaml` — componentes de design system detectados
- `i18n.yaml` — chaves de internacionalizacao
- `conventions.yaml` — convencoes de codigo detectadas

**Por que e versionado:** Sao a fonte de verdade para o grafo de
conhecimento. Todo membro do time precisa da mesma base.

**Como e atualizado:** Automaticamente por hooks (pos-commit, pos-merge)
ou manualmente via `forge reconfigure` -> "re-extrair inventory".

**Se eu apagar:** O forge recria na proxima extracao automatica ou quando
voce rodar `forge reconfigure`.

---

### `graph.db`

**O que contem:** Um banco SQLite com o **grafo de conhecimento** do seu
codigo: classes, funcoes, chamadas, hierarquias, similaridade entre
arquivos, dependencias entre modulos. E o que alimenta os comandos
`forge graph` (Q1–Q17) e as queries de reuso.

**Por que NAO e versionado:** Cada dev tem branches diferentes. O grafo
precisa refletir o codigo que esta no checkout atual — versionar um SQLite
binario geraria conflitos de merge sem sentido.

**Como e atualizado:**
- `forge init` — construcao inicial
- `forge reconfigure` -> rebuild completo
- Hooks automaticos — atualizacoes incrementais a cada edicao/commit

**Se eu apagar:** O forge simplesmente reconstroi na proxima execucao de
`forge graph`, `forge status`, ou no proximo hook pos-edit. A
reconstrucao leva alguns segundos dependendo do tamanho do projeto.

---

### `memory/L1/`

**O que contem:** A memoria de **features em andamento**. Cada feature
ativa tem uma subpasta com:
- `status.json` — estado atual (planning, implementing, done, blocked...)
- `hypothesis.yaml` — hipoteses e decisoes iniciais
- `history.jsonl` — registro cronologico de tudo que aconteceu

**Por que NAO e versionado:** E dado volatil de trabalho em progresso.
Cada dev pode ter features parciais em estados diferentes. Versionar WIP
polui o historico do git com dados que mudam a cada `forge implement`.

**Como e atualizado:** Durante `forge plan` (cria status.json), durante
`forge implement` (atualiza a cada task), e durante a finalizacao
(transiciona para `done`).

**Se eu apagar:** Perde o estado das features em andamento. Da pra
recomecar com `forge plan {slug}`, mas o historico daquela feature se
perde. **Importante:** os artefatos das features (intake, PRD, specs,
task contracts) ficam em `docs/feature-implementation-workflow/`, nao
aqui — esses estao versionados e seguros.

---

### `memory/L1/archived/`

**O que contem:** Um **sumario compacto** de cada feature concluida:
decisoes principais, metricas, aprendizados. E o que alimenta as queries
de reuso (Q11–Q17 do `forge graph`).

**Por que E versionado:** O sumario de features passadas e patrimonio do
time. Versionar permite buscar "ja fizemos algo parecido antes?" sem
depender do checkout de cada dev.

**Como e atualizado:** Automaticamente quando uma feature transiciona
para `done` — o forge comprime o diretorio L1 da feature em um arquivo
`.summary.yaml` e o move para `archived/`.

**Se eu apagar:** Perde o sumario, mas os artefatos completos da feature
(em `docs/feature-implementation-workflow/`) continuam intactos e
versionados. O `forge graph` perde as queries de reuso relacionadas a
essa feature — um rebuild do grafo nao recupera o que foi apagado.

---

### `memory/L2-project.yaml`

**O que contem:** A **memoria compartilhada do time** — convencoes,
decisoes arquiteturais, padroes que sobrevivem entre features. E escrita
pelo `retrospective-agent` e promovida via `forge evolve`.

**Por que E versionado:** E a cristalizacao do aprendizado coletivo. Todo
membro do time precisa enxergar as mesmas convencoes.

**Como e atualizado:** Propostas sao geradas automaticamente pela
retrospectiva de cada feature. Voce revisa e aceita/rejeita via
`forge evolve`. Cada proposta aceita vira uma entrada no L2.

**Se eu apagar:** Perde a memoria compartilhada do time. O `forge init`
cria um L2 vazio — voce comeca do zero.

---

### `hooks/*.sh`

**O que contem:** Scripts shell que o forge instala para manter o grafo e
a memoria atualizados automaticamente. Sao chamados por:
- **Claude Code hooks** (pos-edicao, pos-ferramenta, inicio de sessao)
- **Git hooks** (pre-commit, pos-commit, pre-push)
- **CI hooks** (PR aberto/mergeado, push para main)

**Por que E versionado:** Todo membro do time precisa dos mesmos hooks
para que a engenharia de conhecimento funcione.

**Como e atualizado:** `forge init` copia os hooks do canonical para
`.claude/hooks/`. `forge reconfigure` atualiza se novos hooks forem
adicionados em versoes mais recentes do forge.

**Se eu apagar:** O grafo de conhecimento para de ser atualizado
automaticamente. Os comandos do forge continuam funcionando, mas as
queries de reuso (`forge graph` Q11–Q17) ficam progressivamente
desatualizadas. Solucao: `forge reconfigure` reinstala.

---

### `proposed-evolutions.yaml`

**O que contem:** A fila de **propostas de melhoria** geradas pelo
`retrospective-agent` e pelos validadores de reuso. Cada proposta sugere
uma evolucao: consolidar helpers duplicados, promover descoberta pra
memoria do time, ajustar configuracao de card, etc.

**Por que E versionado:** As propostas representam trabalho a fazer.
Precisa estar disponivel pra todos os membros do time.

**Como e atualizado:** O `retrospective-agent` adiciona propostas
automaticamente. Voce revisa cada uma via `forge evolve` — ao aplicar
ou rejeitar, a proposta sai da fila.

**Se eu apagar:** Perde as propostas pendentes. Nao quebra nada — o forge
apenas recomeca a acumular propostas na proxima retrospectiva.

---

### `forge-version-lock.yaml`

**O que contem:** A versao do forge que estava ativa quando `forge init`
foi executado. Usado pelo `forge doctor` para detectar drift entre a
versao do engine e a versao que o projeto espera.

**Por que E versionado:** Time todo precisa rodar a mesma versao do forge
para garantir consistencia.

**Como e atualizado:** `forge init` cria. `forge upgrade` (futuro)
atualiza. Se voce atualizar o forge manualmente sem rodar upgrade, o
`forge doctor` avisa sobre a divergencia.

**Se eu apagar:** `forge doctor` reporta que o lock esta ausente e trata
como "versao desconhecida" — nao quebra nada, mas perde a protecao contra
drift de versao.

---

### `workflow-config-history.jsonl`

**O que contem:** Um registro **append-only** de toda modificacao feita
no `workflow-config.yaml`. Cada linha e um JSON com timestamp, SHA256
antes/depois, e qual comando fez a mudanca.

**Por que E versionado:** Auditoria. Se alguem mudou a configuracao em um
branch, voce consegue rastrear quando e por que.

**Como e atualizado:** Cada execucao de `forge reconfigure` adiciona uma
linha.

**Se eu apagar:** Perde o historico de reconfiguracoes. Nao quebra nada —
o forge simplesmente comeca um novo historico vazio.

---

### `.gitignore`

**O que contem:** Regras para manter `graph.db`, checkpoints e dados
volateis de memoria fora do git.

**Por que E versionado:** Todo membro do time precisa ignorar os mesmos
arquivos.

**Como e atualizado:** `forge init` cria. Se voce precisa ajustar, edite
a vontade — o forge so toca nele durante `forge init`, nunca durante
reconfigure. O time precisa combinar as alteracoes.

**Se eu apagar:** `graph.db` e outros arquivos locais passam a ser
trackeados pelo git. O `forge init` recria se voce rodar de novo.

---

## Versionados vs locais — por que essa separacao?

O forge separa o que e **compartilhado** do que e **local** por um motivo
pratico: cada dev trabalha em branches diferentes e tem features parciais
diferentes.

```
.claude/
+-- workflow-config.yaml          versionado — time compartilha
+-- cards/                        versionado — time compartilha
+-- inventory/                    versionado — time compartilha
+-- hooks/                        versionado — time compartilha
+-- memory/
|   +-- L1/
|   |   +-- minha-feature/        NAO versionado — WIP local
|   |   +-- archived/             versionado — features passadas
|   +-- L2-project.yaml           versionado — memoria do time
+-- graph.db                      NAO versionado — depende do checkout
+-- proposed-evolutions.yaml      versionado — fila de trabalho
+-- forge-version-lock.yaml       versionado — acordo do time
```

**Linha geral:** dado **volatil** (WIP, grafo binario) nao e versionado.
Dado **de acordo** (config, cards, memoria consolidada) e versionado.

---

## E se eu quiser versionar algo que nao e versionado?

O `forge init` cria um `.claude/.gitignore` com as regras padrao. Voce
pode edita-lo a vontade — ele e versionado, e o forge nunca o sobrescreve
em `forge reconfigure`.

Se o seu time decidir que quer versionar `graph.db` ou `memory/L1/` por
algum motivo, basta remover as linhas correspondentes do `.gitignore`.

**Antes de fazer isso, considere:**

- `graph.db` e binario e muda a cada edicao no codigo — versionar significa
  conflitos de merge frequentes
- `memory/L1/` contem estado de WIP que varia por dev — versionar significa
  que branches com features parciais vao ter dados de L1 conflitantes

Se ainda assim fizer sentido pro seu time, combinem e ajustem o
`.gitignore`. O forge nao interfere.

---

## Resumo

| Caracteristica | Versionados | Locais (gitignorados) |
|---|---|---|
| Exemplos | workflow-config.yaml, cards/, L2, hooks, inventory | graph.db, memory/L1/WIP |
| Quem ve | Todo o time | So voce |
| Protege contra perda? | Sim (git) | Nao (reconstruivel) |
| Conflito de merge? | Potencial (raro) | Inexistente |
| Tamanho no repo | Pequeno (YAML/JSON) | Variavel (SQLite) |
| Se apagar, recupera? | Depende — alguns rodando forge init/reconfigure | Sim — reconstrucao automatica |
