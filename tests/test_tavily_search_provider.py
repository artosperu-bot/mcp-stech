import pytest

from stech_mcp.services.research.search_provider import SearchProviderNotConfigured
from stech_mcp.services.research.tavily_search_provider import TavilySearchProvider


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.payload)


def test_tavily_uses_basic_search_and_domain_filter():
    client = FakeClient({
        "results": [
            {
                "title": "Lenovo PN1",
                "url": "https://support.lenovo.com/pn1",
                "content": "PN1 EAN 4006381333931",
            }
        ]
    })
    provider = TavilySearchProvider(api_key="tvly-test", http_client=client)

    rows = provider.search('"PN1" LENOVO EAN UPC GTIN barcode', domains=("lenovo.com",), limit=10)

    assert [row.url for row in rows] == ["https://support.lenovo.com/pn1"]
    assert rows[0].description == "PN1 EAN 4006381333931"
    url, kwargs = client.calls[0]
    assert url == "https://api.tavily.com/search"
    assert kwargs["json"]["search_depth"] == "basic"
    assert kwargs["json"]["max_results"] == 10
    assert kwargs["json"]["include_domains"] == ["lenovo.com"]
    assert kwargs["headers"]["Authorization"] == "Bearer tvly-test"


def test_tavily_requires_key_before_spending_request():
    provider = TavilySearchProvider(api_key="", http_client=FakeClient({"results": []}))

    with pytest.raises(SearchProviderNotConfigured):
        provider.search("PN1")
