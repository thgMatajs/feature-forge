"""Integration: brownfield init flow via composer + ask_three_paths.

W7.1 do plano DET-6. Cobre AC-6 do SPEC `det-6-multi-axis-backend.md`.

Cenário-âncora: projeto detectável (uniform Firebase Auth) — o handler
roda o composer (W5), monta a tabela de detecção, e emite o intent
``ask_three_paths`` (Phase A) com 3 opções:

  a) confirmar detection como-is
  b) ajustar células divergentes
  c) começar do zero (custom-from-scratch — deferred a W7.2)

## Estratégia de teste

Direct function call (não subprocess) — o handler é importado e invocado
contra ``tmp_path``. Dois caminhos exercitados:

1. **Happy path (Path A — confirm):** primeira chamada catches
   ``PausedForInputError``, lê intent-id do pending, escreve response
   com ``value="a"``, segunda chamada consome e retorna structured
   result com ``choice="confirm"`` + cards selecionados via composer.
2. **Defensive — empty active_cards:** composer retorna estrutura vazia;
   handler trata gracefully (não trava em divisão por zero / KeyError /
   ask_three_paths com options vazias).
3. **Defensive — Conflict cell preservado:** quando composer emite
   ``Conflict``, ambos candidates aparecem na tabela (handler não escolhe
   1 silentemente; expõe ao auditor humano).

## Reuso

- ``engine.detection.composer.compose_backend_axes`` (W5).
- ``engine.ui.question.ask_three_paths`` (Phase A).
- ``engine.ui.intent_state`` (Phase A) para read_pending / write_response.
- Cards reais (``cards/firebase-auth/card.yaml``) como fonte das signals
  — mesma estratégia de ``test_detection_composer_mixed_setup.py``.

## Filtro _SKIP_DIRS (engine/init.py:832-847)

Usamos ``tmp_path`` puro (sem materializar sob ``tests/fixtures/``)
porque ``engine.init._SKIP_DIRS`` filtra paths sob ``.claude/`` e o
worktree atual roda DENTRO de ``.claude/worktrees/det-6-w1/``. Mesma
justificativa documentada em ``test_detection_composer_mixed_setup.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from engine.cards.loader import CardManifest
from engine.detection.composer import Cell, Conflict
from engine.ui import intent_state
from engine.ui.question import PausedForInputError


REPO_ROOT = Path(__file__).resolve().parents[2]
assert (REPO_ROOT / "cards").is_dir(), (
    f"REPO_ROOT resolution broken: {REPO_ROOT} has no cards/ dir."
)
CARDS_DIR = REPO_ROOT / "cards"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _load_real_card(card_dir_name: str) -> CardManifest:
    """Carrega CardManifest do `cards/<name>/card.yaml` real.

    Reusa o loader canônico em vez de remontar dataclass à mão — garante
    que o test exercite exatamente os mesmos defaults / parsing que o
    init em produção. Pula CardManifest.raw porque ele guarda o yaml
    inteiro (que o caller só precisa pra detection block).
    """
    path = CARDS_DIR / card_dir_name / "card.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    identity = raw.get("identity") or {}
    return CardManifest(
        name=str(identity.get("name", "")),
        version=str(identity.get("version", "")),
        schema_version=int(raw.get("schema-version", 1)),
        description=str(identity.get("description", "")),
        category=str(identity.get("category", "")),
        maturity=str(identity.get("maturity", "")),
        provides=list(raw.get("provides") or []),
        requires=list(raw.get("requires") or []),
        conflicts_with=list(raw.get("conflicts-with") or []),
        contributes=dict(raw.get("contributes") or {}),
        detection=dict(raw.get("detection") or {}),
        documentation=dict(raw.get("documentation") or {}),
        raw=raw,
        source_path=CARDS_DIR / card_dir_name,
    )


def _scaffold_project(tmp_path: Path) -> Path:
    """Estrutura mínima pra `_project_root_for_io` resolver `tmp_path`.

    `engine.ui.question._project_root_for_io` walks up looking for
    `.claude/workflow-config.yaml`. Sem esse marker, ele cai no
    fallback `cwd` — que sob pytest é o working dir do runner, NÃO o
    tmp_path. Mesma estratégia que `test_intent_protocol_e2e.py`.

    Pin de host `intent-file` (fallout do commit e43be4c — 2026-06-17):
    desde que `ask_three_paths`/`confirm` passaram a delegar ao host
    adapter resolvido, a suite (rodando sob `CLAUDECODE=1` herdado)
    resolveria o ClaudeCodeAdapter, que emite o marker `<FORGE_INTENT />`
    no stdout em vez de gravar `forge-pending.json`. Estes testes assertam
    justamente o protocolo file-based (pending/response), então fixamos
    `host: intent-file` via `forge-config.yaml` — a precedência mais alta
    em `engine.host.detect.detect_host` (config vence env). Espelha o
    padrão de `tests/unit/test_ui_question_intent.py` + a correção que o
    cluster A aplicou em `tests/unit/test_engine_reconfigure_resume.py`.

    O cache per-`project_root` de `detect_host` é limpo aqui porque o
    config precisa existir ANTES da primeira resolução; idem o log cache
    de `intent_state` (defensivo — cada teste recebe `tmp_path` fresco).
    """
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True, exist_ok=True)
    (claude / "workflow-config.yaml").write_text("{}\n", encoding="utf-8")
    (claude / "forge" / "state").mkdir(parents=True, exist_ok=True)

    forge_dir = claude / "forge"
    (forge_dir / "forge-config.yaml").write_text(
        "host: intent-file\n", encoding="utf-8"
    )
    from engine.host import detect as _host_detect

    _host_detect._clear_cache()
    from engine.ui import intent_state as _intent_state

    _intent_state._reset_log_cache()
    return tmp_path


def _build_uniform_firebase_project(root: Path) -> None:
    """Materializa signals que disparam firebase-auth acima do threshold (0.50).

    Layout produzido:
        <root>/
            app/google-services.json     (confidence 0.20)
            ios/GoogleService-Info.plist (confidence 0.20)
            app/build.gradle.kts         (gradle-dep firebase-auth, 0.35)

    Score esperado: 0.20 + 0.20 + 0.35 = 0.75 ≥ 0.50.
    """
    (root / "app").mkdir(parents=True, exist_ok=True)
    (root / "app" / "google-services.json").write_text(
        '{"project_info": {"project_id": "test"}}', encoding="utf-8"
    )

    (root / "ios").mkdir(parents=True, exist_ok=True)
    (root / "ios" / "GoogleService-Info.plist").write_text(
        '<?xml version="1.0"?><plist></plist>', encoding="utf-8"
    )

    (root / "app" / "build.gradle.kts").write_text(
        """\
plugins { id("com.android.application") }

dependencies {
    implementation("com.google.firebase:firebase-auth:22.0.0")
}
""",
        encoding="utf-8",
    )


def _write_response(project_root: Path, intent_id: str, value: str) -> None:
    """Escreve `.claude/forge/state/forge-response.json` casando o intent-id."""
    response = {
        "schema-version": 1,
        "intent-id": intent_id,
        "value": value,
    }
    state_dir = project_root / ".claude" / "forge" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "forge-response.json").write_text(
        json.dumps(response), encoding="utf-8"
    )


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_brownfield_handler_emits_three_paths_intent_with_detection_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-6 happy path: handler emite intent contendo a tabela detectada.

    Primeira invocação (sem response no disco) deve gravar pending +
    raise PausedForInputError. Lemos o pending, validamos shape: 3 paths
    (a/b/c), gate-name, e que firebase-auth aparece no corpo da pergunta
    (uniformidade detectada → linha "auth — firebase-auth (todas)").
    """
    from engine.init import _handle_backend_multi_axis_brownfield

    _scaffold_project(tmp_path)
    _build_uniform_firebase_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    firebase_auth = _load_real_card("firebase-auth")
    active_cards = [firebase_auth]

    with pytest.raises(PausedForInputError):
        _handle_backend_multi_axis_brownfield(
            project_root=tmp_path,
            active_cards=active_cards,
        )

    pending = intent_state.read_pending(tmp_path)
    assert pending is not None, "handler must emit forge-pending.json on first call"
    assert pending["kind"] == "ask_three_paths", (
        f"expected kind=ask_three_paths, got {pending.get('kind')!r}"
    )

    options = pending["options"]
    assert set(options.keys()) == {"a", "b", "c"}, (
        f"three-paths must have a/b/c keys, got {sorted(options)}"
    )

    paths_detail = pending.get("paths-detail") or []
    assert len(paths_detail) == 3, (
        f"paths-detail must have exactly 3 entries, got {len(paths_detail)}"
    )

    # Labels carry confirm / adjust / scratch semantics.
    labels_lower = " ".join(p["label"].lower() for p in paths_detail)
    assert "confirm" in labels_lower or "confirmar" in labels_lower
    assert "ajust" in labels_lower or "adjust" in labels_lower
    assert "zero" in labels_lower or "scratch" in labels_lower

    # The table goes into the question body (or motive[0]) — searching
    # the whole pending payload is the most resilient assertion: we
    # don't pin to a particular field name, only to the fact that the
    # detected card surfaces somewhere visible.
    serialized = json.dumps(pending, ensure_ascii=False)
    assert "firebase-auth" in serialized, (
        "detected card 'firebase-auth' must appear in the rendered table "
        f"so the user can confirm/adjust; pending payload: {serialized[:400]}"
    )
    assert "auth" in serialized, "axis label 'auth' must appear in the table"


@pytest.mark.integration
def test_brownfield_handler_confirm_returns_structured_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-6 happy path: Path A (confirm) retorna result aplicando o composer.

    Two-phase call:
    1. First call → catches PausedForInputError, reads intent-id from pending.
    2. Pre-seeds response file with value="a" (confirm), calls again →
       handler consumes response, returns structured result with
       `choice="confirm"` and the composer-derived selected cards.
    """
    from engine.init import _handle_backend_multi_axis_brownfield

    _scaffold_project(tmp_path)
    _build_uniform_firebase_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    firebase_auth = _load_real_card("firebase-auth")
    active_cards = [firebase_auth]

    # Phase 1 — capture intent-id from pending.
    with pytest.raises(PausedForInputError):
        _handle_backend_multi_axis_brownfield(
            project_root=tmp_path,
            active_cards=active_cards,
        )

    pending = intent_state.read_pending(tmp_path)
    assert pending is not None
    intent_id = pending["intent-id"]

    # Phase 2 — seed response (Path A = confirm), call again.
    _write_response(tmp_path, intent_id, "a")

    result = _handle_backend_multi_axis_brownfield(
        project_root=tmp_path,
        active_cards=active_cards,
    )

    assert result is not None, "handler must return a structured result"
    assert result["choice"] == "confirm", (
        f"expected choice=confirm, got {result.get('choice')!r}"
    )

    # Composer-driven selection: firebase-auth appears in the result's
    # selected cards (the contract that W7.4 will downstream into the
    # workflow-config write step).
    selected = result.get("selected_card_names") or []
    assert "firebase-auth" in selected, (
        f"confirm path must accept composer detection; selected={selected!r}"
    )

    # Contrato pós-delegação (fallout do commit e43be4c — CR-002,
    # 2026-06-17): com `ask_three_paths`/`confirm` delegando ao host
    # adapter, o consume da response NÃO auto-limpa o pending em disco — a
    # limpeza terminal é responsabilidade do `cli.main` finally (e mesmo lá
    # SPEC §3 preserva pending/response forensicamente, limpando só o
    # intent-log). Isso unifica este handler com `ask`/`ask_text`/
    # `ask_multi` e espelha a correção que o cluster A aplicou em
    # `tests/unit/test_engine_reconfigure_resume.py`. O que prova o consume
    # bem-sucedido NÃO é a ausência do pending, mas o handler ter retornado
    # um result estruturado (`choice="confirm"` + `firebase-auth`) em vez de
    # re-pausar — já assertado acima. A response foi consumida via
    # intent-log; nova chamada não re-emitiria o mesmo intent-id.
    assert intent_state.read_pending(tmp_path) is not None, (
        "pending sobrevive ao consume após delegação (CR-002 — a limpeza "
        "terminal é trabalho do cli.main finally, não do consume per-prompt)"
    )


@pytest.mark.integration
def test_brownfield_handler_empty_active_cards_handled_gracefully(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defensive: 0 active_cards → composer empty result.

    Handler não pode crashear (KeyError / divisão por zero / options
    vazias em ask_three_paths). Mínimo aceitável: emite o intent com
    tabela vazia OU retorna result sinalizando "no detection" sem
    travar.
    """
    from engine.init import _handle_backend_multi_axis_brownfield

    _scaffold_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    # No active_cards at all — composer returns {}.
    # Handler should still emit a three-paths prompt (so the user can
    # pick "scratch" / "custom-from-scratch" path C) OR return a result
    # indicating empty detection. Either way: no exception other than
    # the canonical PausedForInputError.
    with pytest.raises(PausedForInputError):
        _handle_backend_multi_axis_brownfield(
            project_root=tmp_path,
            active_cards=[],
        )

    pending = intent_state.read_pending(tmp_path)
    assert pending is not None, "handler must still surface a prompt"
    assert pending["kind"] == "ask_three_paths"


@pytest.mark.integration
def test_brownfield_handler_conflict_cell_exposes_both_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defensive: Conflict cell → AMBOS candidatos aparecem na tabela.

    Quando composer marca (axis, platform) como Conflict (2+ cards
    matched signals), o handler NÃO escolhe 1 silentemente. Ambos
    candidates devem surfacear pro auditor humano decidir.

    Aqui usamos retrofit-client + ktor-client (mesma fixture pattern de
    test_detection_composer_mixed_setup.py) — ambos batem na cell
    (data, android).
    """
    from engine.init import _handle_backend_multi_axis_brownfield

    _scaffold_project(tmp_path)

    # Materializa setup misto (retrofit + ktor ativos).
    gradle_dir = tmp_path / "gradle"
    gradle_dir.mkdir(parents=True, exist_ok=True)
    (gradle_dir / "libs.versions.toml").write_text(
        """\
[versions]
retrofit = "2.9.0"
ktor     = "2.3.7"

[libraries]
retrofit          = { module = "com.squareup.retrofit2:retrofit", version.ref = "retrofit" }
ktor-client-core  = { module = "io.ktor:ktor-client-core",        version.ref = "ktor" }
""",
        encoding="utf-8",
    )
    (tmp_path / "build.gradle.kts").write_text(
        """\
plugins { kotlin("multiplatform") }

dependencies {
    implementation("com.squareup.retrofit2:retrofit:2.9.0")
    implementation("io.ktor:ktor-client-core:2.3.7")
}
""",
        encoding="utf-8",
    )
    src_dir = tmp_path / "src" / "main" / "kotlin"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "Api.kt").write_text(
        """\
package app.api

import retrofit2.Retrofit
import retrofit2.http.GET
import io.ktor.client.HttpClient

interface LegacyApi {
    @retrofit2.http.GET("/v1/items")
    fun fetch(): String
}

fun newClient() = HttpClient()
""",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)

    retrofit_card = _load_real_card("retrofit-client")
    ktor_card = _load_real_card("ktor-client")
    active_cards = [retrofit_card, ktor_card]

    with pytest.raises(PausedForInputError):
        _handle_backend_multi_axis_brownfield(
            project_root=tmp_path,
            active_cards=active_cards,
        )

    pending = intent_state.read_pending(tmp_path)
    assert pending is not None

    # Both candidates must appear so the user can disambiguate.
    serialized = json.dumps(pending, ensure_ascii=False)
    assert "retrofit-client" in serialized, (
        "Conflict cell must expose both candidates; "
        f"retrofit-client absent from pending: {serialized[:500]}"
    )
    assert "ktor-client" in serialized, (
        "Conflict cell must expose both candidates; "
        f"ktor-client absent from pending: {serialized[:500]}"
    )


# Cell + Conflict imports flagged unused by linters but kept here as
# documentation of the W5 surface the handler consumes — touching that
# surface in a future refactor will land in this file's diff.
_ = (Cell, Conflict)


# ════════════════════════════════════════════════════════════════════════════
# Pilot R1 (P-03, P-09, P-10, P-04, P-02)
# ════════════════════════════════════════════════════════════════════════════

from engine.cards.loader import load_all_cards  # noqa: E402
from engine.detection.composer import compose_backend_axes  # noqa: E402
from engine.init import _normalize_cards_for_composer  # noqa: E402
from engine.utils.paths import cards_canonical_dir  # noqa: E402


def _cell_card_ids(cell) -> set[str]:
    """Extrai os card_ids de um Cell ou de um Conflict.candidates."""
    if isinstance(cell, Cell):
        return {cell.card_id}
    if isinstance(cell, Conflict):
        return {c.card_id for c in cell.candidates}
    return set()


# ── WS-B-1: cards por-plataforma não conflitam (P-03) ───────────────────────


def _force_all_cards_match(monkeypatch: pytest.MonkeyPatch) -> None:
    """Força score acima do threshold pra TODO card, isolando a partição
    por-plataforma do acaso dos signals.

    Cada card canônico declara seu próprio ``detection.threshold`` (ex.:
    0.6) que vence o kwarg ``threshold`` do composer — então um tmp_path
    vazio jamais "casaria". Patcheamos ``_eval_detection_signals`` (usado
    pelo composer) pra devolver score=1.0 → todos os cards entram como
    candidatos nas suas plataformas declaradas; o que sobra a testar é
    PURAMENTE a partição (axis, platform).
    """
    import engine.detection.composer as _composer

    monkeypatch.setattr(
        _composer, "_eval_detection_signals", lambda root, det: (1.0, ["forced"])
    )


@pytest.mark.integration
def test_kmp_per_platform_ui_cards_do_not_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """compose-screens (Android) + swiftui-screens (iOS) são complementares
    por-plataforma, NÃO conflito. Após declararem identity.platforms, o
    composer não os coloca no mesmo (ui, platform) → zero Conflict no eixo
    ui (idem navigation com nav3 × swiftui-navigation)."""
    _force_all_cards_match(monkeypatch)
    cards = load_all_cards(cards_canonical_dir())
    by_name = {c.name: c for c in cards}
    subset = [
        by_name["compose-screens"],
        by_name["swiftui-screens"],
        by_name["nav3"],
        by_name["swiftui-navigation"],
    ]
    normalized = _normalize_cards_for_composer(subset)
    result = compose_backend_axes(tmp_path, normalized, threshold=0.0)
    for axis in ("ui", "navigation"):
        for platform, cell in result.get(axis, {}).items():
            assert not isinstance(cell, Conflict), (
                f"({axis}, {platform}) é Conflict — partição por-plataforma "
                f"quebrada (P-03)"
            )


@pytest.mark.integration
def test_per_platform_cards_partition_to_own_platform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """compose-screens só aparece em (ui, android); swiftui-screens só em
    (ui, ios). O mesmo set não pode repetir nas 3 linhas."""
    _force_all_cards_match(monkeypatch)
    cards = load_all_cards(cards_canonical_dir())
    by_name = {c.name: c for c in cards}
    normalized = _normalize_cards_for_composer(
        [by_name["compose-screens"], by_name["swiftui-screens"]]
    )
    result = compose_backend_axes(tmp_path, normalized, threshold=0.0)
    ui = result.get("ui", {})
    # compose-screens (android) NÃO deve estar em (ui, ios).
    assert "compose-screens" not in _cell_card_ids(ui.get("ios"))
    # swiftui-screens (ios) NÃO deve estar em (ui, android).
    assert "swiftui-screens" not in _cell_card_ids(ui.get("android"))
