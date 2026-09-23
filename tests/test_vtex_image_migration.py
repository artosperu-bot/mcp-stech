from pathlib import Path


def test_vtex_image_publication_migration_is_additive_and_idempotent():
    sql = (Path(__file__).resolve().parents[1] / "sql" / "004_vtex_image_publication.sql").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(sql.upper().split())

    assert "IF OBJECT_ID(N'DBO.PRODUCT_IMAGE_PUBLICATION', N'U') IS NULL" in normalized
    assert "CREATE TABLE DBO.PRODUCT_IMAGE_PUBLICATION" in normalized
    assert "PRODUCT_IMAGE_ID" in normalized
    assert "REMOTE_SKU_ID" in normalized
    assert "REMOTE_FILE_ID" in normalized
    assert "REMOTE_ARCHIVE_ID" in normalized
    assert "STATUS" in normalized
    assert "LAST_ERROR" in normalized
    assert "UNIQUE (CHANNEL, ACCOUNT_CODE, REMOTE_SKU_ID, PRODUCT_IMAGE_ID)" in normalized
    assert "FOREIGN KEY (PRODUCT_IMAGE_ID)" in normalized
    assert "REFERENCES DBO.PRODUCT_IMAGE(PRODUCT_IMAGE_ID)" in normalized
