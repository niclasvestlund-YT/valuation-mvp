"""
Prisjakt new-price client — BLOCKED (HTTP 403).

Investigation result (2026-03-24):
- https://www.prisjakt.nu/search?search=... → HTTP 403 (Cloudflare / bot protection)
- https://api.prisjakt.nu/v0/products?q=... → HTTP 404 (no public API)
- https://www.prisjakt.nu/graphql → HTTP 404
- __NEXT_DATA__ is not present in the blocked 403 response
- No structured data (JSON-LD, meta price tags) returned

Prisjakt is fully JS-rendered behind Cloudflare and does not offer a
public API. Scraping is not viable without headless-browser infrastructure.

Decision: use Serper.dev (serper_new_price_client.py) as the primary new-price
source. SerpAPI Google Shopping remains as an optional fallback.
"""


class PrisjaktClient:
    """Stub — Prisjakt blocks all server-side requests with HTTP 403."""

    @property
    def is_configured(self) -> bool:
        return False

    def get_new_price(self, brand: str, model: str) -> None:
        """Always returns None. Prisjakt is not accessible server-side."""
        return None
