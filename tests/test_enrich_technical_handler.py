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


class FakeIdentityService:
    def __init__(self, result):
        self.result = dict(result)
        self.calls = []

    def research(self, partnumber, requested_fields, progress):
        self.calls.append((partnumber, requested_fields))
        progress("ANALYZING_MISSING_FIELDS", 10)
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


def test_handler_maps_identity_already_verified_without_using_technical_engine():
    engine = FakeEngine(error=AssertionError("technical engine must not run"))
    handler = EnrichTechnicalHandler(engine)
    identity = FakeIdentityService({
        "state": "COMPLETED",
        "result_code": "YA_VERIFICADO",
        "verified_fields": {"ean": "4006381333931"},
        "error_code": None,
    })
    handler.identity_service = identity
    progress = []

    result = handler(
        {"work_type": "RESEARCH_IDENTITY", "partnumber": "pn1", "input": {"requested_fields": ["ean", "upc", "gtin"]}},
        lambda state, pct: progress.append((state, pct)),
    )

    assert result["status"] == "COMPLETED"
    assert result["current_step"] == "YA_VERIFICADO"
    assert identity.calls == [("PN1", ["ean", "upc", "gtin"])]
    assert engine.calls == []
    assert progress == [("ANALYZING_MISSING_FIELDS", 10)]


def test_handler_maps_identity_conflict_to_review_required():
    handler = EnrichTechnicalHandler(FakeEngine())
    handler.identity_service = FakeIdentityService({
        "state": "REVIEW_REQUIRED",
        "result_code": "REVIEW_REQUIRED",
        "verified_fields": {},
        "error_code": "IDENTITY_CONFLICT",
    })

    result = handler(
        {"work_type": "RESEARCH_IDENTITY", "partnumber": "PN1", "input": {}},
        lambda *_: None,
    )

    assert result["status"] == "REVIEW_REQUIRED"
    assert result["current_step"] == "REVIEW_REQUIRED"
    assert result["error_code"] == "IDENTITY_CONFLICT"


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
