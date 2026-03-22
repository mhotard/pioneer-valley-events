"""
Data quality tests — validates that events.json meets the schema.
Run against the live file before deploying.
"""

import json
import os
import re

import pytest

EVENTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "docs", "data", "events.json"
)

VALID_CATEGORIES = {
    "music", "arts", "film", "comedy", "community",
    "academia", "family", "food", "outdoor", "festival",
}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@pytest.fixture(scope="module")
def events():
    with open(EVENTS_PATH) as f:
        data = json.load(f)
    return data.get("events", [])


def test_events_file_exists():
    assert os.path.exists(EVENTS_PATH), f"events.json not found at {EVENTS_PATH}"


def test_events_is_list(events):
    assert isinstance(events, list)


@pytest.mark.parametrize("field", ["id", "title", "date", "venue", "town", "category", "source"])
def test_required_fields_present(events, field):
    for e in events:
        assert field in e and e[field], f"Event missing '{field}': {e.get('title', '?')}"


def test_all_dates_valid_format(events):
    for e in events:
        assert DATE_RE.match(e["date"]), f"Bad date format '{e['date']}' in '{e['title']}'"


def test_all_categories_valid(events):
    for e in events:
        assert e["category"] in VALID_CATEGORIES, (
            f"Invalid category '{e['category']}' in '{e['title']}'"
        )


def test_no_duplicate_ids(events):
    ids = [e["id"] for e in events]
    assert len(ids) == len(set(ids)), "Duplicate event IDs found"


def test_no_empty_titles(events):
    for e in events:
        assert e["title"].strip(), f"Empty title in event id {e['id']}"


def test_towns_are_strings(events):
    for e in events:
        assert isinstance(e["town"], str) and e["town"].strip(), (
            f"Bad town in '{e['title']}'"
        )
