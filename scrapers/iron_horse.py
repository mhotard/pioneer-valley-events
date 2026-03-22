"""Scraper for Iron Horse Music Hall / Pearl Street (iheg.com)."""

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper, Event

BASE_URL = "https://www.iheg.com"
LISTINGS = [
    (f"{BASE_URL}/iron-horse-music-hall/calendar", "Iron Horse Music Hall", "Northampton"),
    (f"{BASE_URL}/pearl-street-nightclub/calendar", "Pearl Street Nightclub", "Northampton"),
]


class IronHorseScraper(BaseScraper):
    name = "iron-horse"
    town = "Northampton"

    def _fetch(self) -> list[Event]:
        headers = {"User-Agent": "PioneerValleyEvents/1.0 (community aggregator)"}
        events = []

        for url, venue_name, town in LISTINGS:
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                for item in soup.select(".event-item, article.event, .listing-item"):
                    try:
                        title_el = item.select_one("h3, h2, .event-title, .title")
                        date_el  = item.select_one("time, .event-date, .date")
                        time_el  = item.select_one(".event-time, .time, .doors")
                        link_el  = item.select_one("a[href]")
                        img_el   = item.select_one("img")
                        desc_el  = item.select_one(".event-description, .description, p")

                        if not title_el or not date_el:
                            continue

                        title    = self.clean(title_el.get_text())
                        raw_date = date_el.get("datetime", date_el.get_text())
                        raw = raw_date[:10] if "T" in raw_date else raw_date
                        date     = self.normalize_date(raw)
                        if not date or not title:
                            continue

                        time  = self.normalize_time(time_el.get_text()) if time_el else ""
                        href  = link_el["href"] if link_el else ""
                        if href and href.startswith("/"):
                            href = BASE_URL + href
                        img   = img_el.get("src", "") if img_el else None
                        desc  = self.clean(desc_el.get_text()[:400]) if desc_el else ""

                        events.append(Event(
                            title=title,
                            date=date,
                            time=time,
                            venue=venue_name,
                            address=(
                                "20 Center St, Northampton, MA 01060"
                                if "Iron Horse" in venue_name
                                else "10 Pearl St, Northampton, MA 01060"
                            ),
                            town=town,
                            description=desc,
                            url=href,
                            image_url=img or None,
                            category="music",
                            source=self.name,
                        ))
                    except Exception as e:
                        print(f"[{self.name}] Skipping item: {e}")
                        continue

            except Exception as e:
                print(f"[{self.name}] Failed to fetch {url}: {e}")

        print(f"[{self.name}] Found {len(events)} events")
        return events
