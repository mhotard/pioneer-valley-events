"""Tests for BaseScraper helpers and the Event dataclass."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scrapers.base import BaseScraper, Event

VALID_CATEGORIES = {
    "music", "arts", "film", "comedy", "community",
    "academia", "family", "food", "outdoor", "festival",
}


# ---- Concrete subclass for testing abstract methods ----

class DummyScraper(BaseScraper):
    name = "dummy"
    town = "Northampton"

    def _fetch(self):
        return []


scraper = DummyScraper()


# ---- Event dataclass ----

class TestEvent:
    def _e(self, title="Test", venue="V", town="T", source="src"):
        return Event(
            title=title, date="2026-04-01", venue=venue, town=town, source=source, category="music"
        )

    def test_id_generated_on_creation(self):
        e = self._e()
        assert e.id.startswith("evt-")
        assert len(e.id) == 14  # "evt-" + 10 hex chars

    def test_same_inputs_produce_same_id(self):
        assert self._e().id == self._e().id

    def test_different_inputs_produce_different_id(self):
        assert self._e("Show A").id != self._e("Show B").id

    def test_to_dict_contains_required_fields(self):
        d = self._e(venue="Venue", town="Northampton", source="test").to_dict()
        for field in ["id", "title", "date", "venue", "town", "source", "category"]:
            assert field in d, f"Missing field: {field}"

    def test_to_dict_id_is_first_key(self):
        keys = list(self._e().to_dict().keys())
        assert keys[0] == "id"


# ---- BaseScraper helpers ----

class TestClean:
    def test_strips_whitespace(self):
        assert scraper.clean("  hello   world  ") == "hello world"

    def test_collapses_newlines(self):
        assert scraper.clean("hello\n\nworld") == "hello world"

    def test_decodes_amp(self):
        assert "&" in scraper.clean("Jazz &amp; Blues")

    def test_empty_string(self):
        assert scraper.clean("") == ""

    def test_none_returns_empty(self):
        assert scraper.clean(None) == ""


class TestNormalizeDate:
    def test_iso_format(self):
        assert scraper.normalize_date("2026-04-01") == "2026-04-01"

    def test_slash_format(self):
        assert scraper.normalize_date("04/01/2026") == "2026-04-01"

    def test_long_format(self):
        assert scraper.normalize_date("April 1, 2026") == "2026-04-01"

    def test_iso_datetime(self):
        assert scraper.normalize_date("2026-04-01T19:00:00") == "2026-04-01"

    def test_invalid_returns_empty(self):
        assert scraper.normalize_date("not a date") == ""


class TestNormalizeTime:
    def test_24hr_to_12hr(self):
        assert scraper.normalize_time("19:30") == "7:30 PM"

    def test_midnight(self):
        assert scraper.normalize_time("00:00") == "12:00 AM"

    def test_noon(self):
        assert scraper.normalize_time("12:00") == "12:00 PM"

    def test_already_12hr(self):
        result = scraper.normalize_time("7:30 PM")
        assert "7:30" in result and "PM" in result


# ---- Scraper contract ----

class TestScraperContract:
    """Every scraper must have name, town, and return Event objects."""

    def test_dummy_has_name(self):
        assert DummyScraper.name != "base"
        assert isinstance(DummyScraper.name, str)
        assert len(DummyScraper.name) > 0

    def test_dummy_has_town(self):
        assert isinstance(DummyScraper.town, str)
        assert len(DummyScraper.town) > 0

    def test_fetch_returns_list(self):
        result = scraper.fetch()
        assert isinstance(result, list)

    def test_fetch_never_raises(self):
        """fetch() must catch all exceptions and return []."""
        class BrokenScraper(BaseScraper):
            name = "broken"
            town = "Nowhere"
            def _fetch(self):
                raise RuntimeError("boom")

        result = BrokenScraper().fetch()
        assert result == []
