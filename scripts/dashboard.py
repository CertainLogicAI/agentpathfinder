#!/usr/bin/env python3
"""AgentPathfinder + Brain API Unified Dashboard

One page, two tabs:
  - Tasks: live Pathfinder task list with visual status
  - Brain Stats: token savings, hit rates, $ saved

Usage:
    python dashboard.py [--port 8080] [--data-dir ./pathfinder_data]

Open browser → http://localhost:8080
"""
import argparse, csv, io, json, os, sys
from datetime import datetime
from pathlib import Path

try:
    from agentpathfinder import TaskEngine, AuditTrail
except ImportError:
    _HERE = Path(__file__).resolve().parent
    for _p in (_HERE / ".." / ".." / ".." / "agentpathfinder",
               _HERE / ".." / ".." / "agentpathfinder",
               _HERE / ".." / "agentpathfinder"):
        if (_p / "pathfinder_core.py").exists():
            sys.path.insert(0, str(_p.parent))
            from agentpathfinder import TaskEngine, AuditTrail
            break
    else:
        print("ERROR: agentpathfinder not found on PYTHONPATH")
        sys.exit(1)

DATA_DIR = Path("./pathfinder_data")
# Optional: set BRAIN_METRICS env var to show Brain API stats tab
# Example: BRAIN_METRICS=/path/to/metrics.json python dashboard.py
BRAIN_METRICS = Path(os.environ.get("BRAIN_METRICS", "/dev/null/nonexistent"))
if not os.environ.get("BRAIN_METRICS"):
    BRAIN_METRICS = None  # No brain metrics unless explicitly configured


def _load_tasks():
    tasks_dir = DATA_DIR / "tasks"
    out = []
    if not tasks_dir.exists():
        return out
    for tf in sorted(tasks_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            task = json.load(tf.open())
            total = task.get("num_steps", 0)
            done = task.get("completed_steps", 0)
            progress = round(done / total * 100, 1) if total else 0
            audit_ok = None
            n_events = 0
            ap = DATA_DIR / "audit" / f"{task['task_id']}.jsonl"
            if ap.exists():
                try:
                    # NOTE: Dashboard reads audit events for display only.
                    # Cryptographic HMAC verification requires the derived audit key
                    # which is not available to the dashboard (by design — key stays
                    # in vault). Use `pf audit <task_id>` CLI for full verification.
                    evs = AuditTrail(ap, b"display-only").read_trail(task["task_id"])
                    n_events = len(evs)
                    # Dashboard does NOT claim tamper verification — that requires
                    # the real audit key. We show structural presence only.
                    audit_ok = None  # Use CLI `pf audit` for cryptographic proof
                except Exception:
                    pass
            out.append({
                "task_id": task["task_id"],
                "name": task.get("name", "Unnamed"),
                "state": task.get("state", "unknown"),
                "created": task.get("created_at", "")[:10] if task.get("created_at") else "?",
                "progress": progress,
                "steps": task.get("steps", []),
                "audit_ok": audit_ok,
                "audit_events": n_events,
            })
        except Exception as e:
            print(f"dashboard: skip {tf}: {e}")
    return out


def _load_brain():
    if BRAIN_METRICS is None or not BRAIN_METRICS.exists():
        return None
    try:
        return json.load(BRAIN_METRICS.open())
    except Exception:
        return None


# Simple HTML with tabs
PAGE_HTML = '''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>AgentPathfinder Dashboard</title>
<style>
:root{--bg:#0f1724;--card:#1e293b;--border:#334155;--text:#e2e8f0;--muted:#64748b;--accent:#2563eb;--ok:#10b981;--warn:#f59e0b;--err:#ef4444;}
*{box-sizing:border-box;margin:0}body{font-family:system-ui,sans-serif;background:var(--bg);color:var(--text);padding:20px;}
h1{font-size:22px;margin-bottom:4px}.subtitle{color:var(--muted);font-size:13px;margin-bottom:18px}
.tabs{display:flex;gap:8px;margin-bottom:14px}
.tab{padding:8px 16px;border-radius:6px;background:var(--card);border:1px solid var(--border);color:var(--muted);cursor:pointer;font-size:14px}
.tab.active{background:var(--accent);color:#fff;border-color:var(--accent)}
.panel{display:none}.panel.active{display:block}
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:14px;margin-bottom:12px}
.card-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.name{font-weight:600;font-size:15px}.badge{padding:3px 10px;border-radius:4px;font-size:11px;font-weight:600}
.b-task_complete{background:var(--ok);color:#000}.b-registered{background:var(--border);color:var(--muted)}
.b-in_progress{background:#0ea5e9;color:#fff}.b-paused{background:var(--warn);color:#000}
.b-failed,.b-reconstruction_failed{background:var(--err);color:#fff}
.meta{font-size:12px;color:var(--muted);margin-bottom:8px}
.bar{background:var(--border);height:6px;border-radius:3px;overflow:hidden;margin:8px 0}
.fill{background:var(--ok);height:100%;border-radius:3px}
.step{display:flex;align-items:center;gap:8px;font-size:13px;padding:3px 0;border-bottom:1px solid var(--border)}
.step:last-child{border:none}.token{font-family:monospace;font-size:10px;color:var(--muted);max-width:110px;overflow:hidden;text-overflow:ellipsis}
.audit{display:flex;gap:8px;align-items:center;margin-top:8px;font-size:12px;color:var(--muted)}
.btn{position:fixed;top:16px;right:16px;padding:8px 14px;background:var(--accent);color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px}
.export{right:100px;background:var(--card);border:1px solid var(--border);color:var(--text)}
.empty{text-align:center;padding:50px 20px;color:var(--muted)}
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:12px}
.stat-card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:14px;text-align:center}
.stat-val{font-size:28px;font-weight:700;color:var(--accent);margin:6px 0}
.section-title{font-size:14px;font-weight:600;color:var(--muted);margin-bottom:8px;text-transform:uppercase;letter-spacing:0.5px}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--border)}
th{color:var(--muted);font-size:11px;text-transform:uppercase}
</style></head>
<body>
<h1>AgentPathfinder Dashboard</h1><p class="subtitle">Tasks + Brain API — one page, zero config</p>
<button class="btn" onclick="location.reload()">Refresh</button>
<button class="btn export" onclick="exportCSV()">Export CSV</button>
<div class="tabs">
<div class="tab active" onclick="show('tasks',this)">Tasks ({{ n_tasks }})</div>
<div class="tab" onclick="show('brain',this)">Brain Stats</div>
</div>
<div id="tasks" class="panel active">
{% if tasks %}{% for t in tasks %}
<div class="card">
<div class="card-header"><span class="name">{{ t.name }}</span><span class="badge b-{{ t.state }}">{{ t.state }}</span></div>
<div class="meta">{{ t.task_id[:8] }}… • {{ t.created }} • {{ t.progress }}%</div>
<div class="bar"><div class="fill" style="width:{{ t.progress }}%"></div></div>
<div class="steps">{% for s in t.steps %}
<div class="step">
<span style="width:20px;text-align:center">{% if s.state=='complete' %}✅{% elif s.state=='failed' %}❌{% elif s.state=='running' %}⏳{% else %}○{% endif %}</span>
<span style="flex:1">{{ s.step_number }}. {{ s.name }}</span>
{% if s.token_id %}<span class="token">{{ s.token_id[:12] }}…</span>{% endif %}
{% if s.error %}<span style="color:var(--err);font-size:11px" title="{{ s.error }}">⚠</span>{% endif %}
</div>{% endfor %}</div>
{% if t.audit_ok is not none %}<div class="audit">
{% if t.audit_ok %}<span style="color:var(--ok)">🔒 Verified</span>{% else %}<span style="color:var(--err)">🚨 Tampered</span>{% endif %}
<span>{{ t.audit_events }} events</span></div>{% endif %}
</div>{% endfor %}{% else %}<div class="empty">No tasks yet.</div>{% endif %}
</div>
<div id="brain" class="panel">
{% if brain %}
<div class="stats-grid">
<div class="stat-card"><div class="stat-val">{{ brain.brain_api.cache_hit_rate_percent | default('—') }}%</div><div class="stat-label">Cache Hit Rate</div></div>
<div class="stat-card"><div class="stat-val">{{ brain.brain_api.tokens_saved | default(0) }}</div><div class="stat-label">Tokens Saved</div></div>
<div class="stat-card"><div class="stat-val">${{ brain.brain_api.est_cost_saved_usd | default(0) }}</div><div class="stat-label">Est. $ Saved</div></div>
<div class="stat-card"><div class="stat-val">{{ brain.brain_api.hallucinations_caught | default(0) }}</div><div class="stat-label">Hallucinations Caught</div></div>
</div>
<div class="section-title">Session</div>
<table><tr><th>Metric</th><th>Value</th></tr>
<tr><td>Duration</td><td>{{ brain.session_duration_seconds | default('—') }} s</td></tr>
<tr><td>Brain API Calls</td><td>{{ brain.brain_api.queries | default(0) }}</td></tr>
<tr><td>Validations</td><td>{{ brain.brain_api.validations | default(0) }}</td></tr>
<tr><td>Cache Entries</td><td>{{ brain.cache.entries | default(0) }}</td></tr>
<tr><td>Timestamp</td><td>{{ brain.timestamp | default('—') }}</td></tr>
</table>
{% else %}<div class="empty">Brain metrics not available.<br><small>Run the Brain skill to populate.</small></div>{% endif %}
</div>
<script>
function show(id,el){document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));document.getElementById(id).classList.add('active');el.classList.add('active');}
function exportCSV(){const rows=[];rows.push(['Task ID','Name','State','Progress %','Steps Done','Steps Total','Audit']);{% for t in tasks %}rows.push(['{{ t.task_id[:8] }}...','{{ t.name }}','{{ t.state }}','{{ t.progress }}','{{ t.steps|selectattr("state","equalto","complete")|list|length }}','{{ t.steps|length }}','{{ "OK" if t.audit_ok else "FAIL" if t.audit_ok is not none else "N/A" }}']);{% endfor %}let csv=rows.map(r=>r.map(v=>'"'+String(v).replace(/"/g,'""')+'"').join(',')).join('\\n');const blob=new Blob([csv],{type:'text/csv'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='pathfinder-report-'+new Date().toISOString().slice(0,10)+'.csv';a.click();}
</script>
</body></html>'''


def _render():
    from flask import Flask, render_template_string, jsonify
    app = Flask(__name__)

    @app.route("/")
    def index():
        tasks = _load_tasks()
        brain = _load_brain()
        return render_template_string(PAGE_HTML, tasks=tasks, brain=brain, n_tasks=len(tasks))

    @app.route("/api/tasks")
    def api_tasks():
        return jsonify(_load_tasks())

    @app.route("/api/brain")
    def api_brain():
        return jsonify(_load_brain() or {})

    @app.route("/api/export/csv")
    def export_csv():
        tasks = _load_tasks()
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["task_id", "name", "state", "progress_pct", "steps_complete", "steps_total", "audit_status"])
        for t in tasks:
            done = sum(1 for s in t["steps"] if s.get("state") == "complete")
            total = len(t["steps"])
            audit = "OK" if t.get("audit_ok") else "FAIL" if t.get("audit_ok") is not None else "N/A"
            w.writerow([t["task_id"], t["name"], t["state"], t["progress"], done, total, audit])
        return (buf.getvalue(), 200, {"Content-Type": "text/csv", "Content-Disposition": f'attachment; filename="pathfinder-report-{datetime.now().strftime("%Y%m%d")}.csv"'})

    @app.route("/api/health")
    def health():
        brain_avail = BRAIN_METRICS.exists() if BRAIN_METRICS is not None else False
        return jsonify({"status": "ok", "tasks": len(_load_tasks()), "brain_available": brain_avail, "timestamp": datetime.utcnow().isoformat()})

    return app


def main():
    p = argparse.ArgumentParser(description="AgentPathfinder Unified Dashboard")
    p.add_argument("--port", type=int, default=int(os.getenv("PATHFINDER_DASH_PORT", "8080")))
    p.add_argument("--data-dir", type=str, default=os.getenv("PATHFINDER_DATA_DIR", "./pathfinder_data"))
    p.add_argument("--host", default="0.0.0.0")
    args = p.parse_args()
    global DATA_DIR
    DATA_DIR = Path(args.data_dir)
    app = _render()
    print(f"\n🔐 AgentPathfinder Dashboard")
    print(f"   http://localhost:{args.port}")
    print(f"   Data: {DATA_DIR}")
    print(f"   Press Ctrl+C to stop\n")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
