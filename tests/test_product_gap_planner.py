from stech_mcp.services.product_gap_planner import ProductGapPlanner
from stech_mcp.services.product_fact_resolver import FactResolution, ProductResolution


class Resolver:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def resolve(self, partnumber, field_codes, category_code):
        self.calls.append((partnumber, tuple(field_codes), category_code))
        return self.result


def _fact(field_code, state, value=None):
    return FactResolution(
        field_code=field_code,
        state=state,
        value=value,
        method="VERIFIED" if state == "RESOLVED" else None,
        source="OFFICIAL" if state == "RESOLVED" else None,
    )


def test_gap_planner_researches_only_missing_or_stale_fields():
    resolution = ProductResolution(
        partnumber="PN1",
        category_code="LAPTOP",
        facts={
            "ram_gb": _fact("ram_gb", "RESOLVED", 16),
            "battery_wh": _fact("battery_wh", "MISSING"),
            "wifi": _fact("wifi", "CONFLICT"),
            "os_name": _fact("os_name", "RESOLVED", "Windows 11"),
        },
        rejected_fields=(),
    )
    resolver = Resolver(resolution)
    planner = ProductGapPlanner(resolver)

    gaps = planner.plan(
        "pn1",
        "laptop",
        ["ram_gb", "battery_wh", "wifi", "os_name"],
        stale_fields=["os_name"],
    )

    assert [(gap.field_code, gap.reason, gap.action) for gap in gaps] == [
        ("battery_wh", "MISSING", "RESEARCH"),
        ("wifi", "CONFLICT", "REVIEW"),
        ("os_name", "STALE", "RESEARCH"),
    ]
    assert resolver.calls == [
        ("PN1", ("ram_gb", "battery_wh", "wifi", "os_name"), "LAPTOP")
    ]


def test_gap_planner_returns_empty_when_all_requested_facts_are_current():
    resolution = ProductResolution(
        partnumber="PN1",
        category_code="LAPTOP",
        facts={"ram_gb": _fact("ram_gb", "RESOLVED", 16)},
        rejected_fields=(),
    )

    gaps = ProductGapPlanner(Resolver(resolution)).plan(
        "PN1",
        "LAPTOP",
        ["ram_gb"],
    )

    assert gaps == []
