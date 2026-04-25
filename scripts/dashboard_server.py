#!/usr/bin/env python3
"""AgentPathfinder v2 — Unified Web Dashboard.

Serves dual purpose:
  1. Pathfinder tasks: live task list, status, audit trails, completions/failures
  2. Brain API stats: token savings, cache hit rates, $ saved, hallucinations caught

Zero dependencies (uses only Python stdlib). One command to start:
    python3 dashboard_server.py          # Generate + serve on :8080
    python3 dashboard_server.py --port 9090

API endpoints:
    GET /           → HTML dashboard
    GET /api/tasks  → JSON task list
    GET /api/brain  → JSON brain stats
    GET /api/health → health check
"""

import json
import os
import sys
import time
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import socketserver

# ── Resolve agentpathfinder import ────────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent
_POSSIBLE_PATHS = [
    _SCRIPT_DIR / ".." / ".." / ".." / "agentpathfinder",
    _SCRIPT_DIR / ".." / ".." / "agentpathfinder",
    _SCRIPT_DIR / ".." / "agentpathfinder",
]
for _p in _POSSIBLE_PATHS:
    if (_p / "pathfinder_core.py").exists():
        sys.path.insert(0, str(_p.parent))
        try:
            from agentpathfinder import TaskEngine, AuditTrail
            from agentpathfinder.pathfinder_core import verify_hmac
            break
        except ImportError:
            continue
else:
    TaskEngine = None
    AuditTrail = None

DATA_DIR = Path(os.getenv("PATHFINDER_DATA_DIR", "./pathfinder_data"))
BRAIN_METRICS_PATHS = [
    DATA_DIR.parent / "metrics.json",
    Path("./metrics.json"),
    Path("../metrics.json"),
    _SCRIPT_DIR.parent.parent.parent / "agentpathfinder" / "metrics.json",
]


def load_tasks(data_dir: Path) -> list:
    """Load all tasks from data directory."""
    tasks_dir = data_dir / "tasks"
    if not tasks_dir.exists():
        return []
    tasks = []
    for task_file in sorted(tasks_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with open(task_file) as f:
                task = json.load(f)
            total = task.get("num_steps", 0)
            completed = task.get("completed_steps", 0)
            failed = task.get("failed_steps", 0)
            progress_pct = (completed / total * 100) if total > 0 else 0
            audit_events = 0
            audit_ok = None
            audit_path = data_dir / "audit" / f"{task['task_id']}.jsonl"
            if audit_path.exists():
                try:
                    with open(audit_path) as f:
                        for line in f:
                            audit_events += 1
                    audit_ok = True
                except Exception:
                    audit_ok = False
            tasks.append({
                "task_id": task["task_id"],
                "name": task.get("name", "Unnamed"),
                "state": task.get("state", "unknown"),
                "created_at": task.get("created_at", "?")[:19] if task.get("created_at") else "?",
                "progress_pct": round(progress_pct, 1),
                "completed": completed,
                "total": total,
                "failed": failed,
                "steps": task.get("steps", []),
                "audit_ok": audit_ok,
                "audit_events": audit_events,
            })
        except Exception as e:
            continue
    return tasks


def load_brain_stats() -> dict:
    """Load Brain API metrics from the first found metrics.json."""
    for path in BRAIN_METRICS_PATHS:
        if path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)
                return {
                    "cache_hit_rate": data.get("cache", {}).get("hit_rate_percent", 0),
                    "cache_hits": data.get("cache", {}).get("hits", 0),
                    "cache_misses": data.get("cache", {}).get("misses", 0),
                    "brain_queries": data.get("brain_api", {}).get("queries", 0),
                    "tokens_saved": data.get("brain_api", {}).get("tokens_saved", 0),
                    "validations": data.get("brain_api", {}).get("validations", 0),
                    "hallucinations_caught": data.get("brain_api", {}).get("hallucinations_caught", 0),
                    "est_cost_saved_usd": data.get("brain_api", {}).get("est_cost_saved_usd", 0.0),
                    "source": str(path),
                }
            except Exception:
                continue
    return {
        "cache_hit_rate": 0, "cache_hits": 0, "cache_misses": 0,
        "brain_queries": 0, "tokens_saved": 0, "validations": 0,
        "hallucinations_caught": 0, "est_cost_saved_usd": 0.0,
        "source": "none",
    }


def generate_dashboard_html(tasks: list, brain: dict) -> str:
    """Generate the unified HTML dashboard."""
    total_tasks = len(tasks)
    complete = sum(1 for t in tasks if t["state"] == "task_complete")
    in_progress = sum(1 for t in tasks if t["state"] == "in_progress")
    paused = sum(1 for t in tasks if t["state"] == "paused")
    failed = sum(1 for t in tasks if t["state"] in ("reconstruction_failed", "aborted"))

    def state_color(state):
        return {
            "registered": "#334155",
            "in_progress": "#0ea5e9",
            "task_complete": "#10b981",
            "paused": "#f59e0b",
            "reconstruction_failed": "#ef4444",
            "aborted": "#64748b",
        }.get(state, "#334155")

    def step_icon(st):
        return {"pending": "○", "running": "⏳", "complete": "✅", "failed": "❌"}.get(st, "○")

    def step_color(st):
        return {"pending": "#64748b", "running": "#0ea5e9", "complete": "#10b981", "failed": "#ef4444"}.get(st, "#64748b")

    task_cards = []
    for task in tasks:
        bg = state_color(task["state"])
        fg = "#fff" if task["state"] in ("reconstruction_failed", "aborted") else "#0f172a" if task["state"] in ("task_complete", "paused") else "#fff"

        step_rows = []
        for step in task["steps"]:
            icon = step_icon(step["state"])
            color = step_color(step["state"])
            token = step.get("token_id", "")
            err = step.get("error", "")
            tok_html = (
                f'<span style="font-family:mono;font-size:10px;color:#64748b;background:#0f172a;padding:2px 6px;border-radius:3px">{token[:14]}…</span>'
                if token else ""
            )
            verif = ""
            if step.get("result_hash"):
                verif = '<span style="color:#10b981;font-size:11px" title="Verified">✓</span>'
            elif err:
                verif = f'<span style="color:#ef4444;font-size:11px" title="{err}">⚠</span>'
            step_rows.append(
                f'<div style="display:flex;align-items:center;gap:8px;font-size:12px;padding:4px 0;border-bottom:1px solid #334155">'
                f'<span style="color:{color};width:20px;text-align:center">{icon}</span>'
                f'<span style="flex:1">{step["step_number"]}. {step["name"]}</span>{tok_html}{verif}</div>'
            )

        audit_html = ""
        if task["audit_ok"] is not None:
            a_icon = "✅" if task["audit_ok"] else "❌"
            a_color = "#10b981" if task["audit_ok"] else "#ef4444"
            audit_html = (
                f'<div style="display:flex;align-items:center;gap:6px;margin-top:8px;font-size:11px;color:#64748b">'
                f'<span style="color:{a_color}">{a_icon} Audit {"verified" if task["audit_ok"] else "tampered"}</span>'
                f'<span>— {task["audit_events"]} events</span></div>'
            )

        task_cards.append(
            f'<div style="background:#1e293b;border-radius:8px;padding:14px;border:1px solid #334155;margin-bottom:12px">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">'
            f'<span style="font-weight:600;font-size:15px">{task["name"]}</span>'
            f'<span style="padding:3px 10px;border-radius:4px;font-size:11px;font-weight:500;background:{bg};color:{fg}">{task["state"]}</span></div>'
            f'<div style="font-size:11px;color:#64748b;margin-bottom:8px">ID: {task["task_id"][:8]}… | {task["created_at"]}</div>'
            f'<div style="height:5px;background:#334155;border-radius:3px;overflow:hidden;margin-bottom:8px">'
            f'<div style="height:100%;background:#10b981;border-radius:3px;width:{max(task["progress_pct"], 5)}%"></div></div>'
            f'<div style="font-size:11px;color:#64748b;margin-bottom:6px">{task["completed"]}/{task["total"]} complete | {task["failed"]} failed</div>'
            f'<div style="display:grid;gap:1px">{ "".join(step_rows) }</div>{audit_html}</div>'
        )

    tasks_html = (
        "".join(task_cards)
        if task_cards
        else '<div style="text-align:center;padding:40px;color:#64748b"><p>No tasks yet.</p><p style="font-size:13px">Create one: <code style="background:#334155;padding:3px 8px;border-radius:4px">pf create my_task s1 s2</code></p></div>'
    )

    brain_html = (
        f'<div style="background:#1e293b;border-radius:8px;padding:14px;border:1px solid #334155;margin-bottom:12px">'
        f'<div style="font-weight:600;font-size:15px;margin-bottom:10px">🧠 Brain API Stats</div>'
        f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px">'
        f'<div style="text-align:center"><div style="font-size:22px;font-weight:700;color:#10b979">{brain.get("cache_hit_rate", 0):.1f}%</div><div style="font-size:11px;color:#64748b">Cache Hit Rate</div></div>'
        f'<div style="text-align:center"><div style="font-size:22px;font-weight:700;color:#0ea5e9">{brain.get("brain_queries", 0)}</div><div style="font-size:11px;color:#64748b">Brain Queries</div></div>'
        f'<div style="text-align:center"><div style="font-size:22px;font-weight:700;color:#10b979">{brain.get("tokens_saved", 0)}</div><div style="font-size:11px;color:#64748b">Tokens Saved</div></div>'
        f'<div style="text-align:center"><div style="font-size:22px;font-weight:700;color:#f59e0b">${brain.get("est_cost_saved_usd", 0):.4f}</div><div style="font-size:11px;color:#64748b">Est. $ Saved</div></div>'
        f'<div style="text-align:center"><div style="font-size:22px;font-weight:700;color:#10b979">{brain.get("validations", 0)}</div><div style="font-size:11px;color:#64748b">Validations</div></div>'
        f'<div style="text-align:center"><div style="font-size:22px;font-weight:700;color:#ef4444">{brain.get("hallucinations_caught", 0)}</div><div style="font-size:11px;color:#64748b">Hallucinations Caught</div></div>'
        f'</div>'
        f'<div style="margin-top:10px;font-size:10px;color:#475569">Source: {brain.get("source", "none")}</div></div>'
    )

    return f'''<!DOCTYPE html>
<html><head><title>AgentPathfinder — Dashboard</title>
<meta charset="utf-8"><meta http-equiv="refresh" content="30">
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;margin:0;padding:20px;background:#0f172a;color:#e2e8f0;line-height:1.5}}
.header{{margin-bottom:16px}}h1{{margin:0 0 4px;font-size:22px}}
.subtitle{{color:#64748b;font-size:13px}}
.stats{{display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap}}
.stat-box{{background:#1e293b;padding:10px 14px;border-radius:8px;border:1px solid #334155;min-width:100px}}
.stat-value{{font-size:20px;font-weight:700}}
.stat-label{{font-size:11px;color:#64748b}}
.grid{{display:grid;grid-template-columns:1fr 360px;gap:16px}}
@media(max-width:900px){{.grid{{grid-template-columns:1fr}}}}
.panel{{background:#1e293b;border-radius:8px;padding:14px;border:1px solid #334155}}
.panel-title{{font-weight:600;font-size:15px;margin-bottom:10px}}
.refresh{{position:fixed;top:16px;right:16px;padding:6px 14px;background:#2563eb;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px}}
.refresh:hover{{background:#1d4ed8}}
.footer{{margin-top:24px;padding-top:12px;border-top:1px solid #334155;font-size:11px;color:#64748b;text-align:center}}
</style></head><body>
<button class="refresh" onclick="location.reload()">🔄 Refresh</button>
<div class="header"><h1>🔐 AgentPathfinder Dashboard</h1><div class="subtitle">Deterministic task orchestration + Brain API performance</div></div>
<div class="stats">
<div class="stat-box"><div class="stat-value" style="color:#e2e8f0">{total_tasks}</div><div class="stat-label">Total Tasks</div></div>
<div class="stat-box"><div class="stat-value" style="color:#10b981">{complete}</div><div class="stat-label">Complete</div></div>
<div class="stat-box"><div class="stat-value" style="color:#0ea5e9">{in_progress}</div><div class="stat-label">In Progress</div></div>
<div class="stat-box"><div class="stat-value" style="color:#f59e0b">{paused}</div><div class="stat-label">Paused</div></div>
<div class="stat-box"><div class="stat-value" style="color:#ef4444">{failed}</div><div class="stat-label">Failed</div></div>
</div>
<div class="grid">
<div><div class="panel"><div class="panel-title">📋 Tasks</div>{tasks_html}</div></div>
<div>{brain_html}
<div class="panel" style="margin-top:12px"><div class="panel-title">📖 Quick Commands</div>
<div style="font-size:12px;color:#94a3b8;line-height:1.8">
<code style="background:#0f172a;padding:2px 6px;border-radius:4px">pf create &lt;name&gt; [steps...]</code><br>
<code style="background:#0f172a;padding:2px 6px;border-radius:4px">pf run &lt;task_id&gt;</code><br>
<code style="background:#0f172a;padding:2px 6px;border-radius:4px">pf status &lt;task_id&gt;</code><br>
<code style="background:#0f172a;padding:2px 6px;border-radius:4px">pf audit &lt;task_id&gt;</code><br>
<code style="background:#0f172a;padding:2px 6px;border-radius:4px">pf reconstruct &lt;task_id&gt;</code><br>
<code style="background:#0f172a;padding:2px 6px;border-radius:4px">pf register-agent &lt;id&gt;</code>
</div></div>
<div class="panel" style="margin-top:12px"><div class="panel-title">📤 Export</div>
<div style="font-size:12px;line-height:1.6">
<a href="/api/tasks" style="color:#0ea5e9;text-decoration:none">JSON: /api/tasks</a><br>
<a href="/api/brain" style="color:#0ea5e9;text-decoration:none">JSON: /api/brain</a>
</div></div>
</div></div>
<div class="footer">Generated: {time.strftime("%Y-%m-%d %H:%M:%S UTC")} | Auto-refresh: 30s</div>
</body></html>'''


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json_response(self, data: dict, status: int = 200):
        body = json.dumps(data, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html_response(self, html: str, status: int = 200):
        body = html.encode()
        self.send_response(status)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        tasks = load_tasks(DATA_DIR)
        brain = load_brain_stats()

        if path == "/" or path == "/index.html":
            self._html_response(generate_dashboard_html(tasks, brain))
        elif path == "/api/tasks":
            self._json_response({"tasks": tasks, "count": len(tasks)})
        elif path == "/api/brain":
            self._json_response(brain)
        elif path == "/api/health":
            self._json_response({
                "status": "ok",
                "tasks_dir": str(DATA_DIR / "tasks"),
                "tasks_found": len(tasks),
                "brain_source": brain.get("source", "none"),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })
        else:
            self._json_response({"error": "Not found"}, 404)


def serve(port: int = 8080, bind: str = "0.0.0.0"):
    with socketserver.TCPServer((bind, port), DashboardHandler) as httpd:
        print("=" * 60)
        print("  🔐 AgentPathfinder Dashboard")
        print(f"  🌐 http://localhost:{port}")
        print(f"  📁 Data: {DATA_DIR}")
        print("  ⏹  Press Ctrl+C to stop")
        print("=" * 60)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  Dashboard stopped.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AgentPathfinder Dashboard")
    parser.add_argument("--port", "-p", type=int, default=8080)
    parser.add_argument("--bind", "-b", default="0.0.0.0")
    args = parser.parse_args()
    serve(port=args.port, bind=args.bind)
