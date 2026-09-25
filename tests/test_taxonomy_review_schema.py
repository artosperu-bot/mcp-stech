from pathlib import Path


def test_taxonomy_review_migration_is_review_first():
    sql = Path("sql/013_taxonomy_review_queue.sql").read_text(encoding="utf-8")
    upper = sql.upper()

    assert "CREATE TABLE DBO.TAXONOMY_REVIEW" in upper
    assert "PRODUCTO_DISTRIBUIDOR_ID" in upper
    assert "PROPOSAL_KIND" in upper
    assert "NEW_CATEGORY" in upper
    assert "NEW_SUBCATEGORY" in upper
    assert "APPROVED" in upper
    assert "APPLIED" in upper
    assert "UPDATE DBO.PRD_PRODUCTO_DISTRIBUIDOR" not in upper
    assert "DELETE FROM" not in upper
    assert "TRUNCATE" not in upper
