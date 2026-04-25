# AgentPathfinder v2

Deterministic task orchestration with cryptographic sharding, tamper-proof audit trails, and agent authentication.

## One-Line Install & Launch

```bash
clawhub install agentpathfinder
pf install
```

Done in under 5 minutes.

## Quickstart

```bash
# Create a 3-step task
pf create "deploy" build push verify
# → ✅ Task created: <uuid>

# Simulate running all steps
pf run <uuid>
# → ✅ deploy is complete! Progress 3/3

# Check status (emoji indicators)
pf status <uuid>
# → ✅ Step 1: build | ✅ Step 2: push | ✅ Step 3: verify

# View audit trail with HMAC verification
pf audit <uuid>
# → ✅ All 5 events verified

# Reconstruct master key (only if all steps completed)
pf reconstruct <uuid>
# → ✅ Key reconstructed

# Register an agent
pf register-agent worker_1
# → 🔑 API key: 0703e5a…b94527

# Start the web dashboard (zero deps!)
pf dashboard --start
# → 🌐 http://localhost:8080
```

## Visual Confirmation

All CLI output includes visual at-a-glance indicators:

| Outcome | Badge |
|---------|-------|
| Success | `✅ Task complete` |
| Failure | `❌ Task failed` + retry suggestion |
| Running | `⏳ Step N running...` |
| Warning | `⚠️ Crash detected` |

## Dashboard

The unified web dashboard (`dashboard_server.py`) shows:
- **Tasks** — live list, step progress, audit integrity, tokens
- **Brain API** — cache hit rate, tokens saved, $ saved, hallucinations caught
- **Exports** — JSON endpoints at `/api/tasks`, `/api/brain`, `/api/health`
- Auto-refreshes every 30s. Zero dependencies.

## Python SDK

```python
from pathfinder_client import PathfinderClient

pf = PathfinderClient()
tid = pf.create("migration", ["backup", "migrate", "validate"])
pf.run(tid)
print(pf.status(tid))
```

See `SKILL.md` for full documentation.

## Files

| File | Purpose |
|------|---------|
| `scripts/pathfinder_client.py` | CLI + SDK wrapper |
| `scripts/visual.py` | Emoji, ANSI color, formatter macros |
| `scripts/dashboard_server.py` | Unified web dashboard (stdlib HTTP) |
| `SKILL.md` | Full documentation |
| `skill.json` | ClawHub metadata |
