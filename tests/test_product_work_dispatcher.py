from __future__ import annotations

import pytest

from stech_mcp.services.product_work_dispatcher import (
    ProductWorkDispatcher,
    UnsupportedWorkTypeError,
    enrichment_handler_not_installed,
)


def test_dispatcher_invokes_registered_handler_and_forwards_progress():
    dispatcher = ProductWorkDispatcher()
    calls = []

    def handler(item, progress):
        progress("ANALYZING_MISSING_FIELDS", 20)
        calls.append(item["partnumber"])
        return {"status": "COMPLETED"}

    dispatcher.register("ENRICH_TECHNICAL", handler)
    progress_calls = []
    result = dispatcher.dispatch(
        {"work_type": "ENRICH_TECHNICAL", "partnumber": "PN1"},
        lambda state, pct: progress_calls.append((state, pct)),
    )

    assert result["status"] == "COMPLETED"
    assert calls == ["PN1"]
    assert progress_calls == [("ANALYZING_MISSING_FIELDS", 20)]


def test_dispatcher_rejects_unknown_work_type_without_fallback():
    dispatcher = ProductWorkDispatcher()
    with pytest.raises(UnsupportedWorkTypeError) as exc:
        dispatcher.dispatch({"work_type": "PUBLISH_MAGIC", "partnumber": "PN1"}, lambda *_: None)
    assert exc.value.code == "UNSUPPORTED_WORK_TYPE"


def test_placeholder_never_reports_false_completion():
    progress_calls = []
    result = enrichment_handler_not_installed(
        {"work_type": "ENRICH_TECHNICAL", "partnumber": "PN1"},
        lambda state, pct: progress_calls.append((state, pct)),
    )
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["error_code"] == "ENRICHMENT_HANDLER_NOT_INSTALLED"
    assert progress_calls == [("ANALYZING_MISSING_FIELDS", 10)]
