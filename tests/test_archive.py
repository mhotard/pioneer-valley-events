"""Tests for the append-only per-year event archive."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pipeline
from json_storage import JsonStorageError
from pipeline import publish_payload, update_archive


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

    def test_corrupt_archive_fails_without_replacement(self, tmp_path):
        path = tmp_path / "archive-2026.json"
        path.write_bytes(b"{corrupt historical bytes")

        with pytest.raises(JsonStorageError, match=str(path)):
            update_archive(
                [make_event("evt-new", "New", "2026-08-01")],
                archive_dir=str(tmp_path),
                today="2026-07-02",
            )

        assert path.read_bytes() == b"{corrupt historical bytes"

    @pytest.mark.parametrize(
        "stored",
        [
            None,
            [],
            {},
            {"events": None},
            {"events": [[]]},
            {"events": [{"id": "", "date": "2026-08-01"}]},
            {"events": [{"id": "evt-1", "date": ""}]},
        ],
    )
    def test_invalid_archive_shape_fails_without_replacement(self, tmp_path, stored):
        path = tmp_path / "archive-2026.json"
        before = json.dumps(stored).encode()
        path.write_bytes(before)

        with pytest.raises(ValueError, match=str(path)):
            update_archive(
                [make_event("evt-new", "New", "2026-08-01")],
                archive_dir=str(tmp_path),
                today="2026-07-02",
            )

        assert path.read_bytes() == before

    def test_duplicate_stored_ids_are_rejected(self, tmp_path):
        path = tmp_path / "archive-2026.json"
        duplicate = make_event("evt-1", "Old", "2026-08-01")
        before = json.dumps({"events": [duplicate, duplicate]}).encode()
        path.write_bytes(before)

        with pytest.raises(ValueError, match="Duplicate archive event id"):
            update_archive(
                [make_event("evt-new", "New", "2026-08-02")],
                archive_dir=str(tmp_path),
                today="2026-07-02",
            )

        assert path.read_bytes() == before

    def test_unreadable_archive_does_not_become_empty(
        self, monkeypatch, tmp_path
    ):
        path = tmp_path / "archive-2026.json"
        path.write_bytes(b"historical bytes")

        def fail_read(*args, **kwargs):
            raise PermissionError(f"cannot read {path}")

        monkeypatch.setattr(pipeline, "read_json", fail_read)
        with pytest.raises(PermissionError, match=str(path)):
            update_archive(
                [make_event("evt-new", "New", "2026-08-01")],
                archive_dir=str(tmp_path),
                today="2026-07-02",
            )

        assert path.read_bytes() == b"historical bytes"

    def test_replacement_failure_leaves_archive_byte_identical(
        self, monkeypatch, tmp_path
    ):
        old = make_event("evt-old", "Old", "2026-08-01")
        path = tmp_path / "archive-2026.json"
        before = json.dumps({"events": [old]}, separators=(",", ":")).encode()
        path.write_bytes(before)

        def fail_write(*args, **kwargs):
            raise OSError("replace failed")

        monkeypatch.setattr(pipeline, "write_json_atomic", fail_write)
        with pytest.raises(OSError, match="replace failed"):
            update_archive(
                [make_event("evt-new", "New", "2026-08-02")],
                archive_dir=str(tmp_path),
                today="2026-07-02",
            )

        assert path.read_bytes() == before


def test_publish_payload_uses_final_events_and_generated_date(tmp_path):
    output_path = tmp_path / "published" / "events.json"
    archive_dir = tmp_path / "archives"
    events = [
        make_event("evt-dec", "Décember Show", "2026-12-30"),
        make_event("evt-jan", "January Show", "2027-01-02"),
    ]
    payload = {"generated": "2026-12-20", "events": events}

    publish_payload(
        payload,
        output_path=str(output_path),
        archive_dir=str(archive_dir),
    )

    published = output_path.read_text()
    assert json.loads(published) == payload
    assert "Décember Show" in published
    assert '\n  "events": [' in published
    for year in ("2026", "2027"):
        archive = load_archive(archive_dir, year)
        assert archive["events"][0]["first_seen"] == "2026-12-20"


def test_publisher_replacement_failure_preserves_previous_events(
    monkeypatch, tmp_path
):
    output_path = tmp_path / "published" / "events.json"
    output_path.parent.mkdir()
    output_path.write_bytes(b"previous complete publication")
    archive_dir = tmp_path / "archives"
    real_write = pipeline.write_json_atomic

    def fail_events(path, value, **kwargs):
        if str(path) == str(output_path):
            raise OSError("replace failed")
        return real_write(path, value, **kwargs)

    monkeypatch.setattr(pipeline, "write_json_atomic", fail_events)
    with pytest.raises(OSError, match="replace failed"):
        publish_payload(
            {"generated": "2026-07-02", "events": []},
            output_path=str(output_path),
            archive_dir=str(archive_dir),
        )

    assert output_path.read_bytes() == b"previous complete publication"
    assert not list(archive_dir.iterdir())
