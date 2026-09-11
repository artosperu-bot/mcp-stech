from stech_mcp.services.research.brave_search_provider import BraveSearchProvider
from stech_mcp.services.research.search_provider import SearchProviderNotConfigured


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "web": {
                "results": [
                    {
                        "title": "PN1 official specs",
                        "url": "https://manufacturer.example/pn1",
                        "description": "Official product specification",
                    }
                ]
            }
        }


class FakeClient:
    def __init__(self):
        self.last_url = None
        self.last_headers = None
        self.last_params = None
        self.last_timeout = None

    def get(self, url, *, headers, params, timeout):
        self.last_url = url
        self.last_headers = headers
        self.last_params = params
        self.last_timeout = timeout
        return FakeResponse()


def test_brave_provider_sends_subscription_header_and_country_params():
    client = FakeClient()
    provider = BraveSearchProvider(
        api_key="secret",
        country="PE",
        search_lang="es",
        http_client=client,
    )

    results = provider.search('"PN1" specifications', domains=("manufacturer.example",), limit=5)

    assert client.last_url == "https://api.search.brave.com/res/v1/web/search"
    assert client.last_headers["X-Subscription-Token"] == "secret"
    assert client.last_params["country"] == "PE"
    assert client.last_params["search_lang"] == "es"
    assert client.last_params["count"] == 5
    assert "site:manufacturer.example" in client.last_params["q"]
    assert results[0].url == "https://manufacturer.example/pn1"
    assert results[0].title == "PN1 official specs"


def test_brave_provider_without_key_fails_closed():
    provider = BraveSearchProvider(api_key="", http_client=FakeClient())

    try:
        provider.search("PN1")
    except SearchProviderNotConfigured as exc:
        assert "BRAVE" in str(exc).upper()
    else:
        raise AssertionError("expected SearchProviderNotConfigured")
