---
summary: "Cryptographic audit trails for AI agent tool calls"
read_when: ["installing", "configuring", "troubleshooting"]
name: AgentPathfinder
description: |
  Cryptographically signed audit trails for AI agent tool calls. Every tool invocation is HMAC-SHA256 signed. Full arguments and results logged. Live dashboard shows which command failed, what the error was, whether agent claimed success falsely. The provenance layer for agent execution.
  
  ✅ See which specific tool failed and why
  ✅ Catch agents claiming success when tools errored  
  ✅ Detect missing tool calls (agent lied about execution)
  ✅ Visual dashboard with real-time HMAC signatures
  ❌ Does NOT verify work was actually done — records claims only
  
  Free forever — no usage caps, no telemetry. Data stays in ~/.agentpathfinder only.
  
  See SAFETY.md for full disclosure of limitations.
version: "1.3.0"
author: CertainLogic
license: MIT
platforms: [linux, macos]
---

# AgentPathfinder

**Your AI agent said "Done." Prove it.** Cryptographically signed tool-level audit trails. See exactly which command failed, what the error was, and whether your agent lied about success.

## What This Is

This system gives you a **cryptographically signed, tamper-evident record of what your agent claims happened.** The audit trail detects unauthorized edits. **It does not independently verify that the agent's claim is true.** An agent can still falsely claim completion — the system just records that claim with a signature so you know who said what when.

## What You Get

| Feature | How It Works | Truth Status |
|---------|-------------|--------------|
| ✅ Signed task tracking | Green = agent signed claim of completion | NOT verified — recorded only |
| ❌ Signed failure tracking | Red = agent signed claim of failure | NOT verified — recorded only |
| 🔒 Cryptographic signing | HMAC-SHA256 signatures on every claimed event | Signature is real |
| 📋 Tamper-evident audit | Unauthorized edits break HMAC signatures | Tampering detected if no key |
| 🔄 Crash recovery | Atomic writes + fsync + rename | Works |
| 📊 Visual status | `pf status` shows ✅/❌/⏳ at a glance | Shows CLAIMED status |
| 💬 Chat notifications | SDK callbacks send updates to your agent's chat | Real-time status updates |

**Pro (coming soon):** Dashboard, multi-agent tracking, audit exports, webhooks.
**Enterprise:** On-prem, SSO/SAML, hosted vault.

## What This Is NOT

| ❌ Does NOT | Why |
|-------------|-----|
| Verify tasks are actually complete | It records claims. You must verify the work independently. |
| Prevent agents from lying | It signs what the agent says. False claims get signed too. |
| Replace human verification | It helps you track claims. You still need to check the actual work. |
| Prove truth of claims | It proves who claimed what and when. Not whether the claim is true. |

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
#    ✅ deploy_api is complete per agent claim. Progress: 4/4
#    ✅ Step 1: agent claimed run_tests complete (token: tok_abc123…)
#    ✅ Step 2: agent claimed build_docker complete (token: tok_def456…)

# Check status — one glance shows CLAIMED status
pf status a7f3d2e1-...
# → ✅ task_complete 4/4 (all green — agent claims complete)
# ⚠️ Remember: green = agent claimed complete, not verified complete

# Check audit integrity (NOT truth verification)
pf audit a7f3d2e1-...
# → ✅ All 6 events signed — integrity intact
# → ⚠️ Signing integrity means no unauthorized edits. Not validated truth.

# Reconstruct the master key (requires all steps to have been CLAIMED complete)
pf reconstruct a7f3d2e1-...
# → ✅ Key reconstructed — all claimed steps present
# → ⚠️ Reconstruction proves all claimed steps exist. Not that they succeeded.
```

## Chat Notifications

Get step/task status updates in your agent's main chat channel:

```python
from agentpathfinder import AgentRuntime

# Define notification callbacks
# These run synchronously when state changes occur

def notify_step_complete(step_number, result):
    # Your agent sends chat message here
    # e.g., message.send(f"✅ Step {step_number} complete")
    print(f"✅ Step {step_number} complete: {result}")

def notify_step_fail(step_number, error):
    # Your agent sends chat message here
    # e.g., message.send(f"❌ Step {step_number} failed")
    print(f"❌ Step {step_number} failed: {error}")

def notify_task_done(task_id, status):
    # Your agent sends chat message here
    # e.g., message.send(f"📋 Task done: {status['completed_steps']}/{status['num_steps']}")
    print(f"📋 Task {task_id} complete: {status['completed_steps']}/{status['num_steps']}")

# Create runtime with callbacks
runtime = AgentRuntime(
    pf.engine, pf.issuing,
    on_step_complete=notify_step_complete,
    on_step_fail=notify_step_fail,
    on_task_complete=notify_task_done
)

# Execute — notifications fire automatically
runtime.execute_task(task_id, step_functions)
```

**How it works:**
- `on_step_complete(step_number, result)` — fires after step succeeds and token is issued
- `on_step_fail(step_number, error)` — fires after step throws exception
- `on_task_complete(task_id, status)` — fires after all steps complete (or task paused)

**Limitations:**
- Callbacks are synchronous — they block execution until they return
- CLI users don't get notifications (no OpenClaw context)
- Your agent must implement the actual message sending (we provide the hook, you wire it)

## Real Execution (Python SDK)

The SDK **executes functions YOU provide and records what they return.**

```python
from pathfinder_client import PathfinderClient
from agentpathfinder import AgentRuntime

pf = PathfinderClient()
tid = pf.create("deploy", ["test", "build", "push"])

# Bind real functions — YOU must independently verify they work
def run_tests():
    result = pytest.main(["-v"])
    # ⚠️ Pathfinder records that this function was called
    # ⚠️ It does NOT independently verify the tests actually passed
    return "passed" if result == 0 else "failed"

# Execute
runtime = AgentRuntime(pf.engine, pf.issuing)
runtime.execute_task(tid, {
    "test": run_tests,
    "build": lambda: docker.build("."),
    "push": lambda: docker.push("app"),
})

# If any step fails → task pauses, audit trail shows what agent claimed happened
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

**Tamper-evident in audit trail, not tamper-proof against the agent.**

- ✅ **Unauthorized edits** to the audit log → HMAC verification fails → detected
- ❌ **Authorized agent** writes false claim → HMAC verification passes → NOT detected
- ❌ **Agent with filesystem access** to `~/.agentpathfinder/vault/` → can read shards, reconstruct key, forge claims

| Feature | How It Works | Verification Status |
|---------|-------------|-------------------|
| Cryptographic sharding | 256-bit master key → N+1 shards via XOR | Real |
| Atomic persistence | temp + fsync + rename — no partial writes | Real |
| Crash recovery | Steps in `running` state detected and reset | Real |
| Concurrency control | Advisory file locks per task | Real |
| Audit integrity | HMAC-SHA256 chain, unauthorized edits detected | Real |
| Agent authentication | Shared-secret HMAC tokens per agent | Real |
| Claim verification | None — signs whatever agent provides | NOT implemented |

For full isolation from agent tampering: upgrade to Pro (hosted vault) or Enterprise (TEE/remote attestation).

## Frequently Asked Questions

**Q: Does "green = complete" mean the task was actually finished?**
A: No. Green means the agent CLAIMED completion and the claim was signed. The claim itself is not independently verified.

**Q: Can an agent trick the system by saying "done" when the task failed?**
A: Yes. The system records and signs whatever the agent claims. You must independently verify the actual work.

**Q: What does "cryptographically signed" actually prove?**
A: It proves: (1) who made the claim, (2) when they made it, (3) that the claim hasn't been edited by anyone without the signing key. It does NOT prove the claim is true.

**Q: How is this different from just trusting the agent?**
A: You get a signed, tamper-evident record of what the agent claimed. This is useful for accountability ("who said what when") and detecting unauthorized edits. But the agent's claims themselves are still trusted.

**Q: Will Pro or Enterprise add real verification?**
A: Pro adds dashboard/convenience. Enterprise may add TEE/hosted vault for stronger isolation. Neither automatically verifies that agent claims are true. Independent verification is always required.

## Data Storage

**All data stays in `~/.agentpathfinder/` only.** No external servers, no telemetry, no analytics.

| What | Where | Content |
|------|-------|---------|
| Task metadata | `~/.agentpathfinder/tasks/*.json` | Task name, steps, agent-reported status |
| Vault shards | `~/.agentpathfinder/vault/*.shard` | 32-byte shards per step |
| Audit trail | `~/.agentpathfinder/audit/*.jsonl` | HMAC-signed event claims |
| Agent config | `~/.agentpathfinder/agents/registry.json` | Agent IDs, shared secrets |

## CLI Reference

| Command | What It Does | Claim Verification |
|---------|-------------|-------------------|
| `pf install` | One-command setup, verify deps | N/A |
| `pf create <name> [steps...]` | Create a new sharded task | N/A |
| `pf run <task_id>` | Simulate running all steps (records claims) | Signs agent claims, does NOT verify |
| `pf status <task_id>` | Visual status: ✅/❌/⏳ at a glance | Shows CLAIMED status |
| `pf audit <task_id>` | Show audit trail signing integrity | Detects unauthorized edits |
| `pf reconstruct <task_id>` | Reconstruct master key | Requires all steps CLAIMED complete |
| `pf register-agent <id>` | Register an agent for authenticated execution | N/A |

**Free tier is task tracking with honest limitations:** local vault, no encryption, agent must be trusted with filesystem access. Upgrade for encrypted vault and other protections.

## License

MIT. Free forever. No usage caps. Pro dashboard coming soon.

---

Built by [CertainLogic](https://certainlogic.ai) — honest tools for honest builders.
