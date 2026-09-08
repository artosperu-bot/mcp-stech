from __future__ import annotations

from stech_mcp.services.product_work_dispatcher import (
    PermanentWorkError,
    ProductWorkDispatcher,
    RetryableWorkError,
    enrichment_handler_not_installed,
)
from stech_mcp.worker import ProductWorkWorker, retry_delay_seconds


class FakeRepository:
    def __init__(self, items):
        self.items = {item["item_id"]: dict(item) for item in items}
        self.queue = [item["item_id"] for item in items]
        self.renewals = []
        self.events = []
        self.attempt_ends = []
        self.released = 0

    def claim_next(self, worker_id, lease_seconds):
        if not self.queue:
            return None
        item_id = self.queue.pop(0)
        item = self.items[item_id]
        item["claimed_by"] = worker_id
        return dict(item)

    def transition_item(self, item_id, *, status, current_step=None, progress_pct=None, error_code=None, error_detail=None):
        item = self.items[item_id]
        item["status"] = status
        if current_step is not None:
            item["current_step"] = current_step
        if progress_pct is not None:
            item["progress_pct"] = progress_pct
        item["last_error_code"] = error_code
        item["last_error_detail"] = error_detail
        return dict(item)

    def schedule_retry(self, item_id, *, error_code, error_detail, delay_seconds):
        item = self.items[item_id]
        item["status"] = "FAILED_RETRYABLE"
        item["attempt_count"] = item.get("attempt_count", 0) + 1
        item["next_attempt_at"] = delay_seconds
        item["last_error_code"] = error_code
        item["last_error_detail"] = error_detail
        return dict(item)

    def renew_claim(self, item_id, worker_id, lease_seconds):
        self.renewals.append((item_id, worker_id, lease_seconds))
        return True

    def record_attempt_start(self, item, worker_id):
        return {"attempt_id": len(self.attempt_ends) + 1, "attempt_number": item.get("attempt_count", 0) + 1}

    def record_attempt_end(self, attempt_id, *, outcome_status, error_code=None, error_detail=None):
        self.attempt_ends.append((attempt_id, outcome_status, error_code, error_detail))

    def record_event(self, item, event_type, *, status=None, detail=None):
        self.events.append((item["item_id"], event_type, status, detail))

    def refresh_job_summary(self, job_id):
        return {"job_id": job_id}

    def release_expired_claims(self):
        self.released += 1
        return 0


def _item(item_id, partnumber, work_type="ENRICH_TECHNICAL", attempt_count=0):
    return {
        "item_id": item_id,
        "job_id": 7,
        "partnumber": partnumber,
        "work_type": work_type,
        "status": "QUEUED",
        "attempt_count": attempt_count,
    }


def test_worker_failure_does_not_stop_next_item():
    repo = FakeRepository([_item(1, "BAD"), _item(2, "GOOD")])
    dispatcher = ProductWorkDispatcher()

    def handler(item, progress):
        progress("ANALYZING_MISSING_FIELDS", 10)
        if item["partnumber"] == "BAD":
            raise PermanentWorkError("INVALID_PRODUCT", "bad product")
        progress("REBUILDING_PRODUCT_MASTER", 90)
        return {"status": "COMPLETED"}

    dispatcher.register("ENRICH_TECHNICAL", handler)
    worker = ProductWorkWorker(repo, dispatcher, worker_id="worker-a", lease_seconds=120)

    assert worker.run_once() is True
    assert worker.run_once() is True
    assert repo.items[1]["status"] == "FAILED"
    assert repo.items[2]["status"] == "COMPLETED"


def test_retryable_failure_gets_deterministic_backoff_and_releases_claim():
    repo = FakeRepository([_item(1, "PN1", attempt_count=0)])
    dispatcher = ProductWorkDispatcher()

    def handler(item, progress):
        progress("ANALYZING_MISSING_FIELDS", 10)
        raise RetryableWorkError("SOURCE_TIMEOUT", "temporary")

    dispatcher.register("ENRICH_TECHNICAL", handler)
    worker = ProductWorkWorker(repo, dispatcher, worker_id="worker-a", lease_seconds=120)
    worker.run_once()

    item = repo.items[1]
    assert item["status"] == "FAILED_RETRYABLE"
    assert item["next_attempt_at"] == 60
    assert retry_delay_seconds(1) == 60
    assert retry_delay_seconds(2) == 120
    assert retry_delay_seconds(99) == 3600


def test_progress_callback_renews_lease_before_state_update():
    repo = FakeRepository([_item(1, "PN1")])
    dispatcher = ProductWorkDispatcher()

    def handler(item, progress):
        progress("ANALYZING_MISSING_FIELDS", 25)
        progress("REBUILDING_PRODUCT_MASTER", 95)
        return {"status": "COMPLETED"}

    dispatcher.register("ENRICH_TECHNICAL", handler)
    worker = ProductWorkWorker(repo, dispatcher, worker_id="worker-a", lease_seconds=180)
    worker.run_once()

    assert repo.renewals == [(1, "worker-a", 180), (1, "worker-a", 180)]


def test_unknown_work_type_becomes_permanent_failure():
    repo = FakeRepository([_item(1, "PN1", work_type="UNKNOWN")])
    worker = ProductWorkWorker(repo, ProductWorkDispatcher(), worker_id="worker-a")
    worker.run_once()

    assert repo.items[1]["status"] == "FAILED"
    assert repo.items[1]["last_error_code"] == "UNSUPPORTED_WORK_TYPE"


def test_placeholder_enrichment_stops_for_review_instead_of_fake_success():
    repo = FakeRepository([_item(1, "PN1")])
    dispatcher = ProductWorkDispatcher()
    dispatcher.register("ENRICH_TECHNICAL", enrichment_handler_not_installed)
    worker = ProductWorkWorker(repo, dispatcher, worker_id="worker-a")
    worker.run_once()

    assert repo.items[1]["status"] == "REVIEW_REQUIRED"
    assert repo.items[1]["last_error_code"] == "ENRICHMENT_HANDLER_NOT_INSTALLED"


def test_worker_releases_expired_claims_only_when_loop_starts():
    repo = FakeRepository([])
    worker = ProductWorkWorker(repo, ProductWorkDispatcher(), worker_id="worker-a", sleep_fn=lambda _: None)

    class StopAfterFirstWait:
        def __init__(self): self.calls = 0
        def is_set(self):
            self.calls += 1
            return self.calls > 1

    worker.run_forever(StopAfterFirstWait())
    assert repo.released == 1
