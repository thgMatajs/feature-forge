"""Non-interactive ``forge graph --json <query>`` flag (Task 3, graph-ia).

Contract (spec AC-3):
- ``--json`` reconhecida ao lado do argumento de query.
- Aliases short (``q1``..``q17``, ``r``), labels textuais (``orphan-files``,
  ``symbols``…), e numeric keys (``1``..``17``) sao todos validos.
- Output e JSON parseavel em stdout. stderr reservado pra erros.
- Modo interactivo (``forge graph`` sem ``--json``) continua disponivel e
  inalterado (regression).
- Sem args apos ``--json`` ou query desconhecida → exit 1 + usage/erro em
  stderr.

Refs:
- docs/superpowers/specs/2026-06-12-graph-ia-evolution.md AC-3
- docs/superpowers/plans/2026-06-12-graph-ia-evolution.md Task 3
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from engine import graph_cli


# ── Helpers ─────────────────────────────────────────────────────────────────


def _seed_graph_db(project_root: Path) -> None:
    """Cria um ``.claude/graph.db`` minimo pra graph_cli passar do guard.

    Apenas o arquivo precisa existir — as queries usadas nestes tests
    (``find_orphan_files``, ``find_reusable_helpers``, etc.) abrem o DB
    em modo read-only mas ja capturam ``OperationalError`` quando as
    tabelas nao existem; isso e suficiente pra exercitar o code path
    do ``--json``.
    """
    cfg_dir = project_root / ".claude"
    cfg_dir.mkdir(exist_ok=True)
    (cfg_dir / "workflow-config.yaml").write_text(
        "schema-version: 1\nidentity:\n  project-slug: test-graph-cli-json\n",
        encoding="utf-8",
    )
    db_path = cfg_dir / "graph.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE IF NOT EXISTS _bootstrap(k TEXT)")
    # Tabelas vazias mas presentes — queries retornam [] sem raise.
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY,
            path TEXT,
            module TEXT,
            source_set TEXT
        );
        CREATE TABLE IF NOT EXISTS symbols (
            id INTEGER PRIMARY KEY,
            file_id INTEGER,
            name TEXT,
            kind TEXT,
            visibility TEXT,
            signature TEXT,
            receiver_type TEXT,
            body_hash TEXT,
            body_tokens TEXT,
            modifiers TEXT,
            line_start INTEGER
        );
        CREATE TABLE IF NOT EXISTS imports (
            from_file_id INTEGER,
            to_symbol TEXT
        );
        CREATE TABLE IF NOT EXISTS reuse_findings (
            id INTEGER PRIMARY KEY,
            category TEXT,
            symbol_name TEXT,
            confidence REAL
        );
        CREATE TABLE IF NOT EXISTS reuse_finding_locations (
            finding_id INTEGER,
            file_id INTEGER,
            module TEXT,
            source_set TEXT,
            line_start INTEGER,
            language TEXT,
            body_hash TEXT
        );
        CREATE TABLE IF NOT EXISTS ds_components (
            id INTEGER PRIMARY KEY,
            name TEXT
        );
        CREATE TABLE IF NOT EXISTS ds_usage (
            component_id INTEGER,
            screen_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS screens (
            id INTEGER PRIMARY KEY,
            feature_slug TEXT,
            file_id INTEGER,
            route_id INTEGER
        );
        """
    )
    conn.commit()
    conn.close()


# ── Happy path ──────────────────────────────────────────────────────────────


def test_json_flag_with_q3_returns_valid_json(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``forge graph --json q3`` (orphan-files) emite JSON parseavel em stdout."""
    _seed_graph_db(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    rc = graph_cli.run(["--json", "q3"])

    assert rc == 0
    out = capsys.readouterr().out.strip()
    parsed = json.loads(out)
    # Orphan-files retorna lista (vazia, pq files table ta vazia)
    assert isinstance(parsed, list)


def test_json_flag_with_numeric_key_works(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Numeric key ``3`` (sem prefix ``q``) tambem resolve pra orphan-files."""
    _seed_graph_db(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    rc = graph_cli.run(["--json", "3"])

    assert rc == 0
    parsed = json.loads(capsys.readouterr().out.strip())
    assert isinstance(parsed, list)


def test_json_flag_with_label_works(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Label textual (``orphan-files``) resolve pro mesmo handler."""
    _seed_graph_db(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    rc = graph_cli.run(["--json", "orphan-files"])

    assert rc == 0
    parsed = json.loads(capsys.readouterr().out.strip())
    assert isinstance(parsed, list)


def test_json_flag_with_query_taking_arg(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--json q5 some-slug`` passa o slug pra ``find_ds_components_used_in``.

    Resultado e lista vazia (DB vazio), mas o handler executa sem prompt.
    """
    _seed_graph_db(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    rc = graph_cli.run(["--json", "q5", "lembrete-rega"])

    assert rc == 0
    parsed = json.loads(capsys.readouterr().out.strip())
    assert isinstance(parsed, list)


# ── Error paths ─────────────────────────────────────────────────────────────


def test_json_flag_without_args_prints_usage_and_exits_1(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``forge graph --json`` (sem query) → exit 1 + usage."""
    _seed_graph_db(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    rc = graph_cli.run(["--json"])

    assert rc == 1
    captured = capsys.readouterr()
    # Usage pode sair em stdout ou stderr — checamos ambos.
    combined = captured.out + captured.err
    assert "forge graph --json" in combined.lower() or "uso" in combined.lower() or "usage" in combined.lower()


def test_json_flag_unknown_query_exits_1(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Query identifier que nao mapeia → exit 1 + erro descritivo."""
    _seed_graph_db(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    rc = graph_cli.run(["--json", "badquerykey"])

    assert rc == 1
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "badquerykey" in combined or "unknown" in combined.lower()


def test_json_flag_skips_interactive_prompt(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--json`` mode NUNCA chama ``question.ask`` do menu.

    Se chamasse, o handler do prompt levantaria ``PromptAbortedError`` (sem
    TTY) e o teste falharia com exit != 0 + nenhum JSON em stdout.
    """
    _seed_graph_db(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    # Sentinel: instrumentamos question.ask pra explodir se chamado.
    from engine.ui import question

    def _boom(*args: object, **kwargs: object) -> str:  # pragma: no cover
        raise AssertionError("question.ask should not be called in --json mode")

    monkeypatch.setattr(question, "ask", _boom)

    rc = graph_cli.run(["--json", "q3"])

    assert rc == 0
    json.loads(capsys.readouterr().out.strip())  # raises if not valid JSON


# ── Regression — modo interactivo continua intacto ──────────────────────────


def test_interactive_mode_unaffected_by_json_implementation(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``forge graph`` (sem ``--json``) ainda chama ``question.ask`` do menu.

    Regression guard: a impl de ``--json`` nao deve curto-circuitar o
    path interactivo.
    """
    _seed_graph_db(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    from engine.ui import question

    called = {"count": 0}

    def _spy(*args: object, **kwargs: object) -> str:
        called["count"] += 1
        return "c"  # cancelar — exit limpo

    monkeypatch.setattr(question, "ask", _spy)

    rc = graph_cli.run([])

    assert rc == 0
    assert called["count"] >= 1, "question.ask deveria ser chamado em modo interativo"


def test_detect_incremental_subcommand_still_works(
    tmp_forge_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``forge graph detect-incremental`` (subcommand existente) continua OK.

    Sem args → return 0 (early exit). Guard que ``--json`` nao engole
    o branch existente.
    """
    _seed_graph_db(tmp_forge_project)
    monkeypatch.chdir(tmp_forge_project)

    rc = graph_cli.run(["detect-incremental"])

    assert rc == 0
