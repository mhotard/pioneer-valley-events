"""Scraper for City of Northampton events calendar."""

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper, Event

BASE_URL = "https://www.northamptonma.gov"
CALENDAR_URL = f"{BASE_URL}/calendar.aspx"


class NorthamptonCityScraper(BaseScraper):
    name = "northampton-city"
    town = "Northampton"

    def _fetch(self) -> list[Event]:
        headers = {"User-Agent": "PioneerValleyEvents/1.0 (community aggregator)"}
        resp = requests.get(CALENDAR_URL, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        events = []
        for item in soup.select(".fc-event, .calendar-item, .event-item, tr.eventRow, li.event"):
            try:
                title_el = item.select_one("a, .event-title, h3, h4, .title, td.eventTitle")
                date_el  = item.select_one("time, .event-date, .date, td.eventDate")
                link_el  = item.select_one("a[href]")
                desc_el  = item.select_one(".description, p, .event-description")

                if not title_el or not date_el:
                    continue

                title    = self.clean(title_el.get_text())
                raw_date = date_el.get("datetime", date_el.get_text())
                date     = self.normalize_date(raw_date[:10] if "T" in raw_date else raw_date)
                if not date or not title:
                    continue

                href = link_el["href"] if link_el else ""
                if href and href.startswith("/"):
                    href = BASE_URL + href
                desc = self.clean(desc_el.get_text()[:400]) if desc_el else ""

                events.append(Event(
                    title=title,
                    date=date,
                    venue="City of Northampton",
                    address="Northampton, MA 01060",
                    town=self.town,
                    description=desc,
                    url=href,
                    category="community",
                    source=self.name,
                ))
            except Exception as e:
                print(f"[{self.name}] Skipping item: {e}")
                continue

        print(f"[{self.name}] Found {len(events)} events")
        return events
