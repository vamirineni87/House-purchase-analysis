"""Web scrapers for county property portals and listing sites."""

from .base import BaseScraper
from .fairfax_icare import FairfaxICareScraper
from .fairfax_plus import FairfaxPLUSScraper
from .lcps_schools import LCPSSchoolScraper
from .loudoun_parcel import LoudounParcelScraper
from .redfin import RedfinScraper
from .realtor import RealtorScraper
from .zillow import ZillowScraper

# Loudoun permits live in their own module rather than a class because
# Tyler EnerGov has a clean unauthenticated REST API — no Playwright
# needed. Re-exported here as a function so callers don't have to know
# the difference.
from .loudoun_permits import fetch_permits as fetch_loudoun_permits

__all__ = [
    "BaseScraper",
    "FairfaxICareScraper",
    "FairfaxPLUSScraper",
    "LCPSSchoolScraper",
    "LoudounParcelScraper",
    "RedfinScraper",
    "RealtorScraper",
    "ZillowScraper",
    "fetch_loudoun_permits",
]
