from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _sql():
    return (ROOT / "sql" / "005_identity_research_queue_v1.sql").read_text(encoding="utf-8")


def test_identity_research_schema_is_additive_and_idempotent():
    sql = _sql().upper()

    assert "OBJECT_ID(N'DBO.PRODUCT_IDENTITY_RESEARCH', N'U') IS NULL" in sql
    assert "CREATE TABLE DBO.PRODUCT_IDENTITY_RESEARCH" in sql
    assert "DROP TABLE" not in sql


def test_identity_research_schema_supports_terminal_and_retry_states():
    sql = _sql()

    for state in (
        "PENDING",
        "RESEARCHING",
        "VERIFIED",
        "PROMOTED",
        "NO_ENCONTRADO",
        "RESEARCH_REQUIRED",
        "CONFLICTO",
        "INVALID_IDENTITY",
        "ERROR",
    ):
        assert state in sql


def test_identity_research_schema_is_isolated_from_stock_history():
    sql = _sql().upper()

    assert "HST_PRODUCTO_OBSERVACION" not in sql
    assert "STOCK" not in sql
    assert "PRECIO" not in sql
