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
import logging
import os
import sys
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher

from scrapers import get_all_scrapers
from scrapers.claude_scraper import ClaudeHTMLScraper

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "docs", "data", "events.json")
LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")
# Only include events within this window (past 3 days → future 90 days)
DATE_MIN = (date.today() - timedelta(days=3)).isoformat()
DATE_MAX = (date.today() + timedelta(days=90)).isoformat()

# Abort (exit non-zero) if more than this fraction of sources error in a full
# run. This turns a silently-degraded run into a loud failure so the GitHub
# Action goes red and emails us, instead of publishing a half-empty site.
MAX_ERROR_FRACTION = 0.34


def api_key_present() -> bool:
    """True if an Anthropic API key is available for the Claude scrapers."""
    return bool(
        os.environ.get("ANTHROPIC_API_KEY_PIONEER")
        or os.environ.get("ANTHROPIC_API_KEY")
    )


def setup_logging():
    """Configure the 'pipeline' logger to write to console and a timestamped log file."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log_path = os.path.join(LOGS_DIR, f"pipeline_{timestamp}.log")

    logger = logging.getLogger("pipeline")
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    logger.addHandler(console)
    logger.addHandler(file_handler)
    return logger, log_path


def deduplicate(events: list) -> list:
    """
    Remove near-duplicate events using title similarity + same date.
    Keeps the event with the richer description.
    """
    by_date: dict[str, list] = {}
    for ev in events:
        candidates = by_date.setdefault(ev["date"], [])
        for i, existing in enumerate(candidates):
            similarity = SequenceMatcher(
                None,
                existing["title"].lower(),
                ev["title"].lower()
            ).ratio()
            if similarity > 0.82:
                # Keep the one with more info
                if len(ev.get("description", "")) > len(existing.get("description", "")):
                    candidates[i] = ev
                break
        else:
            candidates.append(ev)
    return [ev for group in by_date.values() for ev in group]


def filter_by_date(events: list) -> list:
    return [e for e in events if DATE_MIN <= e["date"] <= DATE_MAX]


def run(scrapers, dry_run=False):
    log = logging.getLogger("pipeline")
    all_events = []
    results = []  # (name, url, count, error)

    for scraper in scrapers:
        url_label = getattr(scraper, "url", "") or "(no url)"
        log.info("─── %s  %s", scraper.name, url_label)
        events = scraper.fetch()
        count = len(events)
        error = getattr(scraper, "last_error", None)
        results.append((scraper.name, url_label, count, error))
        all_events.extend(e.to_dict() for e in events)
        log.info("    └─ found %d events%s", count, f"  [ERROR: {error}]" if error else "")

    log.info("")
    log.info("Total raw events: %d", len(all_events))

    all_events = filter_by_date(all_events)
    log.info("After date filter (%s – %s): %d", DATE_MIN, DATE_MAX, len(all_events))

    all_events = deduplicate(all_events)
    log.info("After deduplication: %d", len(all_events))

    # Sort by date, then time
    all_events.sort(key=lambda e: (e["date"], e.get("time", "")))

    # ── Summary ──────────────────────────────────────────────────────────────
    log.info("")
    log.info("══ SCRAPER SUMMARY ══════════════════════════════════════")
    errors = [(n, u, e) for n, u, c, e in results if e]
    zeros  = [(n, u) for n, u, c, e in results if c == 0 and not e]
    for name, url_label, count, error in results:
        status = "ERROR" if error else ("ZERO" if count == 0 else "OK")
        log.info("  %-30s  %4d events  [%s]  %s", name, count, status, url_label)
    log.info("")
    log.info("  Scrapers run:    %d", len(results))
    log.info("  Errors:          %d", len(errors))
    log.info("  Returned zero:   %d (excluding errors)", len(zeros))
    log.info("  Final events:    %d", len(all_events))
    if errors:
        log.warning("")
        log.warning("  Failed scrapers:")
        for name, url_label, err in errors:
            log.warning("    %s (%s): %s", name, url_label, err)
    log.info("══════════════════════════════════════════════════════════")
    # ─────────────────────────────────────────────────────────────────────────

    payload = {
        "generated": date.today().isoformat(),
        "events": all_events,
    }

    if dry_run:
        log.info("")
        log.info("--- DRY RUN (not writing) ---")
        log.info(json.dumps(payload, indent=2)[:2000])
        return results

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    log.info("Wrote %d events to %s", len(all_events), OUTPUT_PATH)
    return results


def main():
    parser = argparse.ArgumentParser(description="Pioneer Valley Events pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Don't write output")
    parser.add_argument("--source", help="Run only this scraper (by name)")
    args = parser.parse_args()

    log, log_path = setup_logging()
    log.info("Pioneer Valley Events pipeline  [%s]", datetime.now().isoformat(timespec="seconds"))
    log.info("Log file: %s", log_path)

    all_scrapers = get_all_scrapers()

    if args.source:
        scrapers = [s for s in all_scrapers if s.name == args.source]
        if not scrapers:
            names = [s.name for s in all_scrapers]
            log.error("Unknown source '%s'. Available: %s", args.source, ", ".join(names))
            sys.exit(1)
    else:
        scrapers = all_scrapers

    # Pre-flight: if any source needs the Anthropic key and it's missing, abort
    # loudly rather than quietly publishing only the non-Claude sources.
    needs_key = any(isinstance(s, ClaudeHTMLScraper) for s in scrapers)
    if needs_key and not api_key_present():
        log.error(
            "ANTHROPIC_API_KEY is not set, but %d source(s) need it. Aborting so "
            "we don't publish a degraded events.json. In GitHub Actions, set the "
            "ANTHROPIC_API_KEY repository secret; locally, run `source ~/.zshrc` first.",
            sum(isinstance(s, ClaudeHTMLScraper) for s in scrapers),
        )
        sys.exit(1)

    results = run(scrapers, dry_run=args.dry_run)

    # Post-run backstop: in a full run, fail if too many sources errored (e.g. a
    # bad/expired key, or a widespread outage) so the failure can't hide.
    if not args.source and results:
        errored = [r for r in results if r[3]]
        if len(errored) > len(results) * MAX_ERROR_FRACTION:
            log.error(
                "%d of %d sources errored (> %.0f%%). Failing the run so it isn't "
                "mistaken for a healthy one.",
                len(errored), len(results), MAX_ERROR_FRACTION * 100,
            )
            sys.exit(1)


if __name__ == "__main__":
    main()
