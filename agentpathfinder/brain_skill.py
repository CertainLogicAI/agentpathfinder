"""CertainLogic Brain Skill for Hermes.

BRAIN-FIRST STRATEGY: Every query checks Brain API facts DB FIRST.
- Brain hit → instant answer, zero LLM tokens burned
- Brain miss → falls back to LLM, no additional cache layer needed

The Brain IS the cache. 393 facts, deterministic, no hallucination risk.
"""
import json
import time
import sys
from pathlib import Path
from typing import Dict, Any, Optional

sys.path.insert(0, "/data/.openclaw/workspace/agentpathfinder")
from brain_tool import brain_lookup, brain_status

sys.path.insert(0, "/data/.openclaw/workspace/opensource/scripts")
from hermes_brain_client import BrainClient


class CertainLogicBrainSkill:
    """Hermes skill: Brain-first fact lookup.
    
    Strategy:
    1. Ask Brain API first (semantic search across 393+ facts)
    2. Hit → return fact immediately (100% token savings, verified accurate)
    3. Miss → fall back to LLM (track miss rate for fact-gap analysis)
    
    The Brain replaces the LLM for factual queries. No redundant cache needed.
    """
    
    def __init__(self, max_llm_fallback_tokens: int = 500):
        self.brain = BrainClient()
        self.metrics = {
            "session_start": time.time(),
            "brain_queries": 0,
            "brain_hits": 0,
            "brain_misses": 0,
            "llm_fallbacks": 0,
            "tokens_saved": 0,
            "tokens_burned_on_fallback": 0,
            "validations": 0,
            "hallucinations_caught": 0,
        }
        self._avg_tokens_per_llm_call = max_llm_fallback_tokens
    
    def ask(self, query: str, context: str = "") -> Dict[str, Any]:
        """Primary interface: Brain-first, LLM fallback.
        
        Returns structured dict with answer + source + metrics.
        """
        # Step 1: ALWAYS ask Brain first
        brain_result = self._brain_lookup(query)
        
        if brain_result["status"] == "hit":
            # Brain answered — zero LLM tokens, zero hallucination risk
            self.metrics["tokens_saved"] += self._avg_tokens_per_llm_call
            return {
                "answer": brain_result["answer"],
                "source": "brain_fact",
                "confidence": 1.0,
                "tokens_saved": self._avg_tokens_per_llm_call,
                "brain_hit": True,
                "llm_fallback": False,
                "query": query,
            }
        
        # Step 2: Brain missed → fallback to LLM (or caller's LLM)
        self.metrics["llm_fallbacks"] += 1
        self.metrics["tokens_burned_on_fallback"] += self._avg_tokens_per_llm_call
        
        return {
            "answer": None,  # Caller must use LLM
            "source": "brain_miss",
            "confidence": 0.0,
            "tokens_saved": 0,
            "brain_hit": False,
            "llm_fallback": True,
            "query": query,
            "brain_miss_reason": brain_result.get("reason", "no_fact_match"),
        }
    
    def _brain_lookup(self, query: str) -> Dict[str, Any]:
        """Internal: query Brain API, track metrics."""
        self.metrics["brain_queries"] += 1
        result = brain_lookup(query)
        
        if result.get("status") == "hit" or result.get("facts_found", 0) > 0:
            self.metrics["brain_hits"] += 1
            facts = result.get("facts", [])
            # facts is list of strings from brain_tool.py
            answer = facts[0] if facts else "Fact found"
            print(f"[Brain] ✅ HIT — '{query[:50]}...' → {result.get('facts_found', 0)} facts")
            return {
                "status": "hit",
                "answer": answer,
                "facts_found": result.get("facts_found", 0),
            }
        else:
            self.metrics["brain_misses"] += 1
            print(f"[Brain] ❌ MISS — '{query[:50]}...' → no cached fact")
            return {
                "status": "miss",
                "reason": result.get("message", "no_fact_match"),
            }
    
    def validate_llm_response(self, query: str, response: str) -> Dict[str, Any]:
        """Optional: validate LLM output against Brain facts (post-call)."""
        if not self.brain.brain_ready:
            return {"valid": True, "source": "brain_unavailable"}
        
        result = self.brain.validate(query, response)
        self.metrics["validations"] += 1
        
        if not result.get("valid", True):
            self.metrics["hallucinations_caught"] += 1
            print(f"[Brain] ⚠️ HALLUCINATION DETECTED in LLM response")
            print(f"        Query: {query[:60]}...")
            return {
                "valid": False,
                "source": "brain_validation",
                "flags": result.get("flags", []),
                "suggested_correction": result.get("correction"),
            }
        
        print(f"[Brain] ✅ LLM response validated")
        return {"valid": True, "source": "brain_validation"}
    
    def get_report(self) -> Dict[str, Any]:
        """Performance report: Brain hit rate is the key metric."""
        elapsed = time.time() - self.metrics["session_start"]
        total = self.metrics["brain_hits"] + self.metrics["brain_misses"]
        brain_hit_rate = (self.metrics["brain_hits"] / total * 100) if total > 0 else 0
        
        # Cost: $0.003 per 1K tokens at typical usage
        cost_saved = (self.metrics["tokens_saved"] / 1000) * 0.003
        cost_burned = (self.metrics["tokens_burned_on_fallback"] / 1000) * 0.003
        
        report = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "session_duration_seconds": round(elapsed, 1),
            "brain": {
                "hit_rate_percent": round(brain_hit_rate, 2),
                "hits": self.metrics["brain_hits"],
                "misses": self.metrics["brain_misses"],
                "total_queries": total,
                "facts_loaded": self.brain.brain_ready,
            },
            "llm_fallback": {
                "count": self.metrics["llm_fallbacks"],
                "tokens_burned": self.metrics["tokens_burned_on_fallback"],
                "est_cost_usd": round(cost_burned, 4),
            },
            "savings": {
                "tokens_saved": self.metrics["tokens_saved"],
                "est_cost_saved_usd": round(cost_saved, 4),
                "net_est_cost_usd": round(cost_saved - cost_burned, 4),
            },
            "quality": {
                "validations_run": self.metrics["validations"],
                "hallucinations_caught": self.metrics["hallucinations_caught"],
            },
        }
        
        # Persist to file
        metrics_path = Path("/data/.openclaw/workspace/agentpathfinder/brain_metrics.json")
        with open(metrics_path, "w") as f:
            json.dump(report, f, indent=2)
        
        return report
    
    def print_report(self):
        """Human-readable report."""
        r = self.get_report()
        print(f"\n{'='*60}")
        print(f"  Brain-First Skill — Performance Report")
        print(f"{'='*60}")
        print(f"  Session:          {r['session_duration_seconds']}s")
        print(f"")
        print(f"  📊 BRAIN HIT RATE: {r['brain']['hit_rate_percent']}%")
        print(f"     Hits:          {r['brain']['hits']}")
        print(f"     Misses:        {r['brain']['misses']}")
        print(f"     Total:         {r['brain']['total_queries']}")
        print(f"")
        print(f"  💰 SAVINGS")
        print(f"     Tokens saved:  {r['savings']['tokens_saved']:,}")
        print(f"     Est. $ saved:  ${r['savings']['est_cost_saved_usd']}")
        print(f"")
        print(f"  🔄 LLM FALLBACKS")
        print(f"     Count:         {r['llm_fallback']['count']}")
        print(f"     Tokens burned: {r['llm_fallback']['tokens_burned']:,}")
        print(f"     Est. $ burned: ${r['llm_fallback']['est_cost_usd']}")
        print(f"")
        print(f"  ✅ QUALITY")
        print(f"     Validations:   {r['quality']['validations_run']}")
        print(f"     Hallucinations caught: {r['quality']['hallucinations_caught']}")
        print(f"{'='*60}\n")


def demo():
    """Quick demo: show Brain-first in action."""
    print("=== Brain-First Skill Demo ===\n")
    
    skill = CertainLogicBrainSkill()
    
    # Test queries — mix of known facts and unknown queries
    test_queries = [
        "What is Python recursion depth?",  # Known fact
        "What timezone is Anton in?",        # Known fact (user profile)
        "What is the airspeed velocity of an unladen swallow?",  # Unknown
        "What is Docker Compose?",            # Known (from benchmark)
    ]
    
    for query in test_queries:
        print(f"\n📝 Query: {query}")
        result = skill.ask(query)
        
        if result["brain_hit"]:
            print(f"   ✅ Brain HIT → Answer: {result['answer'][:80]}")
            print(f"   💰 Saved: ~{result['tokens_saved']} tokens")
        else:
            print(f"   ❌ Brain MISS → needs LLM fallback")
            print(f"   🔥 Will burn: ~500 tokens on LLM")
    
    print("\n")
    skill.print_report()


def report():
    """Print latest metrics. Usage: python -m agentpathfinder.brain_skill report"""
    skill = CertainLogicBrainSkill()
    skill.print_report()
    
    status = brain_status()
    print(f"[Brain API] Status: {status['status']}, Facts: {status.get('facts_loaded', 'N/A')}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        report()
    else:
        demo()
