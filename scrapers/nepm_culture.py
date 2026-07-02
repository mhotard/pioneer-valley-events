"""Scraper for NEPM Culture to Do — weekly Wednesday newsletter."""

import logging
import re

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper, Event
from .claude_scraper import BROWSER_UA, _clean_html, _dicts_to_events, _extract_events

log = logging.getLogger("pipeline")

LISTING_URL = "https://www.nepm.org/culture-to-do"
# Matches hrefs like /culture-to-do/2026-04-29/culture-to-do-april-29-2026
EDITION_PATTERN = re.compile(r"nepm\.org/culture-to-do/(\d{4}-\d{2}-\d{2})/")


class NEPMCultureScraper(BaseScraper):
    name = "nepm-culture"
    url = LISTING_URL
    town = "Pioneer Valley"
    needs_api_key = True  # uses claude_scraper._extract_events

    def _fetch(self) -> list[Event]:
        headers = {"User-Agent": BROWSER_UA}

        resp = requests.get(LISTING_URL, headers=headers, timeout=20)
        resp.raise_for_status()

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

        resp2 = requests.get(latest_url, headers=headers, timeout=20)
        resp2.raise_for_status()

        cleaned = _clean_html(resp2.text)
        dicts = _extract_events(cleaned, "Various Pioneer Valley Venues", self.town, self.name)
        events = _dicts_to_events(dicts, self.name, "Various Pioneer Valley Venues", self.town)

        log.debug("[nepm-culture] Found %d events", len(events))
        return events
