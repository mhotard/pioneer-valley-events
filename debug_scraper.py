#!/usr/bin/env python3
"""
Debug script — fetches each source URL and dumps the first chunk of HTML.
Run this and paste the output here so we can identify the right selectors.

Usage:
    python3 debug_scraper.py
    python3 debug_scraper.py amherst-cinema   # single source
"""

import sys

import requests
from bs4 import BeautifulSoup

SOURCES = {
    "umass":            "https://events.umass.edu/calendar",
    "amherst-cinema":   "https://amherstcinema.org/coming-soon",
    "iron-horse":       "https://www.iheg.com/iron-horse-music-hall/calendar",
    "the-drake":        "https://www.thedrakehotel.net/events",
    "hawks-reed":       "https://www.hawksandreed.com/events",
    "gateway-city":     "https://gatewaycityarts.com/events",
    "northampton":      "https://www.northamptonma.gov/calendar.aspx",
    "academy-of-music": "https://www.academyofmusictheatre.com/events",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
CHARS = 4000  # how many chars of HTML to print per source


def probe(name, url):
    print(f"\n{'='*60}")
    print(f"SOURCE: {name}")
    print(f"URL:    {url}")
    print("="*60)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        print(f"Status: {resp.status_code}  Final URL: {resp.url}")
        html = resp.text
        print(f"HTML length: {len(html)} chars")
        soup = BeautifulSoup(html, "html.parser")

        # Print the body HTML (skip head)
        body = soup.find("body") or soup
        body_html = str(body)
        print(f"\n--- Body HTML (first {CHARS} chars) ---")
        print(body_html[:CHARS])

        # Also print key element counts
        print("\n--- Useful selectors found ---")
        for sel in [
            ".views-row", ".view-content", "article", ".node",
            "h2 a", "h3 a", ".field-content a",
            ".tribe-event", "article.tribe-event",
            ".event", ".event-item", ".event-title",
            "time", "[datetime]",
        ]:
            found = soup.select(sel)
            if found:
                print(f"  {sel}: {len(found)} found — first: {str(found[0])[:120]}")
    except Exception as e:
        print(f"ERROR: {e}")


targets = sys.argv[1:]
for name, url in SOURCES.items():
    if not targets or name in targets:
        probe(name, url)
