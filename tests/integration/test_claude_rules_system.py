"""Integration test for the Claude Code rules system.

Validates structural integrity of CLAUDE.md, .claude/rules/, .claude/hooks/,
settings.json, bootstrap script, and gitignore patterns.

Marker: integration (excluded from rapid lane).
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RULES_DIR = REPO_ROOT / ".claude" / "rules"
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"
STATE_DIR = REPO_ROOT / ".claude" / "state"

EXPECTED_RULES = [
    "README.md",
    "orchestrator-persona.md",
    "subagent-workflow.md",
    "decisions.md",
    "disciplines.md",
    "testing.md",
    "scope.md",
    "reuse.md",
    "superpowers.md",
    "doc-sync.md",
    "plan-auditor.md",
    "project-anatomy.md",
    "SMOKE-CHECKLIST.md",
]

EXPECTED_HOOKS = [
    "session-start-orientation.sh",
    "pre-tool-use-load-bearing.sh",
    "post-edit-doc-drift.sh",
    "pre-commit-feature-forge.sh",
]


pytestmark = pytest.mark.integration


# ───────────────────────────────────── structure


def test_claude_md_root_exists():
    assert (REPO_ROOT / "CLAUDE.md").exists()


def test_settings_json_exists_and_parses():
    path = REPO_ROOT / ".claude" / "settings.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert "hooks" in data
    assert "SessionStart" in data["hooks"]
    assert "PreToolUse" in data["hooks"]
    assert "PostToolUse" in data["hooks"]


def test_bootstrap_script_exists_and_executable():
    path = REPO_ROOT / ".claude" / "bootstrap.sh"
    assert path.exists()
    assert os.access(path, os.X_OK), "bootstrap.sh must be executable"


def test_state_dir_has_gitkeep():
    assert (STATE_DIR / ".gitkeep").exists()


# ───────────────────────────────────── rules


@pytest.mark.parametrize("rule_name", EXPECTED_RULES)
def test_rule_file_exists_with_h1(rule_name):
    path = RULES_DIR / rule_name
    assert path.exists(), f"missing rule: {rule_name}"
    content = path.read_text()
    assert re.match(r"^#\s+\S", content), f"{rule_name} must start with H1"


def _claude_md_references_rule(claude_md: str, rule_name: str) -> bool:
    """True if CLAUDE.md references the rule via an UNAMBIGUOUS literal.

    Deliberately path-anchored (`.claude/rules/<rule>`) or a real markdown
    link to the rule file — NOT a bare basename substring. The bare-substring
    form is what produced the historic false-positive where ``decisions.md``
    matched ``docs/design/01-decisions.md``; anchoring to the rules path or a
    link target eliminates it.
    """
    stem = rule_name[:-3] if rule_name.endswith(".md") else rule_name
    patterns = [
        rf"\.claude/rules/{re.escape(rule_name)}\b",      # full path to file
        rf"\.claude/rules/{re.escape(stem)}\b",           # full path, stem only
        rf"\]\([^)]*{re.escape(rule_name)}\)",            # markdown link target
    ]
    return any(re.search(p, claude_md) for p in patterns)


def _readme_index_rules(readme: str) -> set[str]:
    """Parse the `.claude/rules/README.md` Map table into a set of indexed
    rule stems (basename without `.md`).

    STRUCTURAL parse — a rule counts as indexed only if it appears as the
    FIRST-COLUMN cell of a genuine table row (``| <rule> | ... |``) or as a
    markdown link target inside any table cell. A bare mention elsewhere in
    the prose does NOT count, so a non-indexed rule genuinely fails.
    """
    indexed: set[str] = set()
    for line in readme.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "|" not in stripped[1:]:
            continue  # not a table row
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not cells:
            continue
        first = cells[0]
        # Skip header / separator rows.
        if not first or first.lower() == "rule" or set(first) <= {"-", ":", " "}:
            continue
        # First cell as a literal stem (the canonical form: `| orchestrator-persona |`).
        # Normalise away any markdown emphasis/backticks/link wrappers.
        bare = re.sub(r"[`*_]", "", first).strip()
        link_match = re.match(r"\[([^\]]+)\]\([^)]+\)", bare)
        if link_match:
            bare = link_match.group(1).strip()
        if bare:
            indexed.add(bare[:-3] if bare.endswith(".md") else bare)
        # Also capture any markdown-link targets within the whole row.
        for target in re.findall(r"\]\(([^)]+)\)", stripped):
            base = target.rsplit("/", 1)[-1]
            if base.endswith(".md"):
                indexed.add(base[:-3])
    return indexed


def _rule_is_linked(rule_name: str, claude_md: str, indexed: set[str]) -> bool:
    """The post-Fase-0 invariant for a single rule file.

    README.md is the index itself, so it can never be a row inside its own
    Map table; it is satisfied by being the canonical index file (and it is
    referenced from CLAUDE.md). Every OTHER rule must be either referenced
    unambiguously in CLAUDE.md OR genuinely indexed in the README Map table.
    """
    if rule_name == "README.md":
        return True
    stem = rule_name[:-3] if rule_name.endswith(".md") else rule_name
    return _claude_md_references_rule(claude_md, rule_name) or stem in indexed


@pytest.mark.parametrize("rule_name", EXPECTED_RULES)
def test_rule_file_linked_in_claude_md(rule_name):
    """Post-Fase-0 invariant: every rule file is discoverable.

    On 2026-06-25 (commit cef24d5, "Enxugue Fase 0 mem dogfood") CLAUDE.md
    was deliberately trimmed to Tier-0 only; per-rule detail migrated to the
    `mem` archive and the canonical index moved to `.claude/rules/README.md`
    (the Map table). So the old invariant ("every rule linked literally in
    CLAUDE.md") no longer holds by design.

    The new invariant: each rule file must be EITHER referenced
    unambiguously in CLAUDE.md (path-anchored or a markdown link — never a
    bare-substring match) OR genuinely indexed in the README Map table
    (a real table ROW, parsed structurally — not a loose substring). README.md
    is the index file itself and is satisfied as the canonical index.
    """
    claude_md = (REPO_ROOT / "CLAUDE.md").read_text()
    readme = (RULES_DIR / "README.md").read_text()
    indexed = _readme_index_rules(readme)
    assert _rule_is_linked(rule_name, claude_md, indexed), (
        f"{rule_name} is neither referenced in CLAUDE.md (path-anchored / link) "
        f"nor structurally indexed in .claude/rules/README.md Map table. "
        f"Indexed stems found: {sorted(indexed)}"
    )


def test_expected_rules_matches_disk():
    """EXPECTED_RULES and the on-disk `.claude/rules/*.md` set must be
    identical — guards against a rule file being added/removed without the
    test (and the README index) being kept consistent."""
    on_disk = {p.name for p in RULES_DIR.glob("*.md")}
    assert on_disk == set(EXPECTED_RULES), (
        f"EXPECTED_RULES drifted from disk. "
        f"On disk only: {sorted(on_disk - set(EXPECTED_RULES))}; "
        f"EXPECTED only: {sorted(set(EXPECTED_RULES) - on_disk)}"
    )


def test_readme_index_covers_all_non_readme_rules():
    """The README Map table (canonical index) must cover every non-README
    rule file on disk — the two sources of truth stay consistent."""
    readme = (RULES_DIR / "README.md").read_text()
    indexed = _readme_index_rules(readme)
    expected_stems = {
        r[:-3] for r in EXPECTED_RULES if r != "README.md"
    }
    missing = expected_stems - indexed
    assert not missing, (
        f"rules missing from README Map table index: {sorted(missing)}; "
        f"indexed: {sorted(indexed)}"
    )


def test_linkage_invariant_is_not_near_inert():
    """Anti-near-inert guard (lição C5): a FICTITIOUS, non-indexed rule must
    FAIL the new invariant. Proves the structural check actually rejects
    something rather than passing everything by accident."""
    claude_md = (REPO_ROOT / "CLAUDE.md").read_text()
    readme = (RULES_DIR / "README.md").read_text()
    indexed = _readme_index_rules(readme)
    fake = "totally-fictitious-unindexed-rule.md"
    assert not _rule_is_linked(fake, claude_md, indexed), (
        "near-inert: a fictitious non-indexed rule unexpectedly passed the "
        "linkage invariant — the structural check is not discriminating."
    )
    # And the historic false-positive must now be rejected by the CLAUDE.md
    # arm specifically (it should only pass via the README index, not via a
    # bare-substring CLAUDE.md match against `01-decisions.md`).
    assert not _claude_md_references_rule(claude_md, "decisions.md"), (
        "regression: decisions.md is matching CLAUDE.md via bare substring "
        "(the historic false-positive against 01-decisions.md)."
    )
    assert "decisions" in indexed, (
        "decisions.md should pass the invariant LEGITIMATELY via the README "
        "Map table index, not by accident."
    )


# ───────────────────────────────────── hooks


@pytest.mark.parametrize("hook_name", EXPECTED_HOOKS)
def test_hook_script_exists_executable_valid_bash(hook_name):
    path = HOOKS_DIR / hook_name
    assert path.exists(), f"missing hook: {hook_name}"
    assert os.access(path, os.X_OK), f"{hook_name} must be executable"
    result = subprocess.run(
        ["bash", "-n", str(path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"{hook_name} bash syntax error: {result.stderr}"


# ───────────────────────────────────── pre-commit hard block


def test_pre_commit_hard_blocks_decisions_without_ceremony(tmp_path, monkeypatch):
    """If 01-decisions.md is staged and CHANGELOG.md does NOT contain
    'Revisita decisão', the hook must exit non-zero."""
    hook = HOOKS_DIR / "pre-commit-feature-forge.sh"
    assert hook.exists()

    fake_repo = tmp_path / "fake"
    fake_repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=fake_repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@x"], cwd=fake_repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=fake_repo, check=True)
    (fake_repo / "docs" / "design").mkdir(parents=True)
    (fake_repo / "docs" / "design" / "01-decisions.md").write_text("# fake\n+change\n")
    (fake_repo / "CHANGELOG.md").write_text("# Changelog\n## Unreleased\n- some change\n")
    subprocess.run(["git", "add", "-A"], cwd=fake_repo, check=True)

    # Copy hook into fake repo to allow it to run with that working dir
    fake_hook = fake_repo / "pre-commit-feature-forge.sh"
    shutil.copy(hook, fake_hook)
    os.chmod(fake_hook, 0o755)

    result = subprocess.run(
        ["bash", str(fake_hook)],
        cwd=fake_repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, (
        f"hook should hard-block; got rc={result.returncode}, "
        f"stdout={result.stdout!r}, stderr={result.stderr!r}"
    )
    assert "Revisita decisão" in result.stderr or "BLOCK" in result.stderr


def test_pre_commit_allows_decisions_with_ceremony(tmp_path):
    """If CHANGELOG.md staged includes 'Revisita decisão N', hook must pass."""
    hook = HOOKS_DIR / "pre-commit-feature-forge.sh"

    fake_repo = tmp_path / "fake"
    fake_repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=fake_repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@x"], cwd=fake_repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=fake_repo, check=True)
    (fake_repo / "docs" / "design").mkdir(parents=True)
    (fake_repo / "docs" / "design" / "01-decisions.md").write_text("# fake\n+change\n")
    (fake_repo / "CHANGELOG.md").write_text(
        "# Changelog\n## Unreleased\n- Revisita decisão 22: foo\n"
    )
    subprocess.run(["git", "add", "-A"], cwd=fake_repo, check=True)

    fake_hook = fake_repo / "pre-commit-feature-forge.sh"
    shutil.copy(hook, fake_hook)
    os.chmod(fake_hook, 0o755)

    result = subprocess.run(
        ["bash", str(fake_hook)], cwd=fake_repo, capture_output=True, text=True
    )
    assert result.returncode == 0, f"hook should pass; stderr={result.stderr!r}"


# ───────────────────────────────────── bootstrap idempotency


def test_bootstrap_is_idempotent():
    """Running bootstrap twice produces no diff."""
    bootstrap = REPO_ROOT / ".claude" / "bootstrap.sh"
    # First run
    r1 = subprocess.run(
        ["bash", str(bootstrap)], cwd=REPO_ROOT, capture_output=True, text=True
    )
    assert r1.returncode == 0, f"first run failed: {r1.stderr}"
    # Capture state
    r_status = subprocess.run(
        ["git", "status", "--porcelain", ".claude/"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    state_before = r_status.stdout
    # Second run
    r2 = subprocess.run(
        ["bash", str(bootstrap)], cwd=REPO_ROOT, capture_output=True, text=True
    )
    assert r2.returncode == 0, f"second run failed: {r2.stderr}"
    r_status2 = subprocess.run(
        ["git", "status", "--porcelain", ".claude/"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    state_after = r_status2.stdout
    assert state_before == state_after, "bootstrap is not idempotent"


# ───────────────────────────────────── gitignore


def test_gitignore_covers_state_json():
    """`.claude/state/*.json` must be ignored, but `.gitkeep` must be tracked."""
    # `git check-ignore` accepts non-existent paths — no need to touch the real FS
    result = subprocess.run(
        ["git", "check-ignore", ".claude/state/_probe.json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"state/*.json should be gitignored; rc={result.returncode}"
    )

    result_keep = subprocess.run(
        ["git", "check-ignore", ".claude/state/.gitkeep"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result_keep.returncode != 0, ".gitkeep must NOT be gitignored"
