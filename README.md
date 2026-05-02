# AgentPathfinder

**Green = agent said done. Red = agent said failed. Know what your agent actually claimed.** ✅❌

<p align="center">
  <a href="https://clawhub.ai/certainlogicai/agentpathfinder-agent-task-tracker-free">
    <img src="https://img.shields.io/badge/ClawHub-v1.3.0-blue?logo=package" alt="ClawHub">
  </a>
  <a href="https://github.com/CertainLogicAI/agentpathfinder">
    <img src="https://img.shields.io/github/stars/CertainLogicAI/agentpathfinder?style=social" alt="Stars">
  </a>
</p>

---

## What This Is

A **receipt system for AI agents.** It records who claimed what and when, with proof that the record wasn't tampered with. 

Like a security camera — it doesn't stop theft, but it shows you who was there. AgentPathfinder doesn't stop agents from making mistakes, but it proves what they claimed with a signature you can verify.

---

## The Problem

Your AI agent says **"Done"** — but did it actually finish?

> "If an agent can't show you what it claimed, you're just trusting a hallucination machine. No receipts, no trust." 
> — [@alexabelonix](https://x.com/alexabelonix), 10x hackathon winner, 20K followers

It skipped step 3. Failed silently. Moved on.

You only find out when your customer does. 😤

**AgentPathfinder** gives you a signed record of every step. Green = agent signed claim of completion. Red = agent signed failure. You see what was claimed, not just what was said.

---

## 30-Second Demo

```bash
# 1. Install
clawhub install agentpathfinder

# 2. Create a signed task
pf create deploy "test → build → push → restart"
# → Task created: deploy-a7f3d2e1

# 3. Run it (you see every claim)
pf run deploy-a7f3d2e1
# → ✅ test: agent claimed passed
# → ✅ build: agent claimed complete  
# → ✅ push: agent claimed complete
# → ✅ restart: agent claimed complete
# → ✅ deploy-a7f3d2e1 DONE — all 4 steps recorded

# 4. Check signing integrity
pf audit deploy-a7f3d2e1
# → ✅ All 6 events signed — integrity intact
# → ⚠️ Note: This shows WHO claimed WHAT. Not whether the claim is true.
```

Every step is signed by the agent. If someone edits the results file without permission, `pf audit` detects the change.

---

## What This Does vs. What It Doesn't

| What It **Does** | What It **Does NOT** |
|------------------|----------------------|
| ✅ Records what your agent claimed (like a receipt) | ❌ Check if the agent actually did the work |
| ✅ Signs each claim so you know who said it | ❌ Prove the claim is true |
| ✅ Detects if someone edited the records | ❌ Stop agents from lying |
| ✅ Lets you resume if your agent gets interrupted | ❌ Run or test the work itself |
| ✅ Tells you which agent claimed what when | ❌ Replace human review |

---

## What You Get (Free Forever)

| Feature | What It Means |
|---------|-------------|
| ✅ **Unlimited tasks** | Make as many task checklists as you want. No caps. |
| 🔒 **Proof of who said what** | Every step is signed. You know which agent claimed what, and when. |
| 📋 **Tamper-proof records** | If someone edits the task history without permission, you'll know. The signature breaks. |
| 🔄 **Resume where you left off** | If your agent gets interrupted (power loss, killed, timed out), see exactly which step it was on. Retry from there instead of starting over. |
| 💬 **Chat notifications** | SDK callbacks send real-time step/task updates to your agent's main chat channel. See progress as it happens. |
| 🖥️ **Dashboard** (static) | One-page HTML report of all your tasks. No server needed. |
| 🧠 **Optional Brain integration** | Pull facts from your knowledge base if you have one set up. |
| 🔧 **Tool chain audit** *(v1.3)* | Cryptographically log every tool call and result. Full args and output, not just hashes. Sub-tool chains tracked up to depth 50. |

---

## What Tool Chain Audit Does (v1.3)

**Problem:** You trust your agent to run `exec`, `browser`, or `write` operations. But if something goes wrong, you have no record of exactly which command ran, what it got back, and whether the log was tampered with.

**Solution:** Every tool call is HMAC-signed in the same audit trail as task events:

```python
from agentpathfinder import TaskEngine

engine = TaskEngine()
task_id = engine.create_task("deploy", [{"name": "test"}, {"name": "build"}])

# Get tool audit for step 1
audit = engine.get_tool_audit(task_id, step_number=1)

# Log a tool call with full args
tool_id = audit.log_tool_call("exec", {"command": "pytest --tb=short"})

# ... run the command ...

# Log the result with full output
audit.log_tool_result(tool_id, {"stdout": "3 passed, 0 failed", "stderr": ""})
```

**What gets logged:**
- Tool name and category (system_command, web_automation, filesystem, etc.)
- Full arguments (not just hashes)
- Full output or error details
- Duration and exit code
- Sub-tool depth and parent references

**Why this matters for company brain:**
When your agent writes to production, you need to know exactly what command ran and what happened. Not a hash of it — the actual command. Signed so you know it wasn't edited later.

---

---

## Why Free Forever?

- Free = CLI + local vault + unlimited use
- Pro = Dashboard + multi-agent views + team syncing + webhooks
- Enterprise = On-prem, SSO, compliance exports

**Install costs $0. Upgrade when you're ready.**

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
# → ✅ deploy_api 4/4 complete — agent reported all steps done

# Check signing integrity (NOT truth verification)
pf audit deploy_api
# → ✅ All 6 events signed — integrity intact
# → ⚠️ Signing integrity means: no unauthorized edits. Not: claims are true.

# Reconstruct master key (requires all steps to have been claimed complete)
pf reconstruct deploy_api
# → ✅ Key reconstructed — all reported claims present
```

---

## Advanced: Python SDK

```python
from agentpathfinder import TaskEngine, AgentRuntime, IssuingLayer, AuditTrail

# Create a task engine (stores tasks locally in ~/.agentpathfinder)
engine = TaskEngine()
task_id = engine.create_task("deploy", [{"name": "test"}, {"name": "build"}, {"name": "push"}])

# Set up the signing layer
issuer = IssuingLayer(engine)

# Create runtime to execute steps
runtime = AgentRuntime(engine, issuer)

# Run the task with your own functions
runtime.execute_task(task_id, {
    "test": lambda: your_test_function(),   # YOU must verify this ran
    "build": lambda: your_build_function(), # YOU must verify output
    "push": lambda: your_push_function(),   # YOU must verify registry
})
```

---

## Live Audit Dashboard (v1.3.0)

Watch your agent's tool calls in real-time with cryptographic proof.

```bash
# Generate dashboard for a specific task
python3 scripts/dashboard_v130.py generate --task deploy_api
# → Opens dashboard.html in your browser

# Watch mode: auto-refreshes every 2 seconds
python3 scripts/dashboard_v130.py watch
```

**What you see:**
- 🔧 Every tool call with full arguments
- ✅ Every tool result with exit code and output
- 🔐 HMAC signature next to each event
- 🛡️ Integrity panel: "17 events, 0 tampered"
- ⚠️ Fraud alerts: missing tool results, hanging calls

**Dashboard preview:**
```
Task: deploy_api                    Status: 🔄 Running
Agent: agent_1                     Started: 14:23:01 UTC

Step 1: run_tests
├── 🔧 TOOL_INVOKED  14:23:02  exec
│   args: {command: "pytest tests/ --tb=short", timeout: 120}
│   🔐 HMAC: a1b2c3d4e5f6...
│
├── ✅ TOOL_RESULT   14:23:05  2.3s
│   exit_code: 0
│   stdout: "47 passed in 2.34s"
│   🔐 HMAC: 7d8e9f0a1b2c...

🔐 Audit Trail Integrity    17 events
  Valid HMAC:    17/17 ✅    Tampered: 0
```

**Why this matters:** Other platforms show you traces. AgentPathfinder shows you proof.
```

**The SDK executes the functions YOU provide.** AgentPathfinder records that the function was called and what it returned. It does NOT independently verify that the function actually did what it claimed.

---

## Chat Notifications (Send Status to Your Agent's Chat)

Get real-time step and task updates delivered to your agent's main chat channel:

```python
from agentpathfinder import AgentRuntime

# Define notification callbacks — your agent sends messages as state changes
def notify_step_complete(step_number, result):
    message.send(f"✅ Step {step_number} complete")

def notify_step_fail(step_number, error):
    message.send(f"❌ Step {step_number} failed: {error}")

def notify_task_done(task_id, status):
    message.send(f"📋 Task {task_id} finished: {status['progress']}")

# Create runtime with chat hooks
runtime = AgentRuntime(
    engine, issuer,
    on_step_complete=notify_step_complete,
    on_step_fail=notify_step_fail,
    on_task_complete=notify_task_done
)

# Execute — your chat receives live updates as steps run
runtime.execute_task(task_id, {
    "test": run_tests,
    "build": build_image,
    "push": push_registry,
})
```

**What you see in chat:**
```
✅ Step 1 complete
✅ Step 2 complete
❌ Step 3 failed: Connection timeout
📋 Task deploy-abc123 paused: 2/4 steps complete
```

**How it works:**
- `on_step_complete(step, result)` — fires when step succeeds + token issued
- `on_step_fail(step, error)` — fires when step throws exception
- `on_task_complete(task_id, status)` — fires when all steps done (or task paused)

**Important:**
- Callbacks are synchronous — they block until your `message.send()` returns
- CLI users don't get chat (no agent context) — SDK only
- You implement `message.send()` — we provide the hooks, you wire to your channel

---

## Waitlist: Pro Dashboard

**Note:** Pro dashboard adds convenience views. It does NOT add automatic verification of whether agent claims are true.

- 🖥️ **Live multi-agent view** — see what agents claimed in one place
- 📊 **Team workspace** — share tasks, assign agents, track reported progress
- 🔗 **Webhook notifications** — alert when steps are reported complete
- 📈 **Metrics & trends** — report completion rates, audit history
- 🌐 **Hosted vault** — no local filesystem worries

**Join the waitlist:** Star this repo and DM [@CertainLogicAI](https://x.com/CertainLogicAI) with "pro".

---

## Security

| Threat | What It Does | Limitation |
|--------|-------------|------------|
| Someone edited the task records | Signatures catch unauthorized changes | ✅ Works |
| Agent lies about doing the work | Signs the lie anyway (not a lie detector) | ❌ Does NOT detect false claims |
| Your agent stopped mid-task | You can see which step it was on and retry | ✅ Works |
| Multiple agents working at once | One task at a time per agent (prevents mix-ups) | ✅ Works |
| Wrong agent tries to record tasks | API keys check who's allowed | ✅ Works |
| **Agent snoops on your system** | Signs whatever it finds (can't tell it's forged) | ❌ **Not detected — see below** |
| Local vault breach (unauthorized user) | Upgrade to Pro for encrypted hosted vault | ⚠️ Adds encryption, not complete protection |

⚠️ **Honest limitation:** If an AI agent has full access to your system, it could theoretically find the signing key and create fake records that look valid. The records would pass our automated checks. **Only human review of the actual work catches this.** This is why the free tier is for personal use — upgrade to Pro or Enterprise if you need stronger protection.

---

## How It Works (Simple)

1. You create a task ("deploy website" with steps: test → build → push)
2. Your agent runs each step, recording what it claims happened
3. Every claim is signed — shows who claimed it, when, and what they claimed
4. You check the audit log to see what was claimed (not whether it's true)

**No server needed.** Everything stays on your machine.

---

## Contributing

MIT license. PRs welcome. Issues = features we didn't think of yet.

**Built by:** [CertainLogic](https://certainlogic.ai) — honest tools for honest builders.
