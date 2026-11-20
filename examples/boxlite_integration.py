#!/usr/bin/env python3
"""BoxLite + AgentPathfinder: HMAC-audited exec.

Prerequisites:
    pip install boxlite

Run:
    python3 examples/boxlite_integration.py
"""

import asyncio
from pathlib import Path
from agentpathfinder.boxlite import AuditedBox


async def main():
    audit_dir = Path("/tmp/boxlite-audit-demo")
    audit_dir.mkdir(parents=True, exist_ok=True)

    async with AuditedBox(
        image="python:3.12-slim",
        name="demo-audit-box",
        audit_dir=audit_dir,
    ) as box:
        print(f"Box started: {box.id}")

        # --- normal exec ---
        result = await box.exec("python", "-c", "print(2 + 2)")
        print(f"  exec 1 → exit={result.exit_code}  stdout={result.stdout.strip()}")

        # --- another ---
        result = await box.exec("echo", "hello from the microVM")
        print(f"  exec 2 → exit={result.exit_code}  stdout={result.stdout.strip()}")

        # --- a failing command ---
        result = await box.exec("python", "-c", "import sys; sys.exit(42)")
        print(f"  exec 3 → exit={result.exit_code}")

    # --- read the audit trail ---
    print(f"\nAudit file: {audit_dir / 'demo-audit-box.jsonl'}")
    print(f"Integrity:   {box.audit.verify_integrity()}")

    print("\nEvents:")
    for event in box.audit.read():
        tamper = "✓" if event.get("tamper_ok") else "✗"
        print(f"  [{tamper}] {event['event']:15s}  cmd={event.get('cmd',''):30s}"
              f"  seq={event['seq']}  hmac={event.get('hmac_prefix','')}")


if __name__ == "__main__":
    asyncio.run(main())