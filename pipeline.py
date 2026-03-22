#!/usr/bin/env python3
"""
Pioneer Valley Events — Pipeline
Run this script to scrape all sources, deduplicate, and update docs/data/events.json.

Usage:
    python pipeline.py               # run all scrapers
    python pipeline.py --dry-run     # print results, don't write
    python pipeline.py --source umass  # run a single scraper by name
"""

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher

from scrapers import ALL_SCRAPERS

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "docs", "data", "events.json")
# Only include events within this window (past 3 days → future 90 days)
DATE_MIN = (date.today() - timedelta(days=3)).isoformat()
DATE_MAX = (date.today() + timedelta(days=90)).isoformat()


def deduplicate(events: list) -> list:
    """
    Remove near-duplicate events using title similarity + same date.
    Keeps the event with the richer description.
    """
    unique = []
    for ev in events:
        merged = False
        for existing in unique:
            if existing["date"] != ev["date"]:
                continue
            similarity = SequenceMatcher(
                None,
                existing["title"].lower(),
                ev["title"].lower()
            ).ratio()
            if similarity > 0.82:
                # Keep the one with more info
                if len(ev.get("description", "")) > len(existing.get("description", "")):
                    unique[unique.index(existing)] = ev
                merged = True
                break
        if not merged:
            unique.append(ev)
    return unique


def filter_by_date(events: list) -> list:
    return [e for e in events if DATE_MIN <= e["date"] <= DATE_MAX]


def run(scrapers, dry_run=False):
    all_events = []

    for ScraperClass in scrapers:
        scraper = ScraperClass()
        print(f"\nRunning scraper: {scraper.name}")
        events = scraper.fetch()
        all_events.extend(e.to_dict() for e in events)

    print(f"\nTotal raw events: {len(all_events)}")

    all_events = filter_by_date(all_events)
    print(f"After date filter ({DATE_MIN} – {DATE_MAX}): {len(all_events)}")

    all_events = deduplicate(all_events)
    print(f"After deduplication: {len(all_events)}")

    # Sort by date, then time
    all_events.sort(key=lambda e: (e["date"], e.get("time", "")))

    payload = {
        "generated": date.today().isoformat(),
        "events": all_events,
    }

    if dry_run:
        print("\n--- DRY RUN (not writing) ---")
        print(json.dumps(payload, indent=2)[:2000], "...")
        return

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {len(all_events)} events to {OUTPUT_PATH}")


def main():
    parser = argparse.ArgumentParser(description="Pioneer Valley Events pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Don't write output")
    parser.add_argument("--source", help="Run only this scraper (by name)")
    args = parser.parse_args()

    if args.source:
        scrapers = [s for s in ALL_SCRAPERS if s().name == args.source]
        if not scrapers:
            names = [s().name for s in ALL_SCRAPERS]
            print(f"Unknown source '{args.source}'. Available: {', '.join(names)}")
            sys.exit(1)
    else:
        scrapers = ALL_SCRAPERS

    run(scrapers, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
