from __future__ import annotations

from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import httpx

from stech_mcp.services.research.search_provider import SearchResult


_BING_SEARCH_URL = "https://www.bing.com/search"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/152.0.0.0 Safari/537.36"
)


def _normalize_domains(domains: tuple[str, ...]) -> tuple[str, ...]:
    out: list[str] = []
    for raw in domains:
        value = str(raw or "").strip().lower().strip(".")
        if value and value not in out:
            out.append(value)
    return tuple(out)


def _matches_domain(url: str, domains: tuple[str, ...]) -> bool:
    if not domains:
        return True
    host = str(urlparse(str(url or "")).hostname or "").strip().lower().rstrip(".")
    return any(host == domain or host.endswith("." + domain) for domain in domains)


class _BingResultsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._algo_depth = 0
        self._capture_anchor = False
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []
        self.rows: list[tuple[str, str]] = []

    @staticmethod
    def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
        raw = next((value for key, value in attrs if key == "class"), None) or ""
        return {token.strip() for token in raw.split() if token.strip()}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.lower()
        if self._algo_depth:
            self._algo_depth += 1
        elif lower == "li" and "b_algo" in self._classes(attrs):
            self._algo_depth = 1

        if not self._algo_depth or lower != "a" or self._anchor_href is not None:
            return
        href = str(next((value for key, value in attrs if key == "href"), None) or "").strip()
        if not href.startswith(("http://", "https://")):
            return
        self._capture_anchor = True
        self._anchor_href = href
        self._anchor_text = []

    def handle_data(self, data: str) -> None:
        if self._capture_anchor:
            text = str(data or "").strip()
            if text:
                self._anchor_text.append(text)

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if self._capture_anchor and lower == "a" and self._anchor_href:
            title = " ".join(self._anchor_text).strip() or self._anchor_href
            self.rows.append((title, self._anchor_href))
            self._capture_anchor = False
            self._anchor_href = None
            self._anchor_text = []
        if self._algo_depth:
            self._algo_depth -= 1


class BingHtmlSearchProvider:
    """Discover public result URLs through Bing HTML without an API key.

    Search-result snippets are discovery hints only. Product identity acceptance
    still happens later from the opened destination page and exact-PN evidence.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = 20.0,
        http_client: Any | None = None,
    ) -> None:
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

        normalized_domains = _normalize_domains(domains)
        if normalized_domains:
            if len(normalized_domains) == 1:
                text = f"{text} site:{normalized_domains[0]}"
            else:
                sites = " OR ".join(f"site:{domain}" for domain in normalized_domains)
                text = f"{text} ({sites})"

        count = max(1, min(int(limit), 20))
        owned_client = self.http_client is None
        client = self.http_client or httpx.Client(follow_redirects=True)
        try:
            response = client.get(
                _BING_SEARCH_URL,
                params={"q": text, "count": count},
                headers={"User-Agent": _USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            parser = _BingResultsParser()
            parser.feed(str(response.text or ""))
        finally:
            if owned_client:
                client.close()

        results: list[SearchResult] = []
        seen: set[str] = set()
        for title, url in parser.rows:
            if url in seen or not _matches_domain(url, normalized_domains):
                continue
            seen.add(url)
            results.append(SearchResult(title=title, url=url, description=None))
            if len(results) >= count:
                break
        return results
