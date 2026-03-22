"""Scraper for UMass Amherst events (events.umass.edu) — uses JSON-LD structured data."""

import json
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper, Event

BASE_URL = "https://events.umass.edu"
# Fetch multiple pages to get enough events
PAGES = [
    f"{BASE_URL}/calendar",
    f"{BASE_URL}/calendar?page=1",
]

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


def guess_category(title: str) -> str:
    tl = title.lower()
    for keyword, cat in CATEGORY_MAP.items():
        if keyword in tl:
            return cat
    return "academia"  # UMass events default to academic


def parse_iso(iso: str):
    """Return (date_str 'YYYY-MM-DD', time_str 'H:MM AM/PM') from ISO datetime."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        date_str = dt.strftime("%Y-%m-%d")
        time_str = dt.strftime("%-I:%M %p")
        return date_str, time_str
    except Exception:
        return iso[:10] if len(iso) >= 10 else "", ""


class UMassScraper(BaseScraper):
    name = "umass"
    town = "Amherst"

    def _fetch(self) -> list[Event]:
        headers = {"User-Agent": "PioneerValleyEvents/1.0 (community aggregator)"}
        events = []
        seen_ids = set()

        for page_url in PAGES:
            try:
                resp = requests.get(page_url, headers=headers, timeout=15)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        data = json.loads(script.string or "")
                    except json.JSONDecodeError:
                        continue

                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        if item.get("@type") != "Event":
                            continue

                        name = self.clean(item.get("name", ""))
                        if not name:
                            continue

                        start = item.get("startDate", "")
                        end = item.get("endDate", "")
                        if not start:
                            continue

                        date_str, time_str = parse_iso(start)
                        _, end_time_str = parse_iso(end) if end else ("", "")
                        if not date_str:
                            continue

                        # Deduplicate by name + date
                        key = f"{name}|{date_str}"
                        if key in seen_ids:
                            continue
                        seen_ids.add(key)

                        location = item.get("location", {})
                        if isinstance(location, dict):
                            venue = self.clean(location.get("name", "UMass Amherst"))
                            addr_obj = location.get("address", {})
                            if isinstance(addr_obj, dict):
                                address = ", ".join(filter(None, [
                                    addr_obj.get("streetAddress", ""),
                                    addr_obj.get("addressLocality", ""),
                                    addr_obj.get("addressRegion", ""),
                                    addr_obj.get("postalCode", ""),
                                ]))
                            else:
                                address = str(addr_obj) if addr_obj else "Amherst, MA 01003"
                        else:
                            venue = "UMass Amherst"
                            address = "Amherst, MA 01003"

                        description = self.clean(item.get("description", ""))[:600]
                        event_url = item.get("url", "")
                        image_url = item.get("image", None)
                        if isinstance(image_url, dict):
                            image_url = image_url.get("url")
                        elif isinstance(image_url, list):
                            image_url = image_url[0] if image_url else None

                        events.append(Event(
                            title=name,
                            date=date_str,
                            time=time_str,
                            end_time=end_time_str,
                            venue=venue,
                            address=address,
                            town=self.town,
                            description=description,
                            url=event_url,
                            image_url=image_url,
                            category=guess_category(name),
                            source=self.name,
                        ))

            except Exception as e:
                print(f"[{self.name}] Error on {page_url}: {e}")

        print(f"[{self.name}] Found {len(events)} events")
        return events
