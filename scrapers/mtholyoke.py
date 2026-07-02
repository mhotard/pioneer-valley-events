"""Scraper for Mount Holyoke College events — Localist JSON API (events.mtholyoke.edu)."""

from .localist import LocalistScraper


class MountHolyokeScraper(LocalistScraper):
    name = "mtholyoke"
    url = "https://events.mtholyoke.edu"
    api_url = "https://events.mtholyoke.edu/api/2/events?days=90&pp=100"
    town = "South Hadley"
    default_venue = "Mount Holyoke College"
    default_address = "South Hadley, MA 01075"
    default_category = "academia"
