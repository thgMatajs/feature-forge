"""Concrete ``HostAdapter`` implementations.

Re-exports the canonical adapters used by ``engine.host.registry`` and
direct importers. New adapters land here and get wired into the
registry's detection precedence.
"""
from __future__ import annotations

from engine.host.adapters.intent_file import IntentFileAdapter
from engine.host.adapters.tty import TtyAdapter

__all__ = ["IntentFileAdapter", "TtyAdapter"]
