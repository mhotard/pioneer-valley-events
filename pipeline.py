#!/usr/bin/env python3
"""
Pioneer Valley Events — Pipeline
Run this script to scrape all sources, deduplicate, and update docs/data/events.json.

Usage:
    python pipeline.py               # run all scrapers
    python pipeline.py --dry-run     # print results, don't write
    python pipeline.py --source umass  # run a single scraper by name
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher

from json_storage import read_json, write_json_atomic
from scrapers import get_all_scrapers
from scrapers.base import DAYS_FUTURE, DAYS_PAST, event_time_key

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "docs", "data", "events.json")
ARCHIVE_DIR = os.path.join(os.path.dirname(__file__), "docs", "data")
LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")

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


def filter_by_date(events: list, *, run_date: date | None = None) -> list:
    """Return events within the publication window for one pipeline date."""
    run_date = run_date or date.today()
    date_min = (run_date - timedelta(days=DAYS_PAST)).isoformat()
    date_max = (run_date + timedelta(days=DAYS_FUTURE)).isoformat()
    return [e for e in events if date_min <= e["date"] <= date_max]


def prepare_payload(events: list, *, run_date: date) -> dict:
    """Filter, deduplicate, and chronologically sort event dictionaries."""
    prepared = filter_by_date([event.copy() for event in events], run_date=run_date)
    prepared = deduplicate(prepared)
    prepared.sort(key=lambda event: (event["date"], event_time_key(event)))
    return {"generated": run_date.isoformat(), "events": prepared}


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
        stored = read_json(path, default_factory=lambda: {"events": []})
        stored_events = _validated_archive_events(stored, path)
        archive = {record["id"]: record for record in stored_events}

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
        # Compact JSON: the archive is for analysis, not reading in diffs
        write_json_atomic(
            path,
            {"year": year, "count": len(records), "events": records},
            separators=(",", ":"),
        )
        added[year] = new
    return added


def _validated_archive_events(value: object, path: str) -> list[dict]:
    """Return archive rows after checking the shape needed for safe merging."""
    if not isinstance(value, dict) or not isinstance(value.get("events"), list):
        raise ValueError(f"Invalid archive structure in {path}: expected an events list")

    seen_ids = set()
    for index, record in enumerate(value["events"]):
        if not isinstance(record, dict):
            raise ValueError(f"Invalid archive row {index} in {path}: expected an object")
        event_id = record.get("id")
        event_date = record.get("date")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError(f"Invalid archive row {index} in {path}: unusable event id")
        if not isinstance(event_date, str) or not event_date.strip():
            raise ValueError(f"Invalid archive row {index} in {path}: unusable event date")
        if event_id in seen_ids:
            raise ValueError(f"Duplicate archive event id {event_id!r} in {path}")
        seen_ids.add(event_id)
    return value["events"]


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


def is_unhealthy(results: list, regressions: list) -> bool:
    """Whether a full run exceeds the established unhealthy-source threshold."""
    errored = {name for name, _url, _count, error in results if error}
    regressed = {name for name, _previous_count in regressions}
    return len(errored | regressed) > len(results) * MAX_ERROR_FRACTION


@dataclass
class PipelineResult:
    """Collected pipeline data and the source-health facts derived from it."""

    payload: dict
    results: list
    regressions: list


def run(scrapers, *, previous_counts: dict, run_date: date) -> PipelineResult:
    """Collect and transform events without reading or writing publication files."""
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

    date_min = (run_date - timedelta(days=DAYS_PAST)).isoformat()
    date_max = (run_date + timedelta(days=DAYS_FUTURE)).isoformat()
    date_filtered_count = len(filter_by_date(all_events, run_date=run_date))
    payload = prepare_payload(all_events, run_date=run_date)
    log.info("After date filter (%s – %s): %d", date_min, date_max, date_filtered_count)
    log.info("After deduplication: %d", len(payload["events"]))

    # ── Summary ──────────────────────────────────────────────────────────────
    log.info("")
    log.info("══ SCRAPER SUMMARY ══════════════════════════════════════")
    errors = [(n, u, e) for n, u, c, e in results if e]
    zeros  = [(n, u) for n, u, c, e in results if c == 0 and not e]
    regressions = find_regressions(results, previous_counts)
    regressed = {name for name, _ in regressions}
    for name, url_label, count, error in results:
        if error:
            status = "ERROR"
        elif name in regressed:
            status = f"ZERO ⚠ was {previous_counts[name]}"
        elif count == 0:
            status = "ZERO"
        else:
            status = "OK"
        log.info("  %-30s  %4d events  [%s]  %s", name, count, status, url_label)
    log.info("")
    log.info("  Scrapers run:    %d", len(results))
    log.info("  Errors:          %d", len(errors))
    log.info("  Returned zero:   %d (excluding errors)", len(zeros))
    log.info("  Final events:    %d", len(payload["events"]))
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

    return PipelineResult(payload=payload, results=results, regressions=regressions)


def publish_payload(payload: dict, *, output_path: str, archive_dir: str) -> None:
    """Write the current payload, then upsert its final events into archives."""
    log = logging.getLogger("pipeline")
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    os.makedirs(archive_dir, exist_ok=True)
    write_json_atomic(output_path, payload, indent=2)

    log.info("Wrote %d events to %s", len(payload["events"]), output_path)

    # Append-only historical record (docs/data/archive-YYYY.json) for analysis
    for year, n in update_archive(
        payload["events"], archive_dir=archive_dir, today=payload["generated"]
    ).items():
        log.info("Archive %s: +%d new events", year, n)


def main(argv=None, *, output_path=None, archive_dir=None, run_date=None) -> int:
    """Orchestrate source selection, health assessment, preview, and publication."""
    parser = argparse.ArgumentParser(description="Pioneer Valley Events pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Don't write output")
    parser.add_argument("--source", help="Run only this scraper (by name)")
    args = parser.parse_args(argv)

    output_path = output_path or OUTPUT_PATH
    archive_dir = archive_dir or ARCHIVE_DIR
    run_date = run_date or date.today()

    log, log_path = setup_logging()
    log.info("Pioneer Valley Events pipeline  [%s]", datetime.now().isoformat(timespec="seconds"))
    log.info("Log file: %s", log_path)

    all_scrapers = get_all_scrapers()

    if args.source:
        scrapers = [s for s in all_scrapers if s.name == args.source]
        if not scrapers:
            names = [s.name for s in all_scrapers]
            log.error("Unknown source '%s'. Available: %s", args.source, ", ".join(names))
            return 1
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
        return 1

    previous_counts = previous_source_counts(output_path)
    result = run(scrapers, previous_counts=previous_counts, run_date=run_date)

    # Reject unhealthy full runs before either publication destination is touched.
    if not args.source and is_unhealthy(result.results, result.regressions):
        errored = [item for item in result.results if item[3]]
        unhealthy = len(errored) + len(result.regressions)
        log.error(
            "%d of %d sources unhealthy (%d errored, %d yield regressions; "
            "> %.0f%%). Failing the run so it isn't mistaken for a healthy one.",
            unhealthy,
            len(result.results),
            len(errored),
            len(result.regressions),
            MAX_ERROR_FRACTION * 100,
        )
        return 1

    if args.dry_run:
        log.info("")
        log.info("--- DRY RUN (not writing) ---")
        log.info(json.dumps(result.payload, indent=2)[:2000])
        return 0

    publish_payload(result.payload, output_path=output_path, archive_dir=archive_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
