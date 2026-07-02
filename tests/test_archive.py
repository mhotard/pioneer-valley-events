"""Tests for the append-only per-year event archive."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pipeline import update_archive


def make_event(eid, title, event_date, **kw):
    return {
        "id": eid, "title": title, "date": event_date,
        "time": kw.get("time", "7:00 PM"), "venue": kw.get("venue", "V"),
        "town": "Amherst", "category": "music", "source": "test",
        "description": kw.get("description", ""), "url": "",
    }


def load_archive(tmp_path, year):
    with open(tmp_path / f"archive-{year}.json") as f:
        return json.load(f)


class TestUpdateArchive:
    def test_new_events_added_with_first_seen(self, tmp_path):
        events = [make_event("evt-1", "Show", "2026-08-01")]
        added = update_archive(events, archive_dir=str(tmp_path), today="2026-07-02")
        assert added == {"2026": 1}
        data = load_archive(tmp_path, "2026")
        assert data["count"] == 1
        assert data["events"][0]["first_seen"] == "2026-07-02"

    def test_rerun_does_not_duplicate(self, tmp_path):
        events = [make_event("evt-1", "Show", "2026-08-01")]
        update_archive(events, archive_dir=str(tmp_path), today="2026-07-02")
        added = update_archive(events, archive_dir=str(tmp_path), today="2026-07-09")
        assert added == {"2026": 0}
        assert load_archive(tmp_path, "2026")["count"] == 1

    def test_update_refreshes_details_but_keeps_first_seen(self, tmp_path):
        update_archive(
            [make_event("evt-1", "Show", "2026-08-01", description="old")],
            archive_dir=str(tmp_path), today="2026-07-02",
        )
        update_archive(
            [make_event("evt-1", "Show", "2026-08-01", description="new and longer")],
            archive_dir=str(tmp_path), today="2026-07-09",
        )
        rec = load_archive(tmp_path, "2026")["events"][0]
        assert rec["description"] == "new and longer"
        assert rec["first_seen"] == "2026-07-02"

    def test_events_bucketed_by_event_year(self, tmp_path):
        events = [
            make_event("evt-1", "December Show", "2026-12-30"),
            make_event("evt-2", "January Show", "2027-01-02"),
        ]
        added = update_archive(events, archive_dir=str(tmp_path), today="2026-12-20")
        assert added == {"2026": 1, "2027": 1}
        assert load_archive(tmp_path, "2026")["count"] == 1
        assert load_archive(tmp_path, "2027")["count"] == 1

    def test_nothing_deleted_when_event_leaves_window(self, tmp_path):
        update_archive(
            [make_event("evt-old", "Past Show", "2026-03-01")],
            archive_dir=str(tmp_path), today="2026-03-01",
        )
        # Months later, that event is long out of the pipeline window
        update_archive(
            [make_event("evt-new", "New Show", "2026-08-01")],
            archive_dir=str(tmp_path), today="2026-07-02",
        )
        data = load_archive(tmp_path, "2026")
        assert data["count"] == 2
        assert {e["id"] for e in data["events"]} == {"evt-old", "evt-new"}

    def test_records_sorted_chronologically(self, tmp_path):
        events = [
            make_event("evt-b", "Later", "2026-08-02"),
            make_event("evt-a", "Earlier", "2026-08-01"),
        ]
        update_archive(events, archive_dir=str(tmp_path), today="2026-07-02")
        dates = [e["date"] for e in load_archive(tmp_path, "2026")["events"]]
        assert dates == sorted(dates)
