"""forge upgrade — git pull + venv refresh + smoke + rollback gracioso.

Spec §3 D.2. Plan Task 4.4.

Opera no FORGE_HOME (diretório de instalação do feature-forge), NÃO no
projeto consumidor. Não exige forge-config.yaml.

Sequência:
  1. git fetch origin
  2. Compara HEAD local vs origin/main
  3. Se igual (e não force) → "já no latest", exit 0
  4. git pull --ff-only origin main
  5. pip install -e . --upgrade (venv refresh)
  6. bin/forge --version (smoke)
  7. Se smoke falha → git reset --hard <prev_head> + exit 4
  8. Se smoke ok → "atualizado", exit 0
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


# ── helpers testáveis ─────────────────────────────────────────────────────────


def _git_fetch(forge_home: Path) -> None:
    """Executa git fetch origin no forge_home."""
    subprocess.run(
        ["git", "fetch", "origin"],
        cwd=forge_home,
        check=True,
        capture_output=True,
    )


def _git_head_eq_origin(forge_home: Path) -> bool:
    """True se HEAD local == origin/main (sem commits novos remotos)."""
    local = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=forge_home,
    ).strip()
    remote = subprocess.check_output(
        ["git", "rev-parse", "origin/main"],
        cwd=forge_home,
    ).strip()
    return local == remote


def _git_pull(forge_home: Path) -> None:
    """git pull --ff-only origin main."""
    subprocess.run(
        ["git", "pull", "--ff-only", "origin", "main"],
        cwd=forge_home,
        check=True,
        capture_output=True,
    )


def _git_reset_hard(forge_home: Path, sha: str) -> None:
    """git reset --hard <sha> — rollback pós-smoke-falha."""
    subprocess.run(
        ["git", "reset", "--hard", sha],
        cwd=forge_home,
        check=True,
        capture_output=True,
    )


def _pip_refresh(forge_home: Path) -> None:
    """pip install -e . --upgrade no venv do forge_home."""
    pip_bin = forge_home / ".venv" / "bin" / "pip"
    subprocess.run(
        [str(pip_bin), "install", "-e", str(forge_home), "--upgrade"],
        cwd=forge_home,
        check=True,
        capture_output=True,
    )


def _smoke_version(forge_home: Path) -> bool:
    """Roda bin/forge --version. Retorna True se exit 0, False caso contrário."""
    forge_bin = forge_home / "bin" / "forge"
    result = subprocess.run(
        [str(forge_bin), "--version"],
        cwd=forge_home,
        capture_output=True,
    )
    return result.returncode == 0


def _resolve_forge_home(forge_home: Optional[Path]) -> Path:
    """Resolve forge_home via parâmetro, FORGE_HOME env, ou raiz do repo."""
    if forge_home is not None:
        return Path(forge_home)
    env_val = os.environ.get("FORGE_HOME")
    if env_val:
        return Path(env_val)
    # Fallback: raiz do repo (engine/upgrade.py está 2 níveis abaixo)
    return Path(__file__).resolve().parent.parent


def _git_current_sha(forge_home: Path) -> str:
    """Retorna o SHA atual do HEAD."""
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=forge_home,
    ).decode().strip()


# ── handler público ───────────────────────────────────────────────────────────


def run_upgrade(
    *,
    forge_home: Optional[Path] = None,
    force: bool = False,
) -> int:
    """Executa o upgrade do feature-forge.

    Parâmetros:
        forge_home: diretório de instalação. Se None, resolve via FORGE_HOME
                    env ou raiz do repo.
        force:      ignora o check "já no latest" e atualiza mesmo assim.

    Retorna:
        0 — sucesso ou já no latest
        4 — smoke falhou, rollback executado
        1 — erro inesperado
    """
    home = _resolve_forge_home(forge_home)

    try:
        prev_sha = _git_current_sha(home)
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(
            f"forge upgrade: erro ao ler HEAD — certifique-se de que "
            f"{home} é um repositório git.\n  {exc}\n"
        )
        return 1

    # 1. Fetch
    try:
        _git_fetch(home)
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(
            f"forge upgrade: git fetch falhou. Verifique conexão e credenciais.\n  {exc}\n"
        )
        return 1

    # 2. Verifica se já está no latest
    try:
        at_latest = _git_head_eq_origin(home)
    except subprocess.CalledProcessError:
        # Se origin/main não existe (shallow clone, remote diferente), continua.
        at_latest = False

    if at_latest and not force:
        sys.stdout.write("forge: já no latest — nenhuma atualização disponível.\n")
        return 0

    # 3. Pull
    try:
        _git_pull(home)
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(
            f"forge upgrade: git pull falhou.\n"
            f"  Três caminhos:\n"
            f"  A) Resolva conflitos manualmente em {home} e rode forge upgrade de novo.\n"
            f"  B) Use --force para sobrescrever (perde commits locais).\n"
            f"  C) Contate suporte se o problema persistir.\n"
            f"  Detalhe: {exc}\n"
        )
        return 1

    # 4. Venv refresh
    try:
        _pip_refresh(home)
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(
            f"forge upgrade: pip refresh falhou.\n"
            f"  Tente: {home}/.venv/bin/pip install -e {home} --upgrade\n"
            f"  Detalhe: {exc}\n"
        )
        # Pull já aconteceu — rollback
        try:
            _git_reset_hard(home, prev_sha)
            sys.stderr.write(f"forge upgrade: rollback executado para {prev_sha[:8]}.\n")
        except subprocess.CalledProcessError:
            sys.stderr.write(
                f"forge upgrade: rollback também falhou. Estado pode estar inconsistente.\n"
                f"  Rode manualmente: cd {home} && git reset --hard {prev_sha}\n"
            )
        return 4

    # 5. Smoke
    smoke_ok = _smoke_version(home)
    if not smoke_ok:
        sys.stderr.write(
            "forge upgrade: smoke check falhou após atualização.\n"
            "  Revertendo para versão anterior...\n"
        )
        try:
            _git_reset_hard(home, prev_sha)
            sys.stderr.write(f"  Rollback executado para {prev_sha[:8]}.\n")
            # Tenta re-fazer pip refresh pro sha anterior
            _pip_refresh(home)
        except subprocess.CalledProcessError:
            sys.stderr.write(
                f"forge upgrade: rollback ou pip re-refresh falhou.\n"
                f"  Rode manualmente: cd {home} && git reset --hard {prev_sha}\n"
            )
        return 4

    sys.stdout.write("forge: atualizado com sucesso.\n")
    return 0


# ── CLI adapter ───────────────────────────────────────────────────────────────


def run(argv: list[str]) -> int:
    """Entry point do CLI dispatcher (engine/cli.py COMMANDS registry).

    Aceita:
        --help / -h  → imprime uso e sai 0
        --force      → passa force=True para run_upgrade
        (sem args)   → run_upgrade normal
    """
    if argv and argv[0] in ("--help", "-h"):
        sys.stdout.write(
            "forge upgrade — atualiza o feature-forge para a versão mais recente.\n"
            "\n"
            "Uso: forge upgrade [--force]\n"
            "\n"
            "  --force   Atualiza mesmo que já esteja no latest.\n"
            "\n"
            "Opera no FORGE_HOME (diretório de instalação), não no projeto consumidor.\n"
        )
        return 0

    force = "--force" in argv
    return run_upgrade(force=force)
