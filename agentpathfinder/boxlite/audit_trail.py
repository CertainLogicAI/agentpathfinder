"""AgentPathfinder BoxLite — HMAC-signed audit log for BoxLite executions.

Stores audit events as a JSONL file, each event HMAC-SHA256 signed
using the Pathfinder core. Written to host-side storage (never inside the VM).
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from agentpathfinder.pathfinder_core import hmac_sign, verify_hmac


class BoxLiteAuditTrail:
    """Append-only, HMAC-signed audit log for BoxLite exec commands.

    Each event is canonically JSON-serialized and HMAC-SHA256 signed
    before writing.  Readback verifies every event signature, reporting
    any tampered or corrupted entries.

    Args:
        log_path: Path to the JSONL audit file (on the host filesystem).
        signing_key: HMAC-SHA256 key (derived audit key, never raw master).
        box_id: The BoxLite box identifier (recorded with every event).
    """

    def __init__(
        self,
        log_path: Path,
        signing_key: bytes,
        box_id: str = "unknown",
    ):
        self.log_path = Path(log_path)
        self.signing_key = signing_key
        self.box_id = box_id
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    # --- helpers ----------------------------------------------------------------

    @staticmethod
    def _canonical(event: Dict[str, Any]) -> str:
        return json.dumps(event, sort_keys=True, default=str)

    @staticmethod
    def _now() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def _next_seq(self) -> int:
        if not self.log_path.exists():
            return 0
        count = 0
        with open(self.log_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    count += 1
        return count

    # --- public API -------------------------------------------------------------

    def log(self, event_type: str, *, task_id: str = "", **kwargs: Any) -> Dict[str, Any]:
        """Append a signed event to the audit trail.

        Args:
            event_type: Short label (e.g. CMD_INVOKED, CMD_RESULT).
            task_id: Optional caller-supplied identifier.
            **kwargs: Any extra fields to include in the event.

        Returns:
            The full event dict (including the ``hmac`` field).
        """
        event: Dict[str, Any] = {
            "event": event_type,
            "box_id": self.box_id,
            "task_id": task_id,
            "timestamp": self._now(),
            "seq": self._next_seq(),
        }
        event.update(kwargs)

        canonical = self._canonical(event)
        event["hmac"] = hmac_sign(self.signing_key, canonical)

        with open(self.log_path, "a") as f:
            f.write(json.dumps(event, default=str) + "\n")

        return event

    def read(self, task_id: Optional[str] = None) -> list:
        """Read and verify the entire audit trail.

        Args:
            task_id: If given, only events matching this task_id are returned.

        Returns:
            List of event dicts, each with a ``tamper_ok`` field.
            Corrupted lines are returned as ``{"corrupted": True, "raw": ...}``.
        """
        if not self.log_path.exists():
            return []

        events: list = []
        with open(self.log_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event: Dict[str, Any] = json.loads(line)
                except json.JSONDecodeError:
                    events.append({"corrupted": True, "raw": line})
                    continue

                if task_id and event.get("task_id") != task_id:
                    continue

                stored_hmac = event.pop("hmac", "")
                canonical = json.dumps(event, sort_keys=True, default=str)
                event["tamper_ok"] = verify_hmac(
                    self.signing_key, canonical, stored_hmac
                )
                event["hmac_prefix"] = stored_hmac[:16] + "..." if stored_hmac else ""
                events.append(event)

        return events

    def verify_integrity(self) -> Dict[str, Any]:
        """Verify every event in the audit trail.

        Returns:
            Dict with ``total_events``, ``tampered``, ``corrupted``, ``integrity_ok``.
        """
        events = self.read()
        total = len(events)
        tampered = sum(1 for e in events if not e.get("tamper_ok", True))
        corrupted = sum(1 for e in events if e.get("corrupted", False))

        return {
            "total_events": total,
            "tampered": tampered,
            "corrupted": corrupted,
            "integrity_ok": tampered == 0 and corrupted == 0,
        }