from __future__ import annotations

import zipfile
from pathlib import Path

from stech_mcp.excel.xlsx_cell_patcher import XlsxCellPatcher


WORKBOOK = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Subir plantilla" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>
"""

RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
    Target="worksheets/sheet1.xml"/>
</Relationships>
"""

SHEET = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet
 xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
 xmlns:x14="http://schemas.microsoft.com/office/spreadsheetml/2009/9/main"
 mc:Ignorable="x14">
  <dimension ref="A1:BQ5"/>
  <sheetData>
    <row r="4">
      <c r="A4" t="inlineStr"><is><t>SKU del vendedor #29</t></is></c>
      <c r="BJ4" t="inlineStr"><is><t>Imagen principal #IM1</t></is></c>
      <c r="BK4" t="inlineStr"><is><t>Imagen2 #IM2</t></is></c>
    </row>
    <row r="5">
      <c r="A5" t="inlineStr"><is><t>82YU00XYLM</t></is></c>
      <c r="BI5"><v>2.4</v></c>
    </row>
  </sheetData>
  <extLst>
    <ext uri="{CCE6A557-97BC-4B89-ADB6-D9C93CAAB3DF}">
      <x14:dataValidations count="1">
        <x14:dataValidation type="list"/>
      </x14:dataValidations>
    </ext>
  </extLst>
</worksheet>
"""


def _fixture(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", WORKBOOK)
        archive.writestr("xl/_rels/workbook.xml.rels", RELS)
        archive.writestr("xl/worksheets/sheet1.xml", SHEET)
        archive.writestr("xl/styles.xml", b"STYLE-BYTES-MUST-STAY-IDENTICAL")


def test_xml_patcher_preserves_unknown_validation_extension_and_other_members(tmp_path):
    source = tmp_path / "input.xlsx"
    output = tmp_path / "output.xlsx"
    _fixture(source)

    patcher = XlsxCellPatcher(source)
    result = patcher.write_copy(
        output_path=output,
        sheet_name="Subir plantilla",
        updates={
            5: {
                "BJ": "https://mcp.artos.pe/falabella-images/token?a=1&b=2",
                "BK": "https://mcp.artos.pe/falabella-images/token-2",
            }
        },
    )

    assert result["changed_cells"] == 2
    assert result["writer"] == "XLSX_XML_PRESERVE_EXTENSIONS"

    with zipfile.ZipFile(source, "r") as original, zipfile.ZipFile(output, "r") as generated:
        assert generated.read("xl/styles.xml") == original.read("xl/styles.xml")
        xml = generated.read("xl/worksheets/sheet1.xml").decode("utf-8")

    assert "<x14:dataValidations" in xml
    assert 'mc:Ignorable="x14"' in xml
    assert 'r="BJ5"' in xml
    assert 'r="BK5"' in xml
    assert "token?a=1&amp;b=2" in xml


def test_xml_patcher_reads_headers_and_sku_without_openpyxl(tmp_path):
    source = tmp_path / "input.xlsx"
    _fixture(source)

    patcher = XlsxCellPatcher(source)
    rows = patcher.read_rows(sheet_name="Subir plantilla", rows=[4, 5])

    assert rows[4]["A"] == "SKU del vendedor #29"
    assert rows[4]["BJ"] == "Imagen principal #IM1"
    assert rows[5]["A"] == "82YU00XYLM"
    assert patcher.sheet_dimensions(sheet_name="Subir plantilla") == (5, 69)
