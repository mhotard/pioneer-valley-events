"""Scraper for Western Mass Race Calendar (harriers.org) — reads race_calendar.json directly."""

import logging
from datetime import date

import requests

from .base import BaseScraper, Event

log = logging.getLogger("pipeline")

JSON_URL = "https://harriers.org/Calendar/race_calendar.json"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class HarriersScraper(BaseScraper):
    name = "harriers-race-calendar"
    url = "https://harriers.org/Calendar/wmracecalendar.html"
    town = "Pioneer Valley"

    def _fetch(self) -> list[Event]:
        headers = {"User-Agent": BROWSER_UA}
        resp = requests.get(JSON_URL, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        today = date.today().isoformat()
        events = []

        for r in data.get("RaceItemList", []):
            if not r.get("SubmissionApproved"):
                continue
            if r.get("IsRaceArchive") or r.get("Rejected"):
                continue
            if r.get("SeriesCode", ""):
                continue  # weekly series handled separately in static HTML

            event_date = r.get("EventDateTime", "")[:10]
            if not event_date or event_date < today:
                continue

            # The calendar accepts submissions from anywhere (Cooperstown NY
            # has shown up) — keep Massachusetts races only. Blank state is
            # given the benefit of the doubt (the calendar is WMass-focused).
            state = (r.get("State") or "").strip().upper()
            if state and state != "MA":
                continue

            title = (r.get("EventName") or "").strip()
            if not title:
                continue

            city = (r.get("City") or "").strip()
            state = (r.get("State") or "").strip()
            venue = f"{city}, {state}" if city else state or "Western Mass"
            town = city or "Pioneer Valley"

            distances = (r.get("Distances") or "").strip()
            description = distances if distances else ""

            url = (r.get("RegistrationURL") or r.get("WebSiteURL") or "").strip()

            events.append(Event(
                title=title,
                date=event_date,
                time="",
                end_time="",
                venue=venue,
                address=(r.get("AddressLine1") or "").strip(),
                town=town,
                description=description,
                url=url,
                image_url=None,
                category="outdoor",
                source=self.name,
            ))

        log.debug("[harriers-race-calendar] Found %d events", len(events))
        return events
