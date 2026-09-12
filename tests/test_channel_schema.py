from stech_mcp.excel.channel_schema import build_channel_schema
from stech_mcp.excel.template_models import TemplateField, TemplateSchema


def _template(barcode_column: str, portable_column: str) -> TemplateSchema:
    return TemplateSchema(
        source_filename="template.xlsx",
        data_sheet="Productos",
        sheet_names=("Productos", "Opciones"),
        fields=(
            TemplateField(
                header="Código de barras * #56",
                column_index=1 if barcode_column == "A" else 3,
                column_letter=barcode_column,
                attribute_id="56",
                required=True,
            ),
            TemplateField(
                header="TipoDePortatil * #396393",
                column_index=2 if portable_column == "B" else 4,
                column_letter=portable_column,
                attribute_id="396393",
                required=True,
                allowed_values=("2 en 1", "Macbook", "Laptop", "Laptop Gamer"),
            ),
        ),
    )


def test_channel_schema_uses_attribute_id_as_stable_identity():
    schema = build_channel_schema(_template("A", "B"))

    by_key = {field.stable_key: field for field in schema.fields}
    assert set(by_key) == {"attr:56", "attr:396393"}
    assert by_key["attr:56"].required is True
    assert by_key["attr:396393"].allowed_values == (
        "2 en 1",
        "Macbook",
        "Laptop",
        "Laptop Gamer",
    )


def test_channel_schema_identity_does_not_change_when_columns_move():
    original = build_channel_schema(_template("A", "B"))
    moved = build_channel_schema(_template("C", "D"))

    assert [field.stable_key for field in original.fields] == [
        field.stable_key for field in moved.fields
    ]
    assert next(field for field in moved.fields if field.stable_key == "attr:56").column_letter == "C"
