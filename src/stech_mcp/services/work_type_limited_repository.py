from __future__ import annotations

from typing import Any


class WorkTypeLimitedRepository:
    """Delegate a Product Work repository while limiting claim_next to work types."""

    def __init__(self, inner: Any, allowed_work_types: tuple[str, ...] | list[str]) -> None:
        self.inner = inner
        self.allowed_work_types = tuple(
            dict.fromkeys(
                str(value or "").strip().upper()
                for value in allowed_work_types
                if str(value or "").strip()
            )
        )
        if not self.allowed_work_types:
            raise ValueError("allowed_work_types is required")

    def claim_next(self, worker_id: str, lease_seconds: int = 120):
        return self.inner.claim_next(
            worker_id,
            lease_seconds,
            allowed_work_types=self.allowed_work_types,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)
