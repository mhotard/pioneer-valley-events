"""Scraper for Forbes Library (Northampton) events — LibCal RSS feed."""

import logging
import re

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper, Event
from .jones_library import guess_category

log = logging.getLogger("pipeline")

# LibCal month view RSS (iid/cid found via forbeslibrary.org/events/)
RSS_URL = "https://forbeslibrary.libcal.com/rss.php?iid=1448&m=month&cid=228"

# Description format: "<strong>Date:</strong> Friday, June 12, 2026<br/>
#                      <strong>Time:</strong> 10:30am - 11:00am<br/> ..."
# LibCal's escaping is broken — many items lose their angle brackets entirely
# ("strongDate:/strong Friday, ...br/"), so match the date/time shapes directly.
DATE_FIELD = re.compile(r"Date:\D*?([A-Za-z]+, [A-Za-z]+ \d{1,2}, \d{4})")
TIME_FIELD = re.compile(
    r"Time:\D*?(\d{1,2}(?::\d{2})?\s*[ap]m)(?:\s*-\s*(\d{1,2}(?::\d{2})?\s*[ap]m))?",
    re.IGNORECASE,
)


class ForbesLibraryScraper(BaseScraper):
    name = "forbes-library"
    url = "https://forbeslibrary.org/events/"
    town = "Northampton"

    def _fetch(self) -> list[Event]:
        headers = {"User-Agent": "PioneerValleyEvents/1.0 (community aggregator)"}
        resp = requests.get(RSS_URL, headers=headers, timeout=20)
        resp.raise_for_status()

        # LibCal's RSS is not always well-formed XML, so use the lenient parser
        soup = BeautifulSoup(resp.content, "xml")
        events = []
        seen = set()

        for item in soup.find_all("item"):
            title = self.clean(item.title.get_text() if item.title else "")
            link = item.link.get_text(strip=True) if item.link else ""
            description = item.description.get_text() if item.description else ""
            if not title:
                continue

            m = DATE_FIELD.search(description)
            if not m:
                continue
            date_str = self.normalize_date(self.clean(m.group(1)))
            if not date_str:
                continue

            key = f"{title}|{date_str}"
            if key in seen:
                continue
            seen.add(key)

            # "All Day Event" simply doesn't match the time pattern
            time_str, end_time_str = "", ""
            m = TIME_FIELD.search(description)
            if m:
                time_str = self.normalize_time(m.group(1))
                end_time_str = self.normalize_time(m.group(2)) if m.group(2) else ""

            events.append(Event(
                title=title,
                date=date_str,
                time=time_str,
                end_time=end_time_str,
                venue="Forbes Library",
                address="20 West St, Northampton, MA 01060",
                town=self.town,
                description="",  # RSS description just repeats date/time
                url=link,
                image_url=None,
                category=guess_category(title),
                source=self.name,
            ))

        log.debug("[%s] Found %d events", self.name, len(events))
        return events
