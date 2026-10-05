from pathlib import Path

SQL = Path(__file__).parents[1] / "sql" / "010_product_image_research_v2.sql"


def test_image_research_schema_is_additive_and_persistent():
    text = SQL.read_text(encoding="utf-8")
    upper = text.upper()
    assert "PRODUCT_IMAGE_CANDIDATE" in upper
    assert "IMAGE_REQUIREMENT_POLICY" in upper
    for state in ("PENDING", "VERIFIED", "REJECTED", "CONFLICT", "IMPORTED"):
        assert state in upper
    assert "DROP TABLE DBO.PRODUCT_IMAGE" not in upper
    assert "DELETE FROM DBO.PRODUCT_IMAGE" not in upper
    assert "UX_PRODUCT_IMAGE_CANDIDATE_URL" in upper


def test_master_image_policy_has_safe_seed():
    text = SQL.read_text(encoding="utf-8").upper()
    assert "N'MASTER'" in text
    assert "N'DEFAULT'" in text
    assert "EXACT_PN_REQUIRED" in text