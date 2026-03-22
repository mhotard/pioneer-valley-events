"""Base scraper class for Pioneer Valley Events."""

import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Optional


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
    town: str = ""

    def fetch(self) -> list[Event]:
        """Fetch and return normalized events. Catches all exceptions gracefully."""
        try:
            return self._fetch()
        except Exception as e:
            print(f"[{self.name}] ERROR: {e}")
            return []

    @abstractmethod
    def _fetch(self) -> list[Event]:
        ...

    # ---- helpers ----

    @staticmethod
    def clean(text: str) -> str:
        """Strip extra whitespace and HTML entities."""
        if not text:
            return ""
        text = re.sub(r'\s+', ' ', text).strip()
        text = text.replace('&amp;', '&').replace('&nbsp;', ' ')
        text = text.replace('&#8217;', "'").replace('&#8220;', '"').replace('&#8221;', '"')
        text = text.replace('&ldquo;', '"').replace('&rdquo;', '"').replace('&rsquo;', "'")
        return text

    @staticmethod
    def normalize_date(raw: str) -> str:
        """Try to parse various date strings into YYYY-MM-DD. Returns '' on failure."""
        from datetime import datetime
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
        from datetime import datetime
        for fmt in ["%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p", "%I %p"]:
            try:
                return datetime.strptime(raw.strip(), fmt).strftime("%-I:%M %p")
            except ValueError:
                continue
        return raw.strip()
