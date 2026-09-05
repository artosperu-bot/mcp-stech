from stech_mcp.domain.gtin import (
    barcode_type,
    ean13_from_upc,
    normalize_gtin,
    upc_from_ean13,
    validate_gtin,
)


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


def test_upc_can_be_zero_padded_to_equivalent_ean13():
    assert ean13_from_upc("740617352214") == "0740617352214"
    assert barcode_type("0740617352214") == "EAN_13"


def test_zero_prefixed_ean13_can_be_reduced_to_equivalent_upc():
    assert upc_from_ean13("0740617338515") == "740617338515"


def test_non_zero_prefixed_ean13_has_no_upc_equivalent():
    assert upc_from_ean13("8806094899528") is None


def test_equivalence_helpers_reject_invalid_checksum():
    assert ean13_from_upc("740617352215") is None
    assert upc_from_ean13("0740617352215") is None
