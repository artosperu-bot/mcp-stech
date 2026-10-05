from stech_mcp.services.research.research_planner import ResearchPlanner


def test_planner_only_queries_pending_fields_and_limits_queries_per_field():
    planner = ResearchPlanner(manufacturer_domains={"JBL": ("jbl.com",)})

    plan = planner.plan(
        "PN1",
        "JBL",
        "PORTABLE_SPEAKER",
        ["ip_rating", "speaker_power_w"],
    )

    assert len(plan) <= 4
    assert all(query.partnumber == "PN1" for query in plan)
    assert {query.field_code for query in plan} == {"ip_rating", "speaker_power_w"}
    assert all(len([x for x in plan if x.field_code == field]) <= 2 for field in {"ip_rating", "speaker_power_w"})
    joined = " ".join(query.query for query in plan)
    assert "PN1" in joined
    assert "IP" in joined.upper()
    assert "RAM" not in joined.upper()
    assert plan[0].domains == ("jbl.com",)


def test_planner_dedupes_pending_fields_and_uses_exact_partnumber_quotes():
    planner = ResearchPlanner()
    plan = planner.plan(" 82YU00XYLM ", "LENOVO", "LAPTOP", ["ram_gb", "RAM_GB"])

    assert len(plan) <= 2
    assert all('"82YU00XYLM"' in query.query for query in plan)
    assert all(query.field_code == "ram_gb" for query in plan)
