"""Tests for the `compose-screens` card validator `check-no-suppress.py` (P-24).

O validator é um script subprocess isolado (card validator), invocado pelo
engine como `python3 <script> --project-root <path>` com cwd=project_root e,
opcionalmente, `--scope <kind> --id <target>`. Estes testes espelham esse
contrato real: rodam o script como subprocess sobre fixtures Kotlin em tmp dir.

Regra: bloquear `@Suppress`/`@file:Suppress` em código Compose UI; ignorar
ocorrências em comentário de linha, KDoc e string literal; restringir ao
escopo Compose (segmentos de path) excluindo test source sets.

Plan: docs/superpowers/plans/2026-06-19-pilot-r6-aifirst-blockers.md §C1
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "cards"
    / "compose-screens"
    / "validators"
    / "check-no-suppress.py"
)


def _run(project_root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--project-root", str(project_root), *extra],
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ── happy path ───────────────────────────────────────────────────────────────


def test_clean_compose_passes(tmp_path: Path) -> None:
    _write(
        tmp_path / "androidApp/feature/home/ui/HomeScreen.kt",
        "@Composable\nfun HomeScreen() {\n    Text(\"hi\")\n}\n",
    )
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr


# ── violations ───────────────────────────────────────────────────────────────


def test_suppress_annotation_fails(tmp_path: Path) -> None:
    _write(
        tmp_path / "androidApp/feature/home/ui/HomeScreen.kt",
        "@Suppress(\"LongMethod\")\n@Composable\nfun HomeScreen() {}\n",
    )
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "HomeScreen.kt" in result.stderr
    assert "@Suppress" in result.stderr


def test_file_suppress_fails(tmp_path: Path) -> None:
    _write(
        tmp_path / "androidApp/feature/home/ui/HomeScreen.kt",
        "@file:Suppress(\"ktlint\")\n\npackage feature.home\n",
    )
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "HomeScreen.kt" in result.stderr


# ── false-positive guards (comment / kdoc / string) ──────────────────────────


def test_suppress_in_comment_ignored(tmp_path: Path) -> None:
    _write(
        tmp_path / "androidApp/feature/home/ui/HomeScreen.kt",
        "@Composable\nfun HomeScreen() {\n    // @Suppress aqui é só doc\n}\n",
    )
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr


def test_suppress_in_kdoc_ignored(tmp_path: Path) -> None:
    _write(
        tmp_path / "androidApp/feature/home/ui/HomeScreen.kt",
        "/**\n * Exemplo de uso de @Suppress documentado.\n * @Suppress nada aqui\n */\n"
        "@Composable\nfun HomeScreen() {}\n",
    )
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr


def test_suppress_in_string_literal_ignored(tmp_path: Path) -> None:
    _write(
        tmp_path / "androidApp/feature/home/ui/HomeScreen.kt",
        "@Composable\nfun HomeScreen() {\n    val s = \"@Suppress fake\"\n}\n",
    )
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr


def test_suppress_after_string_with_slashes(tmp_path: Path) -> None:
    """WR-01: `//` dentro de string literal não pode truncar a linha — um
    `@Suppress` REAL que venha depois na mesma linha deve ser detectado.
    """
    _write(
        tmp_path / "androidApp/feature/home/ui/HomeScreen.kt",
        "@Composable\nfun HomeScreen() {\n"
        "    val u = \"a//b\"; @Suppress(\"x\") val y = bad()\n}\n",
    )
    result = _run(tmp_path)
    assert result.returncode == 1, result.stderr
    assert "@Suppress" in result.stderr


def test_suppress_in_raw_string_ignored(tmp_path: Path) -> None:
    """WR-02: `@Suppress` mencionado dentro de raw-string `\"\"\"...\"\"\"`
    multi-linha é documentação, não silenciamento — deve passar.
    """
    _write(
        tmp_path / "androidApp/feature/home/ui/HomeScreen.kt",
        "@Composable\nfun HomeScreen() {\n"
        "    val doc = \"\"\"\n"
        "        Use @Suppress to silence the linter (doc em raw string)\n"
        "    \"\"\"\n}\n",
    )
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr


def test_suppress_after_char_literal_with_quote(tmp_path: Path) -> None:
    """A1: um char literal contendo `"` (ex.: `val q = '"'`) não pode fazer o
    scanner entrar em modo string e engolir um `@Suppress` REAL que venha
    depois na mesma linha. O char literal deve ser neutralizado e o
    `@Suppress` detectado.
    """
    _write(
        tmp_path / "androidApp/feature/home/ui/HomeScreen.kt",
        "@Composable\nfun HomeScreen() {\n"
        "    val q = '\"'; @Suppress(\"UnusedPrivateMember\") val y = bad()\n}\n",
    )
    result = _run(tmp_path)
    assert result.returncode == 1, result.stderr
    assert "@Suppress" in result.stderr


def test_suppress_inside_char_literal_ignored(tmp_path: Path) -> None:
    """A1 (false-positive guard): um char literal sozinho não pode disparar
    falso positivo nem deixar a varredura inconsistente. Linha limpa passa.
    """
    _write(
        tmp_path / "androidApp/feature/home/ui/HomeScreen.kt",
        "@Composable\nfun HomeScreen() {\n"
        "    val esc = '\\''; val nl = '\\n'; val dq = '\"'\n}\n",
    )
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr


def test_unreadable_in_scope_file_fails_closed(tmp_path: Path) -> None:
    """A2: um arquivo .kt em escopo Compose que dispara OSError na leitura NÃO
    pode passar o gate silenciosamente — o validator deve falhar fechado
    (exit 1) e avisar no stderr.

    Determinístico cross-platform: cria um symlink `*.kt` em escopo Compose
    apontando pra um alvo inexistente. A varredura o trata como arquivo (não
    é dir), e `read_text` levanta FileNotFoundError (subclasse de OSError) —
    exatamente o ramo a cobrir, sem depender de chmod (que root ignora).
    """
    import os

    bad = tmp_path / "androidApp/feature/home/ui/HomeScreen.kt"
    bad.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(tmp_path / "does-not-exist.kt", bad)
    except (OSError, NotImplementedError):
        return  # plataforma sem symlink — skip implícito
    result = _run(tmp_path)
    assert result.returncode == 1, result.stderr
    assert "HomeScreen.kt" in result.stderr


def test_build_dir_kt_ignored(tmp_path: Path) -> None:
    """M1: arquivos .kt sob `build/` (gerados) não devem ser varridos — um
    `@Suppress` ali não pode falhar o gate.
    """
    _write(
        tmp_path / "androidApp/feature/home/build/generated/Gen.kt",
        "@Suppress(\"LongMethod\")\nfun gen() {}\n",
    )
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr


def test_symlinked_dir_not_descended(tmp_path: Path) -> None:
    """M1: dirs que são symlink dentro do escopo não devem ser descidos (evita
    loop/hang). O alvo do symlink contém um `@Suppress`; se o validator
    descesse no symlink, varreria como `androidApp/.../link/Bad.kt` (em escopo)
    e falharia. Como NÃO desce em symlinks, deve passar (exit 0).
    """
    import os

    # alvo fora de escopo Compose, com @Suppress dentro
    target = tmp_path / "external/lib"
    _write(target / "Bad.kt", "@Suppress(\"x\")\nfun s() {}\n")
    link = tmp_path / "androidApp/feature/home/link"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        return  # plataforma sem symlink — skip implícito
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr


def test_suppress_in_nested_block_comment(tmp_path: Path) -> None:
    """WR-03: block comments aninhados (`/* /* */ */`) não podem fechar cedo —
    um `@Suppress` dentro do bloco externo deve ser ignorado.
    """
    _write(
        tmp_path / "androidApp/feature/home/ui/HomeScreen.kt",
        "@Composable\nfun HomeScreen() {\n"
        "    /* outer /* inner */ @Suppress */\n}\n",
    )
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr


# ── scope filtering ──────────────────────────────────────────────────────────


def test_non_compose_source_set_ignored(tmp_path: Path) -> None:
    """IN-03: exercita o ramo TEST_SOURCE_SETS real — o path está DENTRO do
    escopo Compose (`composeApp/src/`), mas é um test source set (`commonTest`),
    então `@Suppress` ali é tolerado. A fixture antiga (`shared/src/commonTest`)
    já estava fora do escopo Compose por COMPOSE_PATH_SEGMENTS, então passava
    por acaso sem provar a exclusão de test source set.
    """
    _write(
        tmp_path / "composeApp/src/commonTest/kotlin/feature/home/Foo.kt",
        "@Suppress(\"LongMethod\")\nfun foo() {}\n",
    )
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr


# ── invocation contract ──────────────────────────────────────────────────────


def test_tolerates_scope_and_id_flags(tmp_path: Path) -> None:
    _write(
        tmp_path / "androidApp/feature/home/ui/HomeScreen.kt",
        "@Composable\nfun HomeScreen() {}\n",
    )
    result = _run(tmp_path, "--scope", "feature", "--id", "home")
    assert result.returncode == 0, result.stderr


def test_empty_project_passes(tmp_path: Path) -> None:
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
