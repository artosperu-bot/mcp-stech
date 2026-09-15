from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_product_work_result_json_migration_is_additive_and_idempotent():
    path = ROOT / "sql" / "013_product_work_result_json.sql"
    assert path.exists()
    sql = path.read_text(encoding="utf-8").upper()
    assert "COL_LENGTH" in sql
    assert "DBO.PRODUCT_WORK_ITEM" in sql
    assert "RESULT_JSON" in sql
    assert "NVARCHAR(MAX)" in sql
    assert "ALTER TABLE" in sql
    assert "DROP TABLE" not in sql
    assert "DELETE FROM" not in sql
