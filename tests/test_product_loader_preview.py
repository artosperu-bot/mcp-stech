from stech_mcp.services.product_loader_preview import preview_product_rows


def test_preview_normalizes_partnumber_and_flags_duplicate_without_side_effects():
    result = preview_product_rows(
        [
            {"row_number": 2, "partnumber": " 82yu00xylm ", "brand": "Lenovo"},
            {"row_number": 3, "partnumber": "82YU00XYLM", "brand": "Lenovo"},
        ],
        "carga.xlsx",
    )

    assert result["source_name"] == "carga.xlsx"
    assert result["rows"][0]["partnumber"] == "82YU00XYLM"
    assert result["rows"][0]["duplicate_in_file"] is False
    assert result["rows"][1]["duplicate_in_file"] is True
    assert result["has_blocking_errors"] is True
    assert result["error_count"] == 1
    assert result["errors"][0]["code"] == "DUPLICATE_PARTNUMBER"
    assert result["write_operations"] == 0


def test_preview_requires_exact_partnumber_and_preserves_excel_row_number():
    result = preview_product_rows(
        [
            {"row_number": 8, "partnumber": ""},
            {"row_number": 9, "partnumber": "ABC-123"},
        ],
        "productos.xlsx",
    )

    assert result["rows"][0]["row_number"] == 8
    assert result["errors"][0] == {
        "row_number": 8,
        "partnumber": "",
        "code": "PARTNUMBER_REQUIRED",
        "message": "Part Number requerido",
    }
    assert result["rows"][1]["partnumber"] == "ABC-123"


def test_preview_rejects_non_positive_vtex_category_and_brand_ids():
    result = preview_product_rows(
        [
            {
                "row_number": 2,
                "partnumber": "NEW-001",
                "vtex_category_id": 0,
                "vtex_brand_id": "abc",
            }
        ],
        "nuevos.xlsx",
    )

    codes = {error["code"] for error in result["errors"]}
    assert codes == {"VTEX_CATEGORY_ID_INVALID", "VTEX_BRAND_ID_INVALID"}
    assert result["has_blocking_errors"] is True


def test_preview_accepts_positive_vtex_ids_and_keeps_optional_metadata():
    result = preview_product_rows(
        [
            {
                "row_number": 12,
                "partnumber": "NEW-002",
                "brand": "LENOVO",
                "product_name": "Notebook ejemplo",
                "category": "LAPTOP",
                "vtex_category_id": "65",
                "vtex_brand_id": 2000004,
            }
        ],
        "nuevos.xlsx",
    )

    row = result["rows"][0]
    assert row["vtex_category_id"] == 65
    assert row["vtex_brand_id"] == 2000004
    assert row["brand"] == "LENOVO"
    assert row["product_name"] == "Notebook ejemplo"
    assert result["has_blocking_errors"] is False
