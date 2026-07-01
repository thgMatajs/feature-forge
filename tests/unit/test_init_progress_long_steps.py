"""D1 (Fase 1): steps longos do init (backend, orphan) dão feedback via spinner
GATEADO por TTY — fora de TTY é no-op puro (zero bytes em stdout).

Gate obrigatório (H-001): o loop IA-first usa stdout estruturado (capturado
como JSON pelo host). O spinner NÃO pode escrever em stdout fora de TTY —
corromperia o transcript do host. O gate _is_tty é OBRIGATÓRIO nos dois
steps (backend + orphan); fora de TTY a varredura roda direto, sem spinner.
"""

from __future__ import annotations

import engine.init as init_mod


class _FakeSpinnerCtx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# ── D1.1 — Step 5 (backend/composer) ─────────────────────────────────────────


def test_backend_step_uses_spinner_in_tty(tmp_path, monkeypatch):
    """Step 5 (backend/composer): sob TTY, a varredura é envolvida num spinner."""
    labels = []

    def _fake_spinner(label, **kw):
        labels.append(label)
        return _FakeSpinnerCtx()

    monkeypatch.setattr(init_mod.ui_progress, "spinner", _fake_spinner)
    monkeypatch.setattr(init_mod.renderer, "_is_tty", lambda *a, **k: True)

    # Stub compose_backend_axes para retornar imediatamente sem varredura real.
    monkeypatch.setattr(init_mod, "compose_backend_axes", lambda *a, **k: {})

    # Invoca _scan_backend_with_spinner (o helper que embute o gate+spinner).
    normalized = init_mod._normalize_cards_for_composer([])
    init_mod._scan_backend_with_spinner(tmp_path, normalized)

    assert any("backend" in s.lower() for s in labels), (
        f"esperava spinner com 'backend' no label; labels={labels}"
    )


def test_backend_step_is_noop_in_non_tty(tmp_path, monkeypatch, capsys):
    """H-001: fora de TTY, o spinner NÃO é instanciado e NADA vai pra stdout.

    Prova o gate obrigatório: zero bytes em stdout vindos do spinner —
    o loop IA-first não pode ter o transcript corrompido por texto cinético.

    N-001 — sanity-assert antes do assert de spinner_calls: a varredura
    DEVE ter sido ativada (compose_backend_axes chamado >= 1x) para
    garantir que o teste não é falso-verde por harness inerte.
    """
    spinner_calls = []
    scan_calls = {"n": 0}
    real_scan = init_mod.compose_backend_axes

    def _spy_spinner(label, **kw):
        spinner_calls.append(label)
        return _FakeSpinnerCtx()

    def _counting_scan(*a, **k):
        scan_calls["n"] += 1
        return {}

    monkeypatch.setattr(init_mod.ui_progress, "spinner", _spy_spinner)
    monkeypatch.setattr(init_mod.renderer, "_is_tty", lambda *a, **k: False)
    monkeypatch.setattr(init_mod, "compose_backend_axes", _counting_scan)

    normalized = init_mod._normalize_cards_for_composer([])
    init_mod._scan_backend_with_spinner(tmp_path, normalized)

    # N-001: sanity-assert — a varredura deve ter sido ativada.
    assert scan_calls["n"] >= 1, (
        "N-001: compose_backend_axes NÃO foi chamado — o harness não ativou "
        "a varredura; o assert de spinner_calls abaixo seria falso-verde por "
        "harness inerte (polaridade invertida)."
    )

    # Gate obrigatório: spinner NÃO foi instanciado fora de TTY.
    assert spinner_calls == [], (
        "fora de TTY o spinner NÃO pode ser instanciado (gate _is_tty "
        f"obrigatório); foi chamado com: {spinner_calls}"
    )
    # E, de forma mais forte: zero bytes de progresso em stdout.
    out = capsys.readouterr().out
    assert "…" not in out, (
        "spinner não pode escrever label+'…' em stdout fora de TTY "
        f"(transcript IA-first corrompido); stdout={out!r}"
    )


# ── D1.2 — Step 7.5 (orphan scan) ────────────────────────────────────────────


def test_orphan_step_uses_spinner_in_tty(tmp_path, monkeypatch):
    """Step 7.5 (orphan scan): sob TTY, a varredura é envolvida num spinner."""
    labels = []

    def _fake_spinner(label, **kw):
        labels.append(label)
        return _FakeSpinnerCtx()

    monkeypatch.setattr(init_mod.ui_progress, "spinner", _fake_spinner)
    monkeypatch.setattr(init_mod.renderer, "_is_tty", lambda *a, **k: True)
    monkeypatch.setattr(init_mod, "_check_orphan_signals", lambda *a, **k: [])

    init_mod._scan_orphan_with_spinner(tmp_path, [], None)

    assert any(("orphan" in s.lower() or "órfã" in s.lower()) for s in labels), (
        f"esperava spinner com 'orphan'/'órfã' no label; labels={labels}"
    )


def test_orphan_step_is_noop_in_non_tty(tmp_path, monkeypatch, capsys):
    """H-001: fora de TTY, o orphan spinner NÃO escreve em stdout."""
    spinner_calls = []
    scan_calls = {"n": 0}

    def _spy_spinner(label, **kw):
        spinner_calls.append(label)
        return _FakeSpinnerCtx()

    def _counting_orphan(*a, **k):
        scan_calls["n"] += 1
        return []

    monkeypatch.setattr(init_mod.ui_progress, "spinner", _spy_spinner)
    monkeypatch.setattr(init_mod.renderer, "_is_tty", lambda *a, **k: False)
    monkeypatch.setattr(init_mod, "_check_orphan_signals", _counting_orphan)

    init_mod._scan_orphan_with_spinner(tmp_path, [], None)

    # N-001: sanity-assert — a varredura deve ter sido ativada.
    assert scan_calls["n"] >= 1, (
        "N-001: _check_orphan_signals NÃO foi chamado — harness inerte."
    )

    assert spinner_calls == [], (
        f"fora de TTY o spinner NÃO pode ser instanciado; chamado com: {spinner_calls}"
    )
    out = capsys.readouterr().out
    assert "…" not in out, (
        f"spinner não pode escrever em stdout fora de TTY; stdout={out!r}"
    )
