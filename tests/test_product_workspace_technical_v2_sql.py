from pathlib import Path


def test_product_workspace_v2_exposes_only_approved_technical_facts_without_commercial_writes():
    sql = Path("sql/009_product_workspace_technical_v2.sql").read_text(encoding="utf-8")
    upper = sql.upper()

    assert "V_PRODUCT_WORKSPACE_TECHNICAL_FACT_V2" in upper
    assert "PRODUCT_ENRICHMENT" in upper
    assert "IS_APPROVED = 1" in upper
    assert "FIELD_CODE" in upper
    assert "VALUE_TEXT" in upper
    assert "VALUE_NUMBER" in upper
    assert "SOURCE_PRICE_USD_SIN_IGV" in upper
    assert "SOURCE_STOCK_VALUE" in upper
    assert "UPDATE DBO.PRODUCT_MASTER" not in upper
    assert "UPDATE DBO.PRODUCT_ENRICHMENT" not in upper
