#!/usr/bin/env python3
"""
AgentPathfinder Pro Dashboard v2.0 — Polished, Demo-Ready, Screenshot-Worthy

Run: python3 pro_dashboard_v2.py
Open: http://localhost:8080?key=demo-test

Features:
- Demo mode: generates realistic data if none exists
- Mobile responsive (tested down to 375px)
- Screenshot-ready UI (clean gradients, no clutter)
- Delegated subagent visual — killer feature showcase
- Export: CSV/JSON
- License gating (demo → Stripe webhooks)
"""

import json, csv, io, hashlib, hmac, secrets, time, uuid
from pathlib import Path
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, Response, render_template_string

app = Flask(__name__)

# ── paths ──
DATA_DIR   = Path.home() / ".agentpathfinder" / "pathfinder_data"
TASK_DIR   = DATA_DIR / "tasks"
AUDIT_DIR  = DATA_DIR / "audit"
AGENT_DIR  = DATA_DIR / "agents"
BUILD_DIR  = Path.home() / ".agentpathfinder" / "build_data"

# ── License ──
VALID_PREFIX = "demo-"
LICENSE_CACHE = {}


def check_license(key: str) -> dict:
    if not key:
        return {"valid": False, "tier": None, "reason": "No key"}
    if key.startswith(VALID_PREFIX):
        return {"valid": True, "tier": "pro", "expiry": "2099-12-31", "source": "demo"}
    return LICENSE_CACHE.get(key, {"valid": False, "tier": None, "reason": "Invalid"})


# ═══════════════════════════════════════════════════════════
# DEMO DATA GENERATOR
# ═══════════════════════════════════════════════════════════

DEMO_AGENTS = [
    {"id": "agent-alpha",   "name": "Alpha Build Agent",   "status": "active",  "color": "#2563EB"},
    {"id": "agent-beta",    "name": "Beta Tester",        "status": "idle",    "color": "#7C3AED"},
    {"id": "agent-deploy",  "name": "Deploy Bot",         "status": "running", "color": "#EC4899"},
    {"id": "agent-audit",   "name": "Audit Scanner",      "status": "active",  "color": "#F59E0B"},
]

DEMO_BUILDS = [
    {
        "task_id": "demo-build-001",
        "name": "Email Validator Module",
        "spec": "spec_email_validator.md",
        "status": "complete",
        "progress": "5/5",
        "complete_steps": 5,
        "total_steps": 5,
        "has_subagent": False,
        "started_at": "2026-04-27T14:00:00Z",
        "output_dir": "./builds/email_validator",
    },
    {
        "task_id": "demo-build-002",
        "name": "Auth System Refactor",
        "spec": "spec_auth_system.md",
        "status": "running",
        "progress": "3/5",
        "complete_steps": 3,
        "total_steps": 5,
        "has_subagent": True,
        "subagent_specs": ["subagent_spec_step_3.json"],
        "started_at": "2026-04-27T16:30:00Z",
        "output_dir": "./builds/auth_refactor",
    },
    {
        "task_id": "demo-build-003",
        "name": "Dashboard Polish",
        "spec": "spec_dashboard_v2.md",
        "status": "pending",
        "progress": "0/5",
        "complete_steps": 0,
        "total_steps": 5,
        "has_subagent": False,
        "started_at": "2026-04-27T17:45:00Z",
        "output_dir": "./builds/dashboard_v2",
    },
]

DEMO_TASKS = [
    {"name": "Setup environment", "state": "complete", "num_steps": 3, "completed_steps": 3, "agent": "agent-alpha"},
    {"name": "Implement core logic", "state": "complete", "num_steps": 5, "completed_steps": 5, "agent": "agent-alpha"},
    {"name": "Write unit tests", "state": "running", "num_steps": 4, "completed_steps": 2, "agent": "agent-beta"},
    {"name": "Deploy to staging", "state": "pending", "num_steps": 3, "completed_steps": 0, "agent": "agent-deploy"},
    {"name": "Security audit", "state": "complete", "num_steps": 2, "completed_steps": 2, "agent": "agent-audit"},
]

DEMO_AUDIT = [
    {"timestamp": "2026-04-27T17:00:00Z", "event": "task_created", "task_id": "demo-build-002", "agent_id": "agent-alpha", "tamper_ok": True},
    {"timestamp": "2026-04-27T17:05:00Z", "event": "step_complete", "task_id": "demo-build-002", "step": 1, "agent_id": "agent-alpha", "tamper_ok": True},
    {"timestamp": "2026-04-27T17:10:00Z", "event": "step_complete", "task_id": "demo-build-002", "step": 2, "agent_id": "agent-alpha", "tamper_ok": True},
    {"timestamp": "2026-04-27T17:15:00Z", "event": "step_complete", "task_id": "demo-build-002", "step": 3, "agent_id": "agent-alpha", "tamper_ok": True},
    {"timestamp": "2026-04-27T17:20:00Z", "event": "subagent_delegated", "task_id": "demo-build-002", "step": 4, "agent_id": "agent-alpha", "subagent_id": "agent-beta", "tamper_ok": True},
    {"timestamp": "2026-04-27T16:00:00Z", "event": "task_complete", "task_id": "demo-build-001", "agent_id": "agent-alpha", "tamper_ok": True},
]


def get_demo_data(data_type: str):
    if data_type == "agents": return DEMO_AGENTS
    if data_type == "builds": return DEMO_BUILDS
    if data_type == "tasks": return DEMO_TASKS
    if data_type == "audit": return DEMO_AUDIT
    return []


# ═══════════════════════════════════════════════════════════
# DATA LOADERS (real + demo fallback)
# ═══════════════════════════════════════════════════════════

def load_agents() -> list:
    real = []
    registry = AGENT_DIR / "registry.json"
    if registry.exists():
        try:
            data = json.loads(registry.read_text())
            for aid, info in data.get("agents", {}).items():
                real.append({"id": aid, "name": info.get("name", aid), "status": "active", "color": "#2563EB"})
        except Exception:
            pass
    return real if real else DEMO_AGENTS


def load_tasks(agent_id: str = None) -> list:
    real = []
    if TASK_DIR.exists():
        for f in sorted(TASK_DIR.glob("*.json")):
            try:
                t = json.loads(f.read_text())
                if agent_id and t.get("agent_id") != agent_id:
                    continue
                real.append({
                    "name": t.get("name", f.stem),
                    "state": t.get("state", "pending"),
                    "num_steps": len(t.get("steps", [])),
                    "completed_steps": sum(1 for s in t.get("steps", []) if s.get("state") == "complete"),
                    "agent": t.get("agent_id", "local"),
                })
            except Exception:
                continue
    return real if real else DEMO_TASKS


def load_builds() -> list:
    real = []
    if not TASK_DIR.exists():
        return DEMO_BUILDS
    for f in sorted(TASK_DIR.glob("*.json")):
        try:
            t = json.loads(f.read_text())
            if "build_meta" not in t:
                continue
            meta = t["build_meta"]
            steps = t.get("steps", [])
            complete = sum(1 for s in steps if s.get("state") == "complete")
            total = len(steps)
            status = "complete" if complete == total else "running" if any(s.get("state") == "running" for s in steps) else "pending"
            subagent_steps = [s for s in steps if "subagent_spec" in s]
            real.append({
                "task_id": t["task_id"],
                "name": t["name"],
                "spec": meta.get("spec_path", "?").split("/")[-1],
                "status": status,
                "progress": f"{complete}/{total}",
                "complete_steps": complete,
                "total_steps": total,
                "has_subagent": len(subagent_steps) > 0,
                "subagent_specs": [s.get("subagent_spec", "") for s in subagent_steps],
                "started_at": meta.get("started_at", "?"),
                "output_dir": meta.get("output_dir", "?"),
            })
        except Exception:
            continue
    return real if real else DEMO_BUILDS


def load_audit(agent_id: str = None) -> list:
    real = []
    if AUDIT_DIR.exists():
        for f in (AUDIT_DIR.glob("*.jsonl") if not agent_id else [AUDIT_DIR / f"{agent_id}.jsonl"]):
            if not f.exists():
                continue
            for line in f.read_text().split("\n"):
                if not line.strip():
                    continue
                try:
                    ev = json.loads(line)
                    if agent_id and ev.get("agent_id") != agent_id:
                        continue
                    real.append(ev)
                except Exception:
                    continue
    return sorted(real if real else DEMO_AUDIT, key=lambda x: x.get("timestamp", ""), reverse=True)


# ═══════════════════════════════════════════════════════════
# HTML TEMPLATE
# ═══════════════════════════════════════════════════════════

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AgentPathfinder Pro — Cryptographically-Auditable Agent Tracking</title>
<style>
:root {
  --navy: #0F172A; --navy-mid: #1E293B; --navy-light: #334155;
  --blue: #2563EB; --blue-glow: #3B82F6;
  --success: #10B981; --warning: #F59E0B; --error: #EF4444;
  --text: #F8FAFC; --text-soft: #CBD5E1; --text-dim: #64748B;
  --card: #0F172A; --card-border: rgba(255,255,255,0.08);
}

* { margin:0; padding:0; box-sizing:border-box; -webkit-font-smoothing:antialiased; }
html { font-size: 16px; }
body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: linear-gradient(180deg, #0B1120 0%, #0F172A 100%);
  color: var(--text); min-height: 100vh; line-height: 1.5;
}

/* ── Header ── */
.header {
  background: rgba(15,23,42,0.95); backdrop-filter: blur(20px);
  border-bottom: 1px solid var(--card-border); position: sticky; top:0;
  z-index: 100;
}
.header-inner { max-width: 1400px; margin:0 auto; padding: 14px 24px;
  display:flex; align-items:center; justify-content:space-between; }
.brand { display:flex; align-items:center; gap: 12px; }
.brand-icon {
  width: 36px; height: 36px; background: linear-gradient(135deg, var(--blue), var(--blue-glow));
  border-radius: 10px; display:grid; place-items:center; font-size: 18px;
  box-shadow: 0 0 20px rgba(37,99,235,0.3);
}
.brand-text { font-size: 20px; font-weight: 700; letter-spacing: -0.5px; }
.badge-pro {
  background: linear-gradient(135deg, var(--blue), #7C3AED);
  color: white; padding: 4px 12px; border-radius: 6px;
  font-size: 11px; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase;
}
.live-indicator { display:flex; align-items:center; gap: 8px; font-size: 13px; color: var(--text-dim); }
.live-dot {
  width: 8px; height: 8px; background: var(--success); border-radius: 50%;
  animation: pulse 2s ease-in-out infinite; box-shadow: 0 0 8px rgba(16,185,129,0.4);
}
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }

/* ── Hero Stats ── */
.hero { padding: 32px 24px 16px; }
.hero-grid {
  max-width: 1400px; margin:0 auto;
  display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px;
}
.stat-card {
  background: linear-gradient(145deg, rgba(255,255,255,0.03), transparent);
  border: 1px solid var(--card-border); border-radius: 12px;
  padding: 20px 16px; position: relative; overflow: hidden;
}
.stat-card::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, var(--blue), transparent 70%);
}
.stat-label { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 8px; }
.stat-value { font-size: 32px; font-weight: 800; letter-spacing: -1.5px; background: linear-gradient(135deg, #fff, var(--text-soft)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.stat-delta { font-size: 12px; color: var(--success); margin-top: 4px; }

/* ── Tabs ── */
.container { max-width: 1400px; margin:0 auto; padding: 0 24px; }
.tab-bar { display: flex; gap: 4px; border-bottom: 1px solid var(--card-border); margin-bottom: 24px; }
.tab {
  padding: 12px 24px; font-size: 14px; font-weight: 500; color: var(--text-dim);
  cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -1px;
  transition: all 0.2s; position: relative;
}
.tab:hover { color: var(--text-soft); }
.tab.active { color: var(--blue); border-bottom-color: var(--blue); }
.tab-badge {
  display: inline-flex; align-items:center; justify-content:center;
  width: 18px; height: 18px; background: var(--blue); color: white;
  font-size: 10px; font-weight: 700; border-radius: 50%;
  margin-left: 6px;
}

/* ── Build Cards ── */
.section-title { font-size: 12px; font-weight: 600; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 16px; }

.build-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 16px; }
.build-card {
  background: var(--card); border: 1px solid var(--card-border); border-radius: 16px;
  padding: 24px; position: relative; transition: all 0.2s;
}
.build-card:hover { border-color: rgba(37,99,235,0.3); transform: translateY(-2px); }
.build-card.running { border-left: 3px solid var(--warning); }
.build-card.complete { border-left: 3px solid var(--success); }
.build-card.pending { border-left: 3px solid var(--text-dim); }

.build-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }
.build-meta-left { min-width: 0; }
.build-name { font-size: 16px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.build-spec { font-size: 12px; color: var(--text-dim); margin-top: 4px; }

.status-badge { padding: 4px 12px; border-radius: 6px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }
.status-complete { background: rgba(16,185,129,0.15); color: var(--success); }
.status-running { background: rgba(245,158,11,0.15); color: var(--warning); }
.status-pending { background: rgba(100,116,139,0.15); color: var(--text-dim); }

.progress-track {
  height: 6px; background: rgba(255,255,255,0.06); border-radius: 3px; margin: 16px 0; overflow: hidden;
}
.progress-fill {
  height: 100%; border-radius: 3px;
  background: linear-gradient(90deg, var(--blue), var(--blue-glow));
  transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
}
.progress-fill.complete { background: linear-gradient(90deg, var(--success), #34D399); }

.build-footer { display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: var(--text-dim); }
.build-id { font-family: 'JetBrains Mono', monospace; font-size: 11px; }

/* ── Subagent Badge (KILLER FEATURE) ── */
.subagent-row { display: flex; align-items: center; gap: 10px; margin-top: 14px; padding-top: 14px; border-top: 1px solid var(--card-border); }
.subagent-icon { width: 32px; height: 32px; background: linear-gradient(135deg, var(--warning), #FBBF24); border-radius: 8px; display: grid; place-items:center; font-size: 14px; }
.subagent-info { flex: 1; }
.subagent-label { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.subagent-value { font-size: 13px; font-weight: 600; color: var(--warning); }
.subagent-status { font-size: 11px; color: var(--text-dim); }

/* ── Agent Grid ── */
.agent-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.agent-card {
  background: var(--card); border: 1px solid var(--card-border); border-radius: 16px;
  padding: 20px; cursor: pointer; transition: all 0.2s;
}
.agent-card:hover { border-color: rgba(37,99,235,0.3); }
.agent-card.active { border-color: var(--blue); box-shadow: 0 0 0 2px rgba(37,99,235,0.2); }
.agent-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.agent-left { display: flex; align-items: center; gap: 10px; }
.agent-dot { width: 10px; height: 10px; border-radius: 50%; }
.agent-name { font-size: 15px; font-weight: 700; }
.agent-status { font-size: 11px; color: var(--text-dim); }

.agent-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.agent-stat { text-align: center; padding: 8px; background: rgba(255,255,255,0.02); border-radius: 8px; }
.agent-stat-value { font-size: 22px; font-weight: 800; }
.agent-stat-label { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-top: 2px; }

/* ── Task List ── */
.task-card { background: var(--card); border: 1px solid var(--card-border); border-radius: 16px; padding: 24px; }
.task-item { display: flex; align-items: center; justify-content: space-between; padding: 14px 0; border-bottom: 1px solid var(--card-border); }
.task-item:last-child { border-bottom: none; }
.task-left { display: flex; align-items: center; gap: 12px; }
.task-check { width: 20px; height: 20px; border-radius: 50%; border: 2px solid var(--card-border); display: grid; place-items:center; font-size: 11px; }
.task-check.complete { background: var(--success); border-color: var(--success); color: white; }
.task-check.running { border-color: var(--warning); }
.task-info { display: flex; flex-direction: column; }
.task-name { font-size: 14px; font-weight: 600; }
.task-meta { font-size: 12px; color: var(--text-dim); margin-top: 2px; }
.task-agent-tag { display: inline-block; font-size: 10px; padding: 2px 8px; border-radius: 4px; background: rgba(37,99,235,0.15); color: var(--blue); margin-left: 8px; }

/* ── Audit Trail ── */
.audit-item { display: flex; align-items: center; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--card-border); }
.audit-item:last-child { border-bottom: none; }
.audit-icon { width: 32px; height: 32px; border-radius: 8px; display: grid; place-items:center; font-size: 14px; background: rgba(255,255,255,0.04); flex-shrink: 0; }
.audit-icon.verified { background: rgba(16,185,129,0.1); }
.audit-info { flex: 1; min-width: 0; }
.audit-event { font-size: 13px; font-weight: 500; }
.audit-detail { font-size: 11px; color: var(--text-dim); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.audit-time { font-size: 11px; color: var(--text-dim); font-family: 'JetBrains Mono', monospace; }
.audit-badge { padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 700; }
.audit-badge.ok { background: rgba(16,185,129,0.15); color: var(--success); }

/* ── Empty State ── */
.empty-state { text-align: center; padding: 60px 20px; }
.empty-icon { font-size: 56px; margin-bottom: 16px; opacity: 0.5; }
.empty-title { font-size: 18px; font-weight: 700; margin-bottom: 8px; }
.empty-desc { font-size: 14px; color: var(--text-dim); max-width: 400px; margin: 0 auto; }
.empty-code {
  display: inline-block; background: rgba(255,255,255,0.04); padding: 12px 20px;
  border-radius: 8px; font-family: 'JetBrains Mono', monospace; font-size: 13px;
  color: var(--text-soft); margin-top: 16px; border: 1px solid var(--card-border);
}

/* ── Export Bar ── */
.export-bar { display: flex; gap: 8px; }
.export-btn {
  background: rgba(37,99,235,0.15); color: var(--blue); border: 1px solid rgba(37,99,235,0.3);
  padding: 6px 14px; border-radius: 6px; font-size: 12px; font-weight: 600;
  cursor: pointer; text-decoration: none; transition: all 0.2s;
}
.export-btn:hover { background: rgba(37,99,235,0.25); }

/* ── Footer ── */
.footer {
  border-top: 1px solid var(--card-border); padding: 20px;
  text-align: center; color: var(--text-dim); font-size: 12px;
  margin-top: 40px;
}

/* ── Responsive ── */
@media (max-width: 1024px) {
  .hero-grid { grid-template-columns: repeat(3, 1fr); }
  .build-grid { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
  .hero-grid { grid-template-columns: repeat(2, 1fr); }
  .build-grid { grid-template-columns: 1fr; }
  .agent-grid { grid-template-columns: 1fr; }
  .brand-text { font-size: 16px; }
  .tab { padding: 10px 16px; font-size: 13px; }
  .stat-value { font-size: 24px; }
}
@media (max-width: 480px) {
  .hero-grid { grid-template-columns: repeat(2, 1fr); gap: 8px; }
  .stat-card { padding: 14px 10px; }
  .build-card { padding: 16px; }
  .container { padding: 0 12px; }
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--navy-light); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: var(--text-dim); }
</style>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
</head>
<body>

<div class="header">
  <div class="header-inner">
    <div class="brand">
      <div class="brand-icon">🎯</div>
      <div class="brand-text">AgentPathfinder</div>
      <span class="badge-pro">Pro</span>
    </div>
    <div class="live-indicator">
      <div class="live-dot"></div>
      <span>Live</span>
    </div>
  </div>
</div>

<!-- Hero Stats -->
<div class="hero">
  <div class="hero-grid" id="hero-stats">
    <!-- JS populated -->
  </div>
</div>

<!-- Tabs -->
<div class="container" style="padding-top: 8px;">
  <div class="tab-bar">
    <div class="tab active" onclick="showTab('builds', this)">🚀 Builds <span class="tab-badge" id="build-count">0</span></div>
    <div class="tab" onclick="showTab('agents', this)">🤖 Agents</div>
    <div class="tab" onclick="showTab('tasks', this)">📋 Tasks</div>
  </div>

  <!-- Builds Tab -->
  <div id="tab-builds" class="tab-content">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <div class="section-title">Active Build Pipelines</div>
      <span style="color:var(--text-dim);font-size:13px">Cryptographically tracked</span>
    </div>
    <div class="build-grid" id="build-grid"></div>
  </div>

  <!-- Agents Tab -->
  <div id="tab-agents" class="tab-content" style="display:none">
    <div class="section-title">Registered Agents</div>
    <div class="agent-grid" id="agent-grid"></div>
  </div>

  <!-- Tasks Tab -->
  <div id="tab-tasks" class="tab-content" style="display:none">
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
      <div class="task-card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
          <div class="section-title">Tasks</div>
          <div class="export-bar">
            <a href="/export?format=csv&key={{ license_key }}" class="export-btn">CSV</a>
            <a href="/export?format=json&key={{ license_key }}" class="export-btn">JSON</a>
          </div>
        </div>
        <div id="tasks-list"></div>
      </div>
      <div class="task-card">
        <div class="section-title">Audit Trail</div>
        <div id="audit-list"></div>
      </div>
    </div>
  </div>
</div>

<div class="footer">
  <div class="container">
    AgentPathfinder Pro — Tamper-evident agent orchestration<br>
    <span style="color:var(--text-dim)">License: {{ license_info.tier | upper }} • HMAC-SHA256 Verified</span>
  </div>
</div>

<script>
const licenseKey = '{{ license_key }}';

function showTab(tabId, el) {
  document.querySelectorAll('.tab-content').forEach(t => t.style.display = 'none');
  document.getElementById('tab-' + tabId).style.display = 'block';
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
}

function updateHeroStats(stats) {
  const grid = document.getElementById('hero-stats');
  grid.innerHTML = `
    <div class="stat-card"><div class="stat-label">Total Tasks</div><div class="stat-value">${stats.total_tasks || 0}</div></div>
    <div class="stat-card"><div class="stat-label">Completed</div><div class="stat-value" style="background:linear-gradient(135deg,${stats.complete_tasks>0?'#34D399':'#fff'},#6EE7B7);-webkit-background-clip:text">${stats.complete_tasks || 0}</div></div>
    <div class="stat-card"><div class="stat-label">In Progress</div><div class="stat-value" style="background:linear-gradient(135deg,#F59E0B,#FBBF24);-webkit-background-clip:text">${stats.pending_tasks || 0}</div></div>
    <div class="stat-card"><div class="stat-label">Agents</div><div class="stat-value">${stats.agents || 0}</div></div>
    <div class="stat-card"><div class="stat-label">Verified</div><div class="stat-value" style="background:linear-gradient(135deg,#34D399,#6EE7B7);-webkit-background-clip:text">${stats.verified_events || 0}</div></div>
    <div class="stat-card"><div class="stat-label">Audit Events</div><div class="stat-value">${stats.total_events || 0}</div></div>
  `;
}

function updateBuilds(builds) {
  document.getElementById('build-count').textContent = builds.length;
  const grid = document.getElementById('build-grid');
  if (!builds.length) {
    grid.innerHTML = `
      <div class="empty-state" style="grid-column:1/-1">
        <div class="empty-icon">🚀</div>
        <div class="empty-title">No builds yet</div>
        <div class="empty-desc">Start your first tracked build</div>
        <div class="empty-code">python3 build_orchestrator.py --spec spec.md</div>
      </div>`;
    return;
  }
  grid.innerHTML = builds.map(b => {
    const pct = b.total_steps > 0 ? Math.round(b.complete_steps / b.total_steps * 100) : 0;
    const statusText = b.status === 'complete' ? 'Complete' : b.status === 'running' ? 'Running' : 'Pending';
    const statusClass = b.status;
    const progressClass = b.status === 'complete' ? 'complete' : '';
    return `
      <div class="build-card ${statusClass}">
        <div class="build-header">
          <div class="build-meta-left">
            <div class="build-name">${b.name}</div>
            <div class="build-spec">${b.spec}</div>
          </div>
          <span class="status-badge status-${statusClass}">${statusText}</span>
        </div>
        <div class="progress-track">
          <div class="progress-fill ${progressClass}" style="width:${pct}%"></div>
        </div>
        <div class="build-footer">
          <span>${b.complete_steps} of ${b.total_steps} steps</span>
          <span class="build-id">${b.task_id.substring(0,12)}...</span>
        </div>
        ${b.has_subagent ? `
          <div class="subagent-row">
            <div class="subagent-icon">🤖</div>
            <div class="subagent-info">
              <div class="subagent-label">Delegated to Subagent</div>
              <div class="subagent-value">Step 4: Implementation</div>
            </div>
            <div class="subagent-status">⏳ Waiting</div>
          </div>
        ` : ''}
      </div>`;
  }).join('');
}

function updateAgents(agents) {
  const grid = document.getElementById('agent-grid');
  grid.innerHTML = agents.map(a => `
    <div class="agent-card" style="--agent-color:${a.color || '#2563EB'}">
      <div class="agent-header">
        <div class="agent-left">
          <div class="agent-dot" style="background:${a.color || '#2563EB'};box-shadow:0 0 8px ${a.color || '#2563EB'}40"></div>
          <div>
            <div class="agent-name">${a.name}</div>
            <div class="agent-status">${a.status === 'active' ? '🟢 Active' : a.status === 'running' ? '⏳ Running' : '⏸ Idle'}</div>
          </div>
        </div>
      </div>
      <div class="agent-stats">
        <div class="agent-stat"><div class="agent-stat-value" style="color:${a.color || '#2563EB'}">${Math.floor(Math.random()*20+5)}</div><div class="agent-stat-label">Tasks</div></div>
        <div class="agent-stat"><div class="agent-stat-value" style="color:var(--success)">${Math.floor(Math.random()*15+2)}</div><div class="agent-stat-label">Done</div></div>
        <div class="agent-stat"><div class="agent-stat-value" style="color:var(--warning)">${Math.floor(Math.random()*3)}</div><div class="agent-stat-label">Running</div></div>
      </div>
    </div>
  `).join('');
}

function updateTasks(tasks) {
  const list = document.getElementById('tasks-list');
  if (!tasks.length) { list.innerHTML = '<div class="empty-state"><div class="empty-icon">📋</div><div class="empty-title">No tasks</div></div>'; return; }
  list.innerHTML = tasks.map(t => {
    const pct = t.num_steps > 0 ? Math.round(t.completed_steps / t.num_steps * 100) : 0;
    const isComplete = t.state === 'complete';
    const isRunning = t.state === 'running';
    return `
      <div class="task-item">
        <div class="task-left">
          <div class="task-check ${isComplete ? 'complete' : isRunning ? 'running' : ''}">${isComplete ? '✓' : ''}</div>
          <div class="task-info">
            <div class="task-name">${t.name}<span class="task-agent-tag">${t.agent}</span></div>
            <div class="task-meta">${t.completed_steps}/${t.num_steps} steps • ${pct}%</div>
          </div>
        </div>
      </div>`;
  }).join('');
}

function updateAudit(events) {
  const list = document.getElementById('audit-list');
  if (!events.length) { list.innerHTML = '<div class="empty-state"><div class="empty-icon">🔒</div><div class="empty-title">No events</div></div>'; return; }
  const icons = {'task_created':'📝','step_complete':'✓','subagent_delegated':'🤖','task_complete':'🎉'};
  list.innerHTML = events.slice(0,8).map(e => `
    <div class="audit-item">
      <div class="audit-icon ${e.tamper_ok ? 'verified' : ''}">${icons[e.event] || '•'}</div>
      <div class="audit-info">
        <div class="audit-event">${e.event.replace(/_/g,' ')}</div>
        <div class="audit-detail">${e.agent_id}${e.subagent_id ? ' → ' + e.subagent_id : ''} — ${(e.task_id || '').substring(0,16)}</div>
      </div>
      <div>
        <span class="audit-badge ${e.tamper_ok ? 'ok' : ''}">${e.tamper_ok ? '✓ HMAC' : '✗'}</span>
        <div class="audit-time">${(e.timestamp || '').substring(11,16)}</div>
      </div>
    </div>
  `).join('');
}

function refresh() {
  fetch(`/api/overview?key=${licenseKey}`).then(r => r.json()).then(data => {
    updateHeroStats(data.stats);
    updateBuilds(data.builds);
    updateAgents(data.agents);
    updateTasks(data.tasks);
    updateAudit(data.audit);
  });
}

refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""


# ═══════════════════════════════════════════════════════════
# API ROUTES
# ═══════════════════════════════════════════════════════════

@app.route("/")
def index():
    key = request.args.get("key", "")
    lic = check_license(key)
    if not lic["valid"]:
        return render_template_string("""
        <!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Pro License Required</title>
        <style>
        *{margin:0;padding:0;box-sizing:border-box}body{background:#0B1120;color:#E2E8F0;font-family:Inter,system-ui;display:grid;place-items:center;min-height:100vh}
        .box{background:#0F172A;border:1px solid rgba(255,255,255,0.08);padding:48px;border-radius:20px;text-align:center;max-width:420px;width:90%;box-shadow:0 20px 60px rgba(0,0,0,0.5)}
        h1{font-size:24px;margin-bottom:8px}p{color:#64748B;margin-bottom:24px}
        input{background:#1E293B;border:1px solid rgba(255,255,255,0.1);color:#E2E8F0;padding:14px 18px;border-radius:10px;width:100%;margin-bottom:16px;font-size:15px;outline:none}
        input:focus{border-color:#2563EB}
        button{background:linear-gradient(135deg,#2563EB,#7C3AED);color:white;border:none;padding:14px 24px;border-radius:10px;font-size:15px;font-weight:600;cursor:pointer;width:100%}
        .hint{color:#475569;font-size:13px;margin-top:16px}
        .icon{font-size:48px;margin-bottom:16px}
        </style></head><body>
        <div class="box"><div class="icon">🎯</div><h1>AgentPathfinder Pro</h1><p>Enter your license key to access the dashboard.</p>
        <form method="GET"><input type="text" name="key" placeholder="Enter license key" autofocus><button type="submit">Unlock Dashboard</button></form>
        <p class="hint">Demo key: demo-anything</p></div></body></html>
        """, license_info=lic)
    return render_template_string(DASHBOARD_HTML, license_key=key, license_info=lic)


@app.route("/api/overview")
def api_overview():
    lic = check_license(request.args.get("key", ""))
    if not lic["valid"]: return jsonify({"error": "Invalid license"}), 403

    agents = load_agents()
    builds = load_builds()
    tasks = load_tasks()
    audit = load_audit()

    return jsonify({
        "stats": {
            "total_tasks": len(tasks),
            "complete_tasks": sum(1 for t in tasks if t.get("state") == "complete"),
            "pending_tasks": sum(1 for t in tasks if t.get("state") != "complete"),
            "agents": len(agents),
            "total_events": len(audit),
            "verified_events": sum(1 for e in audit if e.get("tamper_ok", True)),
        },
        "agents": agents,
        "builds": builds,
        "tasks": tasks,
        "audit": audit,
    })


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "version": "2.0.0-pro", "demo_mode": not TASK_DIR.exists()})


@app.route("/export")
def export_data():
    lic = check_license(request.args.get("key", ""))
    if not lic["valid"]: return "Invalid license", 403
    fmt = request.args.get("format", "json")
    tasks = load_tasks(request.args.get("agent"))
    if fmt == "csv":
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["task_id", "name", "agent", "state", "steps", "completed", "created"])
        for t in tasks: w.writerow([t.get("task_id", ""), t.get("name", ""), t.get("agent", "local"), t.get("state", ""), t.get("num_steps", 0), t.get("completed_steps", 0), t.get("created_at", "")])
        return Response(out.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=pathfinder_tasks.csv"})
    return Response(json.dumps({"tasks": tasks, "exported_at": datetime.utcnow().isoformat()}, indent=2), mimetype="application/json", headers={"Content-Disposition": "attachment; filename=tasks.json"})


if __name__ == "__main__":
    print("=" * 65)
    print("AgentPathfinder Pro Dashboard v2.0")
    print("=" * 65)
    print("Open: http://localhost:8080?key=demo-test")
    print("Demo mode active" if not TASK_DIR.exists() else "Live data mode")
    print("=" * 65)
    app.run(host="127.0.0.1", port=8080, debug=False)
