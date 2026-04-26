# CertainLogic Brain-First Skill

**One import. Zero config. Every query hits your Brain facts before burning LLM tokens.**

## What It Does

Drop this into any Hermes / OpenClaw / Claude Code / Cursor session:

```python
from brain_hook import activate_brain_first
activate_brain_first()
```

After activation:
- ✅ Every question-like query checks Brain API **first**
- ✅ Brain hit → instant answer (0 tokens, ~3ms, 100% accurate)
- ✅ Brain miss → falls through to LLM (tracked for gap analysis)
- ✅ All metrics logged automatically

**Results from our test run:**
- 4/4 queries answered from Brain
- 2,000 tokens saved
- $0.006 saved
- 2.42ms average latency
- 100% hit rate on known facts

## For Agents (Free)

Drop in any session:

```python
from brain_hook import activate_brain_first, print_hook_report
activate_brain_first()

# ... do work ...

print_hook_report()  # See tokens saved
```

## For Users (Pro Feature)

**Dashboard coming soon.** Track across all your agents:
- Brain hit rate per agent
- Total tokens saved
- Cost avoided
- Fact gaps (what to add to Brain)
- Trending queries

**Why Pro?**
- Team-wide metrics aggregation
- Multi-agent Brain sync
- Scheduled auto-prewarm
- Priority fact ingestion

## Metrics Log

Every query writes to `brain_hook_metrics.jsonl`:

```json
{"timestamp": "2026-04-26T10:25:00Z", "event": "brain_hit", "query": "What is Python recursion depth?", "tokens_saved": 500, "latency_ms": 2.97}
```

Aggregate anytime:

```python
from brain_hook import print_hook_report
print_hook_report()
```

## Requirements

- Brain API running at `http://127.0.0.1:8000` (or set `BRAIN_API` env var)
- 393+ facts pre-loaded (or add your own)

## Install

```bash
clawhub install agentpathfinder  # Includes brain_hook.py
```

Or copy `brain_hook.py` into your project.

## Why This Matters

**Without Brain-First:**
```
User: "What is Python recursion depth?"
Agent: → calls LLM → 500 tokens → $0.0015 → answer: "1000"
```

**With Brain-First:**
```
User: "What is Python recursion depth?"
Agent: → checks Brain → 3ms → 0 tokens → $0 → answer: "1000"
```

**Scale that across 1000 queries/day = $1.50 saved daily = $45/month.**

## License

MIT. Free forever for individuals. Pro dashboard is paid.
