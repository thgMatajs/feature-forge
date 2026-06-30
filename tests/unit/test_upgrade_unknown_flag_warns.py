"""B1 (Fase 1): forge upgrade avisa em flag desconhecida (não-fatal)."""

from __future__ import annotations

import engine.upgrade as up


def test_unknown_flag_emits_warning_to_stderr(monkeypatch, capsys):
    """Flag não-reconhecida → aviso em stderr; o upgrade ainda roda."""
    called = {}

    def _fake_run_upgrade(*, force: bool, dry_run: bool) -> int:
        called["force"] = force
        called["dry_run"] = dry_run
        return 0

    monkeypatch.setattr(up, "run_upgrade", _fake_run_upgrade)

    rc = up.run(["--dryrun"])  # typo proposital de --dry-run

    assert rc == 0
    err = capsys.readouterr().err
    assert "--dryrun" in err
    assert "não reconhecida" in err or "desconhecida" in err
    # Não-fatal: o upgrade rodou com as flags reconhecidas (nenhuma → defaults).
    assert called == {"force": False, "dry_run": False}


def test_known_flags_emit_no_warning(monkeypatch, capsys):
    """Flags válidas não disparam aviso."""

    def _fake_run_upgrade(*, force: bool, dry_run: bool) -> int:
        return 0

    monkeypatch.setattr(up, "run_upgrade", _fake_run_upgrade)

    up.run(["--dry-run", "--force"])

    err = capsys.readouterr().err
    assert "desconhecida" not in err
    assert "não reconhecida" not in err


def test_help_short_circuits_without_unknown_warning(capsys):
    """--help sai 0 e imprime uso; não dispara o aviso de flag desconhecida."""
    rc = up.run(["--help"])
    assert rc == 0
    out = capsys.readouterr()
    assert "forge upgrade" in out.out
    assert "desconhecida" not in out.err
