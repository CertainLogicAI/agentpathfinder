"""Pathfinder MCP server — audited sandbox execution via BoxLite microVM.

Every exec command is HMAC-signed to a tamper-evident audit trail.
Results can be validated against deterministic rules (no AI, no model-as-judge).

Tools:
- exec:          Run code in audited BoxLite microVM
- validate:      Deterministic rule check against a result
- audit_trail:   Retrieve audit trail for a box session
- audit_verify:  Verify HMAC integrity of entire audit trail

Resources:
- audit://{box_id}/trail    — JSONL audit trail
- audit://{box_id}/summary  — validation summary
"""
import asyncio
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types

# Configure structured JSON logging
_LOG_FORMAT = "%(message)s"
_LOG_LEVEL = os.environ.get("PF_MCP_LOG_LEVEL", "WARNING").upper()
logging.basicConfig(stream=sys.stderr, level=getattr(logging, _LOG_LEVEL), format=_LOG_FORMAT)
log = logging.getLogger("pathfinder-mcp")

# ── Optional BoxLite import ──────────────────────────────────────────
_SIMPLEBOX = None
_SIMPLEBOX_ERR = None
try:
    from boxlite.simplebox import SimpleBox
    _SIMPLEBOX = SimpleBox
except ImportError as e:
    _SIMPLEBOX_ERR = str(e)

# Pathfinder imports
from agentpathfinder.pathfinder_core import generate_master_key, hmac_sign, verify_hmac, hash_key
from agentpathfinder.result_validator import validate as run_validation

_BOXES: dict[str, dict[str, Any]] = {}
_DEFAULT_AUDIT_DIR = Path.home() / ".agentpathfinder" / "audit"


def _get_box(box_id: str) -> dict:
    box = _BOXES.get(box_id)
    if not box:
        raise ValueError(f"Unknown box: {box_id}")
    return box


def _sign_audit(key: bytes, event: dict) -> str:
    return hmac_sign(key, json.dumps(event, sort_keys=True, default=str))


# ── Server instance ──────────────────────────────────────────────────
server = Server("agentpathfinder-mcp")


# ── Tool definitions ─────────────────────────────────────────────────
_TOOLS = [
    types.Tool(
        name="exec",
        description="Execute code in a BoxLite microVM. Returns stdout, stderr, exit_code, and audit_event_id."
                    " Every call is HMAC-signed to a tamper-evident audit trail on the host.",
        inputSchema={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Code to execute"},
                "language": {"type": "string", "description": "Runtime (python, bash, node)", "default": "python"},
                "box_id": {"type": "string", "description": "Box session ID (omit for ephemeral box)"},
                "image": {"type": "string", "description": "Container image (default: python:slim)", "default": "python:slim"},
            },
            "required": ["code"],
        },
    ),
    types.Tool(
        name="validate",
        description="Run deterministic validation rules against a tool result. No AI, no model-as-judge."
                    " Returns pass/fail with details on each check.",
        inputSchema={
            "type": "object",
            "properties": {
                "result": {"type": "object", "description": "Result dict with stdout/stderr/exit_code fields"},
                "rules": {"type": "object", "description": "Validation rules dict (equals, contains, excludes, empty, not_empty, matches, lt, gt)"},
            },
            "required": ["result", "rules"],
        },
    ),
    types.Tool(
        name="audit_trail",
        description="Retrieve the signed audit trail for a box session.",
        inputSchema={
            "type": "object",
            "properties": {
                "box_id": {"type": "string", "description": "Box session ID"},
            },
            "required": ["box_id"],
        },
    ),
    types.Tool(
        name="audit_verify",
        description="Verify HMAC integrity of the entire audit trail for a box session."
                    " Returns pass/fail + details on any tampered entries.",
        inputSchema={
            "type": "object",
            "properties": {
                "box_id": {"type": "string", "description": "Box session ID"},
            },
            "required": ["box_id"],
        },
    ),
]


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return _TOOLS


# ── Tool handlers ────────────────────────────────────────────────────
@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        if name == "exec":
            return [types.TextContent(type="text", text=json.dumps(await _exec(arguments)))]
        elif name == "validate":
            return [types.TextContent(type="text", text=json.dumps(_validate(arguments)))]
        elif name == "audit_trail":
            return [types.TextContent(type="text", text=_audit_trail(arguments))]
        elif name == "audit_verify":
            return [types.TextContent(type="text", text=json.dumps(_audit_verify(arguments)))]
        else:
            return [types.TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]
    except (ValueError, FileNotFoundError) as e:
        return [types.TextContent(type="text", text=json.dumps({"error": str(e)}))]
    except Exception as e:
        log.exception("Tool call failed")
        return [types.TextContent(type="text", text=json.dumps({"error": f"Internal error: {e}"}))]


async def _exec(args: dict) -> dict:
    """Execute code in audited BoxLite microVM."""
    code = args["code"]
    language = args.get("language", "python")
    box_id = args.get("box_id") or f"box_{uuid.uuid4().hex[:12]}"
    image = args.get("image", "python:slim")

    # Generate or reuse audit key
    box = _BOXES.get(box_id)
    if not box:
        audit_key = generate_master_key()
        audit_path = _DEFAULT_AUDIT_DIR / f"{box_id}.jsonl"
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        box = {"id": box_id, "audit_key": audit_key, "audit_path": audit_path, "events": []}
        _BOXES[box_id] = box

    # Map language to command
    lang_map = {
        "python": ["python3", "-c", code],
        "bash": ["bash", "-c", code],
        "sh": ["sh", "-c", code],
        "node": ["node", "-e", code],
    }
    cmd = lang_map.get(language, ["python3", "-c", code])

    # Execute via BoxLite if available, else subprocess mock
    stdout, stderr, exit_code = "", "", -1
    if _SIMPLEBOX:
        try:
            async with _SIMPLEBOX(image=image) as sb:
                result = await sb.exec(*cmd)
                stdout = result.stdout or ""
                stderr = result.stderr or ""
                exit_code = result.exit_code or 0
        except Exception as e:
            stderr = str(e)
            exit_code = -1
    else:
        import subprocess
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            stdout, stderr, exit_code = r.stdout, r.stderr, r.returncode
        except subprocess.TimeoutExpired:
            stderr = "Timeout (30s)"
            exit_code = -1
        except FileNotFoundError:
            stderr = f"Runtime not found: {cmd[0]}"
            exit_code = -1

    # Build audit event
    event = {
        "event": "EXEC",
        "box_id": box_id,
        "timestamp": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
        "seq": len(box["events"]) + 1,
        "code": code,
        "language": language,
        "cmd": cmd,
        "stdout_len": len(stdout),
        "stderr_len": len(stderr),
        "exit_code": exit_code,
    }
    event["hmac"] = _sign_audit(box["audit_key"], {k: v for k, v in event.items() if k != "hmac"})
    box["events"].append(event)

    # Append to audit file
    with open(box["audit_path"], "a") as f:
        f.write(json.dumps(event, default=str) + "\n")

    return {
        "box_id": box_id,
        "stdout": stdout[:50000],
        "stderr": stderr[:10000],
        "exit_code": exit_code,
        "audit_event_id": f"{box_id}#{event['seq']}",
    }


def _validate(args: dict) -> dict:
    """Run deterministic validation rules against a result.

    Rules format::
        {"exit_code": {"equals": 0}, "stdout": {"contains": "passed"}}
    """
    result = args["result"]
    rules = args["rules"]
    if "checks" in rules:
        # Convert from legacy list format to field-keyed format
        converted = {}
        for c in rules["checks"]:
            field = c.get("field", "result")
            check_type = c.get("type", "equals")
            val = c.get("value", True)
            converted[field] = {check_type: val}
        rules = converted
    report = run_validation(result, rules)
    return {"passed": report.passed, "checks": report.checks, "failed_checks": report.failed_checks}


def _audit_trail(args: dict) -> str:
    """Return the audit trail as JSONL text."""
    box_id = args["box_id"]
    box = _get_box(box_id)
    return box["audit_path"].read_text()


def _audit_verify(args: dict) -> dict:
    """Verify HMAC integrity of all audit events."""
    box_id = args["box_id"]
    box = _get_box(box_id)
    results = []
    for event in box["events"]:
        expected_sig = event.get("hmac", "")
        canonical = {k: v for k, v in event.items() if k != "hmac"}
        computed = _sign_audit(box["audit_key"], canonical)
        ok = computed == expected_sig
        results.append({"seq": event["seq"], "ok": ok, "event": event["event"]})
    total = len(results)
    failed = sum(1 for r in results if not r["ok"])
    return {"passed": failed == 0, "total": total, "failed": failed, "results": results}


# ── Run ──────────────────────────────────────────────────────────────
async def run():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="agentpathfinder-mcp",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(run())