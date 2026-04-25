---
summary: "Tamper-evident cryptographic tracking for AI agent siblings"
read_when: ["installing", "configuring", "troubleshooting"]
name: agentpathfinder
description: "Unlimited tamper-evident cryptographic task tracking for AI agents. Green = proven complete. Red = failed or incomplete. Free forever — upgrade for dashboard, multi-agent views, and full audit exports."
version: 1.0.3
author: CertainLogic
license: MIT
platforms: [linux, macos, windows]
---

# AgentPathfinder

**Green = cryptographically proven complete. Red = not. Dead simple in every reply.**

AgentPathfinder gives your AI agents cryptographic proof of task completion. Decompose any task into N steps, shard a master key across them via XOR, and only reconstruct the key when every step finishes successfully. Every event is HMAC-SHA256 signed and written to an append-only audit trail.

**Free forever, unlimited tasks, no usage caps.** Upgrade when you want a dashboard, multi-agent views, or exportable audit files.

## What You Get

| Free | Pro ($29/mo) |
|------|-------------|
| ✅ Unlimited tamper-evident tracking via green/red in messages | 🖥️ Beautiful dead-simple dashboard |
| ✅ Cryptographic sharding (XOR-based, 256-bit) | 📊 Multi-agent sibling tracking |
| ✅ Audit trail with HMAC verification | 📋 Full audit exports (CSV/JSON) |
| ✅ Crash recovery + atomic writes | 🔗 Webhook notifications |
| ✅ CLI with visual confirmations | 📧 Priority support |

**Enterprise:** On-prem deployment, SSO/SAML, exportable tamper-proof audit files for compliance.

## Install

```bash
clawhub install agentpathfinder
```

Then verify:
```bash
pf install
```

## Quickstart

```bash
# Create a 4-step deployment task
pf create "deploy_api" "run_tests" "build_docker" "push_registry" "restart_service"
# → Task created: a7f3d2e1-...

# Run it (simulation mode — see what it looks like)
pf run a7f3d2e1-...
# → ⏳ SIMULATION MODE — No real code executed.
#    ✅ deploy_api is complete! Progress: 4/4
#    ✅ Step 1 complete: run_tests (token: tok_abc123…)
#    ✅ Step 2 complete: build_docker (token: tok_def456…)

# Check status — one glance says it all
pf status a7f3d2e1-...
# → ✅ task_complete 4/4 (all green)

# Verify audit integrity
pf audit a7f3d2e1-...
# → ✅ All 6 events verified

# Reconstruct the master key (only works when all steps pass)
pf reconstruct a7f3d2e1-...
# → ✅ Key reconstructed successfully
```

## Real Execution (Python SDK)

The CLI marks steps complete for demo. For real automation, bind Python functions:

```python
from pathfinder_client import PathfinderClient
from agentpathfinder import AgentRuntime

pf = PathfinderClient()
tid = pf.create("deploy", ["test", "build", "push"])

# Bind real functions
def run_tests():
    subprocess.run(["pytest", "-v"], check=True)
    return "passed"

def build_docker():
    subprocess.run(["docker", "build", "-t", "app", "."], check=True)
    return "app:latest"

# Execute
runtime = AgentRuntime(pf.engine, pf.issuing)
runtime.execute_task(tid, {
    "test": run_tests,
    "build": build_docker,
    "push": lambda: subprocess.run(["docker", "push", "app"], check=True),
})

# If any step fails → task pauses, audit trail shows exactly what happened
# Retry after fixing:
runtime.retry_step(tid, 2, build_docker)
```

## Architecture

```
┌─────────────┐  create_task()   ┌──────────────┐
│   CLI/SDK   │ ───────────────▶ │  TaskEngine  │
│ (pf create) │                  │              │
└─────────────┘                  │ - Generate K │
                                 │ - Split(K,N) │
                                 │ - Write JSON │
                                 └──────────────┘
                                        │
                                 Vault: step shards
                                 Tasks: metadata only
                                        │
┌─────────────┐         ┌──────────────┘
│ AgentRuntime│◄────────│ IssuingLayer │
│(execute_step│  token  │              │
└─────────────┘         │ - HMAC sign  │
        │               │ - Audit log  │
        ▼               └──────────────┘
┌─────────────┐                ▲
│ AuditTrail  │◄───────────────┘
│(JSONL+HMAC) │
└─────────────┘
```

## Security

**Tamper-evident, not tamper-proof.** Every event is HMAC-SHA256 signed with a derived audit key. If someone modifies the audit trail or task files, verification fails and you know immediately.

**Current limitations:** A malicious agent with filesystem access could read vault shards and reconstruct the key. For full isolation, upgrade to Pro (hosted vault) or Enterprise (TEE/remote attestation).

| Feature | How It Works |
|---------|-------------|
| Cryptographic sharding | 256-bit master key split into N+1 shards via XOR |
| Atomic persistence | temp + fsync + rename — no partial writes |
| Crash recovery | Steps in `running` state detected and reset |
| Concurrency control | Advisory file locks per task |
| Audit integrity | HMAC-SHA256 chain, any edit breaks verification |
| Agent authentication | Shared-secret HMAC tokens per agent |

## CLI Reference

| Command | What It Does |
|---------|-------------|
| `pf install` | One-command setup, verify deps |
| `pf create <name> [steps...]` | Create a new sharded task |
| `pf run <task_id>` | Simulate running all steps |
| `pf status <task_id>` | Visual status: ✅/❌/⏳ at a glance |
| `pf audit <task_id>` | Show tamper-verified audit trail |
| `pf reconstruct <task_id>` | Reconstruct master key (all steps required) |
| `pf register-agent <id>` | Register an agent for authenticated execution |
| `pf dashboard` | Start web dashboard (requires Flask) |

## Dashboard

```bash
# Generate a static HTML dashboard (no server needed)
python3 scripts/dashboard_static.py --output report.html
# Open report.html in your browser

# Or start live dashboard
pf dashboard --port 8080
# Open http://localhost:8080
```

The dashboard shows:
- **Tasks tab:** Live status, progress bars, step icons, audit badges
- **Brain Stats tab:** Token savings, cache hit rate, $ saved, hallucinations caught
- **CSV export:** One-click report download

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "agentpathfinder not found" | Run `pf install` to verify setup |
| "Task not found" | Check task ID. Use `pf status` to list recent tasks |
| "Reconstruction failed" | Not all steps complete. Run `pf status` to see which |
| "Step already running" | Previous run crashed. Auto-reset or call `reset_running_step()` |
| "Agent auth failed" | Re-run `pf register-agent <id>` |
| Dashboard won't start | Install Flask: `pip install flask` |
| Audit reports tampered | Files were modified outside the engine. Investigate immediately |

## License

MIT. Free forever. No usage caps. Upgrade to Pro for dashboard and team features.

---

Built by [CertainLogic](https://certainlogic.ai) — deterministic AI, cryptographic proof.
