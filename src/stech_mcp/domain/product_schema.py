from __future__ import annotations

from dataclasses import dataclass
import re


REQUIREMENTS = frozenset({"REQUIRED", "RECOMMENDED"})
REUSE_POLICIES = frozenset({"EXACT_PN_ONLY", "SAME_CHASSIS_ALLOWED"})
VALUE_TYPES = frozenset({"TEXT", "NUMBER", "BOOLEAN", "DIMENSIONS", "RANGE", "LIST"})


def _normalize_token(value: object, *, lower: bool = False) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[\s\-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text.lower() if lower else text.upper()


def normalize_category_code(value: object) -> str:
    return _normalize_token(value)


def normalize_field_code(value: object) -> str:
    return _normalize_token(value, lower=True)


@dataclass(frozen=True, slots=True)
class ProductAttributeDefinition:
    field_code: str
    value_type: str
    unit: str | None
    variant_sensitive: bool
    reuse_policy: str

    def __post_init__(self) -> None:
        field_code = normalize_field_code(self.field_code)
        value_type = str(self.value_type or "").strip().upper()
        reuse_policy = str(self.reuse_policy or "").strip().upper()
        unit = str(self.unit).strip() if self.unit is not None else None

        if not field_code:
            raise ValueError("field_code is required")
        if value_type not in VALUE_TYPES:
            raise ValueError(f"invalid value_type: {self.value_type}")
        if reuse_policy not in REUSE_POLICIES:
            raise ValueError(f"invalid reuse_policy: {self.reuse_policy}")

        object.__setattr__(self, "field_code", field_code)
        object.__setattr__(self, "value_type", value_type)
        object.__setattr__(self, "unit", unit or None)
        object.__setattr__(self, "variant_sensitive", bool(self.variant_sensitive))
        object.__setattr__(self, "reuse_policy", reuse_policy)


@dataclass(frozen=True, slots=True)
class CategoryAttribute:
    category_code: str
    field_code: str
    requirement: str
    ordinal: int
    value_type: str
    unit: str | None
    variant_sensitive: bool
    reuse_policy: str

    def __post_init__(self) -> None:
        category_code = normalize_category_code(self.category_code)
        field_code = normalize_field_code(self.field_code)
        requirement = str(self.requirement or "").strip().upper()
        value_type = str(self.value_type or "").strip().upper()
        reuse_policy = str(self.reuse_policy or "").strip().upper()
        ordinal = int(self.ordinal)
        unit = str(self.unit).strip() if self.unit is not None else None

        if not category_code:
            raise ValueError("category_code is required")
        if not field_code:
            raise ValueError("field_code is required")
        if requirement not in REQUIREMENTS:
            raise ValueError(f"invalid requirement: {self.requirement}")
        if value_type not in VALUE_TYPES:
            raise ValueError(f"invalid value_type: {self.value_type}")
        if reuse_policy not in REUSE_POLICIES:
            raise ValueError(f"invalid reuse_policy: {self.reuse_policy}")
        if ordinal <= 0:
            raise ValueError("ordinal must be greater than zero")

        object.__setattr__(self, "category_code", category_code)
        object.__setattr__(self, "field_code", field_code)
        object.__setattr__(self, "requirement", requirement)
        object.__setattr__(self, "ordinal", ordinal)
        object.__setattr__(self, "value_type", value_type)
        object.__setattr__(self, "unit", unit or None)
        object.__setattr__(self, "variant_sensitive", bool(self.variant_sensitive))
        object.__setattr__(self, "reuse_policy", reuse_policy)
