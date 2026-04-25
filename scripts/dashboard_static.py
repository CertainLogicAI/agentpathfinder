#!/usr/bin/env python3
"""Generate a static HTML dashboard for AgentPathfinder.

No Flask required — just generates an HTML file you open in a browser.
Usage:
    python3 dashboard_static.py [--data-dir ./pathfinder_data] [--output dashboard.html]
    # Then open dashboard.html in your browser
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    from agentpathfinder import AuditTrail
except ImportError:
    _HERE = Path(__file__).resolve().parent
    for _p in (_HERE / ".." / ".." / ".." / "agentpathfinder",
               _HERE / ".." / ".." / "agentpathfinder",
               _HERE / ".." / "agentpathfinder"):
        if (_p / "pathfinder_core.py").exists():
            sys.path.insert(0, str(_p.parent))
            from agentpathfinder import AuditTrail
            break
    else:
        print("ERROR: agentpathfinder not found on PYTHONPATH")
        sys.exit(1)

DATA_DIR = Path("./pathfinder_data")
BRAIN_METRICS = Path("/data/.openclaw/workspace/agentpathfinder/metrics.json")


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
                    evs = AuditTrail(ap, b"dummy").read_trail(task["task_id"])
                    n_events = len(evs)
                    audit_ok = all(e.get("tamper_ok", True) for e in evs)
                except Exception:
                    pass
            steps_html = ""
            for s in task.get("steps", []):
                icon = {"complete": "✅", "failed": "❌", "running": "⏳"}.get(s.get("state"), "○")
                token = f'<span class="token">{s.get("token_id","")[:12]}…</span>' if s.get("token_id") else ""
                err = f'<span style="color:#ef4444;font-size:11px" title="{s.get("error","")}">⚠</span>' if s.get("error") else ""
                steps_html += f'<div class="step"><span style="width:20px;text-align:center">{icon}</span><span style="flex:1">{s["step_number"]}. {s["name"]}</span>{token}{err}</div>'
            audit_html = ""
            if audit_ok is not None:
                status = f'<span style="color:#10b981">🔒 Verified</span>' if audit_ok else f'<span style="color:#ef4444">🚨 Tampered</span>'
                audit_html = f'<div class="audit">{status}<span>{n_events} events</span></div>'
            out.append({
                "name": task.get("name", "Unnamed"),
                "state": task.get("state", "unknown"),
                "created": task.get("created_at", "")[:10] if task.get("created_at") else "?",
                "progress": progress,
                "steps_html": steps_html,
                "audit_html": audit_html,
            })
        except Exception as e:
            print(f"skip {tf}: {e}")
    return out


def _load_brain():
    if not BRAIN_METRICS.exists():
        return None
    try:
        return json.load(BRAIN_METRICS.open())
    except Exception:
        return None


def generate(data_dir=None, output="dashboard.html"):
    if data_dir:
        global DATA_DIR
        DATA_DIR = Path(data_dir)

    tasks = _load_tasks()
    brain = _load_brain()

    tasks_html = ""
    if tasks:
        for t in tasks:
            badge_class = f"b-{t['state']}"
            tasks_html += f'''
<div class="card">
<div class="card-header"><span class="name">{t["name"]}</span><span class="badge {badge_class}">{t["state"]}</span></div>
<div class="meta">Created: {t["created"]} • {t["progress"]}% done</div>
<div class="bar"><div class="fill" style="width:{t["progress"]}%"></div></div>
<div class="steps">{t["steps_html"]}</div>
{t["audit_html"]}
</div>'''
    else:
        tasks_html = '<div class="empty">No tasks yet.<br><small>Create one with: <code>pf create my_task step1 step2</code></small></div>'

    brain_html = ""
    if brain:
        b = brain.get("brain_api", {})
        c = brain.get("cache", {})
        brain_html = f'''
<div class="stats-grid">
<div class="stat-card"><div class="stat-val">{b.get("cache_hit_rate_percent", "—")}%</div><div class="stat-label">Cache Hit Rate</div></div>
<div class="stat-card"><div class="stat-val">{b.get("tokens_saved", 0)}</div><div class="stat-label">Tokens Saved</div></div>
<div class="stat-card"><div class="stat-val">${b.get("est_cost_saved_usd", 0)}</div><div class="stat-label">Est. $ Saved</div></div>
<div class="stat-card"><div class="stat-val">{b.get("hallucinations_caught", 0)}</div><div class="stat-label">Hallucinations Caught</div></div>
</div>
<div class="section-title">Session</div>
<table><tr><th>Metric</th><th>Value</th></tr>
<tr><td>Duration</td><td>{brain.get("session_duration_seconds", "—")} s</td></tr>
<tr><td>Brain API Calls</td><td>{b.get("queries", 0)}</td></tr>
<tr><td>Validations</td><td>{b.get("validations", 0)}</td></tr>
<tr><td>Cache Entries</td><td>{c.get("entries", 0)}</td></tr>
<tr><td>Timestamp</td><td>{brain.get("timestamp", "—")}</td></tr>
</table>'''
    else:
        brain_html = '<div class="empty">Brain metrics not available.<br><small>Run the Brain skill to populate.</small></div>'

    html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>AgentPathfinder Dashboard</title>
<style>
:root{{--bg:#0f1724;--card:#1e293b;--border:#334155;--text:#e2e8f0;--muted:#64748b;--accent:#2563eb;--ok:#10b981;--warn:#f59e0b;--err:#ef4444;}}
*{{box-sizing:border-box;margin:0}}body{{font-family:system-ui,sans-serif;background:var(--bg);color:var(--text);padding:20px;}}
h1{{font-size:22px;margin-bottom:4px}}.subtitle{{color:var(--muted);font-size:13px;margin-bottom:18px}}
.tabs{{display:flex;gap:8px;margin-bottom:14px}}
.tab{{padding:8px 16px;border-radius:6px;background:var(--card);border:1px solid var(--border);color:var(--muted);cursor:pointer;font-size:14px}}
.tab.active{{background:var(--accent);color:#fff;border-color:var(--accent)}}
.panel{{display:none}}.panel.active{{display:block}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:14px;margin-bottom:12px}}
.card-header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}}
.name{{font-weight:600;font-size:15px}}.badge{{padding:3px 10px;border-radius:4px;font-size:11px;font-weight:600}}
.b-task_complete{{background:var(--ok);color:#000}}.b-registered{{background:var(--border);color:var(--muted)}}
.b-in_progress{{background:#0ea5e9;color:#fff}}.b-paused{{background:var(--warn);color:#000}}
.b-failed,.b-reconstruction_failed{{background:var(--err);color:#fff}}
.meta{{font-size:12px;color:var(--muted);margin-bottom:8px}}
.bar{{background:var(--border);height:6px;border-radius:3px;overflow:hidden;margin:8px 0}}
.fill{{background:var(--ok);height:100%;border-radius:3px}}
.step{{display:flex;align-items:center;gap:8px;font-size:13px;padding:3px 0;border-bottom:1px solid var(--border)}}
.step:last-child{{border:none}}.token{{font-family:monospace;font-size:10px;color:var(--muted);max-width:110px;overflow:hidden;text-overflow:ellipsis}}
.audit{{display:flex;gap:8px;align-items:center;margin-top:8px;font-size:12px;color:var(--muted)}}
.empty{{text-align:center;padding:50px 20px;color:var(--muted)}}
.stats-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:12px}}
.stat-card{{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:14px;text-align:center}}
.stat-val{{font-size:28px;font-weight:700;color:var(--accent);margin:6px 0}}
.stat-label{{font-size:12px;color:var(--muted)}}.section-title{{font-size:14px;font-weight:600;color:var(--muted);margin-bottom:8px;text-transform:uppercase;letter-spacing:0.5px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{padding:8px 10px;text-align:left;border-bottom:1px solid var(--border)}}
th{{color:var(--muted);font-size:11px;text-transform:uppercase}}
</style></head>
<body>
<h1>🔐 AgentPathfinder Dashboard</h1><p class="subtitle">Tasks + Brain API — one page, zero config</p>
<p style="color:var(--muted);font-size:12px;margin-bottom:14px">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
<div class="tabs">
<div class="tab active" onclick="show('tasks',this)">Tasks ({len(tasks)})</div>
<div class="tab" onclick="show('brain',this)">Brain Stats</div>
</div>
<div id="tasks" class="panel active">{tasks_html}</div>
<div id="brain" class="panel">{brain_html}</div>
<script>
function show(id,el){{document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));document.getElementById(id).classList.add('active');el.classList.add('active');}}
</script>
</body></html>'''

    Path(output).write_text(html)
    print(f"\n🖥️  Dashboard generated: {Path(output).absolute()}")
    print(f"   Open it in your browser to see the full UI.")
    return output


def main():
    p = argparse.ArgumentParser(description="Generate static Pathfinder dashboard")
    p.add_argument("--data-dir", default=os.getenv("PATHFINDER_DATA_DIR", "./pathfinder_data"))
    p.add_argument("--output", "-o", default="dashboard.html")
    args = p.parse_args()
    generate(args.data_dir, args.output)


if __name__ == "__main__":
    main()
