"""MCP server launcher — CLI entry point for both servers.

Usage:
    python3 -m agentpathfinder.mcp pathfinder   # start Pathfinder MCP server (stdio)
    python3 -m agentpathfinder.mcp memory        # start Memory MCP server (stdio)
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

from .pathfinder_server import PathfinderServer
from .memory_server import MemoryServer


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("--help", "-h", "help"):
        print(__doc__)
        return

    mode = sys.argv[1]

    if mode == "pathfinder":
        server = PathfinderServer()
        asyncio.run(server.run())
    elif mode == "memory":
        server = MemoryServer()
        asyncio.run(server.run())
    else:
        print(f"Unknown server: {mode}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()