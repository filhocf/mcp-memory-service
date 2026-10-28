"""The plugin's own JavaScript test suite, fired from pytest (SPEC-F005 AC1).

The deposited plugin under opencode/ is JavaScript with a `node --test` suite
in opencode/tests/. When node is installed the JS contract is enforced here
too; without node the test skips — the suite still runs in any CI with node.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = REPO_ROOT / "opencode" / "tests"


def test_opencode_node_suite_passes():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not available")

    scripts = sorted(TESTS_DIR.glob("*.test.js"))
    assert scripts, "the plugin's node test suite is missing"

    result = subprocess.run(
        [node, "--test", *[str(script) for script in scripts]],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"node tests failed:\n{result.stdout}\n{result.stderr}"
    )
