from stech_mcp.services.marketplace_preview import build_marketplace_preview


def test_generic_preview_routes_falabella_laptop(monkeypatch):
    def fake_preview(**kwargs):
        return {
            "template": "ProductCreationTemplate / Portátiles|notebooks",
            "field_count": 69,
            "readiness_state": "READY",
            "image_count": len(kwargs.get("image_urls") or []),
            "fields": [],
        }

    monkeypatch.setattr(
        "stech_mcp.services.marketplace_preview.build_falabella_preview",
        fake_preview,
    )

    result = build_marketplace_preview(
        product={"part_number": "82YU00XYLM"},
        marketplace="falabella",
        category="laptop",
        image_urls=["https://ststore227.vtexassets.com/01.jpg"],
    )

    assert result["marketplace"] == "FALABELLA"
    assert result["category"] == "LAPTOP"
    assert result["field_count"] == 69
    assert result["image_count"] == 1
