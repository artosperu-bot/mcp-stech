from __future__ import annotations

import re
from typing import Any

import httpx

from stech_mcp.services.research.search_provider import SearchProviderNotConfigured, SearchResult


_BRAVE_WEB_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
_DOMAIN_RE = re.compile(r"^[A-Za-z0-9.-]+$")


def _normalize_domains(domains: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    for domain in domains:
        value = str(domain or "").strip().lower()
        if not value or not _DOMAIN_RE.fullmatch(value) or value.startswith(".") or value.endswith("."):
            continue
        if value not in result:
            result.append(value)
    return tuple(result)


class BraveSearchProvider:
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

    def search(
        self,
        query: str,
        domains: tuple[str, ...] = (),
        limit: int = 5,
    ) -> list[SearchResult]:
        if not self.api_key:
            raise SearchProviderNotConfigured("Brave Search API key is not configured")
        text = " ".join(str(query or "").split())
        if not text:
            raise ValueError("query is required")

        normalized_domains = _normalize_domains(domains)
        if normalized_domains:
            if len(normalized_domains) == 1:
                text = f"{text} site:{normalized_domains[0]}"
            else:
                site_filter = " OR ".join(f"site:{domain}" for domain in normalized_domains)
                text = f"{text} ({site_filter})"

        count = max(1, min(int(limit), 20))
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key,
        }
        params = {
            "q": text,
            "count": count,
            "country": self.country,
            "search_lang": self.search_lang,
        }

        owned_client = self.http_client is None
        client = self.http_client or httpx.Client()
        try:
            response = client.get(
                _BRAVE_WEB_SEARCH_URL,
                headers=headers,
                params=params,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        finally:
            if owned_client:
                client.close()

        web = payload.get("web") if isinstance(payload, dict) else None
        rows = web.get("results") if isinstance(web, dict) else None
        results: list[SearchResult] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            url = str(row.get("url") or "").strip()
            title = str(row.get("title") or "").strip()
            if not url or not title:
                continue
            description = str(row.get("description") or "").strip() or None
            results.append(SearchResult(title=title, url=url, description=description))
            if len(results) >= count:
                break
        return results
