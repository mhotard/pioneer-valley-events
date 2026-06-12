"""Scraper for UMass Athletics home games via events.umass.edu iCal feed."""

from .ical import ICalScraper

# Lowercase substrings that identify a UMass home venue in the LOCATION field
HOME_VENUE_KEYWORDS = {
    "mullins", "garber", "bubble", "mcguirk", "boyden", "derr",
    "umass", "amherst, mass", "amherst, ma",
}

# Lowercase substrings in SUMMARY that flag an athletic event
SPORT_KEYWORDS = {
    "baseball", "softball", "basketball", "lacrosse", "soccer", "football",
    "volleyball", "tennis", "swimming", "track", "cross country", "rowing",
    "field hockey", "wrestling", "golf", "ice hockey", "hockey", "squash",
    "minutemen", "minutewomen",
}


class UMassAthleticsScraper(ICalScraper):
    name = "umass-athletics"
    url = "https://events.umass.edu/calendar.ics"
    town = "Amherst"
    address = "Amherst, MA 01003"
    default_venue = "UMass Athletics"
    category = "outdoor"

    def accept(self, summary: str, location: str) -> bool:
        sl, ll = summary.lower(), location.lower()
        is_sport = any(kw in sl for kw in SPORT_KEYWORDS)
        is_home = any(kw in ll for kw in HOME_VENUE_KEYWORDS)
        return is_sport and is_home
