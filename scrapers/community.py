"""Community events scraper — reads manually-added events from community_events.json."""

import calendar
import json
import logging
import os
import re
from datetime import date, timedelta

from .base import DAYS_FUTURE, DAYS_PAST, BaseScraper, Event

log = logging.getLogger("pipeline")

WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "last": -1}

# Patterns
RE_EVERY = re.compile(
    r"^every\s+(" + "|".join(WEEKDAYS) + r")$", re.IGNORECASE
)
RE_NTH = re.compile(
    r"^(" + "|".join(ORDINALS) + r")\s+(" + "|".join(WEEKDAYS) + r")\s+of\s+each\s+month$",
    re.IGNORECASE,
)


def expand_recurrence(pattern, range_start, range_end, event_start=None, event_end=None):
    """Expand a recurrence pattern into concrete dates within the given window.

    Returns a list of datetime.date objects.
    """
    # Effective window is the intersection of the pipeline range and event bounds
    start = max(range_start, event_start) if event_start else range_start
    end = min(range_end, event_end) if event_end else range_end
    if start > end:
        return []

    pattern = pattern.strip()

    # "every <weekday>"
    m = RE_EVERY.match(pattern)
    if m:
        target = WEEKDAYS[m.group(1).lower()]
        dates = []
        d = start
        # Advance to first occurrence of target weekday
        while d.weekday() != target:
            d += timedelta(days=1)
        while d <= end:
            dates.append(d)
            d += timedelta(days=7)
        return dates

    # "<ordinal> <weekday> of each month"
    m = RE_NTH.match(pattern)
    if m:
        ordinal = ORDINALS[m.group(1).lower()]
        target = WEEKDAYS[m.group(2).lower()]
        dates = []
        # Iterate over each month in the window
        year, month = start.year, start.month
        while (year, month) <= (end.year, end.month):
            cal = calendar.monthcalendar(year, month)
            # Collect all occurrences of target weekday in this month
            occurrences = [
                week[target] for week in cal if week[target] != 0
            ]
            if ordinal == -1:
                day = occurrences[-1]
            elif 1 <= ordinal <= len(occurrences):
                day = occurrences[ordinal - 1]
            else:
                day = None

            if day:
                d = date(year, month, day)
                if start <= d <= end:
                    dates.append(d)

            # Next month
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1
        return dates

    log.warning("Unrecognized recurrence pattern: %r", pattern)
    return []


class CommunityEventsScraper(BaseScraper):
    """Reads manually-curated events from community_events.json."""

    name = "community"

    def __init__(self, path=None):
        self.path = path or os.path.join(
            os.path.dirname(__file__), "..", "community_events.json"
        )

    def _fetch(self) -> list[Event]:
        if not os.path.exists(self.path):
            log.debug("No community_events.json found at %s — skipping", self.path)
            return []

        with open(self.path) as f:
            data = json.load(f)

        entries = data.get("events", [])
        events = []

        # Use the same date window as the pipeline
        today = date.today()
        range_start = today - timedelta(days=DAYS_PAST)
        range_end = today + timedelta(days=DAYS_FUTURE)

        for i, entry in enumerate(entries):
            title = entry.get("title", "").strip()
            if not title:
                log.warning("community_events.json entry %d has no title — skipping", i)
                continue

            base_kwargs = {
                "title": title,
                "venue": entry.get("venue", ""),
                "town": entry.get("town", ""),
                "source": "community",
                "category": entry.get("category", "community"),
                "time": entry.get("time", ""),
                "end_time": entry.get("end_time", ""),
                "address": entry.get("address", ""),
                "description": entry.get("description", ""),
                "url": entry.get("url", ""),
                "image_url": entry.get("image_url"),
            }

            if "date" in entry:
                # One-off event
                base_kwargs["date"] = entry["date"]
                events.append(Event(**base_kwargs))
            elif "recurrence" in entry:
                # Recurring event — expand into concrete dates
                event_start = (
                    date.fromisoformat(entry["start_date"])
                    if entry.get("start_date") else None
                )
                event_end = (
                    date.fromisoformat(entry["end_date"])
                    if entry.get("end_date") else None
                )
                dates = expand_recurrence(
                    entry["recurrence"], range_start, range_end,
                    event_start, event_end,
                )
                for d in dates:
                    base_kwargs["date"] = d.isoformat()
                    events.append(Event(**base_kwargs))
            else:
                log.warning(
                    "community_events.json entry %d (%s) has no date or recurrence — skipping",
                    i, title,
                )

        log.info("[community] Loaded %d events from community_events.json", len(events))
        return events
