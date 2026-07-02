"""Tests for the weekly email digest — selection window, ordering, capping, escaping."""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from email_digest import MAX_PER_DAY, build_html, select_upcoming

TODAY = date.today().isoformat()
TOMORROW = (date.today() + timedelta(days=1)).isoformat()
NEXT_MONTH = (date.today() + timedelta(days=40)).isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


def make_event(title, event_date, time="7:00 PM", **kw):
    return {
        "title": title, "date": event_date, "time": time,
        "venue": kw.get("venue", "Test Venue"), "town": kw.get("town", "Amherst"),
        "category": kw.get("category", "music"), "url": kw.get("url", ""),
        "description": "", "source": "test",
    }


class TestSelectUpcoming:
    def test_window(self):
        events = [
            make_event("Past", YESTERDAY),
            make_event("Today", TODAY),
            make_event("Tomorrow", TOMORROW),
            make_event("Next Month", NEXT_MONTH),
        ]
        titles = [e["title"] for e in select_upcoming(events, days=14)]
        assert titles == ["Today", "Tomorrow"]

    def test_chronological_within_day(self):
        events = [
            make_event("Noon", TODAY, time="12:00 PM"),
            make_event("Morning", TODAY, time="9:00 AM"),
            make_event("AllDay", TODAY, time=""),
        ]
        titles = [e["title"] for e in select_upcoming(events, days=14)]
        assert titles == ["AllDay", "Morning", "Noon"]


class TestBuildHtml:
    def test_day_capped_with_more_link(self):
        events = [make_event(f"Event {i}", TOMORROW) for i in range(MAX_PER_DAY + 5)]
        html = build_html(select_upcoming(events, 14), total=100, days=14)
        assert html.count("Event ") == MAX_PER_DAY
        assert "+5 more" in html

    def test_no_more_link_when_under_cap(self):
        events = [make_event("Solo Show", TOMORROW)]
        html = build_html(select_upcoming(events, 14), total=1, days=14)
        assert "more" not in html.lower() or "+0" not in html

    def test_html_in_title_escaped(self):
        events = [make_event("<script>alert(1)</script>", TOMORROW)]
        html = build_html(select_upcoming(events, 14), total=1, days=14)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_empty_window_message(self):
        html = build_html([], total=100, days=14)
        assert "No events scheduled" in html
