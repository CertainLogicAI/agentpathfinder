#!/usr/bin/env python3
"""AgentPathfinder v2 — ClawHub CLI client and SDK wrapper.

Deterministic task orchestration with cryptographic sharding.
Usage:
    from pathfinder_client import PathfinderClient
    client = PathfinderClient()
    task_id = client.create("deploy", ["build", "push", "verify"])
    client.run(task_id)
    print(client.status(task_id))
"""

import argparse
import json
import os
import sys
import time
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

# ── Import resolution ───────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR.parent))
from agentpathfinder import (
    TaskEngine, IssuingLayer, AgentRuntime, AuditTrail,
    generate_master_key, split_key, reconstruct_key,
    hmac_sign, verify_hmac, hash_key, derive_key,
)

# Import visual helpers
from visual import (
    fmt_status, fmt_audit_event, fmt_step_complete, fmt_step_failed,
    fmt_task_complete, fmt_task_failed, fmt_reconstruct_ok, fmt_reconstruct_fail,
    fmt_agent_registered, fmt_dashboard_url, fmt_brain_stats, fmt_install_ready,
    fmt_crash_recovery, PASS, FAIL, SPINNER, INFO, badge_ok, badge_fail,
    green, red, yellow, bold, dim,
)

# ── Config ─────────────────────────────────────────────────────────
DATA_DIR = Path(os.getenv("PATHFINDER_DATA_DIR", "./pathfinder_data"))
DASHBOARD_PORT = int(os.getenv("PATHFINDER_DASHBOARD_PORT", "8080"))


class PathfinderClient:
    """SDK wrapper around AgentPathfinder v2 core."""

    def __init__(self, data_dir: Path = None):
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self.engine = TaskEngine(data_dir=self.data_dir)
        self.issuing = IssuingLayer(self.engine)
        self.runtime = AgentRuntime(self.engine, self.issuing)

    # ── Tasks ─────────────────────────────────────────────────────

    def create(self, name: str, steps: List[str]) -> str:
        """Create a new task. Returns the task_id."""
        step_specs = [{"name": s} for s in steps]
        return self.engine.create_task(name, step_specs)

    def run(self, task_id: str) -> Dict[str, Any]:
        """Simulate running all steps and attempt reconstruction."""
        task = self.engine.get_task(task_id)
        for step in task["steps"]:
            sn = step["step_number"]
            if step["state"] in ("pending", "running"):
                result_str = f"simulated_result_for_step_{sn}"
                result_hash = hash_key(result_str.encode())[:16]
                self.issuing.issue_step_token(task_id, sn, result_str, result_hash)
        self.issuing.reconstruct_master_key(task_id)
        return self.engine.get_status(task_id)

    def status(self, task_id: str) -> Dict[str, Any]:
        return self.engine.get_status(task_id)

    def audit(self, task_id: str) -> List[Dict[str, Any]]:
        task = self.engine.get_task(task_id)
        master_key = self.engine._reconstruct_master_key(task)
        audit_key = self.engine._derive_audit_key(master_key)
        audit = AuditTrail(
            self.engine.data_dir / "audit" / f"{task_id}.jsonl",
            audit_key,
        )
        return audit.read_trail(task_id)

    def reconstruct(self, task_id: str) -> Optional[bytes]:
        return self.issuing.reconstruct_master_key(task_id)

    # ── Agents ────────────────────────────────────────────────────

    def register_agent(self, agent_id: str) -> str:
        return self.engine.register_agent(agent_id)

    def verify_agent(self, agent_id: str, api_key: str) -> bool:
        return self.engine.verify_agent(agent_id, api_key)

    # ── Brain Stats ───────────────────────────────────────────────

    def brain_stats(self) -> Optional[Dict[str, Any]]:
        """Load Brain API metrics from metrics.json if available."""
        metrics_path = self.data_dir.parent / "metrics.json"
        if not metrics_path.exists():
            # Try alternate locations
            for alt in [
                Path("./metrics.json"),
                Path("../metrics.json"),
                self.data_dir / "metrics.json",
            ]:
                if alt.exists():
                    metrics_path = alt
                    break
            else:
                return None
        try:
            with open(metrics_path) as f:
                return json.load(f)
        except Exception:
            return None


# ── CLI Handlers with Visual Confirmations ────────────────────────

def cli_create(args):
    client = PathfinderClient()
    name = args.name
    steps = args.steps or ["step_1"]
    task_id = client.create(name, steps)
    print(f"{PASS} Task created: {bold(task_id)}")
    print(f"   {INFO} Name: {name}")
    print(f"   {INFO} Steps: {len(steps)}")
    return task_id


def cli_run(args):
    client = PathfinderClient()
    print(f"{WARN} SIMULATION MODE — No real code executed.")
    print(f"    Use Python SDK for production execution.")
    print(f"    Docs: github.com/CertainLogicAI/agentpathfinder#sdk
")
    print(f"{SPINNER} Running task {dim(args.task_id)}...")
    status = client.run(args.task_id)
    print("")
    if status["overall_state"] == "task_complete":
        print(fmt_task_complete(status["name"], args.task_id))
        print(f"   {bold('Progress:')} {green(status['progress'])}")
        for step in status["steps"]:
            if step["state"] == "complete":
                print(f"   {fmt_step_complete(step['step_number'], step['name'], step.get('token_id',''))}")
    else:
        print(fmt_task_failed(status["name"], args.task_id, "Not all steps completed"))
        for step in status["steps"]:
            if step["state"] == "failed":
                print(f"   {fmt_step_failed(step['step_number'], step['name'], step.get('error','Unknown error'))}")
    print("")
    print(fmt_status(status))
    return status


def cli_status(args):
    client = PathfinderClient()
    try:
        status = client.status(args.task_id)
        print(fmt_status(status))
        # Crash recovery check
        if any(s["state"] == "running" for s in status["steps"]):
            print("")
            print(f"{FAIL} {bold('WARNING:')} Steps stuck in 'running' — possible crash.")
            print(f"   {INFO} Use {bold('pf reset-step')} or check logs.")
    except ValueError as e:
        print(f"{FAIL} {e}")


def cli_audit(args):
    client = PathfinderClient()
    try:
        events = client.audit(args.task_id)
        print(f"\n{bold('Audit Trail for')} {dim(args.task_id)}:")
        for ev in events:
            print(fmt_audit_event(ev))
        tampered = sum(1 for e in events if not e.get("tamper_ok", True))
        print("")
        if tampered == 0:
            print(badge_ok(f"All {len(events)} events verified"))
        else:
            print(badge_fail(f"{tampered} of {len(events)} events TAMPERED"))
    except Exception as e:
        print(f"{FAIL} Audit failed: {e}")


def cli_reconstruct(args):
    client = PathfinderClient()
    key = client.reconstruct(args.task_id)
    if key:
        task = client.engine.get_task(args.task_id)
        print(fmt_reconstruct_ok(task["key_hash"]))
    else:
        print(fmt_reconstruct_fail())
    return key


def cli_register_agent(args):
    client = PathfinderClient()
    api_key = client.register_agent(args.agent_id)
    print(fmt_agent_registered(args.agent_id, api_key))
    return api_key


def cli_dashboard(args):
    """Start the web dashboard."""
    dashboard_script = Path(__file__).parent / "dashboard.py"
    if not dashboard_script.exists():
        print(f"{FAIL} Dashboard server not found: {dashboard_script}")
        sys.exit(1)
    port = args.port if hasattr(args, "port") else DASHBOARD_PORT
    print(f"{SPINNER} Starting dashboard on port {port}...")
    try:
        subprocess.run([sys.executable, str(dashboard_script), "--port", str(port)], check=True)
    except KeyboardInterrupt:
        print(f"\n{INFO} Dashboard stopped.")
    except Exception as e:
        print(f"{FAIL} Dashboard failed: {e}")


def cli_install(args):
    """One-command setup: init data dir, print ready message."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "tasks").mkdir(exist_ok=True)
    (DATA_DIR / "vault").mkdir(exist_ok=True)
    (DATA_DIR / "audit").mkdir(exist_ok=True)
    (DATA_DIR / "agents").mkdir(exist_ok=True)
    print(fmt_install_ready())
    # Try to show brain stats if available
    client = PathfinderClient()
    stats = client.brain_stats()
    if stats:
        print(fmt_brain_stats(stats))


def main():
    parser = argparse.ArgumentParser(
        description="AgentPathfinder v2 — Deterministic task orchestration"
    )
    sub = parser.add_subparsers(dest="command")

    # create
    p_create = sub.add_parser("create", help="Create a new task")
    p_create.add_argument("name", help="Task name")
    p_create.add_argument("steps", nargs="*", help="Step names")
    p_create.set_defaults(func=cli_create)

    # run
    p_run = sub.add_parser("run", help="Simulate running all steps")
    p_run.add_argument("task_id", help="Task ID")
    p_run.set_defaults(func=cli_run)

    # status
    p_status = sub.add_parser("status", help="Show task status")
    p_status.add_argument("task_id", help="Task ID")
    p_status.set_defaults(func=cli_status)

    # audit
    p_audit = sub.add_parser("audit", help="Show audit trail")
    p_audit.add_argument("task_id", help="Task ID")
    p_audit.set_defaults(func=cli_audit)

    # reconstruct
    p_recon = sub.add_parser("reconstruct", help="Reconstruct master key")
    p_recon.add_argument("task_id", help="Task ID")
    p_recon.set_defaults(func=cli_reconstruct)

    # register-agent
    p_agent = sub.add_parser("register-agent", help="Register a new agent")
    p_agent.add_argument("agent_id", help="Agent identifier")
    p_agent.set_defaults(func=cli_register_agent)

    # dashboard
    p_dash = sub.add_parser("dashboard", help="Start web dashboard")
    p_dash.add_argument("--port", "-p", type=int, default=DASHBOARD_PORT, help="Port (default 8080)")
    p_dash.add_argument("--start", action="store_true", default=True, help="Start the server")
    p_dash.set_defaults(func=cli_dashboard)

    # install / setup
    p_install = sub.add_parser("install", help="One-command setup")
    p_install.set_defaults(func=cli_install)

    args = parser.parse_args()
    if hasattr(args, "func"):
        try:
            args.func(args)
        except ValueError as e:
            print(f"{FAIL} {e}")
            sys.exit(1)
        except FileNotFoundError as e:
            print(f"{FAIL} {e}")
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
