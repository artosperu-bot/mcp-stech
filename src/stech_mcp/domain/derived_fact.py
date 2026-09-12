from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class DerivedFact:
    field_code: str
    value: Any
    rule_code: str
    rule_version: int
    inputs: dict[str, Any]
    confidence: float
    explanation: str
    derived_at: datetime
