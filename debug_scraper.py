#!/usr/bin/env python3
"""
Debug script — fetches each source URL and dumps the first chunk of HTML.
Run this and paste the output here so we can identify the right selectors.

Usage:
    python3 debug_scraper.py
    python3 debug_scraper.py amherst-cinema   # single source
"""

import json
import os
import sys

import requests
from bs4 import BeautifulSoup

from scrapers import get_all_scrapers


def load_sources() -> dict:
    """All scraper names → URLs (static scrapers + sources.json entries)."""
    sources_path = os.path.join(os.path.dirname(__file__), "sources.json")
    with open(sources_path) as f:
        config = json.load(f)
    sources = {s["name"]: s["url"] for s in config.get("sources", [])}
    for scraper in get_all_scrapers():
        if scraper.name not in sources and getattr(scraper, "url", ""):
            sources[scraper.name] = scraper.url
    return sources


SOURCES = load_sources()

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
