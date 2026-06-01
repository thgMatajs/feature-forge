# Doc-sync — matriz código→docs

Mandamento #6. Ao tocar código vivo, atualize docs no MESMO commit.

## Matriz canônica

| Mudou… | Atualize obrigatoriamente | Considere também |
|---|---|---|
| `engine/<command>.py` (handler) | CHANGELOG, `08-session-handoff.md` | `README.md §Stats`, `06-command-surface.md` |
| `engine/foundation/*` (cli, utils, ui, persona) | CHANGELOG, handoff | — |
| `validators/<x>.py` | CHANGELOG, handoff stats | `07-discipline.md §2` se policy mudou |
| `hooks/*.sh` ou `.claude/hooks/*.sh` | CHANGELOG, handoff | `05-filesystem-layout.md` |
| Novo card em `cards/` | `README §Stats`, handoff | `02-phases.md` |
| Novo template em `templates/` | `README §Stats`, handoff | `02-phases.md` |
| Schema em `docs/schemas/` | CHANGELOG, `README §Schemas` | qualquer template que use o schema |
| `presets/*.yaml` | CHANGELOG, `README §Preset` | `03-influences.md` se rationale muda |
| `docs/design/01-decisions.md` | CHANGELOG `### Changed (load-bearing)` "Revisita decisão N: ..." | sempre append, nunca delete |
| `docs/design/04-pending.md` | risca gap fechado, adiciona novo | handoff `§Conhecidos limites` |
| `agents/*.md` (prompts) | CHANGELOG, handoff | — |
| `docs/ux/*.md` (roteiros) | CHANGELOG | `08-session-handoff.md` se UX muda |
| Release tag | CHANGELOG seção `## [vX.Y.Z]`, `README versão` | handoff `§Estado` |

## Checklist pré-commit

Antes de `git commit`, confirme:

1. [ ] `CHANGELOG.md` tem entrada em `## [Unreleased]` cobrindo a mudança?
2. [ ] `docs/design/08-session-handoff.md` `**Última atualização:**` é hoje
       (ou no commit também) E `**Estado:**` reflete o que mudou?
3. [ ] `README.md` Stats refletem (se stats mudaram — file count, test
       count, LOC, schemas count)?
4. [ ] Rule específico atualizado SE comportamento mudou (ex.: novo
       validator → mention em `testing.md`; novo subagent_type → mention
       em `subagent-workflow.md`)?
5. [ ] Gap em `04-pending.md` fechado/atualizado se aplicável?

Se algum check falhar, dispatch `gsd-doc-writer` (ou `gsd-executor` com
prompt focado em docs) ANTES do commit final.

## Como editar `08-session-handoff.md`

Campos canônicos a tocar:

```markdown
**Última atualização:** YYYY-MM-DD (v1.X.Y — <slug curto>)
**Estado:** v1.X feito; <próximo>
```

A tabela `| Categoria | Status |` ganha linha quando há nova phase/wave.
Não inventar formato — replicar pattern existente.

`§Conhecidos limites` ganha entrada SE shipping com limitação deliberada
(não bug).

## Como editar `CHANGELOG.md`

Segue keep-a-changelog. Sempre tem `## [Unreleased]` no topo. Seções:

- `### Added` — funcionalidade nova
- `### Changed` — comportamento alterado (não-breaking)
- `### Changed (load-bearing)` — quando revisita decisão locked
- `### Fixed` — bug fix
- `### Removed` — funcionalidade removida (anuncia + razão)

Release move `[Unreleased]` → `[vX.Y.Z] - YYYY-MM-DD` e cria novo
`[Unreleased]` vazio acima.

## Quando NÃO precisa doc-sync (exceções enumeradas)

- Typo puro em comentário (sem mudança de semântica do código)
- Reformatação que ferramenta automatizada gera (`black`, `ruff format`)
- Renomear variável local sem afetar API pública
- Edição de string literal já testada que não muda comportamento
  verificável
- Update de version pin em `pyproject.toml` sem mudança de behavior
  (aplica `### Changed` opcionalmente)

Tudo fora desta lista exige doc-sync. Em dúvida: faça sync.

## Bloqueios opt-in disponíveis (futuro)

Documentados aqui mas NÃO ativos. Pra ativar, descomentar bloco específico
em `.claude/hooks/pre-commit-feature-forge.sh`:

### Test-count regression block

```bash
# Bloco opt-in: descomentar quando quiser ativar
# CURRENT_COUNT=$(pytest --collect-only -q 2>/dev/null | tail -1 | awk '{print $1}')
# BASELINE=$(cat .claude/state/test-count-baseline 2>/dev/null || echo 0)
# if [[ "$CURRENT_COUNT" -lt "$BASELINE" ]]; then
#     git log -1 --pretty=%B | grep -q "Removed.*tests because" || {
#         echo "🛑 test count dropped from $BASELINE to $CURRENT_COUNT without justification" >&2
#         exit 1
#     }
# fi
```

Custo: +1-3s por commit. Quando ligar: se perdas silenciosas começarem.

### Validator cascade fail block

```bash
# Bloco opt-in
# CHANGED=$(git diff --cached --name-only | grep -E '^(engine|validators)/' || true)
# if [[ -n "$CHANGED" ]]; then
#     forge verify --quiet || {
#         echo "🛑 validators failed pré-commit" >&2
#         exit 1
#     }
# fi
```

Custo: +5-15s. Quando ligar: se PRs começarem a quebrar verify pós-merge.

### Per-tool-use Mandamento 0 block

Não-implementável de forma estável hoje — depende de Claude Code expor
distinção main-vs-subagent no hook protocol. Anotado em `04-pending.md`
como gap pra detection futura.
