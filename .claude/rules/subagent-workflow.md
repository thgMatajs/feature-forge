# Subagent Workflow

Como despachar bem. Mandamento 0 diz QUE despacha; este doc diz COMO.

## Qual subagent_type pra quê

| Trabalho | Subagent recomendado | Por quê |
|---|---|---|
| Implementação Python (engine, validators) | `gsd-executor` | atomic commits, disciplina de deviation handling |
| Code review pós-impl | `gsd-code-reviewer` | produz REVIEW.md estruturado com severity |
| Aplicar fixes do review | `gsd-code-fixer` | aplica findings de REVIEW.md com commits atômicos |
| Debug profundo | `gsd-debugger` | scientific method + persistência cross-checkpoint |
| Busca/explore codebase | `Explore` | read-only rápido, protege contexto do orchestrator |
| Pesquisa multi-step | `general-purpose` | catch-all sem disciplina específica |
| Edição de docs (sync, handoff, README) | `gsd-doc-writer` ou `general-purpose` | gsd-doc-writer se houver doc_assignment block; senão general |
| Plano de feature/refactor | `gsd-planner` (via skill writing-plans) | writing-plans skill é o caminho canônico — não dispatch direto |

## Despacho em paralelo

Quando faz sentido (tarefas independentes, sem shared state):

- "Atualizar 3 validators que não dependem entre si" → 3 `Agent` calls em UMA
  mensagem
- "Rules independentes (12 arquivos)" → batches de 3-4 em paralelo
- "Hooks .sh independentes (4 arquivos)" → 4 paralelos OK

Não faz sentido em:

- Feature X depende de refactor Y → sequencial
- Edição do mesmo arquivo → sequencial (overwrites)
- Quando subagent2 precisa do diff produzido por subagent1

Padrão: dispatch paralelo APENAS quando o orchestrator pode reconciliar os
diffs sem conflito.

## Pacote de contexto (recap do orchestrator-persona.md)

Sempre anexe ao prompt do `Agent`:

- TAREFA (1-3 frases, ação concreta + critério de sucesso)
- ARQUIVOS PERMITIDOS PARA EDIT/WRITE (lista explícita)
- ARQUIVOS PARA LER ANTES (CLAUDE.md + rule específico + design doc relevante)
- CRITÉRIO DE SUCESSO TESTÁVEL (pytest path / validator nome)
- ANTI-PADRÕES (não-refator, não-doc-sync se separada, não-load-bearing)
- VOZ mentor calmo se gera artefato
- COMMIT atômico ao final

Sem context-pack, subagent improvisa. Improvisação quebra escopo.

## Anti-padrões

- **Dispatch sem context-pack** — subagent inventa interpretação.
- **Dispatch encadeado quando podia ser paralelo** — desperdício de tempo.
- **Dispatch paralelo quando há ordem** — gera conflito de merge.
- **Re-dispatch sem ler diff anterior** — perde o progresso/contexto do
  subagent original.
- **"Pequeno demais, faço inline"** — VEDADO. Mandamento 0 não tem exceção.
- **Despachar sem critério de sucesso** — subagent acha que "rodou" é
  suficiente.

## Loop de review-fix

Protocolo canônico após implementação:

1. `Agent[gsd-code-reviewer]` com prompt:
   - "Revisa diff de <commit-range>. Foco: <pontos específicos da tarefa>.
     Produz REVIEW.md em `.planning/<phase>/REVIEW.md` com findings classificados."
2. Recebe REVIEW.md → você (orchestrator) lê findings
3. Decisão:
   - **Nenhum finding** → aceita, segue pra verification
   - **Findings high/critical** → `Agent[gsd-code-fixer]` dispatch fix
   - **Push-back ao reviewer** (raro, quando reviewer interpretou errado) →
     re-dispatch com info nova
4. Após fix-dispatch: re-review SE mudanças substanciais; senão segue
5. Verification SEMPRE rola depois (mesmo sem findings)

## Trust-but-verify

Antes de aceitar diff do subagent como "feito":

```bash
git diff --stat HEAD~1..HEAD                                # escopo
git diff HEAD~1..HEAD -- <load-bearing-path>                # leitura full se aplicável
git log -1 --stat                                           # mensagem + arquivos
```

Se desvio (subagent tocou arquivo fora da whitelist do context-pack):

1. Dispatch revert: `Agent[gsd-executor]` com prompt "reverta mudanças em
   <arquivo> mantendo as de <outros>"
2. Re-dispatch task original com whitelist mais explícita

## Overhead reconhecido

Sim, despachar pra typo gera overhead (Agent dispatch + context-pack +
review = ~30-60 segundos pra uma mudança de 1 caractere). É deliberado.

A regra absoluta vale a fricção pra zerar a classe inteira de "side-effect
acidental do orchestrator" — onde o orchestrator pensa que está fazendo
algo trivial mas acaba mexendo em algo load-bearing.

Se a fricção começar a empatar produtividade, anote em
`docs/design/04-pending.md` como gap pra revisitar Mandamento 0 em
versão futura. Mas não burle por conta própria.
