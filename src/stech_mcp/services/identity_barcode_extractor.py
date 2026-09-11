from __future__ import annotations

import re
from typing import Any


def normalize_gtin(value: Any) -> str | None:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits if len(digits) in {8, 12, 13, 14} else None


def validate_gtin(value: Any) -> bool:
    digits = normalize_gtin(value)
    if not digits:
        return False
    body = digits[:-1]
    check = int(digits[-1])
    total = 0
    for offset, ch in enumerate(reversed(body), start=1):
        total += int(ch) * (3 if offset % 2 == 1 else 1)
    return (10 - total % 10) % 10 == check


def _exact_pn(text: str, partnumber: str) -> bool:
    return re.search(rf"(?<![A-Z0-9]){re.escape(partnumber)}(?![A-Z0-9])", text, re.I) is not None


def _excerpt(text: str, needle: str, limit: int = 500) -> str:
    compact = " ".join(str(text or "").split())
    pos = compact.find(needle)
    if pos < 0 or len(compact) <= limit:
        return compact[:limit]
    start = max(0, pos - limit // 2)
    return compact[start:start + limit]


_LABELS = {
    "ean": r"EAN(?:[-_ ]?(?:8|13))?",
    "upc": r"UPC(?:[-_ ]?A|[-_ ]?12)?",
    "gtin": r"GTIN(?:[-_ ]?(?:8|12|13|14))?",
}


class IdentityBarcodeExtractor:
    """Extract barcode candidates only from labeled, checksum-valid evidence."""

    def extract(self, document: dict[str, Any], target_fields: list[str], partnumber: str) -> list[dict[str, Any]]:
        pn = str(partnumber or "").strip().upper()
        if not pn:
            raise ValueError("partnumber is required")
        wanted = []
        for raw in target_fields or []:
            code = str(raw or "").strip().lower()
            if code in _LABELS and code not in wanted:
                wanted.append(code)
        source_url = str(document.get("url") or "").strip() or None
        source_type = str(document.get("source_type") or "OFFICIAL_DOCUMENT").strip().upper()
        confidence = str(document.get("confidence_rank") or "A2").strip().upper()
        out = []
        seen = set()
        for page in document.get("pages") or []:
            text = str((page or {}).get("text") or "")
            if not text:
                continue
            exact = _exact_pn(text, pn)
            page_number = int((page or {}).get("page") or 1)
            for field in wanted:
                pattern = rf"\b{_LABELS[field]}\b\s*(?:code|c[oó]digo)?\s*[:#\-]?\s*([0-9][0-9\s\-]{{6,20}}[0-9])"
                matches = []
                for match in re.finditer(pattern, text, re.I):
                    value = normalize_gtin(match.group(1))
                    if value and validate_gtin(value) and value not in matches:
                        matches.append(value)
                if len(matches) != 1:
                    continue
                value = matches[0]
                # Dedicated fields must match their natural barcode length.
                if field == "upc" and len(value) != 12:
                    continue
                if field == "ean" and len(value) not in {8, 13}:
                    continue
                key = (field, value)
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "field_code": field,
                    "raw_value": value,
                    "normalized_value": value,
                    "unit": None,
                    "source_type": source_type,
                    "source_name": document.get("title"),
                    "source_url": source_url,
                    "source_partnumber": pn if exact else None,
                    "evidence_text": _excerpt(text, value),
                    "page_number": page_number,
                    "confidence_rank": confidence,
                    "status": "PENDING",
                })
        return out
