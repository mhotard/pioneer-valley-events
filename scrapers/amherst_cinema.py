"""Scraper for Amherst Cinema (amherstcinema.org)."""

import re
import requests
from bs4 import BeautifulSoup
from .base import BaseScraper, Event

BASE_URL = "https://amherstcinema.org"
CALENDAR_URL = f"{BASE_URL}/films"


class AmherstCinemaScraper(BaseScraper):
    name = "amherst-cinema"
    town = "Amherst"

    def _fetch(self) -> list[Event]:
        headers = {"User-Agent": "PioneerValleyEvents/1.0 (community aggregator)"}
        resp = requests.get(CALENDAR_URL, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        events = []
        seen = set()

        # Amherst Cinema uses a movie listing grid; each film may have multiple showtimes
        for film in soup.select(".film-item, .movie-item, article.film, .views-row"):
            try:
                title_el = film.select_one("h2, h3, .film-title, .title")
                if not title_el:
                    continue
                title = self.clean(title_el.get_text())
                if not title:
                    continue

                link_el = film.select_one("a[href]")
                href = link_el["href"] if link_el else ""
                if href and href.startswith("/"):
                    href = BASE_URL + href

                img_el = film.select_one("img")
                img = img_el.get("src", "") if img_el else None

                desc_el = film.select_one(".synopsis, .description, p")
                desc = self.clean(desc_el.get_text()[:400]) if desc_el else ""

                # Showtimes
                showtime_els = film.select(".showtime, .show-time, time, .date-time")
                if not showtime_els:
                    # Try to scrape detail page for showtimes
                    showtimes = self._scrape_showtimes(href, headers)
                else:
                    showtimes = []
                    for el in showtime_els:
                        raw = el.get("datetime", el.get_text())
                        if "T" in raw:
                            date = self.normalize_date(raw[:10])
                            time = raw[11:16]  # HH:MM
                        else:
                            date = self.normalize_date(raw)
                            time = ""
                        if date:
                            showtimes.append((date, time))

                if not showtimes:
                    # No dates found, skip
                    continue

                for date, time in showtimes:
                    key = f"{title}-{date}-{time}"
                    if key in seen:
                        continue
                    seen.add(key)

                    events.append(Event(
                        title=title,
                        date=date,
                        time=self.normalize_time(time) if time else "",
                        venue="Amherst Cinema",
                        address="28 Amity St, Amherst, MA 01002",
                        town=self.town,
                        description=desc,
                        url=href,
                        image_url=img or None,
                        category="film",
                        source=self.name,
                    ))

            except Exception as e:
                print(f"[{self.name}] Skipping film: {e}")
                continue

        print(f"[{self.name}] Found {len(events)} events")
        return events

    def _scrape_showtimes(self, url: str, headers: dict) -> list[tuple]:
        """Fetch a film detail page and extract showtime dates."""
        if not url:
            return []
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            showtimes = []
            for el in soup.select("time, .showtime, .date"):
                raw = el.get("datetime", el.get_text())
                if "T" in raw:
                    date = self.normalize_date(raw[:10])
                    time_part = raw[11:16]
                else:
                    date = self.normalize_date(raw)
                    time_part = ""
                if date:
                    showtimes.append((date, time_part))
            return showtimes
        except Exception:
            return []
