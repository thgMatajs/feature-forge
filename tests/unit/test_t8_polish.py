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


# ── MED-03: no-op→exit 0 consistente também no ramo task-commit ───────────────


def test_undo_task_commit_no_commits_is_noop(tmp_forge_project: Path) -> None:
    """MED-03: "sem commits registrados" é no-op legítimo → _NOOP (exit 0),
    não False (exit 1). Nada a reverter ≠ erro."""
    from engine import undo

    result = undo._undo_task_commit(tmp_forge_project, "feature-sem-commits")
    assert result is undo._NOOP, (
        f"sem commits é no-op legítimo, deveria ser _NOOP, obtido {result!r}"
    )
    assert undo._rc_for(result) == 0


def test_undo_task_commit_declined_confirmation_is_noop(
    tmp_forge_project: Path, monkeypatch
) -> None:
    """MED-03: declinar a confirmação é no-op legítimo (nada mutado) → _NOOP."""
    from engine import undo

    # Há um commit registrado, mas o usuário declina a 1ª confirmação.
    monkeypatch.setattr(
        undo,
        "_last_task_commit",
        lambda *a, **k: {"commit_sha": "a" * 40, "task-id": "TASK-0001"},
        raising=False,
    )
    monkeypatch.setattr(undo.question, "confirm", lambda *a, **k: False, raising=False)

    result = undo._undo_task_commit(tmp_forge_project, "feat-x")
    assert result is undo._NOOP, (
        f"declínio de confirmação é no-op (nada mutado), deveria ser _NOOP, "
        f"obtido {result!r}"
    )
    assert undo._rc_for(result) == 0


def test_undo_task_commit_missing_sha_is_real_error(
    tmp_forge_project: Path, monkeypatch
) -> None:
    """MED-03 (contra-prova): entry sem SHA é ERRO real → False (exit 1),
    nunca forçado a 0."""
    from engine import undo

    monkeypatch.setattr(
        undo,
        "_last_task_commit",
        lambda *a, **k: {"task-id": "TASK-0001"},  # sem commit_sha/sha
        raising=False,
    )
    result = undo._undo_task_commit(tmp_forge_project, "feat-x")
    assert result is not undo._NOOP, "erro real (sem SHA) não pode virar no-op"
    assert undo._rc_for(result) == 1


def test_undo_choice_3_uses_rc_for_for_noop(
    tmp_forge_project: Path, monkeypatch
) -> None:
    """MED-03: o ramo choice=="3" do menu deve honrar _NOOP via _rc_for —
    um no-op de task-commit (sem commits) sai 0, não 1."""
    from engine import undo

    (tmp_forge_project / ".claude" / "forge" / "forge-config.yaml").write_text(
        "identity:\n  project-name: demo\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_forge_project)
    monkeypatch.setattr(undo.question, "ask", lambda *a, **k: "3", raising=False)
    monkeypatch.setattr(undo, "_pick_feature", lambda *a, **k: "feat-x", raising=False)
    # Sem commits registrados → _undo_task_commit devolve _NOOP.
    monkeypatch.setattr(undo, "_last_task_commit", lambda *a, **k: None, raising=False)

    rc = undo.run([])
    assert rc == 0, f"no-op de task-commit no ramo 3 deveria sair 0, obtido {rc}"


def test_undo_evolve_declined_confirmation_is_noop(
    tmp_forge_project: Path, monkeypatch
) -> None:
    """MED-03: declinar a reversão de evolve (L2 fallback) é no-op legítimo →
    _NOOP (exit 0), consistente com o ramo task-commit/reconfigure."""
    from engine import undo

    # Sem evento mem-inbox (routed_to None) → cai no fallback L2; L2 existe.
    monkeypatch.setattr(
        undo, "_evolve_apply_event_for", lambda *a, **k: None, raising=False
    )
    l2 = undo.memory_l2_path(tmp_forge_project)
    l2.parent.mkdir(parents=True, exist_ok=True)
    l2.write_text("notes: []\n", encoding="utf-8")
    monkeypatch.setattr(undo.question, "confirm", lambda *a, **k: False, raising=False)

    result = undo._undo_evolve(tmp_forge_project, "P-001")
    assert result is undo._NOOP, (
        f"declínio de reversão evolve é no-op, deveria ser _NOOP, obtido {result!r}"
    )
    assert undo._rc_for(result) == 0


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


def test_evolve_broken_pipe_returns_zero_functional(monkeypatch) -> None:
    """D3 (Fase 1) — regressão funcional: _run_evolve levanta BrokenPipeError →
    run() captura e retorna 0 (não propaga, não retorna 143)."""
    import io
    import sys
    from engine import evolve

    def _raise_broken_pipe(argv):
        raise BrokenPipeError("simulated SIGPIPE")

    monkeypatch.setattr(evolve, "_run_evolve", _raise_broken_pipe)
    # Substitui sys.stdout por um StringIO pra evitar que close() afete o
    # stdout real do pytest (evolve.run fecha o stdout no handler BrokenPipe).
    monkeypatch.setattr(sys, "stdout", io.StringIO())

    rc = evolve.run([])
    assert rc == 0, (
        f"BrokenPipeError não deve propagar; run() deveria retornar 0, obtido {rc}"
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
