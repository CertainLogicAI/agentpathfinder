"""MCP server launcher — CLI entry point for both servers.

Usage:
    python3 -m agentpathfinder.mcp pathfinder   # start Pathfinder MCP server (stdio)
    python3 -m agentpathfinder.mcp memory        # start Memory MCP server (stdio)
    python3 -m agentpathfinder.mcp deepbrain     # start DeepBrain MCP server (stdio)
    python3 -m agentpathfinder.mcp help          # print usage

Each server speaks MCP over stdio.  Configure as an MCP client subprocess:
    {
        "mcpServers": {
            "agentpathfinder": {
                "command": "python3",
                "args": ["-m", "agentpathfinder.mcp", "pathfinder"]
            }
        }
    }
"""
import asyncio
import sys

import importlib

_SERVERS = {
    "pathfinder": "agentpathfinder.mcp.pathfinder_server",
    "memory": "agentpathfinder.mcp.memory_server",
    "deepbrain": "agentpathfinder.mcp.deepbrain_server",
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("--help", "-h", "help"):
        print(__doc__)
        return

    mode = sys.argv[1]
    mod_path = _SERVERS.get(mode)
    if not mod_path:
        print(f"Unknown server: {mode}")
        print(f"Available: {', '.join(_SERVERS.keys())}")
        sys.exit(1)

    mod = importlib.import_module(mod_path)
    asyncio.run(mod.run())


if __name__ == "__main__":
    main()