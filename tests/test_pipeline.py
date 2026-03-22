"""Tests for pipeline deduplication and date-filtering logic."""

import os

# Import the functions under test directly
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pipeline import deduplicate, filter_by_date

# ---- Helpers ----

def make_event(title, event_date, venue="Test Venue", description=""):
    return {
        "id": f"evt-test-{title[:8]}",
        "title": title,
        "date": event_date,
        "venue": venue,
        "town": "Northampton",
        "category": "music",
        "time": "7:00 PM",
        "end_time": "",
        "address": "123 Main St",
        "description": description,
        "url": "https://example.com",
        "image_url": None,
        "source": "test",
    }


TODAY = date.today().isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()
FUTURE = (date.today() + timedelta(days=10)).isoformat()
FAR_FUTURE = (date.today() + timedelta(days=200)).isoformat()


# ---- Deduplication tests ----

class TestDeduplicate:
    def test_empty_list(self):
        assert deduplicate([]) == []

    def test_single_event_unchanged(self):
        events = [make_event("Jazz Night", FUTURE)]
        assert deduplicate(events) == events

    def test_exact_duplicate_removed(self):
        e = make_event("Jazz Night", FUTURE)
        result = deduplicate([e, e.copy()])
        assert len(result) == 1

    def test_same_title_different_dates_both_kept(self):
        e1 = make_event("Jazz Night", FUTURE)
        e2 = make_event("Jazz Night", (date.today() + timedelta(days=20)).isoformat())
        result = deduplicate([e1, e2])
        assert len(result) == 2

    def test_similar_title_same_date_deduped(self):
        # Titles with >82% similarity on the same date → one kept
        e1 = make_event("The Decemberists Live", FUTURE)
        e2 = make_event("The Decemberists Live!", FUTURE)
        result = deduplicate([e1, e2])
        assert len(result) == 1

    def test_different_titles_same_date_both_kept(self):
        e1 = make_event("Jazz Night", FUTURE)
        e2 = make_event("Comedy Show", FUTURE)
        result = deduplicate([e1, e2])
        assert len(result) == 2

    def test_richer_description_wins(self):
        e1 = make_event("Jazz Night", FUTURE, description="Short")
        long_desc = "This is a much longer and more detailed description of the event"
        e2 = make_event("Jazz Night", FUTURE, description=long_desc)
        result = deduplicate([e1, e2])
        assert len(result) == 1
        assert result[0]["description"] == e2["description"]

    def test_different_venues_same_title_date_deduped(self):
        # Same event listed by two sources → deduplicated
        e1 = make_event("Jazz Night", FUTURE, venue="Iron Horse")
        e2 = make_event("Jazz Night", FUTURE, venue="Iron Horse Music Hall")
        result = deduplicate([e1, e2])
        assert len(result) == 1


# ---- Date filter tests ----

class TestFilterByDate:
    def test_future_event_kept(self):
        events = [make_event("Future Show", FUTURE)]
        result = filter_by_date(events)
        assert len(result) == 1

    def test_far_future_event_excluded(self):
        events = [make_event("Way Future Show", FAR_FUTURE)]
        result = filter_by_date(events)
        assert len(result) == 0

    def test_yesterday_excluded(self):
        # DATE_MIN is today - 3 days, so yesterday should be kept
        events = [make_event("Recent Show", YESTERDAY)]
        result = filter_by_date(events)
        assert len(result) == 1

    def test_mixed_list_filtered_correctly(self):
        events = [
            make_event("Past Show", "2020-01-01"),
            make_event("Current Show", FUTURE),
            make_event("Far Future", FAR_FUTURE),
        ]
        result = filter_by_date(events)
        assert len(result) == 1
        assert result[0]["title"] == "Current Show"
