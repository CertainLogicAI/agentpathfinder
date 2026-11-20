"""AgentPathfinder BoxLite — AuditedBox: drop-in SimpleBox with HMAC-signed exec audit.

Usage::

    from agentpathfinder.boxlite import AuditedBox

    async with AuditedBox(image="python:slim") as box:
        result = await box.exec("python", "-c", "print('hello')")
        # result is the normal BoxLite ExecResult

    # Replay audit trail
    for event in box.audit.read():
        print(event["event"], event["tamper_ok"])
"""

import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from agentpathfinder.pathfinder_core import derive_key, generate_master_key
from .audit_trail import BoxLiteAuditTrail

__all__ = ["AuditedBox"]


_DEFAULT_AUDIT_DIR = Path.home() / ".agentpathfinder" / "audit"


def _default_box_name() -> str:
    return f"audited-{uuid.uuid4().hex[:12]}"


class AuditedBox:
    """Drop-in wrapper around :class:`~boxlite.simplebox.SimpleBox` that
    cryptographically signs every exec command with an HMAC-SHA256 audit trail.

    All SimpleBox methods (async context manager, exec, copy_in/out, stop, info,
    etc.) work identically.  The only difference is that every exec is logged
    to a tamper-evident audit file on the host filesystem.

    The signing key *never* enters the BoxLite microVM — it stays on the host.

    Args:
        audit_key: HMAC signing key (32 bytes).  Auto-generated if omitted.
        audit_dir: Directory on the host for the JSONL audit file.
        name: BoxLite box name.  Auto-generated if omitted.
        **kwargs: Forwarded to :class:`~boxlite.simplebox.SimpleBox`.
    """

    def __init__(
        self,
        audit_key: Optional[bytes] = None,
        audit_dir: Optional[Path] = None,
        name: Optional[str] = None,
        **kwargs: Any,
    ):
        from boxlite.simplebox import SimpleBox

        name = name or _default_box_name()
        self._name = name
        self._box = SimpleBox(name=name, **kwargs)

        # Audit key (host-side only)
        if audit_key is None:
            audit_key = generate_master_key()
        else:
            audit_key = derive_key(audit_key, b"boxlite-audit-v1")
        self._audit_key: bytes = audit_key
        self._audit_dir: Path = Path(audit_dir or _DEFAULT_AUDIT_DIR)
        self._audit_trail: Optional[BoxLiteAuditTrail] = None

    # -- properties ------------------------------------------------------------

    @property
    def name(self) -> str:
        """Box name (used as audit file name on the host)."""
        return self._name

    @property
    def audit(self) -> BoxLiteAuditTrail:
        """The :class:`BoxLiteAuditTrail` (lazy-init)."""
        if self._audit_trail is None:
            self._audit_trail = BoxLiteAuditTrail(
                log_path=self._audit_dir / f"{self.name}.jsonl",
                signing_key=self._audit_key,
                box_id=self.name,
            )
        return self._audit_trail

    # -- context manager (delegated) -------------------------------------------

    async def __aenter__(self):
        await self._box.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self._box.__aexit__(exc_type, exc_val, exc_tb)

    async def start(self):
        await self._box.start()
        return self

    @property
    def id(self) -> str:
        return self._box.id

    @property
    def created(self) -> Optional[bool]:
        return self._box.created

    def info(self):
        return self._box.info()

    async def stop(self):
        await self._box.stop()

    async def shutdown(self):
        await self._box.shutdown()

    async def copy_in(self, host_path: str, container_dest: str, **kwargs: Any) -> None:
        await self._box.copy_in(host_path, container_dest, **kwargs)

    async def copy_out(self, container_src: str, host_dest: str, **kwargs: Any) -> None:
        await self._box.copy_out(container_src, host_dest, **kwargs)

    # -- audited exec ----------------------------------------------------------

    async def exec(
        self,
        cmd: str,
        *args: str,
        env: Optional[Dict[str, str]] = None,
        user: Optional[str] = None,
        timeout: Optional[float] = None,
        cwd: Optional[str] = None,
    ) -> "ExecResult":  # noqa: F821  (runtime import)
        """Execute a command with HMAC-signed audit logging.

        All arguments and return value match :class:`~boxlite.simplebox.SimpleBox.exec`.
        """
        from boxlite.exec import ExecResult

        # Log invocation
        self.audit.log(
            "CMD_INVOKED",
            cmd=cmd,
            args=list(args) if args else None,
            env=list(env.keys()) if env else None,
            user=user,
            timeout=timeout,
            cwd=cwd,
        )

        import time as _time
        _start = _time.monotonic()

        # Actual execution via the underlying SimpleBox
        try:
            result: ExecResult = await self._box.exec(
                cmd, *args,
                env=env,
                user=user,
                timeout=timeout,
                cwd=cwd,
            )
        except BaseException as exc:
            _elapsed = _time.monotonic() - _start
            self.audit.log(
                "CMD_ERROR",
                cmd=cmd,
                args=list(args) if args else None,
                error=f"{type(exc).__name__}: {exc}",
                duration_ms=round(_elapsed * 1000),
            )
            raise

        _elapsed = _time.monotonic() - _start

        # Log result
        self.audit.log(
            "CMD_RESULT",
            cmd=cmd,
            exit_code=result.exit_code,
            stdout_len=len(result.stdout or ""),
            stderr_len=len(result.stderr or ""),
            error_message=result.error_message,
            duration_ms=round(_elapsed * 1000),
        )

        return result