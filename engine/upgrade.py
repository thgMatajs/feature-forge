"""forge upgrade — checkout da última release tag + venv refresh + smoke + rollback.

Spec §3 D.2. Plan Task 4.4.

Opera no FORGE_HOME (diretório de instalação do feature-forge), NÃO no
projeto consumidor. Não exige forge-config.yaml.

feature-forge se baseia SEMPRE na última RELEASE TAG (v*), nunca no main
bleeding-edge. O install deixa o repo em detached HEAD numa tag de release;
o upgrade traz as tags novas e faz checkout da mais recente.

Sequência:
  1. Captura prev_sha (HEAD atual) — referência pra rollback
  2. git fetch origin --tags --force (traz tags novas)
  3. Descobre a última tag local (v*, semver desc)
  4. Se nenhuma tag → no-op com aviso, exit 0
  5. Se SHA da última tag == prev_sha (e não force) → "já no latest", exit 0
  6. git checkout --detach <latest_tag>
  7. pip install -e . --upgrade (venv refresh)
  8. bin/forge --version (smoke)
  9. Se smoke falha → git checkout --detach <prev_sha> + exit 4
  10. Se smoke ok → "atualizado para <latest_tag>", exit 0
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from engine.ui.exit_codes import ERR_UPGRADE_FAILED, fail_with_tag


# ── helpers testáveis ─────────────────────────────────────────────────────────


def _git_fetch(forge_home: Path) -> None:
    """Executa git fetch origin --tags --force no forge_home.

    --tags traz tags novas (releases); --force atualiza tags que mudaram de
    SHA remotamente (raro, mas evita divergência silenciosa).
    """
    subprocess.run(
        ["git", "fetch", "origin", "--tags", "--force"],
        cwd=forge_home,
        check=True,
        capture_output=True,
    )


def _latest_local_tag(forge_home: Path) -> Optional[str]:
    """Retorna a última tag de release (v*) por semver desc, ou None.

    Roda após _git_fetch, então as tags remotas já estão disponíveis
    localmente. Usa --sort=-v:refname (semver descendente, git 2.18+).
    """
    out = subprocess.check_output(
        ["git", "tag", "-l", "v*", "--sort=-v:refname"],
        cwd=forge_home,
    ).decode().strip()
    if not out:
        return None
    return out.splitlines()[0].strip()


def _tag_sha(forge_home: Path, tag: str) -> str:
    """Retorna o SHA do commit apontado por <tag> (rev-list -1)."""
    return subprocess.check_output(
        ["git", "rev-list", "-1", tag],
        cwd=forge_home,
    ).decode().strip()


def _git_checkout(forge_home: Path, ref: str) -> None:
    """git checkout --detach <ref> — aponta o HEAD pra uma tag ou SHA.

    Detached HEAD é o estado canônico pós-install (repo numa release tag),
    e também o alvo do rollback (volta pro SHA anterior).
    """
    subprocess.run(
        ["git", "checkout", "--detach", ref],
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
    """Executa o upgrade do feature-forge para a última release tag.

    Parâmetros:
        forge_home: diretório de instalação. Se None, resolve via FORGE_HOME
                    env ou raiz do repo.
        force:      ignora o check "já no latest" e re-checkout a última tag
                    mesmo assim.

    Retorna:
        0 — sucesso, já no latest, ou nenhuma release tag (no-op com aviso)
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

    # 1. Fetch (traz tags novas)
    try:
        _git_fetch(home)
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(
            f"forge upgrade: git fetch falhou. Verifique conexão e credenciais.\n  {exc}\n"
        )
        return 1

    # 2. Descobre a última release tag
    try:
        latest_tag = _latest_local_tag(home)
    except subprocess.CalledProcessError:
        latest_tag = None

    if latest_tag is None:
        sys.stdout.write(
            "forge: nenhuma release tag encontrada — nada para atualizar.\n"
            "  feature-forge se baseia em releases (tags v*); aguarde a próxima.\n"
        )
        return 0

    # 3. Já estamos na última release?
    try:
        latest_sha = _tag_sha(home, latest_tag)
    except subprocess.CalledProcessError:
        latest_sha = None

    if latest_sha == prev_sha and not force:
        sys.stdout.write(
            f"forge: já no latest ({latest_tag}) — nenhuma atualização disponível.\n"
        )
        return 0

    # 4. Checkout da última tag
    try:
        _git_checkout(home, latest_tag)
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(
            f"forge upgrade: checkout da release {latest_tag} falhou.\n"
            f"  Três caminhos:\n"
            f"  A) Verifique mudanças locais não commitadas em {home} e rode de novo.\n"
            f"  B) Restaure o estado anterior: cd {home} && git checkout --detach {prev_sha}\n"
            f"  C) Contate suporte se o problema persistir.\n"
            f"  Detalhe: {exc}\n"
        )
        return 1

    # 5. Venv refresh
    try:
        _pip_refresh(home)
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(
            f"forge upgrade: pip refresh falhou.\n"
            f"  Tente: {home}/.venv/bin/pip install -e {home} --upgrade\n"
            f"  Detalhe: {exc}\n"
        )
        # Checkout já aconteceu — rollback pro sha anterior (código + venv)
        try:
            _git_checkout(home, prev_sha)
            sys.stderr.write(f"forge upgrade: rollback executado para {prev_sha[:8]}.\n")
            # Re-faz pip refresh pro sha anterior — restaura o venv ao estado
            # que funcionava (pip pode ter mutado deps parcialmente acima).
            _pip_refresh(home)
        except subprocess.CalledProcessError:
            sys.stderr.write(
                f"forge upgrade: rollback ou pip re-refresh falhou. Estado pode estar inconsistente.\n"
                f"  Rode manualmente: cd {home} && git checkout --detach {prev_sha}\n"
            )
        return fail_with_tag(ERR_UPGRADE_FAILED)

    # 6. Smoke
    smoke_ok = _smoke_version(home)
    if not smoke_ok:
        sys.stderr.write(
            f"forge upgrade: smoke check falhou após atualização para {latest_tag}.\n"
            "  Revertendo para a versão anterior...\n"
        )
        try:
            _git_checkout(home, prev_sha)
            sys.stderr.write(f"  Rollback executado para {prev_sha[:8]}.\n")
            # Tenta re-fazer pip refresh pro sha anterior
            _pip_refresh(home)
        except subprocess.CalledProcessError:
            sys.stderr.write(
                f"forge upgrade: rollback ou pip re-refresh falhou.\n"
                f"  Rode manualmente: cd {home} && git checkout --detach {prev_sha}\n"
            )
        return fail_with_tag(ERR_UPGRADE_FAILED)

    sys.stdout.write(f"forge: atualizado para {latest_tag} com sucesso.\n")
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
