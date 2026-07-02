"""Scraper for UMass Amherst events — Localist JSON API (events.umass.edu).

Previously scraped JSON-LD from the HTML calendar pages, which yielded ~8
events; the API returns the full listing (~65+).
"""

from .localist import LocalistScraper


class UMassScraper(LocalistScraper):
    name = "umass"
    url = "https://events.umass.edu/calendar"
    api_url = "https://events.umass.edu/api/2/events?days=90&pp=100"
    town = "Amherst"
    default_venue = "UMass Amherst"
    default_address = "Amherst, MA 01003"
    default_category = "academia"
