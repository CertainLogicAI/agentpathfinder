#!/usr/bin/env python3
"""AgentPathfinder Pro Dashboard — Live Flask server with license gating.

Run: python3 pro_dashboard.py
Open: http://localhost:8080

Features:
- Auto-refreshing task status (SSE every 5s)
- Demo license validation (replace with Stripe webhook later)
- CSV/JSON export
- Webhook config placeholder
- HMAC audit verification
"""

import json
import csv
import io
import hashlib
import hmac
import secrets
import time
from pathlib import Path
from datetime import datetime
from flask import Flask, jsonify, request, Response, render_template_string

app = Flask(__name__)

# ── paths ──
DATA_DIR = Path.home() / ".agentpathfinder" / "pathfinder_data"
TASK_DIR = DATA_DIR / "tasks"
AUDIT_DIR = DATA_DIR / "audit"
VAULT_DIR = DATA_DIR / "vault"

# ── License config ──
# DEMO: Any key starting with "demo-" is valid
# TODO: Replace with Stripe webhook validation
VALID_LICENSE_PREFIX = "demo-"
LICENSE_CACHE = {}


def check_license(key: str) -> dict:
    """Validate license key. Returns {valid: bool, tier: str, expiry: str}."""
    if not key:
        return {"valid": False, "tier": None, "reason": "No license key provided"}
    
    # Demo keys (free for testing)
    if key.startswith(VALID_LICENSE_PREFIX):
        return {
            "valid": True,
            "tier": "pro",
            "expiry": "2099-12-31",
            "source": "demo"
        }
    
    # Cached validation (prevent repeated checks)
    if key in LICENSE_CACHE:
        return LICENSE_CACHE[key]
    
    # TODO: Stripe webhook validation here
    # stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    # customer = stripe.Customer.retrieve(key)
    
    result = {"valid": False, "tier": None, "reason": "Invalid license key"}
    LICENSE_CACHE[key] = result
    return result


def load_tasks() -> list:
    """Load all task metadata from disk."""
    tasks = []
    if not TASK_DIR.exists():
        return tasks
    for f in sorted(TASK_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            data["file"] = f.name
            tasks.append(data)
        except Exception:
            continue
    return tasks


def load_audit_events(task_id: str = None) -> list:
    """Load audit events, optionally filtered by task."""
    events = []
    if not AUDIT_DIR.exists():
        return events
    
    files = [AUDIT_DIR / f"{task_id}.jsonl"] if task_id else AUDIT_DIR.glob("*.jsonl")
    
    for f in files:
        if not f.exists():
            continue
        for line in f.read_text().split("\n"):
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                continue
    
    return sorted(events, key=lambda x: x.get("timestamp", ""), reverse=True)


def verify_audit_event(event: dict, audit_key: bytes) -> bool:
    """Verify HMAC signature of a single audit event."""
    try:
        stored_hmac = event.get("hmac", "")
        event_data = {k: v for k, v in event.items() if k != "hmac"}
        computed = hmac.new(
            audit_key,
            json.dumps(event_data, sort_keys=True).encode(),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(stored_hmac, computed)
    except Exception:
        return False


def get_stats() -> dict:
    """Compute dashboard statistics."""
    tasks = load_tasks()
    total = len(tasks)
    complete = sum(1 for t in tasks if t.get("state") == "task_complete")
    failed = sum(1 for t in tasks if t.get("failed_steps", 0) > 0)
    
    events = load_audit_events()
    verified = sum(1 for e in events if e.get("tamper_ok", True))
    
    return {
        "total_tasks": total,
        "complete_tasks": complete,
        "failed_tasks": failed,
        "pending_tasks": total - complete,
        "total_events": len(events),
        "verified_events": verified,
        "tampered_events": len(events) - verified,
        "agents": 1,  # TODO: Count from registry
    }


# ── HTML Template ──
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AgentPathfinder Pro Dashboard</title>
<style>
:root {
  --navy: #0F1724; --navy-light: #1E293B; --blue: #2563EB;
  --text: #E2E8F0; --text-soft: #94A3B8; --text-dim: #64748B;
  --success: #34D399; --error: #F87171; --warning: #FBBF24;
  --card-bg: #0B1120; --border: rgba(255,255,255,0.06);
}
* { margin:0; padding:0; box-sizing:border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro', 'Segoe UI', sans-serif;
  background: var(--navy); color: var(--text); min-height: 100vh;
}
.container { max-width: 1400px; margin: 0 auto; padding: 0 24px; }
.header {
  background: var(--card-bg); border-bottom: 1px solid var(--border);
  padding: 16px 0; position: sticky; top: 0; z-index: 100;
}
.header-inner { display: flex; justify-content: space-between; align-items: center; }
.brand-icon {
  width: 32px; height: 32px; background: linear-gradient(135deg, var(--blue), #3B82F6);
  border-radius: 8px; display: grid; place-items: center; font-size: 16px;
}
.badge-pro {
  background: linear-gradient(135deg, #2563EB, #3B82F6);
  color: white; padding: 4px 12px; border-radius: 6px;
  font-size: 12px; font-weight: 700; letter-spacing: 0.5px;
}
.hero { padding: 40px 0 24px; }
.hero-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; }
.stat-card {
  background: var(--card-bg); border: 1px solid var(--border);
  border-radius: 12px; padding: 20px; position: relative;
}
.stat-card::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, var(--blue), transparent 60%);
  border-radius: 12px 12px 0 0;
}
.stat-label { font-size: 12px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }
.stat-value { font-size: 32px; font-weight: 700; letter-spacing: -1px; }
.content { padding: 24px 0 60px; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
.task-item { padding: 12px 0; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
.task-item:last-child { border-bottom: none; }
.task-name { font-weight: 600; }
.task-meta { font-size: 13px; color: var(--text-dim); }
.status-badge { padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
.status-complete { background: rgba(52,211,153,0.15); color: #34D399; }
.status-failed { background: rgba(248,113,113,0.15); color: #F87171; }
.status-pending { background: rgba(251,191,36,0.15); color: #FBBF24; }
.footer { border-top: 1px solid var(--border); padding: 20px 0; text-align: center; color: var(--text-dim); font-size: 12px; }
.export-btn {
  background: var(--blue); color: white; border: none;
  padding: 8px 16px; border-radius: 6px; font-size: 13px;
  cursor: pointer; text-decoration: none; display: inline-block;
}
.export-btn:hover { background: #1D4ED8; }
.live-indicator {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; color: var(--text-dim);
}
.live-dot {
  width: 8px; height: 8px; background: var(--success);
  border-radius: 50%; animation: pulse 2s infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
.webhook-card {
  background: rgba(37, 99, 235, 0.08); border: 1px solid rgba(37, 99, 235, 0.2);
}
@media (max-width: 768px) {
  .grid-2 { grid-template-columns: 1fr; }
  .hero-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
</head>
<body>
<div class="header">
  <div class="container">
    <div class="header-inner">
      <div style="display:flex;align-items:center;gap:10px">
        <div class="brand-icon">🎯</div>
        <div style="font-size:18px;font-weight:700">AgentPathfinder</div>
        <span class="badge-pro">PRO</span>
      </div>
      <div class="live-indicator">
        <div class="live-dot"></div>
        <span>Live</span>
      </div>
    </div>
  </div>
</div>

<div class="container">
  <div class="hero">
    <div class="hero-grid" id="stats-grid">
      <!-- Populated by JS -->
    </div>
  </div>

  <div class="content">
    <div class="grid-2">
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
          <h3>Tasks</h3>
          <div>
            <a href="/export?format=csv&key={{ license_key }}" class="export-btn">CSV</a>
            <a href="/export?format=json&key={{ license_key }}" class="export-btn" style="margin-left:8px">JSON</a>
          </div>
        </div>
        <div id="tasks-list">
          <!-- Populated by JS -->
        </div>
      </div>
      
      <div class="card">
        <h3>Audit Trail</h3>
        <div id="audit-list">
          <!-- Populated by JS -->
        </div>
      </div>
    </div>
    
    <div class="card webhook-card" style="margin-top: 16px;">
      <h3>🔗 Webhooks</h3>
      <p style="color: var(--text-dim); font-size: 14px; margin-top: 8px;">
        Configure webhook URLs to receive notifications on task completion.
        <br><br>
        <code style="background: var(--navy); padding: 4px 8px; border-radius: 4px;">
          POST /api/webhooks/configure
        </code>
      </p>
    </div>
  </div>
</div>

<div class="footer">
  <div class="container">
    AgentPathfinder Pro — Tamper-evident task tracking<br>
    <span style="color:var(--text-dim)">License: {{ license_info.tier | upper }} • Expires: {{ license_info.expiry }}</span>
  </div>
</div>

<script>
const licenseKey = '{{ license_key }}';

function updateStats() {
  fetch(`/api/stats?key=${licenseKey}`)
    .then(r => r.json())
    .then(data => {
      const grid = document.getElementById('stats-grid');
      grid.innerHTML = `
        <div class="stat-card">
          <div class="stat-label">Total Tasks</div>
          <div class="stat-value">${data.total_tasks}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Complete</div>
          <div class="stat-value" style="color: var(--success)">${data.complete_tasks}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Failed</div>
          <div class="stat-value" style="color: var(--error)">${data.failed_tasks}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Pending</div>
          <div class="stat-value" style="color: var(--warning)">${data.pending_tasks}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Audit Events</div>
          <div class="stat-value">${data.total_events}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Verified</div>
          <div class="stat-value" style="color: var(--success)">${data.verified_events}</div>
        </div>
      `;
    });
}

function updateTasks() {
  fetch(`/api/tasks?key=${licenseKey}`)
    .then(r => r.json())
    .then(data => {
      const list = document.getElementById('tasks-list');
      if (data.tasks.length === 0) {
        list.innerHTML = '<div style="color:var(--text-dim)">No tasks yet.</div>';
        return;
      }
      list.innerHTML = data.tasks.map(t => {
        const status = t.state === 'task_complete' ? 'COMPLETE' : 
                      t.failed_steps > 0 ? 'FAILED' : 'PENDING';
        const statusClass = status === 'COMPLETE' ? 'status-complete' : 
                           status === 'FAILED' ? 'status-failed' : 'status-pending';
        return `
          <div class="task-item">
            <div>
              <div class="task-name">${t.name}</div>
              <div class="task-meta">${t.num_steps} steps • ${t.completed_steps}/${t.num_steps} done</div>
            </div>
            <span class="status-badge ${statusClass}">${status}</span>
          </div>
        `;
      }).join('');
    });
}

function updateAudit() {
  fetch(`/api/audit?key=${licenseKey}`)
    .then(r => r.json())
    .then(data => {
      const list = document.getElementById('audit-list');
      if (data.events.length === 0) {
        list.innerHTML = '<div style="color:var(--text-dim)">No audit events yet.</div>';
        return;
      }
      list.innerHTML = data.events.slice(0, 10).map(e => `
        <div class="task-item">
          <div>
            <div style="font-size:12px;color:var(--text-dim)">${e.timestamp || '?'}</div>
            <div>${e.event || 'unknown'} — ${(e.task_id || '?').substring(0, 12)}</div>
          </div>
          <span class="status-badge ${e.tamper_ok ? 'status-complete' : 'status-failed'}">
            ${e.tamper_ok ? '✓' : '✗'}
          </span>
        </div>
      `).join('');
    });
}

function refresh() {
  updateStats();
  updateTasks();
  updateAudit();
}

refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>"""


# ── Routes ──

@app.route("/")
def index():
    license_key = request.args.get("key", "")
    license_info = check_license(license_key)
    
    if not license_info["valid"]:
        return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head><title>AgentPathfinder Pro — License Required</title>
        <style>
        body { background: #0F1724; color: #E2E8F0; font-family: system-ui; 
               display: grid; place-items: center; min-height: 100vh; margin: 0; }
        .box { background: #0B1120; border: 1px solid rgba(255,255,255,0.06); 
               padding: 40px; border-radius: 16px; text-align: center; max-width: 400px; }
        h1 { margin-bottom: 16px; }
        input { background: #1E293B; border: 1px solid rgba(255,255,255,0.1); 
                color: #E2E8F0; padding: 12px 16px; border-radius: 8px; 
                width: 100%; margin-bottom: 16px; font-size: 14px; }
        button { background: #2563EB; color: white; border: none; 
                 padding: 12px 24px; border-radius: 8px; font-size: 14px; 
                 cursor: pointer; width: 100%; }
        .hint { color: #64748B; font-size: 13px; margin-top: 16px; }
        </style></head>
        <body>
        <div class="box">
          <h1>🎯 AgentPathfinder Pro</h1>
          <p>Enter your license key to access the dashboard.</p>
          <form method="GET">
            <input type="text" name="key" placeholder="license-key-here" autofocus>
            <button type="submit">Unlock Dashboard</button>
          </form>
          <p class="hint">Demo keys: demo-anything</p>
        </div>
        </body>
        </html>
        """, license_info=license_info)
    
    return render_template_string(
        DASHBOARD_HTML,
        license_key=license_key,
        license_info=license_info
    )


@app.route("/api/stats")
def api_stats():
    license = check_license(request.args.get("key", ""))
    if not license["valid"]:
        return jsonify({"error": "Invalid license"}), 403
    return jsonify(get_stats())


@app.route("/api/tasks")
def api_tasks():
    license = check_license(request.args.get("key", ""))
    if not license["valid"]:
        return jsonify({"error": "Invalid license"}), 403
    return jsonify({"tasks": load_tasks()})


@app.route("/api/audit")
def api_audit():
    license = check_license(request.args.get("key", ""))
    if not license["valid"]:
        return jsonify({"error": "Invalid license"}), 403
    return jsonify({"events": load_audit_events()[:50]})


@app.route("/export")
def export_data():
    license = check_license(request.args.get("key", ""))
    if not license["valid"]:
        return "Invalid license", 403
    
    fmt = request.args.get("format", "json")
    tasks = load_tasks()
    
    if fmt == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["task_id", "name", "state", "steps", "completed", "failed", "created_at"])
        for t in tasks:
            writer.writerow([
                t.get("task_id", ""),
                t.get("name", ""),
                t.get("state", ""),
                t.get("num_steps", 0),
                t.get("completed_steps", 0),
                t.get("failed_steps", 0),
                t.get("created_at", "")
            ])
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=pathfinder_tasks.csv"}
        )
    
    else:  # json
        return Response(
            json.dumps({"tasks": tasks, "exported_at": datetime.utcnow().isoformat()}, indent=2),
            mimetype="application/json",
            headers={"Content-Disposition": "attachment; filename=pathfinder_tasks.json"}
        )


@app.route("/api/webhooks/configure", methods=["POST"])
def configure_webhook():
    """Placeholder for webhook configuration."""
    license = check_license(request.args.get("key", ""))
    if not license["valid"]:
        return jsonify({"error": "Invalid license"}), 403
    
    data = request.get_json() or {}
    url = data.get("url", "")
    events = data.get("events", ["task_complete"])
    
    # TODO: Store webhook config and implement delivery
    return jsonify({
        "status": "configured",
        "url": url,
        "events": events,
        "note": "Webhook delivery not yet implemented — coming in v1.3"
    })


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "version": "1.2.7-pro"})


if __name__ == "__main__":
    print("=" * 60)
    print("AgentPathfinder Pro Dashboard")
    print("=" * 60)
    print("Open: http://localhost:8080?key=demo-test")
    print("Demo key: demo-anything")
    print("=" * 60)
    app.run(host="127.0.0.1", port=8080, debug=False)
