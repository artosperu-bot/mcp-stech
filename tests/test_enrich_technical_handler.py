from stech_mcp.services.handlers.enrich_technical import EnrichTechnicalHandler
from stech_mcp.services.product_work_dispatcher import RetryableWorkError


class FakeEngine:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def enrich(self, partnumber, category_code, requested_fields, progress):
        self.calls.append((partnumber, category_code, requested_fields))
        if self.error:
            raise self.error
        return dict(self.result)


def test_handler_maps_engine_review_to_queue_review():
    engine = FakeEngine({
        "state": "REVIEW_REQUIRED",
        "conflicts": [{"field_code": "battery_wh"}],
        "remaining_fields": ["battery_wh"],
        "error_code": None,
    })
    handler = EnrichTechnicalHandler(engine)

    result = handler(
        {"partnumber": "PN1", "input": {"category_code": "LAPTOP"}},
        lambda *_: None,
    )

    assert result["status"] == "REVIEW_REQUIRED"
    assert result["error_code"] == "FACT_CONFLICT"
    assert engine.calls == [("PN1", "LAPTOP", None)]


def test_handler_maps_partial_and_complete_without_publication_side_effects():
    partial = EnrichTechnicalHandler(FakeEngine({
        "state": "PARTIAL",
        "remaining_fields": ["ip_rating"],
        "conflicts": [],
        "error_code": "SEARCH_PROVIDER_NOT_CONFIGURED",
    }))
    complete = EnrichTechnicalHandler(FakeEngine({
        "state": "COMPLETED",
        "remaining_fields": [],
        "conflicts": [],
        "error_code": None,
    }))

    assert partial({"partnumber": "PN1", "input": {}}, lambda *_: None)["status"] == "PARTIAL"
    assert complete({"partnumber": "PN1", "input": {}}, lambda *_: None)["status"] == "COMPLETED"


def test_handler_maps_temporary_network_error_to_retryable_work_error():
    engine = FakeEngine(error=TimeoutError("source timeout"))
    handler = EnrichTechnicalHandler(engine)

    try:
        handler({"partnumber": "PN1", "input": {}}, lambda *_: None)
    except RetryableWorkError as exc:
        assert exc.code == "TEMPORARY_RESEARCH_ERROR"
    else:
        raise AssertionError("expected RetryableWorkError")


def test_handler_maps_missing_product_to_no_data_found():
    engine = FakeEngine(error=LookupError("product not found: PN404"))
    handler = EnrichTechnicalHandler(engine)

    result = handler({"partnumber": "PN404", "input": {}}, lambda *_: None)

    assert result["status"] == "NO_DATA_FOUND"
    assert result["error_code"] == "PRODUCT_NOT_FOUND"
