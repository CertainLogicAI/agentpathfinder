"""Timechain Memory MCP server — long horizon memory via timechain + Brain API.

Semantic recall across 462K rings. Seal new rings. KB search.

Tools:
- recall:          Semantic search across timechain rings
- seal:            Seal a new memory ring to timechain
- brain_search:    Brain KB semantic search
- brain_fact:      Get specific Brain API fact
- chain_stats:     Timechain statistics

Resources:
- timechain://stats — chain height + replay stats
"""
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types

# Structured logging
_LOG_LEVEL = os.environ.get("TC_MCP_LOG_LEVEL", "WARNING").upper()
logging.basicConfig(stream=sys.stderr, level=getattr(logging, _LOG_LEVEL), format="%(message)s")
log = logging.getLogger("timechain-mcp")

# ── Timechain & Brain API configuration ──────────────────────────────
_LOADED = False
_INTERNAL_KEY: str = ""
_TIMECHAIN_URL: str = "http://127.0.0.1:8080"
_BRAIN_URL: str = "http://127.0.0.1:8000"


def _load_config():
    global _LOADED, _INTERNAL_KEY, _TIMECHAIN_URL, _BRAIN_URL
    if _LOADED:
        return
    _TIMECHAIN_URL = os.environ.get("TIMECHAIN_URL", "http://127.0.0.1:8080")
    _BRAIN_URL = os.environ.get("BRAIN_API_URL", "http://127.0.0.1:8000")
    _INTERNAL_KEY = os.environ.get("INTERNAL_API_KEY", "")
    if not _INTERNAL_KEY:
        env_path = Path(os.path.expanduser("~/.openclaw/workspace/.brain_env"))
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("export INTERNAL_API_KEY="):
                    _INTERNAL_KEY = line.split("=", 1)[1].strip().strip('"')
    _LOADED = True


def _headers() -> dict:
    _load_config()
    return {"X-API-Key": _INTERNAL_KEY, "Content-Type": "application/json"} if _INTERNAL_KEY else {}


def _timechain_get(path: str, params: Optional[dict] = None, timeout: int = 10) -> dict:
    _load_config()
    try:
        r = httpx.get(f"{_TIMECHAIN_URL}{path}", headers=_headers(), params=params, timeout=timeout)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def _timechain_post(path: str, payload: dict, timeout: int = 15) -> dict:
    _load_config()
    try:
        r = httpx.post(f"{_TIMECHAIN_URL}{path}", headers=_headers(), json=payload, timeout=timeout)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def _brain_get(path: str, params: Optional[dict] = None, timeout: int = 10) -> dict:
    _load_config()
    try:
        r = httpx.get(f"{_BRAIN_URL}{path}", headers=_headers(), params=params, timeout=timeout)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


# ── Server instance ──────────────────────────────────────────────────
server = Server("timechain-mcp")


# ── Tool definitions ─────────────────────────────────────────────────
_TOOLS = [
    types.Tool(
        name="recall",
        description="Semantic search across 462K timechain memory rings. Returns matching antecedents with scores and excerpts.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "top": {"type": "number", "description": "Max results (1-20)", "default": 5},
            },
            "required": ["query"],
        },
    ),
    types.Tool(
        name="seal",
        description="Seal a new memory ring into the timechain. Types: execution_trace, observation, knowledge_fact, session_pattern, distilled_insight.",
        inputSchema={
            "type": "object",
            "properties": {
                "ring_type": {"type": "string", "description": "Ring type (execution_trace, observation, knowledge_fact, etc.)"},
                "content": {"type": "object", "description": "Ring content / payload (max 100KB)"},
            },
            "required": ["ring_type", "content"],
        },
    ),
    types.Tool(
        name="brain_search",
        description="Search the Brain knowledge base (24K+ facts) semantically.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "number", "description": "Max results", "default": 5},
            },
            "required": ["query"],
        },
    ),
    types.Tool(
        name="brain_fact",
        description="Retrieve a specific Brain API fact by key/slug.",
        inputSchema={
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Fact key or slug"},
            },
            "required": ["slug"],
        },
    ),
    types.Tool(
        name="chain_stats",
        description="View timechain statistics: chain height, ring count, replay stats.",
        inputSchema={"type": "object", "properties": {}},
    ),
]


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return _TOOLS


# ── Tool handlers ────────────────────────────────────────────────────
@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        if name == "recall":
            return [types.TextContent(type="text", text=json.dumps(await _recall(arguments)))]
        elif name == "seal":
            return [types.TextContent(type="text", text=json.dumps(await _seal(arguments)))]
        elif name == "brain_search":
            return [types.TextContent(type="text", text=json.dumps(await _brain_search(arguments)))]
        elif name == "brain_fact":
            return [types.TextContent(type="text", text=json.dumps(await _brain_fact(arguments)))]
        elif name == "chain_stats":
            return [types.TextContent(type="text", text=json.dumps(await _chain_stats()))]
        else:
            return [types.TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]
    except Exception as e:
        log.exception("Tool call failed")
        return [types.TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def _recall(args: dict) -> dict:
    query = args["query"]
    top = min(int(args.get("top", 5)), 20)
    result = _timechain_post("/replay", {"query": query, "top": top})
    if "error" in result:
        return {"error": result["error"], "note": "Timechain may not be running"}
    antecedents = result.get("antecedents", [])
    return {
        "query": query,
        "found": len(antecedents),
        "antecedents": [
            {
                "index": a.get("index", 0),
                "type": a.get("ring_type", "unknown"),
                "score": a.get("score", 0.0),
                "excerpt": str(a.get("payload", {}))[:500] if a.get("payload") else "",
                "timestamp": a.get("timestamp", ""),
            }
            for a in antecedents
        ],
    }


async def _seal(args: dict) -> dict:
    ring_type = args["ring_type"]
    content = args["content"]
    result = _timechain_post("/seal", {"ring_type": ring_type, "payload": content})
    if "error" in result:
        return {"error": result["error"], "note": "Timechain may not be running"}
    return {"ring_index": result.get("index", -1), "ring_type": ring_type, "status": "sealed"}


async def _brain_search(args: dict) -> dict:
    query = args["query"]
    limit = min(int(args.get("limit", 5)), 20)
    result = _brain_get("/facts/search", {"q": query, "limit": limit})
    if "error" in result:
        return {"error": result["error"], "note": "Brain API may not be running"}
    facts = result.get("facts", result.get("results", []))
    return {"query": query, "found": len(facts), "facts": facts}


async def _brain_fact(args: dict) -> dict:
    slug = args["slug"]
    result = _brain_get(f"/facts/{slug}")
    if "error" in result:
        return {"error": result["error"], "note": "Brain API may not be running"}
    return {"slug": slug, "fact": result}


async def _chain_stats() -> dict:
    health = _timechain_get("/health")
    stats = _timechain_get("/stats")
    if "error" in health:
        return {"error": health["error"], "note": "Timechain may not be running"}
    return {
        "chain": health.get("chain", {}),
        "stats": stats.get("stats", stats),
        "status": health.get("status", "unknown"),
    }


# ── Run ──────────────────────────────────────────────────────────────
async def run():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="timechain-mcp",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(run())