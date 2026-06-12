"""Scraper for Amherst College Athletics home games via iCal feed."""

from .ical import ICalScraper

# Lowercase substrings that identify a home game location
HOME_KEYWORDS = {
    "amherst, ma", "amherst college", "pratt field", "lefrak",
    "orr rink", "alumni gym", "lord jeffs", "koch sports", "greenway",
}


class AmherstAthleticsScraper(ICalScraper):
    name = "amherst-athletics"
    url = "https://athletics.amherst.edu/calendar.ics"
    town = "Amherst"
    address = "Amherst, MA 01002"
    default_venue = "Amherst College Athletics"
    category = "outdoor"

    def accept(self, summary: str, location: str) -> bool:
        ll = location.lower()
        return any(kw in ll for kw in HOME_KEYWORDS)
