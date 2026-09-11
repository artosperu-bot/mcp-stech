from stech_mcp.services.fact_extractor import FactExtractor


def test_extractor_returns_pending_evidence_not_approved_fact():
    extractor = FactExtractor()
    items = extractor.extract(
        {
            "url": "https://brand.example/spec",
            "source_type": "MANUFACTURER",
            "confidence_rank": "A1",
            "pages": [
                {"page": 1, "text": "PN1 Bluetooth 5.4, IP67, 30 W"},
            ],
        },
        ["bluetooth_version", "ip_rating", "speaker_power_w"],
        "PN1",
    )

    assert {item["field_code"] for item in items} == {
        "bluetooth_version",
        "ip_rating",
        "speaker_power_w",
    }
    values = {item["field_code"]: item["normalized_value"] for item in items}
    assert values["bluetooth_version"] == "5.4"
    assert values["ip_rating"] == "IP67"
    assert values["speaker_power_w"] == 30
    assert all(item["status"] == "PENDING" for item in items)
    assert all(item["evidence_text"] for item in items)
    assert all(item["source_partnumber"] == "PN1" for item in items)
    assert all(item["page_number"] == 1 for item in items)


def test_extractor_does_not_assign_exact_pn_when_page_does_not_contain_target():
    extractor = FactExtractor()
    items = extractor.extract(
        {
            "url": "https://brand.example/family",
            "source_type": "MANUFACTURER",
            "confidence_rank": "A1",
            "pages": [{"page": 1, "text": "Family specifications Bluetooth 5.4"}],
        },
        ["bluetooth_version"],
        "PN1",
    )

    assert len(items) == 1
    assert items[0]["source_partnumber"] is None


def test_extractor_leaves_ambiguous_multiple_power_values_missing():
    extractor = FactExtractor()
    items = extractor.extract(
        {
            "url": "https://brand.example/spec",
            "source_type": "OFFICIAL_DOCUMENT",
            "confidence_rank": "A2",
            "pages": [{"page": 2, "text": "PN1 output 20 W; adapter 65 W"}],
        },
        ["speaker_power_w"],
        "PN1",
    )

    assert items == []


def test_extractor_only_attempts_requested_fields():
    extractor = FactExtractor()
    items = extractor.extract(
        {
            "url": "https://brand.example/spec",
            "source_type": "MANUFACTURER",
            "confidence_rank": "A1",
            "pages": [{"page": 1, "text": "PN1 Bluetooth 5.4 IP67 30 W"}],
        },
        ["ip_rating"],
        "PN1",
    )

    assert [item["field_code"] for item in items] == ["ip_rating"]
