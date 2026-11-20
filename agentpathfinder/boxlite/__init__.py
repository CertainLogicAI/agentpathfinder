"""AgentPathfinder × BoxLite — HMAC-audited microVM exec.

Provides :class:`AuditedBox`, a drop-in replacement for
:class:`boxlite.simplebox.SimpleBox` that cryptographically signs
every exec command with an HMAC-SHA256 audit trail.

Usage::

    from agentpathfinder.boxlite import AuditedBox

    async with AuditedBox(image="python:slim") as box:
        result = await box.exec("python", "-c", "print(2 + 2)")
        print(result.stdout)                     # "4"
        print(box.audit.verify_integrity())       # {"integrity_ok": True}
"""

from .audited_box import AuditedBox
from .audit_trail import BoxLiteAuditTrail

__all__ = [
    "AuditedBox",
    "BoxLiteAuditTrail",
]