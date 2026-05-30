"""feature-forge validators — invoked by forge verify, forge doctor, pre-commit hooks.

Each validator is also importable:
    from validators import validate_feature_package
    result = validate_feature_package.validate(project_root)

CLI usage:
    python3 validators/<name>.py --project-root <path> [--scope <task|feature>] [--id <id>]

Output: JSON tail-on-stdout with shape
    {"status": "pass"|"warn"|"fail", "message": ..., "what-failed": ...,
     "where": ..., "why": [...], "paths": [...]}

Exit codes: 0=pass, 1=fail, 2=warn (non-blocking)
"""
