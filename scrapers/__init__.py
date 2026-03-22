from .amherst_cinema import AmherstCinemaScraper
from .claude_scraper import load_claude_scrapers
from .umass import UMassScraper

# Hand-written scrapers (kept for sources with reliable structured data)
STATIC_SCRAPERS = [
    UMassScraper,
    AmherstCinemaScraper,
]


def get_all_scrapers(sources_path=None):
    """Return all scraper instances: static hand-written + Claude-powered."""
    scrapers = [cls() for cls in STATIC_SCRAPERS]
    scrapers += load_claude_scrapers(sources_path)
    return scrapers
