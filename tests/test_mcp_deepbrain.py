"""Tests for DeepBrain MCP server — guard, cognition, model query."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentpathfinder.mcp.deepbrain_server import _cognition, _guard, _DEEPBRAIN_OK
from agentpathfinder.mcp.deepbrain_server import _TOOLS


class TestDeepbrainMCP:
    """Test DeepBrain MCP server tool logic."""

    def test_tools_defined(self):
        """Server exports all expected tool definitions."""
        tool_names = [t.name for t in _TOOLS]
        assert "guard" in tool_names
        assert "route" in tool_names
        assert "model_query" in tool_names
        assert "cognition" in tool_names
        assert len(_TOOLS) == 4

    def test_guard_arguments(self):
        """guard tool has correct input schema."""
        guard_tool = [t for t in _TOOLS if t.name == "guard"][0]
        assert "query" in guard_tool.inputSchema["required"]
        props = guard_tool.inputSchema["properties"]
        assert "query" in props
        assert props["query"]["type"] == "string"

    def test_cognition_arguments(self):
        """cognition tool requires query argument."""
        cog_tool = [t for t in _TOOLS if t.name == "cognition"][0]
        assert "query" in cog_tool.inputSchema["required"]

    def test_route_arguments(self):
        """route tool has correct schema."""
        route_tool = [t for t in _TOOLS if t.name == "route"][0]
        assert "query" in route_tool.inputSchema["required"]
        props = route_tool.inputSchema["properties"]
        assert "tier" in props
        assert "execute" in props

    def test_model_query_arguments(self):
        """model_query tool has correct schema."""
        mq_tool = [t for t in _TOOLS if t.name == "model_query"][0]
        assert "prompt" in mq_tool.inputSchema["required"]
        props = mq_tool.inputSchema["properties"]
        assert "model" in props
        assert "temperature" in props

    @pytest.mark.skipif(not _DEEPBRAIN_OK, reason="DeepBrain not installed")
    @pytest.mark.asyncio
    async def test_cognition_works(self):
        """cognition works when DeepBrain is available."""
        result = await _cognition({"query": "write a sorting algorithm"})
        assert "query" in result
        assert result["query"] == "write a sorting algorithm"

    @pytest.mark.skipif(not _DEEPBRAIN_OK, reason="DeepBrain not installed")
    @pytest.mark.asyncio
    async def test_guard_works(self):
        """guard works when DeepBrain is available."""
        result = await _guard({"query": "hello"})
        assert "decision" in result