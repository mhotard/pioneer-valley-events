"""Shared base class for scrapers that read iCal (.ics) feeds."""

import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests

from .base import BaseScraper, Event

log = logging.getLogger("pipeline")

EASTERN = ZoneInfo("America/New_York")


def _format_dt(dt) -> tuple[str, str]:
    """Return (date 'YYYY-MM-DD', time 'H:MM AM/PM') from an iCal dt value."""
    if isinstance(dt, datetime):
        if dt.tzinfo:
            dt = dt.astimezone(EASTERN)
        return dt.strftime("%Y-%m-%d"), dt.strftime("%-I:%M %p")
    return dt.isoformat(), ""


class ICalScraper(BaseScraper):
    """Fetches an iCal feed and converts future VEVENTs to Events.

    Subclasses set the class attributes below and may override
    `accept(summary, location)` to filter which events are kept.
    """

    address: str = ""
    default_venue: str = ""
    category: str = "community"

    def accept(self, summary: str, location: str) -> bool:
        return True

    def _fetch(self) -> list[Event]:
        try:
            from icalendar import Calendar
        except ImportError:
            raise ImportError("icalendar not installed. Run: pip install icalendar")

        headers = {"User-Agent": "PioneerValleyEvents/1.0 (community aggregator)"}
        resp = requests.get(self.url, headers=headers, timeout=20)
        resp.raise_for_status()

        cal = Calendar.from_ical(resp.content)
        today = date.today().isoformat()
        events = []

        for component in cal.walk():
            if component.name != "VEVENT":
                continue

            summary = self.clean(str(component.get("SUMMARY", "")))
            location = self.clean(str(component.get("LOCATION", "")))
            if not summary or not self.accept(summary, location):
                continue

            dtstart = component.get("DTSTART")
            if not dtstart:
                continue
            date_str, time_str = _format_dt(dtstart.dt)
            if date_str < today:
                continue

            dtend = component.get("DTEND")
            end_time_str = _format_dt(dtend.dt)[1] if dtend else ""

            events.append(Event(
                title=summary,
                date=date_str,
                time=time_str,
                end_time=end_time_str,
                venue=location or self.default_venue,
                address=self.address,
                town=self.town,
                description=self.clean(str(component.get("DESCRIPTION", "")))[:400],
                url=str(component.get("URL", "")),
                image_url=None,
                category=self.category,
                source=self.name,
            ))

        log.debug("[%s] Found %d events", self.name, len(events))
        return events
