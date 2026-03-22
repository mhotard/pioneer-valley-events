"""Scraper for Gateway City Arts (Holyoke)."""

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper, Event

BASE_URL = "https://gatewaycityarts.com"
EVENTS_URL = f"{BASE_URL}/events"


class GatewayCityArtsScraper(BaseScraper):
    name = "gateway-city-arts"
    town = "Holyoke"

    def _fetch(self) -> list[Event]:
        headers = {"User-Agent": "PioneerValleyEvents/1.0 (community aggregator)"}
        resp = requests.get(EVENTS_URL, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        events = []
        for item in soup.select(".event, article, .event-item, .tribe-event"):
            try:
                title_el = item.select_one("h2, h3, .event-title, .tribe-event-title")
                date_el  = item.select_one("time, .event-date, .tribe-event-date-start")
                time_el  = item.select_one(".time, .event-time, .tribe-event-time")
                link_el  = item.select_one("a[href]")
                img_el   = item.select_one("img")
                desc_el  = item.select_one(".description, .tribe-event-description, p")

                if not title_el or not date_el:
                    continue

                title    = self.clean(title_el.get_text())
                raw_date = date_el.get("datetime", date_el.get_text())
                date     = self.normalize_date(raw_date[:10] if "T" in raw_date else raw_date)
                if not date or not title:
                    continue

                time  = self.normalize_time(time_el.get_text()) if time_el else ""
                href  = link_el["href"] if link_el else ""
                if href and href.startswith("/"):
                    href = BASE_URL + href
                img   = img_el.get("src", "") if img_el else None
                desc  = self.clean(desc_el.get_text()[:400]) if desc_el else ""

                title_lower = title.lower()
                if any(w in title_lower for w in ["comedy", "stand-up"]):
                    category = "comedy"
                elif any(w in title_lower for w in ["drag", "pride", "queer", "community"]):
                    category = "community"
                elif any(w in title_lower for w in ["dance", "theater", "theatre", "art", "gallery"]):  # noqa: E501
                    category = "arts"
                elif any(w in title_lower for w in ["music", "band", "concert", "jazz", "hip-hop"]):
                    category = "music"
                else:
                    category = "arts"

                events.append(Event(
                    title=title,
                    date=date,
                    time=time,
                    venue="Gateway City Arts",
                    address="92 Race St, Holyoke, MA 01040",
                    town=self.town,
                    description=desc,
                    url=href,
                    image_url=img or None,
                    category=category,
                    source=self.name,
                ))
            except Exception as e:
                print(f"[{self.name}] Skipping item: {e}")
                continue

        print(f"[{self.name}] Found {len(events)} events")
        return events
