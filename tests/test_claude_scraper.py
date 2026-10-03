"""Tests for ClaudeHTMLScraper, ClaudePlaywrightScraper, and helpers."""

import json
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

from scrapers import claude_scraper
from scrapers.claude_scraper import (
    ClaudeHTMLScraper,
    _clean_html,
    _dicts_to_events,
    _parse_json_array,
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


# ---- _parse_json_array ----

class TestParseJsonArray:
    def test_parses_valid_json(self):
        assert _parse_json_array(json.dumps(SAMPLE_DICTS)) == SAMPLE_DICTS

    def test_strips_markdown_fences(self):
        fenced = f"```json\n{json.dumps(SAMPLE_DICTS)}\n```"
        assert _parse_json_array(fenced) == SAMPLE_DICTS

    def test_salvages_truncated_array(self):
        # Simulate hitting max_tokens mid-way through the second object
        full = json.dumps(SAMPLE_DICTS)
        truncated = full[: full.index('"Comedy Show"') + 5]
        result = _parse_json_array(truncated)
        assert len(result) == 1
        assert result[0]["title"] == "Jazz Night"

    def test_salvages_with_leading_text(self):
        raw = "Here are the events:\n" + json.dumps(SAMPLE_DICTS)[:-20]
        result = _parse_json_array(raw)
        assert len(result) == 1

    def test_raises_on_garbage(self):
        with pytest.raises(ValueError):
            _parse_json_array("not valid json")


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
            patch("scrapers.base.requests.get", return_value=mock_response),
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
            "scrapers.base.requests.get",
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
            patch("scrapers.base.requests.get", return_value=mock_response),
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
            patch("scrapers.base.requests.get", return_value=mock_response),
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


# ---- call_haiku / resolve_api_key ----

class TestCallHaiku:
    @staticmethod
    def _message(text="[]", stop_reason="end_turn"):
        message = MagicMock()
        message.content = [MagicMock(text=text)]
        message.stop_reason = stop_reason
        return message

    def test_warns_with_label_when_output_is_truncated(self, caplog):
        with patch("scrapers.claude_scraper._get_client") as mock_client_fn:
            mock_client_fn.return_value.messages.create.return_value = self._message(
                '[{"title": "x"', stop_reason="max_tokens"
            )
            with caplog.at_level("WARNING", logger="pipeline"):
                text = claude_scraper.call_haiku("prompt", label="my-source", retries=1)

        assert text == '[{"title": "x"'
        assert any("my-source" in r.message and "max_tokens" in r.message for r in caplog.records)

    def test_single_attempt_raises_without_sleeping(self):
        with (
            patch("scrapers.claude_scraper._get_client") as mock_client_fn,
            patch("scrapers.claude_scraper.time.sleep") as sleep,
        ):
            mock_client_fn.return_value.messages.create.side_effect = RuntimeError("429")
            with pytest.raises(RuntimeError, match="429"):
                claude_scraper.call_haiku("prompt", retries=1)

        sleep.assert_not_called()

    def test_retries_with_backoff_then_succeeds(self):
        message = self._message("[1]")
        with (
            patch("scrapers.claude_scraper._get_client") as mock_client_fn,
            patch("scrapers.claude_scraper.time.sleep") as sleep,
        ):
            mock_client_fn.return_value.messages.create.side_effect = [
                RuntimeError("first"), RuntimeError("second"), message,
            ]
            assert claude_scraper.call_haiku("prompt", retries=3) == "[1]"

        assert [call.args[0] for call in sleep.call_args_list] == [20, 60]
        create = mock_client_fn.return_value.messages.create
        assert create.call_args.kwargs["model"] == claude_scraper.HAIKU_MODEL


class TestResolveApiKey:
    def test_pioneer_key_wins(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY_PIONEER", "pioneer")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "generic")
        assert claude_scraper.resolve_api_key() == "pioneer"

    def test_falls_back_to_generic_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY_PIONEER", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "generic")
        assert claude_scraper.resolve_api_key() == "generic"

    def test_none_when_unset(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY_PIONEER", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert claude_scraper.resolve_api_key() is None


# ---- Extracted-detail validation (no network/model calls) ----

@pytest.mark.parametrize("raw,valid", [
    ("2024-02-29", True), ("2000-02-29", True), ("2026-02-28", True),
    (" 2026-04-30 \n", True), ("2026-12-31", True),
    ("2026-02-29", False), ("1900-02-29", False), ("2026-04-31", False),
    ("2026-13-01", False), ("2026-00-01", False), ("2026-01-00", False),
    ("0000-01-01", False), ("2026-1-01", False), ("2026-01-01extra", False),
    (None, False), (20260411, False),
])
def test_actual_calendar_dates_and_whitespace(raw, valid):
    counts = {}
    events = _dicts_to_events([{**SAMPLE_DICTS[0], "date": raw}], "src", "Venue", "Town",
                             rejected_counts=counts)
    assert bool(events) == valid
    if valid:
        assert events[0].date == raw.strip()
        assert counts == {}
    else:
        assert counts == {"invalid_date": 1}


@pytest.mark.parametrize("raw,expected", [
    ("7:30 PM", "7:30 PM"), (" 07:30pm ", "7:30 PM"), ("7 PM", "7:00 PM"),
    ("00:00", "12:00 AM"), ("12:00 AM", "12:00 AM"), ("12:00 PM", "12:00 PM"),
    ("23:59", "11:59 PM"), ("19:30:00", "7:30 PM"),
    (None, ""), ("", ""), ("TBA", ""), ("all day", ""), ("midnight-ish", ""),
    ("24:00", ""), ("0:00 PM", ""), ("13:00 PM", ""), ("7:99 PM", ""),
    ("7:30 PM - 9:00 PM", ""), (0, ""), (False, ""),
])
def test_optional_times_never_invent_midnight(raw, expected):
    events = _dicts_to_events([{**SAMPLE_DICTS[0], "time": raw, "end_time": raw}],
                             "src", "Venue", "Town")
    assert len(events) == 1
    assert events[0].time == expected
    assert events[0].end_time == expected


@pytest.mark.parametrize("raw,valid", [
    ("https://example.test/event?q=1#details", True), ("HTTP://example.test/event", True),
    ("  https://example.test/event  ", True), ("http://localhost:8000/event", True),
    ("https://[::1]/event", True), ("", True), (None, True), ("  ", True),
    ("javascript:alert(1)", False), ("data:text/html,hello", False),
    ("file:///tmp/event", False), ("mailto:test@example.test", False),
    ("//example.test/event", False), ("/event", False), ("https:", False),
    ("https://", False), ("https://user:password@example.test/event", False),
    ("https://@example.test/event", False), ("https://example.test:99999/event", False),
    ("https://exa mple.test/event", False), ("https://example.test/line\nbreak", False),
    ("https://example.test/\x00event", False), ("https://example.test\\event", False),
    ("https://./event", False), ("https://%zz.test/event", False),
    ("https://<bad>.test/event", False), ("https://[::1]extra/event", False), (42, False),
])
def test_extracted_links_are_optional_absolute_http_only(raw, valid):
    counts = {}
    events = _dicts_to_events([{**SAMPLE_DICTS[0], "url": raw}], "src", "Venue", "Town",
                             rejected_counts=counts)
    assert bool(events) == valid
    if valid:
        assert events[0].url == (raw.strip() if isinstance(raw, str) else "")
        assert counts == {}
    else:
        assert counts == {"unsafe_url": 1}


def test_valid_payload_keeps_ids_order_and_category_policy():
    events = _dicts_to_events(SAMPLE_DICTS, "test-source", "Test Venue", "Northampton")
    assert [event.id for event in events] == ["evt-7b581d1fca", "evt-c0cc4e6dde"]
    assert [event.title for event in events] == ["Jazz Night", "Comedy Show"]
    assert events[0].to_dict() == {
        "id": "evt-7b581d1fca", "title": "Jazz Night", "date": "2026-04-11",
        "time": "8:00 PM", "end_time": "", "venue": "Test Venue", "address": "",
        "town": "Northampton", "description": "An evening of jazz standards.",
        "url": "https://example.com/jazz", "image_url": None, "category": "music",
        "source": "test-source",
    }
    unknown_category = _dicts_to_events([{**SAMPLE_DICTS[0], "category": "unrecognized"}],
                                       "src", "Venue", "Town")
    assert unknown_category[0].category == "community"


def test_rejections_use_safe_reason_counts_and_missing_optional_fields_are_accepted():
    counts = {}
    events = _dicts_to_events([
        None, 42, {"title": None, "date": "2026-04-11"},
        {"title": "Private invalid date", "date": "2026-02-30"},
        {**SAMPLE_DICTS[0], "url": "javascript:private-value"},
        {"title": "Valid minimal", "date": "2026-04-11"},
    ], "src", "Venue", "Town", rejected_counts=counts, require_valid=True)
    assert counts == {"malformed_record": 2, "missing_title": 1, "invalid_date": 1, "unsafe_url": 1}
    assert [event.title for event in events] == ["Valid minimal"]
    assert events[0].time == events[0].url == events[0].description == ""
    assert events[0].category == "community"


@pytest.mark.parametrize("kind", [claude_scraper.ClaudeHTMLScraper,
                                  claude_scraper.ClaudePlaywrightScraper])
def test_all_invalid_extraction_sets_source_error_but_empty_is_healthy(monkeypatch, kind):
    scraper = kind("test", "https://example.test/events", "Venue", "Town")
    monkeypatch.setattr(scraper, "_get_html", lambda: SAMPLE_HTML)
    extract = MagicMock(side_effect=[[{"title": "Bad", "date": "2026-02-30"}], []])
    monkeypatch.setattr(claude_scraper, "_extract_events", extract)
    assert scraper.fetch() == []
    assert scraper.last_error == "Event extraction contained no valid records"
    assert scraper.last_rejected_counts == {"invalid_date": 1}
    assert scraper.fetch() == []
    assert scraper.last_error is None
    assert scraper.last_rejected_counts == {}
    assert extract.call_count == 2  # One extraction per requested fetch; no retries.


@pytest.mark.parametrize("envelope", [{}, {"title": "Bad"}, "unexpected", None, 42])
def test_non_array_extraction_is_a_source_error(monkeypatch, envelope):
    scraper = ClaudeHTMLScraper("test", "https://example.test/events", "Venue", "Town")
    monkeypatch.setattr(scraper, "_get_html", lambda: SAMPLE_HTML)
    monkeypatch.setattr(claude_scraper, "_extract_events", lambda *args: envelope)
    assert scraper.fetch() == []
    assert scraper.last_error == "Event extraction must be a JSON array"


@pytest.mark.parametrize("all_invalid", [True, False])
def test_nepm_shared_conversion_tracks_health_without_extra_requests(monkeypatch, all_invalid):
    from scrapers import nepm_culture

    scraper = nepm_culture.NEPMCultureScraper()
    responses = [MagicMock(text='<a href="https://www.nepm.org/culture-to-do/2026-04-01/edition">'
                               'Edition</a>'), MagicMock(text=SAMPLE_HTML)]
    get = MagicMock(side_effect=responses)
    rows = [{"title": "Bad", "date": "2026-02-30"}]
    if not all_invalid:
        rows += SAMPLE_DICTS
    monkeypatch.setattr(scraper, "get", get)
    extract = MagicMock(return_value=rows)
    monkeypatch.setattr(nepm_culture, "_extract_events", extract)
    events = scraper.fetch()
    assert len(events) == (0 if all_invalid else 2)
    assert bool(scraper.last_error) == all_invalid
    assert scraper.last_rejected_counts == {"invalid_date": 1}
    assert get.call_count == 2
    assert extract.call_count == 1


@pytest.mark.parametrize("all_invalid", [True, False])
def test_pipeline_reports_rejections_and_applies_existing_health(
    monkeypatch, tmp_path, all_invalid
):
    import logging
    from datetime import date

    import pipeline

    scraper = ClaudeHTMLScraper("test", "https://example.test/events", "Venue", "Town")
    monkeypatch.setattr(scraper, "_get_html", lambda: SAMPLE_HTML)
    rows = [{"title": "private-fixture-title", "date": "2026-02-30"}]
    if not all_invalid:
        rows += SAMPLE_DICTS
    monkeypatch.setattr(claude_scraper, "_extract_events", lambda *args: rows)
    monkeypatch.setattr(pipeline, "get_all_scrapers", lambda: [scraper])
    monkeypatch.setattr(pipeline, "setup_logging", lambda: (logging.getLogger("pipeline"), "test"))
    monkeypatch.setenv("ANTHROPIC_API_KEY_PIONEER", "private-fixture-key")
    publication = tmp_path / "published"
    output = publication / "events.json"
    publication.mkdir()
    output.write_text('{"generated":"2026-04-01","events":[]}')
    archive = publication / "archive-2026.json"
    archive.write_text('{"events":[]}')
    before = (output.read_bytes(), archive.read_bytes())
    report_path = tmp_path / "diagnostics" / "run-report.json"
    status = pipeline.main([], output_path=str(output), archive_dir=str(publication),
                           report_path=str(report_path), run_date=date(2026, 4, 1))
    report_text = report_path.read_text()
    report = json.loads(report_text)
    assert status == (1 if all_invalid else 0)
    assert report["sources"][0]["rejected_records"] == {"invalid_date": 1}
    assert report["sources"][0]["status"] == ("error" if all_invalid else "ok")
    assert "private-fixture-title" not in report_text
    assert "private-fixture-key" not in report_text
    if all_invalid:
        assert report["publication"] == "rejected"
        assert (output.read_bytes(), archive.read_bytes()) == before
    else:
        assert report["publication"] == "accepted"
        assert report["published_event_count"] == 2


def test_pipeline_diagnostic_rejection_counts_are_whitelisted(monkeypatch):
    import pipeline
    from tests.test_pipeline_orchestration import RUN_DATE, FakeScraper

    scraper = FakeScraper("test")
    scraper.last_rejected_counts = {
        "invalid_date": 2, "unsafe_url": "raw-private-fixture-value",
        "missing_title": True, "malformed_record": -1, "private-fixture-key": 100,
    }
    sources = [{"name": "test", "count": None, "status": "not_attempted"}]
    pipeline.run([scraper], previous_counts={}, run_date=RUN_DATE, source_report=sources)
    assert sources[0]["rejected_records"] == {"invalid_date": 2}
