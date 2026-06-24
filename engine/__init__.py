"""feature-forge — engine package.

Python core for the `forge` CLI. The Bash dispatcher in `bin/forge` does
nothing more than `exec python -m engine.cli "$@"` — everything that matters
lives here.
"""

__version__ = "1.6.1"
__all__ = ["__version__"]
