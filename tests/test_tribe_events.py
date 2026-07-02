"""Tests for TribeEventsScraper (springfield-museums, hawks-reed) against a canned payload."""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scrapers.tribe_events import TribeEventsScraper

PAYLOAD = {
    "events": [
        {
            "title": "Walking Tour: Underground Railroad",
            "start_date": "2026-07-13 10:30:00",
            "end_date": "2026-07-13 12:00:00",
            "all_day": False,
            "url": "https://example.org/program/walking-tour",
            "excerpt": "<p>An enlightening stroll</p>",
            "venue": {"venue": "Springfield Museums", "address": "21 Edwards St",
                      "city": "Springfield"},
            "categories": [{"name": "Lectures &amp; Tours"}],
            "image": {"url": "https://example.org/img.jpg"},
        },
        {
            "title": "All Day Festival",
            "start_date": "2026-07-14 00:00:00",
            "end_date": "2026-07-14 23:59:59",
            "all_day": True,
            "url": "",
            "excerpt": "",
            "venue": [],          # tribe sometimes returns [] instead of {}
            "categories": [],
            "image": False,       # and False instead of a dict
        },
    ],
    "next_rest_url": None,
}


class DummyTribe(TribeEventsScraper):
    name = "dummy-tribe"
    url = "https://example.org/events"
    api_base = "https://example.org"
    town = "Fallbacktown"
    default_venue = "Fallback Venue"
    default_category = "community"


def _fetch_with_payload(payload):
    scraper = DummyTribe()
    mock_resp = MagicMock()
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()
    with patch("scrapers.tribe_events.requests.get", return_value=mock_resp):
        return scraper.fetch()


class TestTribeEventsScraper:
    def test_parses_events(self):
        assert len(_fetch_with_payload(PAYLOAD)) == 2

    def test_fields(self):
        e = _fetch_with_payload(PAYLOAD)[0]
        assert e.date == "2026-07-13"
        assert e.time == "10:30 AM"
        assert e.end_time == "12:00 PM"
        assert e.venue == "Springfield Museums"
        assert e.town == "Springfield"
        assert e.description == "An enlightening stroll"  # HTML stripped
        assert e.category == "academia"  # "tour" keyword from category name
        assert e.image_url == "https://example.org/img.jpg"

    def test_all_day_and_fallbacks(self):
        e = _fetch_with_payload(PAYLOAD)[1]
        assert e.time == ""
        assert e.end_time == ""
        assert e.venue == "Fallback Venue"
        assert e.town == "Fallbacktown"
        assert e.image_url is None
        assert e.category == "festival"  # from title keyword

    def test_pagination_follows_next_url_once(self):
        page2 = {"events": [], "next_rest_url": None}
        scraper = DummyTribe()
        r1, r2 = MagicMock(), MagicMock()
        r1.json.return_value = {**PAYLOAD, "next_rest_url": "https://example.org/page2"}
        r2.json.return_value = page2
        r1.raise_for_status = r2.raise_for_status = MagicMock()
        with patch("scrapers.tribe_events.requests.get", side_effect=[r1, r2]) as m:
            events = scraper.fetch()
        assert len(events) == 2
        assert m.call_count == 2
        assert m.call_args_list[1][0][0] == "https://example.org/page2"
