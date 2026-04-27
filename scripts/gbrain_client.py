#!/usr/bin/env python3
"""
GBrain Client — CertainLogic Knowledge Base Manager
Query and populate the deterministic Brain API.

USAGE:
    # Add a fact
    python3 gbrain_client.py add --category product --key "agentpathfinder_free_features" \
        --value "Unlimited tasks, local CLI, audit trails, no usage caps"
    
    # Query
    python3 gbrain_client.py query "What is AgentPathfinder?"
    
    # Import from JSON file
    python3 gbrain_client.py import_facts data/certainlogic_facts.json
    
    # Search by category
    python3 gbrain_client.py category product
"""

import argparse
import json
import requests
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


class GBrainClient:
    """Client for the CertainLogic Brain API."""
    
    def __init__(self, base_url: str = DEFAULT_BASE_URL, verbose: bool = False):
        self.base_url = base_url.rstrip("/")
        self.verbose = verbose
    
    def _log(self, msg: str):
        if self.verbose:
            print(f"[GBrain] {msg}")
    
    def health(self) -> Dict[str, Any]:
        """Check API health."""
        r = requests.get(f"{self.base_url}/health", timeout=10)
        r.raise_for_status()
        return r.json()
    
    def add_fact(self, category: str, key: str, value: str, 
                 source: str = None, fact_type: str = "string") -> Dict[str, Any]:
        """Add a single fact."""
        payload = {
            "category": category,
            "key": key,
            "value": value,
            "type": fact_type,
        }
        if source:
            payload["source"] = source
        
        self._log(f"Adding fact: {category}/{key}")
        r = requests.post(
            f"{self.base_url}/facts",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=10
        )
        r.raise_for_status()
        return r.json()
    
    def query(self, q: str, top_k: int = 5) -> Dict[str, Any]:
        """Query facts by keyword."""
        self._log(f"Querying: {q}")
        r = requests.get(
            f"{self.base_url}/query",
            params={"q": q, "top_k": top_k},
            timeout=10
        )
        r.raise_for_status()
        return r.json()
    
    def list_facts(self, category: str = None, page: int = 1, page_size: int = 50) -> Dict[str, Any]:
        """List facts by category."""
        params = {"page": page, "page_size": page_size}
        if category:
            params["category"] = category
        
        self._log(f"Listing facts: category={category}")
        r = requests.get(
            f"{self.base_url}/facts",
            params=params,
            timeout=10
        )
        r.raise_for_status()
        return r.json()
    
    def import_json(self, filepath: str, dry_run: bool = False) -> Dict[str, int]:
        """Import facts from a JSON file."""
        data = json.loads(Path(filepath).read_text())
        
        added = 0
        skipped = 0
        errors = 0
        
        for item in data:
            if dry_run:
                print(f"  [DRY] Would add: {item['category']}/{item['key']}")
                continue
            
            try:
                self.add_fact(
                    category=item["category"],
                    key=item["key"],
                    value=item["value"],
                    source=item.get("source", ""),
                    fact_type=item.get("type", "string")
                )
                added += 1
                print(f"  ✅ {item['category']}/{item['key']}")
            except requests.exceptions.HTTPError as e:
                if "already exists" in str(e):
                    skipped += 1
                    print(f"  ⏭️  {item['category']}/{item['key']} (exists)")
                else:
                    errors += 1
                    print(f"  ❌ {item['category']}/{item['key']}: {e}")
            except Exception as e:
                errors += 1
                print(f"  ❌ {item['category']}/{item['key']}: {e}")
        
        return {"added": added, "skipped": skipped, "errors": errors}
    
    def search_builder(self, spec_goal: str) -> Optional[Dict[str, Any]]:
        """Search GBrain for build patterns matching a spec goal."""
        results = self.query(spec_goal, top_k=3)
        
        if "hits" not in results or not results["hits"]:
            return None
        
        # Filter for build_spec category
        build_hits = [
            h for h in results["hits"] 
            if h.get("category") == "build_spec" or "build" in h.get("key", "")
        ]
        
        if build_hits:
            return {
                "found": True,
                "best_match": build_hits[0],
                "all_matches": build_hits[:3]
            }
        
        return None


def main():
    parser = argparse.ArgumentParser(description="GBrain Knowledge Base Manager")
    parser.add_argument("--url", default=DEFAULT_BASE_URL, help="Brain API base URL")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Health
    subparsers.add_parser("health", help="Check API health")
    
    # Add
    add_parser = subparsers.add_parser("add", help="Add a fact")
    add_parser.add_argument("--category", required=True)
    add_parser.add_argument("--key", required=True)
    add_parser.add_argument("--value", required=True)
    add_parser.add_argument("--source", default="")
    add_parser.add_argument("--type", default="string")
    
    # Query
    query_parser = subparsers.add_parser("query", help="Query facts")
    query_parser.add_argument("q", help="Query string")
    query_parser.add_argument("--top-k", type=int, default=5)
    
    # Category
    cat_parser = subparsers.add_parser("category", help="List facts by category")
    cat_parser.add_argument("name", help="Category name")
    
    # Import
    import_parser = subparsers.add_parser("import_facts", help="Import facts from JSON")
    import_parser.add_argument("filepath", help="JSON file path")
    import_parser.add_argument("--dry-run", action="store_true", help="Preview without adding")
    
    # Builder search
    build_parser = subparsers.add_parser("builder", help="Search for build patterns")
    build_parser.add_argument("goal", help="Build goal/spec description")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    client = GBrainClient(base_url=args.url, verbose=args.verbose)
    
    try:
        if args.command == "health":
            result = client.health()
            print(json.dumps(result, indent=2))
        
        elif args.command == "add":
            result = client.add_fact(
                category=args.category,
                key=args.key,
                value=args.value,
                source=args.source,
                fact_type=args.type
            )
            print(json.dumps(result, indent=2))
        
        elif args.command == "query":
            result = client.query(args.q, top_k=args.top_k)
            if "hits" in result and result["hits"]:
                print(f"\nFound {len(result['hits'])} matches:")
                for hit in result["hits"]:
                    print(f"\n  📄 {hit.get('key', 'unknown')}")
                    print(f"     Category: {hit.get('category', 'unknown')}")
                    print(f"     Value: {hit.get('value', 'N/A')[:200]}")
                    print(f"     Score: {hit.get('score', 'N/A')}")
            else:
                print("No matches found.")
        
        elif args.command == "category":
            result = client.list_facts(category=args.name)
            print(json.dumps(result, indent=2))
        
        elif args.command == "import_facts":
            print(f"Importing from: {args.filepath}")
            stats = client.import_json(args.filepath, dry_run=args.dry_run)
            print(f"\n{'=' * 40}")
            print(f"Added:   {stats['added']}")
            print(f"Skipped: {stats['skipped']}")
            print(f"Errors:  {stats['errors']}")
        
        elif args.command == "builder":
            result = client.search_builder(args.goal)
            if result and result["found"]:
                print(f"✅ Found {len(result['all_matches'])} build pattern(s)")
                print(f"\nBest match:")
                print(f"  Key:   {result['best_match']['key']}")
                print(f"  Value: {result['best_match']['value'][:300]}")
            else:
                print("❌ No build patterns found. This will be a fresh build.")
    
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to Brain API at {args.url}")
        print(f"   Is the server running? Check: curl {args.url}/health")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
