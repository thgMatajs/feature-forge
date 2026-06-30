"""T8 — P2 polish bundle (BUG-UNDO-1, BUG-RAW-1, BUG-EVOLVE-1/2, BUG-RECONF-1).

Cada item é cirúrgico (1 condição / 1 except / 1 guard) — testes de regressão
vermelho-antes por item.
"""

from __future__ import annotations

from pathlib import Path

import pytest


# ── BUG-UNDO-1: no-op legítimo (sem .bak) deve sair 0, não 1 ──────────────────


def test_undo_reconfigure_noop_without_bak(tmp_forge_project: Path, monkeypatch) -> None:
    """``forge undo`` → reconfigure sem .bak é no-op legítimo → exit 0."""
    from engine import undo

    # Marca o projeto (find_project_root procura forge-config.yaml).
    (tmp_forge_project / ".claude" / "forge" / "forge-config.yaml").write_text(
        "identity:\n  project-name: demo\n", encoding="utf-8"
    )
    # Sem .bak no projeto. Escolhe "2" (reconfigure) no menu.
    monkeypatch.chdir(tmp_forge_project)
    monkeypatch.setattr(undo.question, "ask", lambda *a, **k: "2", raising=False)
    monkeypatch.setattr(undo.question, "confirm", lambda *a, **k: False, raising=False)
    monkeypatch.setattr(undo.question, "ask_text", lambda *a, **k: "", raising=False)

    rc = undo.run([])
    assert rc == 0, f"no-op sem .bak deveria sair 0 (era exit 1 bug), obtido {rc}"


# ── BUG-EVOLVE-1/2: --help reconhecido + BrokenPipe tratado ───────────────────


def test_evolve_help_recognized(capsys) -> None:
    """``forge evolve --help`` imprime uso e sai 0 (não cai no fluxo normal)."""
    from engine import evolve

    rc = evolve.run(["--help"])
    out = capsys.readouterr().out.lower()
    assert rc == 0, f"--help deveria sair 0, obtido {rc}"
    assert "evolve" in out and ("uso" in out or "usage" in out)


def test_implement_help_recognized(capsys) -> None:
    """``forge implement --help`` imprime uso e sai 0 (não trata como slug)."""
    from engine import implement

    rc = implement.run(["--help"])
    out = capsys.readouterr().out.lower()
    assert rc == 0, f"--help deveria sair 0, obtido {rc}"
    assert "implement" in out and ("uso" in out or "usage" in out)


def test_evolve_handles_broken_pipe_in_source() -> None:
    """O run() de evolve trata BrokenPipeError (stdout fecha cedo)."""
    import inspect

    from engine import evolve

    src = inspect.getsource(evolve)
    assert "BrokenPipeError" in src, (
        "evolve não trata BrokenPipeError (SIGPIPE/EOF derruba o loop de render)"
    )


# ── BUG-RAW-1: rebuild-templates avisa que opera no FORGE_HOME ─────────────────


def test_raw_rebuild_templates_warns_forge_home_scope(
    tmp_project_root: Path, monkeypatch, capsys
) -> None:
    """O raw rebuild-templates AVISA (stdout) que opera no FORGE_HOME, não no projeto."""
    from engine import raw

    monkeypatch.chdir(tmp_project_root)
    # Sem cards snapshot → sai cedo, mas o aviso de escopo deve vir ANTES.
    raw._rebuild_templates([])
    out = capsys.readouterr().out.upper()
    assert "FORGE_HOME" in out, (
        "rebuild-templates não avisa no stdout que opera no FORGE_HOME (não no projeto)"
    )


# ── BUG-RECONF-1: dashboard só no 1º passo do loop multi-passo ────────────────


def test_reconfigure_dashboard_only_on_first_pass(
    tmp_forge_project: Path, monkeypatch, capsys
) -> None:
    """O dashboard 'Configuração atual' não é re-impresso quando há checkpoint."""
    from engine import reconfigure
    from engine.host import detect as host_detect

    forge_dir = tmp_forge_project / ".claude" / "forge"
    forge_dir.joinpath("forge-config.yaml").write_text(
        "host: intent-file\nidentity:\n  project-name: demo\n  project-slug: demo\n",
        encoding="utf-8",
    )
    host_detect._clear_cache()
    monkeypatch.chdir(tmp_forge_project)
    # Sai cedo do loop (nenhuma categoria) — isola o comportamento do dashboard.
    monkeypatch.setattr(reconfigure, "_choose_categories", lambda *a, **k: [])

    # 1º passo: sem checkpoint → dashboard aparece.
    reconfigure.run([])
    first_out = capsys.readouterr().out
    assert "Configuração atual" in first_out, "dashboard deveria aparecer no 1º passo"

    # Simula um passo subsequente do mesmo loop: checkpoint em curso.
    reconfigure._save_reconfigure_checkpoint(
        reconfigure._ReconfigureCheckpoint(
            step="step-category:persona",
            at="2026-06-29T00:00:00Z",
            project_root=str(tmp_forge_project),
            intent_id=None,
            menu_path=["persona"],
        )
    )
    reconfigure.run([])
    second_out = capsys.readouterr().out
    assert "Configuração atual" not in second_out, (
        "dashboard NÃO deveria ser re-impresso com checkpoint em curso (BUG-RECONF-1)"
    )
