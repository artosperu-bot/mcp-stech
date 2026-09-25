from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from stech_mcp import server_authoritative as server
from stech_mcp.excel.xlsx_cell_patcher import XlsxCellPatcher


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = PROJECT_ROOT / "EXCEL" / "FALABELLA" / "ENTRADA"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "EXCEL" / "FALABELLA" / "SALIDA"

IMAGE_HEADERS = [
    "Imagen principal #IM1",
    "Imagen2 #IM2",
    "Imagen3 #IM3",
    "Imagen4 #IM4",
    "Imagen5 #IM5",
    "Imagen6 #IM6",
    "Imagen7 #IM7",
    "Imagen8 #IM8",
]


def _normalize(value: Any) -> str:
    return str(value or "").strip()


def _ensure_channel_folders() -> None:
    DEFAULT_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _latest_input() -> Path:
    _ensure_channel_folders()
    candidates = [
        path
        for path in DEFAULT_INPUT_DIR.glob("*.xlsx")
        if path.is_file()
        and not path.name.startswith("~$")
        and "_IMAGENES_FALABELLA" not in path.stem.upper()
    ]
    if not candidates:
        raise FileNotFoundError(
            "No hay archivos .xlsx en "
            f"{DEFAULT_INPUT_DIR}. Copia allí la plantilla Falabella y vuelve a ejecutar."
        )
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name.lower()))


def _resolve_input(requested: str | None) -> Path:
    if requested:
        path = Path(requested).expanduser().resolve()
    else:
        path = _latest_input()
    if not path.is_file():
        raise FileNotFoundError(str(path))
    return path


def _output_path(input_path: Path, requested: str | None) -> Path:
    _ensure_channel_folders()
    if requested:
        return Path(requested).expanduser().resolve()
    return DEFAULT_OUTPUT_DIR / f"{input_path.stem}_IMAGENES_FALABELLA.xlsx"


def _header_map(row: dict[str, str]) -> dict[str, str]:
    return {
        _normalize(value): column
        for column, value in row.items()
        if _normalize(value)
    }


def _find_sku_column(headers: dict[str, str]) -> str:
    for name, column in headers.items():
        if name.casefold().startswith("sku del vendedor"):
            return column
    raise ValueError("No se encontró la columna 'SKU del vendedor' en la fila 4")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Completa las columnas de imágenes de una plantilla Falabella usando "
            "imágenes locales exactas de PC020 y URLs firmadas Cloudflare, "
            "preservando las extensiones internas del XLSX."
        )
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="",
        help=(
            "Ruta opcional al XLSX. Si se omite, usa automáticamente el Excel "
            "más reciente de EXCEL\\FALABELLA\\ENTRADA."
        ),
    )
    parser.add_argument("--output", default="")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--sheet", default="Subir plantilla")
    args = parser.parse_args()

    input_path = _resolve_input(args.input or None)
    output_path = _output_path(input_path, args.output or None)

    workbook = XlsxCellPatcher(input_path)
    max_row, _ = workbook.sheet_dimensions(sheet_name=args.sheet)
    if max_row < 5:
        raise ValueError("La plantilla no contiene filas de producto")

    source_rows = workbook.read_rows(
        sheet_name=args.sheet,
        rows=list(range(4, max_row + 1)),
    )
    headers = _header_map(source_rows.get(4, {}))
    sku_column = _find_sku_column(headers)

    missing_headers = [name for name in IMAGE_HEADERS if name not in headers]
    if missing_headers:
        raise ValueError(f"Faltan columnas de imágenes: {missing_headers}")
    image_columns = [headers[name] for name in IMAGE_HEADERS]

    report_rows: list[dict[str, Any]] = []
    updates: dict[int, dict[str, str]] = {}

    for row_number in range(5, max_row + 1):
        row_values = source_rows.get(row_number, {})
        partnumber = _normalize(row_values.get(sku_column)).upper()
        if not partnumber:
            continue

        try:
            prepared = server.falabella_images_prepare(
                partnumber=partnumber,
                max_images=8,
            )
            images = sorted(
                list(prepared.get("images") or []),
                key=lambda item: int(item.get("position") or 0),
            )
            ordered_urls = [
                str(item["url"])
                for item in images
                if item.get("url")
            ][:8]

            updates[row_number] = {
                column: url
                for column, url in zip(image_columns, ordered_urls, strict=False)
            }
            report_rows.append(
                {
                    "row": row_number,
                    "partnumber": partnumber,
                    "state": prepared.get("state"),
                    "prepared_images": len(images),
                    "candidate_urls": len(ordered_urls),
                    "warning_count": prepared.get("warning_count", 0),
                    "errors": prepared.get("errors") or [],
                }
            )
        except Exception as exc:
            report_rows.append(
                {
                    "row": row_number,
                    "partnumber": partnumber,
                    "state": "ERROR",
                    "prepared_images": 0,
                    "candidate_urls": 0,
                    "warning_count": 0,
                    "errors": [f"{type(exc).__name__}: {exc}"],
                }
            )

    write_result = workbook.write_copy(
        output_path=output_path,
        sheet_name=args.sheet,
        updates=updates,
        overwrite=bool(args.overwrite),
    )

    summary = {
        "ok": True,
        "input": str(input_path),
        "output": str(output_path),
        "sheet": args.sheet,
        "sku_count": len(report_rows),
        "changed_cells": write_result["changed_cells"],
        "preserved_existing": write_result["preserved_existing"],
        "overwrite": bool(args.overwrite),
        "writer": write_result["writer"],
        "template_extensions_preserved": True,
        "auto_input_folder": str(DEFAULT_INPUT_DIR),
        "auto_output_folder": str(DEFAULT_OUTPUT_DIR),
        "rows": report_rows,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
