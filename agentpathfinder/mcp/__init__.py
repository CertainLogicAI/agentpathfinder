"""AgentPathfinder MCP servers — production-grade Model Context Protocol integration.

Two independent MCP servers:

1. **PathfinderServer** — audited sandbox execution via BoxLite microVM.
   Every exec is HMAC-signed. Results can be validated against deterministic rules.

2. **MemoryServer** — long horizon memory via timechain + Brain API.
   Semantic recall across 462K rings. Seal new rings. KB search.

Usage:
    python3 -m agentpathfinder.mcp pathfinder   # start Pathfinder MCP server
    python3 -m agentpathfinder.mcp memory        # start Memory MCP server
    python3 -m agentpathfinder.mcp help          # show usage
"""

__all__ = ["pathfinder_server", "memory_server"]