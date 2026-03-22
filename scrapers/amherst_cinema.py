"""Scraper for Amherst Cinema (amherstcinema.org) — Drupal 7 Views structure."""

import re
from datetime import date, datetime

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper, Event

BASE_URL = "https://amherstcinema.org"
LISTING_URL = f"{BASE_URL}/coming-soon"


def parse_date(raw: str) -> str:
    """
    Parse dates like 'Sun, 3/22' or 'Fri, 3/27' into YYYY-MM-DD.
    Assumes current or next year based on whether the date has passed.
    """
    m = re.search(r'(\d{1,2})/(\d{1,2})', raw)
    if not m:
        return ""
    month, day = int(m.group(1)), int(m.group(2))
    today = date.today()
    year = today.year
    try:
        d = date(year, month, day)
        if d < today - __import__('datetime').timedelta(days=3):
            d = date(year + 1, month, day)
        return d.isoformat()
    except ValueError:
        return ""


def parse_time(raw: str) -> str:
    """Convert '1:30 pm' → '1:30 PM'."""
    raw = raw.strip()
    for fmt in ["%I:%M %p", "%I:%M%p", "%I %p"]:
        try:
            return datetime.strptime(raw.upper(), fmt.upper()).strftime("%-I:%M %p")
        except ValueError:
            continue
    return raw.upper()


class AmherstCinemaScraper(BaseScraper):
    name = "amherst-cinema"
    town = "Amherst"

    def _fetch(self) -> list[Event]:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}  # noqa: E501
        resp = requests.get(LISTING_URL, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        events = []
        seen = set()

        # Each film is in a .col-xs-8 block inside the show_event view
        for film_block in soup.select(".col-xs-8"):
            title_el = film_block.select_one(".title a")
            if not title_el:
                continue

            title = self.clean(title_el.get_text())
            href = title_el.get("href", "")
            film_url = BASE_URL + href if href.startswith("/") else href

            desc_el = film_block.select_one(".body")
            description = self.clean(desc_el.get_text()[:500]) if desc_el else ""

            # Image is in the sibling .col-xs-4
            img_url = None
            col4 = film_block.find_previous_sibling("div", class_="col-xs-4")
            if not col4:
                # Try parent approach
                parent = film_block.parent
                col4 = parent.find("div", class_="col-xs-4") if parent else None
            if col4:
                img_el = col4.select_one("img")
                if img_el:
                    img_url = img_el.get("src")

            # Each showtime is a .views-row inside .times
            for row in film_block.select(".times .views-row"):
                date_el = row.select_one(".date")
                time_el = row.select_one(".time .date-display-single")

                if not date_el:
                    continue

                date_str = parse_date(date_el.get_text())
                if not date_str:
                    continue

                time_str = parse_time(time_el.get_text()) if time_el else ""

                # Showtime ticket link (optional)
                ticket_el = row.select_one(".time a")
                event_url = ticket_el["href"] if ticket_el else film_url

                key = f"{title}|{date_str}|{time_str}"
                if key in seen:
                    continue
                seen.add(key)

                events.append(Event(
                    title=title,
                    date=date_str,
                    time=time_str,
                    venue="Amherst Cinema",
                    address="28 Amity St, Amherst, MA 01002",
                    town=self.town,
                    description=description,
                    url=event_url,
                    image_url=img_url,
                    category="film",
                    source=self.name,
                ))

        print(f"[{self.name}] Found {len(events)} events")
        return events
