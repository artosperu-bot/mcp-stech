from stech_mcp.services.research.bing_html_search_provider import BingHtmlSearchProvider


class FakeResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        return None


class FakeClient:
    def __init__(self, html: str):
        self.html = html
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.html)


def test_bing_html_search_requires_no_api_key_and_returns_result_links():
    html = '''
    <html><body>
      <li class="b_algo"><h2><a href="https://support.lenovo.com/us/en/product/pn1">Lenovo PN1</a></h2></li>
      <li class="b_algo"><h2><a href="https://example.com/pn1">Other result</a></h2></li>
    </body></html>
    '''
    client = FakeClient(html)
    provider = BingHtmlSearchProvider(http_client=client)

    rows = provider.search('"PN1" EAN UPC GTIN', domains=("lenovo.com",), limit=5)

    assert [row.url for row in rows] == ["https://support.lenovo.com/us/en/product/pn1"]
    assert rows[0].title == "Lenovo PN1"
    assert client.calls[0][0] == "https://www.bing.com/search"
    params = client.calls[0][1]["params"]
    assert 'site:lenovo.com' in params["q"]
    assert "api_key" not in client.calls[0][1]


def test_bing_html_search_dedupes_links_and_caps_limit():
    html = '''
    <li class="b_algo"><h2><a href="https://lenovo.com/a">A</a></h2></li>
    <li class="b_algo"><h2><a href="https://lenovo.com/a">A duplicate</a></h2></li>
    <li class="b_algo"><h2><a href="https://lenovo.com/b">B</a></h2></li>
    '''
    provider = BingHtmlSearchProvider(http_client=FakeClient(html))

    rows = provider.search("PN1", domains=("lenovo.com",), limit=1)

    assert [row.url for row in rows] == ["https://lenovo.com/a"]
