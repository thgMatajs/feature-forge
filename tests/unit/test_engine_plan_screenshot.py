"""Vision-wire tests para engine.plan (Wave 1 AI-first C3a).

O engine sanitiza + registra ponteiro; NUNCA interpreta pixel. Cobre três
camadas, todas vivas (sem helper dormente):

  1. `_ingest_screenshot` isolado — traversal rejeitado, formato inválido
     rejeitado sem crash, fingerprint estável, cópia pra screenshots/.
  2. `_elicit_screenshot` (source-inquiry) — só pergunta em product + Wave A;
     silencioso em refactor/bugfix e em resume (starting_wave != A);
     resposta "none" → sem screenshot.
  3. Token merge / render — o intake renderizado preenche os tokens
     `{{screenshots_*}}` (com e sem screenshot) sem vazar token cru, pelo
     MESMO threading da T1 (intake_tokens → _run_static_wave → Wave A).

Refs: docs/superpowers/specs/2026-06-17-ai-first-interaction-layer-design.md
      §4 C3a + §5 (fluxo com/sem screenshot)
"""

from __future__ import annotations

import json
import shutil
import struct
from pathlib import Path

import pytest

from engine import plan
from engine.ui import question
from engine.vision import screenshot as _ss


def _write_png(path: Path, width: int = 400, height: int = 800) -> None:
    """Escreve um PNG mínimo válido (header + IHDR) pros parsers magic-byte."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    chunk = struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr + struct.pack(">I", 0)
    path.write_bytes(sig + chunk + b"\x00" * 32)


# Intake fake com os 3 nomes de token de screenshot (product usa o nome puro,
# refactor/bugfix usam o sufixo `_or_none` — ver templates/feature-intake*.md).
_INTAKE_SCREENSHOT_BODY = (
    "# Intake {{feature_slug}}\n"
    "- screenshots: {{screenshots_count}} file(s) — "
    "{{screenshots_relative_paths_csv}}\n"
    "- screenshots (alt): {{screenshots_count}} file(s) — "
    "{{screenshots_relative_paths_csv_or_none}}\n"
)


# ── _ingest_screenshot — sanitiza + registra ponteiro, nunca crasha ──────────


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


# ── _ingest_screenshot — crash-safe (W-001): IO failure → None, nunca crasha ─


def test_ingest_copy_failure_returns_none_not_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Falha de IO no copy (disco cheio/perm) honra "nunca crasha" → None."""
    feature = tmp_path / "feature"
    (feature / "screenshots").mkdir(parents=True)
    src = feature / "screenshots" / "screen.png"
    _write_png(src, width=400, height=900)
    # Força o caminho do copy: referencia o mesmo arquivo por path absoluto
    # externo? Não — aqui o source já está em screenshots/, então o copy é
    # no-op. Usamos um source bare em feature/ pra ativar o copy real.
    other = feature / "other.png"
    _write_png(other, width=400, height=900)

    def _boom(*_a: object, **_k: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(shutil, "copy2", _boom)
    # copy2 explode DEPOIS do lock/normalize/validate — o contrato exige None.
    assert plan._ingest_screenshot("other.png", feature) is None


def test_ingest_fingerprint_failure_returns_none_not_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Falha no fingerprint (TOCTOU/IO) também degrada gracioso → None."""
    feature = tmp_path / "feature"
    (feature / "screenshots").mkdir(parents=True)
    src = feature / "screenshots" / "screen.png"
    _write_png(src, width=400, height=900)

    def _boom(*_a: object, **_k: object) -> str:
        raise OSError("read error")

    monkeypatch.setattr(_ss, "compute_screenshot_fingerprint", _boom)
    assert plan._ingest_screenshot("screen.png", feature) is None


# ── _ingest_screenshot — external copy-in (W-003): mockup do host ────────────


def test_ingest_accepts_external_absolute_image(tmp_path: Path) -> None:
    """Path absoluto externo (mockup do host) válido → ingerido + copiado."""
    feature = tmp_path / "feature"
    feature.mkdir()
    external = tmp_path / "Desktop" / "mockup.png"
    external.parent.mkdir(parents=True)
    _write_png(external, width=400, height=900)

    result = plan._ingest_screenshot(str(external), feature)
    assert result is not None
    assert result["path"] == "screenshots/mockup.png"
    assert (feature / "screenshots" / "mockup.png").is_file()
    assert len(result["fingerprint"]) == 64


def test_ingest_rejects_external_absolute_non_image(tmp_path: Path) -> None:
    """Path absoluto externo não-imagem → None (validate é o gate real)."""
    feature = tmp_path / "feature"
    feature.mkdir()
    external = tmp_path / "Desktop" / "notes.txt"
    external.parent.mkdir(parents=True)
    external.write_text("not an image", encoding="utf-8")

    assert plan._ingest_screenshot(str(external), feature) is None


# ── _record_screenshot_manifest — persiste fingerprint + platform_hint (WR-02)─


def test_manifest_persists_fingerprint_and_platform(tmp_path: Path) -> None:
    """O manifest grava fingerprint + platform_hint (antes descartados).

    WR-02: `_ingest_screenshot` computa fingerprint (dedup Wave B) +
    platform_hint (override do conductor), mas o `run()` só lia path+count.
    O manifest fecha o handoff de provenance — sem ele os campos eram trabalho
    morto.
    """
    feature = tmp_path / "feature"
    (feature / "screenshots").mkdir(parents=True)
    _write_png(feature / "screenshots" / "tela.png", width=400, height=900)
    result = plan._ingest_screenshot("tela.png", feature)
    assert result is not None

    plan._record_screenshot_manifest(feature, result)

    manifest_path = feature / "screenshots" / "manifest.json"
    assert manifest_path.is_file()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = data["tela.png"]
    assert entry["fingerprint"] == result["fingerprint"]
    assert entry["platform_hint"] == result["platform_hint"]
    assert entry["platform_confidence"] == result["platform_confidence"]
    assert "ingested_at" in entry  # provenance timestamp


def test_manifest_idempotent_same_file(tmp_path: Path) -> None:
    """Dois ingests do MESMO file não duplicam entry (merge por filename)."""
    feature = tmp_path / "feature"
    (feature / "screenshots").mkdir(parents=True)
    _write_png(feature / "screenshots" / "a.png")
    r1 = plan._ingest_screenshot("a.png", feature)
    assert r1 is not None

    plan._record_screenshot_manifest(feature, r1)
    plan._record_screenshot_manifest(feature, r1)

    data = json.loads(
        (feature / "screenshots" / "manifest.json").read_text(encoding="utf-8")
    )
    # Exatamente 1 chave (o filename) — merge por filename, sem duplicar.
    assert list(data.keys()) == ["a.png"]


def test_manifest_merges_multiple_files(tmp_path: Path) -> None:
    """Ingests de files distintos acumulam no mesmo manifest (merge, não overwrite)."""
    feature = tmp_path / "feature"
    (feature / "screenshots").mkdir(parents=True)
    _write_png(feature / "screenshots" / "a.png")
    _write_png(feature / "screenshots" / "b.png")
    ra = plan._ingest_screenshot("a.png", feature)
    rb = plan._ingest_screenshot("b.png", feature)
    assert ra is not None and rb is not None

    plan._record_screenshot_manifest(feature, ra)
    plan._record_screenshot_manifest(feature, rb)

    data = json.loads(
        (feature / "screenshots" / "manifest.json").read_text(encoding="utf-8")
    )
    assert set(data.keys()) == {"a.png", "b.png"}
    assert data["a.png"]["fingerprint"] == ra["fingerprint"]
    assert data["b.png"]["fingerprint"] == rb["fingerprint"]


def test_manifest_survives_corrupt_existing_file(tmp_path: Path) -> None:
    """Manifest pré-existente corrompido → re-seed gracioso (não crasha)."""
    feature = tmp_path / "feature"
    (feature / "screenshots").mkdir(parents=True)
    _write_png(feature / "screenshots" / "a.png")
    (feature / "screenshots" / "manifest.json").write_text(
        "{ corrupt ,,", encoding="utf-8"
    )
    r = plan._ingest_screenshot("a.png", feature)
    assert r is not None

    # Não deve propagar JSONDecodeError — re-seed limpo.
    plan._record_screenshot_manifest(feature, r)
    data = json.loads(
        (feature / "screenshots" / "manifest.json").read_text(encoding="utf-8")
    )
    assert data["a.png"]["fingerprint"] == r["fingerprint"]


# ── _elicit_screenshot — source-inquiry só em product + Wave A ───────────────


def _boom_ask_text(*_a: object, **_k: object) -> str:
    raise AssertionError("ask_text NÃO deveria ser chamado neste contexto")


def test_elicit_skips_non_product_subtype(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feature = tmp_path / "feature"
    feature.mkdir()
    # Garante que NÃO pergunta — qualquer chamada a ask_text falha o teste.
    # C-08: retorno agora é lista — vazia quando não pergunta.
    monkeypatch.setattr(question, "ask_text", _boom_ask_text)
    assert plan._elicit_screenshot(feature, "refactor", "A") == []
    assert plan._elicit_screenshot(feature, "bugfix", "A") == []


def test_elicit_skips_resume_wave(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feature = tmp_path / "feature"
    feature.mkdir()
    # Resume em wave != A → não re-pergunta (sem poluir nem duplicar).
    monkeypatch.setattr(question, "ask_text", _boom_ask_text)
    assert plan._elicit_screenshot(feature, "product", "B") == []
    assert plan._elicit_screenshot(feature, "product", "C") == []


def test_elicit_none_answer_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feature = tmp_path / "feature"
    feature.mkdir()
    monkeypatch.setattr(question, "ask_text", lambda *a, **k: "none")
    assert plan._elicit_screenshot(feature, "product", "A") == []


def test_elicit_valid_png_returns_ingest_dict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feature = tmp_path / "feature"
    (feature / "screenshots").mkdir(parents=True)
    _write_png(feature / "screenshots" / "tela.png", width=400, height=900)
    # ask_text devolve o bare filename → ingest resolve em screenshots/.
    monkeypatch.setattr(question, "ask_text", lambda *a, **k: "tela.png")
    results = plan._elicit_screenshot(feature, "product", "A")
    assert len(results) == 1
    assert results[0]["path"] == "screenshots/tela.png"
    assert len(results[0]["fingerprint"]) == 64


def test_elicit_multiple_paths_ingests_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C-08 (PR18-R8): múltiplos paths separados por vírgula/espaço → todos
    ingeridos; o run() preenche count + CSV a partir da lista."""
    feature = tmp_path / "feature"
    (feature / "screenshots").mkdir(parents=True)
    _write_png(feature / "screenshots" / "home.png", width=400, height=900)
    _write_png(feature / "screenshots" / "detail.png", width=400, height=900)
    monkeypatch.setattr(question, "ask_text", lambda *a, **k: "home.png, detail.png")
    results = plan._elicit_screenshot(feature, "product", "A")
    paths = sorted(r["path"] for r in results)
    assert paths == ["screenshots/detail.png", "screenshots/home.png"]


def test_elicit_partial_invalid_degrades_gracefully(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C-08: um path inválido NÃO derruba os válidos — degradação parcial."""
    feature = tmp_path / "feature"
    (feature / "screenshots").mkdir(parents=True)
    _write_png(feature / "screenshots" / "ok.png", width=400, height=900)
    monkeypatch.setattr(
        question, "ask_text", lambda *a, **k: "ok.png nao-existe-zzz.png"
    )
    results = plan._elicit_screenshot(feature, "product", "A")
    assert len(results) == 1
    assert results[0]["path"] == "screenshots/ok.png"


# ── token merge / render — pelo threading T1 (intake_tokens → Wave A) ────────


def _render_intake_with(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    screenshot_result: dict | None,
) -> str:
    """Renderiza o intake REAL via _run_static_wave('A', ...) com o mesmo
    merge de tokens que run() faz, e devolve o corpo renderizado.
    """
    fake_templates = tmp_path / "templates"
    fake_templates.mkdir()
    (fake_templates / "intake.template.md").write_text(
        _INTAKE_SCREENSHOT_BODY, encoding="utf-8"
    )
    monkeypatch.setattr(plan, "_templates_dir", lambda _root: fake_templates)
    monkeypatch.setattr(plan, "_continue_or_pause", lambda slug, label: "continuar")

    feature_path = tmp_path / "feature"
    feature_path.mkdir()

    # Replica o merge de run() (~L1648): _source_tokens_for + screenshot tokens.
    intake_tokens = plan._source_tokens_for(None)
    _count = "1" if screenshot_result else "0"
    _paths = screenshot_result["path"] if screenshot_result else "none"
    intake_tokens.update(
        {
            "{{screenshots_count}}": _count,
            "{{screenshots_relative_paths_csv}}": _paths,
            "{{screenshots_relative_paths_csv_or_none}}": _paths,
        }
    )

    plan._run_static_wave(
        "A",
        (("intake.template.md", "feature-intake.md"),),
        "tela-bonsai",
        tmp_path,
        feature_path,
        extra_tokens=intake_tokens,
    )
    return (feature_path / "feature-intake.md").read_text(encoding="utf-8")


def test_intake_render_with_screenshot_fills_tokens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rendered = _render_intake_with(
        tmp_path,
        monkeypatch,
        {"path": "screenshots/tela.png", "fingerprint": "x" * 64},
    )
    assert "screenshots: 1 file(s) — screenshots/tela.png" in rendered
    for token in (
        "{{screenshots_count}}",
        "{{screenshots_relative_paths_csv}}",
        "{{screenshots_relative_paths_csv_or_none}}",
    ):
        assert token not in rendered, f"{token} vazou cru no intake"


def test_intake_render_without_screenshot_fills_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rendered = _render_intake_with(tmp_path, monkeypatch, None)
    assert "screenshots: 0 file(s) — none" in rendered
    for token in (
        "{{screenshots_count}}",
        "{{screenshots_relative_paths_csv}}",
        "{{screenshots_relative_paths_csv_or_none}}",
    ):
        assert token not in rendered, f"{token} vazou cru no intake"


# ── token-reinjection (W-002): single-pass render não re-escaneia valores ────


def test_render_source_ref_literal_token_not_mangled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """source-ref contendo `{{screenshots_count}}` sobrevive literal.

    O argv livre do host pode conter o literal `{{screenshots_count}}`.
    Com substituição single-pass, o valor inserido em source-ref NÃO é
    re-escaneado pelo pass de screenshot → o literal é preservado, e os
    tokens reais de screenshot da própria LINHA de screenshots são
    preenchidos normalmente.
    """
    fake_templates = tmp_path / "templates"
    fake_templates.mkdir()
    (fake_templates / "intake.template.md").write_text(
        "# Intake {{feature_slug}}\n"
        "- source-ref: {{source_ref_or_none}}\n"
        "- screenshots: {{screenshots_count}} file(s) — "
        "{{screenshots_relative_paths_csv}}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(plan, "_templates_dir", lambda _root: fake_templates)
    monkeypatch.setattr(plan, "_continue_or_pause", lambda slug, label: "continuar")
    # Onda 2: este teste cobre o RENDER (single-pass), não o content-gate. O
    # argv cru carrega um literal `{{screenshots_count}}` no source-ref que
    # sobrevive de propósito — o gate (que roda APÓS o render) o veria como
    # stub. Neutralizamos o gate aqui pra isolar o que está sob teste.
    monkeypatch.setattr(plan, "_run_content_gate", lambda *a, **k: None)

    feature_path = tmp_path / "feature"
    feature_path.mkdir()

    # argv CRU contendo o literal de um token de screenshot.
    argv = "add {{screenshots_count}} widget"
    intake_tokens = plan._source_tokens_for(argv)
    intake_tokens.update(
        {
            "{{screenshots_count}}": "1",
            "{{screenshots_relative_paths_csv}}": "screenshots/tela.png",
            "{{screenshots_relative_paths_csv_or_none}}": "screenshots/tela.png",
        }
    )
    plan._run_static_wave(
        "A",
        (("intake.template.md", "feature-intake.md"),),
        "tela-bonsai",
        tmp_path,
        feature_path,
        extra_tokens=intake_tokens,
    )
    rendered = (feature_path / "feature-intake.md").read_text(encoding="utf-8")

    # O literal no source-ref NÃO virou "1": single-pass não re-escaneia.
    assert "source-ref: add {{screenshots_count}} widget" in rendered
    # A linha REAL de screenshots foi preenchida normalmente.
    assert "screenshots: 1 file(s) — screenshots/tela.png" in rendered
