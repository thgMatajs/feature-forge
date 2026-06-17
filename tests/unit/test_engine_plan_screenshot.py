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

import struct
from pathlib import Path

import pytest

from engine import plan
from engine.ui import question


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


# ── _elicit_screenshot — source-inquiry só em product + Wave A ───────────────


def _boom_ask_text(*_a: object, **_k: object) -> str:
    raise AssertionError("ask_text NÃO deveria ser chamado neste contexto")


def test_elicit_skips_non_product_subtype(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feature = tmp_path / "feature"
    feature.mkdir()
    # Garante que NÃO pergunta — qualquer chamada a ask_text falha o teste.
    monkeypatch.setattr(question, "ask_text", _boom_ask_text)
    assert plan._elicit_screenshot(feature, "refactor", "A") is None
    assert plan._elicit_screenshot(feature, "bugfix", "A") is None


def test_elicit_skips_resume_wave(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feature = tmp_path / "feature"
    feature.mkdir()
    # Resume em wave != A → não re-pergunta (sem poluir nem duplicar).
    monkeypatch.setattr(question, "ask_text", _boom_ask_text)
    assert plan._elicit_screenshot(feature, "product", "B") is None
    assert plan._elicit_screenshot(feature, "product", "C") is None


def test_elicit_none_answer_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feature = tmp_path / "feature"
    feature.mkdir()
    monkeypatch.setattr(question, "ask_text", lambda *a, **k: "none")
    assert plan._elicit_screenshot(feature, "product", "A") is None


def test_elicit_valid_png_returns_ingest_dict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feature = tmp_path / "feature"
    (feature / "screenshots").mkdir(parents=True)
    _write_png(feature / "screenshots" / "tela.png", width=400, height=900)
    # ask_text devolve o bare filename → ingest resolve em screenshots/.
    monkeypatch.setattr(question, "ask_text", lambda *a, **k: "tela.png")
    result = plan._elicit_screenshot(feature, "product", "A")
    assert result is not None
    assert result["path"] == "screenshots/tela.png"
    assert len(result["fingerprint"]) == 64


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
    monkeypatch.setattr(plan, "_templates_dir", lambda: fake_templates)
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
