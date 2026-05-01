#!/usr/bin/env python3
"""Populate GBrain with CertainLogic facts."""
import json
import requests

BASE_URL = "http://127.0.0.1:8000"
facts = json.loads(open("data/certainlogic_facts.json").read())

added = 0
skipped = 0
errors = 0

for item in facts:
    try:
        r = requests.post(
            f"{BASE_URL}/facts",
            headers={"Content-Type": "application/json"},
            json=item,
            timeout=10
        )
        if r.status_code == 200 or r.status_code == 201:
            added += 1
            print(f"  + {item['category']}/{item['key']}")
        elif "already exists" in r.text:
            skipped += 1
            print(f"  = {item['category']}/{item['key']} (exists)")
        else:
            errors += 1
            print(f"  ! {item['category']}/{item['key']}: HTTP {r.status_code}")
    except Exception as e:
        errors += 1
        print(f"  ! {item['category']}/{item['key']}: {e}")

print(f"\nDone: {added} added, {skipped} skipped, {errors} errors")
