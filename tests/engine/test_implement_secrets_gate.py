"""Tests for the secrets-gate per-task hook integration in engine.implement.

Sub-Task 5B do check_secrets plan: `engine/implement.py` invoca o validator
``check_secrets.validate`` (stage="per_task" → gitleaks) como chamada
in-process entre Review e Commit. O hook surfaca um bloco 3-paths em fail
e respeita ``NO_SECRETS_GATE=1`` como bypass auditado.

Contract:

- ``_run_secrets_gate(project_root)`` retorna dict ``{"status": ..., ...,
  "blocking": bool}``. ``blocking`` é True iff o gate falhou hard.
- ``NO_SECRETS_GATE=1`` → ``{"status": "warn", "blocking": False}`` E
  append em ``.claude/state/secrets-gate-bypass.jsonl`` (path via
  ``_secrets_bypass_log_path`` pra teste redirecionar).
- ``validate()`` retorna ``status: "fail"`` → wrapper marca ``blocking=True``.
- ``validate()`` retorna ``status: "pass"`` (override silenciou) → ``blocking=False``.
- ``validate()`` levanta exceção → ``status: "warn"``, ``blocking=False``.
- import do módulo falha → ``status: "warn"``, ``blocking=False``.

Tests fazem stub direto de ``validators.check_secrets`` via ``sys.modules`` —
hermetic, sem git / tools nativas.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

from engine import implement


def test_run_secrets_gate_blocks_on_fail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """validate() → status=fail marca gate como blocking e preserva 3-paths + render."""
    fake_fail = {
        "status": "fail",
        "message": "Check Secrets gate: 2 secret(s) detectado(s)",
        "render": "🛑 Check Secrets gate\n\nO que falhou:\n  2 candidatos…",
        "paths": [
            {"kind": "fix", "label": "Remover e rotacionar", "motive": ""},
            {"kind": "revert", "label": "Override-justify", "motive": ""},
            {"kind": "split", "label": "Marcar como fixture", "motive": ""},
        ],
    }
    monkeypatch.setitem(
        sys.modules,
        "validators.check_secrets",
        mock.MagicMock(validate=lambda root, **kw: fake_fail),
    )
    result = implement._run_secrets_gate(tmp_path)
    assert result["status"] == "fail"
    assert result["blocking"] is True
    assert isinstance(result.get("paths"), list)
    assert len(result["paths"]) == 3
    assert isinstance(result.get("render"), str)


def test_run_secrets_gate_passes_on_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """validate() → status=pass mantém gate não-blocking (override silenciou ou zero findings)."""
    fake_pass = {
        "status": "pass",
        "message": "zero secrets detectados",
    }
    monkeypatch.setitem(
        sys.modules,
        "validators.check_secrets",
        mock.MagicMock(validate=lambda root, **kw: fake_pass),
    )
    result = implement._run_secrets_gate(tmp_path)
    assert result["status"] == "pass"
    assert result["blocking"] is False


def test_run_secrets_gate_calls_validator_with_per_task_stage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Per-task hook deve invocar validate(stage='per_task') — gitleaks branch.

    A cascade roda stage='cascade' (trufflehog); o hook do `forge implement`
    é rápido (regex) → gitleaks. Sem este teste, regredir pro default
    'cascade' passaria silenciosamente.
    """
    captured: dict[str, object] = {}

    def fake_validate(root: Path, **kw: object) -> dict[str, object]:
        captured["root"] = root
        captured["kw"] = kw
        return {"status": "pass", "message": "ok"}

    monkeypatch.setitem(
        sys.modules,
        "validators.check_secrets",
        mock.MagicMock(validate=fake_validate),
    )
    implement._run_secrets_gate(tmp_path)
    assert captured["root"] == tmp_path
    assert captured["kw"].get("stage") == "per_task"


def test_run_secrets_gate_bypassed_by_env_var(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """NO_SECRETS_GATE=1 short-circuits → warn + JSONL audit line."""
    monkeypatch.setenv("NO_SECRETS_GATE", "1")
    bypass_log = tmp_path / ".claude" / "state" / "secrets-gate-bypass.jsonl"
    monkeypatch.setattr(
        implement, "_secrets_bypass_log_path", lambda root: bypass_log
    )

    def _must_not_call(*a: object, **kw: object) -> dict[str, object]:
        raise AssertionError("validator must not run when NO_SECRETS_GATE=1")

    monkeypatch.setitem(
        sys.modules,
        "validators.check_secrets",
        mock.MagicMock(validate=_must_not_call),
    )

    result = implement._run_secrets_gate(tmp_path)
    assert result["status"] == "warn"
    assert result["blocking"] is False
    assert bypass_log.is_file(), "bypass log file must be created"
    contents = bypass_log.read_text(encoding="utf-8")
    assert "NO_SECRETS_GATE" in contents
    # JSONL discipline — one record per bypass invocation.
    assert contents.strip().count("\n") == 0
    assert contents.endswith("\n")


def test_run_secrets_gate_handles_import_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Import do validator falha → warn (não blocking) — engine boot é resiliente.

    Exercita de fato o branch ``except ImportError`` do
    ``from validators import check_secrets`` em ``_run_secrets_gate``.
    Pra isso, forçamos o próprio import a levantar ``ImportError`` (não o
    ``.validate()``, que cairia no branch ``except Exception`` — esse caminho
    é coberto por ``test_run_secrets_gate_handles_validator_crash``).

    A âncora ``"import failed" in message`` garante que estamos no branch
    certo: o branch de import diz "import failed", o de crash diz "crashed".
    """
    import builtins

    real_import = builtins.__import__

    def boom(name: str, *args: object, **kwargs: object):
        # `from validators import check_secrets` chega aqui como
        # name="validators" com "check_secrets" na fromlist (4º posicional).
        fromlist = args[2] if len(args) >= 3 else kwargs.get("fromlist")
        if name == "validators" and fromlist and "check_secrets" in fromlist:
            raise ImportError("simulated: validators.check_secrets indisponível")
        if name == "validators.check_secrets":
            raise ImportError("simulated: validators.check_secrets indisponível")
        return real_import(name, *args, **kwargs)

    # Limpa cache pra garantir que o import realmente reexecute e bata no boom.
    monkeypatch.delitem(sys.modules, "validators.check_secrets", raising=False)
    monkeypatch.setattr(builtins, "__import__", boom)

    result = implement._run_secrets_gate(tmp_path)
    assert result["status"] == "warn"
    assert result["blocking"] is False
    assert "import failed" in result["message"], (
        "deve ancorar no branch de import-fail, não no de crash; "
        f"got {result['message']!r}"
    )


def test_run_secrets_gate_handles_validator_crash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """validate() levanta → warn (não blocking) com a mensagem do exc."""
    fake_module = mock.MagicMock()
    fake_module.validate.side_effect = RuntimeError("boom — disk read failed")
    monkeypatch.setitem(
        sys.modules, "validators.check_secrets", fake_module
    )
    result = implement._run_secrets_gate(tmp_path)
    assert result["status"] == "warn"
    assert result["blocking"] is False
    assert "boom" in result.get("message", "") or "boom" in str(
        result.get("message", "")
    )


def test_run_secrets_gate_handles_non_dict_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """validate() retorna non-dict → warn (defensivo)."""
    monkeypatch.setitem(
        sys.modules,
        "validators.check_secrets",
        mock.MagicMock(validate=lambda root, **kw: "not a dict"),
    )
    result = implement._run_secrets_gate(tmp_path)
    assert result["status"] == "warn"
    assert result["blocking"] is False


def test_render_secrets_gate_block_uses_canonical_render(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_render_secrets_gate_block` surfaca o canonical render quando presente.

    Spec §3 + disciplines §1: header literal `🛑 Check Secrets gate` e o
    bloco "Três caminhos pra resolver" são load-bearing UX — sem este
    teste, o render correto poderia nunca chegar ao usuário.
    """
    captured: list[str] = []
    monkeypatch.setattr(
        implement.renderer,
        "write",
        lambda line="": captured.append(str(line)),
    )
    monkeypatch.setattr(implement.renderer, "bold", lambda s: s)
    monkeypatch.setattr(implement.renderer, "dim", lambda s: s)

    canonical = (
        "🛑 Check Secrets gate\n"
        "\n"
        "O que falhou:\n"
        "  2 candidatos a secret detectados em arquivos staged.\n"
        "\n"
        "Três caminhos pra resolver:\n"
        "\n"
        "  1) Remover e rotacionar\n"
    )
    fake_fail = {
        "status": "fail",
        "message": "Check Secrets gate: 2 secret(s)",
        "render": canonical,
        "paths": [
            {"kind": "fix", "label": "Remover", "motive": ""},
            {"kind": "revert", "label": "Override", "motive": ""},
            {"kind": "split", "label": "Fixture", "motive": ""},
        ],
    }
    implement._render_secrets_gate_block(fake_fail)
    out = "\n".join(captured)
    assert "🛑 Check Secrets gate" in out, (
        f"canonical header missing in render output; got:\n{out}"
    )
    assert "Três caminhos pra resolver" in out


def test_apply_mode_handoff_blocks_when_secrets_gate_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Integração `_apply_mode_handoff`: CC ok + secrets fail → handoff aborta.

    Garante que secrets bloqueia mesmo quando CC passou (gates agrupados).
    """
    captured: list[str] = []
    monkeypatch.setattr(
        implement.renderer,
        "write",
        lambda line="": captured.append(str(line)),
    )
    monkeypatch.setattr(implement.renderer, "bold", lambda s: s)
    monkeypatch.setattr(implement.renderer, "dim", lambda s: s)

    monkeypatch.setattr(
        implement,
        "_run_cc_gate",
        lambda root: {"status": "pass", "blocking": False},
    )
    monkeypatch.setattr(
        implement,
        "_run_secrets_gate",
        lambda root: {
            "status": "fail",
            "blocking": True,
            "message": "Check Secrets gate: 1 secret",
            "render": (
                "🛑 Check Secrets gate\n\n"
                "Três caminhos pra resolver:\n\n  1) Remover\n"
            ),
            "paths": [
                {"kind": "fix", "label": "Remover", "motive": ""},
                {"kind": "revert", "label": "Override", "motive": ""},
                {"kind": "split", "label": "Fixture", "motive": ""},
            ],
        },
    )

    task = implement.TaskContract(
        task_id="TASK-0001",
        path=tmp_path / "task.yaml",
        description="dummy",
        allowed_files=[],
        validations=[],
        gates=[],
        dependencies=[],
        bdd_scenarios=[],
        status="ready",
        raw={},
    )
    implement._apply_mode_handoff(task, slug="dummy", project_root=tmp_path)

    out = "\n".join(captured)
    assert "🛑 Check Secrets gate" in out, (
        "secrets gate render ausente — handoff não bloqueou"
    )
    # Mensagem de instrução de commit NÃO deve aparecer (handoff returna)
    assert "1) forge verify" not in out, (
        "handoff emitiu commit-instructions apesar do secrets fail"
    )
