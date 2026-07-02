"""Tests for ForbesLibraryScraper — LibCal's escaping is broken, so the regexes
must survive BOTH well-formed and bracket-stripped description variants."""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scrapers.forbes_library import DATE_FIELD, TIME_FIELD, ForbesLibraryScraper

WELL_FORMED = (
    "<strong>Date:</strong> Friday, June 12, 2026<br/> "
    "<strong>Time:</strong> 10:30am - 11:00am<br/> "
    "<strong>Location:</strong> Community Room<br/>"
)
# What LibCal actually emits for many items — angle brackets stripped entirely
MANGLED = (
    "strongDate:/strong Friday, June 12, 2026br/ "
    "strongTime:/strong 3:30pm - 4:30pmbr/ strongLocation:/strong Watson Roombr/"
)
ALL_DAY = (
    "<strong>Date:</strong> Friday, June 12, 2026<br/> "
    "<strong>Time:</strong> All Day Event<br/>"
)

RSS_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>Forbes</title>
<item><title>Toddler Storytime</title>
<link>https://forbeslibrary.libcal.com/event/1</link>
<description>{well}</description></item>
<item><title>Book Group</title>
<link>https://forbeslibrary.libcal.com/event/2</link>
<description>{mangled}</description></item>
<item><title>Puppet Parade</title>
<link>https://forbeslibrary.libcal.com/event/3</link>
<description>{allday}</description></item>
</channel></rss>""".format(well=WELL_FORMED, mangled=MANGLED, allday=ALL_DAY)


class TestRegexes:
    def test_date_matches_well_formed(self):
        assert DATE_FIELD.search(WELL_FORMED).group(1) == "Friday, June 12, 2026"

    def test_date_matches_mangled(self):
        assert DATE_FIELD.search(MANGLED).group(1) == "Friday, June 12, 2026"

    def test_time_matches_well_formed(self):
        m = TIME_FIELD.search(WELL_FORMED)
        assert (m.group(1), m.group(2)) == ("10:30am", "11:00am")

    def test_time_matches_mangled(self):
        m = TIME_FIELD.search(MANGLED)
        assert (m.group(1), m.group(2)) == ("3:30pm", "4:30pm")

    def test_all_day_has_no_time_match(self):
        assert TIME_FIELD.search(ALL_DAY) is None


class TestForbesScraper:
    def _fetch(self):
        scraper = ForbesLibraryScraper()
        mock_resp = MagicMock()
        mock_resp.content = RSS_TEMPLATE.encode()
        mock_resp.raise_for_status = MagicMock()
        with patch("scrapers.forbes_library.requests.get", return_value=mock_resp):
            return scraper.fetch()

    def test_all_three_variants_parse(self):
        events = self._fetch()
        assert len(events) == 3

    def test_mangled_item_gets_correct_times(self):
        events = self._fetch()
        book_group = next(e for e in events if e.title == "Book Group")
        assert book_group.date == "2026-06-12"
        assert book_group.time == "3:30 PM"
        assert book_group.end_time == "4:30 PM"

    def test_all_day_item_has_empty_time(self):
        events = self._fetch()
        parade = next(e for e in events if e.title == "Puppet Parade")
        assert parade.time == ""
        assert parade.date == "2026-06-12"
