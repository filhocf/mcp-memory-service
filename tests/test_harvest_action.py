"""Tests for action=harvest in memory_consolidate handler.

Tests the on-demand harvest feature including security validation,
error handling, and dry-run functionality.
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_memory_service.server.handlers.consolidation import handle_memory_consolidate


def _run(coro):
    """Run a coroutine in a fresh event loop (Python 3.14 compatible)."""
    return asyncio.run(coro)


def _make_mock_server(storage=None):
    """Create a mock server with optional storage."""
    server = MagicMock()
    server.storage = storage
    return server


def _make_mock_storage():
    """Create a mock storage backend."""
    storage = AsyncMock()
    return storage


class TestHarvestActionBasic:
    """Basic functionality tests for harvest action."""

    def test_harvest_action_no_storage_returns_error(self):
        """Test that harvest action returns error when server.storage is None."""
        server = _make_mock_server(storage=None)
        arguments = {"action": "harvest"}
        
        result = _run(handle_memory_consolidate(server, arguments))
        
        assert len(result) == 1
        assert result[0].type == "text"
        assert "Error: storage not available" in result[0].text

    def test_harvest_action_with_default_path(self):
        """Test that harvest action uses MCP_HARVEST_SESSION_DIR when path is not provided."""
        server = _make_mock_server(storage=_make_mock_storage())
        
        with patch.dict(os.environ, {"MCP_HARVEST_SESSION_DIR": "/test/sessions"}):
            with patch("mcp_memory_service.harvest.harvester.SessionHarvester") as mock_harvester_class:
                with patch("mcp_memory_service.services.memory_service.MemoryService") as mock_ms_class:
                    with patch("mcp_memory_service.harvest.models.HarvestConfig") as mock_config_class:
                        # Setup mocks
                        mock_harvester = MagicMock()
                        mock_harvester.harvest_and_store = AsyncMock(return_value=[])
                        mock_harvester_class.return_value = mock_harvester
                        
                        arguments = {"action": "harvest"}
                        result = _run(handle_memory_consolidate(server, arguments))
                        
                        # Verify SessionHarvester was created with expanded path
                        mock_harvester_class.assert_called_once()
                        call_kwargs = mock_harvester_class.call_args[1]
                        assert call_kwargs["project_dir"] == "/test/sessions"

    def test_harvest_action_dry_run_with_fixture(self, monkeypatch):
        """Test harvest action in dry_run mode with temporary session fixture."""
        server = _make_mock_server(storage=_make_mock_storage())
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Set allowed roots to include our test directory to pass security guard
            monkeypatch.setenv("MCP_HARVEST_ALLOWED_ROOTS", tmpdir)
            
            # Create a test session file in Kiro legacy format
            session_file = Path(tmpdir) / "test_session.jsonl"
            session_data = [
                {"kind": "Prompt", "data": {"content": "Test prompt 1"}},
                {"kind": "Prompt", "data": {"content": "Test prompt 2"}},
            ]
            
            with open(session_file, "w") as f:
                for item in session_data:
                    f.write(json.dumps(item) + "\n")
            
            with patch("mcp_memory_service.harvest.harvester.SessionHarvester") as mock_harvester_class:
                with patch("mcp_memory_service.services.memory_service.MemoryService") as mock_ms_class:
                    with patch("mcp_memory_service.harvest.models.HarvestConfig") as mock_config_class:
                        # Setup mock harvest result
                        mock_result = SimpleNamespace(candidates=["candidate1", "candidate2"], stored=0)
                        mock_harvester = MagicMock()
                        mock_harvester.harvest_and_store = AsyncMock(return_value=[mock_result])
                        mock_harvester_class.return_value = mock_harvester
                        
                        arguments = {
                            "action": "harvest",
                            "path": tmpdir,
                            "dry_run": True,
                            "sessions": 10,
                            "use_llm": False
                        }
                        
                        result = _run(handle_memory_consolidate(server, arguments))
                        
                        assert len(result) == 1
                        assert result[0].type == "text"
                        text = result[0].text
                        assert "Harvest (DRY-RUN)" in text
                        assert f"from {tmpdir}" in text
                        assert "sessions: 1" in text
                        assert "candidates: 2" in text
                        assert "stored: 0" in text

    def test_harvest_action_with_storage(self, monkeypatch):
        """Test harvest action with actual storage (not dry_run)."""
        server = _make_mock_server(storage=_make_mock_storage())
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Set allowed roots to include our test directory to pass security guard
            monkeypatch.setenv("MCP_HARVEST_ALLOWED_ROOTS", tmpdir)
            
            with patch("mcp_memory_service.harvest.harvester.SessionHarvester") as mock_harvester_class:
                with patch("mcp_memory_service.services.memory_service.MemoryService") as mock_ms_class:
                    with patch("mcp_memory_service.harvest.models.HarvestConfig") as mock_config_class:
                        # Setup mock harvest result with stored memories
                        mock_result = SimpleNamespace(candidates=["candidate1"], stored=1)
                        mock_harvester = MagicMock()
                        mock_harvester.harvest_and_store = AsyncMock(return_value=[mock_result])
                        mock_harvester_class.return_value = mock_harvester
                        
                        arguments = {
                            "action": "harvest",
                            "path": tmpdir,
                            "dry_run": False,
                            "use_llm": False
                        }
                        
                        result = _run(handle_memory_consolidate(server, arguments))
                        
                        assert len(result) == 1
                        assert result[0].type == "text"
                        text = result[0].text
                        assert "Harvest (STORED)" in text
                        assert "sessions: 1" in text
                        assert "candidates: 1" in text
                        assert "stored: 1" in text

    def test_harvest_action_missing_harvest_module(self):
        """Test harvest action when harvest module is unavailable."""
        server = _make_mock_server(storage=_make_mock_storage())
        
        with patch("mcp_memory_service.harvest.harvester.SessionHarvester", side_effect=ImportError("No module named 'harvest'")):
            arguments = {"action": "harvest"}
            result = _run(handle_memory_consolidate(server, arguments))
            
            assert len(result) == 1
            assert result[0].type == "text"
            assert "No module named 'harvest'" in result[0].text


class TestHarvestActionSecurity:
    """Security tests for harvest action - path validation vulnerabilities."""

    def test_harvest_action_path_traversal_attack(self):
        """Test that harvest action properly blocks path traversal attacks."""
        server = _make_mock_server(storage=_make_mock_storage())
        
        # These are malicious paths that should be rejected by the security guard
        malicious_paths = [
            "/etc/passwd",  # Absolute path to sensitive file
            "../../etc/passwd",  # Relative path traversal
            "/home/claudio/.ssh",  # User's private keys
            "../../../root",  # Attempt to access root directory
        ]
        
        for malicious_path in malicious_paths:
            with patch("mcp_memory_service.harvest.harvester.SessionHarvester") as mock_harvester_class:
                with patch("mcp_memory_service.services.memory_service.MemoryService"):
                    with patch("mcp_memory_service.harvest.models.HarvestConfig"):
                        mock_harvester = MagicMock()
                        mock_harvester.harvest_and_store = AsyncMock(return_value=[])
                        mock_harvester_class.return_value = mock_harvester
                        
                        arguments = {
                            "action": "harvest",
                            "path": malicious_path,
                            "use_llm": False
                        }
                        
                        result = _run(handle_memory_consolidate(server, arguments))
                        
                        # SECURITY FIX: The path traversal is now properly blocked
                        assert len(result) == 1
                        assert result[0].type == "text"
                        assert "outside allowed roots" in result[0].text
                        
                        # Verify SessionHarvester was NOT called (attack blocked)
                        mock_harvester_class.assert_not_called()

    def test_harvest_action_should_validate_allowed_roots(self):
        """Test that harvest action should implement allowlist validation (currently missing)."""
        server = _make_mock_server(storage=_make_mock_storage())
        
        # This test defines the EXPECTED behavior after the security fix
        with patch.dict(os.environ, {
            "MCP_HARVEST_SESSION_DIR": "~/.kiro/sessions/cli",
            "MCP_HARVEST_ALLOWED_ROOTS": "~/.kiro:/tmp/test_sessions"
        }):
            # Path within allowed roots should succeed
            allowed_path = "/tmp/test_sessions"
            
            with patch("mcp_memory_service.harvest.harvester.SessionHarvester") as mock_harvester_class:
                with patch("mcp_memory_service.services.memory_service.MemoryService"):
                    with patch("mcp_memory_service.harvest.models.HarvestConfig"):
                        mock_harvester = MagicMock()
                        mock_harvester.harvest_and_store = AsyncMock(return_value=[])
                        mock_harvester_class.return_value = mock_harvester
                        
                        arguments = {
                            "action": "harvest",
                            "path": allowed_path,
                            "use_llm": False
                        }
                        
                        result = _run(handle_memory_consolidate(server, arguments))
                        
                        # Currently this will pass because no validation exists
                        # After security fix, this should still pass (allowed path)
                        assert len(result) == 1
                        assert result[0].type == "text"

    def test_harvest_action_symlink_vulnerability(self):
        """Test that harvest action properly blocks symlink attacks after resolve()."""
        server = _make_mock_server(storage=_make_mock_storage())
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a symlink pointing to a sensitive directory
            sensitive_dir = "/etc"  # or any sensitive directory
            symlink_path = Path(tmpdir) / "malicious_link"
            
            try:
                symlink_path.symlink_to(sensitive_dir)
                
                with patch("mcp_memory_service.harvest.harvester.SessionHarvester") as mock_harvester_class:
                    with patch("mcp_memory_service.services.memory_service.MemoryService"):
                        with patch("mcp_memory_service.harvest.models.HarvestConfig"):
                            mock_harvester = MagicMock()
                            mock_harvester.harvest_and_store = AsyncMock(return_value=[])
                            mock_harvester_class.return_value = mock_harvester
                            
                            arguments = {
                                "action": "harvest",
                                "path": str(symlink_path),
                                "use_llm": False
                            }
                            
                            result = _run(handle_memory_consolidate(server, arguments))
                            
                            # SECURITY FIX: With resolve(), symlink attacks are now prevented
                            # The symlink resolves to /etc which is outside allowed roots
                            assert len(result) == 1
                            assert result[0].type == "text"
                            assert "outside allowed roots" in result[0].text
                            
                            # Verify SessionHarvester was NOT called (attack blocked)
                            mock_harvester_class.assert_not_called()
                            
            except (OSError, NotImplementedError):
                # Symlink creation might fail on some systems, skip this test
                pytest.skip("Symlink creation not supported on this system")


class TestHarvestActionParameters:
    """Test parameter validation and default values."""

    def test_harvest_action_parameter_defaults(self, monkeypatch):
        """Test that harvest action uses correct default parameter values."""
        server = _make_mock_server(storage=_make_mock_storage())
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Set allowed roots to include our test directory to pass security guard
            monkeypatch.setenv("MCP_HARVEST_ALLOWED_ROOTS", tmpdir)
            
            with patch("mcp_memory_service.harvest.harvester.SessionHarvester") as mock_harvester_class:
                with patch("mcp_memory_service.services.memory_service.MemoryService") as mock_ms_class:
                    with patch("mcp_memory_service.harvest.models.HarvestConfig") as mock_config_class:
                        mock_harvester = MagicMock()
                        mock_harvester.harvest_and_store = AsyncMock(return_value=[])
                        mock_harvester_class.return_value = mock_harvester
                        
                        arguments = {
                            "action": "harvest",
                            "path": tmpdir
                        }
                        
                        _run(handle_memory_consolidate(server, arguments))
                        
                        # Verify HarvestConfig was called with correct defaults
                        mock_config_class.assert_called_once()
                        config_kwargs = mock_config_class.call_args[1]
                        assert config_kwargs["sessions"] == 50  # default
                        assert config_kwargs["dry_run"] is False  # default
                        assert config_kwargs["use_llm"] is True  # default
                        assert config_kwargs["force_reharvest"] is False  # default

    def test_harvest_action_custom_parameters(self, monkeypatch):
        """Test that harvest action respects custom parameter values."""
        server = _make_mock_server(storage=_make_mock_storage())
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Set allowed roots to include our test directory to pass security guard
            monkeypatch.setenv("MCP_HARVEST_ALLOWED_ROOTS", tmpdir)
            
            with patch("mcp_memory_service.harvest.harvester.SessionHarvester") as mock_harvester_class:
                with patch("mcp_memory_service.services.memory_service.MemoryService") as mock_ms_class:
                    with patch("mcp_memory_service.harvest.models.HarvestConfig") as mock_config_class:
                        mock_harvester = MagicMock()
                        mock_harvester.harvest_and_store = AsyncMock(return_value=[])
                        mock_harvester_class.return_value = mock_harvester
                        
                        arguments = {
                            "action": "harvest",
                            "path": tmpdir,
                            "sessions": 25,
                            "dry_run": True,
                            "use_llm": False,
                            "force_reharvest": True
                        }
                        
                        _run(handle_memory_consolidate(server, arguments))
                        
                        # Verify HarvestConfig was called with custom values
                        mock_config_class.assert_called_once()
                        config_kwargs = mock_config_class.call_args[1]
                        assert config_kwargs["sessions"] == 25
                        assert config_kwargs["dry_run"] is True
                        assert config_kwargs["use_llm"] is False
                        assert config_kwargs["force_reharvest"] is True


class TestHarvestActionValidation:
    """Test action validation and enum support."""

    def test_harvest_action_enum_validation(self):
        """Test that 'harvest' is accepted as a valid action."""
        server = _make_mock_server(storage=_make_mock_storage())
        
        # Test valid action
        arguments = {"action": "harvest"}
        result = _run(handle_memory_consolidate(server, arguments))
        
        # Should not fail with "Invalid action" error
        assert len(result) == 1
        assert "Invalid action" not in result[0].text

    def test_invalid_action_rejected(self):
        """Test that invalid actions are properly rejected."""
        server = _make_mock_server(storage=_make_mock_storage())
        
        arguments = {"action": "invalid_action"}
        result = _run(handle_memory_consolidate(server, arguments))
        
        assert len(result) == 1
        assert result[0].type == "text"
        assert "Invalid action 'invalid_action'" in result[0].text

    def test_missing_action_parameter(self):
        """Test that missing action parameter is handled."""
        server = _make_mock_server(storage=_make_mock_storage())
        
        arguments = {}  # No action parameter
        result = _run(handle_memory_consolidate(server, arguments))
        
        assert len(result) == 1
        assert result[0].type == "text"
        assert "action parameter is required" in result[0].text


class TestHarvestActionErrorHandling:
    """Test error handling scenarios."""

    def test_harvest_action_harvester_exception(self):
        """Test error handling when SessionHarvester raises an exception."""
        server = _make_mock_server(storage=_make_mock_storage())
        
        with patch("mcp_memory_service.harvest.harvester.SessionHarvester") as mock_harvester_class:
            mock_harvester_class.side_effect = Exception("Harvester initialization failed")
            
            arguments = {"action": "harvest"}
            result = _run(handle_memory_consolidate(server, arguments))
            
            assert len(result) == 1
            assert result[0].type == "text"
            assert "Error in memory_consolidate action 'harvest'" in result[0].text

    def test_harvest_action_memory_service_exception(self):
        """Test error handling when MemoryService initialization fails."""
        server = _make_mock_server(storage=_make_mock_storage())
        
        with patch("mcp_memory_service.services.memory_service.MemoryService") as mock_ms_class:
            mock_ms_class.side_effect = Exception("MemoryService init failed")
            
            arguments = {"action": "harvest"}
            result = _run(handle_memory_consolidate(server, arguments))
            
            assert len(result) == 1
            assert result[0].type == "text"
            assert "Error in memory_consolidate action 'harvest'" in result[0].text

    def test_harvest_action_harvest_and_store_exception(self):
        """Test error handling when harvest_and_store fails."""
        server = _make_mock_server(storage=_make_mock_storage())
        
        with patch("mcp_memory_service.harvest.harvester.SessionHarvester") as mock_harvester_class:
            with patch("mcp_memory_service.services.memory_service.MemoryService"):
                with patch("mcp_memory_service.harvest.models.HarvestConfig"):
                    mock_harvester = MagicMock()
                    mock_harvester.harvest_and_store = AsyncMock(side_effect=Exception("Storage error"))
                    mock_harvester_class.return_value = mock_harvester
                    
                    arguments = {"action": "harvest"}
                    result = _run(handle_memory_consolidate(server, arguments))
                    
                    assert len(result) == 1
                    assert result[0].type == "text"
                    assert "Error in memory_consolidate action 'harvest'" in result[0].text