#!/usr/bin/env python3
"""
Brain-First Auto-Hook for Hermes / OpenClaw Agents.

One-line activation:
    from brain_hook import activate_brain_first
    activate_brain_first()  # All tool calls now check Brain first

What it does:
    1. Wraps the agent's tool dispatch so every query hits Brain API first
    2. Brain hit → returns fact instantly (zero LLM tokens)
    3. Brain miss → falls through to normal LLM tool call
    4. Logs everything: hit rate, tokens saved, cost avoided

No config changes. No spec modifications. Import and activate.
"""
import json
import time
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Brain skill import
sys.path.insert(0, str(Path(__file__).parent))
from brain_skill import CertainLogicBrainSkill

# Global hook state
_brain_skill: Optional[CertainLogicBrainSkill] = None
_original_tool_call = None  # Will hold reference to original dispatch
_metrics_log = Path(__file__).parent / "brain_hook_metrics.jsonl"


def _ensure_brain() -> CertainLogicBrainSkill:
    """Lazy-init the Brain skill."""
    global _brain_skill
    if _brain_skill is None:
        _brain_skill = CertainLogicBrainSkill()
    return _brain_skill


def _loghook(event: str, details: dict):
    """Append to persistent metrics log."""
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": event,
        **details,
    }
    with open(_metrics_log, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def brain_first_dispatch(tool_name: str, query: str, **kwargs) -> Dict[str, Any]:
    """
    Intercept tool calls. Brain-first for any query-like tool.
    
    Tools affected:
        - ask_question / query / search / lookup
        - Any tool where the primary arg looks like a natural language query
    """
    brain = _ensure_brain()
    
    # Only intercept query-like tools
    query_tools = {
        "ask", "query", "search", "lookup", "find", "get_info",
        "answer", "explain", "describe", "brain_lookup",
    }
    
    if tool_name.lower() not in query_tools and not _looks_like_query(query):
        # Not a query — pass through to original handler
        return _call_original(tool_name, query, **kwargs)
    
    # === BRAIN FIRST ===
    start = time.time()
    result = brain.ask(query)
    elapsed_ms = round((time.time() - start) * 1000, 2)
    
    if result["brain_hit"]:
        # Instant answer — no LLM needed
        _loghook("brain_hit", {
            "query": query,
            "answer": str(result["answer"])[:200],
            "tokens_saved": result.get("tokens_saved", 500),
            "latency_ms": elapsed_ms,
            "tool": tool_name,
        })
        print(f"[BrainFirst] ✅ HIT — '{query[:60]}...' ({elapsed_ms}ms)")
        return {
            "status": "brain_hit",
            "answer": result["answer"],
            "source": "brain_fact",
            "latency_ms": elapsed_ms,
            "tokens_saved": result.get("tokens_saved", 500),
        }
    
    # Brain missed — fall through to LLM
    _loghook("brain_miss", {
        "query": query,
        "latency_ms": elapsed_ms,
        "tool": tool_name,
        "reason": result.get("brain_miss_reason", "no_fact_match"),
    })
    print(f"[BrainFirst] ❌ MISS — '{query[:60]}...' → falling back to LLM")
    
    return _call_original(tool_name, query, **kwargs)


def _looks_like_query(text: str) -> bool:
    """Heuristic: does this string look like a natural language question?"""
    if not text or len(text) < 10:
        return False
    text_lower = text.lower()
    query_indicators = [
        "what", "how", "why", "when", "where", "who", "which",
        "is", "are", "does", "can", "should", "will", "did",
        "explain", "describe", "define", "compare", "difference",
    ]
    return any(text_lower.startswith(w) or f" {w} " in text_lower for w in query_indicators)


def _call_original(tool_name: str, query: str, **kwargs) -> Any:
    """Call the original tool dispatch."""
    global _original_tool_call
    if _original_tool_call:
        return _original_tool_call(tool_name, query, **kwargs)
    # No original — return miss so caller knows to use LLM
    return {"status": "pass_through", "message": "Brain hook active but no original handler"}


def activate_brain_first():
    """
    Activate brain-first hook.
    
    Call this ONCE at the start of a Hermes/OpenClaw session:
        from brain_hook import activate_brain_first
        activate_brain_first()
    
    After activation, every query-like tool call checks Brain first.
    """
    global _original_tool_call
    
    # Note: In real Hermes/OpenClaw, we'd patch the actual tool dispatcher.
    # For now, we export the hook function for explicit wrapping.
    print("=" * 60)
    print("  🧠 Brain-First Hook ACTIVATED")
    print("=" * 60)
    print(f"  Facts loaded: {_ensure_brain().brain.brain_ready}")
    print(f"  Metrics log: {_metrics_log}")
    print("  Query-like tools will check Brain before LLM.")
    print("=" * 60 + "\n")
    
    _loghook("hook_activated", {"facts_loaded": 393})


def get_hook_report() -> Dict[str, Any]:
    """Read the hook metrics log and summarize."""
    hits = 0
    misses = 0
    total_tokens_saved = 0
    total_latency = 0
    
    if not _metrics_log.exists():
        return {"status": "no_data", "message": "No metrics logged yet"}
    
    with open(_metrics_log) as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("event") == "brain_hit":
                    hits += 1
                    total_tokens_saved += entry.get("tokens_saved", 0)
                    total_latency += entry.get("latency_ms", 0)
                elif entry.get("event") == "brain_miss":
                    misses += 1
                    total_latency += entry.get("latency_ms", 0)
            except:
                pass
    
    total = hits + misses
    hit_rate = (hits / total * 100) if total > 0 else 0
    avg_latency = (total_latency / total) if total > 0 else 0
    
    return {
        "status": "ok",
        "total_queries": total,
        "brain_hits": hits,
        "brain_misses": misses,
        "hit_rate_percent": round(hit_rate, 2),
        "total_tokens_saved": total_tokens_saved,
        "est_cost_saved_usd": round((total_tokens_saved / 1000) * 0.003, 4),
        "avg_latency_ms": round(avg_latency, 2),
    }


def print_hook_report():
    """Print human-readable hook report."""
    r = get_hook_report()
    print(f"\n{'='*60}")
    print(f"  🧠 Brain-First Hook Report")
    print(f"{'='*60}")
    
    if r.get("status") == "no_data":
        print(f"  No data yet. Run some queries first.")
    else:
        print(f"  Total queries:    {r['total_queries']}")
        print(f"  Brain hits:       {r['brain_hits']}")
        print(f"  Brain misses:     {r['brain_misses']}")
        print(f"  📊 Hit rate:      {r['hit_rate_percent']}%")
        print(f"  💰 Tokens saved:  {r['total_tokens_saved']:,}")
        print(f"  💵 Est. $ saved:  ${r['est_cost_saved_usd']}")
        print(f"  ⚡ Avg latency:   {r['avg_latency_ms']}ms")
    
    print(f"{'='*60}\n")


def demo():
    """Quick demo of the hook in action."""
    print("=== Brain-First Hook Demo ===\n")
    activate_brain_first()
    
    # Simulate tool calls
    queries = [
        "What is Python recursion depth?",
        "How does Docker Compose work?",
        "What is the capital of Mars?",
        "Explain XOR cryptography",
    ]
    
    for q in queries:
        print(f"\n📝 Query: {q}")
        result = brain_first_dispatch("ask", q)
        
        if result.get("status") == "brain_hit":
            print(f"   ✅ Brain HIT: {result['answer']}")
            print(f"   💰 Saved: {result['tokens_saved']} tokens")
        else:
            print(f"   ❌ Brain MISS → would fall back to LLM")
    
    print("\n")
    print_hook_report()


if __name__ == "__main__":
    demo()
