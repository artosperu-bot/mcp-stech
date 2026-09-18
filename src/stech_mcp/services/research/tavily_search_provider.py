from __future__ import annotations

from typing import Any

import httpx

from stech_mcp.services.research.search_provider import SearchProviderNotConfigured, SearchResult


_TAVILY_SEARCH_URL = "https://api.tavily.com/search"


def _normalize_domains(domains: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for raw in domains:
        value = str(raw or "").strip().lower().strip(".")
        if value and value not in out:
            out.append(value)
    return out


class TavilySearchProvider:
    """Tavily Basic Search provider used only as a bounded identity fallback.

    One call to this provider is intended to consume one Tavily Basic Search
    credit. The per-Part-Number budget is enforced by ProductIdentityResearchService,
    not here, so concurrent product jobs do not share mutable provider state.
    """

    def __init__(
        self,
        *,
        api_key: str = "",
        timeout_seconds: float = 20.0,
        http_client: Any | None = None,
    ) -> None:
        self.api_key = str(api_key or "").strip()
        self.timeout_seconds = float(timeout_seconds)
        self.http_client = http_client

    def search(
        self,
        query: str,
        domains: tuple[str, ...] = (),
        limit: int = 5,
    ) -> list[SearchResult]:
        text = " ".join(str(query or "").split())
        if not text:
            raise ValueError("query is required")
        if not self.api_key:
            raise SearchProviderNotConfigured("TAVILY_API_KEY is not configured")

        return_limit = max(1, min(int(limit), 20))
        payload: dict[str, Any] = {
            "query": text,
            "search_depth": "basic",
            "max_results": return_limit,
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
        }
        normalized_domains = _normalize_domains(domains)
        if normalized_domains:
            payload["include_domains"] = normalized_domains

        owned_client = self.http_client is None
        client = self.http_client or httpx.Client(follow_redirects=True)
        try:
            response = client.post(
                _TAVILY_SEARCH_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
        finally:
            if owned_client:
                client.close()

        rows: list[SearchResult] = []
        seen: set[str] = set()
        for item in list(data.get("results") or []):
            url = str((item or {}).get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            rows.append(
                SearchResult(
                    title=str((item or {}).get("title") or url).strip(),
                    url=url,
                    description=str((item or {}).get("content") or "").strip() or None,
                )
            )
            if len(rows) >= return_limit:
                break
        return rows
