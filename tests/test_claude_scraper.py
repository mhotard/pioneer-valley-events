"""Tests for ClaudeHTMLScraper, ClaudePlaywrightScraper, and helpers."""

import json
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scrapers.claude_scraper import (
    ClaudeHTMLScraper,
    _clean_html,
    _dicts_to_events,
    load_claude_scrapers,
)

# ---- Sample data ----

SAMPLE_HTML = """
<html><body>
  <nav>Nav junk</nav>
  <main>
    <h2>Upcoming Events</h2>
    <div class="event">
      <h3>Jazz Night</h3>
      <p>Friday, April 11, 2026 at 8:00 PM</p>
      <p>An evening of jazz standards.</p>
    </div>
  </main>
  <script>alert('hi')</script>
  <footer>Footer junk</footer>
</body></html>
"""

SAMPLE_DICTS = [
    {
        "title": "Jazz Night",
        "date": "2026-04-11",
        "time": "8:00 PM",
        "end_time": "",
        "description": "An evening of jazz standards.",
        "url": "https://example.com/jazz",
        "category": "music",
    },
    {
        "title": "Comedy Show",
        "date": "2026-04-18",
        "time": "9:00 PM",
        "end_time": "",
        "description": "",
        "url": "",
        "category": "comedy",
    },
]


# ---- _clean_html ----

class TestCleanHtml:
    def test_removes_scripts(self):
        result = _clean_html(SAMPLE_HTML)
        assert "alert('hi')" not in result

    def test_removes_nav(self):
        result = _clean_html(SAMPLE_HTML)
        assert "Nav junk" not in result

    def test_removes_footer(self):
        result = _clean_html(SAMPLE_HTML)
        assert "Footer junk" not in result

    def test_keeps_main_content(self):
        result = _clean_html(SAMPLE_HTML)
        assert "Jazz Night" in result

    def test_respects_max_length(self):
        big_html = "<div>" + "x" * 100_000 + "</div>"
        result = _clean_html(big_html)
        assert len(result) <= 20_100  # slight buffer for tags


# ---- _dicts_to_events ----

class TestDictsToEvents:
    def test_converts_valid_dicts(self):
        events = _dicts_to_events(SAMPLE_DICTS, "test-source", "Test Venue", "Northampton")
        assert len(events) == 2

    def test_event_fields_populated(self):
        events = _dicts_to_events(SAMPLE_DICTS[:1], "test-source", "Test Venue", "Northampton")
        e = events[0]
        assert e.title == "Jazz Night"
        assert e.date == "2026-04-11"
        assert e.time == "8:00 PM"
        assert e.category == "music"
        assert e.source == "test-source"
        assert e.venue == "Test Venue"
        assert e.town == "Northampton"

    def test_skips_missing_title(self):
        bad = [{"date": "2026-04-11", "category": "music"}]
        events = _dicts_to_events(bad, "src", "Venue", "Town")
        assert len(events) == 0

    def test_skips_missing_date(self):
        bad = [{"title": "Event", "category": "music"}]
        events = _dicts_to_events(bad, "src", "Venue", "Town")
        assert len(events) == 0

    def test_truncates_long_description(self):
        d = [{**SAMPLE_DICTS[0], "description": "x" * 1000}]
        events = _dicts_to_events(d, "src", "Venue", "Town")
        assert len(events[0].description) <= 500

    def test_handles_malformed_dict_gracefully(self):
        bad = [None, 42, {"title": "Good", "date": "2026-04-11", "category": "music"}]
        events = _dicts_to_events(bad, "src", "Venue", "Town")
        assert len(events) == 1


# ---- ClaudeHTMLScraper ----

class TestClaudeHTMLScraper:
    def _make_scraper(self):
        return ClaudeHTMLScraper(
            name="test-html",
            url="https://example.com/events",
            venue="Test Venue",
            town="Northampton",
        )

    def test_has_name(self):
        s = self._make_scraper()
        assert s.name == "test-html"

    def test_has_town(self):
        s = self._make_scraper()
        assert s.town == "Northampton"

    def test_fetch_returns_events_from_haiku(self):
        scraper = self._make_scraper()

        mock_response = MagicMock()
        mock_response.text = SAMPLE_HTML
        mock_response.raise_for_status = MagicMock()

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=json.dumps(SAMPLE_DICTS))]

        with (
            patch("scrapers.claude_scraper.requests.get", return_value=mock_response),
            patch("scrapers.claude_scraper._get_client") as mock_client_fn,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_message
            mock_client_fn.return_value = mock_client

            events = scraper.fetch()

        assert len(events) == 2
        assert events[0].title == "Jazz Night"

    def test_fetch_returns_empty_on_http_error(self):
        scraper = self._make_scraper()
        with patch(
            "scrapers.claude_scraper.requests.get",
            side_effect=Exception("connection refused"),
        ):
            events = scraper.fetch()
        assert events == []

    def test_fetch_returns_empty_on_invalid_json(self):
        scraper = self._make_scraper()

        mock_response = MagicMock()
        mock_response.text = SAMPLE_HTML
        mock_response.raise_for_status = MagicMock()

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="not valid json")]

        with (
            patch("scrapers.claude_scraper.requests.get", return_value=mock_response),
            patch("scrapers.claude_scraper._get_client") as mock_client_fn,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_message
            mock_client_fn.return_value = mock_client

            events = scraper.fetch()

        assert events == []

    def test_fetch_strips_markdown_fences(self):
        scraper = self._make_scraper()
        fenced = f"```json\n{json.dumps(SAMPLE_DICTS)}\n```"

        mock_response = MagicMock()
        mock_response.text = SAMPLE_HTML
        mock_response.raise_for_status = MagicMock()

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=fenced)]

        with (
            patch("scrapers.claude_scraper.requests.get", return_value=mock_response),
            patch("scrapers.claude_scraper._get_client") as mock_client_fn,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_message
            mock_client_fn.return_value = mock_client

            events = scraper.fetch()

        assert len(events) == 2


# ---- load_claude_scrapers ----

class TestLoadClaudeScrapers:
    def test_loads_from_sources_json(self, tmp_path):
        config = {
            "sources": [
                {
                    "name": "test-html",
                    "url": "https://example.com",
                    "venue": "Test Venue",
                    "town": "Northampton",
                    "type": "html",
                },
                {
                    "name": "test-playwright",
                    "url": "https://example.com/js",
                    "venue": "JS Venue",
                    "town": "Amherst",
                    "type": "playwright",
                },
            ]
        }
        p = tmp_path / "sources.json"
        p.write_text(json.dumps(config))

        scrapers = load_claude_scrapers(str(p))
        assert len(scrapers) == 2
        assert scrapers[0].name == "test-html"
        assert scrapers[1].name == "test-playwright"

    def test_returns_empty_for_empty_sources(self, tmp_path):
        p = tmp_path / "sources.json"
        p.write_text(json.dumps({"sources": []}))
        assert load_claude_scrapers(str(p)) == []

    def test_html_type_creates_html_scraper(self, tmp_path):
        from scrapers.claude_scraper import ClaudeHTMLScraper

        config = {"sources": [
            {"name": "x", "url": "https://x.com", "venue": "X", "town": "Y", "type": "html"}
        ]}
        p = tmp_path / "sources.json"
        p.write_text(json.dumps(config))
        scrapers = load_claude_scrapers(str(p))
        assert isinstance(scrapers[0], ClaudeHTMLScraper)

    def test_playwright_type_creates_playwright_scraper(self, tmp_path):
        from scrapers.claude_scraper import ClaudePlaywrightScraper

        config = {"sources": [
            {"name": "x", "url": "https://x.com", "venue": "X", "town": "Y", "type": "playwright"}
        ]}
        p = tmp_path / "sources.json"
        p.write_text(json.dumps(config))
        scrapers = load_claude_scrapers(str(p))
        assert isinstance(scrapers[0], ClaudePlaywrightScraper)
