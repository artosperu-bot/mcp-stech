from stech_mcp.domain.gtin import barcode_type, normalize_gtin, validate_gtin


def test_normalizes_common_gtin_formatting():
    assert normalize_gtin(" 8806-0948 99528 ") == "8806094899528"


def test_validates_ean13_and_rejects_bad_check_digit():
    assert validate_gtin("8806094899528") is True
    assert barcode_type("8806094899528") == "EAN_13"
    assert validate_gtin("8806094899529") is False


def test_supports_upc_ean8_and_gtin14_lengths():
    assert barcode_type("036000291452") == "UPC_A"
    assert barcode_type("96385074") == "EAN_8"
    assert barcode_type("10012345678902") == "GTIN_14"
