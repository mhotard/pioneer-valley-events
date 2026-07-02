"""Tests for the LocalistScraper base (umass, mtholyoke) against a canned API payload."""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scrapers.localist import LocalistScraper, guess_category, parse_iso

PAYLOAD = {
    "events": [
        {"event": {
            "title": "Jazz Ensemble Concert",
            "location_name": "Buckley Recital Hall",
            "description_text": "An evening of standards.",
            "localist_url": "https://events.example.edu/event/jazz",
            "photo_url": "https://img.example.edu/jazz.jpg",
            "event_instances": [
                {"event_instance": {"start": "2026-07-10T19:30:00-04:00",
                                    "end": "2026-07-10T21:00:00-04:00",
                                    "all_day": False}},
            ],
        }},
        {"event": {
            "title": "Juneteenth",   # all-day, no location
            "event_instances": [
                {"event_instance": {"start": "2026-07-11T00:00:00-04:00",
                                    "all_day": True}},
            ],
        }},
        {"event": {
            "title": "",             # no title → skipped
            "event_instances": [
                {"event_instance": {"start": "2026-07-12T10:00:00-04:00"}},
            ],
        }},
    ]
}


class DummyLocalist(LocalistScraper):
    name = "dummy-localist"
    url = "https://events.example.edu"
    api_url = "https://events.example.edu/api/2/events"
    town = "Testville"
    default_venue = "Example College"
    default_address = "Testville, MA"
    default_category = "academia"


def _fetch_with_payload(payload):
    scraper = DummyLocalist()
    mock_resp = MagicMock()
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()
    with patch("scrapers.localist.requests.get", return_value=mock_resp):
        return scraper.fetch()


class TestLocalistScraper:
    def test_parses_events(self):
        events = _fetch_with_payload(PAYLOAD)
        assert len(events) == 2  # titled events only

    def test_fields(self):
        e = _fetch_with_payload(PAYLOAD)[0]
        assert e.title == "Jazz Ensemble Concert"
        assert e.date == "2026-07-10"
        assert e.time == "7:30 PM"
        assert e.end_time == "9:00 PM"
        assert e.venue == "Buckley Recital Hall"
        assert e.url == "https://events.example.edu/event/jazz"
        assert e.category == "music"  # keyword guess from title
        assert e.source == "dummy-localist"

    def test_all_day_has_no_time_and_default_venue(self):
        e = _fetch_with_payload(PAYLOAD)[1]
        assert e.time == ""
        assert e.venue == "Example College"

    def test_duplicate_instances_deduped(self):
        payload = {"events": [PAYLOAD["events"][0], PAYLOAD["events"][0]]}
        assert len(_fetch_with_payload(payload)) == 1

    def test_http_error_caught_by_fetch(self):
        scraper = DummyLocalist()
        with patch("scrapers.localist.requests.get", side_effect=Exception("boom")):
            assert scraper.fetch() == []
        assert scraper.last_error == "boom"


class TestHelpers:
    def test_parse_iso(self):
        assert parse_iso("2026-07-10T19:30:00-04:00") == ("2026-07-10", "7:30 PM")

    def test_parse_iso_garbage(self):
        assert parse_iso("") == ("", "")

    def test_guess_category_default(self):
        assert guess_category("Something Untypeable", default="academia") == "academia"
