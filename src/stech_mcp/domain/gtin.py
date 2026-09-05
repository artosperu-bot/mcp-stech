from __future__ import annotations


_GTIN_LENGTHS = {8: "EAN_8", 12: "UPC_A", 13: "EAN_13", 14: "GTIN_14"}


def normalize_gtin(value: str | None) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    compact = raw.replace(" ", "").replace("-", "")
    return compact if compact.isdigit() else None


def validate_gtin(value: str | None) -> bool:
    normalized = normalize_gtin(value)
    if normalized is None or len(normalized) not in _GTIN_LENGTHS:
        return False

    digits = [int(char) for char in normalized]
    check_digit = digits[-1]
    total = 0
    weight = 3
    for digit in reversed(digits[:-1]):
        total += digit * weight
        weight = 1 if weight == 3 else 3
    expected = (10 - (total % 10)) % 10
    return check_digit == expected


def barcode_type(value: str | None) -> str | None:
    normalized = normalize_gtin(value)
    if normalized is None or not validate_gtin(normalized):
        return None
    return _GTIN_LENGTHS.get(len(normalized))


def ean13_from_upc(value: str | None) -> str | None:
    """Return the 13-digit zero-padded GTIN representation of a valid UPC-A."""
    normalized = normalize_gtin(value)
    if normalized is None or barcode_type(normalized) != "UPC_A":
        return None
    candidate = "0" + normalized
    return candidate if barcode_type(candidate) == "EAN_13" else None


def upc_from_ean13(value: str | None) -> str | None:
    """Return UPC-A when a valid EAN/GTIN-13 is the zero-padded form of UPC-A."""
    normalized = normalize_gtin(value)
    if normalized is None or barcode_type(normalized) != "EAN_13" or not normalized.startswith("0"):
        return None
    candidate = normalized[1:]
    return candidate if barcode_type(candidate) == "UPC_A" else None
