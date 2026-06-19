"""A3 ENV-1 — scrubbed_subprocess_env remove sinais de host agêntico.

Subprocessos filhos do forge (validators spawnados por ingest) não devem
herdar CLAUDECODE / OPENCODE_* / CODEX* / CURSOR_* / FORGE_FORCE_*_MODE — senão
um forge aninhado escolheria o adapter errado e penderia esperando um driver
inexistente (hang).
"""
from __future__ import annotations

from engine.host import env as host_env


_POLLUTERS = {
    "CLAUDECODE": "1",
    "FORGE_FORCE_INTENT_MODE": "1",
    "FORGE_FORCE_TTY_MODE": "1",
    "OPENCODE_VERSION": "0.9",
    "OPENCODE_SERVER_PASSWORD": "secret",
    "CODEX_CLI": "1",
    "CURSOR_AGENT": "1",
    "CURSOR_TRACE_ID": "abc",
}


def test_scrub_removes_all_agentic_keys(monkeypatch):
    for k, v in _POLLUTERS.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("JAVA_HOME", "/opt/java")

    scrubbed = host_env.scrubbed_subprocess_env()

    for k in _POLLUTERS:
        assert k not in scrubbed, f"{k} deveria ter sido removido do env"
    # Keys legítimas preservadas (deny-list cirúrgica, não allowlist).
    assert scrubbed.get("PATH") == "/usr/bin"
    assert scrubbed.get("JAVA_HOME") == "/opt/java"


def test_scrub_returns_copy_not_mutating_os_environ(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    import os

    scrubbed = host_env.scrubbed_subprocess_env()
    assert "CLAUDECODE" not in scrubbed
    # os.environ original NÃO foi mutado — só a cópia.
    assert os.environ.get("CLAUDECODE") == "1"


def test_scrubbed_env_makes_detect_fall_through(monkeypatch):
    """Prova o efeito: com env scrubbed aplicado a os.environ, nenhum
    detector de host agêntico dispara."""
    for k, v in _POLLUTERS.items():
        monkeypatch.setenv(k, v)

    scrubbed = host_env.scrubbed_subprocess_env()
    monkeypatch.setattr("os.environ", scrubbed)
    assert host_env.detect_claude_code() is False
    assert host_env.detect_opencode() is False
    assert host_env.detect_codex() is False
    assert host_env.detect_cursor() is False


def _install_fake_validator(validators_root, name):
    """Cria um validator stub executável no diretório que ingest resolve via
    forge_home()/validators — necessário pro `v_path.is_file()` guard passar e
    o subprocess.run ser realmente alcançado."""
    validators_root.mkdir(parents=True, exist_ok=True)
    (validators_root / f"{name}.py").write_text("print('{}')\n")


def _make_run_spy():
    """subprocess.run spy que captura o env de TODOS os spawns (lista)."""
    captured: dict[str, list] = {"envs": []}

    def _fake_run(cmd, **kwargs):
        captured["envs"].append(kwargs.get("env"))

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""

        return _R()

    return _fake_run, captured


_HOST_KEYS = ("CLAUDECODE", "OPENCODE_VERSION", "CODEX_CLI", "CURSOR_AGENT",
              "FORGE_FORCE_INTENT_MODE", "FORGE_FORCE_TTY_MODE")


def _assert_no_host_keys(env):
    assert env is not None, "ingest deve passar env= explícito ao subprocesso"
    for k in _HOST_KEYS:
        assert k not in env, f"{k} vazou pro env do subprocesso de ingest"


def test_post_subagent_validate_spawns_with_scrubbed_env(tmp_path, monkeypatch):
    """Spawn-site real ingest.py:377 (_handle_post_subagent_validate) passa
    env= sem nenhum sinal de host agêntico."""
    import subprocess

    from engine import ingest

    for k in _HOST_KEYS:
        monkeypatch.setenv(k, "1")

    # forge_home()/validators é onde _handle_post_subagent_validate resolve os
    # validators. 'feature-intake' mapeia pra ['validate_feature_package'].
    forge_root = tmp_path / "forge_home"
    _install_fake_validator(forge_root / "validators", "validate_feature_package")
    monkeypatch.setattr(ingest, "forge_home", lambda: forge_root)

    fake_run, captured = _make_run_spy()
    monkeypatch.setattr(subprocess, "run", fake_run)

    ingest._handle_post_subagent_validate(
        {"subagent": "feature-intake", "task-id": "TASK-0001"},
        tmp_path,
    )

    assert captured["envs"], "o spawn real não foi alcançado — wire não exercitado"
    for env in captured["envs"]:
        _assert_no_host_keys(env)


def test_ci_pr_ingest_spawns_with_scrubbed_env(tmp_path, monkeypatch):
    """Spawn-site real ingest.py:442 (_handle_ci_pr_ingest) passa env= sem
    nenhum sinal de host agêntico."""
    import subprocess

    from engine import ingest

    for k in _HOST_KEYS:
        monkeypatch.setenv(k, "1")

    # _CI_VALIDATORS é uma tupla fixa; instala todos pra os spawns serem
    # alcançados (cada v_path.is_file() precisa existir).
    forge_root = tmp_path / "forge_home"
    for v_name in ingest._CI_VALIDATORS:
        _install_fake_validator(forge_root / "validators", v_name)
    monkeypatch.setattr(ingest, "forge_home", lambda: forge_root)

    fake_run, captured = _make_run_spy()
    monkeypatch.setattr(subprocess, "run", fake_run)

    ingest._handle_ci_pr_ingest(
        {"feature-slug": "auth-login", "pr-number": "42"},
        tmp_path,
    )

    assert captured["envs"], "o spawn real não foi alcançado — wire não exercitado"
    for env in captured["envs"]:
        _assert_no_host_keys(env)
