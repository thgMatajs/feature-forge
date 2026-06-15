"""Lazy auto-build em ``engine/graph_cli.py`` (Task 9.5, graph-ia-evolution).

Contract (spec AC-11):

- Quando ``.claude/graph.db`` está ausente, ``_maybe_auto_build`` invoca
  ``engine.graph.builder.build_full`` antes do dispatch da query.
- Quando o DB existe mas ``files`` table está vazia, idem.
- Flag ``--no-auto-build`` (CI/scripts) desativa o auto-build e mantém
  comportamento legado (graph_cli sai com erro se DB ausente).
- Em ``--json`` mode, mensagem de "buildando..." vai pra stderr (nunca
  stdout — stdout fica limpo pra JSON consumers).

Refs:
- docs/superpowers/specs/2026-06-12-graph-ia-evolution.md AC-11
- docs/superpowers/plans/2026-06-12-graph-ia-evolution.md Task 9.5.3/9.5.6/9.5.7
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from engine import graph_cli


# ── Helpers ─────────────────────────────────────────────────────────────────


def _seed_empty_graph_db(project_root: Path) -> Path:
    """Cria ``.claude/graph.db`` com schema canônico mas sem build marker.

    Simula o estado pós-``init_schema`` mas pré-``build_full``: a tabela
    ``meta`` existe mas ``last_full_rebuild_at`` ainda não foi setado.
    Este é o trigger canônico do lazy auto-build (Task 9.5 spec AC-11).
    """
    cfg_dir = project_root / ".claude"
    cfg_dir.mkdir(exist_ok=True)
    (cfg_dir / "workflow-config.yaml").write_text(
        "schema-version: 1\nidentity:\n  project-slug: test-lazy-build\n",
        encoding="utf-8",
    )
    db_path = cfg_dir / "graph.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY, path TEXT, module TEXT, source_set TEXT
        );
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY, value TEXT
        );
        """
    )
    conn.commit()
    conn.close()
    return db_path


def _ensure_workflow_config(project_root: Path) -> None:
    """Cria workflow-config.yaml mínimo (sem touch no DB)."""
    cfg_dir = project_root / ".claude"
    cfg_dir.mkdir(exist_ok=True)
    (cfg_dir / "workflow-config.yaml").write_text(
        "schema-version: 1\nidentity:\n  project-slug: test-lazy-build\n",
        encoding="utf-8",
    )


def _patch_build_full(monkeypatch: pytest.MonkeyPatch, calls: list[Path]) -> None:
    """Substitui ``engine.graph.builder.build_full`` por spy.

    Captura cada invocação em ``calls`` e cria um DB seedado mínimo no
    target, simulando build bem-sucedido sem walk de filesystem real.
    """

    def _fake_build_full(project_root: Path, *args: object, **kwargs: object) -> dict:
        calls.append(project_root)
        # Cria DB seedado pra graph_cli passar do guard pós-build
        cfg_dir = project_root / ".claude"
        cfg_dir.mkdir(exist_ok=True)
        db_path = cfg_dir / "graph.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY, path TEXT, module TEXT, source_set TEXT
            );
            CREATE TABLE IF NOT EXISTS symbols (
                id INTEGER PRIMARY KEY, file_id INTEGER, name TEXT, kind TEXT,
                visibility TEXT, signature TEXT, receiver_type TEXT,
                body_hash TEXT, body_tokens TEXT, modifiers TEXT, line_start INTEGER
            );
            CREATE TABLE IF NOT EXISTS imports (from_file_id INTEGER, to_symbol TEXT);
            INSERT INTO files(path, module, source_set) VALUES ('Probe.kt', ':app', 'main');
            """
        )
        conn.commit()
        conn.close()
        return {"files_scanned": 1, "symbols_extracted": 0, "edges_created": 0, "duration_ms": 1}

    monkeypatch.setattr("engine.graph.builder.build_full", _fake_build_full)


# ── Lazy build triggers ────────────────────────────────────────────────────


def test_lazy_build_triggers_when_db_missing(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``.claude/graph.db`` ausente + ``forge graph --json q3`` → build dispatched."""
    _ensure_workflow_config(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    calls: list[Path] = []
    _patch_build_full(monkeypatch, calls)

    rc = graph_cli.run(["--json", "q3"])

    assert rc == 0
    assert len(calls) == 1
    assert calls[0].resolve() == tmp_forge_project.resolve()


def test_lazy_build_triggers_when_db_never_built(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DB existe mas ``meta.last_full_rebuild_at`` está NULL → build dispatched.

    O helper ``_seed_empty_graph_db`` cria schema mínimo (``files``, ``meta``)
    sem inserir o marker ``last_full_rebuild_at`` — o trigger canônico do
    lazy auto-build (spec AC-11) é exatamente esse: DB inicializado mas
    nunca buildado.
    """
    _seed_empty_graph_db(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    calls: list[Path] = []
    _patch_build_full(monkeypatch, calls)

    rc = graph_cli.run(["--json", "q3"])

    assert rc == 0
    assert len(calls) == 1


def test_lazy_build_skipped_with_no_auto_build_flag(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--no-auto-build`` desativa auto-build, mantém comportamento legado.

    Sem DB + flag → graph_cli sai com erro (mensagem canônica de DB
    ausente em ``--json`` mode), ``build_full`` NÃO é chamado.
    """
    _ensure_workflow_config(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    calls: list[Path] = []
    _patch_build_full(monkeypatch, calls)

    rc = graph_cli.run(["--no-auto-build", "--json", "q3"])

    # Sem build, DB ausente → exit 1 + mensagem canônica
    assert rc == 1
    assert len(calls) == 0
    err = capsys.readouterr().err
    assert "graph.db" in err.lower()


def test_json_usage_error_does_not_trigger_auto_build(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """H-005: ``forge graph --json`` (sem query) NÃO dispara build_full.

    Antes do fix v1.3, ``_maybe_auto_build`` rodava ANTES da validação de
    argv — usuário que digitava `forge graph --json` por engano pagava
    ~30s-2min de build pra receber exit 1 + usage. Agora a validação roda
    primeiro, e o build só acontece se o argv for legítimo.
    """
    _ensure_workflow_config(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    calls: list[Path] = []
    _patch_build_full(monkeypatch, calls)

    rc = graph_cli.run(["--json"])

    assert rc == 1, "usage error deve sair com exit 1"
    assert len(calls) == 0, "build_full NÃO deve rodar quando argv é inválido"
    # Usage message presente em stderr ou stdout
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "forge graph --json" in combined.lower() or "uso" in combined.lower()


def test_json_unknown_query_does_not_trigger_auto_build(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """H-005: ``forge graph --json badquerykey`` NÃO dispara build_full.

    Query desconhecida vai sair com exit 1 antes de pagar o custo do build.
    """
    _ensure_workflow_config(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    calls: list[Path] = []
    _patch_build_full(monkeypatch, calls)

    rc = graph_cli.run(["--json", "badquerykey"])

    assert rc == 1
    assert len(calls) == 0, "build_full NÃO deve rodar quando query é desconhecida"


def test_lazy_build_quiet_in_json_mode(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Em ``--json`` mode, mensagem de build vai pra stderr (não polui stdout JSON)."""
    _ensure_workflow_config(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    calls: list[Path] = []
    _patch_build_full(monkeypatch, calls)

    rc = graph_cli.run(["--json", "q3"])

    assert rc == 0
    captured = capsys.readouterr()
    # stdout deve ser JSON puro (lista vazia neste case — files seedado tem 1
    # entry mas q3=orphan-files pode retornar [] dependendo do schema)
    stdout = captured.out.strip()
    # Garantia: stdout não contém mensagem de build
    assert "buildando" not in stdout.lower()
    assert "building" not in stdout.lower()
    # JSON parseável
    import json
    json.loads(stdout)  # raises se inválido
