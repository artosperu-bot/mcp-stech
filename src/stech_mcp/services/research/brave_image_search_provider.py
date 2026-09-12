from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from stech_mcp.services.research.image_search_provider import ImageSearchResult
from stech_mcp.services.research.search_provider import SearchProviderNotConfigured


_BRAVE_IMAGE_SEARCH_URL = "https://api.search.brave.com/res/v1/images/search"


class BraveImageSearchProvider:
    def __init__(
        self,
        *,
        api_key: str,
        country: str = "PE",
        search_lang: str = "es",
        timeout_seconds: float = 15.0,
        http_client: Any | None = None,
    ) -> None:
        self.api_key = str(api_key or "").strip()
        self.country = str(country or "PE").strip().upper() or "PE"
        self.search_lang = str(search_lang or "es").strip().lower() or "es"
        self.timeout_seconds = float(timeout_seconds)
        self.http_client = http_client

    def search(self, query: str, count: int = 10) -> list[ImageSearchResult]:
        if not self.api_key:
            raise SearchProviderNotConfigured("Brave Image Search API key is not configured")
        text = " ".join(str(query or "").split())
        if not text:
            raise ValueError("query is required")
        limit = max(1, min(int(count), 50))

        owned_client = self.http_client is None
        client = self.http_client or httpx.Client()
        try:
            response = client.get(
                _BRAVE_IMAGE_SEARCH_URL,
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": self.api_key,
                },
                params={
                    "q": text,
                    "count": limit,
                    "country": self.country,
                    "search_lang": self.search_lang,
                    "safesearch": "strict",
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        finally:
            if owned_client:
                client.close()

        rows = payload.get("results") if isinstance(payload, dict) else []
        output: list[ImageSearchResult] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            properties = row.get("properties") if isinstance(row.get("properties"), dict) else {}
            image_url = str(properties.get("url") or row.get("image_url") or "").strip()
            if not image_url:
                continue
            page_url = str(row.get("url") or "").strip() or None
            thumbnail = row.get("thumbnail") if isinstance(row.get("thumbnail"), dict) else {}
            host = urlparse(page_url or image_url).hostname
            output.append(
                ImageSearchResult(
                    title=str(row.get("title") or "").strip(),
                    image_url=image_url,
                    page_url=page_url,
                    thumbnail_url=str(thumbnail.get("src") or "").strip() or None,
                    width=int(properties["width"]) if properties.get("width") else None,
                    height=int(properties["height"]) if properties.get("height") else None,
                    source_domain=str(host).lower() if host else None,
                )
            )
            if len(output) >= limit:
                break
        return output
