import logging
from xml.etree import ElementTree as ET

import requests

from backend.app.core.config import settings
from backend.app.utils.cache import get_cached, set_cached

logger = logging.getLogger(__name__)

TRADERA_XML_NAMESPACE = {"tradera": "http://api.tradera.com"}
_RATE_LIMIT_CACHE_KEY = "tradera:rate_limited"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _body_preview(value: str, *, limit: int = 400) -> str:
    return " ".join(value.split())[:limit]


class TraderaClient:
    def __init__(
        self,
        app_id: int | None = None,
        app_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.app_id = app_id if app_id is not None else settings.tradera_app_id
        self.app_key = (app_key or settings.tradera_app_key or "").strip() or None
        self.base_url = (base_url or settings.tradera_base_url).rstrip("/")
        self.timeout_seconds = timeout_seconds or settings.tradera_timeout_seconds

    @property
    def is_configured(self) -> bool:
        return self.app_id is not None and bool(self.app_key)

    def search(
        self,
        query: str,
        *,
        category_id: int = 0,
        page_number: int = 1,
        order_by: str = "EndDateDescending",
    ) -> list[dict]:
        normalized_query = " ".join(query.split())
        if not normalized_query:
            return []

        if get_cached(_RATE_LIMIT_CACHE_KEY):
            logger.info("tradera.rate_limited_cached query=%s", normalized_query)
            return []

        cache_key = f"tradera:{normalized_query}:{category_id}:{order_by}"
        cached = get_cached(cache_key)
        if cached is not None:
            logger.info("tradera.cache_hit query=%s count=%s", normalized_query, len(cached))
            return cached

        if not self.is_configured:
            logger.info(
                "tradera.search.not_configured query=%s app_id_present=%s app_key_present=%s",
                normalized_query,
                self.app_id is not None,
                bool(self.app_key),
            )
            return []

        logger.info(
            "tradera.search.request_start query=%s app_id_present=%s app_key_present=%s base_url=%s category_id=%s page_number=%s order_by=%s",
            normalized_query,
            self.app_id is not None,
            bool(self.app_key),
            self.base_url,
            category_id,
            page_number,
            order_by,
        )

        try:
            response = requests.post(
                f"{self.base_url}/Search",
                data={
                    "appId": str(self.app_id),
                    "appKey": self.app_key,
                    "query": normalized_query,
                    "categoryId": str(category_id),
                    "pageNumber": str(page_number),
                    "orderBy": order_by,
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 429:
                # Rate limited — set a flag so ALL subsequent queries skip the API for 1h
                logger.warning("tradera.search.rate_limited query=%s", normalized_query)
                set_cached(_RATE_LIMIT_CACHE_KEY, True)
            else:
                logger.warning("tradera.search.request_failed query=%s reason=%s", normalized_query, exc)
            return []
        except requests.RequestException as exc:
            logger.warning("tradera.search.request_failed query=%s reason=%s", normalized_query, exc)
            return []

        try:
            raw_results = self._parse_search_response(response.text)
            if not raw_results:
                logger.info(
                    "tradera.search.empty_response query=%s status_code=%s body_preview=%s",
                    normalized_query,
                    response.status_code,
                    _body_preview(response.text),
                )
            else:
                # Only cache non-empty results — empty means no listings now, not never
                set_cached(cache_key, raw_results)
            logger.info(
                "tradera.search.raw_results query=%s count=%s",
                normalized_query,
                len(raw_results),
            )
            return raw_results
        except ET.ParseError as exc:
            logger.warning("tradera.search.parse_failed query=%s reason=%s", normalized_query, exc)
            return []

    def _parse_search_response(self, xml_text: str) -> list[dict]:
        root = ET.fromstring(xml_text)
        item_elements, path_used = self._find_item_elements(root)
        logger.info(
            "tradera.search.item_nodes_found count=%s path=%s",
            len(item_elements),
            path_used,
        )
        if not item_elements:
            return []

        extracted_items: list[dict] = []
        seen_ids: set[str] = set()

        for candidate in item_elements:
            raw_item = self._extract_item_payload(candidate)
            item_id = raw_item.get("Id") or raw_item.get("ItemId")
            title = raw_item.get("ShortDescription") or raw_item.get("Description") or raw_item.get("Title")
            if not item_id or not title:
                continue

            item_id = str(item_id).strip()
            if item_id in seen_ids:
                continue

            seen_ids.add(item_id)
            extracted_items.append(raw_item)

        return extracted_items

    def _find_item_elements(self, root: ET.Element) -> tuple[list[ET.Element], str]:
        namespaced_items = root.findall("./tradera:Items", TRADERA_XML_NAMESPACE)
        if namespaced_items:
            return namespaced_items, "./tradera:Items"

        tolerant_items = [
            element
            for element in root.iter()
            if _local_name(element.tag) in {"Items", "Item"} and self._looks_like_item_element(element)
        ]
        return tolerant_items, "iter(local-name in {'Items','Item'})"

    def _looks_like_item_element(self, element: ET.Element) -> bool:
        child_names = {_local_name(child.tag) for child in list(element)}
        return bool({"Id", "ItemId"} & child_names) and bool(
            {"ShortDescription", "Description", "Title"} & child_names
        )

    def _extract_item_payload(self, element: ET.Element) -> dict:
        payload: dict[str, str] = {}
        for child in list(element):
            if len(list(child)) > 0:
                continue

            key = _local_name(child.tag)
            value = (child.text or "").strip()
            if not key or not value:
                continue

            payload[key] = value

        return payload
