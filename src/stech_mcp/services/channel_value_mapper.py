from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from stech_mcp.excel.channel_schema import ChannelField


@dataclass(frozen=True)
class MappingResult:
    state: str
    value: Any | None
    rule_code: str | None
    reason: str | None = None


def _text(value: Any) -> str:
    return str(value or "").strip()


class ChannelValueMapper:
    """Map canonical values without free-form guessing.

    Closed-list fields accept only exact values, case-only normalization, or an
    explicit deterministic rule such as boolean Sí/No. Anything else remains
    REVIEW_REQUIRED instead of choosing the nearest-looking marketplace value.
    """

    @staticmethod
    def _boolean_value(value: bool, allowed_values: tuple[str, ...]) -> str | None:
        true_labels = {"sí", "si", "yes", "true"}
        false_labels = {"no", "false"}
        candidates = true_labels if value else false_labels
        for allowed in allowed_values:
            if allowed.strip().casefold() in candidates:
                return allowed
        return None

    def map(self, field: ChannelField, canonical_value: Any) -> MappingResult:
        allowed = tuple(field.allowed_values or ())
        if not allowed:
            return MappingResult(
                state="MAPPED",
                value=canonical_value,
                rule_code="OPEN_VALUE",
            )

        if isinstance(canonical_value, bool):
            mapped = self._boolean_value(canonical_value, allowed)
            if mapped is not None:
                return MappingResult(
                    state="MAPPED",
                    value=mapped,
                    rule_code="BOOLEAN_SI_NO_V1",
                )

        for option in allowed:
            if canonical_value == option:
                return MappingResult(
                    state="MAPPED",
                    value=option,
                    rule_code="EXACT_ALLOWED_VALUE",
                )

        source = _text(canonical_value)
        if source:
            for option in allowed:
                if source.casefold() == option.strip().casefold():
                    return MappingResult(
                        state="MAPPED",
                        value=option,
                        rule_code="CASEFOLD_ALLOWED_VALUE",
                    )

        return MappingResult(
            state="REVIEW_REQUIRED",
            value=None,
            rule_code=None,
            reason="NO_EXACT_ALLOWED_MAPPING",
        )
