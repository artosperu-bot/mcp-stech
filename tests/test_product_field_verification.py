import pytest

from stech_mcp.services.product_field_verification import ProductFieldVerificationService


class FakeEnrichmentRepository:
    def __init__(self):
        self.upserts = []
        self.evidence = []

    def upsert(self, **kwargs):
        self.upserts.append(kwargs)
        return {"enrichment_id": 17, "preserved_manual": False, **kwargs}

    def add_evidence(self, **kwargs):
        self.evidence.append(kwargs)
        return {"evidence_id": 44, **kwargs}


def test_exact_official_evidence_persists_verified_variant_sensitive_field():
    repo = FakeEnrichmentRepository()
    service = ProductFieldVerificationService(repo)

    result = service.verify(
        partnumber="82yu00xylm",
        field_code="ssd_capacity_gb",
        value_number=512,
        unit="GB",
        confidence_grade="A1",
        source_url="https://psref.lenovo.com/Detail/Lenovo_V15_G4_AMN?M=82YU00XYLM",
        source_type="OFFICIAL_DOCUMENT",
        source_partnumber="82YU00XYLM",
        evidence_text="Storage 512GB SSD M.2 2242 PCIe 4.0x4 NVMe",
    )

    assert result["verified"] is True
    assert result["enrichment_id"] == 17
    assert result["evidence_id"] == 44
    assert repo.upserts[0]["partnumber"] == "82YU00XYLM"
    assert repo.upserts[0]["field_code"] == "ssd_capacity_gb"
    assert repo.upserts[0]["method"] == "VERIFIED"
    assert repo.upserts[0]["is_approved"] is True
    assert repo.evidence[0]["source_domain"] == "psref.lenovo.com"
    assert repo.evidence[0]["rank_score"] == 100


def test_variant_sensitive_field_rejects_non_exact_source_partnumber():
    service = ProductFieldVerificationService(FakeEnrichmentRepository())

    with pytest.raises(ValueError, match="exact source_partnumber"):
        service.verify(
            partnumber="82YU00XYLM",
            field_code="gpu_model",
            value_text="AMD Radeon 610M",
            confidence_grade="A1",
            source_url="https://example.com/spec",
            source_type="OFFICIAL_DOCUMENT",
            source_partnumber="82YU00OTHER",
            evidence_text="GPU Radeon 610M",
        )


def test_verified_non_manual_value_requires_real_evidence_url_and_text():
    service = ProductFieldVerificationService(FakeEnrichmentRepository())

    with pytest.raises(ValueError, match="source_url and evidence_text"):
        service.verify(
            partnumber="82YU00XYLM",
            field_code="warranty",
            value_text="1 año",
            confidence_grade="A2",
            source_type="OFFICIAL_DOCUMENT",
            source_partnumber="82YU00XYLM",
        )


def test_low_confidence_source_cannot_verify_variant_sensitive_field():
    service = ProductFieldVerificationService(FakeEnrichmentRepository())

    with pytest.raises(ValueError, match="A1, A2 or B"):
        service.verify(
            partnumber="82YU00XYLM",
            field_code="ssd_capacity_gb",
            value_number=512,
            confidence_grade="C",
            source_url="https://retailer.example/product",
            source_type="TRUSTED_RETAILER",
            source_partnumber="82YU00XYLM",
            evidence_text="512 GB SSD",
        )
