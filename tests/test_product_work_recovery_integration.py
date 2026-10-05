from __future__ import annotations

from stech_mcp.services.product_work_dispatcher import (
    PermanentWorkError,
    ProductWorkDispatcher,
    RetryableWorkError,
)
from stech_mcp.worker import ProductWorkWorker


TERMINAL = {"COMPLETED", "PARTIAL", "REVIEW_REQUIRED", "NO_DATA_FOUND", "FAILED", "CANCELLED"}


class RecoveryRepository:
    """Small in-memory contract repo that mirrors Product Work recovery semantics."""

    def __init__(self):
        self.items = {
            1: self._item(1, "PN1"),
            2: self._item(2, "PN2"),
            3: self._item(3, "PN3"),
        }
        self.events = []
        self.attempt_ends = []
        self.attempt_rows = []
        self.job_status = "PENDING"

    @staticmethod
    def _item(item_id, pn):
        return {
            "item_id": item_id,
            "job_id": 77,
            "partnumber": pn,
            "work_type": "ENRICH_TECHNICAL",
            "status": "QUEUED",
            "attempt_count": 0,
            "max_attempts": 3,
            "claimed_by": None,
            "claim_expired": False,
            "next_attempt_at": None,
        }

    def claim_next(self, worker_id, lease_seconds):
        del lease_seconds
        for item_id in sorted(self.items):
            item = self.items[item_id]
            if item["status"] not in {"QUEUED", "FAILED_RETRYABLE"}:
                continue
            if item["claimed_by"] is not None:
                continue
            if item["attempt_count"] >= item["max_attempts"]:
                continue
            item["claimed_by"] = worker_id
            item["attempt_count"] += 1
            return dict(item)
        return None

    def force_abandoned_claim(self, item_id):
        item = self.items[item_id]
        item["claimed_by"] = "dead-worker"
        item["attempt_count"] += 1
        item["status"] = "RESEARCHING"
        item["claim_expired"] = True

    def release_expired_claims(self):
        count = 0
        for item in self.items.values():
            if not item["claim_expired"] or item["status"] in TERMINAL:
                continue
            item["status"] = "FAILED" if item["attempt_count"] >= item["max_attempts"] else "FAILED_RETRYABLE"
            item["claimed_by"] = None
            item["claim_expired"] = False
            item["last_error_code"] = "WORKER_LEASE_EXPIRED"
            count += 1
        return count

    def transition_item(self, item_id, *, status, current_step=None, progress_pct=None, error_code=None, error_detail=None):
        item = self.items[item_id]
        item["status"] = status
        if current_step is not None:
            item["current_step"] = current_step
        if progress_pct is not None:
            item["progress_pct"] = progress_pct
        item["last_error_code"] = error_code
        item["last_error_detail"] = error_detail
        if status in TERMINAL:
            item["claimed_by"] = None
        return dict(item)

    def schedule_retry(self, item_id, *, error_code, error_detail, delay_seconds):
        item = self.items[item_id]
        item["status"] = "FAILED" if item["attempt_count"] >= item["max_attempts"] else "FAILED_RETRYABLE"
        item["claimed_by"] = None
        item["next_attempt_at"] = delay_seconds
        item["last_error_code"] = error_code
        item["last_error_detail"] = error_detail
        return dict(item)

    def renew_claim(self, item_id, worker_id, lease_seconds):
        del lease_seconds
        return self.items[item_id]["claimed_by"] == worker_id

    def record_attempt_start(self, item, worker_id):
        attempt_id = len(self.attempt_rows) + 1
        row = {
            "attempt_id": attempt_id,
            "attempt_number": item["attempt_count"],
            "item_id": item["item_id"],
            "worker_id": worker_id,
        }
        self.attempt_rows.append(row)
        return row

    def record_attempt_end(self, attempt_id, *, outcome_status, error_code=None, error_detail=None):
        self.attempt_ends.append((attempt_id, outcome_status, error_code, error_detail))

    def record_event(self, item, event_type, *, status=None, detail=None):
        self.events.append((item["item_id"], event_type, status, detail))

    def refresh_job_summary(self, job_id):
        assert job_id == 77
        states = [item["status"] for item in self.items.values()]
        active = [state for state in states if state not in TERMINAL]
        if active:
            self.job_status = "RUNNING"
        elif all(state == "COMPLETED" for state in states):
            self.job_status = "COMPLETED"
        elif all(state == "FAILED" for state in states):
            self.job_status = "FAILED"
        else:
            self.job_status = "PARTIAL"
        return {"job_id": job_id, "status": self.job_status}


def test_job_survives_abandoned_claim_retry_and_permanent_failure():
    repo = RecoveryRepository()

    # Simulate PC/process death while PN1 is already mid-research.
    repo.force_abandoned_claim(1)
    assert repo.items[1]["status"] == "RESEARCHING"

    dispatcher = ProductWorkDispatcher()
    pn2_calls = {"count": 0}

    def handler(item, progress):
        pn = item["partnumber"]
        progress("ANALYZING_MISSING_FIELDS", 20)
        if pn == "PN2":
            pn2_calls["count"] += 1
            if pn2_calls["count"] == 1:
                raise RetryableWorkError("SOURCE_TIMEOUT", "temporary source timeout")
        if pn == "PN3":
            raise PermanentWorkError("INVALID_PRODUCT", "permanent product error")
        progress("REBUILDING_PRODUCT_MASTER", 90)
        return {"status": "COMPLETED"}

    dispatcher.register("ENRICH_TECHNICAL", handler)
    worker = ProductWorkWorker(repo, dispatcher, worker_id="replacement-worker", lease_seconds=120)

    # Startup recovery converts the abandoned nonterminal claim into reclaimable work.
    assert repo.release_expired_claims() == 1
    assert repo.items[1]["status"] == "FAILED_RETRYABLE"
    assert repo.items[1]["last_error_code"] == "WORKER_LEASE_EXPIRED"

    while worker.run_once():
        pass

    assert repo.items[1]["status"] == "COMPLETED"
    assert repo.items[1]["attempt_count"] == 2  # dead worker + replacement worker
    assert repo.items[2]["status"] == "COMPLETED"
    assert repo.items[2]["attempt_count"] == 2  # first timeout + retry
    assert repo.items[3]["status"] == "FAILED"
    assert repo.items[3]["attempt_count"] == 1
    assert repo.job_status == "PARTIAL"
    assert repo.events
    assert any(event[1] == "RETRY_SCHEDULED" for event in repo.events)
    assert any(event[1] == "FAILED" and event[0] == 3 for event in repo.events)
