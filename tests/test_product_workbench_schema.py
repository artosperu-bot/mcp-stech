from pathlib import Path


def test_product_workbench_job_schema_has_required_tables_and_identity_fields():
    sql = Path("sql/005_product_workbench_jobs.sql").read_text(encoding="utf-8")

    for table in (
        "product_loader_job",
        "product_loader_job_item",
        "product_loader_job_event",
    ):
        assert table in sql

    lowered = sql.lower()
    for field in (
        "input_json",
        "row_number",
        "partnumber",
        "product_id_vtex",
        "sku_id_vtex",
        "product_ref_id_vtex",
        "sku_ref_id_vtex",
        "last_error_code",
        "last_error_detail",
    ):
        assert field in lowered

    assert "unique" in lowered
    assert "create index" in lowered
