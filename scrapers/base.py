"""Base scraper class for Pioneer Valley Events."""

import hashlib
import html
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional

log = logging.getLogger("pipeline")

# The publication window, shared by the pipeline and any scraper that
# pre-filters (community.py, tribe_events.py): events from DAYS_PAST days ago
# through DAYS_FUTURE days out are kept. Change it here, nowhere else.
DAYS_PAST = 3
DAYS_FUTURE = 90


def event_time_key(ev: dict) -> tuple:
    """Chronological sort key for an event dict's 'time' field.

    All-day events (no/unparseable time) sort first. Never sort times as raw
    strings — "12:00 PM" < "9:00 AM" lexicographically.
    """
    raw = (ev.get("time") or "").strip()
    for fmt in ("%I:%M %p", "%I %p"):
        try:
            t = datetime.strptime(raw, fmt)
            return (1, t.hour * 60 + t.minute)
        except ValueError:
            continue
    return (0, 0)


@dataclass
class Event:
    title: str
    date: str          # YYYY-MM-DD
    venue: str
    town: str
    source: str
    category: str
    time: str = ""
    end_time: str = ""
    address: str = ""
    description: str = ""
    url: str = ""
    image_url: Optional[str] = None
    id: str = field(default="", init=False)

    def __post_init__(self):
        self.id = self._make_id()

    def _make_id(self):
        key = f"{self.source}-{self.date}-{self.title}"
        return "evt-" + hashlib.md5(key.encode()).hexdigest()[:10]

    def to_dict(self):
        d = asdict(self)
        # Move id to front
        return {"id": d.pop("id"), **d}


class BaseScraper(ABC):
    name: str = "base"
    url: str = ""
    town: str = ""
    # Set True on scrapers that call the Anthropic API; the pipeline pre-flight
    # aborts if any such scraper is selected and no API key is set.
    needs_api_key: bool = False

    def fetch(self) -> list[Event]:
        """Fetch and return normalized events. Catches all exceptions gracefully."""
        self.last_error: Optional[str] = None
        try:
            return self._fetch()
        except Exception as e:
            self.last_error = str(e)
            log.error("[%s] ERROR: %s", self.name, e)
            return []

    @abstractmethod
    def _fetch(self) -> list[Event]:
        ...

    # ---- helpers ----

    @staticmethod
    def clean(text: str) -> str:
        """Strip extra whitespace and decode HTML entities."""
        if not text:
            return ""
        text = html.unescape(text)
        return re.sub(r'\s+', ' ', text).strip()

    @staticmethod
    def normalize_date(raw: str) -> str:
        """Try to parse various date strings into YYYY-MM-DD. Returns '' on failure."""
        formats = [
            "%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y",
            "%A, %B %d, %Y", "%A, %b %d, %Y", "%d %B %Y",
            "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return ""

    @staticmethod
    def normalize_time(raw: str) -> str:
        """Convert time strings to 12-hour format. Returns raw on failure."""
        for fmt in ["%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p", "%I %p"]:
            try:
                return datetime.strptime(raw.strip(), fmt).strftime("%-I:%M %p")
            except ValueError:
                continue
        return raw.strip()
