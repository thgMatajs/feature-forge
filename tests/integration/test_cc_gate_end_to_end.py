"""End-to-end integration tests for the cc-gate.

Each test wires the validator into a temp git repo, stages fixture files,
and exercises one of the 5 spec §5 integration scenarios. Per-language
smoke tests are guarded by ``@pytest.mark.skipif`` so the suite remains
green on machines without all 4 native CC tools.

Scenarios:
    1. cascade_position_correct  — CC validator sits right after
       check_no_invented_behavior in the default cascade.
    2. fail_fast_skips_cc        — earlier validator failing under
       fail_fast=True must mark CC gate as ``skipped``.
    3. per_task_fail_blocks      — staging a high-CC Python file with no
       override yields status=fail and the canonical 3-paths block.
    4. override_permits_commit   — ``CC-OVERRIDE:`` line in commit body
       silences a specific (file, func) and lets the gate pass.
    5. smoke_per_language        — parametric per-language pipeline,
       skipif when the tool isn't on PATH.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "cc_gate"

pytestmark = pytest.mark.integration


def _git_init(repo: Path) -> None:
    """Initialize a temp repo with a single empty commit so HEAD exists."""
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@forge.local"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "forge-test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)
    (repo / ".gitkeep").write_text("", encoding="utf-8")
    subprocess.run(["git", "add", ".gitkeep"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)


def _stage(repo: Path, rel_path: str, content: str) -> None:
    """Write `content` to `rel_path` and `git add` it."""
    p = repo / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", rel_path], cwd=repo, check=True)


def _setup_workflow_config(repo: Path, cc_block: dict | None = None) -> None:
    """Write a minimal `.claude/workflow-config.yaml` enabling cc-gate."""
    import yaml

    (repo / ".claude").mkdir(exist_ok=True)
    cfg = {
        "schema-version": 1,
        "identity": {"project-slug": "test", "preset": "kmp-mobile"},
        "cards": {"active": []},
        "cc-gate": cc_block or {"enabled": True, "kotlin": 10, "python": 10},
    }
    (repo / ".claude" / "workflow-config.yaml").write_text(
        yaml.safe_dump(cfg), encoding="utf-8"
    )


def _import_validator():
    """Import check_cyclomatic_complexity, ensuring validators/ is on sys.path.

    conftest.py already adds it for the suite, but we re-assert here so the
    file can be invoked stand-alone (e.g. ``pytest <file>::<test>``).
    """
    validators_dir = Path(__file__).resolve().parents[2] / "validators"
    if str(validators_dir) not in sys.path:
        sys.path.insert(0, str(validators_dir))
    import check_cyclomatic_complexity as v
    return v


# ── Scenario 1: cascade position ────────────────────────────────────────────


def test_verify_cascade_position(tmp_path: Path) -> None:
    """CC gate is listed AFTER check_no_invented_behavior in the default cascade."""
    from engine import verify

    specs = verify._default_validator_specs(tmp_path)
    names = [s.name for s in specs]
    assert "check_cyclomatic_complexity" in names, (
        "cc gate must be registered in the default validator cascade"
    )
    assert "check_no_invented_behavior" in names, (
        "expected check_no_invented_behavior to anchor the cascade"
    )
    assert (
        names.index("check_cyclomatic_complexity")
        == names.index("check_no_invented_behavior") + 1
    ), f"cc gate must follow check_no_invented_behavior; got order {names}"


# ── Scenario 2: fail-fast ───────────────────────────────────────────────────


def test_cascade_failfast_skips_cc_when_earlier_validator_fails(
    tmp_path: Path, monkeypatch
) -> None:
    """fail_fast=True + earlier fail ⇒ CC gate result.status == 'skipped'."""
    from engine import verify

    captured: list[str] = []

    def fake_invoke(spec, root):
        captured.append(spec.name)
        if spec.name == "check_no_invented_behavior":
            return verify._ValidatorResult(
                name=spec.name, status="fail", duration_ms=1
            )
        return verify._ValidatorResult(
            name=spec.name, status="pass", duration_ms=1
        )

    monkeypatch.setattr(verify, "_invoke_validator", fake_invoke)
    specs = verify._default_validator_specs(tmp_path)
    results = verify._run_cascade(
        specs, fail_fast=True, project_root=tmp_path, interactive=False
    )
    cc = next(r for r in results if r.name == "check_cyclomatic_complexity")
    assert cc.status == "skipped", (
        f"cc gate must be skipped after earlier fail in fail-fast cascade; got {cc.status}"
    )
    # And the CC gate was NOT actually invoked.
    assert "check_cyclomatic_complexity" not in captured, (
        "fail-fast must not even invoke the CC gate after an earlier fail"
    )


# ── Scenario 3: per-task fail blocks commit instructions ────────────────────


@pytest.mark.skipif(shutil.which("radon") is None, reason="radon not installed")
def test_per_task_fail_blocks_commit(tmp_path: Path) -> None:
    """High-CC Python staged without override → fail with the 3-paths block."""
    _git_init(tmp_path)
    _setup_workflow_config(tmp_path)
    _stage(
        tmp_path,
        "engine/parser/lexer.py",
        (FIXTURES / "python_high_cc.py").read_text(encoding="utf-8"),
    )

    v = _import_validator()
    result = v.validate(tmp_path)

    assert result["status"] == "fail", (
        f"expected fail when staging python_high_cc.py; got {result}"
    )
    # result_fail enforces exactly 3 paths via _common.result_fail; assert it
    # propagated end-to-end.
    assert len(result["paths"]) == 3, (
        f"discipline §1 requires exactly 3 paths; got {len(result['paths'])}"
    )


# ── Scenario 4: override-justify permits commit ─────────────────────────────


@pytest.mark.skipif(shutil.which("radon") is None, reason="radon not installed")
def test_override_permits_commit(tmp_path: Path) -> None:
    """CC-OVERRIDE: line in commit body silences a specific (file, func)."""
    _git_init(tmp_path)
    _setup_workflow_config(tmp_path)
    _stage(
        tmp_path,
        "engine/parser/lexer.py",
        (FIXTURES / "python_high_cc.py").read_text(encoding="utf-8"),
    )
    # Simulate pre-commit hook populating COMMIT_EDITMSG with an override.
    # Note: U+2014 em-dash is load-bearing — the strict regex requires it.
    (tmp_path / ".git" / "COMMIT_EDITMSG").write_text(
        "feat(parser): tokenizer\n\n"
        "CC-OVERRIDE: engine/parser/lexer.py:tokenize cc=13 — state machine irreducible\n",
        encoding="utf-8",
    )

    v = _import_validator()
    result = v.validate(tmp_path)
    assert result["status"] in ("pass", "warn"), (
        f"override must silence the only violation; got {result}"
    )


# ── Scenario 5: per-language smoke (skip when tool missing) ─────────────────


@pytest.mark.parametrize(
    "language,tool,fixture,target_file",
    [
        ("kotlin", "detekt", "kotlin_high_cc.kt", "app/HighCC.kt"),
        ("swift", "swiftlint", "swift_high_cc.swift", "ios/HighCC.swift"),
        ("ts", "eslint", "ts_high_cc.ts", "src/highCC.ts"),
        ("python", "radon", "python_high_cc.py", "engine/parser/lexer.py"),
    ],
)
def test_smoke_per_language_high_cc(
    language: str,
    tool: str,
    fixture: str,
    target_file: str,
    tmp_path: Path,
) -> None:
    """Per-language pipeline smoke. Skips when the native tool isn't on PATH."""
    if shutil.which(tool) is None:
        pytest.skip(f"{tool} not installed in test environment")

    _git_init(tmp_path)
    _setup_workflow_config(tmp_path)
    _stage(
        tmp_path,
        target_file,
        (FIXTURES / fixture).read_text(encoding="utf-8"),
    )

    v = _import_validator()
    result = v.validate(tmp_path)
    assert result["status"] in ("fail", "warn", "pass"), (
        f"unexpected status from {language} pipeline: {result.get('status')!r}"
    )
    if result["status"] == "fail":
        # Same 3-paths invariant: discipline §1 / _common.result_fail.
        assert len(result["paths"]) == 3, (
            f"{language} fail result must carry exactly 3 paths"
        )
