import pytest

from stech_mcp.services.product_identity_promotion import ProductIdentityPromotionService


class FakeEnrichmentRepository:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def get_approved(self, partnumber, field_codes=None):
        self.calls.append((partnumber, field_codes))
        return [row for row in self.rows if not field_codes or row["field_code"] in field_codes]


class FakeIdentityRepository:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]
        self.promotions = []

    def list_by_partnumber(self, partnumber):
        return [dict(row) for row in self.rows if row["part_number"] == partnumber]

    def promote_missing_identifier(self, *, partnumber, target_field, value, confidence, source):
        self.promotions.append((partnumber, target_field, value, confidence, source))
        changed = 0
        for row in self.rows:
            if row["part_number"] == partnumber and not str(row.get(target_field) or "").strip():
                row[target_field] = value
                row["identity_confidence"] = confidence
                row["identity_source"] = source
                changed += 1
        return changed


class FakeAuditRepository:
    def __init__(self):
        self.events = []

    def add_audit_event(self, **kwargs):
        self.events.append(kwargs)


def build_service(enrichments, operational_rows):
    identity = FakeIdentityRepository(operational_rows)
    audit = FakeAuditRepository()
    service = ProductIdentityPromotionService(
        enrichment_repository=FakeEnrichmentRepository(enrichments),
        identity_repository=identity,
        audit_repository=audit,
    )
    return service, identity, audit


def test_promotes_verified_exact_ean_to_all_blank_operational_rows():
    service, identity, audit = build_service(
        [{
            "enrichment_id": 123,
            "partnumber": "EP-T2510NBEGWW",
            "field_code": "ean",
            "value_text": "8806094899528",
            "value_number": None,
            "method": "VERIFIED",
            "confidence_grade": "B",
            "is_approved": True,
        }],
        [
            {"producto_distribuidor_id": 1, "part_number": "EP-T2510NBEGWW", "ean": None, "upc": None},
            {"producto_distribuidor_id": 2, "part_number": "EP-T2510NBEGWW", "ean": "", "upc": None},
        ],
    )

    result = service.promote("EP-T2510NBEGWW", "EAN", approved_by="CHATGPT")

    assert result["status"] == "PROMOTED"
    assert result["value"] == "8806094899528"
    assert result["updated_count"] == 2
    assert identity.promotions[0][1:4] == ("ean", "8806094899528", 80)
    assert audit.events[-1]["event_type"] == "IDENTIFIER_PROMOTED"


def test_blocks_when_operational_identity_conflicts():
    service, identity, audit = build_service(
        [{
            "enrichment_id": 123,
            "partnumber": "EP-T2510NBEGWW",
            "field_code": "ean",
            "value_text": "8806094899528",
            "method": "VERIFIED",
            "confidence_grade": "B",
            "is_approved": True,
        }],
        [{"producto_distribuidor_id": 1, "part_number": "EP-T2510NBEGWW", "ean": "8806094899999", "upc": None}],
    )

    result = service.promote("EP-T2510NBEGWW", "ean")

    assert result["status"] == "OPERATIONAL_CONFLICT"
    assert identity.promotions == []
    assert audit.events[-1]["event_type"] == "IDENTIFIER_PROMOTION_BLOCKED"


def test_rejects_unverified_or_low_confidence_enrichment():
    service, identity, _ = build_service(
        [{
            "enrichment_id": 1,
            "partnumber": "PN1",
            "field_code": "ean",
            "value_text": "8806094899528",
            "method": "ESTIMATED",
            "confidence_grade": "E",
            "is_approved": True,
        }],
        [{"producto_distribuidor_id": 1, "part_number": "PN1", "ean": None, "upc": None}],
    )

    with pytest.raises(ValueError, match="VERIFIED"):
        service.promote("PN1", "ean")
    assert identity.promotions == []


def test_gtin12_promotes_to_upc_but_gtin14_is_not_mapped_to_operational_columns():
    service, identity, _ = build_service(
        [{
            "enrichment_id": 2,
            "partnumber": "PN2",
            "field_code": "gtin",
            "value_text": "036000291452",
            "method": "VERIFIED",
            "confidence_grade": "A1",
            "is_approved": True,
        }],
        [{"producto_distribuidor_id": 2, "part_number": "PN2", "ean": None, "upc": None}],
    )
    result = service.promote("PN2", "gtin")
    assert result["target_field"] == "upc"
    assert identity.promotions[0][1] == "upc"

    service14, identity14, _ = build_service(
        [{
            "enrichment_id": 3,
            "partnumber": "PN14",
            "field_code": "gtin",
            "value_text": "10012345678902",
            "method": "VERIFIED",
            "confidence_grade": "A1",
            "is_approved": True,
        }],
        [{"producto_distribuidor_id": 3, "part_number": "PN14", "ean": None, "upc": None}],
    )
    result14 = service14.promote("PN14", "gtin")
    assert result14["status"] == "UNSUPPORTED_OPERATIONAL_GTIN"
    assert identity14.promotions == []
