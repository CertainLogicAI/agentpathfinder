"""AgentPathfinder dashboard static HTML generator.

Generates dashboard.html showing task status, audit trails, and metrics.
"""
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, List

# ── paths ──
DASHBOARD_DIR = Path(__file__).parent
TASK_DIR = Path.home() / ".agentpathfinder" / "pathfinder_data" / "tasks"
AUDIT_DIR = Path.home() / ".agentpathfinder" / "pathfinder_data" / "audit"
METRICS_FILE = Path.home() / ".agentpathfinder" / "metrics.json"

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AgentPathfinder Dashboard</title>
<style>
:root {{
  --navy: #0F1724; --navy-light: #1E293B; --blue: #2563EB;
  --text: #E2E8F0; --text-soft: #94A3B8; --text-dim: #64748B;
  --success: #34D399; --error: #F87171; --warning: #FBBF24;
  --card-bg: #0B1120; --border: rgba(255,255,255,0.06);
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro', 'Segoe UI', sans-serif;
  background: var(--navy); color: var(--text); min-height: 100vh;
}}
.container {{ max-width: 1400px; margin: 0 auto; padding: 0 24px; }}
.header {{
  background: var(--card-bg); border-bottom: 1px solid var(--border);
  padding: 16px 0; position: sticky; top: 0; z-index: 100;
}}
.header-inner {{ display: flex; justify-content: space-between; align-items: center; }}
.brand-icon {{
  width: 32px; height: 32px; background: linear-gradient(135deg, var(--blue), #3B82F6);
  border-radius: 8px; display: grid; place-items: center; font-size: 16px;
}}
.hero {{ padding: 40px 0 24px; }}
.hero-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }}
.stat-card {{
  background: var(--card-bg); border: 1px solid var(--border);
  border-radius: 12px; padding: 20px;
}}
.stat-card::before {{
  content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, var(--blue), transparent 60%);
}}
.stat-label {{ font-size: 12px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }}
.stat-value {{ font-size: 32px; font-weight: 700; letter-spacing: -1px; }}
.content {{ padding: 24px 0 60px; }}
.grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
.card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }}
.footer {{ border-top: 1px solid var(--border); padding: 20px 0; text-align: center; color: var(--text-dim); font-size: 12px; }}
</style>
</head>
<body>
<div class="header">
  <div class="container">
    <div class="header-inner">
      <div style="display:flex;align-items:center;gap:10px">
        <div class="brand-icon">🎯</div>
        <div style="font-size:18px;font-weight:700">AgentPathfinder</div>
      </div>
    </div>
  </div>
</div>

<div class="container">
  <div class="hero">
    <div class="hero-grid">
      <div class="stat-card">
        <div class="stat-label">Active Tasks</div>
        <div class="stat-value">{tasks_count}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Audit Events</div>
        <div class="stat-value">{audit_count}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Agents</div>
        <div class="stat-value">{agent_count}</div>
      </div>
    </div>
  </div>

  <div class="content">
    <div class="grid-2">
      <div class="card">
        <h3>Tasks</h3>
        {tasks_html}
      </div>
      <div class="card">
        <h3>Audit Trail</h3>
        {audit_html}
      </div>
    </div>
  </div>
</div>

<div class="footer">
  <div class="container">
    AgentPathfinder — Tamper-evident task tracking<br>
    <span style="color:var(--text-dim)">Version 1.2.6 • MIT License</span>
  </div>
</div>
</body>
</html>"""


def _count_json(dir_path: Path) -> int:
    if not dir_path.exists():
        return 0
    return len(list(dir_path.glob("*.json")))


def _count_jsonl_lines(dir_path: Path) -> int:
    count = 0
    for f in dir_path.glob("*.jsonl"):
        count += sum(1 for line in open(f) if line.strip())
    return count


def _load_tasks_html() -> str:
    if not TASK_DIR.exists() or not list(TASK_DIR.glob("*.json")):
        return '<div style="color:var(--text-dim)">No tasks yet.</div>'
    
    tasks = []
    for f in sorted(TASK_DIR.glob("*.json")):
        data = json.loads(f.read_text())
        tasks.append(data)
    
    html = '<ul style="list-style:none;padding:0">'
    for t in tasks[:10]:
        html += f'''<li style="padding:8px 0;border-bottom:1px solid var(--border)">
            <strong>{t.get("name", "Untitled")}</strong>
            <span style="color:var(--text-dim);font-size:12px"> — {t.get("status", "unknown")}</span>
        </li>'''
    html += '</ul>'
    return html


def _load_audit_html() -> str:
    if not AUDIT_DIR.exists():
        return '<div style="color:var(--text-dim)">No audit events yet.</div>'
    
    events = []
    for f in sorted(AUDIT_DIR.glob("*.jsonl")):
        for line in open(f):
            line = line.strip()
            if not line:
                continue
            events.append(json.loads(line))
    
    if not events:
        return '<div style="color:var(--text-dim)">No audit events yet.</div>'
    
    html = '<ul style="list-style:none;padding:0">'
    for e in events[-10:]:
        html += f'''<li style="padding:8px 0;border-bottom:1px solid var(--border)">
            <span style="font-size:12px;color:var(--text-dim)">{e.get("timestamp", "?")}</span>
            <div>{e.get("event", "unknown")} — task: {e.get("task_id", "?")[:12]}</div>
        </li>'''
    html += '</ul>'
    return html


def generate_dashboard(output_path: str = "report.html") -> Path:
    out = DASHBOARD_DIR / output_path
    
    tasks_count = _count_json(TASK_DIR)
    audit_count = _count_jsonl_lines(AUDIT_DIR)
    agent_count = _count_json(Path.home() / ".agentpathfinder" / "pathfinder_data" / "agents")
    
    html = HTML_TEMPLATE.format(
        tasks_count=tasks_count,
        audit_count=audit_count,
        agent_count=agent_count,
        tasks_html=_load_tasks_html(),
        audit_html=_load_audit_html(),
    )
    
    out.write_text(html)
    return out


if __name__ == "__main__":
    path = generate_dashboard()
    print(f"Dashboard written to: {path}")
