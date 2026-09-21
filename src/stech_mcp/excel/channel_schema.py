from __future__ import annotations

from dataclasses import dataclass

from stech_mcp.excel.template_models import TemplateField, TemplateSchema


@dataclass(frozen=True)
class ChannelField:
    stable_key: str
    header: str
    column_letter: str
    required: bool
    allowed_values: tuple[str, ...] = ()
    attribute_id: str | None = None
    column_index: int | None = None


@dataclass(frozen=True)
class ChannelSchema:
    source_filename: str
    data_sheet: str
    fields: tuple[ChannelField, ...]


def _stable_key(field: TemplateField) -> str:
    if field.attribute_id:
        return f"attr:{field.attribute_id}"
    return f"header:{field.header.strip().casefold()}"


def build_channel_schema(template: TemplateSchema) -> ChannelSchema:
    """Convert an inspected workbook into a channel-neutral field schema.

    Attribute IDs embedded in marketplace headers are the primary identity.
    Column positions remain output coordinates only and may change between
    template versions without changing field identity.
    """

    return ChannelSchema(
        source_filename=template.source_filename,
        data_sheet=template.data_sheet,
        fields=tuple(
            ChannelField(
                stable_key=_stable_key(field),
                header=field.header,
                column_letter=field.column_letter,
                required=field.required,
                allowed_values=tuple(field.allowed_values),
                attribute_id=field.attribute_id,
                column_index=field.column_index,
            )
            for field in template.fields
        ),
    )
