import logging
from datetime import datetime, timedelta
from ..models import PricePoint
from . import serpapi as _serpapi

logger = logging.getLogger(__name__)


async def get_price_history(query: str, api_key: str) -> tuple[list[PricePoint], float | None]:
    """Returns (price_history_list, lowest_price_6m).

    No real historical data source is wired up yet — return empty to avoid
    presenting fabricated history as real price trends.
    """
    return [], None
