#!/usr/bin/env python3
"""E2E test — creates a minimal boxlite stub for import compatibility.

Run:
    python3 tests/test_boxlite_e2e.py
"""

import asyncio
import json
import os
import sys
import tempfile
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Minimal boxlite stub — provides ExecResult so the real AuditedBox can import it
# ---------------------------------------------------------------------------
import types as _types
_boxlite_stub = _types.ModuleType("boxlite")
_boxlite_stub.__path__ = []
_boxlite_stub.__package__ = "boxlite"

@dataclass
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str
    error_message: str | None = None

_boxlite_exec_module = _types.ModuleType("boxlite.exec")
_boxlite_exec_module.__package__ = "boxlite.exec"
_boxlite_exec_module.ExecResult = ExecResult
_boxlite_stub.exec = _boxlite_exec_module
_boxlite_stub.ExecResult = ExecResult

_boxlite_simplebox_module = _types.ModuleType("boxlite.simplebox")
_boxlite_simplebox_module.__package__ = "boxlite.simplebox"

class MockSimpleBox:
    """Stand-in for boxlite.simplebox.SimpleBox — runs commands via subprocess."""

    def __init__(self, name: str = "mock-box", **kwargs):
        self._name = name
        self._started = False

    @property
    def id(self) -> str:
        return f"mock-{self._name}"

    @property
    def created(self) -> Optional[bool]:
        return True

    def info(self) -> dict:
        return {"id": self.id, "name": self._name, "type": "mock"}

    async def __aenter__(self):
        self._started = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._started = False

    async def start(self):
        self._started = True
        return self

    async def stop(self):
        self._started = False

    async def shutdown(self):
        await self.stop()

    async def copy_in(self, *args, **kwargs):
        pass

    async def copy_out(self, *args, **kwargs):
        pass

    async def exec(self, cmd: str, *args: str, env=None, user=None,
                   timeout=None, cwd=None) -> ExecResult:
        full_cmd = [cmd] + list(args)
        try:
            proc = subprocess.run(full_cmd, capture_output=True, text=True,
                                  timeout=timeout or 30, cwd=cwd or os.getcwd())
            return ExecResult(exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)
        except FileNotFoundError as e:
            return ExecResult(exit_code=-1, stdout="", stderr=str(e), error_message=str(e))
        except subprocess.TimeoutExpired as e:
            return ExecResult(exit_code=-2, stdout=e.stdout or "", stderr=(e.stderr or "")+"\n[timeout]",
                              error_message="TimeoutExpired")

_boxlite_simplebox_module.MockSimpleBox = MockSimpleBox
_boxlite_stub.simplebox = _boxlite_simplebox_module

sys.modules["boxlite"] = _boxlite_stub
sys.modules["boxlite.exec"] = _boxlite_exec_module
sys.modules["boxlite.simplebox"] = _boxlite_simplebox_module

# Now patch AuditedBox to use MockSimpleBox instead of importing the real thing
from agentpathfinder.boxlite.audited_box import AuditedBox
from agentpathfinder.pathfinder_core import generate_master_key

_original_init = AuditedBox.__init__

def _patched_init(self, audit_key=None, audit_dir=None, name=None, **kwargs):
    name = name or f"mock-audited-{id(self)}"
    self._name = name
    self._box = MockSimpleBox(name=name, **kwargs)
    if audit_key is None:
        audit_key = generate_master_key()
    else:
        from agentpathfinder.pathfinder_core import derive_key
        audit_key = derive_key(audit_key, b"boxlite-audit-v1")
    self._audit_key = audit_key
    self._audit_dir = Path(audit_dir or Path.home() / ".agentpathfinder" / "audit")
    self._audit_trail = None

AuditedBox.__init__ = _patched_init

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
AUDIT_DIR = Path(tempfile.mkdtemp(prefix="boxlite-audit-"))

async def test_basic_exec():
    print(f"\n{'='*60}")
    print("TEST 1: Basic audited exec (echo, python, ls)")
    print(f"{'='*60}")

    async with AuditedBox(name="demo-box", audit_dir=AUDIT_DIR) as box:
        r1 = await box.exec("echo", "hello from mock box")
        assert r1.exit_code == 0
        assert "hello from mock box" in r1.stdout
        print(f"  ✓ echo hello → exit={r1.exit_code}  '{r1.stdout.strip()}'")

        r2 = await box.exec("python3", "-c", "print(2 + 2)")
        assert r2.exit_code == 0
        assert "4" in r2.stdout
        print(f"  ✓ python calc → exit={r2.exit_code}  '{r2.stdout.strip()}'")

        r3 = await box.exec("ls", "-la")
        assert r3.exit_code == 0
        print(f"  ✓ ls -la → exit={r3.exit_code}  {len(r3.stdout.splitlines())} lines")

        r4 = await box.exec("python3", "-c", "exit(42)")
        assert r4.exit_code == 42
        print(f"  ✓ python exit(42) → exit={r4.exit_code}")

    events = box.audit.read()
    print(f"\n  Audit trail: {len(events)} events")
    for ev in events:
        t = "✓" if ev.get("tamper_ok") else "✗"
        print(f"    [{t}] {ev['event']:15s} cmd={ev.get('cmd',''):30s} seq={ev['seq']}")

    report = box.audit.verify_integrity()
    assert report["integrity_ok"]
    print(f"\n  ✓ Integrity OK — {report['total_events']} events, 0 tampered")
    return box

async def test_tamper_detection(box):
    print(f"\n{'='*60}")
    print("TEST 2: Tamper detection")
    print(f"{'='*60}")

    audit_file = AUDIT_DIR / f"{box.name}.jsonl"
    raw = audit_file.read_text()
    tampered = raw.replace('"event": "CMD_INVOKED"', '"event": "FORGED"', 1)
    audit_file.write_text(tampered)

    events = box.audit.read()
    bad = [e for e in events if not e.get("tamper_ok", True)]
    print(f"  Total events: {len(events)}")
    print(f"  Tampered:     {len(bad)}")
    for ev in bad:
        print(f"    ⚠ {ev.get('event')} seq={ev.get('seq')} — HMAC fails")

    report = box.audit.verify_integrity()
    assert not report["integrity_ok"]
    assert report["tampered"] >= 1
    print(f"  ✓ Integrity: {report['integrity_ok']} ({report['tampered']} tampered)")

async def test_forged_event():
    print(f"\n{'='*60}")
    print("TEST 3: Forged event detection")
    print(f"{'='*60}")

    async with AuditedBox(name="forge-test", audit_dir=AUDIT_DIR) as box:
        await box.exec("echo", "real cmd")
    forge_line = json.dumps({"event": "CMD_INVOKED", "box_id": "forge-test",
                               "cmd": "rm -rf /", "seq": 999}) + "\n"
    (AUDIT_DIR / "forge-test.jsonl").open("a").write(forge_line)

    events = box.audit.read()
    bad = [e for e in events if not e.get("tamper_ok", True)]
    print(f"  Total: {len(events)}, Forged flagged: {len(bad)}")
    assert len(bad) >= 1
    print(f"  ✓ Forged entry caught")

async def test_multiple_boxes():
    print(f"\n{'='*60}")
    print("TEST 4: Multiple boxes, independent trails")
    print(f"{'='*60}")
    async with AuditedBox(name="box-a", audit_dir=AUDIT_DIR) as a, \
               AuditedBox(name="box-b", audit_dir=AUDIT_DIR) as b:
        await a.exec("echo", "from a")
        await b.exec("echo", "from b")
        await a.exec("echo", "another a")
    ae = a.audit.read()
    be = b.audit.read()
    print(f"  Box A: {len(ae)} events, Box B: {len(be)} events")
    # 2 execs per box = 4 events each (CMD_INVOKED + CMD_RESULT per exec)
    assert len(ae) == 4 and len(be) == 2
    assert a.audit.verify_integrity()["integrity_ok"]
    assert b.audit.verify_integrity()["integrity_ok"]
    print(f"  ✓ Both independent and intact")

async def main():
    print("AgentPathfinder × BoxLite — E2E Test Suite (mock runtime)")
    print(f"Audit dir: {AUDIT_DIR}")
    box = await test_basic_exec()
    await test_tamper_detection(box)
    await test_forged_event()
    await test_multiple_boxes()
    print(f"\n{'='*60}\nALL E2E TESTS PASSED.\n{'='*60}")

if __name__ == "__main__":
    asyncio.run(main())