"""Shared base for schools on the Localist events platform (Concept3D).

Localist exposes a clean public JSON API at /api/2/events — always prefer it
over scraping the HTML calendar. UMass and Mount Holyoke subclass this.
"""

import logging
from datetime import datetime

import requests

from .base import BaseScraper, Event

log = logging.getLogger("pipeline")

CATEGORY_MAP = {
    "music": "music", "concert": "music",
    "performance": "arts", "theater": "arts", "theatre": "arts", "dance": "arts",
    "art": "arts", "exhibition": "arts", "gallery": "arts",
    "film": "film", "movie": "film", "cinema": "film",
    "lecture": "academia", "talk": "academia", "seminar": "academia",
    "symposium": "academia", "workshop": "academia", "colloquium": "academia",
    "comedy": "comedy",
    "family": "family", "children": "family", "kids": "family",
    "sport": "outdoor", "recreation": "outdoor", "athletic": "outdoor",
    "softball": "outdoor", "lacrosse": "outdoor", "baseball": "outdoor",
    "basketball": "outdoor", "soccer": "outdoor", "football": "outdoor",
    "volleyball": "outdoor", "tennis": "outdoor", "swimming": "outdoor",
    "track": "outdoor", "cross country": "outdoor", "rowing": "outdoor",
    "field hockey": "outdoor", "wrestling": "outdoor", "golf": "outdoor",
    "food": "food",
    "festival": "festival", "fair": "festival",
}


def guess_category(title: str, default: str = "academia") -> str:
    tl = title.lower()
    for keyword, cat in CATEGORY_MAP.items():
        if keyword in tl:
            return cat
    return default


def parse_iso(iso: str):
    """Return (date_str 'YYYY-MM-DD', time_str 'H:MM AM/PM') from ISO datetime."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d"), dt.strftime("%-I:%M %p")
    except Exception:
        return iso[:10] if len(iso) >= 10 else "", ""


class LocalistScraper(BaseScraper):
    """Subclasses set `api_url` plus the class attrs below."""

    api_url: str = ""          # e.g. "https://events.example.edu/api/2/events?days=90&pp=100"
    default_venue: str = ""
    default_address: str = ""
    default_category: str = "academia"

    def _fetch(self) -> list[Event]:
        headers = {"User-Agent": "PioneerValleyEvents/1.0 (community aggregator)"}
        resp = requests.get(self.api_url, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        events = []
        seen = set()

        for item in data.get("events", []):
            ev = item.get("event", {})
            title = self.clean(ev.get("title", ""))
            if not title:
                continue

            for inst_wrap in ev.get("event_instances", []):
                inst = inst_wrap.get("event_instance", {})
                start = inst.get("start", "")
                if not start:
                    continue
                date_str, time_str = parse_iso(start)
                if not date_str:
                    continue
                if inst.get("all_day"):
                    time_str = ""

                key = f"{title}|{date_str}"
                if key in seen:
                    continue
                seen.add(key)

                end = inst.get("end") or ""
                end_time_str = parse_iso(end)[1] if end else ""

                events.append(Event(
                    title=title,
                    date=date_str,
                    time=time_str,
                    end_time=end_time_str,
                    venue=self.clean(ev.get("location_name", "")) or self.default_venue,
                    address=self.clean(ev.get("address", "")) or self.default_address,
                    town=self.town,
                    description=self.clean(ev.get("description_text", ""))[:500],
                    url=ev.get("localist_url", "") or ev.get("url") or "",
                    image_url=ev.get("photo_url"),
                    category=guess_category(title, self.default_category),
                    source=self.name,
                ))

        log.debug("[%s] Found %d events", self.name, len(events))
        return events
