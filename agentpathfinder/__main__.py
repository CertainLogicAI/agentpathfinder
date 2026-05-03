"""AgentPathfinder package.

Enables: python3 -m agentpathfinder
"""

from .pathfinder_core import (
    generate_master_key,
    split_key,
    reconstruct_key,
    hmac_sign,
    verify_hmac,
    hash_key,
    derive_key,
    shard_to_hex,
    shard_from_hex,
)
from .audit_trail import AuditTrail
from .tool_audit import ToolAuditChain, AuditedToolExecutor
from .task_engine import TaskEngine, TaskState
from .issuing_layer import IssuingLayer
from .agent_runtime import AgentRuntime

__version__ = "1.3.0"
__all__ = [
    "generate_master_key",
    "split_key",
    "reconstruct_key",
    "hmac_sign",
    "verify_hmac",
    "hash_key",
    "derive_key",
    "shard_to_hex",
    "shard_from_hex",
    "AuditTrail",
    "ToolAuditChain",
    "AuditedToolExecutor",
    "TaskEngine",
    "TaskState",
    "IssuingLayer",
    "AgentRuntime",
]


if __name__ == "__main__":
    from .scripts.pathfinder_client import main
    main()
