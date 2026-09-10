from pathlib import Path


SQL = Path("sql/006_product_work_queue_v2.sql")


def test_product_work_schema_has_required_contract():
    text = SQL.read_text(encoding="utf-8").upper()
    for token in (
        "PRODUCT_WORK_JOB",
        "PRODUCT_WORK_ITEM",
        "PRODUCT_WORK_EVENT",
        "PRODUCT_WORK_ATTEMPT",
        "CONTEXT_HASH",
        "CLAIMED_BY",
        "CLAIM_EXPIRES_AT",
        "NEXT_ATTEMPT_AT",
        "FAILED_RETRYABLE",
        "ENRICH_TECHNICAL",
    ):
        assert token in text


def test_product_work_schema_does_not_reuse_vtex_loader_tables():
    text = SQL.read_text(encoding="utf-8").upper()
    assert "CREATE TABLE DBO.PRODUCT_LOADER_JOB" not in text
    assert "CREATE TABLE DBO.PRODUCT_LOADER_JOB_ITEM" not in text
    assert "ALTER TABLE DBO.PRODUCT_LOADER_JOB" not in text
    assert "ALTER TABLE DBO.PRODUCT_LOADER_JOB_ITEM" not in text


def test_active_work_unique_index_does_not_filter_on_computed_column():
    text = SQL.read_text(encoding="utf-8").upper()
    assert "WHERE ACTIVE_WORK_KEY IS NOT NULL" not in text
    assert "ON DBO.PRODUCT_WORK_ITEM(PARTNUMBER, CONTEXT_HASH)" in text
    assert "WHERE STATUS IN (" in text
    for state in (
        "QUEUED",
        "LOADING_SOURCE_DATA",
        "ANALYZING_MISSING_FIELDS",
        "RESEARCHING",
        "READING_DOCUMENTS",
        "VALIDATING",
        "PROMOTING_FACTS",
        "REBUILDING_PRODUCT_MASTER",
        "FAILED_RETRYABLE",
    ):
        assert f"N'{state}'" in text
