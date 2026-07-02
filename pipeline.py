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
from scrapers.base import DAYS_FUTURE, DAYS_PAST, event_time_key

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "docs", "data", "events.json")
ARCHIVE_DIR = os.path.join(os.path.dirname(__file__), "docs", "data")
LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")
# Only include events within this window (constants live in scrapers/base.py)
DATE_MIN = (date.today() - timedelta(days=DAYS_PAST)).isoformat()
DATE_MAX = (date.today() + timedelta(days=DAYS_FUTURE)).isoformat()

# Abort (exit non-zero) if more than this fraction of sources are unhealthy in
# a full run — errored, OR silently dropped from a productive yield to zero.
# This turns a silently-degraded run into a loud failure so the GitHub Action
# goes red and emails us, instead of publishing a half-empty site.
MAX_ERROR_FRACTION = 0.34

# A source counts as a "yield regression" if it produced at least this many
# events in the previous published events.json but returned zero (without
# erroring) this run. Catches broken extractions that don't raise.
MIN_PREV_FOR_REGRESSION = 5


def api_key_present() -> bool:
    """True if an Anthropic API key is available for the Claude scrapers."""
    return bool(
        os.environ.get("ANTHROPIC_API_KEY_PIONEER")
        or os.environ.get("ANTHROPIC_API_KEY")
    )


MAX_LOG_FILES = 50


def prune_old_logs():
    """Keep only the newest MAX_LOG_FILES logs so logs/ doesn't grow forever."""
    try:
        logs = sorted(
            (os.path.join(LOGS_DIR, f) for f in os.listdir(LOGS_DIR) if f.endswith(".log")),
            key=os.path.getmtime,
            reverse=True,
        )
        for old in logs[MAX_LOG_FILES:]:
            os.remove(old)
    except OSError:
        pass  # pruning is best-effort; never block a run over it


def setup_logging():
    """Configure the 'pipeline' logger to write to console and a timestamped log file."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    prune_old_logs()
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


def venues_compatible(v1: str, v2: str) -> bool:
    """Could these two venue strings plausibly be the same place?

    Guards dedup against merging same-title events at genuinely different
    venues (e.g. "Toddler Storytime" at Jones Library AND Forbes Library on
    the same day). Aggregator entries ("Various ... Venues") and empty venues
    stay compatible with everything so cross-source dupes still merge.
    """
    a, b = v1.strip().lower(), v2.strip().lower()
    if not a or not b or "various" in a or "various" in b:
        return True
    if a in b or b in a:  # "Iron Horse" vs "Iron Horse Music Hall"
        return True
    return a.split()[0] == b.split()[0]


def deduplicate(events: list) -> list:
    """
    Remove near-duplicate events: similar title + same date + compatible venue.
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
            if similarity > 0.82 and venues_compatible(
                existing.get("venue", ""), ev.get("venue", "")
            ):
                # Keep the one with more info
                if len(ev.get("description", "")) > len(existing.get("description", "")):
                    candidates[i] = ev
                break
        else:
            candidates.append(ev)
    return [ev for group in by_date.values() for ev in group]


def filter_by_date(events: list) -> list:
    return [e for e in events if DATE_MIN <= e["date"] <= DATE_MAX]


def update_archive(events: list, archive_dir: str = ARCHIVE_DIR, today: str = "") -> dict:
    """Upsert published events into per-year archives (docs/data/archive-YYYY.json).

    Append-only historical record for analysis: keyed by event id, bucketed by
    the year of the event's date. Re-scraped events refresh their details but
    keep their original first_seen; nothing is ever deleted. Returns
    {year: number_of_newly_added_events}.
    """
    today = today or date.today().isoformat()
    by_year: dict = {}
    for e in events:
        by_year.setdefault(e["date"][:4], []).append(e)

    added = {}
    for year, evs in sorted(by_year.items()):
        path = os.path.join(archive_dir, f"archive-{year}.json")
        try:
            with open(path) as f:
                archive = {a["id"]: a for a in json.load(f).get("events", [])}
        except (OSError, json.JSONDecodeError):
            archive = {}

        new = 0
        for e in evs:
            existing = archive.get(e["id"])
            if existing is None:
                new += 1
                first_seen = today
            else:
                first_seen = existing.get("first_seen", today)
            archive[e["id"]] = {**e, "first_seen": first_seen}

        records = sorted(archive.values(), key=lambda a: (a["date"], event_time_key(a)))
        with open(path, "w", encoding="utf-8") as f:
            # Compact JSON: the archive is for analysis, not reading in diffs
            json.dump(
                {"year": year, "count": len(records), "events": records},
                f, ensure_ascii=False, separators=(",", ":"),
            )
        added[year] = new
    return added


def previous_source_counts(path: str = OUTPUT_PATH) -> dict:
    """Per-source event counts from the currently-published events.json."""
    try:
        with open(path) as f:
            events = json.load(f).get("events", [])
    except (OSError, json.JSONDecodeError):
        return {}
    counts: dict = {}
    for e in events:
        src = e.get("source", "")
        counts[src] = counts.get(src, 0) + 1
    return counts


def find_regressions(results: list, prev_counts: dict) -> list:
    """Sources that yielded 0 (without erroring) but were recently productive.

    results is a list of (name, url, count, error) tuples. Returns a list of
    (name, previous_count) pairs.
    """
    return [
        (name, prev_counts[name])
        for name, _url, count, error in results
        if count == 0
        and not error
        and prev_counts.get(name, 0) >= MIN_PREV_FOR_REGRESSION
    ]


def run(scrapers, dry_run=False):
    log = logging.getLogger("pipeline")
    all_events = []
    results = []  # (name, url, count, error)

    # Snapshot the published per-source counts before we overwrite the file,
    # so we can flag sources that silently dropped to zero.
    prev_counts = previous_source_counts()

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

    # Sort by date, then chronological time (never sort times as raw strings)
    all_events.sort(key=lambda e: (e["date"], event_time_key(e)))

    # ── Summary ──────────────────────────────────────────────────────────────
    log.info("")
    log.info("══ SCRAPER SUMMARY ══════════════════════════════════════")
    errors = [(n, u, e) for n, u, c, e in results if e]
    zeros  = [(n, u) for n, u, c, e in results if c == 0 and not e]
    regressions = find_regressions(results, prev_counts)
    regressed = {name for name, _ in regressions}
    for name, url_label, count, error in results:
        if error:
            status = "ERROR"
        elif name in regressed:
            status = f"ZERO ⚠ was {prev_counts[name]}"
        elif count == 0:
            status = "ZERO"
        else:
            status = "OK"
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
    if regressions:
        log.warning("")
        log.warning("  Yield regressions (produced events last run, zero now):")
        for name, prev in regressions:
            log.warning("    %s: %d → 0", name, prev)
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
        return results, regressions

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    log.info("Wrote %d events to %s", len(all_events), OUTPUT_PATH)

    # Append-only historical record (docs/data/archive-YYYY.json) for analysis
    for year, n in update_archive(all_events).items():
        log.info("Archive %s: +%d new events", year, n)

    return results, regressions


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
        if not args.dry_run:
            # A single-source run must never overwrite events.json (it would
            # contain only that source's events) — force dry-run behavior.
            log.warning("--source runs never write output; treating as --dry-run.")
            args.dry_run = True
    else:
        scrapers = all_scrapers

    # Pre-flight: if any source needs the Anthropic key and it's missing, abort
    # loudly rather than quietly publishing only the non-Claude sources.
    needing_key = [s for s in scrapers if getattr(s, "needs_api_key", False)]
    if needing_key and not api_key_present():
        log.error(
            "ANTHROPIC_API_KEY is not set, but %d source(s) need it. Aborting so "
            "we don't publish a degraded events.json. In GitHub Actions, set the "
            "ANTHROPIC_API_KEY repository secret; locally, run `source ~/.zshrc` first.",
            len(needing_key),
        )
        sys.exit(1)

    results, regressions = run(scrapers, dry_run=args.dry_run)

    # Post-run backstop: in a full run, fail if too many sources are unhealthy
    # (errored, or silently dropped from productive to zero) so the failure
    # can't hide behind a green checkmark.
    if not args.source and results:
        errored = [r for r in results if r[3]]
        unhealthy = len(errored) + len(regressions)
        if unhealthy > len(results) * MAX_ERROR_FRACTION:
            log.error(
                "%d of %d sources unhealthy (%d errored, %d yield regressions; "
                "> %.0f%%). Failing the run so it isn't mistaken for a healthy one.",
                unhealthy, len(results), len(errored), len(regressions),
                MAX_ERROR_FRACTION * 100,
            )
            sys.exit(1)


if __name__ == "__main__":
    main()
