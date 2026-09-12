import pytest

from stech_mcp.services.research.brave_image_search_provider import BraveImageSearchProvider
from stech_mcp.services.research.search_provider import SearchProviderNotConfigured


class Response:
    def raise_for_status(self):
        pass

    def json(self):
        return {
            "results": [
                {
                    "title": "Lenovo 82YU00XYLM",
                    "url": "https://www.lenovo.com/p/82YU00XYLM",
                    "properties": {
                        "url": "https://p3-ofp.static.pub/image.jpg",
                        "width": 1200,
                        "height": 900,
                    },
                    "thumbnail": {"src": "https://thumb/image.jpg"},
                }
            ]
        }


class Client:
    def __init__(self):
        self.calls = []

    def get(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return Response()


def test_no_api_key_raises_not_configured_without_network():
    client = Client()
    provider = BraveImageSearchProvider(api_key="", http_client=client)
    with pytest.raises(SearchProviderNotConfigured):
        provider.search("82YU00XYLM")
    assert client.calls == []


def test_brave_image_search_parses_image_and_page_urls():
    client = Client()
    provider = BraveImageSearchProvider(api_key="k", http_client=client)
    rows = provider.search("82YU00XYLM Lenovo", count=5)
    assert rows[0].image_url == "https://p3-ofp.static.pub/image.jpg"
    assert rows[0].page_url == "https://www.lenovo.com/p/82YU00XYLM"
    assert rows[0].width == 1200
    assert "/images/search" in client.calls[0][0][0]
