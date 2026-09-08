from __future__ import annotations

from typing import Any

from stech_mcp.domain.product_loader_models import normalize_partnumber


def _positive_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def preview_product_rows(rows: list[dict[str, Any]], source_name: str) -> dict[str, Any]:
    normalized_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    seen: set[str] = set()

    for index, source_row in enumerate(rows or [], start=1):
        row = dict(source_row or {})
        try:
            row_number = int(row.get("row_number") or index)
        except (TypeError, ValueError):
            row_number = index
        partnumber = normalize_partnumber(row.get("partnumber"))
        duplicate = bool(partnumber and partnumber in seen)
        if partnumber:
            seen.add(partnumber)

        normalized = {**row, "row_number": row_number, "partnumber": partnumber, "duplicate_in_file": duplicate}

        if not partnumber:
            errors.append(
                {
                    "row_number": row_number,
                    "partnumber": "",
                    "code": "PARTNUMBER_REQUIRED",
                    "message": "Part Number requerido",
                }
            )
        elif duplicate:
            errors.append(
                {
                    "row_number": row_number,
                    "partnumber": partnumber,
                    "code": "DUPLICATE_PARTNUMBER",
                    "message": "Part Number duplicado en el archivo",
                }
            )

        for key, code, label in (
            ("vtex_category_id", "VTEX_CATEGORY_ID_INVALID", "CategoryId VTEX inválido"),
            ("vtex_brand_id", "VTEX_BRAND_ID_INVALID", "BrandId VTEX inválido"),
        ):
            raw = row.get(key)
            if raw is None or raw == "":
                continue
            parsed = _positive_int(raw)
            if parsed is None:
                errors.append(
                    {
                        "row_number": row_number,
                        "partnumber": partnumber,
                        "code": code,
                        "message": label,
                    }
                )
            else:
                normalized[key] = parsed

        normalized_rows.append(normalized)

    return {
        "source_name": str(source_name or "").strip(),
        "rows": normalized_rows,
        "errors": errors,
        "warnings": warnings,
        "row_count": len(normalized_rows),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "has_blocking_errors": bool(errors),
        "write_operations": 0,
    }
