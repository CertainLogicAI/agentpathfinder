---
summary: "AgentPathfinder v2"
read_when: ["installing", "configuring", "troubleshooting"]
---

# AgentPathfinder

Deterministic task orchestration with cryptographic sharding. Decompose any task into N substeps, shard a master key via XOR across them, and reconstruct only when every step completes successfully. Tamper-proof audit trails, crash recovery, file locking, and agent authentication included.

## What is AgentPathfinder

AgentPathfinder splits a 256-bit master key into N+1 shards using XOR: one per substep plus one held by the issuer. Step shards live in a filesystem vault, never in the task JSON. The master key is only reconstructible when **all** substeps finish. Every event is HMAC-SHA256 signed and written to an append-only JSONL audit trail. Agents authenticate with shared-secret HMAC tokens. No database required.

## Visual Confirmation Messages

Every CLI reply uses at-a-glance emoji indicators:

| State | Visual |
|-------|--------|
| Task complete | `✅ Task complete` |
| Task failed | `❌ Task failed` + error + retry suggestion |
| Step running | `⏳ Step N running...` |
| Audit verified | `✅ All N events verified` |
| Audit tampered | `❌ N events TAMPERED` |
| Key reconstructed | `✅ Key reconstructed` |
| Crash detected | `⚠️ Crash detected` + reset suggestion |

## Quick Reference

| Need | Command |
|------|---------|
| Install + init | `pf install` |
| Create a task | `pf create <name> [step_name...]` |
| Run all steps | `pf run <task_id>` |
| Check status | `pf status <task_id>` |
| Show audit trail | `pf audit <task_id>` |
| Reconstruct key | `pf reconstruct <task_id>` |
| Register agent | `pf register-agent <agent_id>` |
| Start dashboard | `pf dashboard --start` |

## One-Command Install

```bash
clawhub install agentpathfinder
pf install            # init data dirs + print ready banner
```

Output:
```
🚀 AgentPathfinder v2 Ready!
   ✅ Skill installed
   ✅ Data directory initialized
   🖥️ Dashboard:  pf dashboard --start
   ℹ️ Quick start:  pf create my_task step1 step2
```

## Installation

### 1. Install the skill

```bash
clawhub install agentpathfinder
```

### 2. Initialize

```bash
pf install
```

This creates `./pathfinder_data/` with subdirs `tasks`, `vault`, `audit`, `agents`.

### 3. Verify import

```bash
python3 -c "from pathfinder_client import PathfinderClient; print('OK')"
```

### 4. Use in your agent

```python
import sys
sys.path.insert(0, "/usr/local/lib/node_modules/openclaw/skills/agentpathfinder/scripts")
from pathfinder_client import PathfinderClient

client = PathfinderClient()

# Create a multi-step task
task_id = client.create("deploy_service", [
    "build_image", "push_registry", "update_k8s", "verify_health"
])
print(f"Created: {task_id}")

# Check status (with visual emoji formatting)
print(client.status(task_id))

# View audit trail
for ev in client.audit(task_id):
    print(ev)

# Reconstruct master key (only after all steps complete)
key = client.reconstruct(task_id)
```

## CLI Usage

### pf create — Create a new task

```bash
pf create "deploy" build push verify
# ✅ Task created: <task_id>
```

### pf run — Simulate running all steps

```bash
pf run <task_id>
# ✅ deploy is complete! ID: <task_id>
#    Progress: 3/3
#    ✅ Step 1 complete: build (token: tok_abc…)
#    ✅ Step 2 complete: push (token: tok_def…)
#    ✅ Step 3 complete: verify (token: tok_ghi…)
```

### pf status — Show task status

```bash
pf status <task_id>
# Task: deploy (<task_id>)
# State: task_complete
# Progress: 3/3
#
# Steps:
#   ✅ Step 1: build   token: tok_abc…
#   ✅ Step 2: push    token: tok_def…
#   ✅ Step 3: verify  token: tok_ghi…
```

### pf audit — Show signed audit trail

```bash
pf audit <task_id>
# ✅ All 5 events verified
```

### pf reconstruct — Reconstruct master key

```bash
pf reconstruct <task_id>
# ✅ Key reconstructed successfully
#    Key hash: 51e2bb5…
```

### pf register-agent — Register an agent

```bash
pf register-agent agent_alpha
# ✅ Agent registered: agent_alpha
#    🔑 API key: 0703e5a…b94527
```

## Dashboard

One command starts the web dashboard:

```bash
pf dashboard --start
```

Or directly:

```bash
python3 scripts/dashboard_server.py --port 8080
```

What you get:
- **Tasks panel** — live task list with step progress, audit integrity, tokens
- **Brain API stats** — cache hit rate, tokens saved, $ saved, validations, hallucinations caught
- **Auto-refresh** — page reloads every 30s
- **JSON exports** — `/api/tasks`, `/api/brain`, `/api/health`

No Flask, no dependencies — pure Python stdlib.

## SDK Usage

```python
from pathfinder_client import PathfinderClient

pf = PathfinderClient()

# Creation
tid = pf.create("migration", ["backup", "migrate", "validate"])

# Simulation run
pf.run(tid)

# Status with emojis
st = pf.status(tid)
print(st["overall_state"], st["progress"])

# Audit
for ev in pf.audit(tid):
    print(ev["event"], ev.get("tamper_ok"))

# Reconstruct
key = pf.reconstruct(tid)
print(f"Key hex: {key.hex()[:16]}...")

# Agents
api_key = pf.register_agent("worker_1")
print(f"API key: {api_key}")

# Brain stats
stats = pf.brain_stats()
print(f"Cache hit rate: {stats['cache']['hit_rate_percent']:.1f}%")
```

## Architecture

```
┌─────────────────┐     create_task()     ┌──────────────┐
│   CLI / SDK     │ ────────────────────▶ │  TaskEngine  │
│  (pf create...) │                       │              │
└─────────────────┘                       │ - generate K │
        │                                 │ - split(K,N) │
        │                                 │ - write JSON │
        │                                 └──────────────┘
        │                                        │
        │                                 vault: step shards
        │                                 task JSON: metadata
        ▼                                        │
┌─────────────────┐         ┌──────────────┐    │
│  AgentRuntime   │◄────────│ IssuingLayer │◄───┘
│  (execute_step) │  token  │              │
└─────────────────┘         │ - shard vault│
        │                   │ - HMAC sign  │
        │                   │ - audit log  │
        ▼                   └──────────────┘
┌─────────────────┐                ▲
│   AuditTrail    │◄───────────────┘
│  (JSONL + HMAC) │
└─────────────────┘
```

## Security Features

| Feature | How it works |
|---------|-------------|
| **Cryptographic Sharding** | Master key split into N+1 shards via XOR. Step shards isolated in filesystem vault. |
| **Tamper Evidence** | Every audit event HMAC-SHA256 signed with a key derived from the master key. Any edit breaks verification. |
| **Crash Recovery** | Steps enter a `running` state with an idempotency key. Crashed steps are detected and reset to `pending`. |
| **Concurrency Control** | Advisory file locks (`fcntl.LOCK_EX`) per task prevent concurrent writes. |
| **Atomic Writes** | All file writes go through temp file + `fsync` + `os.rename`, eliminating partial writes. |
| **Agent Authentication** | Agents register once and receive a 256-bit shared secret. Every step request must carry a valid HMAC-SHA256 signature. |
| **Key Derivation** | Audit signing key is derived from the master key via HMAC("audit_signing_key"). Raw master key never touches the audit code. |
| **Strict All-or-Nothing** | Key reconstruction fails unless **every** step is complete and hashes match. No partial credit. |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "Task not found" | Verify the task_id. Tasks live in `./pathfinder_data/tasks/`. |
| "Reconstruction failed" | Not all steps are complete. Run `pf status` to see which steps are pending/failed. |
| "Step already running" | A previous run crashed. Run `pf status` to find crashed steps, or call `reset_running_step()` via SDK. |
| "Agent authentication failed" | The agent is unregistered or the HMAC signature is wrong. Re-run `pf register-agent <id>`. |
| Audit reports tampered | Stop immediately. The audit trail or task JSON was modified outside the engine. Investigate the filesystem. |
| ImportError on `agentpathfinder` | Symlink `../../agentpathfinder` into the skill scripts dir, or adjust `sys.path` to your source checkout. |
| Dashboard won't start | Port 8080 may be in use. Use `pf dashboard --port 9090`. |

## License

MIT
