from .amherst_athletics import AmherstAthleticsScraper
from .amherst_cinema import AmherstCinemaScraper
from .claude_scraper import load_claude_scrapers
from .community import CommunityEventsScraper
from .forbes_library import ForbesLibraryScraper
from .harriers import HarriersScraper
from .jones_library import JonesLibraryScraper
from .mtholyoke import MountHolyokeScraper
from .nepm_culture import NEPMCultureScraper
from .tribe_events import (
    HawksReedScraper,
    HistoricDeerfieldScraper,
    SpringfieldMuseumsScraper,
)
from .umass import UMassScraper
from .umass_athletics import UMassAthleticsScraper

# Hand-written scrapers (kept for sources with reliable structured data)
STATIC_SCRAPERS = [
    UMassScraper,
    UMassAthleticsScraper,
    AmherstAthleticsScraper,
    AmherstCinemaScraper,
    CommunityEventsScraper,
    JonesLibraryScraper,
    ForbesLibraryScraper,
    MountHolyokeScraper,
    NEPMCultureScraper,
    HarriersScraper,
    SpringfieldMuseumsScraper,
    HawksReedScraper,
    HistoricDeerfieldScraper,
]


def get_all_scrapers(sources_path=None):
    """Return all scraper instances: static hand-written + Claude-powered."""
    scrapers = [cls() for cls in STATIC_SCRAPERS]
    scrapers += load_claude_scrapers(sources_path)
    return scrapers
