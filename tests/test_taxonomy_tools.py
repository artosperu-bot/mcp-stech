from stech_mcp.tools.taxonomy import register_taxonomy_tools


class FakeMCP:
    def __init__(self):
        self.names = []

    def tool(self):
        def decorate(func):
            self.names.append(func.__name__)
            return func
        return decorate


class FakeService:
    pass


def test_taxonomy_tools_are_registered():
    mcp = FakeMCP()
    registered = register_taxonomy_tools(mcp, service=FakeService())

    expected = {
        "taxonomy_missing_list",
        "taxonomy_catalog_get",
        "taxonomy_review_sync",
        "taxonomy_review_list",
        "taxonomy_review_get",
        "taxonomy_propose",
        "taxonomy_sql_preview",
        "taxonomy_approve",
        "taxonomy_reject",
        "taxonomy_apply",
    }
    assert set(registered) == expected
    assert set(mcp.names) == expected
