# AgentPathfinder

**Green = proven. Red = not. No more trusting "Done" from AI agents. 🟢🔴**

<p align="center">
  <a href="https://clawhub.ai/certainlogicai/agentpathfinder-agent-task-tracker-free">
    <img src="https://img.shields.io/badge/ClawHub-v1.2.2-blue?logo=package" alt="ClawHub">
  </a>
  <a href="https://github.com/CertainLogicAI/agentpathfinder">
    <img src="https://img.shields.io/github/stars/CertainLogicAI/agentpathfinder?style=social" alt="Stars">
  </a>
</p>

---

## The Problem

Your AI agent says **"Done"** — but did it actually finish? Or did it fail step 3 silently and move on? 

You only find out when your customer does. 😤

**AgentPathfinder** gives you cryptographic proof of every step. Green = cryptographically verified complete. Red = failed or not run. No surprises.

---

## 30-Second Demo

```bash
# 1. Install
clawhub install agentpathfinder

# 2. Create a tamper-evident task
pf create deploy "test → build → push → restart"
# → Task created: deploy-a7f3d2e1

# 3. Run it (you see every step)
pf run deploy-a7f3d2e1
# → ✅ test passed
# → ✅ build complete  
# → ✅ push complete
# → ✅ restart complete
# → ✅ deploy-a7f3d2e1 DONE — all 4 steps verified
```

**That's it.** Every step was cryptographically signed. If anyone tampers with the results, `pf audit` catches it instantly.

---

## What You Get (Free Forever)

| Feature | Details |
|---------|---------|
| ✅ **Unlimited tasks** | No usage caps. Ever. |
| 🔒 **Cryptographic proof** | Every step HMAC-signed with derived audit key |
| 🧠 **Brain-first queries** | Checks local facts DB before burning LLM tokens |
| 🛡️ **Hallucination guard** | Auto-validates outputs against known facts |
| 📋 **Tamper-evident audit** | Any edit to results breaks verification |
| 🔄 **Crash recovery** | Interrupted tasks resume safely |
| 🖥️ **Dashboard** (static) | Zero-dependency HTML report |

---

## Why Free Forever?

We sell ** peace of mind**, not seat licenses.

- Free = CLI + local vault + unlimited use
- Pro = Dashboard + multi-agent views + team syncing + webhooks
- Enterprise = On-prem, SSO, compliance exports

**Install costs $0. Upgrade when you're ready.**

---

## The Story

> *"I got tired of my agents saying 'Done' only to find out they failed halfway through and didn't tell me. Built a tracker that proves every step. Now I sleep better."*
> — Anton, @CertainLogicAI

---

## Install

```bash
# Via ClawHub (recommended)
clawhub install agentpathfinder

# Via pip
pip install git+https://github.com/CertainLogicAI/agentpathfinder.git

# Or clone and run
 git clone https://github.com/CertainLogicAI/agentpathfinder.git
cd agentpathfinder && python3 -m agentpathfinder
```

## Quick Start

```bash
# Create a task with 4 steps
pf create deploy_api "run_tests" "build_image" "push_registry" "restart_service"

# Check status (emoji indicators)
pf status deploy_api
# → ✅ deploy_api 4/4 complete

# Tamper check
pf audit deploy_api
# → ✅ All 6 events cryptographically verified

# Reconstruct master key (all steps must pass)
pf reconstruct deploy_api
# → ✅ Key reconstructed
```

---

## Advanced: Python SDK

```python
from agentpathfinder import PathfinderClient, AgentRuntime

pf = PathfinderClient()
tid = pf.create("deploy", ["test", "build", "push"])

# Bind real functions
runtime = AgentRuntime(pf.engine, pf.issuing)
runtime.execute_task(tid, {
    "test": lambda: pytest.main(["-v"]),
    "build": lambda: docker.build("."),
    "push": lambda: docker.push("app"),
})

# If a step fails, retry after fixing
runtime.retry_step(tid, 2, docker.build)
```

---

## Waitlist: Pro Dashboard

The Pro dashboard is shipping soon. Features:

- 🖥️ **Live multi-agent view** — see all your agents' tasks in one place
- 📊 **Team workspace** — share tasks, assign agents, track progress
- 🔗 **Webhook notifications** — Slack, Discord, email alerts
- 📈 **Metrics & trends** — tokens saved, brain hit rate, audit history
- 🌐 **Hosted vault** — no local filesystem worries

**Join the waitlist:** Star this repo and DM [@CertainLogicAI](https://x.com/CertainLogicAI) with "pro".

---

## Security

| Threat | Protection |
|--------|-----------|
| Tampered results | HMAC-SHA256 audit chain — any edit breaks verification |
| Crash mid-task | Atomic writes + crash recovery |
| Concurrent access | Advisory file locks per task |
| Unauthorized agents | 256-bit API keys + HMAC-signed requests |
| Local vault breach | Upgrade to Pro for hosted vault (no filesystem access) |

See [SAFETY.md](SAFETY.md) for full disclosure.

---

## Architecture (50 words)

TaskEngine generates 256-bit master key → splits via XOR into N+1 shards → stores shards in vault, metadata in task JSON → AgentRuntime executes steps, gets HMAC-signed tokens → AuditTrail logs everything → reconstruction only when all steps pass.

---

## Contributing

MIT license. PRs welcome. Issues = features we didn't think of yet.

**Built by:** [CertainLogic](https://certainlogic.ai) — deterministic AI, cryptographic proof.
