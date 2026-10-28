#!/usr/bin/env python3
"""Install the memory-service as a first-class client of a harness.

Thin adapter over :mod:`mcp_memory_service.installers.core` — the logic lives in
the package so a wheel installed from PyPI ships it (SPEC-F007 R2/R6). This file
keeps the script entry point working for checkouts and cron lines that call it
by path.

Usage:
    python scripts/harness/instalar.py                      # detect and install
    python scripts/harness/instalar.py --dry-run            # print the plan only
    python scripts/harness/instalar.py --harness kiro       # force one harness
    python scripts/harness/instalar.py --root /tmp/sandbox  # ad-hoc sandbox
    python scripts/harness/instalar.py --uninstall
    python scripts/harness/instalar.py --list
"""

from __future__ import annotations

import sys
from pathlib import Path

# A checkout may run this script without the package installed; make the src
# tree importable from this file's location before the delegation import.
_SRC = Path(__file__).resolve().parents[2] / "src"
if _SRC.is_dir():
    sys.path.insert(0, str(_SRC))

from mcp_memory_service.installers import core  # noqa: E402

# Re-export the installer API: the tests (and cron lines) import this module and
# call detect/harnesses/plan_for directly. `main` is deliberately NOT a copy: it
# resolves through `core` at call time, so a test (or wrapper) patching
# `core.main` is seen by every delegate, whatever the import order.
globals().update(
    {
        name: getattr(core, name)
        for name in dir(core)
        if not name.startswith("_") and name != "main"
    }
)


def main(argv: list[str] | None = None) -> int:
    """Delegate to the packaged installer's entry point."""
    return core.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) or 0)
