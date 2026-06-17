# Camada de Interação AI-First (Driver + Grill) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax.

**Goal:** Tornar o feature-forge dirigível de ponta a ponta por hosts agênticos (Claude Code / opencode), ensinando o host a dirigir o intent loop, abrindo o front-door pra ticket/frase, ligando a entrada visual dormente, e fazendo o grill confrontar o pedido contra o que já existe.

**Architecture:** O engine só orquestra + sanitiza (deriva slug, semeia intake, valida screenshot, registra fingerprint) e emite intent via `<FORGE_INTENT/>`+exit 2 — nunca interpreta pixel/domínio. O raciocínio (grounded-challenge) vive no prompt do `planning-conductor.md` (Phase 2.5) lido do FORGE_HOME. A `SKILL.md`/`AGENTS.md` instalados no consumidor são instruções pro host (Decisão 22: comportamento, não import).

**Tech Stack:** Python 3.13 + Bash dispatcher + YAML/MD specs/prompts; pytest (`.venv/bin/pytest`).

## Global Constraints

- **Test runner:** `.venv/bin/pytest` (NUNCA o pytest do sistema — só o `.venv` tem json5+deps; system pytest dá false fails).
- **Baseline atual (pós cross-AI review do PR #17):** rapid **1611** / integration **168** / e2e **30**; counts não caem sem justificativa. Re-confirme com `.venv/bin/pytest -m "not integration and not e2e" -q | tail -1`.
- **Mandamento 0:** cada task é executada por subagente — cada uma carrega Files permitidos + critério de sucesso testável + anti-padrões.
- **Decisões locked preservadas:** 22 (engine NÃO importa nada da SKILL.md/AGENTS.md — são comportamento pro host), 18 (FORGE_HOME XDG `~/.local/share/feature-forge/`), 10 (zero flags — argv posicional + screenshot conversacional, sem flag CLI).
- **Voz mentor calmo** nos artefatos gerados. `forge verify` sem hard fail. Doc-sync no fim (Task 6).
- **Reuso (Mandamento 3):** `engine/vision/screenshot.py` já existe (wire, não reescreve); conductor Phase 1-4 + `AskUserQuestion` agrupado existem (Phase 2.5 reusa o contexto); `merge_settings_json` reusado pro install; `validate_readiness.py` estendido (não recriado).

---

### Task 1: Front-door + CASING-BUG fix (engine/plan.py)

Slugify determinístico + aceitar ticket/frase no argv com confirmação conversacional + semear intake + trocar `SystemExit` por mensagem mentor-calmo + corrigir o CASING-BUG do `_render_template`.

**Files:**
- Modify `engine/plan.py` — adicionar `_derive_slug` (perto de `_is_valid_slug`, ~L369); reescrever `_elicit_slug` (~L1078-1120); ajustar `run()` (~L1387-1416, ponto pós-slug); corrigir `_render_template` (~L384-403); adicionar `_seed_intake_source` helper.
- Create `tests/unit/test_engine_plan_frontdoor.py`

**Interfaces:**
- Produces `engine.plan._derive_slug(text: str) -> str` — determinístico; lança `ValueError` quando não derivável.
- Produces `engine.plan._seed_intake_source(feature_path: Path, raw_text: str, source_type: str, source_ref: str) -> None`
- Consumes `engine.plan._is_valid_slug(value: str) -> bool` (existente, ~L369).
- Consumes `engine.ui.question.ask_text(prompt, *, default=None, validator=None, validator_hint=None) -> str` (existente; usado pra confirmar/ajustar o slug derivado).
- Modifies `engine.plan._render_template(template_name: str, target: Path, slug: str) -> bool` — passa a substituir `{{feature_slug}}` lowercase + tokens triviais.

#### Step 1.1 — Teste falhando: `_derive_slug` determinístico

- [ ] Escrever `tests/unit/test_engine_plan_frontdoor.py` com os casos de slugify:

```python
"""Front-door + CASING-BUG tests para engine.plan (Wave 1 AI-first).

Cobre: slugify determinístico (_derive_slug), seed do intake
(_seed_intake_source) e a regression do CASING-BUG (_render_template
substitui {{feature_slug}} lowercase).

Refs:
- docs/superpowers/specs/2026-06-17-ai-first-interaction-layer-design.md §4 C3
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import plan


# ── _derive_slug — slugify determinístico ────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("adicionar detalhe do bonsai", "adicionar-detalhe-do-bonsai"),
        ("IN-37234", "in-37234"),
        ("Lembrete de Rega", "lembrete-de-rega"),
        ("notificação às 8h", "notificacao-as-8h"),
        ("a   b    c", "a-b-c"),
        ("--leading-and-trailing--", "leading-and-trailing"),
        ("café com leite", "cafe-com-leite"),
    ],
)
def test_derive_slug_deterministic(text: str, expected: str) -> None:
    assert plan._derive_slug(text) == expected


def test_derive_slug_truncates_to_50() -> None:
    long = "palavra " * 20
    out = plan._derive_slug(long)
    assert len(out) <= 50
    assert plan._is_valid_slug(out), out


def test_derive_slug_starts_with_letter() -> None:
    # Começa com dígito → prefixa pra garantir início com letra.
    out = plan._derive_slug("123 fix")
    assert out[0].isalpha(), out
    assert plan._is_valid_slug(out), out


def test_derive_slug_empty_raises() -> None:
    with pytest.raises(ValueError):
        plan._derive_slug("")
    with pytest.raises(ValueError):
        plan._derive_slug("   !!!   ")
```

- [ ] Rodar e ver FAIL (função não existe):

```bash
.venv/bin/pytest tests/unit/test_engine_plan_frontdoor.py -q
```

Esperado: `AttributeError: module 'engine.plan' has no attribute '_derive_slug'` (ou ImportError equivalente) → todos os casos em FAIL/ERROR.

#### Step 1.2 — Impl `_derive_slug`

- [ ] Adicionar logo após `_is_valid_slug` (~L371) em `engine/plan.py`:

```python
import unicodedata as _unicodedata


def _derive_slug(text: str) -> str:
    """Deriva slug kebab-case determinístico de ticket/frase livre.

    Regras (spec §4 C3): lowercase · NFKD strip de acentos · não-alfanum
    → hífen · colapsa hífens · trunca pra 2..50 chars · garante início com
    letra (prefixa "f-" quando começa com dígito). Levanta ``ValueError``
    quando nada derivável (string vazia ou só pontuação).
    """
    normalized = _unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    out_chars: list[str] = []
    for ch in ascii_text:
        out_chars.append(ch if (ch.isalnum()) else "-")
    collapsed = "-".join(filter(None, "".join(out_chars).split("-")))
    if not collapsed:
        raise ValueError(
            f"não consegui derivar um slug de {text!r} — só caracteres inválidos."
        )
    if not collapsed[0].isalpha():
        collapsed = f"f-{collapsed}"
    collapsed = collapsed[:50].rstrip("-")
    if len(collapsed) < 2:
        collapsed = f"{collapsed}-x"[:50]
    return collapsed
```

- [ ] Rodar e ver PASS:

```bash
.venv/bin/pytest tests/unit/test_engine_plan_frontdoor.py -q
```

Esperado: os 4 grupos de slugify PASS; demais testes ainda ausentes.

#### Step 1.3 — Teste falhando: CASING-BUG regression

- [ ] Adicionar ao mesmo arquivo de teste:

```python
# ── CASING-BUG — _render_template substitui {{feature_slug}} lowercase ───────


def test_render_template_substitutes_lowercase_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Templates carregam {{feature_slug}} (lowercase, 74×). O engine renderizava
    {{FEATURE_SLUG}} (uppercase) — token sobrava cru. Asserir que some.
    """
    fake_templates = tmp_path / "templates"
    fake_templates.mkdir()
    (fake_templates / "x.template.md").write_text(
        "# Feature {{feature_slug}}\nslug: {{feature_slug}}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(plan, "_templates_dir", lambda: fake_templates)

    target = tmp_path / "out.md"
    created = plan._render_template("x.template.md", target, "lembrete-rega")
    assert created is True
    rendered = target.read_text(encoding="utf-8")
    assert "{{feature_slug}}" not in rendered, "lowercase token não substituído"
    assert "lembrete-rega" in rendered
```

- [ ] Rodar e ver FAIL:

```bash
.venv/bin/pytest tests/unit/test_engine_plan_frontdoor.py::test_render_template_substitutes_lowercase_token -q
```

Esperado: `AssertionError: lowercase token não substituído` (o engine só substituía `{{FEATURE_SLUG}}`).

#### Step 1.4 — Impl CASING-BUG fix em `_render_template`

- [ ] Em `engine/plan.py` (~L401), trocar a linha de substituição por substituição lowercase + tokens triviais. Atualizar o corpo de `_render_template`:

```python
def _render_template(template_name: str, target: Path, slug: str) -> bool:
    """Copy `templates/{template_name}` to `target`. Returns True if newly created.

    Templating leve: substitui os tokens que o engine conhece de forma
    confiável — slug (lowercase, como os templates usam, 74×), timestamp,
    e a origem (source_type/source_ref). Tudo o mais fica verbatim — a
    população completa é trabalho do host entre as waves.
    """
    src = _templates_dir() / template_name
    if not src.is_file():
        raise FileNotFoundError(
            f"template '{template_name}' not found at {src}. "
            "Templates wave (1+2) must have shipped before forge plan can run."
        )
    if target.exists():
        return False
    ensure_dir(target.parent)
    raw = src.read_text(encoding="utf-8")
    substitutions = {
        "{{feature_slug}}": slug,
        "{{FEATURE_SLUG}}": slug,  # legacy uppercase — preservado p/ compat
        "{{generated_at_iso8601}}": utc_now_iso(),
    }
    for token, value in substitutions.items():
        raw = raw.replace(token, value)
    target.write_text(raw, encoding="utf-8")
    return True
```

- [ ] Rodar e ver PASS:

```bash
.venv/bin/pytest tests/unit/test_engine_plan_frontdoor.py::test_render_template_substitutes_lowercase_token -q
```

Esperado: 1 passed.

#### Step 1.5 — Teste falhando: seed do intake + front-door no run

- [ ] Adicionar ao arquivo de teste:

```python
# ── _seed_intake_source — grava texto cru no campo source do intake ──────────


def test_seed_intake_source_writes_raw_text(tmp_path: Path) -> None:
    feature_path = tmp_path / "feature"
    feature_path.mkdir()
    intake = feature_path / "feature-intake.md"
    intake.write_text(
        "# Intake\n<!-- forge:source -->\n",
        encoding="utf-8",
    )
    plan._seed_intake_source(
        feature_path,
        raw_text="adicionar detalhe do bonsai",
        source_type="phrase",
        source_ref="adicionar detalhe do bonsai",
    )
    body = intake.read_text(encoding="utf-8")
    assert "adicionar detalhe do bonsai" in body
    assert "source-type: phrase" in body


def test_seed_intake_source_noop_when_no_intake(tmp_path: Path) -> None:
    feature_path = tmp_path / "feature"
    feature_path.mkdir()
    # Sem feature-intake.md → não crasha (degradação graciosa).
    plan._seed_intake_source(
        feature_path, raw_text="x", source_type="phrase", source_ref="x"
    )
```

- [ ] Rodar e ver FAIL (`_seed_intake_source` ausente):

```bash
.venv/bin/pytest tests/unit/test_engine_plan_frontdoor.py -k seed_intake -q
```

Esperado: `AttributeError: ... '_seed_intake_source'`.

#### Step 1.6 — Impl `_seed_intake_source` + reescrita do `_elicit_slug` + wire no `run`

- [ ] Adicionar `_seed_intake_source` em `engine/plan.py` (perto dos helpers, após `_render_template`):

```python
def _seed_intake_source(
    feature_path: Path,
    raw_text: str,
    source_type: str,
    source_ref: str,
) -> None:
    """Semeia o texto/ticket cru no campo source do feature-intake.md.

    Anexa um bloco YAML-front comentado no topo do arquivo de intake (o
    conductor refina via grill). No-op silencioso se o intake ainda não
    existe — degradação graciosa, sem crash.
    """
    intake = feature_path / "feature-intake.md"
    if not intake.is_file():
        return
    block = (
        "<!-- forge:source-seed\n"
        f"source-type: {source_type}\n"
        f"source-ref: {source_ref}\n"
        f"raw: {raw_text}\n"
        "-->\n"
    )
    body = intake.read_text(encoding="utf-8")
    intake.write_text(block + body, encoding="utf-8")
```

- [ ] Reescrever `_elicit_slug` (~L1078) pra aceitar ticket/frase, derivar + confirmar via `ask_text`, e trocar o `SystemExit`. Substituir o bloco inicial:

```python
def _elicit_slug(argv_slug: Optional[str], project_root: Optional[Path] = None) -> str:
    if argv_slug:
        if _is_valid_slug(argv_slug):
            return argv_slug
        # Não é slug válido → trata como ticket/frase: deriva + confirma.
        # Decisão 10: argv posicional, sem flag. Slug-derivável NÃO é erro.
        try:
            derived = _derive_slug(argv_slug)
        except ValueError:
            sys.stderr.write(
                f"forge plan: não consegui derivar um slug de {argv_slug!r}. "
                "Tente uma frase com ao menos uma letra (ex.: 'lembrete de rega').\n"
            )
            raise SystemExit(1)
        confirmed = question.ask_text(
            f"Derivei '{derived}' do que você passou — confirma ou ajusta?",
            default=derived,
            validator=_is_valid_slug,
            validator_hint="kebab-case lowercase, 2..50 chars, deve começar com letra.",
        )
        return confirmed

    # ... (resto inalterado: checkpoint + ask_text do slug, ~L1087-1120)
```

- [ ] No `run()` (~L1398-1416), capturar o argv cru e semear o intake após `feature_path` ser criado (~L1465-1466). Adicionar, logo após `ensure_dir(feature_path)`:

```python
    # Front-door (spec §4 C3): se o argv original não era slug válido,
    # semeia o texto cru no intake pra o conductor refinar via grill.
    if argv_slug and not _is_valid_slug(argv_slug):
        _seed_intake_source(
            feature_path,
            raw_text=argv_slug,
            source_type="ticket" if _looks_like_ticket(argv_slug) else "phrase",
            source_ref=argv_slug,
        )
```

- [ ] Adicionar helper `_looks_like_ticket` perto de `_derive_slug`:

```python
import re as _re

_TICKET_RE = _re.compile(r"^[A-Z]{2,6}-\d{2,6}$")


def _looks_like_ticket(text: str) -> bool:
    """True quando o argv tem forma de ticket-id (ex.: IN-37234)."""
    return bool(_TICKET_RE.match(text.strip()))
```

- [ ] Rodar e ver PASS (suite do arquivo inteira):

```bash
.venv/bin/pytest tests/unit/test_engine_plan_frontdoor.py -q
```

Esperado: todos passam (slugify + casing + seed).

#### Step 1.7 — Regression guard + commit

- [ ] Confirmar que os testes legados do plan + render seguem verdes:

```bash
.venv/bin/pytest tests/unit/test_engine_plan_resume.py -q
.venv/bin/pytest -k "render_template or plan_intake or commands_plan" -q
```

Esperado: 0 failed.

- [ ] Commit atômico:

```bash
git add engine/plan.py tests/unit/test_engine_plan_frontdoor.py
git commit -m "feat(plan): front-door ticket/frase + CASING-BUG fix (Wave 1)"
```

**Anti-padrões (NÃO fazer):**
- Não tocar `engine/vision/` (é a Task 2).
- Não refatorar `run()` além do ponto de seed + `_elicit_slug`.
- Não fazer doc-sync aqui (é a Task 6).
- Não remover o token `{{FEATURE_SLUG}}` uppercase do dict (compat).
- Não usar Write/Edit fora de `engine/plan.py` + o arquivo de teste novo.

---

### Task 2: Vision wire (engine/plan.py) — depende da Task 1

Ligar `engine/vision/screenshot.py` (dormente) ao front-door: path(s) na source-inquiry → `normalize_screenshot_path` → `validate_screenshot` → copia pra `{feature}/screenshots/` → `compute_screenshot_fingerprint` no manifest. `infer_platform_inference` só como hint. Engine NÃO interpreta pixel.

**Files:**
- Modify `engine/plan.py` — adicionar `_ingest_screenshot(raw_input: str, feature_path: Path) -> dict | None` helper + manifest writer `_record_screenshot_manifest`.
- Create `tests/unit/test_engine_plan_screenshot.py`

**Interfaces:**
- Consumes `engine.vision.screenshot.normalize_screenshot_path(raw_input: str, feature_dir: Path) -> Path` (existente, ~L328).
- Consumes `engine.vision.screenshot.validate_screenshot(path: Path, *, max_size_mb: int = 10) -> list[str]` (existente, ~L188).
- Consumes `engine.vision.screenshot.compute_screenshot_fingerprint(path: Path) -> str` (existente, ~L289).
- Consumes `engine.vision.screenshot.infer_platform_inference(width: int, height: int) -> PlatformInference` (existente, ~L224).
- Consumes `engine.vision.screenshot.load_screenshot(path: Path) -> ScreenshotMetadata` (existente, ~L140).
- Produces `engine.plan._ingest_screenshot(raw_input: str, feature_path: Path) -> dict | None` — retorna `{path, fingerprint, platform_hint}` ou `None` quando inválido (sem crash).

#### Step 2.1 — Teste falhando: traversal rejeitado + formato inválido limpo

- [ ] Escrever `tests/unit/test_engine_plan_screenshot.py`:

```python
"""Vision-wire tests para engine.plan._ingest_screenshot (Wave 1 AI-first C3a).

O engine sanitiza + registra ponteiro; NUNCA interpreta pixel. Cobre:
traversal rejeitado, formato inválido rejeitado sem crash, fingerprint
estável, cópia pra screenshots/.

Refs: docs/superpowers/specs/2026-06-17-ai-first-interaction-layer-design.md §4 C3a
"""

from __future__ import annotations

import struct
from pathlib import Path

from engine import plan


def _write_png(path: Path, width: int = 400, height: int = 800) -> None:
    """Escreve um PNG mínimo válido (header + IHDR) pros parsers magic-byte."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    chunk = struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr + struct.pack(">I", 0)
    path.write_bytes(sig + chunk + b"\x00" * 32)


def test_ingest_rejects_path_traversal(tmp_path: Path) -> None:
    feature = tmp_path / "feature"
    feature.mkdir()
    # Path absoluto fora da feature → ValueError dentro de normalize →
    # _ingest devolve None (rejeição limpa, sem crash).
    result = plan._ingest_screenshot("/etc/passwd", feature)
    assert result is None


def test_ingest_rejects_invalid_format(tmp_path: Path) -> None:
    feature = tmp_path / "feature"
    feature.mkdir()
    bogus = feature / "notes.txt"
    bogus.write_text("not an image", encoding="utf-8")
    result = plan._ingest_screenshot(str(bogus), feature)
    assert result is None  # validate_screenshot rejeita, sem crash
```

- [ ] Rodar e ver FAIL:

```bash
.venv/bin/pytest tests/unit/test_engine_plan_screenshot.py -q
```

Esperado: `AttributeError: ... '_ingest_screenshot'`.

#### Step 2.2 — Impl `_ingest_screenshot`

- [ ] Adicionar em `engine/plan.py` (perto dos helpers de feature path):

```python
def _ingest_screenshot(raw_input: str, feature_path: Path) -> Optional[dict]:
    """Sanitiza + registra um screenshot fornecido conversacionalmente.

    spec §4 C3a — o engine NÃO interpreta pixel: normaliza o path
    (traversal-safe), valida formato/tamanho, copia pra
    ``{feature}/screenshots/`` e calcula o fingerprint sha256. Devolve
    ``None`` em qualquer rejeição (path inválido, formato inválido) —
    mensagem mentor-calmo no stderr, segue sem a imagem. ``platform_hint``
    é só hint de baixa confiança que o conductor pode sobrepor.
    """
    from engine.vision import screenshot as _ss

    try:
        resolved = _ss.normalize_screenshot_path(raw_input, feature_path)
    except (ValueError, FileNotFoundError) as exc:
        sys.stderr.write(f"forge plan: screenshot ignorado — {exc}\n")
        return None

    issues = _ss.validate_screenshot(resolved)
    if issues:
        sys.stderr.write(
            "forge plan: screenshot ignorado — "
            + "; ".join(issues)
            + ". Sigo sem a imagem; marque needs-elicitation se for UI.\n"
        )
        return None

    screenshots_dir = feature_path / "screenshots"
    ensure_dir(screenshots_dir)
    dest = screenshots_dir / resolved.name
    if resolved.resolve() != dest.resolve():
        shutil.copy2(resolved, dest)

    fingerprint = _ss.compute_screenshot_fingerprint(dest)
    meta = _ss.load_screenshot(dest)
    return {
        "path": str(dest.relative_to(feature_path)),
        "fingerprint": fingerprint,
        "platform_hint": meta.platform_inference.platform,
        "platform_confidence": meta.platform_inference.confidence,
    }
```

- [ ] Confirmar imports no topo de `engine/plan.py`: `shutil` e `ensure_dir` já presentes (usados por `_render_template`); `Optional` já importado. Se `shutil` ausente, adicionar `import shutil`.

- [ ] Rodar e ver PASS:

```bash
.venv/bin/pytest tests/unit/test_engine_plan_screenshot.py -q
```

Esperado: 2 passed.

#### Step 2.3 — Teste falhando: fingerprint estável + cópia ok

- [ ] Adicionar ao arquivo de teste:

```python
def test_ingest_copies_and_fingerprints(tmp_path: Path) -> None:
    feature = tmp_path / "feature"
    (feature / "screenshots").mkdir(parents=True)
    src = feature / "screenshots" / "screen.png"
    _write_png(src, width=400, height=900)

    result = plan._ingest_screenshot("screen.png", feature)
    assert result is not None
    assert result["path"] == "screenshots/screen.png"
    assert len(result["fingerprint"]) == 64  # sha256 hex
    assert result["platform_hint"] in {"mobile", "tablet", "web", "unknown"}


def test_ingest_fingerprint_stable(tmp_path: Path) -> None:
    feature = tmp_path / "feature"
    (feature / "screenshots").mkdir(parents=True)
    src = feature / "screenshots" / "a.png"
    _write_png(src)
    r1 = plan._ingest_screenshot("a.png", feature)
    r2 = plan._ingest_screenshot("a.png", feature)
    assert r1 is not None and r2 is not None
    assert r1["fingerprint"] == r2["fingerprint"]
```

- [ ] Rodar e ver PASS:

```bash
.venv/bin/pytest tests/unit/test_engine_plan_screenshot.py -q
```

Esperado: 4 passed.

#### Step 2.4 — Commit

- [ ] Confirmar suite vision + plan verde:

```bash
.venv/bin/pytest tests/unit/test_engine_plan_screenshot.py tests/unit/test_engine_plan_frontdoor.py -q
.venv/bin/pytest -k vision -q
```

Esperado: 0 failed.

- [ ] Commit atômico:

```bash
git add engine/plan.py tests/unit/test_engine_plan_screenshot.py
git commit -m "feat(plan): wire engine/vision screenshot ingest no front-door (Wave 1 C3a)"
```

**Anti-padrões (NÃO fazer):**
- Não modificar `engine/vision/screenshot.py` (é reuso puro — só consome).
- Não interpretar pixel/conteúdo da imagem no engine (isso é do conductor multimodal).
- Não fazer crash em screenshot inválido — rejeição limpa devolvendo `None`.
- Não fazer doc-sync aqui.

---

### Task 3: Driver SKILL.md + AGENTS.md + install (engine/init.py)

Criar a `SKILL.md` (Claude Code) + `AGENTS.md` (opencode) no repo (FORGE_HOME) e instalar brownfield-safe no consumidor via `forge init`.

**Files:**
- Create `skills/feature-forge/SKILL.md`
- Create `templates/AGENTS.md.template` (template do AGENTS.md do consumidor)
- Modify `engine/init.py` — adicionar `_install_ai_driver(project_root: Path) -> None` (perto de `_install_hooks`, ~L641) + chamar em `_run_pipeline` no Step 13 (~L1607-1628).
- Create `tests/integration/test_init_ai_driver.py`

**Interfaces:**
- Consumes `engine.utils.settings_merge.merge_settings_json(existing: dict, additions: dict) -> dict` (existente — padrão brownfield-safe reusado pra append-only).
- Consumes `engine.utils.paths.forge_home() -> Path` (existente).
- Produces `engine.init._install_ai_driver(project_root: Path) -> None` — copia `SKILL.md` pra `.claude/skills/feature-forge/SKILL.md` (brownfield-safe: não clobber se já existe non-forge) e renderiza `AGENTS.md` na raiz (append-only).

#### Step 3.1 — Criar SKILL.md (protocolo + workflow)

- [ ] Criar `skills/feature-forge/SKILL.md` (voz mentor calmo, conciso/token-aware):

```markdown
---
name: feature-forge
description: Dirige o feature-forge — orquestra o ciclo de planejamento e implementação de features mobile. Use ao rodar qualquer comando `forge`.
---

# feature-forge — driver

Você dirige o `forge`. O engine emite intenções e pausa; você responde e re-invoca.

## Protocolo do intent loop

Ao rodar um comando `forge` que sai com **exit 2** + uma linha
`<FORGE_INTENT kind=... intent-id=... question=... options=... .../>` no stdout:

1. Parseie os atributos do marker (`kind`, `intent-id`, `question`, `options`).
2. Chame `AskUserQuestion` nativo com o `question` + `options`.
3. Escreva `.claude/forge/state/forge-response.json` no schema de
   `docs/schemas/intent-protocol.md`, com o **mesmo `intent-id`**.
4. Re-invoque o `forge` com **argv idêntico** ao da chamada que pausou.
5. Repita até exit 0, 1 ou 130.

Legenda de exit: **0**=ok · **1**=erro · **2**=pausado (responda) · **130**=cancelado.

> Re-invoque com argv idêntico. Mudar o argv troca o `intent-id` e o engine
> rejeita (exit 1).

## Workflow — mapa de verbos

| Verbo | O que dirige |
|---|---|
| `forge init` | install no projeto (interativo via intent loop) |
| `forge plan "<ticket\|frase\|slug>"` | planejamento — ver abaixo |
| `forge implement` | dirige a execução das waves |
| `forge verify` | cascade de validators |
| `forge status` | estado da feature |

**Ao rodar `forge plan`:** depois que o engine derivar/confirmar o slug e
semear o intake, **dispatch `agents/planning-conductor.md` (lido do FORGE_HOME)**
e dirija a elicitação dele — o conductor usa `AskUserQuestion` direto. O
screenshot entra conversacionalmente (path na source-inquiry), sem flag.
```

#### Step 3.2 — Criar AGENTS.md template (opencode)

- [ ] Criar `templates/AGENTS.md.template`:

```markdown
# feature-forge — driver (opencode)

Você dirige o `forge`. O engine emite intenções e pausa; você responde e re-invoca.

## Protocolo do intent loop (opencode)

Ao rodar um `forge` que sai com **exit 2** + linha `<FORGE_INTENT .../>`:

1. Leia o pending em `.claude/forge/state/forge-pending.json`.
2. Pergunte ao usuário (mecanismo opencode) com `question` + `options`.
3. Escreva `.claude/forge/state/forge-response.json` com o **mesmo `intent-id`**
   (schema: `docs/schemas/intent-protocol.md`).
4. Re-invoque o `forge` com **argv idêntico**.
5. Repita até exit 0/1/130. Legenda: 0=ok · 1=erro · 2=pausado · 130=cancelado.

## Workflow

Ao rodar `forge plan`, dispatch `agents/planning-conductor.md` (do FORGE_HOME)
e dirija a elicitação. Screenshot entra conversacionalmente (path na
source-inquiry), sem flag.
```

#### Step 3.3 — Teste falhando: install idempotente + brownfield-safe

- [ ] Escrever `tests/integration/test_init_ai_driver.py`:

```python
"""Install do driver AI-first (SKILL.md + AGENTS.md) via forge init.

Cobre: idempotência, brownfield (preserva conteúdo existente), conteúdo
mínimo (legenda de exit + regra de dispatch do conductor).

Refs: docs/superpowers/specs/2026-06-17-ai-first-interaction-layer-design.md §4 C1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import init as forge_init


pytestmark = pytest.mark.integration


def test_install_ai_driver_creates_skill_and_agents(
    tmp_forge_project: Path,
) -> None:
    forge_init._install_ai_driver(tmp_forge_project)
    skill = tmp_forge_project / ".claude" / "skills" / "feature-forge" / "SKILL.md"
    agents = tmp_forge_project / "AGENTS.md"
    assert skill.is_file()
    assert agents.is_file()
    body = skill.read_text(encoding="utf-8")
    # Conteúdo mínimo: legenda de exit + regra de dispatch.
    assert "exit 2" in body
    assert "planning-conductor.md" in body
    assert "argv idêntico" in body


def test_install_ai_driver_idempotent(tmp_forge_project: Path) -> None:
    forge_init._install_ai_driver(tmp_forge_project)
    skill = tmp_forge_project / ".claude" / "skills" / "feature-forge" / "SKILL.md"
    first = skill.read_text(encoding="utf-8")
    forge_init._install_ai_driver(tmp_forge_project)
    assert skill.read_text(encoding="utf-8") == first  # sem duplicar/clobber


def test_install_ai_driver_brownfield_preserves_existing_agents(
    tmp_forge_project: Path,
) -> None:
    agents = tmp_forge_project / "AGENTS.md"
    agents.write_text("# Meu AGENTS.md\nregras do usuário\n", encoding="utf-8")
    forge_init._install_ai_driver(tmp_forge_project)
    body = agents.read_text(encoding="utf-8")
    assert "regras do usuário" in body  # conteúdo do usuário preservado
    assert "feature-forge" in body  # bloco do forge anexado
```

- [ ] Rodar e ver FAIL:

```bash
.venv/bin/pytest tests/integration/test_init_ai_driver.py -q
```

Esperado: `AttributeError: ... '_install_ai_driver'`.

#### Step 3.4 — Impl `_install_ai_driver`

- [ ] Adicionar em `engine/init.py` (perto de `_install_hooks`, ~L676):

```python
# ── AI driver install (Step 13.5) ────────────────────────────────────────────

_AGENTS_FORGE_MARKER = "<!-- FORGE_AI_DRIVER -->"


def _install_ai_driver(project_root: Path) -> None:
    """Instala a SKILL.md (Claude Code) + AGENTS.md (opencode) no consumidor.

    Brownfield-safe (spec §4 C1):
    - `SKILL.md` → `.claude/skills/feature-forge/SKILL.md`: copia do FORGE_HOME.
      Se já existe e NÃO carrega o front-matter do forge, preserva o do usuário
      (não clobber); senão sobrescreve (canonical wins, idempotente).
    - `AGENTS.md` (raiz): append-only via marker. Se o marker já existe, no-op;
      se o arquivo existe sem o marker, anexa o bloco do forge preservando o
      conteúdo do usuário; se ausente, cria.
    """
    home = forge_home()

    # SKILL.md
    skill_src = home / "skills" / "feature-forge" / "SKILL.md"
    if skill_src.is_file():
        skill_dst = project_root / ".claude" / "skills" / "feature-forge" / "SKILL.md"
        canonical = skill_src.read_text(encoding="utf-8")
        if not skill_dst.exists():
            ensure_dir(skill_dst.parent)
            skill_dst.write_text(canonical, encoding="utf-8")
        elif "name: feature-forge" in skill_dst.read_text(encoding="utf-8"):
            # É a nossa skill (não a do usuário) → canonical wins (idempotente).
            skill_dst.write_text(canonical, encoding="utf-8")
        # else: existe mas é do usuário → preserva, não clobber.

    # AGENTS.md (append-only via marker)
    agents_tpl = home / "templates" / "AGENTS.md.template"
    if agents_tpl.is_file():
        block = _AGENTS_FORGE_MARKER + "\n" + agents_tpl.read_text(encoding="utf-8")
        agents_dst = project_root / "AGENTS.md"
        if not agents_dst.exists():
            agents_dst.write_text(block + "\n", encoding="utf-8")
        else:
            current = agents_dst.read_text(encoding="utf-8")
            if _AGENTS_FORGE_MARKER not in current:
                agents_dst.write_text(current.rstrip("\n") + "\n\n" + block + "\n", encoding="utf-8")
            # else: marker presente → idempotente, no-op.
```

- [ ] Rodar e ver PASS:

```bash
.venv/bin/pytest tests/integration/test_init_ai_driver.py -q
```

Esperado: 3 passed.

#### Step 3.5 — Wire no `_run_pipeline`

- [ ] Em `engine/init.py` no Step 13 (~L1617, após `_merge_forge_hooks_into_settings`), adicionar a chamada dentro do mesmo `try`:

```python
        _merge_forge_hooks_into_settings(project_root)
        # Step 13.5 — driver AI-first (SKILL.md CC + AGENTS.md opencode).
        # Brownfield-safe, idempotente (spec §4 C1).
        _install_ai_driver(project_root)
        if n_hooks:
            renderer.write(f"  └─ {n_hooks} hooks instalados em .claude/forge/hooks/")
```

- [ ] Rodar smoke do init greenfield (confirma que o pipeline não quebra):

```bash
.venv/bin/pytest tests/integration/test_init_greenfield.py -q
```

Esperado: 0 failed (e o driver fica instalado pelo pipeline).

#### Step 3.6 — Commit

- [ ] Commit atômico:

```bash
git add skills/feature-forge/SKILL.md templates/AGENTS.md.template engine/init.py tests/integration/test_init_ai_driver.py
git commit -m "feat(init): driver AI-first SKILL.md + AGENTS.md install brownfield-safe (Wave 1 C1)"
```

**Anti-padrões (NÃO fazer):**
- Não fazer o engine importar nada de SKILL.md/AGENTS.md (Decisão 22 — são comportamento pro host).
- Não clobber `AGENTS.md`/`SKILL.md` pré-existente do usuário (brownfield-safe).
- Não hardcodar o path do FORGE_HOME — usar `forge_home()` (Decisão 18).
- Não fazer doc-sync aqui.

---

### Task 4: Grounded-challenge Phase 2.5 (prompt-only)

Adicionar a Phase 2.5 entre Phase 2 e Phase 3 no `planning-conductor.md` (confronta o pedido contra grafo/inventory/L2) + cena no roteiro de UX. Prompt-only — sem pytest; valida via smoke + roteiro.

**Files:**
- Modify `agents/planning-conductor.md` — inserir `### Phase 2.5 — Grounded challenge` entre Phase 2 (~L309) e Phase 3 (~L401); renumerar referências internas a "6 phases" → "7 phases" se necessário.
- Modify `docs/ux/forge-plan-roteiro.md` — adicionar cena de confronto + no-visual branch.

**Interfaces:**
- Consumes (no prompt): grafo Q1 (similar-features) + Q11-Q17 (reuse-intelligence); `engine/inventory/` (design-system/i18n/conventions); L2 `decisions-frozen` + memory L2/L3 — todos já carregados pelo conductor na Phase 1.
- Produces: cada conflito vira pergunta agrupada na Phase 3 (`AskUserQuestion` existente); resolução + rationale entram no `rationale-trace.yaml`.

#### Step 4.1 — Inserir Phase 2.5 no conductor

- [ ] Em `agents/planning-conductor.md`, inserir entre o fim da Phase 2 (~L399) e `### Phase 3` (~L401):

```markdown
### Phase 2.5 — Grounded challenge (confronta o pedido)

Antes de elicitar, confronte o pedido contra o que JÁ existe. Esta fase NÃO
bloqueia — ela transforma conflitos em perguntas pra Phase 3 (D3: confronta +
humano decide). Inputs (reuso do que você já carregou na Phase 1):

- Grafo **Q1** (similar-features) + **Q11-Q17** (reuse-intelligence)
- `engine/inventory/` — design-system, i18n, conventions
- L2 `decisions-frozen` + memory L2/L3

Confronte em 4 frentes. Pra cada conflito, registre um item `challenge:` com
`rationale-trace`:

| Frente | Exemplo de confronto |
|---|---|
| **Duplicação** | "Q1 mostra `bonsai-list` já persiste `starred` — reusar / estender / novo?" |
| **Terminologia** | "o termo X conflita com a entidade Y da L2 — alinhar nomenclatura?" |
| **Decisão frozen** | "isso contraria a decisão D-N (frozen) — revisitar ou ajustar o pedido?" |
| **Fora do design-system** | "o componente Z não está no design-system do projeto — usar o equivalente W?" |

Cada conflito vira uma pergunta na Phase 3 (agrupada no `AskUserQuestion`
existente), no formato "confronta + humano decide". A resolução + o porquê
entram no `rationale-trace.yaml`.

#### No-visual branch (D5 — feature UI/product sem input visual)

Se a feature é UI/product e não há screenshot/mockup, confronte no front da
elicitação com 3-caminhos:

```
🛑 Feature de UI sem referência visual

Esta tela vai ser planejada sem nenhuma referência visual. Três caminhos:

  1) Anexar mockup/screenshot
     vira fluxo "com screenshot" (o engine sanitiza + fingerprint).

  2) Descrever a tela em texto
     os estados viram `confirmed` com `source: prd/intake`.

  3) Reusar a screen-analysis de uma feature similar da L2
     herda a extração de uma tela parecida (Q1 mostra candidatos).

Abortar continua um caminho honesto só se nenhum dos três rolar.
```

#### Degradação graciosa

Grafo/inventory/L2 ausente (projeto sem bootstrap) → pule o que não tem e
anote no `rationale-trace` ("grafo ausente — confronto de duplicação pulado").
NUNCA crashe o grill por falta de fonte.
```

- [ ] Atualizar o header da seção Strategy (~L97) de "6 phases" pra "7 phases" e qualquer enumeração que liste as fases por número (busca por "Phase 6" e "6 phases" no arquivo; ajustar contagem, não o conteúdo das outras fases).

#### Step 4.2 — Cena no roteiro de UX

- [ ] Em `docs/ux/forge-plan-roteiro.md`, adicionar uma cena de confronto + no-visual branch (replicar o estilo das cenas existentes — narrativa mentor-calmo + bloco de transcript). Inserir após a cena de ambiguity-map (procurar a cena correspondente à Phase 2 e adicionar a 2.5 logo depois).

#### Step 4.3 — Smoke + commit

- [ ] Validar que o prompt não tem placeholders soltos nem comandos inventados:

```bash
grep -nE '\b(TBD|TODO|FIXME)\b' agents/planning-conductor.md docs/ux/forge-plan-roteiro.md
grep -nE 'forge [a-z-]+ --' agents/planning-conductor.md
```

Esperado: nenhuma saída (sem placeholder, sem flag em comando citado).

- [ ] Confirmar suite agnóstica não quebrou (prompts não têm pytest, mas confirma que nada importava os arquivos):

```bash
.venv/bin/pytest -m "not integration and not e2e" -q | tail -1
```

Esperado: count ≥ 1611, 0 failed.

- [ ] Commit atômico:

```bash
git add agents/planning-conductor.md docs/ux/forge-plan-roteiro.md
git commit -m "feat(conductor): grounded-challenge Phase 2.5 + no-visual branch (Wave 1 C4)"
```

**Anti-padrões (NÃO fazer):**
- Não escrever código Python — esta task é prompt-only.
- Não inventar comando `forge` fora da command-surface canônica.
- Não tornar o grill bloqueante (D3: confronta + humano decide).
- Não usar `AskUserQuestion` novo — reusar o agrupado da Phase 3.
- Não fazer doc-sync de CHANGELOG/handoff aqui (é a Task 6); o roteiro de UX faz parte do escopo desta task porque é onde a cena vive.

---

### Task 5: Readiness enforce — needs-elicitation scan

Adicionar scan de `needs-elicitation: true` não-promovido na Phase 5 do `readiness-reviewer.md` (block em contract spec, warning em narrativa) + backing no `validators/validate_readiness.py`.

**Files:**
- Modify `agents/readiness-reviewer.md` — adicionar item ao `### Phase 5 — Discipline scan` (~L239-261).
- Modify `validators/validate_readiness.py` — adicionar `_scan_needs_elicitation(f_root: Path) -> list[str]` + integrar no `validate()` (~L70).
- Create `tests/validators/test_validate_readiness_elicitation.py`

**Interfaces:**
- Consumes `validators._common.result_fail / result_warn / make_paths` (já usados em `validate_readiness.py`).
- Consumes `validators._common.feature_dir(project_root, slug) -> Path` (já usado, ~L81).
- Produces `validators.validate_readiness._scan_needs_elicitation(f_root: Path) -> list[str]` — retorna lista de `arquivo:linha` com `needs-elicitation` ativo em contract spec (`*-spec.yaml`/`task-*.md`).

#### Step 5.1 — Teste falhando

- [ ] Escrever `tests/validators/test_validate_readiness_elicitation.py`:

```python
"""needs-elicitation scan no validate_readiness (Wave 1 C5).

Block-severity quando `needs-elicitation: true` sobrevive não-promovido em
contract spec; warning em narrativa.

Refs: docs/superpowers/specs/2026-06-17-ai-first-interaction-layer-design.md §4 C5
"""

from __future__ import annotations

from pathlib import Path

from validators import validate_readiness


def test_scan_flags_needs_elicitation_in_contract(tmp_path: Path) -> None:
    f_root = tmp_path
    spec = f_root / "data-contract-spec.yaml"
    spec.write_text(
        "fields:\n  - name: starred\n    persist: needs-elicitation\n",
        encoding="utf-8",
    )
    hits = validate_readiness._scan_needs_elicitation(f_root)
    assert any("data-contract-spec.yaml" in h for h in hits)


def test_scan_clean_when_no_marker(tmp_path: Path) -> None:
    f_root = tmp_path
    (f_root / "data-contract-spec.yaml").write_text(
        "fields:\n  - name: starred\n    persist: true\n",
        encoding="utf-8",
    )
    assert validate_readiness._scan_needs_elicitation(f_root) == []
```

- [ ] Rodar e ver FAIL:

```bash
.venv/bin/pytest tests/validators/test_validate_readiness_elicitation.py -q
```

Esperado: `AttributeError: ... '_scan_needs_elicitation'`.

#### Step 5.2 — Impl `_scan_needs_elicitation` + integrar

- [ ] Adicionar em `validators/validate_readiness.py` (antes de `validate()`):

```python
# Contract specs onde needs-elicitation não-promovido é block-severity.
_CONTRACT_GLOBS = ("*-spec.yaml", "tasks/task-*.md", "*-contract*.yaml")


def _scan_needs_elicitation(f_root: Path) -> list[str]:
    """Retorna `arquivo:linha` com `needs-elicitation` ativo em contract specs.

    spec §4 C5 — fecha o ponto-cego "thin-but-structurally-complete": um campo
    `needs-elicitation` que o conductor não promoveu a `blocking: true` open
    question pode escapar como ready se a cadeia story→task fecha nominalmente.
    """
    hits: list[str] = []
    for pattern in _CONTRACT_GLOBS:
        for path in sorted(f_root.glob(pattern)):
            if not path.is_file():
                continue
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if "needs-elicitation" in line:
                    rel = path.relative_to(f_root)
                    hits.append(f"{rel}:{lineno}")
    return hits
```

- [ ] Integrar no `validate()` — após o parse do verdict (~L103, antes do `return` de sucesso), adicionar o gate:

```python
    elicitation_hits = _scan_needs_elicitation(f_root)
    if elicitation_hits:
        return result_fail(
            f"needs-elicitation não-promovido em {len(elicitation_hits)} contract spec(s)",
            what_failed="needs-elicitation: true sobreviveu em contract spec",
            where="; ".join(elicitation_hits[:5]),
            why=[
                "Campo needs-elicitation deve virar blocking:true open-question, não escapar como ready.",
                "Fecha o ponto-cego thin-but-structurally-complete (spec C5).",
            ],
            paths=make_paths(
                "Promover cada needs-elicitation a blocking:true em open-questions.yaml",
                "O conductor elicita na próxima rodada de Phase 3.",
                "Resolver inline se o valor já é conhecido",
                "Se foi marcado por engano e o default é claro.",
                "Reverter pra antes do plan — `forge undo`",
                "Se o escopo da feature mudou.",
            ),
        )
```

- [ ] Rodar e ver PASS:

```bash
.venv/bin/pytest tests/validators/test_validate_readiness_elicitation.py -q
```

Esperado: 2 passed.

#### Step 5.3 — Atualizar o prompt do readiness-reviewer + commit

- [ ] Em `agents/readiness-reviewer.md` no `### Phase 5 — Discipline scan` (~L254, junto do bloco "Forbidden phrases"), adicionar:

```markdown
- **needs-elicitation não-promovido** (spec C5):
  ```bash
  grep -rEn 'needs-elicitation' docs/.../features/{slug}/*-spec.yaml \
    docs/.../features/{slug}/tasks/
  ```
  Cada hit em contract spec ou task contract é **block-severity** (o campo
  devia ter virado `blocking: true` open-question). Hits em narrativa
  (PRD prosa, intake) são **warning-severity**.
```

- [ ] Confirmar que a suite de validators não regrediu:

```bash
.venv/bin/pytest tests/validators/ -q | tail -1
```

Esperado: count ≥ baseline da pasta, 0 failed.

- [ ] Commit atômico:

```bash
git add agents/readiness-reviewer.md validators/validate_readiness.py tests/validators/test_validate_readiness_elicitation.py
git commit -m "feat(readiness): needs-elicitation scan block em contract spec (Wave 1 C5)"
```

**Anti-padrões (NÃO fazer):**
- Não reescrever o forbidden-phrases scan — estender ao lado.
- Não tornar needs-elicitation em narrativa block-severity (só contract specs bloqueiam).
- Não mudar a tabela de verdict da Phase 6 do readiness (o `result_fail` já casa com `blocked`).
- Não fazer doc-sync aqui.

---

### Task 6: Doc-sync (Mandamento 6) — por último

Sincronizar CHANGELOG + handoff + command-surface + pending + getting-started + README (se stats). Reflete o que as Tasks 1-5 entregaram.

**Files:**
- Modify `CHANGELOG.md` — `## [Unreleased]`: Added (driver + front-door + grounded-challenge + readiness), Fixed (CASING-BUG), Changed (vision wire).
- Modify `docs/design/08-session-handoff.md` — `**Última atualização:**` = 2026-06-17 + `**Estado:**` reflete Wave 1.
- Modify `docs/design/06-command-surface.md` — `forge plan` aceita ticket/frase (comportamento novo).
- Modify `docs/design/04-pending.md` — risca AMBIGUITY-DEAD + CASING-BUG; registra OUT (MCP, EXIT-2-COLLISION, DEAD-VERIFY, CONC-1, TOKEN-BLIND) como follow-ups.
- Modify `docs/guides/getting-started.md` — seção "como o forge fala com o host AI" (o driver).
- Modify `README.md` — só se stats mudaram (novo artefato/skill).

**Interfaces:** N/A (doc-only).

#### Step 6.1 — CHANGELOG

- [ ] Em `CHANGELOG.md` sob `## [Unreleased]`:

```markdown
### Added
- Camada de interação AI-first (Wave 1): driver `SKILL.md` (Claude Code) +
  `AGENTS.md` (opencode) instalados brownfield-safe por `forge init`; ensinam
  o host a dirigir o intent loop (exit 2 + marker → AskUserQuestion → response
  → re-invoca) e a dispatchar o `planning-conductor.md` do FORGE_HOME.
- `forge plan` front-door: aceita ticket-id (ex.: `IN-37234`) ou frase livre
  como argv posicional, deriva slug kebab-case determinístico, confirma
  conversacionalmente e semeia o texto cru no `feature-intake.md`.
- Grounded-challenge Phase 2.5 no `planning-conductor.md`: confronta o pedido
  contra grafo (Q1/Q11-Q17) + inventory + L2 (duplicação/terminologia/decisão
  frozen/fora-do-DS), com no-visual branch (3-caminhos) e degradação graciosa.
- Readiness enforce: `validate_readiness` + `readiness-reviewer.md` Phase 5
  agora escaneiam `needs-elicitation` não-promovido (block em contract spec,
  warning em narrativa).

### Fixed
- CASING-BUG: `_render_template` agora substitui `{{feature_slug}}` (lowercase,
  como os 74 usos nos templates) — antes só substituía `{{FEATURE_SLUG}}`
  uppercase e o token sobrava cru nos artefatos.

### Changed
- `engine/vision/screenshot.py` (antes dormente) agora é ligado ao front-door
  do `forge plan`: screenshot fornecido conversacionalmente é normalizado
  (traversal-safe), validado, copiado pra `{feature}/screenshots/` e registrado
  com fingerprint sha256. O engine não interpreta pixel.
```

#### Step 6.2 — Handoff + command-surface + pending + getting-started

- [ ] `docs/design/08-session-handoff.md`: atualizar `**Última atualização:** 2026-06-17 (Wave 1 AI-first — driver + grill)` e `**Estado:**` refletindo a camada AI-first entregue. Adicionar linha na tabela de categorias se houver nova wave.

- [ ] `docs/design/06-command-surface.md`: na linha do `forge plan`, registrar que aceita `<ticket|frase|slug>` como argv posicional (Decisão 10 preservada — argv, não flag).

- [ ] `docs/design/04-pending.md`: riscar (strike-through ou mover pra "fechados") **AMBIGUITY-DEAD** e **CASING-BUG**; adicionar como follow-ups OUT desta wave: **MCP server** (norte estratégico D1), **EXIT-2-COLLISION** (wave de robustez), **DEAD-VERIFY** (wave de hooks), **CONC-1** (wave de concorrência), **TOKEN-BLIND/`--json`/manifesto/`forge status` router** (wave de token economy).

- [ ] `docs/guides/getting-started.md`: adicionar seção "Como o forge fala com seu host AI" explicando o driver (SKILL.md/AGENTS.md) + o intent loop em linguagem de usuário.

- [ ] `README.md`: atualizar stats só se o count de artefatos/skills mudou (nova `SKILL.md`).

#### Step 6.3 — Verify + commit

- [ ] Rodar suite completa + verify:

```bash
.venv/bin/pytest -m "not integration and not e2e" -q | tail -1
.venv/bin/pytest -m integration -q | tail -1
./bin/forge verify
```

Esperado: rapid ≥ 1611, integration ≥ 168, 0 failed; `forge verify` sem hard fail.

- [ ] Commit atômico:

```bash
git add CHANGELOG.md docs/design/08-session-handoff.md docs/design/06-command-surface.md docs/design/04-pending.md docs/guides/getting-started.md README.md
git commit -m "docs(sync): Wave 1 AI-first — driver/front-door/grill/readiness + CASING-BUG"
```

**Anti-padrões (NÃO fazer):**
- Não tocar `docs/design/01-decisions.md` (nenhuma decisão revisitada — spec §10).
- Não atualizar README stats se nada mudou.
- Não incluir escopo OUT como entregue — só registrar como follow-up em 04-pending.

---

## Self-Review

**Spec coverage (spec §4 componentes → tasks):**
- C1 (driver SKILL.md + AGENTS.md + install brownfield-safe) → Task 3. ✅
- C3 (front-door argv ticket/frase + slugify + confirma + seed + troca SystemExit) → Task 1. ✅
- CASING-BUG (`_render_template` `{{feature_slug}}` lowercase) → Task 1. ✅
- C3a (vision wire: normalize→validate→copy→fingerprint, hint só) → Task 2. ✅
- C4 (grounded-challenge Phase 2.5 + no-visual branch + degradação graciosa) → Task 4. ✅
- C5 (readiness enforce: needs-elicitation scan, block contract / warning narrativa) → Task 5. ✅
- Doc-sync (§9) → Task 6. ✅
- Testing (§7): front-door unit (Task 1), vision unit (Task 2), SKILL/AGENTS smoke+install (Task 3), grounded-challenge smoke+roteiro (Task 4), readiness validator test (Task 5). ✅

**Decisões locked (spec §10):** nenhuma revisitada. 22 preservada (engine não importa SKILL.md/AGENTS.md — Task 3 anti-padrão explícito). 18 preservada (`forge_home()`, Task 3). 10 preservada (argv posicional + screenshot conversacional, sem flag — Tasks 1/2). ✅

**Escopo OUT respeitado:** MCP, EXIT-2-COLLISION, DEAD-VERIFY, CONC-1, TOKEN-BLIND não implementados — só registrados como follow-up em 04-pending (Task 6). ✅

**Placeholder scan:** nenhum `TBD`/`TODO`/`FIXME` no plano. Os `...` que aparecem (`docs/.../features/{slug}/`) são verbatim de comandos `grep` dentro do prompt do readiness-reviewer (sintaxe de path glob do agente), não placeholders do plano. ✅

**Type/name consistency:** `_derive_slug`, `_seed_intake_source`, `_looks_like_ticket`, `_render_template`, `_ingest_screenshot`, `_install_ai_driver`, `_scan_needs_elicitation` — grafia consistente em todas as referências entre tasks e Self-Review. Assinaturas das funções de `engine/vision/screenshot.py` (`normalize_screenshot_path`, `validate_screenshot`, `compute_screenshot_fingerprint`, `infer_platform_inference`, `load_screenshot`) batem com o código lido. ✅

**Reuso (Mandamento 3):** `engine/vision/screenshot.py` reusado (Task 2 não reescreve); `merge_settings_json` reusado como padrão brownfield (Task 3); conductor Phase 1-4 + `AskUserQuestion` agrupado reusados (Task 4); `validate_readiness` + forbidden-phrases scan estendidos, não recriados (Task 5). ✅

**Dependências:** Task 2 depende de Task 1 (mesmo arquivo `engine/plan.py` + slugify). Tasks 3/4/5 independentes entre si. Task 6 por último (reflete 1-5). ✅
