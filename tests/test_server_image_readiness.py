def test_product_readiness_reports_combined_source_image_inventory(monkeypatch):
    import stech_mcp.server as server

    monkeypatch.setattr(
        server.product_master_repository,
        "get",
        lambda partnumber: {
            "partnumber": partnumber,
            "readiness_state": "LISTO_PARA_REVISAR",
            "identity_score": 100,
            "technical_score": 100,
            "image_score": 100,
            "package_score": 70,
            "coolbox_score": 100,
            "image_count": 0,
        },
    )
    monkeypatch.setattr(
        server.product_master_repository,
        "get_latest_draft",
        lambda partnumber, marketplace: {
            "field_count": 81,
            "required_missing_count": 0,
            "estimated_count": 4,
            "approval_status": None,
        },
    )
    monkeypatch.setattr(
        server,
        "product_images_get",
        lambda partnumber: {
            "found": True,
            "partnumber": partnumber,
            "source_image_count": 4,
            "workspace_image_count": 1,
            "image_count": 5,
            "usable_image_count": 4,
            "approved_image_count": 0,
            "images": [{"source_eligible": True}] * 4 + [{"is_approved": False}],
        },
    )

    result = server.product_readiness_get("82XQ00LYLM")

    readiness = result["readiness"]
    assert readiness["image_count"] == 5
    assert readiness["source_image_count"] == 4
    assert readiness["workspace_image_count"] == 1
    assert readiness["usable_image_count"] == 4
    assert readiness["approved_image_count"] == 0
