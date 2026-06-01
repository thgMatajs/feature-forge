# Smoke Checklist (one-time, post-bootstrap)

5 verificações manuais pra confirmar que o rules system está vivo.

Execute **uma vez** após rodar `bash .claude/bootstrap.sh` pela primeira vez.

## 1. SessionStart hook injeta orientação?

- Abre sessão Claude Code nova no repo.
- Confirma que o início da conversa tem (no contexto inicial, antes do
  primeiro prompt seu):
  - `🔨 feature-forge — orientação de sessão`
  - Linha "Última atualização handoff"
  - Mandamento 0 lembrete

✅ se aparece. ❌ se não:
- `cat .claude/settings.json` — `SessionStart` está registrado?
- `ls -la .claude/hooks/session-start-orientation.sh` — exec?
- `bash -n .claude/hooks/session-start-orientation.sh` — sintaxe OK?

## 2. PostToolUse drift hook dispara em edit de arquivo "vivo"?

- Pede ao Claude (na sessão): "Despacha um subagent pra adicionar um
  comentário inócuo em `engine/cli.py` na primeira linha (algo tipo
  `# smoke test {{date}}`)".
- Após o dispatch concluir, confirma stderr contém:
  - `📝 doc-drift`
  - Listagem de docs a sync

✅ se aparece. ❌ se não:
- `cat .claude/settings.json` — `PostToolUse` registrado com matcher correto?
- `cat .claude/state/drift-warned.json` — apareceu entrada?

(Depois reverte: `git checkout engine/cli.py`.)

## 3. PreToolUse load-bearing hook dispara em edit de doc load-bearing?

- Pede: "Despacha subagent pra adicionar nota dummy no fim de
  `docs/design/00-vision.md`".
- Confirma stderr contém:
  - `🛑 LOAD-BEARING edit`
- Confirma audit log:
  - `cat .claude/state/load-bearing-edits.jsonl | tail -1`
  - Deve ter linha JSON com timestamp + file + tool.

✅ se ambos. ❌ se não — debug similar ao #2.

(Reverte: `git checkout docs/design/00-vision.md`.)

## 4. Pre-commit hard block dispara em `01-decisions.md` sem ceremony?

```bash
# Simula edit sem ceremony
echo "# probe" >> docs/design/01-decisions.md
git add docs/design/01-decisions.md
echo "## probe Unreleased" >> CHANGELOG.md
git add CHANGELOG.md
git commit -m "probe" 2>&1 | head -20
```

Expected: exit 1 com mensagem contendo "BLOCK" e "Revisita decisão".

Agora com ceremony:

```bash
# Cleanup probe
git restore --staged docs/design/01-decisions.md CHANGELOG.md
git checkout docs/design/01-decisions.md CHANGELOG.md

# Re-stage com ceremony
echo "# probe" >> docs/design/01-decisions.md
git add docs/design/01-decisions.md
echo "## Unreleased" >> CHANGELOG.md
echo "- Revisita decisão 99: probe — testing hard block" >> CHANGELOG.md
git add CHANGELOG.md
git commit -m "probe"
```

Expected: commit passes.

Cleanup: `git reset --soft HEAD~1` + revert dos arquivos.

✅ se ambos comportamentos. ❌ se inverso:
- `bash -n .claude/hooks/pre-commit-feature-forge.sh` — sintaxe?
- `.git/hooks/pre-commit` é symlink pra `hooks/git-pre-commit`?

## 5. Mandamento 0 — modelo dispatcha pra mudança trivial?

- Pede: "Quero adicionar um espaço em branco no final do README.md.
  Faça."
- Observa: o orchestrator (sessão principal) PROPÕE dispatch subagent?
  Ou tenta `Edit` direto?

✅ se dispatch. ❌ se Edit direto:
- Confirma CLAUDE.md foi carregado (ler topo do contexto da sessão)
- Confirma `.claude/rules/orchestrator-persona.md` é referenciado em
  CLAUDE.md
- Reset da sessão, tenta de novo

Se persistente: é sinal que CLAUDE.md root precisa de Mandamento 0 mais
forte. Ajuste no `CLAUDE.md` e re-teste.

## Resultado esperado

5/5 passam = sistema vivo. Marque a data abaixo:

> **Última execução do checklist:** YYYY-MM-DD — N/5 passou.
> Observações:

(Update após cada execução manual.)
