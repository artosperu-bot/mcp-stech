def test_server_module_imports_and_exposes_initial_tools():
    import stech_mcp.server as server

    assert server.mcp is not None
    assert callable(server.stech_health)
    assert callable(server.product_get)
    assert callable(server.product_search)
    assert callable(server.product_history)
    assert callable(server.coolbox_preview)
    assert callable(server.packaging_estimate_weight)
    assert callable(server.packaging_validate_dimensions)
    assert callable(server.packaging_rule_get)
    assert callable(server.packaging_resolve)
    assert callable(server.marketplace_preview)
    assert callable(server.product_prepare)
    assert callable(server.product_master_get)
    assert callable(server.product_readiness_get)
    assert callable(server.channel_draft_get)
    assert callable(server.product_approve)
    assert callable(server.product_field_verify)
    assert callable(server.product_enrichment_get)
    assert callable(server.product_identity_missing_list)
    assert callable(server.product_identity_promote_verified)
    assert callable(server.product_images_get)
