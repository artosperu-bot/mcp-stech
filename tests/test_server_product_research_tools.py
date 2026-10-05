import stech_mcp.server_authoritative as runtime


server = runtime._server


def test_product_research_tools_are_registered_as_server_callables():
    for name in (
        "product_technical_missing_list",
        "product_research_plan",
        "product_source_ingest",
        "product_fact_candidates",
        "product_fact_promote",
        "product_fact_promote_batch",
        "product_channel_readiness",
    ):
        assert callable(getattr(server, name, None)), name
