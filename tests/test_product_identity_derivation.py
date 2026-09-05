from stech_mcp.services.product_identity_derivation import ProductIdentityDerivationService


class FakeIdentityRepository:
    def __init__(self, rows):
        self.rows = rows
        self.promotions = []
        self.pages = []

    def list_by_partnumber(self, partnumber):
        return [dict(row) for row in self.rows]

    def promote_missing_identifier(self, **kwargs):
        self.promotions.append(kwargs)
        target = kwargs["target_field"]
        for row in self.rows:
            if not row.get(target):
                row[target] = kwargs["value"]
        return sum(1 for _ in self.rows)

    def list_missing_identifiers(self, **kwargs):
        if self.pages:
            return self.pages.pop(0)
        return {"products": [], "count": 0, "has_more": False, "next_after_id": kwargs.get("after_id", 0)}

    def partnumber_collision_stats(self, partnumbers):
        return {pn: {"active_row_count": 1, "active_brand_count": 1} for pn in partnumbers}


class FakeAuditRepository:
    def __init__(self):
        self.events = []

    def add_audit_event(self, **kwargs):
        self.events.append(kwargs)


def make_service(rows):
    identity = FakeIdentityRepository(rows)
    audit = FakeAuditRepository()
    return ProductIdentityDerivationService(identity_repository=identity, audit_repository=audit), identity, audit


def test_derives_ean13_from_existing_valid_upc_without_web_research():
    service, identity, audit = make_service([
        {
            "producto_distribuidor_id": 904,
            "distribuidor_codigo": "DELTRON",
            "part_number": "SPSD/2TB",
            "marca": "KINGSTON",
            "ean": None,
            "upc": "740617352214",
        }
    ])

    result = service.derive_for_partnumber("SPSD/2TB")

    assert result["status"] == "DERIVED"
    assert result["derived"]["ean"] == "0740617352214"
    assert identity.promotions[0]["target_field"] == "ean"
    assert identity.promotions[0]["value"] == "0740617352214"
    assert "DERIVED_GTIN_EQUIVALENCE" in identity.promotions[0]["source"]
    assert audit.events[-1]["event_type"] == "IDENTIFIER_EQUIVALENT_DERIVED"


def test_derives_upc_from_zero_prefixed_ean13():
    service, identity, _ = make_service([
        {
            "producto_distribuidor_id": 905,
            "distribuidor_codigo": "DELTRON",
            "part_number": "SXS1000/1000G",
            "marca": "KINGSTON",
            "ean": "0740617338515",
            "upc": None,
        }
    ])

    result = service.derive_for_partnumber("SXS1000/1000G")

    assert result["status"] == "DERIVED"
    assert result["derived"]["upc"] == "740617338515"
    assert identity.promotions[0]["target_field"] == "upc"


def test_non_zero_prefixed_ean_does_not_invent_upc():
    service, identity, _ = make_service([
        {
            "producto_distribuidor_id": 1,
            "distribuidor_codigo": "DELTRON",
            "part_number": "SAMSUNG",
            "marca": "SAMSUNG",
            "ean": "8806094899528",
            "upc": None,
        }
    ])

    result = service.derive_for_partnumber("SAMSUNG")

    assert result["status"] == "NO_DERIVATION"
    assert identity.promotions == []


def test_invalid_existing_identifier_blocks_derivation():
    service, identity, _ = make_service([
        {
            "producto_distribuidor_id": 1,
            "distribuidor_codigo": "DELTRON",
            "part_number": "BAD-PN",
            "marca": "KINGSTON",
            "ean": None,
            "upc": "740617352215",
        }
    ])

    result = service.derive_for_partnumber("BAD-PN")

    assert result["status"] == "INVALID_EXISTING_IDENTIFIER"
    assert identity.promotions == []


def test_multiple_brand_rows_block_derivation():
    service, identity, _ = make_service([
        {"producto_distribuidor_id": 1, "part_number": "DUP", "marca": "A", "ean": None, "upc": "740617352214"},
        {"producto_distribuidor_id": 2, "part_number": "DUP", "marca": "B", "ean": None, "upc": "740617352214"},
    ])

    result = service.derive_for_partnumber("DUP")

    assert result["status"] == "IDENTITY_CONFLICT"
    assert identity.promotions == []
