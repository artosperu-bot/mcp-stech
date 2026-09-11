from __future__ import annotations

from collections.abc import Callable
from typing import Any


ProgressCallback = Callable[[str, int], None]
WorkHandler = Callable[[dict[str, Any], ProgressCallback], dict[str, Any]]


class WorkExecutionError(RuntimeError):
    def __init__(self, code: str, detail: str | None = None):
        self.code = str(code or "WORK_ERROR").strip().upper()
        self.detail = detail
        super().__init__(detail or self.code)


class RetryableWorkError(WorkExecutionError):
    pass


class PermanentWorkError(WorkExecutionError):
    pass


class UnsupportedWorkTypeError(PermanentWorkError):
    def __init__(self, work_type: str):
        super().__init__("UNSUPPORTED_WORK_TYPE", f"unsupported work type: {work_type}")


class ProductWorkDispatcher:
    def __init__(self) -> None:
        self._handlers: dict[str, WorkHandler] = {}

    def register(self, work_type: str, handler: WorkHandler) -> None:
        normalized = str(work_type or "").strip().upper()
        if not normalized:
            raise ValueError("work_type is required")
        self._handlers[normalized] = handler
        for raw_alias in getattr(handler, "aliases", ()) or ():
            alias = str(raw_alias or "").strip().upper()
            if alias and alias != normalized:
                self._handlers[alias] = handler

    def dispatch(
        self,
        item: dict[str, Any],
        progress: ProgressCallback,
    ) -> dict[str, Any]:
        work_type = str(item.get("work_type") or "").strip().upper()
        handler = self._handlers.get(work_type)
        if handler is None:
            raise UnsupportedWorkTypeError(work_type)
        result = handler(item, progress)
        if not isinstance(result, dict):
            raise PermanentWorkError("INVALID_HANDLER_RESULT", "handler must return a dict")
        return result


def enrichment_handler_not_installed(
    item: dict[str, Any],
    progress: ProgressCallback,
) -> dict[str, Any]:
    """Safe Plan-A placeholder until Product Enrichment Core (Plan B) is installed."""
    progress("ANALYZING_MISSING_FIELDS", 10)
    return {
        "status": "REVIEW_REQUIRED",
        "error_code": "ENRICHMENT_HANDLER_NOT_INSTALLED",
        "error_detail": "Product Enrichment Core V2 is not installed yet.",
    }
