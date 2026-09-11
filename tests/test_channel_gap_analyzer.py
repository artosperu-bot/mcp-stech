from stech_mcp.services.channel_gap_analyzer import ChannelGapAnalyzer


def test_not_configured_when_channel_has_no_requirements():
    class Requirements:
        def get(self, *args, **kwargs):
            return None

    result = ChannelGapAnalyzer(
        requirement_repository=Requirements(),
        technical_status_service=object(),
        image_readiness_service=object(),
    ).get("PN1", "FALABELLA", "LAPTOP")
    assert result["state"] == "NOT_CONFIGURED"


def test_required_missing_field_and_images_make_incomplete():
    class Requirements:
        def get(self, *args, **kwargs):
            return {
                "channel_code": "FALABELLA",
                "category_code": "LAPTOP",
                "version_code": "V2",
                "fields": [
                    {"target_field_code": "cpu_model", "master_field_code": "cpu_model", "requirement": "REQUIRED", "data_scope": "TECHNICAL"},
                    {"target_field_code": "plug_type", "master_field_code": "plug_type", "requirement": "REQUIRED", "data_scope": "TECHNICAL"},
                    {"target_field_code": "sale_price", "master_field_code": None, "requirement": "REQUIRED", "data_scope": "COMMERCIAL"},
                ],
            }

    class Technical:
        def get(self, pn):
            return {"known_fields": {"cpu_model": "Ryzen 5"}, "conflicts": [], "completion_pct": 50}

    class Images:
        def get(self, *args, **kwargs):
            return {"state": "INCOMPLETE", "image_count": 1, "required_min": 3, "missing_reasons": ["required_count_not_met"]}

    result = ChannelGapAnalyzer(
        requirement_repository=Requirements(),
        technical_status_service=Technical(),
        image_readiness_service=Images(),
    ).get("PN1", "FALABELLA", "LAPTOP")
    assert result["state"] == "INCOMPLETE"
    by_field = {row["target_field_code"]: row for row in result["fields"]}
    assert by_field["cpu_model"]["state"] == "COMPLETE"
    assert by_field["cpu_model"]["status"] == "COMPLETE"
    assert by_field["plug_type"]["state"] == "MISSING"
    assert by_field["sale_price"]["state"] == "CHANNEL_INPUT"
    assert result["image_readiness"]["state"] == "INCOMPLETE"
    assert result["missing_count"] == 1
    assert result["conflict_count"] == 0
    assert result["completion_pct"] == 33


def test_required_conflict_blocks_even_if_other_fields_complete():
    class Requirements:
        def get(self, *args, **kwargs):
            return {
                "version_code": "V2",
                "fields": [
                    {"target_field_code": "ram_gb", "master_field_code": "ram_gb", "requirement": "REQUIRED", "data_scope": "TECHNICAL"}
                ],
            }

    class Technical:
        def get(self, pn):
            return {"known_fields": {"ram_gb": 16}, "conflicts": ["ram_gb"], "completion_pct": 100}

    class Images:
        def get(self, *args, **kwargs):
            return {"state": "READY", "image_count": 4, "required_min": 1, "missing_reasons": []}

    result = ChannelGapAnalyzer(
        requirement_repository=Requirements(),
        technical_status_service=Technical(),
        image_readiness_service=Images(),
    ).get("PN1", "FALABELLA", "LAPTOP")
    assert result["state"] == "BLOCKED_CONFLICT"
