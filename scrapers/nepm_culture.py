"""Scraper for NEPM Culture to Do — weekly Wednesday newsletter."""

import logging
import re

from bs4 import BeautifulSoup

from .base import BROWSER_UA, BaseScraper, Event
from .claude_scraper import _clean_html, _dicts_to_events, _extract_events

log = logging.getLogger("pipeline")

LISTING_URL = "https://www.nepm.org/culture-to-do"
# Matches hrefs like /culture-to-do/2026-04-29/culture-to-do-april-29-2026
EDITION_PATTERN = re.compile(r"nepm\.org/culture-to-do/(\d{4}-\d{2}-\d{2})/")


class NEPMCultureScraper(BaseScraper):
    name = "nepm-culture"
    url = LISTING_URL
    town = "Pioneer Valley"
    needs_api_key = True  # uses claude_scraper._extract_events
    user_agent = BROWSER_UA

    def _fetch(self) -> list[Event]:
        resp = self.get(LISTING_URL)
        soup = BeautifulSoup(resp.text, "html.parser")
        editions = {}
        for a in soup.find_all("a", href=EDITION_PATTERN):
            m = EDITION_PATTERN.search(a["href"])
            if m:
                date_str = m.group(1)
                editions[date_str] = a["href"]

        if not editions:
            log.warning("[nepm-culture] No edition links found on listing page")
            return []

        latest_date = max(editions)
        latest_url = editions[latest_date]
        log.debug("[nepm-culture] Most recent edition: %s  %s", latest_date, latest_url)

        resp2 = self.get(latest_url)
        cleaned = _clean_html(resp2.text)
        dicts = _extract_events(cleaned, "Various Pioneer Valley Venues", self.town, self.name)
        events = _dicts_to_events(dicts, self.name, "Various Pioneer Valley Venues", self.town)

        log.debug("[nepm-culture] Found %d events", len(events))
        return events
