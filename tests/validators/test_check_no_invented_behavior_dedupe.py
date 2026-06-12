"""M-09 regression: validator must use shared git_staged_files with -M80%.

The local `_git_staged_files` in `validators/check_no_invented_behavior.py`
was a near-duplicate of `_diff.git_staged_files` without rename detection.
This test pins the dedupe: the validator must NOT redefine its own private
helper, and must expose `git_staged_files` imported from `_diff`.
"""

from __future__ import annotations


def test_check_no_invented_behavior_imports_from_diff() -> None:
    """The validator must import git_staged_files from _diff, not redefine it."""
    import importlib

    mod = importlib.import_module("check_no_invented_behavior")
    assert not hasattr(mod, "_git_staged_files"), (
        "validators/check_no_invented_behavior.py still defines a local "
        "_git_staged_files; should import from _diff."
    )
    assert hasattr(mod, "git_staged_files"), (
        "validators/check_no_invented_behavior.py must expose "
        "git_staged_files (imported from _diff) after M-09 dedupe."
    )

    # Source identity: ensure the symbol *is* the shared _diff implementation.
    from _diff import git_staged_files as shared

    assert mod.git_staged_files is shared, (
        "git_staged_files in check_no_invented_behavior must be the same "
        "object as _diff.git_staged_files (shared, with -M80% rename detect)."
    )
