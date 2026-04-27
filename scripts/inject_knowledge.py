#!/usr/bin/env python3
"""
Knowledge Injector — Populate GBrain with CertainLogic business data.

This script reads from data/certainlogic_facts.json and injects into GBrain.
Future versions will also inject from build specs, customer interactions, etc.

Requires:
  - Brain API running at localhost:8000 (or set BRAIN_API env var)
  - data/certainlogic_facts.json present (auto-populated if missing from template)

USAGE:
    python3 inject_knowledge.py                    # Import all facts
    python3 inject_knowledge.py --build-specs      # Import current build specs
    python3 inject_knowledge.py --customer name "ACME Corp" --data "Wants SSO..."
    python3 inject_knowledge.py --show             # Show all GBrain facts
"""

import argparse
import json
import os
import requests
from pathlib import Path
from datetime import datetime

BRAIN_API = os.getenv("BRAIN_API", "http://127.0.0.1:8000")
FACTS_FILE = Path(__file__).parent.parent / "data" / "certainlogic_facts.json"


def add_fact(category: str, key: str, value: str, source: str = "auto-inject"):
    """Add a single fact to GBrain."""
    try:
        r = requests.post(
            f"{BRAIN_API}/facts",
            headers={"Content-Type": "application/json"},
            json={
                "category": category,
                "key": key,
                "value": value,
                "type": "string",
                "source": source,
            },
            timeout=10,
        )
        if r.status_code in (200, 201):
            return True, f"+ {category}/{key}"
        elif r.status_code == 409 or "already exists" in r.text:
            return True, f"= {category}/{key} (exists)"
        else:
            return False, f"! {category}/{key}: HTTP {r.status_code}"
    except Exception as e:
        return False, f"! {category}/{key}: {e}"


def import_facts(filepath: Path):
    """Import facts from JSON file."""
    if not filepath.exists():
        print(f"Facts file not found: {filepath}")
        print("Creating from template...")
        create_template(filepath)
        return
    
    data = json.loads(filepath.read_text())
    added = skipped = errors = 0
    
    for item in data:
        ok, msg = add_fact(
            item["category"],
            item["key"],
            item["value"],
            item.get("source", "data-import"),
        )
        print(f"  {msg}")
        if "(exists)" in msg:
            skipped += 1
        elif ok:
            added += 1
        else:
            errors += 1
    
    print(f"\nDone: {added} added, {skipped} skipped, {errors} errors")
    print(f"Brain API: {BRAIN_API}")


def import_build_specs():
    """Find and import all build specs from .build_data."""
    build_dir = Path(".build_data")
    if not build_dir.exists():
        print("No .build_data directory found.")
        return
    
    specs = list(build_dir.glob("spec_*.md"))
    if not specs:
        print("No build specs found.")
        return
    
    for spec in specs:
        name = spec.stem.replace("spec_", "")
        content = spec.read_text()
        ok, msg = add_fact("build_spec", f"{name}_spec", content, source="auto-build")
        print(f"  {msg}")


def add_customer_interaction(name: str, data: str):
    """Log a customer interaction."""
    key = f"{name.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}"
    ok, msg = add_fact("customer", key, data, source="manual-entry")
    print(f"  {msg}")


def show_facts():
    """Show all facts from GBrain."""
    try:
        r = requests.get(f"{BRAIN_API}/facts?page_size=100", timeout=10)
        if r.status_code == 200:
            data = r.json()
            print(f"\nTotal facts: {data.get('count', 'unknown')}")
            by_cat = {}
            for key, fact in data.get("facts", {}).items():
                cat = fact.get("source", "unknown").split("/")[0]
                by_cat.setdefault(cat, []).append(key)
            for cat, keys in sorted(by_cat.items()):
                print(f"\n  [{cat}] ({len(keys)} facts)")
                for k in keys[:5]:
                    print(f"    - {k}")
                if len(keys) > 5:
                    print(f"    ... and {len(keys) - 5} more")
        else:
            print(f"Error: HTTP {r.status_code}")
    except Exception as e:
        print(f"Error: {e}")


def create_template(filepath: Path):
    """Create a template facts file."""
    template = [
        {
            "category": "product",
            "key": "product_name",
            "value": "Your product name here",
            "type": "string",
            "source": "template",
        }
    ]
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(json.dumps(template, indent=2))
    print(f"Template created: {filepath}")
    print("Edit it, then run: python3 inject_knowledge.py")


def main():
    parser = argparse.ArgumentParser(description="Knowledge Injector for GBrain")
    parser.add_argument("--build-specs", action="store_true", help="Import build specs")
    parser.add_argument("--customer", nargs=2, metavar=("NAME", "DATA"), help="Log customer interaction")
    parser.add_argument("--show", action="store_true", help="Show all facts")
    parser.add_argument("--facts-file", default=str(FACTS_FILE), help="Path to facts JSON")
    args = parser.parse_args()
    
    if args.show:
        show_facts()
    elif args.build_specs:
        import_build_specs()
    elif args.customer:
        add_customer_interaction(args.customer[0], args.customer[1])
    else:
        # Default: import from facts file
        import_facts(Path(args.facts_file))


if __name__ == "__main__":
    main()
