# DET-3 — `gradle-dep` signal type — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduzir o signal type `gradle-dep` no schema de detection de cards, que abstrai presença de uma coordenada Maven em qualquer formato Gradle suportado (`build.gradle*` legado + `gradle/libs.versions.toml` moderno). Engine resolve onde procurar; card declara apenas a coordenada.

**Architecture:** Novo branch no avaliador vivo `engine/init.py:_eval_detection_signals` (linha ~160-194) que delega pra helper `_eval_gradle_dep(project_root, coordinate)`. Helper varre catálogos TOML primeiro (curto-circuita no primeiro match), build.gradle legado em fallback. Validação de shape entra em `engine/cards/loader.py` (regra CARD-019 nova). Cards canônicos com signals `file-content` em `**/build.gradle*` + coordenada Maven migram pra `gradle-dep` (avaliação 1-a-1 com regra do SPEC). Cards com `file-content` em código (`**/*.kt`, `**/Podfile*`, etc.) ficam intactos.

**Tech Stack:** Python core (`engine/init.py`, `engine/cards/loader.py`), TOML parsing via `tomllib` (stdlib em 3.11+) ou fallback simples por linha. YAML edits em `cards/*/` (canonical + audit-trail). Doc edits em `docs/schemas/card.md`. Tests em `tests/unit/test_eval_gradle_dep.py` + fixtures em `tests/fixtures/gradle-dep-*/`.

**Spec:** `docs/superpowers/specs/det-3-gradle-dep-signal.md` (commit pareado, mesma branch `feat/gradle-dep-signal`).

---

## Reuse-first evidence (Mandamento #3)

Antes de criar helpers novos, consultei o engine existente:

```bash
# Avaliador único de signals
grep -rn "file-content\|file_content" engine/ --include="*.py" | grep -v test
# → /engine/init.py:184 (único)

# Glob walker existente
grep -n "def _glob_any\|def _SKIP_DIRS" engine/init.py
# → :592 _glob_any (stream-based, depth-capped, _SKIP_DIRS aplicado)
```

Decisões de reuso:

- **`_glob_any` é reusado** para o fallback build.gradle (mesma semântica de varredura linha-a-linha com `_SKIP_DIRS` e depth-cap). Não duplicamos lógica de walk.
- **TOML parsing**: Python stdlib `tomllib` (3.11+). `pyproject.toml` já declara Python ≥3.11 (verificar em Task 0); se sim, sem nova dep. Senão, fallback regex linha-a-linha pra `module = "..."` e par `group/name` (mais lento mas zero dep nova, alinhado a Decision 22).
- **`_eval_detection_signals`** ganha branch novo (mesmo padrão dos branches `directory-exists`, `file-exists`, `file-content`) — não criar avaliador paralelo.
- **`validators/_common.py`** não cobre validação de shape em cards (responsabilidade do loader); CARD-019 nova segue o padrão CARD-015/CARD-016 inline.

`forge graph` Q11 não roda offline (snapshot atual desatualizado pós-últimos commits); reuso confirmado por grep manual + leitura de `engine/init.py` + `engine/cards/loader.py`. Sem near-duplicate detectada.

---

## File Structure

| Ação | Arquivo | Responsabilidade |
|---|---|---|
| Modificar | `engine/init.py` | Branch novo `gradle-dep` em `_eval_detection_signals` + helper `_eval_gradle_dep` + helpers TOML (parse_libs_versions / scan_legacy_gradle) |
| Modificar | `engine/cards/loader.py` | Regra CARD-019: validação de shape de `gradle-dep` (coordinate string `<group>:<artifact>`, sem versão, sem espaços) |
| Modificar | `docs/schemas/card.md` | Adicionar `gradle-dep` na tabela §"Signal types" + exemplo + ATC sobre vapor `dependency` |
| Criar | `tests/fixtures/gradle-dep-toml-only/` | Fixture AC-1 (TOML moderno apenas) |
| Criar | `tests/fixtures/gradle-dep-toml-split/` | Fixture AC-2 (group + name split) |
| Criar | `tests/fixtures/gradle-dep-legacy/` | Fixture AC-3 (build.gradle apenas) |
| Criar | `tests/fixtures/gradle-dep-hybrid/` | Fixture AC-4 (catálogo + legado) |
| Criar | `tests/fixtures/gradle-dep-negative/` | Fixture AC-5 (TOML com outras deps) |
| Criar | `tests/fixtures/gradle-dep-file-content-preserved/` | Fixture AC-6 (file-content backward compat) |
| Criar | `tests/unit/test_eval_gradle_dep.py` | Tests unitários cobrindo AC-1..AC-6 + edge cases + CARD-019 |
| Modificar | `cards/<each>/detection/signals.yaml` + `cards/<each>/card.yaml` | Migração avaliada 1-a-1 conforme política do SPEC (Task 7 cobre cada card) |
| Modificar | `CHANGELOG.md` | `### Added` — gradle-dep signal type. `### Changed` — N cards migrados |
| Modificar | `docs/design/08-session-handoff.md` | "Última atualização" + estado: Phase 0 DET-3 entregue |
| Modificar | `docs/design/04-pending.md` | Marca DET-3 como ✅ resolvido na seção pilot |

Justificativa load-bearing (Mandamento #4):

- `docs/schemas/card.md` — load-bearing per `.claude/rules/scope.md`. Schema doc é fonte canônica do signal types; sem este edit o novo tipo não entra no contrato. Mudança está no escopo direto da tarefa.
- `cards/**` — load-bearing per scope.md. Migração de signals é a entrega do SPEC; mudança é necessária por consequência direta do design contract aprovado.

---

## Task 0: Pre-flight check (env + dep)

**Files:** none (read-only)

- [ ] **Step 0.1: Confirmar Python ≥3.11 (necessário pra `tomllib`)**

Run:
```bash
grep -n "python" pyproject.toml | head -3
python3 --version
```
Expected: `requires-python = ">=3.11"` (ou superior); `python3 --version` em 3.11+.

Se Python <3.11, abrir 3-caminhos (discipline §1): (A) abandonar `tomllib` e usar fallback regex (sem nova dep, mais código), (B) bumpar `requires-python` (decisão load-bearing — abrir brainstorm separado), (C) pausar plano.

- [ ] **Step 0.2: Confirmar baseline pytest verde**

Run: `pytest -q 2>&1 | tail -3`
Expected: `1113 passed` (ou baseline equivalente sem failures). Se vermelho, abort — não inicia plano em árvore verde-quebrada.

- [ ] **Step 0.3: Verificar working tree limpo + branch correta**

Run: `git status && git branch --show-current`
Expected: working tree clean; branch `feat/gradle-dep-signal`.

---

## Task 1: Test fixtures (RED — fixtures + falhantes esperadas)

**Files:**
- Create: `tests/fixtures/gradle-dep-toml-only/gradle/libs.versions.toml`
- Create: `tests/fixtures/gradle-dep-toml-only/settings.gradle.kts` (mínimo plausível)
- Create: `tests/fixtures/gradle-dep-toml-split/gradle/libs.versions.toml`
- Create: `tests/fixtures/gradle-dep-legacy/app/build.gradle.kts`
- Create: `tests/fixtures/gradle-dep-hybrid/gradle/libs.versions.toml`
- Create: `tests/fixtures/gradle-dep-hybrid/app/build.gradle.kts`
- Create: `tests/fixtures/gradle-dep-negative/gradle/libs.versions.toml`
- Create: `tests/fixtures/gradle-dep-file-content-preserved/app/src/main/kotlin/Foo.kt`

- [ ] **Step 1.1: Criar fixtures conforme contratos do SPEC (AC-1..AC-6)**

Cada fixture é um diretório mínimo plausível com APENAS os arquivos necessários pra acionar o branch específico. Conteúdos canônicos:

**AC-1 — `gradle-dep-toml-only/gradle/libs.versions.toml`:**
```toml
[versions]
ktor = "2.3.7"

[libraries]
ktor-client-core = { module = "io.ktor:ktor-client-core", version.ref = "ktor" }
ktor-client-cio  = { module = "io.ktor:ktor-client-cio",  version.ref = "ktor" }
```

**AC-2 — `gradle-dep-toml-split/gradle/libs.versions.toml`:**
```toml
[versions]
ktor = "2.3.7"

[libraries]
ktor-core = { group = "io.ktor", name = "ktor-client-core", version.ref = "ktor" }
```

**AC-3 — `gradle-dep-legacy/app/build.gradle.kts`:**
```kotlin
dependencies {
    implementation("io.ktor:ktor-client-core:2.3.7")
}
```

**AC-4 — `gradle-dep-hybrid/`:** combina conteúdo de AC-1 (libs.versions.toml) + AC-3 (build.gradle.kts) lado-a-lado.

**AC-5 — `gradle-dep-negative/gradle/libs.versions.toml`:**
```toml
[libraries]
junit = { module = "junit:junit", version = "4.13.2" }
```

**AC-6 — `gradle-dep-file-content-preserved/app/src/main/kotlin/Foo.kt`:**
```kotlin
import io.ktor.client.HttpClient

class Foo { val client = HttpClient() }
```

- [ ] **Step 1.2: Verificar criação**

Run: `find tests/fixtures/gradle-dep-* -type f | sort`
Expected: 8 arquivos listados (um por fixture, exceto hybrid que tem 2).

**NÃO fazer:** adicionar `build/`, `.gradle/`, `node_modules/` ou outros diretórios skipados — só os arquivos canônicos.

---

## Task 2: Test failing (RED — escreve antes de implementar)

**Files:**
- Create: `tests/unit/test_eval_gradle_dep.py`

- [ ] **Step 2.1: Escrever testes unitários cobrindo AC-1..AC-6 + edge cases**

Esqueleto canônico (escrever full conteúdo seguindo este shape; mentor calmo, sem hedging):

```python
"""Tests for gradle-dep signal type evaluation.

Cobre AC-1..AC-6 do SPEC det-3-gradle-dep-signal.md + edge cases
(TOML mal-formado, coordenada inválida, ambos formatos co-existindo).
"""

from pathlib import Path

import pytest

from engine.init import _eval_detection_signals, _eval_gradle_dep

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _detection(coordinate: str, confidence: float = 0.5) -> dict:
    return {"signals": [{"type": "gradle-dep", "coordinate": coordinate, "confidence": confidence}]}


def test_ac1_toml_only_module_format() -> None:
    """AC-1: libs.versions.toml com `module = "io.ktor:..."` → match."""
    score, matched = _eval_detection_signals(
        FIXTURES / "gradle-dep-toml-only",
        _detection("io.ktor:ktor-client-core"),
    )
    assert score == 0.5
    assert any("io.ktor:ktor-client-core" in m for m in matched)


def test_ac2_toml_split_group_name_format() -> None:
    """AC-2: libs.versions.toml com `group + name` separados → match."""
    score, _ = _eval_detection_signals(
        FIXTURES / "gradle-dep-toml-split",
        _detection("io.ktor:ktor-client-core"),
    )
    assert score == 0.5


def test_ac3_build_gradle_legacy() -> None:
    """AC-3: build.gradle.kts declarando dep diretamente → match."""
    score, _ = _eval_detection_signals(
        FIXTURES / "gradle-dep-legacy",
        _detection("io.ktor:ktor-client-core"),
    )
    assert score == 0.5


def test_ac4_hybrid_no_double_counting() -> None:
    """AC-4: catálogo + build.gradle → match exatamente uma vez."""
    score, _ = _eval_detection_signals(
        FIXTURES / "gradle-dep-hybrid",
        _detection("io.ktor:ktor-client-core"),
    )
    assert score == 0.5  # confidence única, sem soma duplicada


def test_ac5_negative_no_match() -> None:
    """AC-5: TOML sem a coordenada → sem match."""
    score, _ = _eval_detection_signals(
        FIXTURES / "gradle-dep-negative",
        _detection("io.ktor:ktor-client-core"),
    )
    assert score == 0.0


def test_ac6_file_content_preserved() -> None:
    """AC-6: file-content em **/*.kt continua funcionando após introdução de gradle-dep."""
    score, _ = _eval_detection_signals(
        FIXTURES / "gradle-dep-file-content-preserved",
        {"signals": [{"type": "file-content", "glob": "**/*.kt", "contains": "io.ktor.client", "confidence": 0.2}]},
    )
    assert score == 0.2


def test_helper_returns_false_for_missing_coordinate() -> None:
    """Defesa: coordenada ausente retorna False (não raise)."""
    assert _eval_gradle_dep(FIXTURES / "gradle-dep-negative", "io.ktor:ktor-client-core") is False


def test_helper_handles_empty_coordinate() -> None:
    """Defesa: coordenada vazia/None retorna False (não raise)."""
    assert _eval_gradle_dep(FIXTURES / "gradle-dep-toml-only", "") is False
    assert _eval_gradle_dep(FIXTURES / "gradle-dep-toml-only", None) is False  # type: ignore[arg-type]


def test_helper_handles_malformed_toml(tmp_path: Path) -> None:
    """Defesa: TOML mal-formado não bloqueia (try/except silencioso)."""
    (tmp_path / "gradle").mkdir()
    (tmp_path / "gradle" / "libs.versions.toml").write_text("not valid toml [[[", encoding="utf-8")
    assert _eval_gradle_dep(tmp_path, "io.ktor:ktor-client-core") is False
```

- [ ] **Step 2.2: Confirmar testes FALHAM (RED phase)**

Run: `pytest tests/unit/test_eval_gradle_dep.py -x 2>&1 | tail -20`
Expected: ImportError ou AttributeError citando `_eval_gradle_dep` não existir. Se algum teste passar inesperadamente, abort: significa que alguém já implementou, refazer análise.

**NÃO fazer:** implementar `_eval_gradle_dep` ainda. Esta task é estritamente RED.

---

## Task 3: Implementação do helper `_eval_gradle_dep` + branch no avaliador (GREEN)

**Files:**
- Modify: `engine/init.py`

- [ ] **Step 3.1: Adicionar imports necessários**

No topo de `engine/init.py`, adicionar (mantendo ordem alfabética dos imports stdlib):

```python
try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover — defesa pra ambientes <3.11
    tomllib = None  # type: ignore[assignment]
```

Justificativa: `tomllib` é stdlib em ≥3.11 (confirmado em Task 0); fallback `None` mantém o código tolerante a downgrade involuntário em CI exótica (não temos Decision aprovando bump pra 3.12, mas o gate `requires-python >=3.11` já cobre).

- [ ] **Step 3.2: Implementar `_eval_gradle_dep` próximo a `_glob_any`**

Inserir logo abaixo de `_glob_any` (~linha 621 ou onde fizer sentido topologicamente):

```python
def _eval_gradle_dep(project_root: Path, coordinate: str | None) -> bool:
    """True se a coordenada Maven existe em qualquer formato Gradle.

    Ordem: 1) catálogo gradle/*.versions.toml, 2) build.gradle(.kts) legado.
    Curto-circuita no primeiro match. Defensivo contra TOML mal-formado
    (try/except silencioso, alinhado a `_glob_any`).
    """
    if not coordinate or ":" not in coordinate:
        return False
    group, _, artifact = coordinate.partition(":")
    if not group or not artifact:
        return False

    # 1) Catálogo TOML (path canônico gradle/*.versions.toml)
    if tomllib is not None:
        for toml_path in (project_root / "gradle").glob("*.versions.toml"):
            try:
                with toml_path.open("rb") as fh:
                    data = tomllib.load(fh)
            except (OSError, tomllib.TOMLDecodeError):
                continue
            libraries = data.get("libraries") or {}
            if not isinstance(libraries, dict):
                continue
            for entry in libraries.values():
                if not isinstance(entry, dict):
                    continue
                module = entry.get("module")
                if isinstance(module, str) and module == coordinate:
                    return True
                grp = entry.get("group")
                nm = entry.get("name")
                if isinstance(grp, str) and isinstance(nm, str) and grp == group and nm == artifact:
                    return True

    # 2) build.gradle(.kts) legado — reusa _glob_any por economia
    if _glob_any(project_root, "**/build.gradle*", coordinate):
        return True

    return False
```

- [ ] **Step 3.3: Adicionar branch novo em `_eval_detection_signals`**

Editar `_eval_detection_signals` (~linha 172-194), adicionar branch ANTES do branch `file-content` (ordem semântica: tipos específicos antes do genérico):

```python
elif kind == "gradle-dep":
    coordinate = sig.get("coordinate")
    if isinstance(coordinate, str) and coordinate:
        ok = _eval_gradle_dep(project_root, coordinate)
```

E atualizar o label fallback no `matched.append`:
```python
label = sig.get("coordinate") or sig.get("contains") or sig.get("path") or sig.get("glob") or kind
```

- [ ] **Step 3.4: Rodar testes (GREEN phase)**

Run: `pytest tests/unit/test_eval_gradle_dep.py -xvs 2>&1 | tail -30`
Expected: 9 tests pass (AC-1..AC-6 + 3 defense tests). Se algum vermelho, debug com `systematic-debugging` — não commit até verde.

- [ ] **Step 3.5: Rodar suite full pra confirmar zero regressão**

Run: `pytest -q 2>&1 | tail -3`
Expected: `1122 passed` (1113 baseline + 9 novos). Sem failures, sem skips novos.

---

## Task 4: Validação de shape em `engine/cards/loader.py` (CARD-019)

**Files:**
- Modify: `engine/cards/loader.py`

- [ ] **Step 4.1: Adicionar test pra CARD-019 (RED)**

Adicionar em `tests/unit/test_eval_gradle_dep.py`:

```python
def test_card019_coordinate_shape_valid(tmp_path: Path) -> None:
    """CARD-019: coordinate válida no shape `<group>:<artifact>`."""
    from engine.cards.loader import _validate_card_manifest_shape  # ou helper equivalente

    valid = {"detection": {"signals": [{"type": "gradle-dep", "coordinate": "io.ktor:ktor-client-core", "confidence": 0.5}]}}
    violations = _validate_card_manifest_shape(valid, tmp_path)
    assert not any("CARD-019" in v for v in violations)


def test_card019_coordinate_rejects_version_suffix(tmp_path: Path) -> None:
    """CARD-019: rejeita coordenada com versão sufixada."""
    from engine.cards.loader import _validate_card_manifest_shape

    bad = {"detection": {"signals": [{"type": "gradle-dep", "coordinate": "io.ktor:ktor-client-core:2.3.7", "confidence": 0.5}]}}
    violations = _validate_card_manifest_shape(bad, tmp_path)
    assert any("CARD-019" in v for v in violations)


def test_card019_coordinate_rejects_missing_colon(tmp_path: Path) -> None:
    """CARD-019: rejeita coordenada sem ':' separator."""
    from engine.cards.loader import _validate_card_manifest_shape

    bad = {"detection": {"signals": [{"type": "gradle-dep", "coordinate": "io.ktor", "confidence": 0.5}]}}
    violations = _validate_card_manifest_shape(bad, tmp_path)
    assert any("CARD-019" in v for v in violations)
```

**Importante:** verificar o nome real do helper em `engine/cards/loader.py` antes (pode ser `_validate_card_yaml`, `_validate_card_manifest`, etc.). Ajustar import.

Run: `pytest tests/unit/test_eval_gradle_dep.py -k card019 -x`
Expected: 3 failures (helper não valida `gradle-dep` ainda).

- [ ] **Step 4.2: Implementar CARD-019 em loader.py**

Localizar bloco que valida signals (`engine/cards/loader.py:639-656`). Adicionar after `confidence_sum` validation, dentro do loop `for sig in signals`:

```python
if sig.get("type") == "gradle-dep":
    coord = sig.get("coordinate")
    if not isinstance(coord, str) or not coord:
        violations.append("CARD-019: gradle-dep signal requires `coordinate` (string)")
    elif coord.count(":") != 1:
        violations.append(
            f"CARD-019: gradle-dep coordinate must be `<group>:<artifact>` (got {coord!r})"
        )
    elif " " in coord:
        violations.append(f"CARD-019: gradle-dep coordinate must not contain spaces (got {coord!r})")
    else:
        group, _, artifact = coord.partition(":")
        if not group or not artifact:
            violations.append(f"CARD-019: gradle-dep coordinate missing group or artifact (got {coord!r})")
```

- [ ] **Step 4.3: Confirmar GREEN**

Run: `pytest tests/unit/test_eval_gradle_dep.py -k card019 -x`
Expected: 3 pass.

Run: `pytest -q 2>&1 | tail -3`
Expected: `1125 passed` (1113 + 9 + 3). Zero regressão.

---

## Task 5: Schema doc update (`docs/schemas/card.md`)

**Files:**
- Modify: `docs/schemas/card.md`

Justificativa load-bearing (Mandamento #4): `docs/schemas/card.md` é load-bearing per `.claude/rules/scope.md`. Edit é direto e necessário — schema doc é fonte canônica de signal types; sem este edit, contrato fica out-of-sync com o engine (mesmo gap de hoje com `dependency` vapor, agora resolvido pra `gradle-dep`).

- [ ] **Step 5.1: Adicionar `gradle-dep` na tabela §"Signal types"**

Localizar tabela em `docs/schemas/card.md:383-389`. Adicionar linha entre `file-content` e `dependency`:

```markdown
| `gradle-dep` | `coordinate: <group>:<artifact>` (sem versão, sem espaços). Match em `gradle/*.versions.toml` (TOML, format module/group+name) E em `**/build.gradle*` (substring). Ordem: catálogo primeiro, build.gradle fallback. |
```

- [ ] **Step 5.2: Adicionar nota sobre o vapor `dependency`**

Após a tabela §"Signal types", adicionar:

```markdown
> **Nota:** o tipo `dependency` lista-se no schema mas **não está implementado**
> em `engine/init.py:_eval_detection_signals`. Cards declarados com `type: dependency`
> são silenciosamente ignorados. O sucessor canônico para deps Gradle é
> `gradle-dep`. Cleanup do vapor `dependency` é tracked em `docs/design/04-pending.md`
> como follow-up não-bloqueante a DET-3.
```

- [ ] **Step 5.3: Adicionar exemplo de `gradle-dep` no bloco YAML §"DETECTION"**

Localizar bloco em `docs/schemas/card.md:232-256`. Adicionar entre os signals existentes:

```yaml
    - type:       gradle-dep
      coordinate: "io.ktor:ktor-client-core"
      confidence: 0.5
```

- [ ] **Step 5.4: Adicionar CARD-019 na lista de validation rules**

Localizar `docs/schemas/card.md:509-511` (CARD-015 / CARD-016 listing). Adicionar:

```
CARD-019  detection.signals[*].coordinate (when type=gradle-dep) must be `<group>:<artifact>`, no version, no spaces
```

- [ ] **Step 5.5: Verificar**

Run: `grep -c "gradle-dep" docs/schemas/card.md`
Expected: ≥ 4 (tabela + nota + exemplo + CARD-019).

**NÃO fazer:** refatorar outras seções; remover ou renomear `dependency`; alterar exemplos pré-existentes além da inserção.

---

## Task 6: Migration audit — listar candidatos 1-a-1

**Files:** none (read-only audit)

Antes de migrar qualquer card, audit explícito de cada um pra decidir migrate vs preserve segundo a política do SPEC §"Migration policy".

- [ ] **Step 6.1: Gerar mapa de signals build.gradle*-tocando**

Run:
```bash
for f in cards/*/detection/signals.yaml; do
    echo "=== $f ==="
    awk '/^  - /{block=$0; next}
         {block=block "\n" $0}
         /^[^ ]/{print block; block=""}
         END{print block}' "$f" \
      | grep -B1 -A2 "build.gradle"
done > /tmp/det3-audit.txt
cat /tmp/det3-audit.txt | head -60
```

Expected: bloco por card listando signals candidatos. Salvar mental ou em scratch — é input pra Task 7.

- [ ] **Step 6.2: Aplicar regra do SPEC pra cada candidate**

Pra cada signal listado em Step 6.1, classificar:

| Signal contém | Glob | Política | Ação Task 7 |
|---|---|---|---|
| Coordenada `<group>:<artifact>` completa | `**/build.gradle*` | Migrate | swap pra `gradle-dep` |
| Apenas `<artifact>` sem group | `**/build.gradle*` | Migrate se group inferível pela doc do card; senão preserve | swap ou keep |
| String não-coordenada (palavra-chave, plugin id) | `**/build.gradle*` | Preserve | keep file-content |
| Qualquer string | `**/*.kt`, `**/*.swift`, `**/Podfile*`, etc. | Preserve | keep file-content |

Anotar decisão por card no commit body de Task 7. Cards com ambiguidade → preserve por conservadorismo.

- [ ] **Step 6.3: Confirmar CARD-016 sanity post-audit**

Pra cada card que vai migrar, confirmar que a soma de confidences NÃO muda (apenas renomeamos o tipo). Garante que CARD-016 não dispara após migration.

**Critério de sucesso da task:** lista determinística de cards a migrar (com coordinate exata) + lista de cards a preservar (com razão). Esta task é puramente analítica — não modifica arquivos.

---

## Task 7: Migration dos cards canônicos

**Files (depende de Task 6 — lista exata determinada lá):**
- Modify: `cards/<each-migration-target>/detection/signals.yaml` (audit-trail)
- Modify: `cards/<each-migration-target>/card.yaml` (canonical mirror)

Espera-se que a lista cubra pelo menos: `ktor-client`, `retrofit-client`, `kotlinx-serialization-json`, `room-database`, `firebase-auth`, `firestore-persistence`, `firestore-realtime`, `firestore-security-rules`, `firebase-storage`, `crashlytics`, `datastore-prefs`, `koin-annotations`, `compose-screens`, `kmp-shared`, `kotlin-language`, `nav3`, `skie-bridge` — mas o número exato depende de Task 6 (alguns podem ser preserve-as-is).

- [ ] **Step 7.1: Para CADA card-alvo (atômico per card)**

Sub-passos (repetir por card):

a) Abrir `cards/<name>/detection/signals.yaml` e localizar o signal a migrar.
b) Substituir o bloco:
   ```yaml
   - id:         <preserved-id>
     type:       file-content
     glob:       "**/build.gradle*"
     contains:   "<coordinate-or-artifact>"
     confidence: <preserved-value>
     rationale:  "<preserved-rationale>"
   ```
   por:
   ```yaml
   - id:         <preserved-id>
     type:       gradle-dep
     coordinate: "<canonical-maven-coordinate>"
     confidence: <preserved-value>
     rationale:  "<preserved-rationale> Migrado de file-content em DET-3 (libs.versions.toml + build.gradle)."
   ```
c) Abrir `cards/<name>/card.yaml` e fazer a mesma substituição no bloco `detection.signals`.
d) Salvar.

- [ ] **Step 7.2: Rodar loader validation por card**

Run (uma vez no fim, varre todos):
```bash
pytest tests/integration/test_cards_resolver_meobonsai.py tests/unit/test_card_yaml_validation.py -x 2>&1 | tail -10
```
Expected: green. CARD-019 não dispara (todas as coordinates são `<group>:<artifact>` sem versão).

- [ ] **Step 7.3: Verificar pytest baseline preservada**

Run: `pytest --collect-only -q 2>&1 | tail -1 && pytest -q 2>&1 | tail -3`
Expected: count ≥ `BASELINE + N` (onde `BASELINE` = `pytest --collect-only -q | tail -1` rodado em Task 0.2 antes do plano; `N` = soma de tests adicionados em Tasks 2 e 4 — 9 gradle-dep + 3 CARD-019 = 12). Sem novos tests nesta task (migration não introduz tests novos, AC-7 é coberto via integration que já existe). Zero failures.

- [ ] **Step 7.4: AC-7 — verificar zero regressão em e2e**

Run: `RUN_E2E=1 pytest tests/e2e/test_e2e_brownfield_init.py -xvs 2>&1 | tail -20`
Expected: brownfield init no MeoBonsai (fixture canônica) continua detectando os mesmos cards que detectava pré-migration. Se algum card perdeu detecção, é regressão — abrir 3-caminhos: (A) fix coordinate na migration, (B) revert do card específico pra file-content, (C) split em commit separado pra investigar.

**NÃO fazer:** mexer em signals que não usem `**/build.gradle*`; renomear `id`; alterar `confidence`; tocar `threshold` ou `alternative-cards`.

---

## Task 8: Doc-sync (Mandamento #6)

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/design/08-session-handoff.md`
- Modify: `docs/design/04-pending.md`

- [ ] **Step 8.1: CHANGELOG.md entry**

Adicionar em `## [Unreleased]`:

```markdown
### Added

- Signal type `gradle-dep` em `engine/init.py:_eval_detection_signals` — abstrai presença de coordenada Maven em catálogo `gradle/*.versions.toml` (TOML moderno, formato `module = "<group>:<artifact>"` e `group + name` split) OU em `**/build.gradle*` (legado). Card declara `type: gradle-dep` + `coordinate: <group>:<artifact>`; engine resolve onde procurar. Resolve DET-3 do pilot v1.2-dev 2026-06-10 (scanner cego pra libs.versions.toml). Regra de validação CARD-019 nova em `engine/cards/loader.py`.

### Changed

- N cards canônicos migrados de `file-content` em `**/build.gradle*` pra `gradle-dep` (mesma coordenada, semântica mais ampla cobrindo catálogos modernos). Signals em `**/*.kt`, `**/Podfile*`, `**/Package.swift` preservados como `file-content` (não-Gradle). Backward compat de `file-content` preservada.
- `docs/schemas/card.md` §"Signal types" lista `gradle-dep`; nota sobre vapor `dependency` (declared em schema, never implemented) — cleanup separado.
```

(Substituir `N` pelo número real determinado em Task 7.)

- [ ] **Step 8.2: handoff atualizado**

Em `docs/design/08-session-handoff.md`, atualizar:
- `**Última atualização:** 2026-06-10 (v1.2-dev — DET-3 gradle-dep signal type entregue)`
- `**Estado:** v1.2-dev Phase 0 DET-3 ✅ shipped; Phase A (DRIFT-1) próxima; B1/B2/DET-5/DET-6 acoplados a Phase B`

- [ ] **Step 8.3: 04-pending.md marca DET-3 ✅**

Em `docs/design/04-pending.md`, seção `## v1.2-dev pilot 2026-06-10 — findings + phase sequencing` → `#### DET-3 — Scanner cego pra libs.versions.toml`:

Prefixar título com `✅ resolvido 2026-06-10:`. Adicionar bloco curto após a descrição original:

```markdown
**Resolução shipped 2026-06-10:** Plan `docs/superpowers/plans/det-3-gradle-dep-signal.md`. Novo signal type `gradle-dep` + helper `_eval_gradle_dep` em `engine/init.py` + CARD-019 em loader + migration de N cards. Catálogo `gradle/libs.versions.toml` agora coberto.
```

- [ ] **Step 8.4: README.md stats — verificar**

Run: `grep -E "tests|validators|cards" README.md | head -5`

Se stats mencionam "1113 tests" → atualizar para "1125 tests" (1113 + 9 gradle-dep + 3 CARD-019). Se README só fala "~1113" qualitativamente, manter ou ajustar pra "~1125". Se nenhuma stat muda perceptivelmente, deixar README.

**NÃO fazer:** refatorar handoff ou pending além das linhas indicadas; adicionar entry em CHANGELOG fora de `[Unreleased]`.

---

## Task 9: Verification final (Mandamento #2)

**Files:** none (read-only)

- [ ] **Step 9.1: pytest full suite**

Run: `pytest 2>&1 | tail -10`
Expected: count ≥ `BASELINE + N` passed, `0 failed` (onde `BASELINE` foi capturado em Task 0.2 via `pytest --collect-only -q | tail -1`; `N` = 12 = 9 novos tests gradle-dep da Task 2 + 3 novos tests CARD-019 da Task 4 + 0 da Task 7 + qualquer test adicional incidental). Zero failures, zero skips novos.

- [ ] **Step 9.2: forge verify**

Run: `forge verify 2>&1 | tail -20`
Expected: cascade verde, sem hard fails. Migration não introduz validator novo nem quebra existentes.

- [ ] **Step 9.3: Smoke do CLI**

Run: `./bin/forge --version && python -c "from engine.init import _eval_gradle_dep; print(_eval_gradle_dep)"`
Expected: versão + função importável.

- [ ] **Step 9.4: AC-7 e2e completa**

Run: `RUN_E2E=1 pytest tests/e2e/ -x 2>&1 | tail -10`
Expected: e2e suite verde. Brownfield init em MeoBonsai detecta mesmos cards que pré-DET-3.

- [ ] **Step 9.5: Subagent reviewer (gsd-code-reviewer)**

Orquestrador dispatcha review com prompt focado em:
- AC-1..AC-9 cobertos por tests
- CARD-019 não-bypassável
- Migration não introduz desync card.yaml ↔ signals.yaml
- Backward compat de `file-content` preservada
- Voz mentor calmo nos artefatos modificados (CHANGELOG, handoff, schema)

Findings high/critical → fix-dispatch loop.

---

## Verification (overall criteria)

Acceptance criteria do SPEC mapeados a tasks:

| AC | Coberto por |
|---|---|
| AC-1 (TOML module format) | Task 1 fixture + Task 2 test_ac1_toml_only_module_format |
| AC-2 (TOML split group+name) | Task 1 fixture + Task 2 test_ac2_toml_split_group_name_format |
| AC-3 (build.gradle legacy) | Task 1 fixture + Task 2 test_ac3_build_gradle_legacy |
| AC-4 (hybrid no double-count) | Task 1 fixture + Task 2 test_ac4_hybrid_no_double_counting |
| AC-5 (negative no match) | Task 1 fixture + Task 2 test_ac5_negative_no_match |
| AC-6 (file-content preserved) | Task 1 fixture + Task 2 test_ac6_file_content_preserved |
| AC-7 (zero regressão e2e) | Task 7.4 + Task 9.4 (e2e brownfield) |
| AC-8 (schema + CARD-019) | Task 4 (loader + tests) + Task 5 (schema doc) |
| AC-9 (pytest baseline) | Task 9.1 (`pytest` = 1125 passed) |

## Commits esperados

Atomic per task ou grupos coesos:

1. `test(det-3): fixtures + failing tests for gradle-dep signal` (Tasks 1 + 2)
2. `feat(det-3): gradle-dep signal type + _eval_gradle_dep helper` (Task 3)
3. `feat(det-3): CARD-019 shape validation for gradle-dep` (Task 4)
4. `docs(det-3): schema card.md lists gradle-dep signal type` (Task 5)
5. `refactor(det-3): migrate N cards from file-content to gradle-dep` (Tasks 6 + 7)
6. `docs(det-3): doc-sync — CHANGELOG + handoff + 04-pending` (Task 8)

Verification (Task 9) é leitura — não gera commit.

## Anti-padrões (NÃO fazer durante execução)

- Implementar `_eval_gradle_dep` antes dos testes RED falharem (Task 2 → Task 3 é estritamente RED → GREEN).
- Migrar `file-content` em `**/*.kt`, `**/Podfile*`, `**/Package.swift` — preservar (política do SPEC).
- Tocar `confidence` ou `threshold` de cards durante migration — apenas type+coordinate.
- Implementar parse semântico de TOML com resolução de `version.ref` — fora de escopo.
- Cobrir npm/swift/pod neste plano — fora de escopo.
- Cleanup do vapor `dependency` neste plano — follow-up separado.
- Refatorar `_glob_any` ou outros helpers existentes durante o trabalho.
- Bumpar `requires-python` em `pyproject.toml` sem brainstorm separado.
- Voz corporativa, hedging ou emoji decorativo em CHANGELOG/handoff/schema.

## Pending gaps coverage (Mandamento #4 / M2)

Este plano fecha DET-3 de `docs/design/04-pending.md` §"v1.2-dev pilot 2026-06-10 — findings + phase sequencing". Task 8.3 atualiza o pending. Anti-goals novos (cleanup do vapor `dependency`, ecossistemas npm/swift/pod, schema-version normalization em signals.yaml) são anotados na seção "Considerações futuras" do SPEC.
