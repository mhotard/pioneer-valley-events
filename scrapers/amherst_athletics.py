"""Scraper for Amherst College Athletics home games via iCal feed."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests

from .base import BaseScraper, Event

ICAL_URL = "https://athletics.amherst.edu/calendar.ics"
EASTERN = ZoneInfo("America/New_York")

# Lowercase substrings that identify a home game location
HOME_KEYWORDS = {
    "amherst, ma", "amherst college", "pratt field", "lefrak",
    "orr rink", "Alumni Gym".lower(), "lord jeffs".lower(),
    "koch sports".lower(), "greenway".lower(),
}


def _is_home(location: str) -> bool:
    ll = location.lower()
    return any(kw in ll for kw in HOME_KEYWORDS)


class AmherstAthleticsScraper(BaseScraper):
    name = "amherst-athletics"
    town = "Amherst"

    def _fetch(self) -> list[Event]:
        try:
            from icalendar import Calendar
        except ImportError:
            raise ImportError("icalendar not installed. Run: pip install icalendar")

        headers = {"User-Agent": "PioneerValleyEvents/1.0 (community aggregator)"}
        resp = requests.get(ICAL_URL, headers=headers, timeout=20)
        resp.raise_for_status()

        cal = Calendar.from_ical(resp.content)
        today = date.today()
        events = []

        for component in cal.walk():
            if component.name != "VEVENT":
                continue

            summary = self.clean(str(component.get("SUMMARY", "")))
            location = self.clean(str(component.get("LOCATION", "")))

            if not _is_home(location):
                continue

            dtstart = component.get("DTSTART")
            if not dtstart:
                continue

            dt = dtstart.dt
            if isinstance(dt, datetime):
                if dt.tzinfo:
                    dt = dt.astimezone(EASTERN)
                date_str = dt.strftime("%Y-%m-%d")
                time_str = dt.strftime("%-I:%M %p")
            else:
                date_str = dt.isoformat()
                time_str = ""

            if date_str < today.isoformat():
                continue

            dtend = component.get("DTEND")
            end_time_str = ""
            if dtend:
                dt_end = dtend.dt
                if isinstance(dt_end, datetime):
                    if dt_end.tzinfo:
                        dt_end = dt_end.astimezone(EASTERN)
                    end_time_str = dt_end.strftime("%-I:%M %p")

            description = self.clean(str(component.get("DESCRIPTION", "")))[:400]
            url = str(component.get("URL", ""))

            events.append(Event(
                title=summary,
                date=date_str,
                time=time_str,
                end_time=end_time_str,
                venue=location or "Amherst College Athletics",
                address="Amherst, MA 01002",
                town=self.town,
                description=description,
                url=url,
                image_url=None,
                category="outdoor",
                source=self.name,
            ))

        print(f"[{self.name}] Found {len(events)} events")
        return events
