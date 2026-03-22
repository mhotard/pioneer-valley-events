"""
Claude-powered scrapers for Pioneer Valley Events.

ClaudeHTMLScraper  — fetches static HTML pages, sends to Haiku for extraction.
ClaudePlaywrightScraper — renders JS-heavy pages with Playwright, then Haiku extracts.

Both are configured via sources.json entries:
  {"name": "...", "url": "...", "venue": "...", "town": "...", "type": "html"|"playwright"}
"""

import json
import logging
import os
from typing import Optional

import requests
from anthropic import Anthropic
from bs4 import BeautifulSoup

from .base import BaseScraper, Event

log = logging.getLogger("pipeline")

_client: Optional[Anthropic] = None

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

EXTRACT_PROMPT = """\
You are an event data extractor. Extract all upcoming events from the HTML below.

Return a JSON array. Each element must have exactly these fields:
  title       — string, required
  date        — string, YYYY-MM-DD format, required
  time        — string, H:MM AM/PM, or ""
  end_time    — string, H:MM AM/PM, or ""
  description — string, max 400 chars, or ""
  url         — full URL to the event or ticket page, or ""
  category    — one of: music, arts, film, comedy, community, academia,
               family, food, outdoor, festival

Context:
  Venue: {venue}
  Town:  {town}
  Today: {today}  ← only include events on or after this date
  Year:  {year}   ← assume this year for dates that don't include a year

Rules:
  - Return ONLY valid JSON. No markdown fences, no explanation.
  - If no events are found, return [].
  - Dates must be YYYY-MM-DD.
  - Times must be H:MM AM/PM (e.g., "7:30 PM").
  - Skip events that have already passed.

HTML:
{html}"""

MAX_HTML_CHARS = 20_000  # ~5k tokens — enough for a full event listing page


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY_PIONEER") or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY_PIONEER environment variable is not set. "
                "Get a key at https://console.anthropic.com/"
            )
        _client = Anthropic(api_key=api_key)
    return _client


def _clean_html(html: str) -> str:
    """Strip scripts, styles, nav, footer — keep main content."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "header", "footer", "aside"]):
        tag.decompose()
    # Try to isolate the main content area
    main = soup.find("main") or soup.find("div", id="main") or soup.find("div", id="content")
    content = str(main) if main else str(soup.body or soup)
    return content[:MAX_HTML_CHARS]


def _extract_events(html: str, venue: str, town: str) -> list[dict]:
    """Call Haiku and return parsed list of event dicts."""
    from datetime import date

    today = date.today().isoformat()
    year = str(date.today().year)

    prompt = EXTRACT_PROMPT.format(
        venue=venue, town=town, today=today, year=year, html=html
    )

    client = _get_client()
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    return json.loads(raw)


def _dicts_to_events(dicts: list[dict], source_name: str, venue: str, town: str) -> list[Event]:
    """Convert raw dicts from Haiku into validated Event objects."""
    events = []
    for d in dicts:
        try:
            title = str(d.get("title", "")).strip()
            date_str = str(d.get("date", "")).strip()
            if not title or not date_str:
                continue

            events.append(Event(
                title=title,
                date=date_str,
                time=str(d.get("time", "")),
                end_time=str(d.get("end_time", "")),
                venue=venue,
                address="",
                town=town,
                description=str(d.get("description", ""))[:500],
                url=str(d.get("url", "")),
                image_url=None,
                category=str(d.get("category", "community")),
                source=source_name,
            ))
        except Exception as e:
            log.warning("[%s] Skipping malformed event dict: %s", source_name, e)
    return events


class ClaudeHTMLScraper(BaseScraper):
    """Fetches a static HTML page and uses Haiku to extract events."""

    def __init__(self, name: str, url: str, venue: str, town: str):
        self.name = name
        self.url = url
        self.venue = venue
        self.town = town

    def _fetch(self) -> list[Event]:
        headers = {"User-Agent": BROWSER_UA}
        resp = requests.get(self.url, headers=headers, timeout=20)
        resp.raise_for_status()

        cleaned = _clean_html(resp.text)
        dicts = _extract_events(cleaned, self.venue, self.town)
        events = _dicts_to_events(dicts, self.name, self.venue, self.town)

        log.debug("[%s] Found %d events", self.name, len(events))
        return events


class ClaudePlaywrightScraper(BaseScraper):
    """Renders a JS-heavy page with Playwright, then uses Haiku to extract events."""

    def __init__(self, name: str, url: str, venue: str, town: str):
        self.name = name
        self.url = url
        self.venue = venue
        self.town = town

    def _fetch(self) -> list[Event]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ImportError(
                "Playwright is not installed. "
                "Run: pip install playwright && playwright install chromium"
            )

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=BROWSER_UA)
            page.goto(self.url, wait_until="networkidle", timeout=30_000)
            # Wait a beat for any deferred rendering
            page.wait_for_timeout(2000)
            html = page.content()
            browser.close()

        cleaned = _clean_html(html)
        dicts = _extract_events(cleaned, self.venue, self.town)
        events = _dicts_to_events(dicts, self.name, self.venue, self.town)

        log.debug("[%s] Found %d events", self.name, len(events))
        return events


def load_claude_scrapers(sources_path: Optional[str] = None) -> list[BaseScraper]:
    """Load scraper instances from sources.json."""
    if sources_path is None:
        sources_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources.json")

    with open(sources_path) as f:
        config = json.load(f)

    scrapers = []
    for s in config.get("sources", []):
        name = s["name"]
        url = s["url"]
        venue = s["venue"]
        town = s["town"]
        kind = s.get("type", "html")

        if kind == "playwright":
            scrapers.append(ClaudePlaywrightScraper(name, url, venue, town))
        else:
            scrapers.append(ClaudeHTMLScraper(name, url, venue, town))

    return scrapers
