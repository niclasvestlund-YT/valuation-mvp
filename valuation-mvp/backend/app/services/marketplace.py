import logging
from ..models import MarketListing
from . import serpapi as _serpapi

logger = logging.getLogger(__name__)


async def search_listings(query: str, api_key: str) -> list[MarketListing]:
    try:
        return await _serpapi.search_facebook_marketplace(query, api_key)
    except Exception as e:
        logger.warning(f"Facebook Marketplace search error: {e}")
        return []
