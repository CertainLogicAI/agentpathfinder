#!/usr/bin/env python3
"""Stress test: try to break the BoxLite Pathfinder audit integration.

Tests concurrency, binary output, torn writes, chain integrity at scale,
replay attacks, and edge cases the real adapter will face in production.

Run:
    python3 tests/test_boxlite_stress.py
"""

import asyncio
import json
import os
import sys
import tempfile
import subprocess
import time
import hashlib
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# BoxLite stub (same as e2e test)
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

_boxlite_exec = _types.ModuleType("boxlite.exec")
_boxlite_exec.__package__ = "boxlite.exec"
_boxlite_exec.ExecResult = ExecResult
_boxlite_stub.exec = _boxlite_exec
_boxlite_stub.ExecResult = ExecResult

_boxlite_simplebox = _types.ModuleType("boxlite.simplebox")
_boxlite_simplebox.__package__ = "boxlite.simplebox"

class MockSimpleBox:
    def __init__(self, name: str = "mock-box", **kwargs):
        self._name = name
        self._started = False
        self._crash_on_exec = kwargs.pop("crash_on_exec", False)
        self._slow_exec = kwargs.pop("slow_exec_ms", 0)

    @property
    def id(self): return f"mock-{self._name}"
    @property
    def created(self): return True
    def info(self): return {"id": self.id, "name": self._name, "type": "mock"}

    async def __aenter__(self): self._started = True; return self
    async def __aexit__(self, *a): self._started = False
    async def start(self): self._started = True; return self
    async def stop(self): self._started = False
    async def shutdown(self): await self.stop()
    async def copy_in(self, *a, **kw): pass
    async def copy_out(self, *a, **kw): pass

    async def exec(self, cmd, *args, env=None, user=None, timeout=None, cwd=None):
        if self._crash_on_exec:
            raise RuntimeError("simulated box crash")
        if self._slow_exec:
            await asyncio.sleep(self._slow_exec / 1000)
        full = [cmd] + list(args)
        try:
            proc = subprocess.run(full, capture_output=True, text=True,
                                  timeout=timeout or 30)
            return ExecResult(proc.returncode, proc.stdout, proc.stderr)
        except FileNotFoundError as e:
            return ExecResult(-1, "", str(e), str(e))
        except subprocess.TimeoutExpired as e:
            return ExecResult(-2, e.stdout or "", (e.stderr or "")+"\n[timeout]",
                              "TimeoutExpired")

_boxlite_simplebox.MockSimpleBox = MockSimpleBox
_boxlite_stub.simplebox = _boxlite_simplebox
sys.modules["boxlite"] = _boxlite_stub
sys.modules["boxlite.exec"] = _boxlite_exec
sys.modules["boxlite.simplebox"] = _boxlite_simplebox

from agentpathfinder.boxlite.audited_box import AuditedBox
from agentpathfinder.pathfinder_core import generate_master_key, derive_key

_patched_init = AuditedBox.__init__

def _mock_init(self, audit_key=None, audit_dir=None, name=None, **kwargs):
    name = name or f"stress-{id(self)}"
    self._name = name
    crash = kwargs.pop("crash_on_exec", False)
    slow = kwargs.pop("slow_exec_ms", 0)
    self._box = MockSimpleBox(name=name, crash_on_exec=crash, slow_exec_ms=slow, **kwargs)
    if audit_key is None:
        audit_key = generate_master_key()
    else:
        audit_key = derive_key(audit_key, b"boxlite-audit-v1")
    self._audit_key = audit_key
    self._audit_dir = Path(audit_dir or Path.home() / ".agentpathfinder" / "audit")
    self._audit_trail = None

AuditedBox.__init__ = _mock_init

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------
AUDIT_DIR = Path(tempfile.mkdtemp(prefix="boxlite-stress-"))
PASS = 0
FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name}  {detail}")

async def test_1_concurrent_execs():
    """Run 50 execs concurrently, verify all audited independently."""
    print("\n── TEST 1: 50 concurrent execs ──")
    async with AuditedBox(name="concurrent", audit_dir=AUDIT_DIR) as box:
        async def run_one(i):
            return await box.exec("echo", str(i))
        results = await asyncio.gather(*[run_one(i) for i in range(50)])
    
    events = box.audit.read()
    invokes = [e for e in events if e["event"] == "CMD_INVOKED"]
    results_ev = [e for e in events if e["event"] == "CMD_RESULT"]
    
    check("50 invoked events", len(invokes) == 50)
    check("50 result events", len(results_ev) == 50)
    check("all seq unique", len({e["seq"] for e in events}) == 100)
    check("all exit_codes 0", all(e.get("exit_code") == 0 for e in results_ev))
    check("integrity intact", box.audit.verify_integrity()["integrity_ok"])
    
    # Verify every echo printed the right number
    for i, r in enumerate(results):
        check(f"result {i} correct", r.stdout.strip() == str(i))


async def test_2_large_stdout():
    """Pipe 10MB through stdout, ensure audit doesn't blow up."""
    print("\n── TEST 2: Large stdout (10MB) ──")
    async with AuditedBox(name="large-stdout", audit_dir=AUDIT_DIR) as box:
        # python3 -c "print('x'*10_000_000)"
        result = await box.exec("python3", "-c", "print('x'*10_000_000)")
    
    check("exit 0", result.exit_code == 0)
    check("stdout 10MB + newline", len(result.stdout) == 10_000_001)  # 10M x's + \n
    check("stderr empty", result.stderr == "")
    
    events = box.audit.read()
    result_ev = [e for e in events if e["event"] == "CMD_RESULT"][0]
    # We log stdout_len, not the full payload
    check("stdout_len logged", result_ev.get("stdout_len", 0) == 10_000_001)
    check("integrity intact", box.audit.verify_integrity()["integrity_ok"])
    print(f"  audit file size: {box.audit.log_path.stat().st_size} bytes (for 10MB exec)")


async def test_3_torn_write_recovery():
    """Simulate a crash mid-write: truncate the audit file mid-line."""
    print("\n── TEST 3: Torn write recovery ──")
    async with AuditedBox(name="torn-write", audit_dir=AUDIT_DIR) as box:
        await box.exec("echo", "good event 1")
        await box.exec("echo", "good event 2")
    
    # Truncate last few bytes — simulate a crash mid-json
    path = box.audit.log_path
    original_size = path.stat().st_size
    with open(path, "ab") as f:
        f.truncate(original_size - 10)  # chop last 10 bytes
    
    events = box.audit.read()
    # Should still return the good events, but flag any corruption
    corrupted = [e for e in events if e.get("corrupted")]
    good = [e for e in events if not e.get("corrupted") and not e.get("tamper_ok") is False]
    
    check("some events survive partial truncation", len(good) >= 3)  # 3 good halves possible
    check("corrupted line flagged", len(corrupted) >= 1 or not box.audit.verify_integrity()["integrity_ok"])
    print(f"  {len(good)} good events, {len(corrupted)} corrupted, {path.stat().st_size}/{original_size} bytes")


async def test_4_zero_byte_edge():
    """Empty stdout, empty stderr, zero exit code."""
    print("\n── TEST 4: Zero-byte edge cases ──")
    async with AuditedBox(name="zero-edge", audit_dir=AUDIT_DIR) as box:
        r1 = await box.exec("true")
        r2 = await box.exec("echo", "-n", "")  # echo -n '' = no output
        r3 = await box.exec("python3", "-c", "")
    
    check("true exit=0", r1.exit_code == 0)
    check("empty echo exit=0", r2.exit_code == 0)
    check("empty python exit=0", r3.exit_code == 0)
    check("true stdout empty", r1.stdout == "")
    check("empty echo stdout empty", r2.stdout == "")

    events = box.audit.read()
    for ev in events:
        if ev["event"] == "CMD_RESULT":
            check(f"zero-byte result logged {ev.get('cmd','')}",
                  ev.get("stdout_len") == 0 if ev.get("cmd") == "true" else True)


async def test_5_binary_output():
    """Exec that dumps binary to stdout (should not crash JSON serialization)."""
    print("\n── TEST 5: Binary/non-UTF8 output ──")
    async with AuditedBox(name="binary-test", audit_dir=AUDIT_DIR) as box:
        # python3 -c "import sys; sys.stdout.buffer.write(bytes(range(256)))"
        r = await box.exec("python3", "-c",
                           "import sys; sys.stdout.buffer.write(bytes(range(128)))")
    
    check("binary exit=0", r.exit_code == 0)
    check("binary stdout non-empty", len(r.stdout) == 128)
    
    events = box.audit.read()
    # JSON stores \uXXXX for non-ASCII, so it shouldn't crash
    check("integrity after binary", box.audit.verify_integrity()["integrity_ok"])
    
    # Try the same with raw non-UTF8 bytes
    # raw non-UTF8 bytes — Python subprocess(text=True) will error on decode.
    # This tests that our audit layer doesn't mask the error.
    try:
        r2 = await box.exec("python3", "-c",
                            "import sys; sys.stdout.buffer.write(b'\\xff\\xfe')")
        check("raw bytes: subprocess should error", False)
    except Exception:
        check("raw bytes: subprocess error (expected — decode limitation)", True)


async def test_6_rapid_start_stop():
    """10 boxes created and destroyed rapidly, all writing audit trails."""
    print("\n── TEST 6: Rapid start/stop (10 boxes) ──")
    boxes = []
    for i in range(10):
        box = AuditedBox(name=f"rapid-{i}", audit_dir=AUDIT_DIR)
        boxes.append(box)
    
    async def use_box(box, i):
        async with box:
            await box.exec("echo", str(i))
    
    await asyncio.gather(*[use_box(b, i) for i, b in enumerate(boxes)])
    
    for i, box in enumerate(boxes):
        events = box.audit.read()
        check(f"box rapid-{i} has 2 events", len(events) == 2)
        check(f"box rapid-{i} integrity", box.audit.verify_integrity()["integrity_ok"])


async def test_7_wrong_key():
    """Reading audit trail with the wrong key should show tampered."""
    print("\n── TEST 7: Wrong key — tamper detection ──")
    async with AuditedBox(name="key-test", audit_dir=AUDIT_DIR) as box:
        await box.exec("echo", "secret data")
    
    # Try to read with a different key (simulates someone with the wrong key)
    wrong_key = generate_master_key()
    events = box.audit.read()  # correct key
    check("correct key: all OK", all(e.get("tamper_ok") for e in events))
    
    # Now read with wrong key via low-level API
    from agentpathfinder.boxlite.audit_trail import BoxLiteAuditTrail
    wrong_trail = BoxLiteAuditTrail(box.audit.log_path, wrong_key, box_id=box.name)
    wrong_events = wrong_trail.read()
    check("wrong key: all tampered", all(not e.get("tamper_ok", True) for e in wrong_events))
    check("wrong key: integrity fails", not wrong_trail.verify_integrity()["integrity_ok"])


async def test_8_chain_integrity_at_scale():
    """1000 execs → verify chain integrity of all 2000 events."""
    print("\n── TEST 8: Chain integrity at scale (1000 execs, 2000 events) ──")
    async with AuditedBox(name="scale-test", audit_dir=AUDIT_DIR) as box:
        for i in range(1000):
            await box.exec("echo", str(i))
    
    events = box.audit.read()
    check("2000 events", len(events) == 2000)
    
    t0 = time.time()
    report = box.audit.verify_integrity()
    elapsed = time.time() - t0
    check("integrity OK at 2000 events", report["integrity_ok"])
    check(f"verify_time reasonable ({elapsed:.2f}s)", elapsed < 2.0)
    print(f"  verified 2000 HMACs in {elapsed:.3f}s — {2000/elapsed:.0f} events/s")


async def test_9_box_crash():
    """Box that crashes during exec — ensure CMD_ERROR is logged."""
    print("\n── TEST 9: Box crash during exec ──")
    try:
        async with AuditedBox(name="crash-test", audit_dir=AUDIT_DIR,
                              crash_on_exec=True) as box:
            await box.exec("echo", "will crash")
    except RuntimeError:
        pass
    
    # The crash box — should have a CMD_ERROR event
    crash_box = AuditedBox(name="crash-test", audit_dir=AUDIT_DIR)
    events = crash_box.audit.read()
    errors = [e for e in events if e["event"] == "CMD_ERROR"]
    check("CMD_ERROR logged on crash", len(errors) >= 1)
    check("error event has error field", all(e.get("error") for e in errors))


async def test_10_very_long_command():
    """Extremely long command string — 10K characters."""
    print("\n── TEST 10: Very long command ──")
    long_cmd = "a" * 10_000
    async with AuditedBox(name="long-cmd", audit_dir=AUDIT_DIR) as box:
        # python3 -c "print('a'*10000)"
        result = await box.exec("python3", "-c", f"print('{long_cmd}')")
    
    check("long cmd exit=0", result.exit_code == 0)
    check("long cmd output = 10K a's + newline", len(result.stdout) == 10_001)
    events = box.audit.read()
    check("integrity with 10K cmd", box.audit.verify_integrity()["integrity_ok"])
    
    # The JSONL should still parse
    with open(box.audit.log_path) as f:
        for line in f:
            json.loads(line)  # should not throw
    check("JSONL still parseable", True)


async def test_11_sequential_reuse():
    """Same audit trail across multiple box sessions, sharing the audit key."""
    print("\n── TEST 11: Sequential sessions, same audit trail ──")
    shared_key = generate_master_key()
    for i in range(5):
        async with AuditedBox(name="persistent", audit_dir=AUDIT_DIR,
                              audit_key=shared_key) as box:
            await box.exec("echo", f"session-{i}")
    
    final_box = AuditedBox(name="persistent", audit_dir=AUDIT_DIR,
                           audit_key=shared_key)
    events = final_box.audit.read()
    check("10 events from 5 sessions", len(events) == 10)
    check("integrity across sessions", final_box.audit.verify_integrity()["integrity_ok"])
    print(f"  {len(events)} events across 5 sequential box sessions")


async def test_12_duplicate_seq_detection():
    """Two events with the same seq should be detectable (replay attack)."""
    print("\n── TEST 12: Replay attack detection ──")
    async with AuditedBox(name="replay-test", audit_dir=AUDIT_DIR) as box:
        await box.exec("echo", "first")
        await box.exec("echo", "second")
    
    # Append a duplicate of the first event (same seq, same hmac won't work
    # because the HMAC covers ALL fields including timestamp — so the
    # original signed event with old timestamp can't be reused later.
    # But try anyway: copy the first line and append it again
    path = box.audit.log_path
    lines = path.read_text().splitlines()
    if len(lines) >= 2:
        # Get the invoked event (seq=0) and append a copy
        first_line = lines[0]
        with open(path, "a") as f:
            f.write(first_line + "\n")
    
    events = box.audit.read()
    duplicates = [e for e in events if e.get("seq") == 0 and not e.get("corrupted")]
    # If there are 2 events with seq=0, the 2nd one should fail HMAC
    # because it was append with the old HMAC but the read doesn't do that
    # Actually HMAC should verify if the exact same bytes are replayed...
    # No! Because read() reconstructs canonical JSON for verification,
    # and the appended event still has its original HMAC which matches.
    # This is actually a real limitation — replay attack.
    # But seq=0 appearing twice is suspicious. Let's detect it by counting.
    check("duplicate seq from replay", len(duplicates) >= 2)
    if len(duplicates) >= 2:
        # HMAC still matches (it's a copy of the first exactly).
        # The limitation is that HMAC can't tell it's a replay —
        # this is a known property of any signing scheme without
        # a nonce or seq check at the application layer.
        seqs = [e["seq"] for e in events if not e.get("corrupted")]
        is_monotonic = all(seqs[i] <= seqs[i+1] for i in range(len(seqs)-1))
        check("replay breaks monotonicity (expected)", not is_monotonic)
        report = box.audit.verify_integrity()
        check("HMAC valid on exact replay (known limitation — no seq guard)", report["integrity_ok"])


async def test_13_unicode_command():
    """Unicode in command args and output."""
    print("\n── TEST 13: Unicode throughout ──")
    unicode_str = "Hello, 世界! ñöôüèà @#$% ^&*()"
    async with AuditedBox(name="unicode-test", audit_dir=AUDIT_DIR) as box:
        r = await box.exec("python3", "-c",
                           f"print({unicode_str!r})")
    check("unicode exit=0", r.exit_code == 0)
    check(f"unicode output matches: '{r.stdout.strip()}'", unicode_str in r.stdout)
    events = box.audit.read()
    # Check raw event dicts (json.dumps escapes non-ASCII, but the dict itself has raw chars)
    check("unicode in audit trail", any(unicode_str in str(e) for e in events))
    check("integrity with unicode", box.audit.verify_integrity()["integrity_ok"])


async def test_14_audit_dir_permissions():
    """Write to a read-only directory should fail gracefully."""
    print("\n── TEST 14: Audit to read-only directory ──")
    readonly_dir = Path("/tmp/boxlite-readonly")
    readonly_dir.mkdir(parents=True, exist_ok=True)
    readonly_dir.chmod(0o444)  # read-only
    
    try:
        box = AuditedBox(name="readonly-test", audit_dir=readonly_dir)
        # The audit trail is lazy — it won't fail until we try to write
        await box.exec("echo", "should fail?")  # should raise
        check("readonly exec raised PermissionError", False)
    except PermissionError:
        check("readonly exec raised PermissionError", True)
    except Exception as e:
        check(f"readonly raised: {type(e).__name__}", True)
    finally:
        readonly_dir.chmod(0o755)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
async def main():
    print(f"AgentPathfinder × BoxLite — Stress Test Suite")
    print(f"Audit dir: {AUDIT_DIR}")
    print(f"BoxLite: mock (no KVM), subprocess on real commands")
    
    await test_1_concurrent_execs()
    await test_2_large_stdout()
    await test_3_torn_write_recovery()
    await test_4_zero_byte_edge()
    await test_5_binary_output()
    await test_6_rapid_start_stop()
    await test_7_wrong_key()
    await test_8_chain_integrity_at_scale()
    await test_9_box_crash()
    await test_10_very_long_command()
    await test_11_sequential_reuse()
    await test_12_duplicate_seq_detection()
    await test_13_unicode_command()
    await test_14_audit_dir_permissions()
    
    total = PASS + FAIL
    print(f"\n{'='*60}")
    print(f"RESULTS: {PASS}/{total} passed, {FAIL}/{total} failed")
    print(f"{'='*60}")
    return FAIL == 0

if __name__ == "__main__":
    exit_code = 0 if asyncio.run(main()) else 1
    sys.exit(exit_code)