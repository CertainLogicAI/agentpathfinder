"""Tests for Pathfinder MCP server — audited execution + validation."""
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentpathfinder.mcp.pathfinder_server import _exec, _validate, _audit_verify, _BOXES


class TestPathfinderMCP:
    """Test Pathfinder MCP server tool logic."""

    def setup_method(self):
        _BOXES.clear()

    @pytest.mark.asyncio
    async def test_exec_accepts_code(self):
        """exec accepts code and returns output structure."""
        result = await _exec({"code": "print('hello')", "language": "python"})
        assert "box_id" in result
        assert "stdout" in result
        assert "stderr" in result
        assert "exit_code" in result
        assert "audit_event_id" in result
        assert result["exit_code"] == 0
        assert "hello" in result["stdout"]

    @pytest.mark.asyncio
    async def test_exec_creates_audit_event(self):
        """exec creates an HMAC-signed audit event."""
        result = await _exec({"code": "x = 1 + 1", "language": "python"})
        box_id = result["box_id"]
        box = _BOXES.get(box_id)
        assert box is not None
        assert len(box["events"]) == 1
        event = box["events"][0]
        assert event["event"] == "EXEC"
        assert event["exit_code"] == 0
        assert "hmac" in event
        assert event["box_id"] == box_id

    @pytest.mark.asyncio
    async def test_exec_accepts_custom_box_id(self):
        """exec reuses an existing box session when box_id is provided."""
        custom_id = f"test_box_{uuid.uuid4().hex[:8]}"
        r1 = await _exec({"code": "print('a')", "box_id": custom_id})
        r2 = await _exec({"code": "print('b')", "box_id": custom_id})
        assert r1["box_id"] == custom_id
        assert r2["box_id"] == custom_id
        box = _BOXES[custom_id]
        assert len(box["events"]) == 2

    @pytest.mark.asyncio
    async def test_exec_bash(self):
        """exec supports bash language."""
        result = await _exec({"code": "echo 'shell works'", "language": "bash"})
        assert result["exit_code"] == 0
        assert "shell works" in result["stdout"]

    @pytest.mark.asyncio
    async def test_exec_multiline_code(self):
        """exec handles multiline Python code."""
        code = """
a = 2
b = 3
print(f"sum={a+b}")
"""
        result = await _exec({"code": code, "language": "python"})
        assert result["exit_code"] == 0
        assert "sum=5" in result["stdout"]

    def test_validate_passes(self):
        """validate returns pass for matching checks."""
        result = {"stdout": "All 12 tests passed", "exit_code": 0}
        rules = {"stdout": {"contains": "passed"}}
        report = _validate({"result": result, "rules": rules})
        assert report["passed"] is True, f"Failed: {report['failed_checks']}"
        assert len(report["failed_checks"]) == 0

    def test_validate_fails(self):
        """validate returns fail for failing checks."""
        result = {"stdout": "BUILD FAILED", "exit_code": 1}
        rules = {"exit_code": {"equals": 0}}
        report = _validate({"result": result, "rules": rules})
        assert report["passed"] is False
        assert len(report["failed_checks"]) == 1

    def test_validate_multiple_checks_and(self):
        """validate supports multiple field checks."""
        result = {"stdout": "Tests: 10 passed, 0 failed", "exit_code": 0}
        rules = {"exit_code": {"equals": 0}, "stdout": {"contains": "passed"}}
        report = _validate({"result": result, "rules": rules})
        assert report["passed"] is True, f"Failed: {report['failed_checks']}"

    @pytest.mark.asyncio
    async def test_audit_verify_passes(self):
        """audit_verify returns passed=True for untampered audit trails."""
        r1 = await _exec({"code": "print('a')"})
        r2 = await _exec({"code": "print('b')", "box_id": r1["box_id"]})
        report = _audit_verify({"box_id": r1["box_id"]})
        assert report["passed"] is True
        assert report["total"] == 2
        assert report["failed"] == 0

    @pytest.mark.asyncio
    async def test_audit_verify_detects_tamper(self):
        """audit_verify detects manually modified audit events."""
        r = await _exec({"code": "print('a')"})
        box_id = r["box_id"]
        box = _BOXES[box_id]
        # Tamper with the event
        box["events"][0]["exit_code"] = 999
        report = _audit_verify({"box_id": box_id})
        assert report["passed"] is False
        assert report["failed"] >= 1

    @pytest.mark.asyncio
    async def test_exec_handles_empty_code(self):
        """exec handles empty code strings."""
        result = await _exec({"code": "", "language": "python"})
        assert result["exit_code"] == 0
        assert "audit_event_id" in result