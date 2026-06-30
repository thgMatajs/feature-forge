"""Unit tests — discovery cache do init (BUG-2, Onda 3).

O Step 2 (discovery) do `forge init` re-roda os 3 extractors caros
(`extract_design_system`/`extract_i18n`/`extract_conventions`) a CADA
invocação — incluindo o loop mecânico (host replaying response), onde cada
response é um PROCESSO NOVO (CLI). Em monorepo real isso custa ~220s/ciclo.

Fix (BUG-2): cachear o resultado de discovery num arquivo PERSISTENTE em disco
(`.claude/.init-discovery-cache.yaml`, lifecycle = checkpoint), e carregá-lo no
loop mecânico em vez de re-rodar. LRU intra-processo NÃO fecha o bug (cada
response = processo novo).

Acks do plan-auditor:
- L-001: nome concreto do cache file, persistente, lifecycle=checkpoint (some
  com `_clear_checkpoint`), e coberto pelo `.claude/.gitignore` que o init semeia.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import init
from engine.inventory.design_system import (
    DesignSystemInventory,
    DSComponent,
    DSTokens,
)
from engine.inventory.i18n import I18nInventory, I18nKey
from engine.inventory.conventions import ConventionsInventory


def _make_ds() -> DesignSystemInventory:
    return DesignSystemInventory(
        components=[
            DSComponent(name="Button", level="atom", status="stable"),
            DSComponent(name="Card", level="molecule", status="stable"),
        ],
        tokens=DSTokens(colors={"primary": "#112233"}, spacing={"sm": 4}),
        raw={
            "components": [
                {"name": "Button", "level": "atom", "status": "stable"},
                {"name": "Card", "level": "molecule", "status": "stable"},
            ],
            "tokens": {
                "colors": {"values": {"primary": "#112233"}},
                "spacing": {"values": {"sm": 4}},
            },
            "detection": {"naming": "Meo*"},
        },
    )


def _make_i18n() -> I18nInventory:
    return I18nInventory(
        keys=[I18nKey(key="a.b"), I18nKey(key="c.d"), I18nKey(key="e.f")],
        languages=["en", "pt-BR"],
        source_of_truth="locales",
        generated_paths={"android": ["app/res/values/strings.xml"]},
        raw={
            "source-of-truth": {"path": "locales", "locales": ["en", "pt-BR"]},
            "stats": {"total-keys": 3},
            "generation": {"outputs": {"android": ["app/res/values/strings.xml"]}},
        },
    )


def _make_conv() -> ConventionsInventory:
    return ConventionsInventory(
        di_pattern="hilt",
        folder_layout={"android": "{Screen}Screen.kt"},
        raw={
            "di-pattern": {"name": "hilt"},
            "folder-layout": {"android": "{Screen}Screen.kt"},
        },
    )


def test_discovery_cache_path_is_under_claude(tmp_path):
    """L-001: nome concreto, persistente, sob `.claude/`."""
    p = init._discovery_cache_path(tmp_path)
    assert p.name == ".init-discovery-cache.yaml"
    assert p.parent.name == ".claude"


def test_discovery_cache_roundtrips_inventories(tmp_path):
    """O cache carregado reproduz fielmente os 3 inventories (counts iguais)."""
    ds, i18n, conv = _make_ds(), _make_i18n(), _make_conv()
    init._save_discovery_cache(tmp_path, ds, i18n, conv)
    loaded = init._load_discovery_cache(tmp_path)
    assert loaded is not None
    lds, li18n, lconv = loaded
    # DS: contagem de components preservada (consumida no summary L2827).
    assert len(lds.components) == len(ds.components) == 2
    assert lds.raw == ds.raw
    # i18n: len(keys) preservado (consumido no summary L2828) + raw.
    assert len(li18n.keys) == len(i18n.keys) == 3
    assert li18n.raw == i18n.raw
    # conventions: raw preservado (consumido em _build_* L3838).
    assert lconv.raw == conv.raw


def test_discovery_cache_miss_returns_none(tmp_path):
    """Sem cache em disco → None (caller re-roda discovery normalmente)."""
    assert init._load_discovery_cache(tmp_path) is None


def test_discovery_cache_cleared_with_checkpoint(tmp_path):
    """Lifecycle = checkpoint: `_clear_checkpoint` remove o cache de discovery."""
    ds, i18n, conv = _make_ds(), _make_i18n(), _make_conv()
    init._save_discovery_cache(tmp_path, ds, i18n, conv)
    assert init._discovery_cache_path(tmp_path).exists()
    init._clear_checkpoint(tmp_path)
    assert not init._discovery_cache_path(tmp_path).exists()
    assert init._load_discovery_cache(tmp_path) is None


def test_discovery_cache_in_gitignore_seed(tmp_path):
    """L-001: o cache file entra no `.claude/.gitignore` semeado pelo init."""
    init._write_claude_gitignores(tmp_path)
    gi = (tmp_path / ".claude" / ".gitignore").read_text(encoding="utf-8")
    assert ".init-discovery-cache.yaml" in gi


# ── Contrato comportamental BUG-2 (extractors NÃO re-rodam no loop mecânico) ──


def _drive_init_to_discovery(monkeypatch, tmp_path, counters):
    """Roda init.run([]) com prompts neutralizados, espionando os 3 extractors.

    Os extractors viram contadores que delegam ao real (pra popular o cache
    fielmente na 1ª passada). O init aborta cedo (prompt → 'abort'); o que
    importa é se discovery (Step 2) re-rodou ou carregou do cache.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("engine.ui.question.ask", lambda *a, **kw: "abort", raising=False)
    monkeypatch.setattr("engine.ui.question.ask_text", lambda *a, **kw: "", raising=False)
    monkeypatch.setattr("engine.ui.question.confirm", lambda *a, **kw: False, raising=False)
    monkeypatch.setattr("engine.ui.question.ask_multi", lambda *a, **kw: [], raising=False)

    real_ds = init.extract_design_system
    real_i18n = init.extract_i18n
    real_conv = init.extract_conventions

    def spy_ds(root):
        counters["ds"] += 1
        return real_ds(root)

    def spy_i18n(root):
        counters["i18n"] += 1
        return real_i18n(root)

    def spy_conv(root):
        counters["conv"] += 1
        return real_conv(root)

    monkeypatch.setattr(init, "extract_design_system", spy_ds, raising=False)
    monkeypatch.setattr(init, "extract_i18n", spy_i18n, raising=False)
    monkeypatch.setattr(init, "extract_conventions", spy_conv, raising=False)

    try:
        init.run([])
    except (SystemExit, RuntimeError, ValueError, OSError, KeyError, FileNotFoundError):
        pass


def test_discovery_recomputed_on_fresh_run_and_cache_written(
    monkeypatch, tmp_path
):
    """1ª invocação (não-replaying): extractors RODAM e o cache é escrito no Step 2.

    (Num init que COMPLETA, `_clear_checkpoint` no fim apaga o cache junto — é o
    lifecycle correto. Por isso espionamos `_save_discovery_cache` em vez de
    checar o arquivo no fim.)
    """
    counters = {"ds": 0, "i18n": 0, "conv": 0}
    monkeypatch.setattr(
        "engine.ui.intent_state.host_is_replaying",
        lambda *a, **kw: False,
        raising=False,
    )
    saved = {"n": 0}
    real_save = init._save_discovery_cache

    def spy_save(root, ds, i18n, conv):
        saved["n"] += 1
        return real_save(root, ds, i18n, conv)

    monkeypatch.setattr(init, "_save_discovery_cache", spy_save, raising=False)

    _drive_init_to_discovery(monkeypatch, tmp_path, counters)
    # Discovery rodou ao menos uma vez (greenfield → extractors chamados).
    assert counters["ds"] >= 1
    # Cache foi semeado durante o Step 2 (pro próximo ciclo mecânico).
    assert saved["n"] >= 1


def test_discovery_not_recomputed_on_mechanical_reinvoke(monkeypatch, tmp_path):
    """Loop mecânico (host replaying) + cache presente → extractors NÃO rodam.

    Núcleo do BUG-2: cada response do host é um processo novo; sem cache em
    disco o discovery re-pagaria os ~220s. Com o cache, contador fica em 0.
    """
    # Pré-semeia o cache (simula o discovery do ciclo anterior).
    init._save_discovery_cache(tmp_path, _make_ds(), _make_i18n(), _make_conv())
    # Pré-grava um checkpoint (o ramo de discovery-cache só roda quando há
    # checkpoint anterior + replaying).
    init._save_checkpoint(
        init._InitCheckpoint(
            step="step-2-discovery",
            at="2026-06-10T00:00:00Z",
            project_root=str(tmp_path),
            preset="kmp-mobile",
            intent_id="some-downstream-intent",
        )
    )
    # Força o ramo de loop mecânico.
    monkeypatch.setattr(
        "engine.ui.intent_state.host_is_replaying",
        lambda *a, **kw: True,
        raising=False,
    )
    counters = {"ds": 0, "i18n": 0, "conv": 0}
    _drive_init_to_discovery(monkeypatch, tmp_path, counters)
    assert counters == {"ds": 0, "i18n": 0, "conv": 0}, (
        f"extractors re-rodaram no loop mecânico apesar do cache: {counters}"
    )


# ── B2 (Fase 1): content-fingerprint hardening ────────────────────────────────


def test_discovery_cache_invalidated_by_content_fingerprint(tmp_path):
    """B2 (Fase 1): se o fingerprint do source mudou, o cache é cache-miss
    mesmo com o arquivo presente — hardening fora do replay mecânico."""
    # Semeia um cache válido com fingerprint do estado atual.
    init._save_discovery_cache(
        tmp_path,
        None,
        None,
        ConventionsInventory(raw={"k": "v"}),
    )
    # Carrega com o MESMO fingerprint → cache-hit.
    assert init._load_discovery_cache(tmp_path) is not None

    # Muda o conteúdo da árvore (novo dir top-level) → fingerprint diverge.
    (tmp_path / "novo-modulo").mkdir()

    # Agora o load deve ser cache-miss (fingerprint não casa).
    assert init._load_discovery_cache(tmp_path) is None


def test_discovery_cache_hit_when_fingerprint_matches(tmp_path):
    """Sem mudança de conteúdo entre save e load → cache-hit (preserva o ganho
    de não re-varrer no replay mecânico)."""
    init._save_discovery_cache(
        tmp_path, None, None, ConventionsInventory(raw={"k": "v"})
    )
    loaded = init._load_discovery_cache(tmp_path)
    assert loaded is not None
    _, _, conv = loaded
    assert conv is not None and conv.raw == {"k": "v"}
