def test_product_field_verify_returns_controlled_validation_error(monkeypatch):
    import stech_mcp.server as server

    def fail(**kwargs):
        raise ValueError("unsupported source_type 'X'")

    monkeypatch.setattr(server.product_field_verification_service, "verify", fail)

    result = server.product_field_verify(
        partnumber="PN-1",
        field_code="ean",
        confidence_grade="B",
        source_url="https://example.com/p",
        source_type="X",
        source_partnumber="PN-1",
        evidence_text="evidence",
        value_text="4006381333931",
    )

    assert result["verified"] is False
    assert result["status"] == "VALIDATION_ERROR"
    assert result["retryable"] is True
    assert "unsupported source_type" in result["error"]


def test_research_record_returns_controlled_validation_error(monkeypatch):
    import stech_mcp.server as server

    def fail(**kwargs):
        raise ValueError("bad research payload")

    monkeypatch.setattr(server.product_identity_research_service, "record", fail)

    result = server.product_identity_research_record(
        producto_distribuidor_id=1,
        partnumber="PN-1",
        identifier_type="EAN",
        status="VERIFIED",
    )

    assert result["recorded"] is False
    assert result["status"] == "VALIDATION_ERROR"
    assert result["retryable"] is True
