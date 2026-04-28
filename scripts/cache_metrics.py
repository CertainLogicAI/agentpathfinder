#!/usr/bin/env python3
"""Query cache metrics tracker — honest coding-only measurement.

Run this after every build/test session to log actual cache performance.
Only coding queries count toward hit rate. Marketing/sales/weather bypass.

Usage:
    python3 scripts/cache_metrics.py --report
    python3 scripts/cache_metrics.py --reset
    python3 scripts/cache_metrics.py --log-query "python test" --hit
"""
import argparse
import json
import os
from pathlib import Path
from datetime import datetime

METRICS_FILE = Path.home() / ".agentpathfinder" / "cache_metrics.json"

# Coding keywords — queries containing these count toward hit rate
CODING_KEYWORDS = [
    "python", "build", "test", "git", "docker", "pytest", "compile",
    "function", "class", "module", "import", "script", "code",
    "debug", "error", "exception", "lint", "type hint", "refactor"
]

NON_CODING_KEYWORDS = [
    "marketing", "sales", "weather", "blog", "x thread", "announcement",
    "marketplace", "influencer", "testimonial", "pricing", "stripe"
]


def load_metrics():
    if METRICS_FILE.exists():
        return json.loads(METRICS_FILE.read_text())
    return {
        "coding_hits": 0,
        "coding_misses": 0,
        "non_coding_bypassed": 0,
        "total_queries": 0,
        "daily_log": {},
        "first_run": datetime.now().isoformat()
    }


def save_metrics(data):
    METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    METRICS_FILE.write_text(json.dumps(data, indent=2))


def is_coding_query(query: str) -> bool:
    query_lower = query.lower()
    # Non-coding takes priority
    if any(kw in query_lower for kw in NON_CODING_KEYWORDS):
        return False
    return any(kw in query_lower for kw in CODING_KEYWORDS)


def log_query(query: str, hit: bool):
    data = load_metrics()
    data["total_queries"] += 1
    today = datetime.now().strftime("%Y-%m-%d")
    
    if today not in data["daily_log"]:
        data["daily_log"][today] = {"hits": 0, "misses": 0, "bypassed": 0}
    
    if is_coding_query(query):
        if hit:
            data["coding_hits"] += 1
            data["daily_log"][today]["hits"] += 1
        else:
            data["coding_misses"] += 1
            data["daily_log"][today]["misses"] += 1
    else:
        data["non_coding_bypassed"] += 1
        data["daily_log"][today]["bypassed"] += 1
    
    save_metrics(data)
    action = "HIT" if hit else "MISS" if is_coding_query(query) else "BYPASS"
    print(f"[{action}] ({'coding' if is_coding_query(query) else 'non-coding'}) {query[:60]}")


def report():
    data = load_metrics()
    total_coding = data["coding_hits"] + data["coding_misses"]
    hit_rate = (data["coding_hits"] / total_coding * 100) if total_coding > 0 else 0
    
    print("=" * 50)
    print("  QUERY CACHE METRICS")
    print("=" * 50)
    print(f"  Coding hits:     {data['coding_hits']}")
    print(f"  Coding misses:   {data['coding_misses']}")
    print(f"  Coding hit rate: {hit_rate:.1f}%")
    print(f"  Non-coding bypassed: {data['non_coding_bypassed']}")
    print(f"  Total queries:   {data['total_queries']}")
    print()
    print("  Daily breakdown:")
    for day, stats in sorted(data.get("daily_log", {}).items())[-7:]:
        day_total = stats["hits"] + stats["misses"]
        day_rate = (stats["hits"] / day_total * 100) if day_total > 0 else 0
        print(f"    {day}: {stats['hits']}H/{stats['misses']}M/{stats['bypassed']}B → {day_rate:.0f}% hit rate")
    print()
    print(f"  First run: {data.get('first_run', 'unknown')}")
    print("=" * 50)


def reset():
    if METRICS_FILE.exists():
        METRICS_FILE.unlink()
    print("✅ Metrics reset")


def main():
    parser = argparse.ArgumentParser(description="Cache metrics tracker")
    parser.add_argument("--report", action="store_true", help="Show current metrics")
    parser.add_argument("--reset", action="store_true", help="Reset all metrics")
    parser.add_argument("--log-query", type=str, help="Log a query")
    parser.add_argument("--hit", action="store_true", help="Mark query as cache hit")
    args = parser.parse_args()
    
    if args.reset:
        reset()
    elif args.log_query:
        log_query(args.log_query, args.hit)
    else:
        report()


if __name__ == "__main__":
    main()
