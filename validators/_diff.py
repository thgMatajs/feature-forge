"""Diff-mode helpers — extracted from CC gate per Phase 0.

Usados por qualquer gate que precise limitar análise a staged files / diff
hunks, ou classificar ranges como new/modified/unchanged vs HEAD.

A separação em módulo próprio (vs deixar no CC validator) responde à
generalização planejada: futuros gates (cobertura, lint-on-changed,
deprecated-api-on-changed, etc.) reusam o mesmo raciocínio de staged-set +
hunk extraction. Sem o módulo, cada gate reinventaria o subprocess
`git diff --cached -U0` e a regra de classificação — caminho garantido pra
divergência sutil em rename detection (-M80%), timeout, ou semântica de
overlap.

Doc canônica: `docs/superpowers/specs/2026-06-04-gate-infra-extract-design.md`.

Contrato preservado vs versões privadas no CC gate:
  - `git_staged_files` mantém `-M80%` (rename detection per F-001/F-006).
  - `extract_diff_hunks` usa `-U0` pra hunks compactos sem context noise.
  - `classify_range_against_hunks` aplica regras §2 step 9 do CC spec
    (new = contido em add hunk; modified = intersecta; unchanged = nada).
  - `read_commit_body` lê `COMMIT_EDITMSG` (pre-commit) com fallback pra
    `git log -1 --format=%B HEAD` (pós-commit).

Falha silenciosa é regra: git ausente / não-repo / timeout devolvem
listas/strings vazias em vez de levantar — caller decide se isso bloqueia
o gate (CC trata "0 staged" como pass legítimo).
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# E1 — `kind` é Literal pra type-narrowing em callers. Runtime aceita
# qualquer string (preservação byte-a-byte com o contrato anterior), mas
# mypy/pyright/pylance reclamam de valores fora do triplet.
HunkKind = Literal["add", "del", "ctx"]


@dataclass(frozen=True)
class DiffHunk:
    """Range de linhas com classificação de diff side.

    `kind` é "add" por enquanto (único valor emitido pelo extractor — capta
    o lado `+` do diff). Futuros gates podem estender pra "del"/"ctx" se
    precisarem do raciocínio simétrico (ex.: detectar deleção de função
    que ainda tem callers).
    """

    start: int
    end: int
    kind: HunkKind


def classify_range_against_hunks(
    func_range: tuple[int, int],
    diff_hunks: list[DiffHunk],
) -> str:
    """Classifica um range de linhas como ``new`` | ``modified`` | ``unchanged``.

    Generalização do antigo ``classify_function`` do CC gate — renomeada
    pra refletir que qualquer range (não só funções) é classificável.

    Args:
        func_range: (start, end) inclusive, 1-indexed.
        diff_hunks: lista de DiffHunk extraídos do staged diff do mesmo
            arquivo. Lista vazia ⇒ retorna ``"unchanged"`` (não há diff a
            comparar — chamada típica pra arquivo só com hunks de outras
            seções).

    Regras (CC spec §2 step 9, preservadas literalmente):
        - ``new``        — ``func_range`` inteiro contido num add hunk.
        - ``modified``   — ``func_range`` intersecta qualquer hunk.
        - ``unchanged``  — nenhum overlap.
    """
    if not diff_hunks:
        return "unchanged"

    f_start, f_end = func_range
    add_hunks = [h for h in diff_hunks if h.kind == "add"]

    # "new" — range inteiro contido num único add hunk.
    for h in add_hunks:
        if h.start <= f_start and h.end >= f_end:
            return "new"

    # "modified" — qualquer interseção com qualquer hunk.
    for h in diff_hunks:
        if h.start <= f_end and h.end >= f_start:
            return "modified"

    return "unchanged"


def extract_diff_hunks(
    project_root: Path,
    files: list[Path],
) -> dict[str, list[DiffHunk]]:
    """Parse ``git diff --cached -U0`` por arquivo; devolve hunks por rel path.

    Apenas o lado ``+`` do diff é capturado — caller usa o resultado pra
    ``classify_range_against_hunks`` (new vs modified vs unchanged). ``-U0``
    produz hunks compactos sem context lines (reduz parsing noise).

    Falhas silenciosas (timeout, git ausente, arquivo fora do project_root)
    viram ``[]`` pro arquivo afetado — caller trata como "sem hunks" sem
    precisar de try/except.
    """
    by_file: dict[str, list[DiffHunk]] = {}
    for f in files:
        try:
            rel = str(f.relative_to(project_root))
        except ValueError:
            # Arquivo fora do project_root — skip silenciosamente.
            continue
        try:
            proc = subprocess.run(
                ["git", "-C", str(project_root), "diff", "--cached", "-U0", "--", rel],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (subprocess.SubprocessError, OSError):
            by_file[rel] = []
            continue
        hunks: list[DiffHunk] = []
        for line in proc.stdout.splitlines():
            if not line.startswith("@@"):
                continue
            # Hunk header: @@ -a,b +c,d @@
            m = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if not m:
                continue
            start = int(m.group(1))
            length = int(m.group(2)) if m.group(2) else 1
            hunks.append(
                DiffHunk(start=start, end=start + max(length - 1, 0), kind="add")
            )
        by_file[rel] = hunks
    return by_file


def git_staged_files(
    project_root: Path,
    *,
    extensions: set[str] | None = None,
) -> list[Path]:
    """Lista absoluta de paths de ``git diff --cached --name-only``.

    Args:
        project_root: raiz do repo consumidor.
        extensions: conjunto de suffixes (ex.: ``{".kt", ".swift", ".py"}``).
            Quando ``None``, devolve todos os staged files; quando set,
            filtra por ``p.suffix in extensions``.

    Preserva ``-M80%`` (rename detection per CC spec F-001/F-006): função
    renomeada (≥80% similaridade) classifica como "modified" pelo delta
    rule, não como "new" + delete. Sem o flag, renames viram falso-positivo
    com absolute-rule.

    Git indisponível / não-repo / timeout → lista vazia (caller trata como
    "nenhum arquivo a checar"). Timeout 10s evita hang em repo gigante.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(project_root), "diff", "--cached", "-M80%", "--name-only"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        return []
    if out.returncode != 0:
        return []
    files: list[Path] = []
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        p = project_root / line
        if not p.is_file():
            continue
        if extensions is not None and p.suffix not in extensions:
            continue
        files.append(p)
    return files


def read_commit_body(project_root: Path) -> str:
    """Best-effort read do commit message body (pra detectar override-justify).

    Ordem:
      1. ``.git/COMMIT_EDITMSG`` — populado pelo pre-commit hook (caso
         comum em ``forge implement``). Lê mesmo se o commit ainda não foi
         feito (cenário típico de gate rodando ENTRE Review e Commit).
      2. ``git log -1 --format=%B HEAD`` — fallback pós-commit (``forge
         verify`` rodando depois do commit já formado).

    Não-encontrado / erro → string vazia (sem overrides aplicáveis). O
    contrato silencioso casa com o caller que itera procurando padrão
    ``CC-OVERRIDE: ...`` (ou similar) — vazio = nada a aplicar.
    """
    # D1 — Resolve gitdir pra suportar worktrees (onde `.git` é arquivo
    # apontando pra `<repo>/.git/worktrees/<name>`). Antes lookup direto em
    # `project_root / ".git" / "COMMIT_EDITMSG"` falhava silenciosamente em
    # worktree, forçando fallback pra `git log` (que retorna commit prévio
    # em contexto pre-commit — bug observável neste próprio repo).
    #
    # Ordem de resolução:
    #   1. `git rev-parse --git-dir` (canônico — funciona em worktree real).
    #   2. Parse manual de `.git` file (`gitdir: <path>` line) — fallback
    #      pra cenários onde git CLI não consegue invocar (ex.: test fixtures
    #      sintéticas sem HEAD/refs).
    #   3. `<project_root>/.git/COMMIT_EDITMSG` direto (plain checkout).
    editmsg: Path | None = None
    try:
        proc = subprocess.run(
            ["git", "-C", str(project_root), "rev-parse", "--git-dir"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            git_dir = Path(proc.stdout.strip())
            if not git_dir.is_absolute():
                git_dir = project_root / git_dir
            editmsg = git_dir / "COMMIT_EDITMSG"
    except (subprocess.SubprocessError, OSError):
        pass

    if editmsg is None or not editmsg.is_file():
        dot_git = project_root / ".git"
        if dot_git.is_file():
            # Worktree: parse `gitdir: <path>` do .git file.
            try:
                first_line = dot_git.read_text(encoding="utf-8", errors="replace").splitlines()[0]
                if first_line.startswith("gitdir:"):
                    git_dir_path = Path(first_line.split(":", 1)[1].strip())
                    if not git_dir_path.is_absolute():
                        git_dir_path = project_root / git_dir_path
                    candidate = git_dir_path / "COMMIT_EDITMSG"
                    if candidate.is_file():
                        editmsg = candidate
            except (OSError, IndexError):
                pass
        elif dot_git.is_dir():
            candidate = dot_git / "COMMIT_EDITMSG"
            if candidate.is_file():
                editmsg = candidate

    if editmsg is not None and editmsg.is_file():
        try:
            return editmsg.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
    try:
        proc = subprocess.run(
            ["git", "-C", str(project_root), "log", "-1", "--format=%B"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0:
            return proc.stdout
    except (subprocess.SubprocessError, OSError):
        pass
    return ""
