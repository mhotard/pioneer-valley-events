"""Tests for pipeline transformation and source-health logic."""

import copy
import os

# Import the functions under test directly
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pipeline import (
    MIN_PREV_FOR_REGRESSION,
    SourceResult,
    api_key_present,
    deduplicate,
    filter_by_date,
    find_regressions,
    is_unhealthy,
    prepare_payload,
)

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

    def test_same_venue_spelled_differently_deduped(self):
        # Same event listed by two sources → deduplicated
        e1 = make_event("Jazz Night", FUTURE, venue="Iron Horse")
        e2 = make_event("Jazz Night", FUTURE, venue="Iron Horse Music Hall")
        result = deduplicate([e1, e2])
        assert len(result) == 1

    def test_same_title_at_genuinely_different_venues_kept(self):
        # Both libraries run "Toddler Storytime" — these are distinct events
        e1 = make_event("Toddler Storytime", FUTURE, venue="Jones Library")
        e2 = make_event("Toddler Storytime", FUTURE, venue="Forbes Library")
        result = deduplicate([e1, e2])
        assert len(result) == 2

    def test_aggregator_venue_still_merges(self):
        # An aggregator's "Various..." venue must not block cross-source dedup
        e1 = make_event("Jazz Night", FUTURE, venue="Iron Horse Music Hall")
        e2 = make_event("Jazz Night", FUTURE, venue="Various Pioneer Valley Venues")
        result = deduplicate([e1, e2])
        assert len(result) == 1

    def test_empty_venue_still_merges(self):
        e1 = make_event("Jazz Night", FUTURE, venue="Iron Horse Music Hall")
        e2 = make_event("Jazz Night", FUTURE, venue="")
        result = deduplicate([e1, e2])
        assert len(result) == 1


# ---- Date filter tests ----

class TestApiKeyPresent:
    def test_true_when_pioneer_key_set(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY_PIONEER", "sk-test")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert api_key_present() is True

    def test_true_when_fallback_key_set(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY_PIONEER", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        assert api_key_present() is True

    def test_false_when_no_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY_PIONEER", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert api_key_present() is False


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

    def test_fixed_date_boundaries_are_inclusive(self):
        run_date = date(2026, 7, 10)
        events = [
            make_event("Too Old", "2026-07-06"),
            make_event("Old Boundary", "2026-07-07"),
            make_event("Future Boundary", "2026-10-08"),
            make_event("Too New", "2026-10-09"),
        ]

        assert [e["title"] for e in filter_by_date(events, run_date=run_date)] == [
            "Old Boundary",
            "Future Boundary",
        ]

    def test_explicit_date_is_evaluated_per_call(self):
        event = make_event("Moving Window", "2026-07-01")

        assert filter_by_date([event], run_date=date(2026, 7, 4)) == [event]
        assert filter_by_date([event], run_date=date(2026, 7, 5)) == []


class TestPreparePayload:
    def test_filters_then_deduplicates_then_sorts_without_mutating_input(self):
        run_date = date(2026, 7, 10)
        events = [
            make_event("Jazz Night", "2026-07-11", description="short"),
            {
                **make_event(
                    "Jazz Night!",
                    "2026-07-11",
                    description="a much richer event description",
                ),
                "source": "other",
                "time": "7:00 PM",
            },
            {**make_event("No Time", "2026-07-11"), "time": ""},
            {**make_event("Morning", "2026-07-11"), "time": "9:00 AM"},
            {**make_event("Noon", "2026-07-11"), "time": "12:00 PM"},
            {**make_event("Midnight", "2026-07-11"), "time": "12:00 AM"},
            make_event("Outside Window", "2026-10-09"),
            make_event("Jazz Night", "2026-07-11", venue="Forbes Library"),
        ]
        original = copy.deepcopy(events)

        payload = prepare_payload(events, run_date=run_date)

        assert payload["generated"] == "2026-07-10"
        assert [event["title"] for event in payload["events"]] == [
            "No Time",
            "Midnight",
            "Morning",
            "Noon",
            "Jazz Night!",
            "Jazz Night",
        ]
        assert payload["events"][-2]["description"] == "a much richer event description"
        assert payload["events"][-1]["venue"] == "Forbes Library"
        assert events == original

    def test_equal_description_duplicate_keeps_first(self):
        first = make_event("Jazz Night", "2026-07-11", description="same")
        second = {
            **make_event("Jazz Night!", "2026-07-11", description="same"),
            "source": "other",
        }

        payload = prepare_payload([first, second], run_date=date(2026, 7, 10))

        assert payload["events"] == [first]


# ---- Yield-regression detection tests ----

class TestFindRegressions:
    # results tuples: (name, url, count, error)
    def test_productive_to_zero_flagged(self):
        results = [SourceResult("forbes-library", "u", 0, None)]
        prev = {"forbes-library": 154}
        assert find_regressions(results, prev) == [("forbes-library", 154)]

    def test_errored_source_not_flagged_as_regression(self):
        results = [SourceResult("forbes-library", "u", 0, "boom")]
        prev = {"forbes-library": 154}
        assert find_regressions(results, prev) == []

    def test_always_zero_source_not_flagged(self):
        # hawks-reed was 0 last run too — that's a known-OK ZERO, not a regression
        results = [SourceResult("hawks-reed", "u", 0, None)]
        prev = {"hawks-reed": 0}
        assert find_regressions(results, prev) == []

    def test_low_yield_source_not_flagged(self):
        # A source that only ever had a couple of events can hit 0 naturally
        results = [SourceResult("valley-arts-newsletter", "u", 0, None)]
        prev = {"valley-arts-newsletter": MIN_PREV_FOR_REGRESSION - 1}
        assert find_regressions(results, prev) == []

    def test_new_source_not_flagged(self):
        results = [SourceResult("brand-new", "u", 0, None)]
        assert find_regressions(results, {}) == []

    def test_productive_source_still_productive_not_flagged(self):
        results = [SourceResult("umass", "u", 12, None)]
        prev = {"umass": 20}
        assert find_regressions(results, prev) == []

    @staticmethod
    def _results(total, errors=0):
        return [
            SourceResult(
                name=f"source-{i}",
                url="u",
                count=0 if i < errors else 1,
                error="boom" if i < errors else None,
            )
            for i in range(total)
        ]

    def test_regression_threshold_is_inclusive_at_five(self):
        results = [SourceResult("low", "u", 0, None), SourceResult("boundary", "u", 0, None)]
        assert find_regressions(results, {"low": 4, "boundary": 5}) == [("boundary", 5)]

    def test_health_threshold_preserves_strict_greater_than(self):
        assert is_unhealthy(self._results(3, errors=1), []) is False
        assert is_unhealthy(self._results(3, errors=2), []) is True
        assert is_unhealthy(self._results(50, errors=17), []) is False
        assert is_unhealthy(self._results(50, errors=18), []) is True

    def test_mixed_errors_and_regressions_determine_health(self):
        results = self._results(3, errors=1)
        assert is_unhealthy(results, [("source-2", 5)]) is True

    def test_errored_source_is_not_counted_twice_if_also_listed_as_regression(self):
        results = self._results(3, errors=1)
        assert is_unhealthy(results, [("source-0", 5)]) is False

    def test_no_sources_is_not_unhealthy(self):
        assert is_unhealthy([], []) is False
