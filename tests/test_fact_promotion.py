from stech_mcp.services.fact_promotion import FactPromotionService


class FakeVerificationService:
    def __init__(self):
        self.calls = []

    def verify(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "verified": True,
            "preserved_manual": False,
            "field_code": kwargs["field_code"],
            "confidence_grade": kwargs["confidence_grade"],
        }


class FakeCandidateRepository:
    def __init__(self):
        self.states = []

    def update_state(self, candidate_id, state):
        self.states.append((candidate_id, state))
        return {"product_fact_candidate_id": candidate_id, "state": state}


class FakeEnrichmentRepository:
    def __init__(self, approved=None):
        self.approved = list(approved or [])

    def get_approved(self, partnumber, field_codes=None):
        rows = [row for row in self.approved if row["partnumber"] == partnumber]
        if field_codes:
            rows = [row for row in rows if row["field_code"] in field_codes]
        return rows


def candidate(field_code, value, *, rank, source_partnumber="PN1", source_type=None, candidate_id=None):
    source_by_rank = {
        "A1": "MANUFACTURER",
        "A2": "OFFICIAL_DOCUMENT",
        "B": "AUTHORIZED_DISTRIBUTOR",
        "C": "TRUSTED_RETAILER",
    }
    return {
        "product_fact_candidate_id": candidate_id,
        "field_code": field_code,
        "normalized_value": value,
        "unit": None,
        "confidence_rank": rank,
        "source_type": source_type or source_by_rank[rank],
        "source_url": f"https://source.example/{field_code}",
        "source_partnumber": source_partnumber,
        "evidence_text": f"{field_code} = {value}",
    }


def build_service(approved=None):
    verification = FakeVerificationService()
    candidate_repo = FakeCandidateRepository()
    service = FactPromotionService(
        verification_service=verification,
        enrichment_repository=FakeEnrichmentRepository(approved),
        candidate_repository=candidate_repo,
    )
    return service, verification, candidate_repo


def test_exact_manufacturer_beats_authorized_distributor():
    service, verification, candidate_repo = build_service()
    result = service.evaluate_and_promote("PN1", [
        candidate("bluetooth_version", "5.3", rank="B", candidate_id=1),
        candidate("bluetooth_version", "5.4", rank="A1", candidate_id=2),
    ])

    assert result["promoted"]["bluetooth_version"] == "5.4"
    assert verification.calls[0]["confidence_grade"] == "A1"
    assert (2, "PROMOTED") in candidate_repo.states
    assert (1, "REJECTED") in candidate_repo.states


def test_variant_sensitive_other_pn_is_rejected_before_verification():
    service, verification, candidate_repo = build_service()
    result = service.evaluate_and_promote("PN1", [
        candidate("ram_gb", 16, rank="A1", source_partnumber="PN2", candidate_id=7),
    ])

    assert "ram_gb" not in result["promoted"]
    assert result["rejected"][0]["reason"] == "SOURCE_PARTNUMBER_MISMATCH"
    assert verification.calls == []
    assert candidate_repo.states == [(7, "REJECTED")]


def test_existing_approved_a1_is_not_downgraded_by_b_or_c():
    approved = [{
        "partnumber": "PN1",
        "field_code": "bluetooth_version",
        "value_text": "5.4",
        "value_number": None,
        "method": "VERIFIED",
        "confidence_grade": "A1",
        "is_approved": True,
    }]
    service, verification, candidate_repo = build_service(approved)
    result = service.evaluate_and_promote("PN1", [
        candidate("bluetooth_version", "5.3", rank="B", candidate_id=3),
        candidate("bluetooth_version", "5.2", rank="C", candidate_id=4),
    ])

    assert result["promoted"] == {}
    assert result["preserved"]["bluetooth_version"] == "5.4"
    assert verification.calls == []
    assert set(candidate_repo.states) == {(3, "REJECTED"), (4, "REJECTED")}


def test_existing_manual_is_never_overwritten_automatically():
    approved = [{
        "partnumber": "PN1",
        "field_code": "ip_rating",
        "value_text": "IP68",
        "value_number": None,
        "method": "MANUAL",
        "confidence_grade": "A1",
        "is_approved": True,
    }]
    service, verification, candidate_repo = build_service(approved)
    result = service.evaluate_and_promote("PN1", [
        candidate("ip_rating", "IP67", rank="A1", candidate_id=5),
    ])

    assert result["promoted"] == {}
    assert result["preserved"]["ip_rating"] == "IP68"
    assert verification.calls == []
    assert candidate_repo.states == [(5, "REJECTED")]


def test_equal_strength_different_values_become_review_required_conflict():
    service, verification, candidate_repo = build_service()
    result = service.evaluate_and_promote("PN1", [
        candidate("ip_rating", "IP67", rank="A1", candidate_id=10),
        candidate("ip_rating", "IP68", rank="A1", candidate_id=11),
    ])

    assert result["promoted"] == {}
    assert result["state"] == "REVIEW_REQUIRED"
    assert result["conflicts"][0]["field_code"] == "ip_rating"
    assert verification.calls == []
    assert set(candidate_repo.states) == {(10, "CONFLICT"), (11, "CONFLICT")}
