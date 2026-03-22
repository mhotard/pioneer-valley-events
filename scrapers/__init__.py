from .amherst_cinema import AmherstCinemaScraper
from .gateway_city_arts import GatewayCityArtsScraper
from .hawks_reed import HawksReedScraper
from .iron_horse import IronHorseScraper
from .northampton import NorthamptonCityScraper
from .the_drake import TheDrakeScraper
from .umass import UMassScraper

ALL_SCRAPERS = [
    UMassScraper,
    IronHorseScraper,
    AmherstCinemaScraper,
    TheDrakeScraper,
    NorthamptonCityScraper,
    HawksReedScraper,
    GatewayCityArtsScraper,
]
