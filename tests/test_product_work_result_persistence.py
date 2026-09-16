from stech_mcp.services.product_work_dispatcher import ProductWorkDispatcher
from stech_mcp.worker import ProductWorkWorker


class ResultRepository:
    def __init__(self):
        self.item = {
            "item_id": 1,
            "job_id": 9,
            "partnumber": "PN1",
            "work_type": "RESEARCH_IDENTITY",
            "status": "QUEUED",
            "attempt_count": 0,
            "max_attempts": 3,
        }
        self.claimed = False
        self.terminal_result = None

    def claim_next(self, worker_id, lease_seconds):
        if self.claimed:
            return None
        self.claimed = True
        return dict(self.item)

    def record_attempt_start(self, item, worker_id):
        self.item["attempt_count"] += 1
        return {"attempt_id": 1, "attempt_number": self.item["attempt_count"]}

    def transition_item(self, item_id, *, status, current_step=None, progress_pct=None, error_code=None, error_detail=None, result=None):
        self.item["status"] = status
        if current_step is not None:
            self.item["current_step"] = current_step
        if progress_pct is not None:
            self.item["progress_pct"] = progress_pct
        self.item["last_error_code"] = error_code
        self.item["last_error_detail"] = error_detail
        if result is not None:
            self.terminal_result = result
            self.item["result"] = result
        return dict(self.item)

    def renew_claim(self, *args):
        return True

    def record_attempt_end(self, *args, **kwargs):
        pass

    def record_event(self, *args, **kwargs):
        pass

    def refresh_job_summary(self, job_id):
        return {"job_id": job_id}


def test_worker_passes_structured_handler_result_to_terminal_transition():
    repository = ResultRepository()
    dispatcher = ProductWorkDispatcher()

    class Handler:
        aliases = ("RESEARCH_IDENTITY",)

        def __call__(self, item, progress):
            return {
                "status": "COMPLETED",
                "current_step": "VTEX_EAN_SYNCED",
                "result": {
                    "partnumber": "PN1",
                    "decision": "PROMOTED",
                    "verified_fields": {"upc": "740617352214"},
                    "vtex_state": "VTEX_EAN_SYNCED",
                },
            }

    dispatcher.register("ENRICH_TECHNICAL", Handler())
    worker = ProductWorkWorker(repository, dispatcher, worker_id="worker-result")

    assert worker.run_once() is True
    assert repository.terminal_result == {
        "partnumber": "PN1",
        "decision": "PROMOTED",
        "verified_fields": {"upc": "740617352214"},
        "vtex_state": "VTEX_EAN_SYNCED",
    }
