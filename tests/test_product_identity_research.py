from stech_mcp.services.product_identity_research import (
    ProductIdentityResearchService,
    classify_partnumber,
)


class FakeIdentityRepository:
    def __init__(self):
        self.pages = [
            {
                "products": [
                    {
                        "producto_distribuidor_id": 10,
                        "part_number": "PN-10",
                        "marca": "KINGSTON",
                        "nombre": "Valid product",
                        "ean": None,
                        "upc": None,
                        "distribuidor_codigo": "DELTRON",
                    },
                    {
                        "producto_distribuidor_id": 11,
                        "part_number": "N/A",
                        "marca": "GENERIC",
                        "nombre": "Placeholder",
                        "ean": None,
                        "upc": None,
                        "distribuidor_codigo": "DELTRON",
                    },
                    {
                        "producto_distribuidor_id": 12,
                        "part_number": "PN-12",
                        "marca": "KINGSTON",
                        "nombre": "Already researched",
                        "ean": None,
                        "upc": None,
                        "distribuidor_codigo": "DELTRON",
                    },
                ],
                "count": 3,
                "has_more": False,
                "next_after_id": 12,
            }
        ]

    def list_missing_identifiers(self, **kwargs):
        return self.pages.pop(0) if self.pages else {
            "products": [], "count": 0, "has_more": False, "next_after_id": kwargs.get("after_id", 0)
        }


class FakeResearchRepository:
    def __init__(self):
        self.saved = []
        self.states = {
            (12, "EAN"): {"status": "NO_ENCONTRADO"},
            (12, "UPC"): {"status": "NO_ENCONTRADO"},
        }

    def get_for_product_ids(self, product_ids):
        return {key: value for key, value in self.states.items() if key[0] in set(product_ids)}

    def upsert(self, **kwargs):
        self.saved.append(kwargs)
        self.states[(kwargs["producto_distribuidor_id"], kwargs["identifier_type"])] = kwargs
        return kwargs

    def summary(self, partnumber=None):
        return {"total": len(self.states), "by_status": {"NO_ENCONTRADO": 2}}


class FakeVerificationService:
    def __init__(self):
        self.calls = []

    def verify(self, **kwargs):
        self.calls.append(kwargs)
        return {"verified": True, "enrichment_id": 77, "confidence_grade": kwargs["confidence_grade"]}


class FakePromotionService:
    def __init__(self, result=None):
        self.calls = []
        self.result = result or {
            "found": True,
            "promoted": True,
            "status": "PROMOTED",
            "updated_count": 1,
            "value": "4006381333931",
        }

    def promote(self, partnumber, identifier_type, approved_by="CHATGPT"):
        self.calls.append((partnumber, identifier_type, approved_by))
        return dict(self.result)


def make_service(promotion_result=None):
    research = FakeResearchRepository()
    verify = FakeVerificationService()
    promote = FakePromotionService(promotion_result)
    service = ProductIdentityResearchService(
        identity_repository=FakeIdentityRepository(),
        research_repository=research,
        verification_service=verify,
        promotion_service=promote,
    )
    return service, research, verify, promote


def test_classify_partnumber_rejects_catalog_placeholders():
    assert classify_partnumber("N/A")[0] is False
    assert classify_partnumber("Cerrar")[0] is False
    assert classify_partnumber(" null ")[0] is False
    assert classify_partnumber("SXS1000/1000G") == (True, None)


def test_queue_skips_terminal_research_and_auto_marks_invalid_identity():
    service, research, _, _ = make_service()

    result = service.queue(after_id=0, limit=100)

    assert result["count"] == 1
    assert result["products"][0]["part_number"] == "PN-10"
    assert result["products"][0]["pending_identifiers"] == ["EAN", "UPC"]
    assert any(row["producto_distribuidor_id"] == 11 and row["status"] == "INVALID_IDENTITY" for row in research.saved)
    assert result["skipped_terminal_count"] == 1
    assert result["invalid_identity_count"] == 1


def test_record_verified_outcome_verifies_promotes_and_persists_promoted_state():
    service, research, verify, promote = make_service()

    result = service.record(
        producto_distribuidor_id=10,
        partnumber="PN-10",
        identifier_type="EAN",
        status="VERIFIED",
        value_text="4006381333931",
        confidence_grade="A1",
        source_url="https://manufacturer.example/pn-10",
        source_type="OFFICIAL_WEBSITE",
        source_partnumber="PN-10",
        evidence_text="Exact PN and EAN",
        approved_by="CHATGPT",
    )

    assert result["status"] == "PROMOTED"
    assert verify.calls[0]["field_code"] == "ean"
    assert promote.calls == [("PN-10", "EAN", "CHATGPT")]
    assert research.saved[-1]["status"] == "PROMOTED"
    assert research.saved[-1]["value_text"] == "4006381333931"


def test_record_no_result_persists_terminal_status_without_verification():
    service, research, verify, promote = make_service()

    result = service.record(
        producto_distribuidor_id=10,
        partnumber="PN-10",
        identifier_type="UPC",
        status="NO_ENCONTRADO",
        note="No strong exact-PN evidence after bounded search",
    )

    assert result["status"] == "NO_ENCONTRADO"
    assert verify.calls == []
    assert promote.calls == []
    assert research.saved[-1]["status"] == "NO_ENCONTRADO"


def test_record_operational_conflict_persists_conflict_status():
    conflict = {
        "found": True,
        "promoted": False,
        "status": "OPERATIONAL_CONFLICT",
        "value": "4006381333931",
        "conflicts": [{"current_value": "5901234123457"}],
    }
    service, research, _, _ = make_service(conflict)

    result = service.record(
        producto_distribuidor_id=10,
        partnumber="PN-10",
        identifier_type="EAN",
        status="VERIFIED",
        value_text="4006381333931",
        confidence_grade="A1",
        source_url="https://manufacturer.example/pn-10",
        source_type="MANUFACTURER",
        source_partnumber="PN-10",
        evidence_text="Exact PN and EAN",
    )

    assert result["status"] == "CONFLICTO"
    assert research.saved[-1]["status"] == "CONFLICTO"


def test_status_returns_repository_summary():
    service, _, _, _ = make_service()
    assert service.status()["total"] == 2
