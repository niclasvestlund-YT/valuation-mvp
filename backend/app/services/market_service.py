from backend.app.services.market_data_service import MarketDataService


class MarketService:
    def __init__(self, market_data_service: MarketDataService | None = None) -> None:
        self.market_data_service = market_data_service or MarketDataService()

    def get_comparables(self, brand: str, model: str, category: str | None = None) -> list[dict]:
        normalized_comparables = self.market_data_service.get_comparables(
            brand=brand,
            model=model,
            category=category,
        )

        comparables: list[dict] = []
        for comparable in normalized_comparables:
            listing_type = "sold" if comparable.status == "completed" else "active"
            comparables.append(
                {
                    "title": comparable.title,
                    "price": comparable.price,
                    "listing_type": listing_type,
                    "source": comparable.source,
                    "listing_id": comparable.listing_id,
                    "currency": comparable.currency,
                    "url": comparable.url,
                    "ended_at": comparable.ended_at.isoformat() if comparable.ended_at else None,
                    "shipping_cost": comparable.shipping_cost,
                    "condition_hint": comparable.condition_hint,
                    "status": comparable.status,
                    "raw": comparable.raw,
                }
            )

        return comparables

    def get_prices(self, brand: str, model: str, category: str | None = None) -> list[int]:
        return [int(round(float(comparable["price"]))) for comparable in self.get_comparables(brand, model, category)]
