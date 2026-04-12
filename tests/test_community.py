"""Tests for the community events scraper and recurrence expansion."""

import json
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scrapers.community import CommunityEventsScraper, expand_recurrence

# ---- expand_recurrence ----


class TestExpandEveryWeekday:
    def test_every_tuesday_in_30_days(self):
        start = date(2026, 4, 1)
        end = date(2026, 4, 30)
        dates = expand_recurrence("every Tuesday", start, end)
        assert all(d.weekday() == 1 for d in dates)  # Tuesday = 1
        assert len(dates) == 4  # April 2026 has 4 Tuesdays (7, 14, 21, 28)

    def test_every_sunday(self):
        start = date(2026, 4, 1)
        end = date(2026, 4, 30)
        dates = expand_recurrence("every Sunday", start, end)
        assert all(d.weekday() == 6 for d in dates)
        assert len(dates) == 4

    def test_case_insensitive(self):
        start = date(2026, 4, 1)
        end = date(2026, 4, 30)
        dates = expand_recurrence("Every TUESDAY", start, end)
        assert len(dates) == 4


class TestExpandNthWeekday:
    def test_second_friday(self):
        start = date(2026, 1, 1)
        end = date(2026, 6, 30)
        dates = expand_recurrence("second Friday of each month", start, end)
        assert len(dates) == 6
        # Verify each is a Friday
        assert all(d.weekday() == 4 for d in dates)
        # Verify each is in days 8-14 (second week)
        assert all(8 <= d.day <= 14 for d in dates)

    def test_first_saturday(self):
        start = date(2026, 4, 1)
        end = date(2026, 4, 30)
        dates = expand_recurrence("first Saturday of each month", start, end)
        assert len(dates) == 1
        assert dates[0] == date(2026, 4, 4)

    def test_last_wednesday(self):
        start = date(2026, 4, 1)
        end = date(2026, 4, 30)
        dates = expand_recurrence("last Wednesday of each month", start, end)
        assert len(dates) == 1
        assert dates[0] == date(2026, 4, 29)

    def test_fourth_monday(self):
        start = date(2026, 4, 1)
        end = date(2026, 4, 30)
        dates = expand_recurrence("fourth Monday of each month", start, end)
        assert len(dates) == 1
        assert dates[0] == date(2026, 4, 27)


class TestExpandBounds:
    def test_event_start_end_narrows_window(self):
        dates = expand_recurrence(
            "every Monday",
            range_start=date(2026, 1, 1),
            range_end=date(2026, 12, 31),
            event_start=date(2026, 4, 1),
            event_end=date(2026, 4, 30),
        )
        assert all(date(2026, 4, 1) <= d <= date(2026, 4, 30) for d in dates)

    def test_no_overlap_returns_empty(self):
        dates = expand_recurrence(
            "every Monday",
            range_start=date(2026, 5, 1),
            range_end=date(2026, 5, 31),
            event_start=date(2026, 1, 1),
            event_end=date(2026, 2, 28),
        )
        assert dates == []

    def test_unrecognized_pattern_returns_empty(self):
        dates = expand_recurrence("biweekly on Thursdays", date(2026, 1, 1), date(2026, 12, 31))
        assert dates == []


# ---- CommunityEventsScraper ----


def _write_events(events, tmpdir):
    path = os.path.join(tmpdir, "community_events.json")
    with open(path, "w") as f:
        json.dump({"events": events}, f)
    return path


class TestCommunityEventsScraper:
    def test_one_off_event(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_events([{
                "title": "Spring Concert",
                "date": date.today().isoformat(),
                "venue": "Town Hall",
                "town": "Amherst",
                "category": "music",
            }], tmpdir)
            scraper = CommunityEventsScraper(path=path)
            events = scraper.fetch()
            assert len(events) == 1
            assert events[0].title == "Spring Concert"
            assert events[0].source == "community"

    def test_recurring_event_expands(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_events([{
                "title": "Open Mic Night",
                "recurrence": "every Wednesday",
                "venue": "Cafe",
                "town": "Northampton",
                "category": "music",
            }], tmpdir)
            scraper = CommunityEventsScraper(path=path)
            events = scraper.fetch()
            # Should produce multiple events (roughly 13 Wednesdays in 93 days)
            assert len(events) >= 10
            assert all(e.title == "Open Mic Night" for e in events)
            # Each should have a unique date-based ID
            ids = [e.id for e in events]
            assert len(ids) == len(set(ids))

    def test_missing_file_returns_empty(self):
        scraper = CommunityEventsScraper(path="/nonexistent/path.json")
        events = scraper.fetch()
        assert events == []

    def test_entry_without_title_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_events([{
                "date": date.today().isoformat(),
                "town": "Amherst",
            }], tmpdir)
            scraper = CommunityEventsScraper(path=path)
            events = scraper.fetch()
            assert events == []

    def test_entry_without_date_or_recurrence_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_events([{
                "title": "Mystery Event",
                "town": "Amherst",
            }], tmpdir)
            scraper = CommunityEventsScraper(path=path)
            events = scraper.fetch()
            assert events == []

    def test_default_category_is_community(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_events([{
                "title": "Block Party",
                "date": date.today().isoformat(),
                "town": "Amherst",
            }], tmpdir)
            scraper = CommunityEventsScraper(path=path)
            events = scraper.fetch()
            assert events[0].category == "community"
