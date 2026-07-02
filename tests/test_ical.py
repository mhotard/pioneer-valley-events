"""Tests for the ICalScraper base against a small .ics fixture."""

import os
import sys
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scrapers.ical import ICalScraper

FUTURE = (date.today() + timedelta(days=7)).strftime("%Y%m%d")
PAST = (date.today() - timedelta(days=30)).strftime("%Y%m%d")

ICS = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
SUMMARY:Basketball vs Rivals
LOCATION:Home Court, Amherst, MA
DTSTART:{FUTURE}T190000Z
DTEND:{FUTURE}T210000Z
URL:https://example.edu/game
END:VEVENT
BEGIN:VEVENT
SUMMARY:Old Game
LOCATION:Home Court, Amherst, MA
DTSTART:{PAST}T190000Z
END:VEVENT
BEGIN:VEVENT
SUMMARY:Away Game
LOCATION:Elsewhere Stadium
DTSTART:{FUTURE}T190000Z
END:VEVENT
END:VCALENDAR
"""


class DummyICal(ICalScraper):
    name = "dummy-ical"
    url = "https://example.edu/calendar.ics"
    town = "Amherst"
    address = "Amherst, MA"
    default_venue = "Example Athletics"
    category = "outdoor"

    def accept(self, summary: str, location: str) -> bool:
        return "amherst" in location.lower()


def _fetch():
    scraper = DummyICal()
    mock_resp = MagicMock()
    mock_resp.content = ICS.encode()
    mock_resp.raise_for_status = MagicMock()
    with patch("scrapers.ical.requests.get", return_value=mock_resp):
        return scraper.fetch()


class TestICalScraper:
    def test_past_and_rejected_events_skipped(self):
        events = _fetch()
        # Old Game is past; Away Game fails accept(); one event remains
        assert [e.title for e in events] == ["Basketball vs Rivals"]

    def test_fields(self):
        e = _fetch()[0]
        assert e.date == (date.today() + timedelta(days=7)).isoformat()
        assert e.time == "3:00 PM"  # 19:00 UTC → 15:00 Eastern (EDT)
        assert e.end_time == "5:00 PM"
        assert e.venue == "Home Court, Amherst, MA"
        assert e.url == "https://example.edu/game"
        assert e.category == "outdoor"
