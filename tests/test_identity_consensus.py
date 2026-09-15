from stech_mcp.services.identity_consensus import evaluate_identity_consensus


def candidate(value, source_type, url, *, field="upc", grade="B", pn="PN-001"):
    return {
        "field_code": field,
        "normalized_value": value,
        "canonical_gtin": str(value).zfill(14),
        "source_type": source_type,
        "source_url": url,
        "source_partnumber": pn,
        "confidence_rank": grade,
    }


def test_primary_manufacturer_exact_candidate_is_promotable():
    rows = [candidate("036602301972", "MANUFACTURER", "https://psref.lenovo.com/p", grade="A1")]
    result = evaluate_identity_consensus("PN-001", rows)
    assert result["decision"] == "PROMOTED"
    assert result["promotable_candidates"] == rows
    assert result["evidence_summary"]["has_primary"] is True


def test_two_independent_strong_sources_with_authorized_distributor_promote():
    rows = [
        candidate("036602301972", "AUTHORIZED_DISTRIBUTOR", "https://www.deltron.com.pe/p"),
        candidate("036602301972", "AUTHORIZED_DISTRIBUTOR", "https://pe.ingrammicro.com/p"),
    ]
    result = evaluate_identity_consensus("PN-001", rows)
    assert result["decision"] == "PROMOTED"
    assert len(result["promotable_candidates"]) == 2
    assert result["evidence_summary"]["strong_source_count"] == 2
    assert result["evidence_summary"]["has_authorized_distributor"] is True


def test_two_retailers_never_promote_even_when_they_agree():
    rows = [
        candidate("036602301972", "TRUSTED_RETAILER", "https://simple.ripley.com.pe/p", grade="C"),
        candidate("036602301972", "TRUSTED_RETAILER", "https://www.falabella.com.pe/p", grade="C"),
    ]
    result = evaluate_identity_consensus("PN-001", rows)
    assert result["decision"] == "CANDIDATE"
    assert result["promotable_candidates"] == []


def test_single_authorized_distributor_is_candidate_not_promoted():
    rows = [candidate("036602301972", "AUTHORIZED_DISTRIBUTOR", "https://www.deltron.com.pe/p")]
    result = evaluate_identity_consensus("PN-001", rows)
    assert result["decision"] == "CANDIDATE"
    assert result["promotable_candidates"] == []


def test_conflicting_strong_gtins_require_review():
    rows = [
        candidate("036602301972", "AUTHORIZED_DISTRIBUTOR", "https://www.deltron.com.pe/a"),
        candidate("740617352214", "AUTHORIZED_DISTRIBUTOR", "https://pe.ingrammicro.com/b"),
    ]
    result = evaluate_identity_consensus("PN-001", rows)
    assert result["decision"] == "CONFLICT"
    assert result["promotable_candidates"] == []
    assert result["conflicts"]


def test_partnumber_mismatch_is_not_eligible_for_consensus():
    rows = [candidate("036602301972", "MANUFACTURER", "https://psref.lenovo.com/p", grade="A1", pn="OTHER")]
    result = evaluate_identity_consensus("PN-001", rows)
    assert result["decision"] == "CANDIDATE"
    assert result["promotable_candidates"] == []
