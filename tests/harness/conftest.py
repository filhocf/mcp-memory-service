"""Fixtures for the isolated lab — SPEC-F008 §5.1.

The service is REAL and module-scoped (booted once per module, isolated
database), each test gets a fresh sandboxed XDG tree. R1 applies to the test
process as well: `lab()` monkeypatches HOME/XDG before the installer or the
real client resolves any user path.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import lab as lab_module  # noqa: E402 — the module; the fixture named `lab` would shadow it


@pytest.fixture(scope="module")
def mms_service(tmp_path_factory: pytest.TempPathFactory):
    """The real service instance: free port, DB under the test tree."""
    handle = lab_module.boot_service(tmp_path_factory.mktemp("mms-lab-service"))
    try:
        yield handle
    finally:
        if handle.process.poll() is None:
            handle.process.terminate()
            try:
                handle.process.wait(timeout=10)
            except Exception:  # noqa: BLE001
                handle.process.kill()


@pytest.fixture
def lab(mms_service, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "home"
    # Measured (OpenCode 2.1.3): the client resolves its config from
    # $HOME/.config/opencode and ignores XDG_CONFIG_HOME — so the sandbox
    # keeps the XDG vars coherent under HOME instead of pointing elsewhere.
    config_home = home / ".config"
    data_home = home / ".local" / "share"
    state_home = home / ".local" / "state"
    for directory in (home, config_home, data_home, state_home):
        directory.mkdir(parents=True, exist_ok=True)

    # R1: every user path the lab process resolves lives under tmp_path.
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.setenv("XDG_STATE_HOME", str(state_home))

    return lab_module.Lab(
        home=home,
        config_home=config_home,
        data_home=data_home,
        state_home=state_home,
        root=config_home / "opencode",
        port=mms_service.port,
    )
