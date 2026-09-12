from stech_mcp.services.product_fact_resolver import ProductFactResolver


class Products:
    def get_by_partnumber(self, partnumber):
        if partnumber != "PN1":
            return None
        return {
            "part_number": "PN1",
            "marca": "LENOVO",
            "category_code": "LAPTOP",
        }


class Enrichments:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def get_approved(self, partnumber, field_codes=None):
        assert partnumber == "PN1"
        rows = list(self.rows)
        if field_codes:
            wanted = set(field_codes)
            rows = [row for row in rows if row.get("field_code") in wanted]
        return rows


class Deltron:
    def __init__(self, candidates=None):
        self.candidates = list(candidates or [])

    def adapt(self, product, *, category_code):
        assert product["part_number"] == "PN1"
        assert category_code == "LAPTOP"
        return list(self.candidates)


class Candidates:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def list_for_product(self, partnumber):
        return list(self.rows)


def _deltron(field_code, value):
    return {
        "field_code": field_code,
        "normalized_value": value,
        "source_type": "AUTHORIZED_DISTRIBUTOR",
        "source_name": "DELTRON",
        "source_partnumber": "PN1",
        "confidence_rank": "B",
    }


def _resolver(*, enrichments=None, deltron=None, candidates=None, policy=None):
    return ProductFactResolver(
        product_repository=Products(),
        enrichment_repository=Enrichments(enrichments),
        deltron_adapter=Deltron(deltron),
        fact_candidate_repository=Candidates(candidates),
        field_policy=policy or {},
    )


def test_manual_approved_value_wins_over_distributor_value():
    resolver = _resolver(
        enrichments=[
            {
                "field_code": "ram_gb",
                "value_number": 16,
                "method": "MANUAL",
                "confidence_grade": "A1",
                "is_approved": True,
            }
        ],
        deltron=[_deltron("ram_gb", 8)],
    )

    result = resolver.resolve("PN1", ["ram_gb"], "LAPTOP")
    fact = result.facts["ram_gb"]

    assert fact.state == "RESOLVED"
    assert fact.value == 16
    assert fact.method == "MANUAL"
    assert fact.source == "APPROVED_ENRICHMENT"


def test_deltron_is_used_when_exact_field_has_no_approved_value():
    resolver = _resolver(deltron=[_deltron("ram_gb", 16)])

    fact = resolver.resolve("PN1", ["ram_gb"], "LAPTOP").facts["ram_gb"]

    assert fact.state == "RESOLVED"
    assert fact.value == 16
    assert fact.method == "DISTRIBUTOR"
    assert fact.source == "DELTRON"


def test_two_strong_different_sources_create_conflict_without_explicit_precedence():
    resolver = _resolver(
        enrichments=[
            {
                "field_code": "memory_speed_mhz",
                "value_number": 5500,
                "method": "VERIFIED",
                "confidence_grade": "A1",
                "is_approved": True,
            }
        ],
        deltron=[_deltron("memory_speed_mhz", 4800)],
    )

    fact = resolver.resolve("PN1", ["memory_speed_mhz"], "LAPTOP").facts[
        "memory_speed_mhz"
    ]

    assert fact.state == "CONFLICT"
    assert fact.value is None
    assert set(fact.alternatives) == {"4800", "5500"}


def test_explicit_deltron_authoritative_policy_resolves_and_keeps_discrepancy():
    resolver = _resolver(
        enrichments=[
            {
                "field_code": "memory_speed_mhz",
                "value_number": 5500,
                "method": "VERIFIED",
                "confidence_grade": "A1",
                "is_approved": True,
            }
        ],
        deltron=[_deltron("memory_speed_mhz", 4800)],
        policy={"memory_speed_mhz": "DELTRON_AUTHORITATIVE"},
    )

    fact = resolver.resolve("PN1", ["memory_speed_mhz"], "LAPTOP").facts[
        "memory_speed_mhz"
    ]

    assert fact.state == "RESOLVED"
    assert fact.value == 4800
    assert fact.source == "DELTRON"
    assert fact.policy_code == "DELTRON_AUTHORITATIVE"
    assert fact.alternatives == ("5500",)


def test_missing_field_is_explicit_and_commercial_fields_are_rejected():
    resolver = _resolver()

    result = resolver.resolve(
        "PN1",
        ["battery_wh", "price", "stock", "cost", "promotion"],
        "LAPTOP",
    )

    assert result.facts["battery_wh"].state == "MISSING"
    assert set(result.rejected_fields) == {"price", "stock", "cost", "promotion"}
    assert not ({"price", "stock", "cost", "promotion"} & set(result.facts))


def test_existing_conflict_candidate_marks_field_conflict():
    resolver = _resolver(
        deltron=[_deltron("ram_gb", 16)],
        candidates=[
            {
                "field_code": "ram_gb",
                "normalized_value": 8,
                "state": "CONFLICT",
                "confidence_rank": "A1",
            }
        ],
    )

    fact = resolver.resolve("PN1", ["ram_gb"], "LAPTOP").facts["ram_gb"]

    assert fact.state == "CONFLICT"
