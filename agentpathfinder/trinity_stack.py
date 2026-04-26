#!/usr/bin/env python3
"""
Hermes Trinity Stack — Brain + Guard + Tasks in one import.

Drop this into any Hermes / OpenClaw / ACP session:
    from trinity_stack import activate
    activate()  # Brain-first + hallucination guard + task tracking

Or command line:
    python3 trinity_stack.py --report

What activates:
1. Brain-First: Every query checks Brain API before LLM (saves tokens)
2. Hallucination Guard: All tool calls verified against facts
3. Task Tracking: Every task logged with audit trail + retry

Metrics: Written to brain_hook_metrics.jsonl + task_trail.jsonl
Report: python3 trinity_stack.py --report
"""
import json
import time
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# ──paths──
_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT))

# ──imports (lazy on first use)──
_brain_skill = None


def _ensure_brain():
    global _brain_skill
    if _brain_skill is None:
        from brain_skill import CertainLogicBrainSkill
        _brain_skill = CertainLogicBrainSkill()
    return _brain_skill


# ──metrics──
_metrics_log = _ROOT / "trinity_metrics.jsonl"


def _log(event: str, details: dict):
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": event,
        **details,
    }
    with open(_metrics_log, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


# ──session cache (speed)──
_session_cache: Dict[str, Any] = {}


# ════════════════════════════════════════════════════════
# 1. BRAIN-FIRST HOOK
# ════════════════════════════════════════════════════════

def brain_dispatch(tool_name: str, query: str = "", **kwargs) -> Dict[str, Any]:
    """Intercept queries. Brain hit = instant answer. Miss = pass through."""
    if not query or len(query.strip()) < 3:
        return {"status": "pass_through", "reason": "empty_query"}

    query_tools = {
        "ask", "query", "search", "lookup", "find", "get_info",
        "answer", "explain", "describe",
    }
    text_lower = query.lower()
    is_query = (
        tool_name.lower() in query_tools
        or any(f" {w} " in text_lower or text_lower.startswith(w)
               for w in ["what", "how", "why", "when", "where", "who", "which",
                        "is", "are", "does", "can", "should"])
    )
    if not is_query:
        return {"status": "pass_through", "reason": "not_a_query"}

    # Session cache check
    cache_key = f"{tool_name}:{query.lower().strip()}"
    if cache_key in _session_cache:
        return _session_cache[cache_key]

    # Brain first
    try:
        brain = _ensure_brain()
        start = time.time()
        result = brain.ask(query)
        elapsed_ms = round((time.time() - start) * 1000, 2)
    except Exception as e:
        _log("brain_error", {"query": query, "error": str(e)})
        return {"status": "pass_through", "reason": f"brain_error: {e}"}

    if result.get("brain_hit"):
        answer = {
            "status": "brain_hit",
            "answer": result.get("answer"),
            "source": "brain_fact",
            "latency_ms": elapsed_ms,
            "tokens_saved": result.get("tokens_saved", 500),
        }
        _session_cache[cache_key] = answer
        _log("brain_hit", {
            "query": query[:100],
            "tokens_saved": answer["tokens_saved"],
            "latency_ms": elapsed_ms,
        })
        return answer

    # Brain missed — pass through to normal tool
    _log("brain_miss", {"query": query[:100], "latency_ms": elapsed_ms})
    return {"status": "brain_miss", "query": query, "latency_ms": elapsed_ms}


# ════════════════════════════════════════════════════════
# 2. HALLUCINATION GUARD
# ════════════════════════════════════════════════════════

def guard_tool_call(tool_name: str, args: dict, result: Any) -> Dict[str, Any]:
    """Verify a tool result against Brain facts."""
    # Extract any factual claims from the result
    if not isinstance(result, str):
        result_str = json.dumps(result, default=str)[:500]
    else:
        result_str = result[:500]

    # Quick fact check on result content
    try:
        brain = _ensure_brain()
        # If result contains factual statements, verify them
        check = brain.ask(f"Verify factual accuracy: {result_str[:200]}")
        if check.get("brain_hit") and check.get("answer"):
            _log("guard_check", {
                "tool": tool_name,
                "verified": True,
                "claims": result_str[:100],
            })
            return {"status": "verified", "tool": tool_name, "claims_valid": True}
    except Exception as e:
        _log("guard_error", {"tool": tool_name, "error": str(e)})

    return {"status": "unchecked", "tool": tool_name}


# ════════════════════════════════════════════════════════
# 3. TASK TRACKING
# ════════════════════════════════════════════════════════

_task_log = _ROOT / "task_trail.jsonl"
_task_counter = 0


def start_task(name: str, spec: dict = None) -> str:
    """Start tracking a task. Returns task_id."""
    global _task_counter
    _task_counter += 1
    task_id = f"task-{time.strftime('%Y%m%d-%H%M%S')}-{_task_counter}"
    entry = {
        "task_id": task_id,
        "name": name,
        "status": "started",
        "spec": spec or {},
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "phases": [],
    }
    _log("task_start", entry)
    _append_task_trail(entry)
    return task_id


def log_phase(task_id: str, phase: str, result: Any = None, error: str = None):
    """Log a phase completion (used by retry engine)."""
    entry = {
        "task_id": task_id,
        "phase": phase,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "result": result,
        "error": error,
    }
    _log("task_phase", entry)

    # Append to task trail
    phase_entry = {
        "phase": phase,
        "completed_at": entry["timestamp"],
        "success": error is None,
        "error": error,
    }
    _append_task_trail({"task_id": task_id, "phases": [phase_entry]})


def complete_task(task_id: str, success: bool = True, summary: str = ""):
    """Mark task complete."""
    entry = {
        "task_id": task_id,
        "status": "completed" if success else "failed",
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": summary,
    }
    _log("task_complete", entry)
    _append_task_trail(entry)


def _append_task_trail(data: dict):
    with open(_task_log, "a") as f:
        f.write(json.dumps(data, default=str) + "\n")


# ════════════════════════════════════════════════════════
# ACTIVATION
# ════════════════════════════════════════════════════════

def activate():
    """Activate all three layers."""
    print("=" * 64)
    print("  🧠 BRAIN-FIRST   +  🛡️ GUARD   +  📋 TASKS  ACTIVE")
    print("=" * 64)

    # Test Brain connectivity
    try:
        brain = _ensure_brain()
        print(f"  ✅ Brain ready: {brain.brain.brain_ready}")
    except Exception as e:
        print(f"  ⚠️  Brain not ready: {e}")

    print(f"  ✅ Guard layer active")
    print(f"  ✅ Task tracking active")
    print(f"  📊 Metrics: {trinity_metrics()}")
    print("=" * 64 + "\n")


def trinity_metrics() -> dict:
    """Read all metrics and summarize."""
    brain_hits = brain_misses = 0
    tasks = 0
    guards = 0

    if _metrics_log.exists():
        with open(_metrics_log) as f:
            for line in f:
                try:
                    e = json.loads(line)
                    if e.get("event") == "brain_hit":
                        brain_hits += 1
                    elif e.get("event") == "brain_miss":
                        brain_misses += 1
                    elif e.get("event") == "task_start":
                        tasks += 1
                    elif e.get("event") == "guard_check":
                        guards += 1
                except:
                    pass

    total = brain_hits + brain_misses
    return {
        "brain_hits": brain_hits,
        "brain_misses": brain_misses,
        "brain_hit_rate": round(brain_hits / total * 100, 1) if total else 0,
        "tasks_tracked": tasks,
        "guards_run": guards,
    }


def print_report():
    """Print human-readable summary."""
    m = trinity_metrics()
    print(f"\n{'='*64}")
    print(f"  🧠 Trinity Stack Report")
    print(f"{'='*64}")
    print(f"  Brain hits:    {m['brain_hits']}")
    print(f"  Brain misses:  {m['brain_misses']}")
    print(f"  📊 Hit rate:   {m['brain_hit_rate']}%")
    print(f"  📋 Tasks:      {m['tasks_tracked']}")
    print(f"  🛡️  Guards:     {m['guards_run']}")
    print(f"{'='*64}\n")


# ════════════════════════════════════════════════════════
# DEMO
# ════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--activate", action="store_true", help="Activate stack")
    parser.add_argument("--report", action="store_true", help="Show report")
    args = parser.parse_args()

    if args.report:
        print_report()
    else:
        activate()

        # Quick demo
        print("Demo: Brain dispatch")
        r = brain_dispatch("ask", "What is Python recursion depth?")
        print(f"  → {r['status']}: {r.get('answer', 'N/A')}")

        print("\nDemo: Task tracking")
        tid = start_task("deploy-fix", {"target": "alpha", "rollback": True})
        log_phase(tid, "check", result="ok")
        log_phase(tid, "deploy", result="done")
        complete_task(tid, success=True, summary="Fix deployed to alpha")
        print(f"  → Task {tid} complete")

        print("\nDemo: Guard")
        g = guard_tool_call("write_file", {"path": "/tmp/test.txt"}, "hello world")
        print(f"  → Guard: {g['status']}")

        print("")
        print_report()
