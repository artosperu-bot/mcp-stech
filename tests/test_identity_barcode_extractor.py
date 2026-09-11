from stech_mcp.services.identity_barcode_extractor import IdentityBarcodeExtractor, validate_gtin


def test_validate_gtin_checksum_for_supported_lengths():
    assert validate_gtin("96385074") is True          # GTIN-8 / EAN-8
    assert validate_gtin("036000291452") is True      # GTIN-12 / UPC-A
    assert validate_gtin("4006381333931") is True     # GTIN-13 / EAN-13
    assert validate_gtin("10012345678902") is True    # GTIN-14


def test_validate_gtin_rejects_invalid_checksum_or_unsupported_length():
    assert validate_gtin("4006381333932") is False
    assert validate_gtin("036000291453") is False
    assert validate_gtin("1234567890") is False


def test_extract_only_labeled_valid_code_with_exact_partnumber():
    extractor=IdentityBarcodeExtractor()
    items=extractor.extract({"url":"https://lenovo.com/pn1","source_type":"MANUFACTURER","confidence_rank":"A1","title":"Official","pages":[{"page":1,"text":"PN1 EAN: 4006381333931 Serial: 4006381333932"}]},["ean","upc","gtin"],"PN1")
    assert len(items)==1
    assert items[0]["field_code"]=="ean"
    assert items[0]["normalized_value"]=="4006381333931"
    assert items[0]["source_partnumber"]=="PN1"


def test_invalid_or_unlabeled_number_is_not_evidence():
    extractor=IdentityBarcodeExtractor()
    items=extractor.extract({"url":"https://lenovo.com/pn1","source_type":"MANUFACTURER","confidence_rank":"A1","pages":[{"page":1,"text":"PN1 EAN: 4006381333932 other 4006381333931"}]},["ean"],"PN1")
    assert items==[]
