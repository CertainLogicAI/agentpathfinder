#!/usr/bin/env python3
"""Client CLI for AgentPathfinder.

Usage:
    pf create <name> <step1> [<step2> ...]  — Create a new task
    pf status <task_id>                     — Show task status
    pf audit <task_id>                      — Verify HMAC signatures
    pf reset <task_id> <step_name>          — Reset a step
    pf dash <task_id>                       — Generate dashboard
    pf doctor                               — Check installation
"""

import sys
import json
from pathlib import Path

# Add parent dir to path if running from source
try:
    from agentpathfinder import TaskEngine
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from agentpathfinder import TaskEngine


def create_task(args):
    if len(args) < 2:
        print("Usage: pf create <name> <step1> [<step2> ...]")
        sys.exit(1)
    engine = TaskEngine()
    name = args[0]
    steps = [{"name": s} for s in args[1:]]
    task_id = engine.create_task(name, steps)
    print(f"Task created: {task_id}")
    print(f"Steps: {', '.join(args[1:])}")
    return task_id


def show_status(args):
    if len(args) < 1:
        print("Usage: pf status <task_id>")
        sys.exit(1)
    engine = TaskEngine()
    status = engine.get_status(args[0])
    print(f"Task: {status['name']}")
    print(f"State: {status['state']}")
    for step in status.get("steps", []):
        icon = "✅" if step["status"] == "complete" else "⏳" if step["status"] == "running" else "⏸️"
        print(f"  {icon} {step['name']}: {step['status']}")


def audit_task(args):
    if len(args) < 1:
        print("Usage: pf audit <task_id>")
        sys.exit(1)
    engine = TaskEngine()
    result = engine.audit_trail(args[0])  # backward compat alias
    print(f"Events: {result['event_count']}")
    print(f"HMAC valid: {result['all_hmac_valid']}")
    for ev in result.get("events", [])[:5]:
        t = ev.get("event_type", "?")
        s = ev.get("status", "")
        print(f"  {t}: {s}")


def reset_step(args):
    if len(args) < 2:
        print("Usage: pf reset <task_id> <step_name>")
        sys.exit(1)
    engine = TaskEngine()
    # Find step number by name
    task = engine.get_task(args[0])
    step_name = args[1]
    step_num = None
    for i, s in enumerate(task.get("steps", [])):
        if s.get("name") == step_name:
            step_num = i
            break
    if step_num is None:
        print(f"Step '{step_name}' not found")
        sys.exit(1)
    engine.reset_step(args[0], step_num)
    print(f"Step '{step_name}' reset")


def generate_dashboard(args):
    if len(args) < 1:
        print("Usage: pf dash <task_id>")
        sys.exit(1)
    task_id = args[0]
    import subprocess
    dashboard_script = Path(__file__).parent / "dashboard_v130.py"
    if not dashboard_script.exists():
        print("Dashboard script not found. Install with: pip install agentpathfinder[dashboard]")
        sys.exit(1)
    print(f"Generating dashboard for {task_id}...")
    subprocess.run([sys.executable, str(dashboard_script), "generate", "--task", task_id])


def doctor_check():
    print("AgentPathfinder Installation Check")
    print("=" * 40)
    issues = []

    # Check package import
    try:
        from agentpathfinder import TaskEngine, ToolAuditChain
        print("✅ Package import: OK")
    except ImportError as e:
        print(f"❌ Package import: FAILED ({e})")
        issues.append("import")

    # Check data dir
    engine = TaskEngine()
    if engine.data_dir.exists():
        print(f"✅ Data directory: {engine.data_dir}")
    else:
        print(f"⚠️  Data directory missing (will be created): {engine.data_dir}")

    # Check dashboard script
    dash = Path(__file__).parent / "dashboard_v130.py"
    if dash.exists():
        print("✅ Dashboard script: found")
    else:
        print("⚠️  Dashboard script: not found (install with [dashboard] extra)")

    # Check version
    try:
        import agentpathfinder
        ver = getattr(agentpathfinder, '__version__', 'unknown')
        print(f"✅ Version: {ver}")
    except Exception:
        print("⚠️  Version: unknown")

    print()
    if issues:
        print(f"❌ Found {len(issues)} issue(s). Please reinstall.")
        sys.exit(1)
    else:
        print("✅ All checks passed. Ready to use.")


def main():
    if len(sys.argv) < 2:
        print("AgentPathfinder CLI")
        print("Usage: pf <command> [args...]")
        print("Commands: create, status, audit, reset, dash, doctor")
        sys.exit(0)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    handlers = {
        "create": create_task,
        "status": show_status,
        "audit": audit_task,
        "reset": reset_step,
        "dash": generate_dashboard,
        "doctor": doctor_check,
    }

    handler = handlers.get(cmd)
    if handler is None:
        print(f"Unknown command: {cmd}")
        print("Commands: create, status, audit, reset, dash, doctor")
        sys.exit(1)

    # doctor takes no args
    if cmd == "doctor":
        doctor_check()
    else:
        handler(args)


if __name__ == "__main__":
    main()
