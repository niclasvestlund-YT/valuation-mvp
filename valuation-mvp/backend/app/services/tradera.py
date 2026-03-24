import logging
import httpx
from lxml import etree
from ..models import MarketListing

logger = logging.getLogger(__name__)

TRADERA_ENDPOINT = "https://api.tradera.com/v3/SearchService.asmx"
SOAP_ACTION = "http://api.tradera.com/Search"

# Field name confirmed from WSDL: "query" (not "searchQuery")
# orderBy must be a string value (not int)
# itemStatus does not exist in the schema — filter client-side via IsEnded
# MaxResultAge is required in ConfigurationHeader
SOAP_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:tns="http://api.tradera.com">
  <soap:Header>
    <tns:AuthenticationHeader>
      <tns:AppId>{app_id}</tns:AppId>
      <tns:AppKey>{app_key}</tns:AppKey>
    </tns:AuthenticationHeader>
    <tns:ConfigurationHeader>
      <tns:Sandbox>0</tns:Sandbox>
      <tns:MaxResultAge>0</tns:MaxResultAge>
    </tns:ConfigurationHeader>
  </soap:Header>
  <soap:Body>
    <tns:Search>
      <tns:query>{query}</tns:query>
      <tns:categoryId>0</tns:categoryId>
      <tns:pageNumber>1</tns:pageNumber>
      <tns:orderBy>EndDateDescending</tns:orderBy>
    </tns:Search>
  </soap:Body>
</soap:Envelope>"""

NS = "http://api.tradera.com"


def _parse_price(item: etree._Element) -> float:
    # MaxBid is 0 when there are no bids — fall back to BuyItNowPrice
    for field in ("MaxBid", "BuyItNowPrice", "NextBid"):
        el = item.find(f"{{{NS}}}{field}")
        if el is not None and el.text:
            try:
                val = float(el.text)
                if val > 0:
                    return val
            except ValueError:
                continue
    return 0.0


async def search_listings(query: str, app_id: str, app_key: str) -> list[MarketListing]:
    body = SOAP_TEMPLATE.format(app_id=app_id, app_key=app_key, query=query)
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": SOAP_ACTION,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(TRADERA_ENDPOINT, content=body.encode("utf-8"), headers=headers)
            response.raise_for_status()
    except Exception as e:
        logger.warning(f"Tradera API error: {e}")
        return []

    try:
        root = etree.fromstring(response.content)
        errors = root.findall(f".//{{{NS}}}Code")
        if errors:
            logger.warning(f"Tradera API errors: {[e.text for e in errors]}")
            return []

        raw_items = root.findall(f".//{{{NS}}}Items")
        total_el = root.find(f".//{{{NS}}}TotalNumberOfItems")
        logger.info(f"Tradera search: query={query!r} total={total_el.text if total_el is not None else '?'} returned={len(raw_items)}")

        listings = []
        for item in raw_items:
            try:
                title_el = item.find(f"{{{NS}}}ShortDescription")
                url_el = item.find(f"{{{NS}}}ItemUrl")
                end_date_el = item.find(f"{{{NS}}}EndDate")
                is_ended_el = item.find(f"{{{NS}}}IsEnded")

                if title_el is None or not title_el.text:
                    continue

                price = _parse_price(item)
                if price <= 0:
                    continue

                is_ended = (is_ended_el is not None and is_ended_el.text == "true")
                listings.append(MarketListing(
                    title=title_el.text,
                    price=price,
                    source="tradera",
                    url=url_el.text if url_el is not None else None,
                    status="sold" if is_ended else "active",
                    date=end_date_el.text if end_date_el is not None else None,
                ))
            except Exception:
                continue

        sold = sum(1 for item in listings if item.status == "sold")
        logger.info(f"Tradera parsed: {len(listings)} listings ({sold} sold, {len(listings)-sold} active)")
        return listings

    except Exception as e:
        logger.warning(f"Tradera XML parse error: {e}")
        return []
