"""Shared base for WordPress sites running The Events Calendar ("tribe") plugin.

These sites expose a public REST API at /wp-json/tribe/events/v1/events —
far cheaper and more reliable than scraping their HTML.
"""

import logging
from datetime import date, timedelta

import requests
from bs4 import BeautifulSoup

from .base import DAYS_FUTURE, BaseScraper, Event

log = logging.getLogger("pipeline")

MAX_PAGES = 4  # 50 events per page

CATEGORY_MAP = {
    "music": "music", "concert": "music",
    "film": "film", "movie": "film",
    "theater": "arts", "theatre": "arts", "art": "arts", "craft": "arts",
    "design": "arts", "exhibit": "arts", "dance": "arts",
    "comedy": "comedy",
    "lecture": "academia", "tour": "academia", "class": "academia",
    "talk": "academia", "workshop": "academia",
    "family": "family", "kids": "family", "children": "family",
    "food": "food",
    "festival": "festival", "fair": "festival",
}


def _strip_html(raw: str) -> str:
    return BeautifulSoup(raw or "", "html.parser").get_text(" ", strip=True)


class TribeEventsScraper(BaseScraper):
    """Subclasses set `api_base` (the site root URL) plus the class attrs below."""

    api_base: str = ""           # e.g. "https://www.example.com"
    default_venue: str = ""
    default_category: str = "community"

    def guess_category(self, title: str, category_names: list[str]) -> str:
        text = " ".join([title] + category_names).lower()
        for keyword, cat in CATEGORY_MAP.items():
            if keyword in text:
                return cat
        return self.default_category

    def _fetch(self) -> list[Event]:
        headers = {"User-Agent": "PioneerValleyEvents/1.0 (community aggregator)"}
        start = date.today().isoformat()
        end = (date.today() + timedelta(days=DAYS_FUTURE)).isoformat()
        next_url = (
            f"{self.api_base}/wp-json/tribe/events/v1/events"
            f"?per_page=50&start_date={start}&end_date={end}"
        )

        events = []
        seen = set()

        for _ in range(MAX_PAGES):
            resp = requests.get(next_url, headers=headers, timeout=20)
            resp.raise_for_status()
            data = resp.json()

            for ev in data.get("events", []):
                title = self.clean(_strip_html(ev.get("title", "")))
                start_date = ev.get("start_date", "")  # "2026-06-11 10:00:00"
                if not title or len(start_date) < 10:
                    continue
                date_str = start_date[:10]

                key = f"{title}|{date_str}"
                if key in seen:
                    continue
                seen.add(key)

                time_str = ""
                if not ev.get("all_day") and len(start_date) >= 16:
                    time_str = self.normalize_time(start_date[11:16])
                end_date = ev.get("end_date", "")
                end_time_str = ""
                if not ev.get("all_day") and len(end_date) >= 16 and end_date[:10] == date_str:
                    end_time_str = self.normalize_time(end_date[11:16])

                venue = ev.get("venue") or {}
                if not isinstance(venue, dict):
                    venue = {}
                category_names = [
                    _strip_html(c.get("name", "")) for c in ev.get("categories", [])
                ]

                image = ev.get("image")
                image_url = image.get("url") if isinstance(image, dict) else None

                events.append(Event(
                    title=title,
                    date=date_str,
                    time=time_str,
                    end_time=end_time_str,
                    venue=self.clean(venue.get("venue", "")) or self.default_venue,
                    address=self.clean(venue.get("address", "")),
                    town=self.clean(venue.get("city", "")) or self.town,
                    description=self.clean(_strip_html(ev.get("excerpt", "")))[:500],
                    url=ev.get("url", ""),
                    image_url=image_url,
                    category=self.guess_category(title, category_names),
                    source=self.name,
                ))

            next_url = data.get("next_rest_url")
            if not next_url:
                break

        log.debug("[%s] Found %d events", self.name, len(events))
        return events


class SpringfieldMuseumsScraper(TribeEventsScraper):
    name = "springfield-museums"
    url = "https://springfieldmuseums.org/calendar-of-events/"
    api_base = "https://springfieldmuseums.org"
    town = "Springfield"
    default_venue = "Springfield Museums"
    default_category = "arts"


class HawksReedScraper(TribeEventsScraper):
    name = "hawks-reed"
    url = "https://www.hawksandreed.com/events"
    api_base = "https://www.hawksandreed.com"
    town = "Greenfield"
    default_venue = "Hawks & Reed Performing Arts Center"
    default_category = "music"
