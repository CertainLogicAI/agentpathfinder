#!/usr/bin/env python3
"""Tests for AgentPathfinder BoxLite audit module (no BoxLite runtime needed)."""
import json
import tempfile
from pathlib import Path
from agentpathfinder.pathfinder_core import generate_master_key
from agentpathfinder.boxlite.audit_trail import BoxLiteAuditTrail


def test_audit_trail_roundtrip():
    key = generate_master_key()
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "test-box.jsonl"
        trail = BoxLiteAuditTrail(log_path, key, box_id="test-box")

        # Log events
        e1 = trail.log("CMD_INVOKED", cmd="echo", args=["hello"])
        e2 = trail.log("CMD_RESULT", cmd="echo", exit_code=0, stdout_len=5)
        assert e1["event"] == "CMD_INVOKED"
        assert e2["event"] == "CMD_RESULT"
        assert e2["seq"] == 1  # 1-indexed-ish, starts at 0

        # Read back
        events = trail.read()
        assert len(events) == 2
        for ev in events:
            assert ev["tamper_ok"] is True, f"tampered: {ev}"
            assert "hmac" not in ev  # stripped during read

        # Integrity check
        report = trail.verify_integrity()
        assert report["integrity_ok"] is True
        assert report["total_events"] == 2

        # Tamper simulation — append a forged event to the JSONL
        # (simulates someone inserting a fake log entry)
        forged = r'{"event":"CMD_INVOKED","box_id":"test-box","cmd":"rm -rf /","seq":99,"hmac":"00000000000000000000000000000000"}' + chr(10)
        with open(log_path, 'a') as f:
            f.write(forged)

        report = trail.verify_integrity()
        assert report["integrity_ok"] is False
        assert report["tampered"] >= 1

        print("  ✓ audit trail round-trip: pass")
        print(f"  ✓ tamper detection:  {report['tampered']} tampered of {report['total_events']}")


def test_audit_trail_filter():
    key = generate_master_key()
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "filter.jsonl"
        trail = BoxLiteAuditTrail(log_path, key, box_id="box1")

        trail.log("CMD_INVOKED", task_id="task-a", cmd="ls")
        trail.log("CMD_INVOKED", task_id="task-b", cmd="pwd")
        trail.log("CMD_INVOKED", task_id="task-a", cmd="echo")

        all_events = trail.read()
        assert len(all_events) == 3

        filtered = trail.read(task_id="task-a")
        assert len(filtered) == 2
        for ev in filtered:
            assert ev["task_id"] == "task-a"

        print(f"  ✓ filter by task_id: {len(filtered)} of {len(all_events)}")


def test_audit_trail_corruption():
    key = generate_master_key()
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "corrupt.jsonl"
        trail = BoxLiteAuditTrail(log_path, key, box_id="box1")

        trail.log("CMD_INVOKED", cmd="ls")
        # Inject a non-JSON line
        with open(log_path, "a") as f:
            f.write("NOT JSON\n")
        trail.log("CMD_RESULT", cmd="ls", exit_code=0)

        events = trail.read()
        assert len(events) == 3
        corrupted = [e for e in events if e.get("corrupted")]
        assert len(corrupted) == 1

        report = trail.verify_integrity()
        assert report["corrupted"] == 1
        assert report["integrity_ok"] is False

        print(f"  ✓ corruption detection: {report['corrupted']} corrupted")


if __name__ == "__main__":
    print("AgentPathfinder × BoxLite — audit trail tests\n")
    test_audit_trail_roundtrip()
    test_audit_trail_filter()
    test_audit_trail_corruption()
    print("\nAll tests passed.")