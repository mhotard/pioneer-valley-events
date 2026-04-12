"""Scraper for Jones Library events — uses their RSS feed."""

import logging
import xml.etree.ElementTree as ET

import requests

from .base import BaseScraper, Event

log = logging.getLogger("pipeline")

RSS_URL = "https://www.joneslibrary.org/RSSFeed.aspx?ModID=58&CID=All-calendar.xml"
NS = {"cal": "https://www.joneslibrary.org/Calendar.aspx"}

CATEGORY_MAP = {
    "book": "community", "reading": "community", "story": "family",
    "teen": "community", "kids": "family", "children": "family",
    "craft": "arts", "art": "arts", "knit": "arts", "crochet": "arts",
    "music": "music", "concert": "music",
    "film": "film", "movie": "film",
    "lecture": "academia", "talk": "academia", "workshop": "academia",
    "tutor": "academia", "homework": "academia",
    "food": "food", "garden": "outdoor",
    "festival": "festival", "fair": "festival",
}


def guess_category(title: str) -> str:
    tl = title.lower()
    for keyword, cat in CATEGORY_MAP.items():
        if keyword in tl:
            return cat
    return "community"  # Library events default to community


def parse_time_range(time_str: str):
    """Parse '02:00 PM - 03:00 PM' into (start, end) normalized times."""
    parts = [p.strip() for p in time_str.split("-")]
    start = BaseScraper.normalize_time(parts[0]) if parts else ""
    end = BaseScraper.normalize_time(parts[1]) if len(parts) > 1 else ""
    return start, end


def clean_location(raw: str) -> tuple[str, str]:
    """Extract venue and address from location string. Returns (venue, address)."""
    # Location is usually just an address like "101 University Drive - Suite B1, Amherst, MA 01002"
    # or sometimes just "Amherst, MA 01002"
    raw = raw.strip()
    if not raw:
        return "Jones Library", ""
    # If it looks like a street address, use Jones Library as venue
    return "Jones Library", raw


class JonesLibraryScraper(BaseScraper):
    name = "jones-library"
    url = RSS_URL
    town = "Amherst"

    def _fetch(self) -> list[Event]:
        headers = {"User-Agent": "PioneerValleyEvents/1.0 (community aggregator)"}
        resp = requests.get(RSS_URL, headers=headers, timeout=15)
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        events = []
        seen = set()

        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            if not title:
                continue

            # Use the custom calendarEvent fields (more reliable than parsing description)
            date_str = (item.findtext("cal:EventDates", namespaces=NS) or "").strip()
            time_str = (item.findtext("cal:EventTimes", namespaces=NS) or "").strip()
            location = (item.findtext("cal:Location", namespaces=NS) or "").strip()
            link = (item.findtext("link") or "").strip()

            # Parse date — format is "April 12, 2026"
            date_normalized = self.normalize_date(date_str)
            if not date_normalized:
                log.debug("[jones-library] Skipping %r — bad date %r", title, date_str)
                continue

            # Dedup by title + date
            key = f"{title}|{date_normalized}"
            if key in seen:
                continue
            seen.add(key)

            # Parse time range
            start_time, end_time = parse_time_range(time_str) if time_str else ("", "")

            # Parse location
            venue, address = clean_location(location)

            # Check for image
            enclosure = item.find("enclosure")
            image_url = enclosure.get("url") if enclosure is not None else None

            events.append(Event(
                title=self.clean(title),
                date=date_normalized,
                time=start_time,
                end_time=end_time,
                venue=venue,
                address=address,
                town=self.town,
                description="",  # RSS description just repeats the time
                url=link,
                image_url=image_url,
                category=guess_category(title),
                source=self.name,
            ))

        log.debug("[jones-library] Found %d events", len(events))
        return events
