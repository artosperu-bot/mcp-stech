from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any


def register_excel_tools(
    mcp: Any,
    *,
    inspector: Any,
    writer: Any,
    namespace: Any | None = None,
) -> dict[str, Any]:
    """Expose safe Excel inspection/copy writing for HERMES.

    Excel stays an adapter/output. These tools never research product facts and
    never overwrite the original workbook.
    """

    @mcp.tool()
    def excel_template_inspect(path: str) -> dict[str, Any]:
        source = Path(str(path or "").strip())
        if source.suffix.lower() != ".xlsx":
            raise ValueError("only .xlsx files are supported")
        if not source.exists():
            raise FileNotFoundError(str(source))

        schema = inspector.inspect(source)
        payload = asdict(schema)
        payload["field_count"] = len(schema.fields)
        payload["required_field_count"] = sum(1 for field in schema.fields if field.required)
        payload["closed_list_field_count"] = sum(1 for field in schema.fields if field.allowed_values)
        return payload

    @mcp.tool()
    def excel_write_copy(
        source_path: str,
        output_path: str,
        row_updates: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        source = Path(str(source_path or "").strip())
        output = Path(str(output_path or "").strip())
        if source.suffix.lower() != ".xlsx" or output.suffix.lower() != ".xlsx":
            raise ValueError("source_path and output_path must be .xlsx files")
        if not source.exists():
            raise FileNotFoundError(str(source))
        if source.resolve() == output.resolve():
            raise ValueError("the original Excel cannot be overwritten")

        schema = inspector.inspect(source)
        normalized_updates: dict[int, dict[str, Any]] = {}
        for raw_row, values in dict(row_updates or {}).items():
            row_number = int(raw_row)
            if row_number < 1:
                raise ValueError("row numbers must be positive")
            if not isinstance(values, dict):
                raise ValueError(f"row {row_number} updates must be an object")
            normalized_updates[row_number] = dict(values)

        report = writer.write(
            source_path=source,
            output_path=output,
            schema=schema,
            row_updates=normalized_updates,
        )
        return {
            "source_path": str(source),
            "output_path": report.output_path,
            "updated_cell_count": len(report.updated_cells),
            "updated_cells": list(report.updated_cells),
            "skipped_formula_cells": list(report.skipped_formula_cells),
            "original_untouched": True,
        }

    registered = {
        "excel_template_inspect": excel_template_inspect,
        "excel_write_copy": excel_write_copy,
    }
    if namespace is not None:
        for name, func in registered.items():
            setattr(namespace, name, func)
    return registered
