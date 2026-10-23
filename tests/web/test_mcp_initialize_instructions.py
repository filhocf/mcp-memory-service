# Copyright 2024 Heinrich Krupp
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""RED tests for SPEC-F006: `instructions` in the MCP HTTP `initialize` result.

Requirements covered: R1 (field present), R2 (doctrine content), R3 (size
budget), R4 (suppression switch), R5 (stability), R6 (protocol shape).

These tests are expected to FAIL on the pre-implementation tree: the
`initialize` result has no `instructions` key (KeyError/assert), not a
collection or import error. The module under test
(`mcp_memory_service.web.api.mcp_instructions`) does not exist yet, so it is
imported lazily inside the test bodies.
"""

import importlib
import os
import tempfile

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from mcp_memory_service.storage.sqlite_vec import SqliteVecMemoryStorage
from mcp_memory_service.web.dependencies import set_storage

INSTRUCTIONS_MODULE = "mcp_memory_service.web.api.mcp_instructions"
DISABLE_ENV = "MCP_DISABLE_INSTRUCTIONS"
MAX_INSTRUCTIONS_CHARS = 1200

INITIALIZE_PAYLOAD = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1"},
    },
}


# ---------------------------------------------------------------------------
# Fixtures — copied from tests/web/api/test_jsonrpc_endpoint.py so this file
# does not depend on (or modify) that module.
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "test.db")


@pytest_asyncio.fixture
async def initialized_storage(temp_db, monkeypatch):
    monkeypatch.setenv("MCP_SEMANTIC_DEDUP_ENABLED", "false")
    storage = SqliteVecMemoryStorage(temp_db)
    await storage.initialize()
    yield storage
    await storage.close()


@pytest.fixture
def test_app(initialized_storage, monkeypatch):
    # Patch module-level auth config directly instead of reloading modules
    # (see test_jsonrpc_endpoint.py for the rationale).
    from mcp_memory_service.web.oauth import middleware

    monkeypatch.setattr(middleware, "API_KEY", None)
    monkeypatch.setattr(middleware, "OAUTH_ENABLED", False)
    monkeypatch.setattr(middleware, "ALLOW_ANONYMOUS_ACCESS", True)

    # The switch is read per request, so the ambient value must not leak in.
    monkeypatch.delenv(DISABLE_ENV, raising=False)

    from mcp_memory_service.web.api import mcp as mcp_api
    from mcp_memory_service.web.app import app
    from mcp_memory_service.web.oauth.middleware import (
        AuthenticationResult,
        get_current_user,
        require_read_access,
    )

    set_storage(initialized_storage)

    # Drop any singleton MemoryServer built by an earlier test so it cannot
    # point at a closed storage.
    monkeypatch.setattr(mcp_api, "_memory_server", None)

    async def mock_user():
        return AuthenticationResult(
            authenticated=True,
            client_id="test",
            scope="read write admin",
            auth_method="test",
        )

    app.dependency_overrides[get_current_user] = mock_user
    app.dependency_overrides[require_read_access] = mock_user

    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def _initialize(test_app):
    """POST `initialize` and return the JSON-RPC result object."""
    response = test_app.post("/mcp", json=INITIALIZE_PAYLOAD)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["jsonrpc"] == "2.0"
    return body["result"]


def _instructions_module():
    """Import the module under test, failing the test (not collection)."""
    try:
        return importlib.import_module(INSTRUCTIONS_MODULE)
    except ImportError as exc:  # pragma: no cover - RED on the current tree
        pytest.fail(
            f"{INSTRUCTIONS_MODULE} is not importable yet "
            f"(SPEC-F006 section 5.1): {exc}"
        )


# ---------------------------------------------------------------------------
# R1 — field present
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_initialize_includes_non_empty_instructions(test_app):
    """R1 / AC2: `result.instructions` is a non-empty string."""
    result = _initialize(test_app)

    assert "instructions" in result, (
        "initialize result must include `instructions` (SPEC-F006 R1); "
        f"got keys: {sorted(result)}"
    )
    instructions = result["instructions"]
    assert isinstance(instructions, str)
    assert instructions.strip(), "instructions must not be blank"


# ---------------------------------------------------------------------------
# R3 — size budget
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_instructions_respect_size_budget(test_app):
    """R3 / AC2: the text is at most 1200 characters."""
    instructions = _initialize(test_app)["instructions"]

    assert len(instructions) <= MAX_INSTRUCTIONS_CHARS, (
        f"instructions is {len(instructions)} chars, budget is "
        f"{MAX_INSTRUCTIONS_CHARS} (SPEC-F006 R3)"
    )


# ---------------------------------------------------------------------------
# R2 — doctrine content
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_instructions_cover_doctrine(test_app):
    """R2: search-first, cheap reads, what to store, transport-supplied agent_id."""
    instructions = _initialize(test_app)["instructions"]
    lowered = instructions.lower()

    assert "memory_search" in instructions, "must name the memory_search tool"

    # Cheap-read limits.
    assert "limit" in lowered, "must mention the `limit` read knob"
    assert "max_response_chars" in instructions, (
        "must mention the `max_response_chars` read budget"
    )

    # Storage guidance: what is worth persisting.
    assert any(word in lowered for word in ("store", "stored", "persist")), (
        "must give storage guidance (`store`)"
    )
    assert "decision" in lowered, "must mention storing decisions"
    assert any(word in lowered for word in ("procedure", "runbook", "how-to")), (
        "must mention storing procedures"
    )

    # agent_id comes from the transport/harness, not the model.
    assert "agent_id" in lowered, "must mention `agent_id`"
    assert any(word in lowered for word in ("transport", "harness")), (
        "must say agent_id comes from the transport/harness"
    )
    assert "invent" in lowered, "must forbid inventing an agent_id"


# ---------------------------------------------------------------------------
# R5 — stability + module contract
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_instructions_are_byte_identical_across_calls(test_app):
    """R5 / AC3: two calls in the same process return identical strings."""
    first = _initialize(test_app)["instructions"]
    second = _initialize(test_app)["instructions"]

    assert first.encode("utf-8") == second.encode("utf-8"), (
        "instructions must be a module constant, not generated per request"
    )


def test_instructions_module_exposes_constant_and_switch(monkeypatch):
    """R5: `MCP_INSTRUCTIONS` is a str and `instructions_enabled()` toggles."""
    module = _instructions_module()

    assert isinstance(getattr(module, "MCP_INSTRUCTIONS", None), str), (
        "mcp_instructions must expose MCP_INSTRUCTIONS as a str"
    )
    assert getattr(module, "MCP_INSTRUCTIONS"), "MCP_INSTRUCTIONS must not be empty"

    enabled = getattr(module, "instructions_enabled", None)
    assert callable(enabled), "mcp_instructions must expose instructions_enabled()"

    monkeypatch.delenv(DISABLE_ENV, raising=False)
    assert enabled() is True, "instructions_enabled() must default to True"

    monkeypatch.setenv(DISABLE_ENV, "1")
    assert enabled() is False, "instructions_enabled() must honor the switch"

    monkeypatch.setenv(DISABLE_ENV, "0")
    assert enabled() is True, "instructions_enabled() must treat `0` as enabled"


@pytest.mark.integration
def test_response_text_matches_module_constant(test_app):
    """R5: the endpoint returns the module constant verbatim."""
    instructions = _initialize(test_app)["instructions"]
    module = _instructions_module()

    assert instructions == module.MCP_INSTRUCTIONS, (
        "the endpoint must return MCP_INSTRUCTIONS unchanged"
    )


# ---------------------------------------------------------------------------
# R4 — suppression switch
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_suppressing_env_values_omit_instructions(test_app, monkeypatch):
    """R4 / AC4: `1`, `true`, `TRUE`, padded `1` omit the field entirely."""
    disabled_values = ["1", "true", "TRUE", " 1 "]

    for value in disabled_values:
        monkeypatch.setenv(DISABLE_ENV, value)
        result = _initialize(test_app)
        assert "instructions" not in result, (
            f"{DISABLE_ENV}={value!r} must omit result.instructions; "
            f"got: {result.get('instructions')!r}"
        )


@pytest.mark.integration
def test_enabling_env_values_keep_instructions(test_app, monkeypatch):
    """R4: `0`, `false`, empty and unset keep the field present."""
    enabled_values = ["0", "false", ""]

    for value in enabled_values:
        monkeypatch.setenv(DISABLE_ENV, value)
        assert "instructions" in _initialize(test_app), (
            f"{DISABLE_ENV}={value!r} must keep result.instructions"
        )

    monkeypatch.delenv(DISABLE_ENV, raising=False)
    assert "instructions" in _initialize(test_app), (
        f"unset {DISABLE_ENV} must keep result.instructions"
    )


# ---------------------------------------------------------------------------
# R6 — protocol shape preserved
# ---------------------------------------------------------------------------

BASE_SHAPE = {
    "protocolVersion": "2024-11-05",
    "capabilities": {"tools": {}},
    "serverInfo": {"name": "mcp-memory-service"},
}


def _assert_base_shape(result):
    assert result["protocolVersion"] == BASE_SHAPE["protocolVersion"]
    assert result["capabilities"] == BASE_SHAPE["capabilities"]

    server_info = result["serverInfo"]
    assert set(server_info) == {"name", "version"}, (
        f"serverInfo must keep name+version, got: {sorted(server_info)}"
    )
    assert server_info["name"] == BASE_SHAPE["serverInfo"]["name"]
    assert isinstance(server_info["version"], str) and server_info["version"], (
        "serverInfo.version must be a non-empty string"
    )


@pytest.mark.integration
def test_shape_preserved_with_instructions(test_app):
    """R6 / AC5: adding `instructions` changes nothing else."""
    result = _initialize(test_app)

    assert set(result) == {
        "protocolVersion",
        "capabilities",
        "serverInfo",
        "instructions",
    }, f"unexpected initialize keys: {sorted(result)}"
    _assert_base_shape(result)

    # Deep-equal against the canonical shape once the new field is removed.
    without_instructions = {
        key: value for key, value in result.items() if key != "instructions"
    }
    expected = {
        "protocolVersion": BASE_SHAPE["protocolVersion"],
        "capabilities": BASE_SHAPE["capabilities"],
        "serverInfo": {
            "name": BASE_SHAPE["serverInfo"]["name"],
            "version": without_instructions["serverInfo"]["version"],
        },
    }
    assert without_instructions == expected


@pytest.mark.integration
def test_shape_preserved_without_instructions(test_app, monkeypatch):
    """R6 / AC5: regression guard — suppression leaves the rest untouched."""
    monkeypatch.setenv(DISABLE_ENV, "1")
    result = _initialize(test_app)

    assert "instructions" not in result
    _assert_base_shape(result)

    expected = {
        "protocolVersion": BASE_SHAPE["protocolVersion"],
        "capabilities": BASE_SHAPE["capabilities"],
        "serverInfo": {
            "name": BASE_SHAPE["serverInfo"]["name"],
            "version": result["serverInfo"]["version"],
        },
    }
    assert result == expected
