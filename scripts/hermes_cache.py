"""Hermes query cache — intercept tool calls, deduplicate, track hit rates.

PERSISTENT CACHE: Cache survives across sessions. On init, loads previous
cache from disk. On every write, flushes to disk. This gives accurate hit
rates across long-running agent sessions.
"""
import json
import time
import hashlib
from pathlib import Path
from functools import wraps
from typing import Any, Dict, Optional


class QueryCache:
    """Persistent LRU cache for tool call deduplication with hit rate tracking."""
    
    def __init__(
        self,
        max_size: int = 1000,
        metrics_path: Optional[Path] = None,
        cache_path: Optional[Path] = None,
    ):
        self._max_size = max_size
        self._metrics_path = metrics_path or Path(
            "/data/.openclaw/workspace/agentpathfinder/cache_metrics.json"
        )
        self._cache_path = cache_path or Path(
            "/data/.openclaw/workspace/agentpathfinder/cache_data.json"
        )
        
        # Load persisted cache
        self._cache: Dict[str, Any] = {}
        self._access_order: list = []
        self._hits = 0
        self._misses = 0
        self._load_cache()
    
    def _load_cache(self):
        """Load cache + metrics from disk if present."""
        if self._cache_path.exists():
            try:
                with open(self._cache_path) as f:
                    data = json.load(f)
                self._cache = data.get("cache", {})
                self._access_order = data.get("access_order", [])
                # Trim to max_size in case config changed
                while len(self._cache) > self._max_size:
                    lru = self._access_order.pop(0)
                    self._cache.pop(lru, None)
            except Exception:
                self._cache = {}
                self._access_order = []
        
        # Load metrics separately so they survive cache clears
        if self._metrics_path.exists():
            try:
                with open(self._metrics_path) as f:
                    metrics = json.load(f)
                self._hits = metrics.get("hits", 0)
                self._misses = metrics.get("misses", 0)
            except Exception:
                self._hits = 0
                self._misses = 0
    
    def _save_cache(self):
        """Persist cache to disk."""
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._cache_path, "w") as f:
            json.dump(
                {"cache": self._cache, "access_order": self._access_order},
                f,
                indent=2,
                default=str,
            )
    
    def _save_metrics(self):
        """Persist metrics to disk."""
        self._metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics = self.get_metrics()
        with open(self._metrics_path, "w") as f:
            json.dump(metrics, f, indent=2)
    
    def _make_key(self, tool_name: str, **kwargs) -> str:
        """Canonical cache key from tool name + arguments."""
        canonical = json.dumps(
            {"tool": tool_name, "args": kwargs},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:32]
    
    def get(self, tool_name: str, **kwargs) -> Optional[Any]:
        """Check cache. Returns cached result or None."""
        key = self._make_key(tool_name, **kwargs)
        if key in self._cache:
            self._hits += 1
            # Move to end (most recently used)
            self._access_order.remove(key)
            self._access_order.append(key)
            self._save_metrics()
            return self._cache[key]
        self._misses += 1
        self._save_metrics()
        return None
    
    def set(self, result: Any, tool_name: str, **kwargs):
        """Store result in cache and flush to disk."""
        key = self._make_key(tool_name, **kwargs)
        
        # Evict if at capacity
        if len(self._cache) >= self._max_size and key not in self._cache:
            lru_key = self._access_order.pop(0)
            del self._cache[lru_key]
        
        # Remove old position if updating
        if key in self._access_order:
            self._access_order.remove(key)
        
        self._cache[key] = result
        self._access_order.append(key)
        self._save_cache()
    
    def get_metrics(self) -> Dict[str, Any]:
        """Current cache performance metrics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0
        return {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "cache_size": len(self._cache),
            "max_size": self._max_size,
            "total_queries": total,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_percent": round(hit_rate, 2),
            "miss_rate_percent": round(100 - hit_rate, 2),
        }
    
    def save_metrics(self):
        """Persist metrics to disk."""
        metrics = self.get_metrics()
        self._save_metrics()
        return metrics
    
    def cached_call(self, tool_name: str, fn, **kwargs):
        """Execute fn with caching. Returns (result, was_cached)."""
        cached = self.get(tool_name, **kwargs)
        if cached is not None:
            return cached, True
        
        result = fn(**kwargs)
        self.set(result, tool_name, **kwargs)
        return result, False
    
    def clear_cache(self):
        """Clear all cached entries (preserves metrics)."""
        self._cache = {}
        self._access_order = []
        self._save_cache()
    
    def clear_metrics(self):
        """Reset hit/miss counters (preserves cached data)."""
        self._hits = 0
        self._misses = 0
        self._save_metrics()


# Global cache instance
_global_cache: Optional[QueryCache] = None

def get_cache() -> QueryCache:
    """Get or create the global persistent query cache."""
    global _global_cache
    if _global_cache is None:
        _global_cache = QueryCache()
    return _global_cache


def cached_tool(tool_name: str):
    """Decorator to cache a tool function's results."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(**kwargs):
            cache = get_cache()
            result, was_cached = cache.cached_call(tool_name, fn, **kwargs)
            return result
        return wrapper
    return decorator


def report_metrics() -> Dict[str, Any]:
    """Get and save current cache metrics."""
    cache = get_cache()
    metrics = cache.save_metrics()
    print(
        f"[CacheMetrics] Persistent cache: {metrics['cache_size']} entries, "
        f"hit rate: {metrics['hit_rate_percent']}% "
        f"({metrics['hits']}/{metrics['total_queries']})"
    )
    return metrics


if __name__ == "__main__":
    # Quick test — demonstrates persistence across runs
    cache = QueryCache(max_size=3)
    
    def mock_read(path):
        return f"content of {path}"
    
    # Miss (new)
    r1, c1 = cache.cached_call("read_file", mock_read, path="/x.py")
    assert c1 == False
    assert r1 == "content of /x.py"
    
    # Hit (from memory)
    r2, c2 = cache.cached_call("read_file", mock_read, path="/x.py")
    assert c2 == True
    assert r2 == "content of /x.py"
    
    metrics = cache.get_metrics()
    print(f"✅ Cache test passed — {metrics['cache_size']} entries, {metrics['hit_rate_percent']}% hit rate")
    print(f"   Data persisted to: {cache._cache_path}")
    print(f"   Metrics persisted to: {cache._metrics_path}")
