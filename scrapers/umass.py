"""Scraper for UMass Amherst events (events.umass.edu)."""

import re
import requests
from bs4 import BeautifulSoup
from .base import BaseScraper, Event

BASE_URL = "https://events.umass.edu"
LISTING_URL = f"{BASE_URL}/calendar"

CATEGORY_MAP = {
    "music": "music",
    "concert": "music",
    "performance": "arts",
    "theater": "arts",
    "theatre": "arts",
    "art": "arts",
    "film": "film",
    "movie": "film",
    "lecture": "academia",
    "talk": "academia",
    "seminar": "academia",
    "symposium": "academia",
    "workshop": "academia",
    "comedy": "comedy",
    "family": "family",
    "children": "family",
    "sport": "outdoor",
    "recreation": "outdoor",
    "food": "food",
    "festival": "festival",
    "fair": "festival",
}


def guess_category(title: str, tags: list[str]) -> str:
    combined = (title + " " + " ".join(tags)).lower()
    for keyword, cat in CATEGORY_MAP.items():
        if keyword in combined:
            return cat
    return "community"


class UMassScraper(BaseScraper):
    name = "umass"
    town = "Amherst"

    def _fetch(self) -> list[Event]:
        headers = {"User-Agent": "PioneerValleyEvents/1.0 (community aggregator)"}
        resp = requests.get(LISTING_URL, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        events = []
        # UMass events calendar uses .views-row items
        for row in soup.select(".views-row, article.event-item, .em-item"):
            try:
                title_el = row.select_one("h3 a, h2 a, .views-field-title a, .event-title a")
                date_el  = row.select_one(".date-display-single, time, .views-field-field-event-date, .em-date")
                venue_el = row.select_one(".views-field-field-location, .location, .em-venue")
                time_el  = row.select_one(".views-field-field-event-time, .time, .em-time")

                if not title_el or not date_el:
                    continue

                title = self.clean(title_el.get_text())
                raw_date = date_el.get("datetime", date_el.get_text())
                date = self.normalize_date(raw_date[:10] if "T" in raw_date else raw_date)
                if not date:
                    continue

                venue = self.clean(venue_el.get_text()) if venue_el else "UMass Amherst"
                time  = self.normalize_time(time_el.get_text()) if time_el else ""
                url   = BASE_URL + title_el["href"] if title_el.get("href", "").startswith("/") else title_el.get("href", "")

                # Fetch detail page for description
                description = ""
                if url:
                    try:
                        detail = requests.get(url, headers=headers, timeout=10)
                        dsoup = BeautifulSoup(detail.text, "html.parser")
                        desc_el = dsoup.select_one(".field-name-body, .event-description, .views-field-body")
                        if desc_el:
                            description = self.clean(desc_el.get_text()[:600])
                    except Exception:
                        pass

                tags = [t.get_text() for t in row.select(".views-field-field-category a, .tag, .category")]
                category = guess_category(title, tags)

                events.append(Event(
                    title=title,
                    date=date,
                    time=time,
                    venue=venue,
                    address="Amherst, MA 01003",
                    town=self.town,
                    description=description,
                    url=url,
                    category=category,
                    source=self.name,
                ))
            except Exception as e:
                print(f"[{self.name}] Skipping row: {e}")
                continue

        print(f"[{self.name}] Found {len(events)} events")
        return events
