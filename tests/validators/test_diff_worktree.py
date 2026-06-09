"""Worktree-safe `read_commit_body` + Literal DiffHunk.kind (PR #7 D1, E1).

D1 — `read_commit_body` resolvia `project_root / ".git" / "COMMIT_EDITMSG"`
direto. Em worktree, `.git` é arquivo (não diretório) apontando pra
`gitdir: <real-path>/.git/worktrees/<name>`. O lookup direto falhava,
forçando fallback pra `git log` (que retorna commit prévio em pre-commit).

Fix: usa `git rev-parse --git-dir` pra resolver o gitdir real antes de
ler `COMMIT_EDITMSG`.

E1 — `DiffHunk.kind` agora é `Literal["add", "del", "ctx"]` (sem behavior
change em runtime — type narrowing pra benefício de callers).
"""

from __future__ import annotations

from pathlib import Path

from _diff import DiffHunk, read_commit_body


def test_read_commit_body_resolves_gitdir_in_worktree(tmp_path: Path) -> None:
    """Em worktree (`.git` é arquivo), COMMIT_EDITMSG vive no gitdir real."""
    # Setup: simula estrutura worktree
    real_gitdir = tmp_path / "real_repo" / ".git" / "worktrees" / "wt-foo"
    real_gitdir.mkdir(parents=True)
    expected_msg = "feat(test): este é o commit em curso\n\nCorpo do commit.\n"
    (real_gitdir / "COMMIT_EDITMSG").write_text(expected_msg, encoding="utf-8")

    # Worktree path tem `.git` como arquivo apontando pro gitdir real
    worktree = tmp_path / "wt-foo"
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {real_gitdir}\n", encoding="utf-8")

    body = read_commit_body(worktree)
    # Deve ter resolvido o gitdir e lido o COMMIT_EDITMSG correto
    assert "feat(test): este é o commit em curso" in body
    assert "Corpo do commit." in body


def test_read_commit_body_still_works_in_plain_checkout(tmp_path: Path) -> None:
    """Plain checkout (`.git` é diretório) preserva comportamento prévio."""
    repo = tmp_path / "plain"
    git_dir = repo / ".git"
    git_dir.mkdir(parents=True)
    expected = "fix: plain checkout commit\n"
    (git_dir / "COMMIT_EDITMSG").write_text(expected, encoding="utf-8")
    body = read_commit_body(repo)
    assert "fix: plain checkout commit" in body


def test_diff_hunk_kind_accepts_canonical_values() -> None:
    """E1 — `kind` é Literal["add", "del", "ctx"] em type level; runtime aceita os 3."""
    add = DiffHunk(start=1, end=5, kind="add")
    delh = DiffHunk(start=1, end=5, kind="del")
    ctx = DiffHunk(start=1, end=5, kind="ctx")
    assert add.kind == "add"
    assert delh.kind == "del"
    assert ctx.kind == "ctx"
