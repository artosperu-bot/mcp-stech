from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_product_image_hash_dedup_is_scoped_to_partnumber_and_variant():
    sql = (ROOT / "sql" / "003_product_workspace_v1.sql").read_text(encoding="utf-8")

    assert "UX_product_image_partnumber_hash_variant" in sql
    assert "ON dbo.product_image(partnumber, sha256_hash, variant_type)" in sql
    assert "CREATE UNIQUE INDEX UX_product_image_sha256_notnull\n        ON dbo.product_image(sha256_hash)" not in sql


def test_workspace_schema_is_additive_and_contains_required_entities():
    sql = (ROOT / "sql" / "003_product_workspace_v1.sql").read_text(encoding="utf-8")

    for name in (
        "dbo.product_master",
        "dbo.channel_draft",
        "dbo.channel_draft_field",
        "dbo.product_image",
        "dbo.product_audit_event",
        "dbo.V_PRODUCT_WORKSPACE_V1",
    ):
        assert name in sql
    assert "DROP TABLE" not in sql.upper()
