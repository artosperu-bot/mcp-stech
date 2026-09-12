from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TemplateField:
    header: str
    column_index: int
    column_letter: str
    attribute_id: str | None = None
    required: bool = False
    allowed_values: tuple[str, ...] = ()

    @property
    def stable_key(self) -> str:
        return self.attribute_id or self.header.strip().casefold()


@dataclass(frozen=True)
class TemplateSchema:
    source_filename: str
    data_sheet: str
    sheet_names: tuple[str, ...]
    fields: tuple[TemplateField, ...]
    brands: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    formula_cells: tuple[str, ...] = ()
