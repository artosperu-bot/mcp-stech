from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape


_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CELL_RE = re.compile(r"^([A-Z]+)([0-9]+)$")


def _column_number(name: str) -> int:
    value = 0
    for char in str(name or "").upper():
        if not ("A" <= char <= "Z"):
            raise ValueError(f"invalid column name: {name}")
        value = value * 26 + (ord(char) - ord("A") + 1)
    return value


def _cell_parts(reference: str) -> tuple[str, int]:
    match = _CELL_RE.match(str(reference or "").upper())
    if not match:
        raise ValueError(f"invalid cell reference: {reference}")
    return match.group(1), int(match.group(2))


class XlsxCellPatcher:
    """Patch worksheet cell values while preserving unsupported XLSX extensions.

    The original ZIP members are copied byte-for-byte except for the selected
    worksheet XML. Within that XML only target <c> elements are inserted or
    replaced. This avoids openpyxl round-tripping the workbook and therefore
    preserves Falabella x14/x14ac data-validation extensions and other unknown
    workbook features.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        if not self.path.is_file():
            raise FileNotFoundError(str(self.path))

    @staticmethod
    def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
        try:
            payload = archive.read("xl/sharedStrings.xml")
        except KeyError:
            return []
        root = ET.fromstring(payload)
        values: list[str] = []
        for item in root.findall(f"{{{_MAIN_NS}}}si"):
            text = "".join(
                node.text or ""
                for node in item.iter(f"{{{_MAIN_NS}}}t")
            )
            values.append(text)
        return values

    @staticmethod
    def _worksheet_path(archive: zipfile.ZipFile, sheet_name: str) -> str:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rel_id: str | None = None
        sheets = workbook.find(f"{{{_MAIN_NS}}}sheets")
        if sheets is not None:
            for sheet in sheets:
                if sheet.attrib.get("name") == sheet_name:
                    rel_id = sheet.attrib.get(f"{{{_DOC_REL_NS}}}id")
                    break
        if not rel_id:
            raise ValueError(f"worksheet not found: {sheet_name}")

        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target: str | None = None
        for relation in rels.findall(f"{{{_PKG_REL_NS}}}Relationship"):
            if relation.attrib.get("Id") == rel_id:
                target = relation.attrib.get("Target")
                break
        if not target:
            raise ValueError(f"worksheet relationship not found: {sheet_name}")
        if target.startswith("/"):
            return target.lstrip("/")
        return f"xl/{target}"

    @staticmethod
    def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
        cell_type = cell.attrib.get("t")
        if cell_type == "inlineStr":
            return "".join(
                node.text or ""
                for node in cell.iter(f"{{{_MAIN_NS}}}t")
            )
        value = cell.find(f"{{{_MAIN_NS}}}v")
        raw = value.text if value is not None and value.text is not None else ""
        if cell_type == "s" and raw:
            try:
                return shared_strings[int(raw)]
            except (ValueError, IndexError):
                return ""
        return raw

    def read_rows(
        self,
        *,
        sheet_name: str,
        rows: list[int],
    ) -> dict[int, dict[str, str]]:
        requested = {int(row) for row in rows}
        with zipfile.ZipFile(self.path, "r") as archive:
            sheet_path = self._worksheet_path(archive, sheet_name)
            shared_strings = self._shared_strings(archive)
            root = ET.fromstring(archive.read(sheet_path))

        result: dict[int, dict[str, str]] = {}
        sheet_data = root.find(f"{{{_MAIN_NS}}}sheetData")
        if sheet_data is None:
            return result
        for row in sheet_data.findall(f"{{{_MAIN_NS}}}row"):
            row_number = int(row.attrib.get("r") or 0)
            if row_number not in requested:
                continue
            cells: dict[str, str] = {}
            for cell in row.findall(f"{{{_MAIN_NS}}}c"):
                reference = str(cell.attrib.get("r") or "")
                if not reference:
                    continue
                column, _ = _cell_parts(reference)
                cells[column] = self._cell_value(cell, shared_strings)
            result[row_number] = cells
        return result

    def sheet_dimensions(self, *, sheet_name: str) -> tuple[int, int]:
        with zipfile.ZipFile(self.path, "r") as archive:
            sheet_path = self._worksheet_path(archive, sheet_name)
            root = ET.fromstring(archive.read(sheet_path))
        dimension = root.find(f"{{{_MAIN_NS}}}dimension")
        reference = str(dimension.attrib.get("ref") or "") if dimension is not None else ""
        if ":" in reference:
            _, last = reference.split(":", 1)
        else:
            last = reference
        if not last:
            return (0, 0)
        column, row = _cell_parts(last)
        return row, _column_number(column)

    @staticmethod
    def _style_attribute(cell_xml: str) -> str:
        match = re.search(r'\bs="([^"]+)"', cell_xml)
        return f' s="{escape(match.group(1))}"' if match else ""

    @staticmethod
    def _inline_cell(reference: str, value: str, style_attribute: str = "") -> str:
        escaped = escape(str(value), {'"': '&quot;'})
        preserve = ' xml:space="preserve"' if escaped != escaped.strip() else ""
        return (
            f'<c r="{reference}"{style_attribute} t="inlineStr">'
            f'<is><t{preserve}>{escaped}</t></is></c>'
        )

    @classmethod
    def _patch_row(
        cls,
        row_xml: str,
        *,
        row_number: int,
        values: dict[str, str],
        overwrite: bool,
    ) -> tuple[str, int, int]:
        changed = 0
        preserved = 0
        for column, value in sorted(values.items(), key=lambda item: _column_number(item[0])):
            reference = f"{column.upper()}{row_number}"
            pattern = re.compile(
                rf'<c\b(?=[^>]*\br="{re.escape(reference)}")([^>]*)/>|'
                rf'<c\b(?=[^>]*\br="{re.escape(reference)}")([^>]*)>.*?</c>',
                flags=re.DOTALL,
            )
            match = pattern.search(row_xml)
            if match:
                existing = match.group(0)
                # Existing non-empty image URLs are preserved unless overwrite is explicit.
                has_value = bool(
                    re.search(r"<(?:v|t)(?:\s[^>]*)?>.*?</(?:v|t)>", existing, re.DOTALL)
                )
                if has_value and not overwrite:
                    preserved += 1
                    continue
                replacement = cls._inline_cell(
                    reference,
                    value,
                    cls._style_attribute(existing),
                )
                row_xml = row_xml[:match.start()] + replacement + row_xml[match.end():]
                changed += 1
                continue

            new_cell = cls._inline_cell(reference, value)
            closing = row_xml.rfind("</row>")
            if closing < 0:
                raise ValueError(f"invalid row XML for row {row_number}")
            row_xml = row_xml[:closing] + new_cell + row_xml[closing:]
            changed += 1
        return row_xml, changed, preserved

    @classmethod
    def _patch_sheet_xml(
        cls,
        payload: bytes,
        *,
        updates: dict[int, dict[str, str]],
        overwrite: bool,
    ) -> tuple[bytes, int, int]:
        text = payload.decode("utf-8")
        total_changed = 0
        total_preserved = 0
        for row_number in sorted(updates):
            pattern = re.compile(
                rf'<row\b(?=[^>]*\br="{int(row_number)}")[^>]*>.*?</row>',
                flags=re.DOTALL,
            )
            match = pattern.search(text)
            if not match:
                raise ValueError(f"worksheet row not found: {row_number}")
            patched, changed, preserved = cls._patch_row(
                match.group(0),
                row_number=int(row_number),
                values=updates[row_number],
                overwrite=overwrite,
            )
            text = text[:match.start()] + patched + text[match.end():]
            total_changed += changed
            total_preserved += preserved
        return text.encode("utf-8"), total_changed, total_preserved

    def write_copy(
        self,
        *,
        output_path: str | Path,
        sheet_name: str,
        updates: dict[int, dict[str, str]],
        overwrite: bool = False,
    ) -> dict[str, Any]:
        destination = Path(output_path).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")

        with zipfile.ZipFile(self.path, "r") as source:
            sheet_path = self._worksheet_path(source, sheet_name)
            sheet_payload = source.read(sheet_path)
            patched, changed, preserved = self._patch_sheet_xml(
                sheet_payload,
                updates=updates,
                overwrite=bool(overwrite),
            )
            with zipfile.ZipFile(temporary, "w") as target:
                for info in source.infolist():
                    payload = patched if info.filename == sheet_path else source.read(info.filename)
                    target.writestr(info, payload)

        temporary.replace(destination)
        return {
            "output": str(destination),
            "changed_cells": changed,
            "preserved_existing": preserved,
            "sheet_name": sheet_name,
            "writer": "XLSX_XML_PRESERVE_EXTENSIONS",
        }